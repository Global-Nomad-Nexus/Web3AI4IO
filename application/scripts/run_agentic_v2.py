#!/usr/bin/env python3
"""Register or run the three-model V2 evidence-ladder audit."""

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
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.agentic_v2 import (
    EXPERIMENT_VERSION,
    Condition,
    PromptPacket,
    build_call_registry,
    build_conditions,
    build_evidence_blocks,
    build_prompt_packet,
    validate_registry_shape,
)
from trustworthy_launchpads.agentic_v2_providers import (
    ProviderError,
    build_request_body,
    extract_json_object,
    invoke,
    load_model_specs,
    preflight,
    redact_text,
    repair_packet,
    validate_structured_response,
)
from trustworthy_launchpads.io import load_config


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_from_application(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            default=json_scalar_default,
        ),
        encoding="utf-8",
    )


def json_scalar_default(value: Any) -> Any:
    """Convert scalar values inferred by pandas/numpy into JSON-native values."""

    item = getattr(value, "item", None)
    if callable(item):
        converted = item()
        if converted is not value:
            return converted
    raise TypeError(
        f"Object of type {value.__class__.__name__} is not JSON serializable"
    )


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT.parent,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def prepare_prompts(
    *,
    case_config: Any,
    conditions: list[Condition],
    blocks: Mapping[str, Any],
    table_root: Path | None,
) -> dict[str, PromptPacket]:
    return {
        condition.condition_id: build_prompt_packet(
            case_config, condition, blocks, table_root=table_root
        )
        for condition in conditions
    }


def merge_resume(fresh: pd.DataFrame, existing_path: Path, *, resume: bool) -> pd.DataFrame:
    if not resume or not existing_path.exists():
        return fresh
    old = pd.read_csv(existing_path, keep_default_na=False)
    old_by_id = old.set_index("call_id", drop=False)
    rows: list[dict[str, Any]] = []
    for row in fresh.to_dict(orient="records"):
        call_id = row["call_id"]
        if call_id not in old_by_id.index:
            rows.append(row)
            continue
        previous = old_by_id.loc[call_id]
        if isinstance(previous, pd.DataFrame):
            raise ValueError(f"Existing registry has duplicate call_id: {call_id}")
        if str(previous["prompt_hash"]) != str(row["prompt_hash"]):
            raise ValueError(f"Prompt hash changed for resumable call {call_id}")
        if str(previous["evidence_hash"]) != str(row["evidence_hash"]):
            raise ValueError(f"Evidence hash changed for resumable call {call_id}")
        merged = dict(row)
        for column in fresh.columns:
            if column in previous.index and column not in {
                "experiment_version",
                "case_id",
                "model_spec_id",
                "provider",
                "requested_model",
                "condition_id",
                "condition_family",
                "canonical_rung",
                "factorial_bits",
                "present_evidence_ids",
                "missing_evidence_ids",
                "leakage_expected",
                "run_id",
                "seed",
                "prompt_hash",
                "evidence_hash",
                "audit_packet_id",
            }:
                merged[column] = previous[column]
        rows.append(merged)
    return pd.DataFrame(rows, columns=fresh.columns)


def write_registration_artifacts(
    *,
    output_dir: Path,
    experiment: Mapping[str, Any],
    case_config: Any,
    model_specs: list[dict[str, Any]],
    conditions: list[Condition],
    blocks: Mapping[str, Any],
    packets: Mapping[str, PromptPacket],
    registry: pd.DataFrame,
    selection: str,
    runs_per_cell: int,
    control_repeats: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "evidence_blocks.json", {key: value.as_dict() for key, value in blocks.items()})
    write_json(
        output_dir / "condition_manifest.json",
        [
            {
                "condition_id": condition.condition_id,
                "family": condition.family,
                "canonical_rung": condition.canonical_rung,
                "factorial_bits": condition.factorial_bits,
                "present_evidence_ids": list(condition.present_evidence_ids),
                "missing_evidence_ids": list(condition.missing_evidence_ids),
                "leakage_expected": condition.leakage_expected,
            }
            for condition in conditions
        ],
    )
    for condition in conditions:
        packet = packets[condition.condition_id]
        write_json(
            output_dir / "prompts" / f"{condition.condition_id}.json",
            {
                **packet.as_dict(),
                "condition_id": condition.condition_id,
                "condition_family": condition.family,
                "leakage_expected": condition.leakage_expected,
            },
        )
    safe_models = [
        {
            key: value
            for key, value in spec.items()
            if key not in {"api_key", "authorization", "headers"}
        }
        for spec in model_specs
    ]
    write_json(
        output_dir / "experiment_manifest.json",
        {
            "experiment_version": EXPERIMENT_VERSION,
            "case_id": case_config.case_id,
            "condition_selection": selection,
            "runs_per_cell": runs_per_cell,
            "control_repeats": control_repeats,
            "registered_calls": int(len(registry)),
            "models": safe_models,
            "random_seed": int(experiment["random_seed"]),
            "git_commit": git_commit(),
            "python": platform.python_version(),
            "created_at_utc": utc_now(),
            "external_upload_boundary": "aggregate evidence blocks only; no manuscript, transactions, or wallet-level data",
            "confidence_policy": "exploratory_only_not_calibration",
        },
    )
    atomic_csv(output_dir / "run_registry.csv", registry)


