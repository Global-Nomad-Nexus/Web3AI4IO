#!/usr/bin/env python3
"""Fail-closed verification for the 60-call Telegram replication."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.telegram_replication import FORBIDDEN_PROMPT_MARKERS


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(output: Path, archive: Path | None = None) -> dict:
    errors = []
    required = ["experiment_manifest.json", "condition_manifest.json", "evidence_blocks.json", "run_registry.csv"]
    for name in required:
        if not (output / name).exists(): errors.append(f"Missing {name}")
    if errors: return {"status": "FAIL", "errors": errors}
    registry = pd.read_csv(output / "run_registry.csv", keep_default_na=False)
    if len(registry) != 60: errors.append(f"Expected 60 calls, found {len(registry)}")
    if registry.duplicated(["model_spec_id", "condition_id", "run_id"]).any(): errors.append("Duplicate model/condition/run slot")
    expected = {10}
    if set(registry.groupby(["model_spec_id", "condition_id"]).size()) != expected: errors.append("Every model-condition cell must contain exactly 10 calls")
    if set(registry.groupby("model_spec_id").size()) != {20}: errors.append("Every model must contain exactly 20 calls")
    for condition in ("T0_ASSOCIATION", "T1_BOUNDARY_COMPLETE"):
        prompt = json.loads((output / "prompts" / f"{condition}.json").read_text(encoding="utf-8"))
        source = f"{prompt['system_prompt']}\n---USER---\n{prompt['user_prompt']}"
        if hashlib.sha256(source.encode()).hexdigest() != prompt["prompt_hash"]: errors.append(f"Prompt hash mismatch: {condition}")
        found = [marker for marker in FORBIDDEN_PROMPT_MARKERS if marker in source.lower()]
        if found: errors.append(f"Answer leakage in {condition}: {found}")
    terminal = {"ok", "parse_failed", "provider_error", "registered_not_run"}
    unknown = sorted(set(registry.status.astype(str)).difference(terminal))
    if unknown: errors.append(f"Unknown statuses: {unknown}")
    if (output / "cell_scores.csv").exists():
        cells = pd.read_csv(output / "cell_scores.csv")
        conserved = cells[["ok", "parse_failed", "provider_error", "registered_not_run"]].sum(axis=1)
        if not conserved.eq(cells["registered"]).all(): errors.append("Status-denominator conservation failed")
        if int(cells.registered.sum()) != 60: errors.append("Cell-score denominators do not sum to 60")
    if archive and (archive / "archive_manifest.json").exists():
        manifest = json.loads((archive / "archive_manifest.json").read_text(encoding="utf-8"))
        for filename, digest in manifest["release_files"].items():
            if not (archive / filename).exists() or sha256(archive / filename) != digest: errors.append(f"Archive hash mismatch: {filename}")
    secret_pattern = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
    for path in output.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".csv", ".jsonl", ".txt"} and secret_pattern.search(path.read_text(encoding="utf-8", errors="replace")):
            errors.append(f"Credential-like value in {path.relative_to(output)}")
    return {"status": "PASS" if not errors else "FAIL", "registered_calls": len(registry), "status_counts": registry.status.value_counts().sort_index().to_dict(), "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-config", default=str(ROOT / "configs" / "telegram_replication.json"))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--archive-dir", default="")
    args = parser.parse_args()
    experiment = json.loads(Path(args.experiment_config).read_text(encoding="utf-8"))
    output = Path(args.output_dir).expanduser().resolve() if args.output_dir else (ROOT / experiment["output_root"]).resolve()
    archive = Path(args.archive_dir).expanduser().resolve() if args.archive_dir else (ROOT / experiment["archive_root"]).resolve()
    result = verify(output, archive)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS": raise SystemExit(1)


if __name__ == "__main__":
    main()
