#!/usr/bin/env python3
"""Run matched-pair diagnostics for the Clanker/Base cross-chain case."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / "artifacts" / "external_validation"
TABLES = ROOT / "artifacts" / "tables"
EVENT_ID = "CLANKER_SNIPER_DECAY_V41_BASE_20250826"

DEFAULT_METRICS = [
    "active_traders",
    "swap_count",
    "buy_count",
    "sell_count",
    "volume_usd",
    "early_sender_top10_share_60s",
    "holder_concentration_top10",
    "holder_count",
]

DIAGNOSTIC_COLUMNS = [
    "event_id",
    "diagnostic_id",
    "horizon_days",
    "metric",
    "n_pairs",
    "treated_mean",
    "control_mean",
    "att_mean_pair_diff",
    "median_pair_diff",
    "ci95_low",
    "ci95_high",
    "positive_pair_share",
    "sample_status",
    "claim_boundary",
    "source_artifact",
]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, df: pd.DataFrame, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for column in columns:
        if column not in df.columns:
            df[column] = ""
    df = df[columns].where(pd.notna(df), "")
    df.to_csv(path, index=False)


def bootstrap_ci(values: np.ndarray, *, reps: int, seed: int) -> tuple[float, float]:
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan"), float("nan")
    if len(values) == 1:
        return float(values[0]), float(values[0])
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(reps, len(values)), replace=True).mean(axis=1)
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def infer_sample_status(horizons: pd.DataFrame) -> str:
    manifest = read_json(TABLES / "clanker_base_full_cohort_manifest_summary.json")
    expected_rows = int(manifest.get("expected_horizon_rows", 0) or 0)
    expected_tokens = int(manifest.get("cohort_tokens", 0) or 0)
    observed_rows = len(horizons)
    observed_tokens = int(horizons["token_id"].nunique()) if "token_id" in horizons else 0
    if expected_rows and observed_rows >= expected_rows and observed_tokens >= expected_tokens:
        return "full_cohort_matched_diagnostics"
    return "bounded_or_partial_matched_diagnostics"


def run_diagnostics(horizons: pd.DataFrame, metrics: list[str], reps: int, seed: int) -> pd.DataFrame:
    if horizons.empty:
        return pd.DataFrame(columns=DIAGNOSTIC_COLUMNS)
    required = {"cohort_match_id", "cohort_side", "horizon_days"}
    missing = required.difference(horizons.columns)
    if missing:
        raise RuntimeError(f"Token horizons are missing required columns: {sorted(missing)}")
    sample_status = infer_sample_status(horizons)
    rows: list[dict[str, Any]] = []
    horizons = horizons.copy()
    horizons["horizon_days"] = pd.to_numeric(horizons["horizon_days"], errors="coerce")
    for horizon in sorted(horizons["horizon_days"].dropna().astype(int).unique()):
        h = horizons.loc[horizons["horizon_days"].eq(horizon)].copy()
        for metric in metrics:
            if metric not in h.columns:
                continue
            values = h[["cohort_match_id", "cohort_side", metric]].copy()
            values[metric] = pd.to_numeric(values[metric], errors="coerce")
            pivot = values.pivot_table(
                index="cohort_match_id",
                columns="cohort_side",
                values=metric,
                aggfunc="mean",
            )
            if not {"post_v4_1_treated", "pre_v4_0_control"}.issubset(set(pivot.columns)):
                continue
            paired = pivot[["post_v4_1_treated", "pre_v4_0_control"]].dropna()
            if paired.empty:
                continue
            diffs = (paired["post_v4_1_treated"] - paired["pre_v4_0_control"]).to_numpy(dtype=float)
            ci_low, ci_high = bootstrap_ci(diffs, reps=reps, seed=seed + horizon + len(rows))
            rows.append(
                {
                    "event_id": EVENT_ID,
                    "diagnostic_id": f"clanker_base_matched_pair:{metric}:{horizon}d",
                    "horizon_days": horizon,
                    "metric": metric,
                    "n_pairs": int(len(diffs)),
                    "treated_mean": float(paired["post_v4_1_treated"].mean()),
                    "control_mean": float(paired["pre_v4_0_control"].mean()),
                    "att_mean_pair_diff": float(np.mean(diffs)),
                    "median_pair_diff": float(np.median(diffs)),
                    "ci95_low": ci_low,
                    "ci95_high": ci_high,
                    "positive_pair_share": float(np.mean(diffs > 0)),
                    "sample_status": sample_status,
                    "claim_boundary": (
                        "Matched-pair diagnostic for Clanker/Base v4.1 versus v4.0. Use as causal diagnostics "
                        "only within the covered sample; platform-wide claims require full manifest import coverage."
                    ),
                    "source_artifact": "artifacts/external_validation/clanker_base_token_horizons.csv",
                }
            )
    return pd.DataFrame(rows).reindex(columns=DIAGNOSTIC_COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizons", default=str(EXTERNAL / "clanker_base_token_horizons.csv"))
    parser.add_argument("--metrics", default=",".join(DEFAULT_METRICS))
    parser.add_argument("--bootstrap-reps", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument("--out", default=str(TABLES / "clanker_base_causal_diagnostics.csv"))
    parser.add_argument("--summary-out", default=str(TABLES / "clanker_base_causal_diagnostics_summary.json"))
    args = parser.parse_args()

    horizons_path = Path(args.horizons).expanduser().resolve()
    horizons = pd.read_csv(horizons_path, low_memory=False)
    metrics = [part.strip() for part in args.metrics.split(",") if part.strip()]
    diagnostics = run_diagnostics(horizons, metrics, args.bootstrap_reps, args.seed)
    out_path = Path(args.out).expanduser().resolve()
    summary_path = Path(args.summary_out).expanduser().resolve()
    write_csv(out_path, diagnostics, DIAGNOSTIC_COLUMNS)

    summary = {
        "event_id": EVENT_ID,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_artifact": str(horizons_path),
        "diagnostic_rows": int(len(diagnostics)),
        "metrics": sorted(diagnostics["metric"].unique().tolist()) if not diagnostics.empty else [],
        "horizons": sorted(pd.to_numeric(diagnostics["horizon_days"], errors="coerce").dropna().astype(int).unique().tolist())
        if not diagnostics.empty
        else [],
        "sample_status": diagnostics["sample_status"].iloc[0] if not diagnostics.empty else "no_diagnostics",
        "claim_boundary": (
            "Diagnostics summarize matched-pair differences. They do not upgrade the Base case to platform-wide "
            "causal replication unless full-cohort import coverage is complete."
        ),
        "outputs": {"diagnostics": str(out_path)},
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Clanker/Base causal diagnostics written: rows={len(diagnostics)} status={summary['sample_status']}")


if __name__ == "__main__":
    main()
