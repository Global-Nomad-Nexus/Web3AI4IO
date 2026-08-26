#!/usr/bin/env python3
"""Register or execute the fixed 60-call Telegram targeted replication."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_agentic_v2_all import runtime_environment
from trustworthy_launchpads.agentic_v2 import PromptPacket
from trustworthy_launchpads.agentic_v2_providers import (
    ProviderError, build_request_body, extract_json_object, invoke, load_model_specs,
    preflight, redact_text, repair_packet, validate_response_against_schema,
)
from trustworthy_launchpads.telegram_replication import (
    CONDITIONS, EVIDENCE_IDS, EXPERIMENT_VERSION, OUTPUT_SCHEMA, SCHEMA_NAME,
    build_evidence_blocks, build_prompt_packet, build_registry,
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n", encoding="utf-8")


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def git_commit() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def merge_resume(fresh: pd.DataFrame, path: Path, resume: bool) -> pd.DataFrame:
    if not resume or not path.exists():
        return fresh
    prior = pd.read_csv(path, keep_default_na=False).set_index("call_id", drop=False)
    rows = []
    immutable = {
        "call_id", "experiment_version", "case_id", "model_spec_id", "provider", "requested_model",
        "condition_id", "condition_family", "present_evidence_ids", "missing_evidence_ids", "run_id",
        "seed", "prompt_hash", "evidence_hash", "audit_packet_id",
    }
    for row in fresh.to_dict(orient="records"):
        old = prior.loc[row["call_id"]] if row["call_id"] in prior.index else None
        if old is None:
            rows.append(row)
            continue
        if str(old["prompt_hash"]) != row["prompt_hash"] or str(old["evidence_hash"]) != row["evidence_hash"]:
            raise ValueError(f"Prompt or evidence changed for resumable call {row['call_id']}")
        rows.append({key: row[key] if key in immutable else old[key] for key in fresh.columns})
    return pd.DataFrame(rows, columns=fresh.columns)


def normalize_interrupted_registry(path: Path) -> int:
    """Atomically return stale in-flight slots to the resumable not-run state."""

    if not path.exists():
        return 0
    registry = pd.read_csv(path, keep_default_na=False)
    interrupted = registry["status"].astype(str).eq("running")
    count = int(interrupted.sum())
    if count:
        registry.loc[interrupted, "status"] = "registered_not_run"
        registry.loc[interrupted, "started_at_utc"] = ""
        registry.loc[interrupted, "completed_at_utc"] = ""
        registry.loc[interrupted, "error"] = "interrupted_before_terminal_response; safe_to_resume"
        atomic_csv(path, registry)
    return count


def register(output: Path, experiment: Mapping[str, Any], specs: list[dict[str, Any]], registry: pd.DataFrame) -> dict[str, PromptPacket]:
    blocks = build_evidence_blocks(REPO)
    packets = {condition: build_prompt_packet(condition, blocks) for condition in CONDITIONS}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "evidence_blocks.json", {key: value.as_dict() for key, value in blocks.items()})
    write_json(output / "condition_manifest.json", [
        {"condition_id": condition, "present_evidence_ids": list(present),
         "missing_evidence_ids": [item for item in EVIDENCE_IDS if item not in present]}
        for condition, present in CONDITIONS.items()
    ])
    for condition, packet in packets.items():
        write_json(output / "prompts" / f"{condition}.json", {"condition_id": condition, **packet.as_dict()})
    write_json(output / "experiment_manifest.json", {
        "experiment_version": EXPERIMENT_VERSION, "case_id": experiment["case_id"],
        "registered_calls": 60, "runs_per_cell": 10, "conditions": 2,
        "models": [{key: value for key, value in spec.items() if key not in {"api_key", "headers"}} for spec in specs],
        "random_seed": experiment["random_seed"], "temperature": 0,
        "git_commit": git_commit(), "python": platform.python_version(), "created_at_utc": utc_now(),
        "external_upload_boundary": "only the two aggregate Telegram evidence blocks; no manuscript, token rows, transactions, wallets, or claim-boundary text",
        "analysis_scope": "targeted two-condition case replication; not population-level generalization or model ranking",
    })
    atomic_csv(output / "run_registry.csv", registry)
    return packets


def run(output: Path, registry: pd.DataFrame, specs: list[dict[str, Any]], packets: Mapping[str, PromptPacket], timeout: float, resume: bool) -> pd.DataFrame:
    by_id = {str(spec["model_spec_id"]): spec for spec in specs}
    preflights = {}
    pending_models = {
        str(row.model_spec_id) for row in registry.itertuples()
        if not (resume and str(row.status) in {"ok", "parse_failed", "provider_error"})
    }
    for model_id in sorted(pending_models):
        info = preflight(by_id[model_id], timeout=min(timeout, 20.0))
        expected = str(by_id[model_id].get("expected_model_digest_prefix", ""))
        if expected and not str(info.get("model_digest", "")).startswith(expected):
            raise ProviderError(f"Ollama digest mismatch for {model_id}")
        preflights[model_id] = info
    write_json(output / "provider_preflight.json", preflights)

    current_commit = git_commit()
    for index, row in registry.iterrows():
        if resume and str(row["status"]) in {"ok", "parse_failed", "provider_error"}:
            continue
        spec = dict(by_id[str(row["model_spec_id"])])
        spec["seed"] = int(row["seed"])
        packet = packets[str(row["condition_id"])]
        call_dir = output / "calls" / str(row["call_id"])
        request = build_request_body(spec, packet, output_schema=OUTPUT_SCHEMA, schema_name=SCHEMA_NAME)
        write_json(call_dir / "prompt.json", {"call_id": row["call_id"], "condition_id": row["condition_id"], **packet.as_dict()})
        write_json(call_dir / "request.json", request)
        registry.at[index, "started_at_utc"] = utc_now()
        registry.at[index, "status"] = "running"
        atomic_csv(output / "run_registry.csv", registry)
        secret = os.environ.get(str(spec.get("api_key_env", "")), "")
        try:
            result = invoke(spec, packet, timeout=timeout, output_schema=OUTPUT_SCHEMA, schema_name=SCHEMA_NAME)
            write_json(call_dir / "response.json", result.raw_response)
            write_json(call_dir / "response_text.json", {"content": result.response_text})
            total_input, total_output = result.input_tokens, result.output_tokens
            total_reasoning, total_cost = result.reasoning_tokens, result.estimated_cost_usd
            repair_attempted = 0
            try:
                parsed = validate_response_against_schema(
                    extract_json_object(result.response_text), output_schema=OUTPUT_SCHEMA, evidence_ids=EVIDENCE_IDS
                )
            except ValueError as first_error:
                repair_attempted = 1
                repair = repair_packet(result.response_text, output_schema=OUTPUT_SCHEMA)
                repair_request = build_request_body(spec, repair, output_schema=OUTPUT_SCHEMA, schema_name=SCHEMA_NAME)
                write_json(call_dir / "repair_request.json", repair_request)
                repaired = invoke(spec, repair, timeout=timeout, output_schema=OUTPUT_SCHEMA, schema_name=SCHEMA_NAME)
                write_json(call_dir / "repair_response.json", repaired.raw_response)
                total_input += repaired.input_tokens; total_output += repaired.output_tokens
                total_reasoning += repaired.reasoning_tokens; total_cost += repaired.estimated_cost_usd
                try:
                    parsed = validate_response_against_schema(
                        extract_json_object(repaired.response_text), output_schema=OUTPUT_SCHEMA, evidence_ids=EVIDENCE_IDS
                    )
                except ValueError as second_error:
                    parsed = None
                    registry.at[index, "status"] = "parse_failed"
                    registry.at[index, "error"] = redact_text(f"Initial parse: {first_error}; repair parse: {second_error}", [secret])[:1200]
            if parsed is not None:
                write_json(call_dir / "parsed.json", parsed)
                registry.at[index, "status"] = "ok"; registry.at[index, "error"] = ""
            registry.at[index, "returned_model"] = result.returned_model
            registry.at[index, "model_digest"] = result.model_digest or str(preflights.get(str(row["model_spec_id"]), {}).get("model_digest", ""))
            registry.at[index, "input_tokens"] = total_input; registry.at[index, "output_tokens"] = total_output
            registry.at[index, "reasoning_tokens"] = total_reasoning
            registry.at[index, "estimated_cost_usd"] = round(total_cost, 10)
            registry.at[index, "parse_repair_attempted"] = repair_attempted
        except (ProviderError, ValueError) as exc:
            registry.at[index, "status"] = "provider_error"
            registry.at[index, "error"] = redact_text(str(exc), [secret])[:1200]
        registry.at[index, "completed_at_utc"] = utc_now()
        write_json(call_dir / "provenance.json", {
            "call_id": row["call_id"], "git_commit": current_commit, "provider": row["provider"],
            "requested_model": row["requested_model"], "returned_model": registry.at[index, "returned_model"],
            "model_digest": registry.at[index, "model_digest"], "prompt_hash": row["prompt_hash"],
            "evidence_hash": row["evidence_hash"], "seed": int(row["seed"]), "status": registry.at[index, "status"],
            "started_at_utc": registry.at[index, "started_at_utc"], "completed_at_utc": registry.at[index, "completed_at_utc"],
            "token_usage": {"input": registry.at[index, "input_tokens"], "output": registry.at[index, "output_tokens"], "reasoning": registry.at[index, "reasoning_tokens"]},
            "parse_repair_attempted": int(registry.at[index, "parse_repair_attempted"]), "error": registry.at[index, "error"],
        })
        atomic_csv(output / "run_registry.csv", registry)
        done = int(registry["status"].astype(str).isin({"ok", "parse_failed", "provider_error"}).sum())
        print(f"progress {done}/60: {row['model_spec_id']} {row['condition_id']} run={row['run_id']} status={registry.at[index, 'status']}", flush=True)
    return registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-config", default=str(ROOT / "configs" / "telegram_replication.json"))
    parser.add_argument("--model-panel", default="all")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()
    experiment = json.loads(Path(args.experiment_config).read_text(encoding="utf-8"))
    if experiment["experiment_version"] != EXPERIMENT_VERSION:
        raise SystemExit("Experiment version mismatch")
    os.environ.update(runtime_environment())
    specs = load_model_specs(experiment, args.model_panel)
    blocks = build_evidence_blocks(REPO)
    packets = {condition: build_prompt_packet(condition, blocks) for condition in CONDITIONS}
    fresh = build_registry(specs, packets, runs=int(experiment["runs_per_cell"]), seed=int(experiment["random_seed"]))
    output = Path(args.output_dir).expanduser().resolve() if args.output_dir else (ROOT / experiment["output_root"]).resolve()
    registry_path = output / "run_registry.csv"
    if args.resume and not args.dry_run:
        recovered = normalize_interrupted_registry(registry_path)
        if recovered:
            print(f"Recovered {recovered} interrupted slot(s); completed calls remain untouched.", flush=True)
    registry = merge_resume(fresh, registry_path, args.resume and not args.dry_run)
    packets = register(output, experiment, specs, registry)
    if args.dry_run:
        print(f"Registered exactly {len(registry)} calls at {output}; no provider was contacted.")
        return
    try:
        registry = run(output, registry, specs, packets, args.timeout, args.resume)
    except KeyboardInterrupt:
        recovered = normalize_interrupted_registry(registry_path)
        print(
            f"Interrupted safely. Recovered {recovered} in-flight slot(s); "
            "rerun the same command to resume.",
            flush=True,
        )
        raise SystemExit(130) from None
    print(json.dumps({"output_dir": str(output), "status_counts": registry["status"].value_counts().sort_index().to_dict()}, indent=2))


if __name__ == "__main__":
    main()