def selected_cell_keys(registry: pd.DataFrame, max_cells: int) -> set[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in registry.to_dict(orient="records"):
        key = (str(row["model_spec_id"]), str(row["condition_id"]))
        if key not in seen:
            keys.append(key)
            seen.add(key)
    if max_cells > 0:
        keys = keys[:max_cells]
    return set(keys)


def pending_model_ids(
    registry: pd.DataFrame,
    allowed_cells: set[tuple[str, str]],
    *,
    resume: bool,
) -> set[str]:
    return {
        str(row["model_spec_id"])
        for row in registry.to_dict(orient="records")
        if (str(row["model_spec_id"]), str(row["condition_id"])) in allowed_cells
        and not (resume and str(row["status"]) == "ok")
    }


def archive_call_base(
    call_dir: Path,
    row: Mapping[str, Any],
    packet: PromptPacket,
    request_body: Mapping[str, Any],
) -> None:
    write_json(
        call_dir / "prompt.json",
        {
            **packet.as_dict(),
            "call_id": row["call_id"],
            "condition_id": row["condition_id"],
            "leakage_expected": bool(int(row["leakage_expected"])),
        },
    )
    write_json(call_dir / "request.json", dict(request_body))


def run_calls(
    *,
    output_dir: Path,
    registry: pd.DataFrame,
    model_specs: list[dict[str, Any]],
    packets: Mapping[str, PromptPacket],
    resume: bool,
    max_cells: int,
    timeout: float,
) -> pd.DataFrame:
    specs = {str(item["model_spec_id"]): item for item in model_specs}
    allowed_cells = selected_cell_keys(registry, max_cells)
    models_to_run = pending_model_ids(registry, allowed_cells, resume=resume)
    preflight_path = output_dir / "provider_preflight.json"
    preflights: dict[str, dict[str, Any]] = (
        read_json(preflight_path) if preflight_path.exists() else {}
    )
    for model_id, spec in specs.items():
        if model_id not in models_to_run:
            continue
        info = preflight(spec, timeout=min(timeout, 20.0))
        expected = str(spec.get("expected_model_digest_prefix", ""))
        observed = str(info.get("model_digest", ""))
        if expected and not observed.startswith(expected):
            raise ProviderError(
                f"Ollama digest mismatch for {model_id}: expected prefix {expected}, observed {observed}"
            )
        preflights[model_id] = info
    write_json(preflight_path, preflights)

    registry = registry.copy()
    current_commit = git_commit()
    for index, row in registry.iterrows():
        cell = (str(row["model_spec_id"]), str(row["condition_id"]))
        if cell not in allowed_cells:
            continue
        if resume and str(row["status"]) == "ok":
            continue
        spec = dict(specs[str(row["model_spec_id"])])
        spec["seed"] = int(row["seed"])
        packet = packets[str(row["condition_id"])]
        call_dir = output_dir / "calls" / str(row["call_id"])
        request_body = build_request_body(spec, packet)
        archive_call_base(call_dir, row, packet, request_body)
        registry.at[index, "started_at_utc"] = utc_now()
        registry.at[index, "status"] = "running"
        atomic_csv(output_dir / "run_registry.csv", registry)
        secrets = [
            value
            for env_name in (str(spec.get("api_key_env", "")),)
            if env_name and (value := os.environ.get(env_name, ""))
        ]
        try:
            result = invoke(spec, packet, timeout=timeout)
            write_json(call_dir / "response.json", result.raw_response)
            write_json(call_dir / "response_text.json", {"content": result.response_text})
            repair_attempted = 0
            total_input = result.input_tokens
            total_output = result.output_tokens
            total_reasoning = result.reasoning_tokens
            total_cost = result.estimated_cost_usd
            returned_model = result.returned_model
            model_digest = result.model_digest or str(preflights[str(row["model_spec_id"])].get("model_digest", ""))
            try:
                parsed = validate_structured_response(extract_json_object(result.response_text))
            except ValueError as first_error:
                repair_attempted = 1
                repair = repair_packet(result.response_text)
                repair_request = build_request_body(spec, repair)
                write_json(call_dir / "repair_request.json", repair_request)
                repair_result = invoke(spec, repair, timeout=timeout)
                write_json(call_dir / "repair_response.json", repair_result.raw_response)
                total_input += repair_result.input_tokens
                total_output += repair_result.output_tokens
                total_reasoning += repair_result.reasoning_tokens
                total_cost += repair_result.estimated_cost_usd
                try:
                    parsed = validate_structured_response(extract_json_object(repair_result.response_text))
                except ValueError as second_error:
                    registry.at[index, "status"] = "parse_failed"
                    registry.at[index, "error"] = redact_text(
                        f"Initial parse: {first_error}; repair parse: {second_error}", secrets
                    )[:1200]
                    parsed = None
            if parsed is not None:
                write_json(call_dir / "parsed.json", parsed)
                registry.at[index, "status"] = "ok"
                registry.at[index, "error"] = ""
            registry.at[index, "returned_model"] = returned_model
            registry.at[index, "model_digest"] = model_digest
            registry.at[index, "input_tokens"] = total_input
            registry.at[index, "output_tokens"] = total_output
            registry.at[index, "reasoning_tokens"] = total_reasoning
            registry.at[index, "estimated_cost_usd"] = round(total_cost, 10)
            registry.at[index, "parse_repair_attempted"] = repair_attempted
        except (ProviderError, ValueError) as exc:
            registry.at[index, "status"] = "provider_error"
            registry.at[index, "error"] = redact_text(str(exc), secrets)[:1200]
        registry.at[index, "completed_at_utc"] = utc_now()
        write_json(
            call_dir / "provenance.json",
            {
                "call_id": row["call_id"],
                "git_commit": current_commit,
                "provider": row["provider"],
                "requested_model": row["requested_model"],
                "returned_model": registry.at[index, "returned_model"],
                "model_digest": registry.at[index, "model_digest"],
                "prompt_hash": row["prompt_hash"],
                "evidence_hash": row["evidence_hash"],
                "seed": int(row["seed"]),
                "status": registry.at[index, "status"],
                "started_at_utc": registry.at[index, "started_at_utc"],
                "completed_at_utc": registry.at[index, "completed_at_utc"],
                "token_usage": {
                    "input": registry.at[index, "input_tokens"],
                    "output": registry.at[index, "output_tokens"],
                    "reasoning": registry.at[index, "reasoning_tokens"],
                },
                "parse_repair_attempted": int(registry.at[index, "parse_repair_attempted"]),
                "error": registry.at[index, "error"],
            },
        )
        atomic_csv(output_dir / "run_registry.csv", registry)
    return registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experiment-config", default=str(ROOT / "configs" / "agentic_v2.json")
    )
    parser.add_argument("--model-panel", default="all")
    parser.add_argument(
        "--conditions", choices=["canonical", "factorial", "controls", "all"], default="all"
    )
    parser.add_argument("--runs-per-cell", type=int, default=None)
    parser.add_argument("--control-repeats", type=int, default=None)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-cells", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--table-root", default="")
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()

    experiment_path = Path(args.experiment_config).expanduser().resolve()
    experiment = read_json(experiment_path)
    if experiment.get("experiment_version") != EXPERIMENT_VERSION:
        raise SystemExit(
            f"Config version {experiment.get('experiment_version')} does not match {EXPERIMENT_VERSION}"
        )
    case_config = load_config(resolve_from_application(experiment["case_config"]))
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else resolve_from_application(experiment["output_root"])
    )
    table_root = Path(args.table_root).expanduser().resolve() if args.table_root else None
    runs_per_cell = args.runs_per_cell or int(experiment["runs_per_cell"])
    control_repeats = args.control_repeats or int(experiment["control_repeats"])
    model_specs = load_model_specs(experiment, args.model_panel)
    conditions = build_conditions(args.conditions)
    blocks = build_evidence_blocks(case_config, table_root=table_root)
    packets = prepare_prompts(
        case_config=case_config,
        conditions=conditions,
        blocks=blocks,
        table_root=table_root,
    )
    fresh = build_call_registry(
        config=case_config,
        model_specs=model_specs,
        conditions=conditions,
        prompt_packets=packets,
        runs_per_cell=runs_per_cell,
        control_repeats=control_repeats,
        random_seed=int(experiment["random_seed"]),
    )
    validate_registry_shape(
        fresh,
        selection=args.conditions,
        model_count=len(model_specs),
        runs=runs_per_cell,
        controls=control_repeats,
    )
    registry_path = output_dir / "run_registry.csv"
    registry = merge_resume(fresh, registry_path, resume=args.resume and not args.dry_run)
    write_registration_artifacts(
        output_dir=output_dir,
        experiment=experiment,
        case_config=case_config,
        model_specs=model_specs,
        conditions=conditions,
        blocks=blocks,
        packets=packets,
        registry=registry,
        selection=args.conditions,
        runs_per_cell=runs_per_cell,
        control_repeats=control_repeats,
    )
    if args.dry_run:
        print(f"Registered {len(registry)} calls at {output_dir}; no provider was contacted.")
        return
    registry = run_calls(
        output_dir=output_dir,
        registry=registry,
        model_specs=model_specs,
        packets=packets,
        resume=args.resume,
        max_cells=args.max_cells,
        timeout=args.timeout,
    )
    counts = registry["status"].astype(str).value_counts().sort_index().to_dict()
    print(json.dumps({"output_dir": str(output_dir), "status_counts": counts}, indent=2))


if __name__ == "__main__":
    main()
