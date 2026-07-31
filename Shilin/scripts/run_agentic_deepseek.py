#!/usr/bin/env python3
"""Run registered Shilin agentic prompts with the DeepSeek chat API.

The script reads an API key from the environment or from a local .env file,
appends a compact, versioned artifact bundle to each registered L0--L7 prompt,
and writes artifacts/agent_runs/agent_runs.csv plus raw response JSON files.
API keys are never written to disk.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.agentic import RUN_SCHEMA, prompt_hash
from trustworthy_launchpads.io import load_config


DEFAULT_ENV_PATH = Path("/Users/oushilin/Desktop/SRS/02_Shanghai_Library_Project/StableTrade_Atlas_ODC-main/.env")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def artifact_table(path: Path, *, rows: int = 12, columns: list[str] | None = None) -> str:
    if not path.exists():
        return f"[missing: {path.name}]"
    frame = pd.read_csv(path)
    if columns:
        keep = [column for column in columns if column in frame.columns]
        frame = frame.loc[:, keep]
    return frame.head(rows).to_csv(index=False)


def artifact_json(path: Path, *, max_chars: int = 2200) -> str:
    if not path.exists():
        return f"[missing: {path.name}]"
    payload = json.loads(path.read_text(encoding="utf-8"))
    text = json.dumps(payload, indent=2, sort_keys=True)
    return text[:max_chars]


def build_data_bundle(config_path: Path, rung: str) -> str:
    config = load_config(config_path)
    tables = config.tables_dir
    parts = [
        "Artifact bundle appended by run_agentic_deepseek.py.",
        f"Case id: {config.case_id}",
        f"Event date: {config.raw['event_date']} UTC",
        "Instruction: use only the evidence below. Do not invent unreported tables, Dune exports, or agent runs.",
    ]
    ladder = pd.read_csv(tables / "deterministic_ladder.csv")
    rung_index = int(rung[1:])
    ladder_slice = ladder.loc[ladder["rung"].str[1:].astype(int).le(rung_index)]
    parts.extend(
        [
            "\n[deterministic ladder available up to this rung]",
            ladder_slice[
                ["rung", "outcome", "estimate", "ci95_low", "ci95_high", "p_value", "worked_decision", "notes"]
            ].to_csv(index=False),
        ]
    )
    if rung in {"L0", "L1", "L2"}:
        parts.extend(
            [
                "\n[PyFixest DiD cross-check]",
                artifact_table(
                    tables / "pyfixest_did_crosscheck.csv",
                    columns=["spec_id", "estimate", "ci95_low", "ci95_high", "p_value", "interpretation"],
                ),
            ]
        )
    if rung in {"L3", "L4"}:
        parts.extend(
            [
                "\n[event-study coefficients]",
                artifact_table(
                    tables / "event_study_coefficients_shilin.csv",
                    rows=20,
                    columns=["rel_week", "coef", "ci95_low", "ci95_high", "reference_week"],
                ),
                "\n[pretrend diagnostics]",
                artifact_json(tables / "pretrend_diagnostics.json"),
            ]
        )
    if rung == "L5":
        parts.extend(
            [
                "\n[stakeholder metrics relevant to H1/H4]",
                artifact_table(
                    tables / "result1_stakeholder_metric_battery.csv",
                    rows=12,
                    columns=["dimension", "stakeholder", "metric", "unit", "value_label", "status", "interpretation"],
                ),
                "\n[HF Pump.fun latest-per-mint risk snapshot summary]",
                artifact_json(tables / "hf_pump_risk_snapshot_summary.json"),
            ]
        )
    if rung in {"L6", "L7"}:
        parts.extend(
            [
                "\n[wild-cluster bootstrap]",
                artifact_json(tables / "wild_cluster_bootstrap.json"),
                "\n[claim scope ledger]",
                artifact_table(tables / "claim_scope_ledger.csv", rows=8),
            ]
        )
    if rung == "L7":
        parts.extend(
            [
                "\n[data availability ledger]",
                artifact_table(tables / "data_availability_ledger.csv", rows=20),
                "\n[frequency and data-richness sensitivity]",
                artifact_table(tables / "result1_frequency_sensitivity.csv", rows=20),
            ]
        )
    return "\n".join(parts)


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def deepseek_chat(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> dict[str, Any]:
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        DEEPSEEK_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def mention_flags(text: str) -> dict[str, int]:
    lower = text.lower()
    return {
        "mentions_control_group": int(any(term in lower for term in ["control group", "control", "did"])),
        "mentions_pretrend": int(any(term in lower for term in ["pre-trend", "pretrend", "parallel trend"])),
        "mentions_stakeholders": int(any(term in lower for term in ["stakeholder", "retail", "creator", "community"])),
        "mentions_uncertainty": int(any(term in lower for term in ["uncertain", "confidence interval", "ci", "p-value"])),
    }


def coerce_float(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return str(float(value))
    except (TypeError, ValueError):
        return ""


def coerce_confidence(value: Any) -> str:
    if value is None or value == "":
        return "0.0"
    if isinstance(value, str):
        lower = value.strip().lower()
        labels = {
            "very low": 0.1,
            "low": 0.25,
            "medium-low": 0.4,
            "medium": 0.5,
            "moderate": 0.5,
            "medium-high": 0.65,
            "high": 0.75,
            "very high": 0.9,
        }
        if lower in labels:
            return str(labels[lower])
        if lower.endswith("%"):
            try:
                return str(float(lower.rstrip("%")) / 100)
            except ValueError:
                return "0.0"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "0.0"
    if numeric > 1 and numeric <= 100:
        numeric = numeric / 100
    return str(max(0.0, min(1.0, numeric)))


def normalize_row(
    *,
    parsed: dict[str, Any],
    raw_text: str,
    case_id: str,
    rung: str,
    model: str,
    provider: str,
    run_id: int,
    temperature: float,
    prompt_digest: str,
    data_access: str,
    raw_response_path: str,
) -> dict[str, Any]:
    flags = mention_flags(raw_text + " " + json.dumps(parsed, ensure_ascii=False))
    decision = str(parsed.get("worked_decision") or "no_or_uncertain")
    confidence = coerce_confidence(parsed.get("self_reported_confidence"))
    return {
        "case_id": case_id,
        "rung": rung,
        "model": model,
        "provider": provider,
        "run_id": run_id,
        "run_date_utc": datetime.now(UTC).isoformat(),
        "temperature": temperature,
        "prompt_hash": prompt_digest,
        "data_access": data_access,
        "tools_allowed": "none; API runner appended local artifact bundle",
        "headline_estimate": coerce_float(parsed.get("headline_estimate")),
        "ci95_low": coerce_float(parsed.get("ci95_low")),
        "ci95_high": coerce_float(parsed.get("ci95_high")),
        "worked_decision": decision,
        "self_reported_confidence": confidence,
        **flags,
        "final_claim": str(parsed.get("final_claim") or raw_text[:240]).replace("\n", " "),
        "raw_response_path": raw_response_path,
    }


def write_agent_runs_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(RUN_SCHEMA))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in RUN_SCHEMA})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs" / "pumpswap_case.json"))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--runs-per-rung", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--max-tokens", type=int, default=900)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    env_values = load_env_file(Path(args.env_file).expanduser())
    api_key = os.environ.get("DEEPSEEK_API_KEY") or env_values.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY not found in environment or --env-file.")
    model = os.environ.get("DEEPSEEK_MODEL") or env_values.get("DEEPSEEK_MODEL") or "deepseek-chat"

    config = load_config(args.config)
    runs_per_rung = args.runs_per_rung or int(config.raw.get("agentic", {}).get("runs_per_rung_target", 10))
    temperature = (
        args.temperature
        if args.temperature is not None
        else float(config.raw.get("agentic", {}).get("temperature", 0))
    )
    agent_dir = config.agent_runs_dir
    raw_dir = agent_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = agent_dir / "agent_runs.csv"
    if out_path.exists() and not args.overwrite:
        raise SystemExit(f"{out_path} exists. Use --overwrite to replace it.")

    rows: list[dict[str, Any]] = []
    prompt_manifest = pd.read_csv(config.tables_dir / "agentic_prompt_manifest.csv")
    for rung in prompt_manifest["rung"].tolist():
        system_template = (config.project_root / f"prompts/{rung}_system.md").read_text(encoding="utf-8")
        user_template = (config.project_root / f"prompts/{rung}_user.md").read_text(encoding="utf-8")
        data_bundle = build_data_bundle(Path(args.config), rung)
        user_prompt = (
            f"{user_template}\n\n"
            "Return only a JSON object with these keys: headline_estimate, ci95_low, ci95_high, "
            "worked_decision, self_reported_confidence, final_claim. Use null for unavailable numeric fields.\n\n"
            f"{data_bundle}"
        )
        digest = prompt_hash(system_template, user_prompt)
        data_access = str(prompt_manifest.loc[prompt_manifest["rung"].eq(rung), "data_access"].iloc[0])
        for run_id in range(1, runs_per_rung + 1):
            raw_rel = Path("artifacts") / "agent_runs" / "raw" / f"{model}_{rung}_run{run_id:03d}.json"
            raw_path = config.project_root / raw_rel
            try:
                payload = deepseek_chat(
                    api_key=api_key,
                    model=model,
                    system_prompt=system_template,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=args.max_tokens,
                    timeout=args.timeout,
                )
                content = (
                    payload.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                parsed = extract_json_object(content)
                status = "ok"
                error = ""
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
                payload = {}
                content = ""
                parsed = {
                    "headline_estimate": None,
                    "ci95_low": None,
                    "ci95_high": None,
                    "worked_decision": "no_or_uncertain",
                    "self_reported_confidence": 0,
                    "final_claim": f"DeepSeek run failed: {type(exc).__name__}",
                }
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
            raw_path.write_text(
                json.dumps(
                    {
                        "status": status,
                        "error": error,
                        "model": model,
                        "rung": rung,
                        "run_id": run_id,
                        "temperature": temperature,
                        "prompt_hash": digest,
                        "content": content,
                        "api_response": payload,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            rows.append(
                normalize_row(
                    parsed=parsed,
                    raw_text=content,
                    case_id=config.case_id,
                    rung=rung,
                    model=model,
                    provider="DeepSeek",
                    run_id=run_id,
                    temperature=temperature,
                    prompt_digest=digest,
                    data_access=data_access,
                    raw_response_path=str(raw_rel),
                )
            )
            write_agent_runs_csv(out_path, rows)
            print(f"{rung} run {run_id}/{runs_per_rung}: {status}", flush=True)
            time.sleep(args.sleep)

    write_agent_runs_csv(out_path, rows)
    print(f"Wrote {out_path} with {len(rows)} rows.")


if __name__ == "__main__":
    main()
