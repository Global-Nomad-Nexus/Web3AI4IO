#!/usr/bin/env python3
"""Recompute the fixed-panel matched-cell analysis from archived call scores."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.agentic_v2_scoring import (
    matched_factorial_effects,
    matched_factorial_pairs,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive-dir",
        default=str(ROOT.parent / "reproduction" / "archived" / "application" / "agentic_v2"),
    )
    parser.add_argument("--seed", type=int, default=20260729)
    parser.add_argument("--bootstrap-draws", type=int, default=2000)
    args = parser.parse_args()

    archive = Path(args.archive_dir).expanduser().resolve()
    source = archive / "call_scores.csv"
    calls = pd.read_csv(source, keep_default_na=False)
    pairs = matched_factorial_pairs(calls)
    effects = matched_factorial_effects(
        calls, seed=args.seed, draws=args.bootstrap_draws
    )
    if len(pairs) != 3 * 4 * 8 * 9:
        raise SystemExit(f"Unexpected matched pair rows: {len(pairs)}")
    pair_counts = pairs.groupby(["model_spec_id", "factor"])["matched_background"].nunique()
    if not pair_counts.eq(8).all():
        raise SystemExit(f"Not every model/factor has eight pairs: {pair_counts.to_dict()}")

    pair_path = archive / "matched_factorial_pairs.csv"
    effect_path = archive / "matched_factorial_effects.csv"
    pairs.to_csv(pair_path, index=False)
    effects.to_csv(effect_path, index=False)
    manifest = {
        "analysis": "hierarchical_matched_cell_fixed_model_panel",
        "source": source.name,
        "source_sha256": sha256(source),
        "seed": args.seed,
        "bootstrap_draws": args.bootstrap_draws,
        "models_resampled": False,
        "models_fixed_equal_weight": 3,
        "matched_backgrounds_per_model_factor": 8,
        "calls_per_cell": 10,
        "interpretation": "descriptive interval for this fixed model panel and factorial grid; not population-model inference",
        "outputs": {
            pair_path.name: sha256(pair_path),
            effect_path.name: sha256(effect_path),
        },
    }
    manifest_path = archive / "matched_analysis_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
