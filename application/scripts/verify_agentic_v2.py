#!/usr/bin/env python3
"""Fail-closed integrity verification for V2 registration and run artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.agentic_v2 import PRIMARY_FORBIDDEN_MARKERS


SECRET_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
TERMINAL_STATUSES = {"ok", "parse_failed", "provider_error", "registered_not_run"}


def resolve(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def hash_prompt(payload: dict[str, Any]) -> str:
    source = f"{payload['system_prompt']}\n---USER---\n{payload['user_prompt']}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def verify(output_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    advisories: list[str] = []
    required = [
        output_dir / "experiment_manifest.json",
        output_dir / "condition_manifest.json",
        output_dir / "evidence_blocks.json",
        output_dir / "run_registry.csv",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        return {"status": "FAIL", "errors": [f"Missing required artifacts: {missing}"], "advisories": []}

    manifest = json.loads((output_dir / "experiment_manifest.json").read_text(encoding="utf-8"))
    conditions = json.loads((output_dir / "condition_manifest.json").read_text(encoding="utf-8"))
    registry = pd.read_csv(output_dir / "run_registry.csv", keep_default_na=False)
    if len(registry) != int(manifest["registered_calls"]):
        errors.append("Registry row count does not match experiment manifest")
    if registry.duplicated(["model_spec_id", "condition_id", "run_id"]).any():
        errors.append("Duplicate model/condition/run slots in registry")
    if manifest.get("condition_selection") == "all" and len(manifest.get("models", [])) == 3:
        if int(manifest.get("runs_per_cell", 0)) == 10 and int(manifest.get("control_repeats", 0)) == 3:
            if len(registry) != 714:
                errors.append(f"Preregistered all-condition design has {len(registry)} calls, expected 714")
    unknown_statuses = sorted(set(registry["status"].astype(str)).difference(TERMINAL_STATUSES))
    if unknown_statuses:
        errors.append(f"Non-terminal or unknown registry statuses: {unknown_statuses}")

    by_condition = {str(item["condition_id"]): item for item in conditions}
    if len(by_condition) != len(conditions):
        errors.append("Duplicate condition IDs in condition manifest")
    factorial = [item for item in conditions if item["family"] == "factorial"]
    bits = [str(item["factorial_bits"]) for item in factorial]
    if len(factorial) not in {0, 5, 16}:
        errors.append(f"Unexpected number of factorial conditions: {len(factorial)}")
    if len(bits) != len(set(bits)):
        errors.append("Duplicate factorial bit combinations")

    for condition_id, condition in by_condition.items():
        prompt_path = output_dir / "prompts" / f"{condition_id}.json"
        if not prompt_path.exists():
            errors.append(f"Missing prompt archive for {condition_id}")
            continue
        prompt = json.loads(prompt_path.read_text(encoding="utf-8"))
        if hash_prompt(prompt) != prompt.get("prompt_hash"):
            errors.append(f"Prompt hash mismatch for {condition_id}")
        combined = f"{prompt['system_prompt']}\n{prompt['user_prompt']}".lower()
        if not bool(condition.get("leakage_expected")):
            found = [marker for marker in PRIMARY_FORBIDDEN_MARKERS if marker in combined]
            if found:
                errors.append(f"Primary prompt {condition_id} contains forbidden markers: {found}")
        elif "worked_decision" not in combined:
            errors.append(f"Legacy positive control {condition_id} does not contain its expected leakage marker")

    for row in registry.to_dict(orient="records"):
        status = str(row["status"])
        if status == "registered_not_run":
            continue
        call_dir = output_dir / "calls" / str(row["call_id"])
        for filename in ("prompt.json", "request.json", "provenance.json"):
            if not (call_dir / filename).exists():
                errors.append(f"{row['call_id']} missing {filename}")
        if status in {"ok", "parse_failed"} and not (call_dir / "response.json").exists():
            errors.append(f"{row['call_id']} missing response.json")
        if status == "ok" and not (call_dir / "parsed.json").exists():
            errors.append(f"{row['call_id']} missing parsed.json")

    score_path = output_dir / "cell_scores.csv"
    if score_path.exists():
        scores = pd.read_csv(score_path, keep_default_na=False)
        registered_sum = int(pd.to_numeric(scores["registered_runs"], errors="coerce").sum())
        if registered_sum != len(registry):
            errors.append(
                f"Cell-score denominators sum to {registered_sum}; registry contains {len(registry)} calls"
            )
        conserved = (
            pd.to_numeric(scores["ok_runs"], errors="coerce")
            + pd.to_numeric(scores["parse_failed_runs"], errors="coerce")
            + pd.to_numeric(scores["provider_error_runs"], errors="coerce")
            + pd.to_numeric(scores["not_run"], errors="coerce")
        )
        if not conserved.eq(pd.to_numeric(scores["registered_runs"], errors="coerce")).all():
            errors.append("At least one cell violates status denominator conservation")
    else:
        advisories.append("Scores have not been generated; run score_agentic_v2.py after model execution")

    matched_pairs_path = output_dir / "matched_factorial_pairs.csv"
    matched_effects_path = output_dir / "matched_factorial_effects.csv"
    if matched_pairs_path.exists() and matched_effects_path.exists():
        pairs = pd.read_csv(matched_pairs_path, keep_default_na=False)
        counts = pairs.groupby(["model_spec_id", "factor", "metric"])["matched_background"].nunique()
        if not counts.eq(8).all():
            errors.append("Matched analysis does not contain 8 backgrounds per model/factor/metric")
        effects = pd.read_csv(matched_effects_path, keep_default_na=False)
        pooled = effects.loc[effects["model_spec_id"].astype(str).eq("pooled")]
        if not pd.to_numeric(pooled["matched_pairs"], errors="coerce").eq(24).all():
            errors.append("Pooled matched effects do not all use 24 fixed-panel pairs")
        legacy_path = output_dir / "factorial_effects.csv"
        if legacy_path.exists():
            legacy = pd.read_csv(legacy_path, keep_default_na=False)
            legacy = legacy.loc[
                legacy["model_spec_id"].astype(str).eq("pooled")
                & legacy["effect_type"].astype(str).eq("main_effect")
            ].set_index(["factor", "metric"])
            matched = pooled.set_index(["factor", "metric"])
            shared = legacy.index.intersection(matched.index)
            drift = (
                pd.to_numeric(legacy.loc[shared, "mean_difference_bit1_minus_bit0"], errors="coerce")
                - pd.to_numeric(matched.loc[shared, "mean_difference_bit1_minus_bit0"], errors="coerce")
            ).abs()
            if not drift.le(1e-12).all():
                errors.append("Matched-cell point estimates drift from the balanced call-level estimates")
    else:
        advisories.append("Matched-cell primary analysis has not been generated")

    scan_extensions = {".json", ".csv", ".md", ".txt"}
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in scan_extensions:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text):
            errors.append(f"Credential-like value found in {path.relative_to(output_dir)}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "registered_calls": int(len(registry)),
        "status_counts": registry["status"].astype(str).value_counts().sort_index().to_dict(),
        "errors": errors,
        "advisories": advisories,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-config", default=str(ROOT / "configs" / "agentic_v2.json"))
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    experiment = json.loads(Path(args.experiment_config).expanduser().read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else resolve(experiment["output_root"])
    result = verify(output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
