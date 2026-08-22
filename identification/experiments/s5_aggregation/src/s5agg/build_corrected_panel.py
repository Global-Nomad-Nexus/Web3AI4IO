"""Build the identification-side derived corrected panel for S5 (researcher lock 2026-08-14).

Reads the immutable upstream bundle raw DefiLlama dumps and the processed
724-row source panel; writes a derived panel that preserves every original
column and adds correction provenance:

  daily_volume_usd            original value from the source panel (untouched)
  coverage_status             observed | observed_structural_zero |
                              missing_coverage_gap | observed_corrected
  correction_reason           free-text provenance (empty when none)
  source_fields               raw file(s) + field the row derives from
  daily_volume_usd_corrected  analysis value; NaN where missing_coverage_gap
  log_volume                  log1p of the ORIGINAL value (as in source panel)
  log_volume_corrected        log1p of the corrected value

Correction rules (locked):
  * meteora_combined before 2025-01-17  -> missing (no fill, no interpolation,
    no imputation from other markets). The upstream parent listing covered
    only the DAMM V1 child adapter before 2025-01-17 and shows intermittent
    literal-zero adapter failures (see zero_day_audit.md).
  * meteora_combined from 2025-01-17    -> parent Meteora totalDataChart value
    only (parent includes DLMM from 2025-01-17); the independent meteora-dlmm
    series is NOT added again (the source panel double-counts it, ~1.94-2.00x).
  * pump_ecosystem / raydium / orca     -> unchanged (coverage audit passed
    for the registered pre window; see coverage_audit_primary_markets.json).

The source panel must still validate at 724 rows / 4 units x 181 days
(source-panel validation requirement); the primary analysis uses the
3 markets x 181 days = 543 rows subset.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import paths

COVERAGE_BOUNDARY = pd.Timestamp("2025-01-17", tz="UTC")

METEORA_PARENT_RAW = paths.BUNDLE / (
    "01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local"
    "/data/raw/defillama_summary_meteora.json"
)
METEORA_DLMM_RAW = paths.BUNDLE / (
    "01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local"
    "/data/raw/defillama_summary_meteora_dlmm.json"
)

SOURCE_FIELDS = {
    "pump_ecosystem": "defillama_summary_pump_fun.json:totalDataChart + defillama_summary_pump_swap.json:totalDataChart (structural zeros pre-launch)",
    "raydium": "defillama_summary_raydium.json:totalDataChart",
    "orca": "defillama_summary_orca.json:totalDataChart",
    "meteora_combined": "defillama_summary_meteora.json:totalDataChart (parent; includes DLMM from 2025-01-17) + defillama_summary_meteora_dlmm.json:totalDataChart",
}

REASON_MISSING = (
    "upstream parent listing covered only the Meteora DAMM V1 child adapter "
    "before 2025-01-17, with intermittent literal-zero adapter failures; DLMM "
    "not covered; set missing per researcher lock 2026-08-14 (no fill, no "
    "interpolation, no imputation from other markets)"
)
REASON_CORRECTED = (
    "use parent Meteora totalDataChart value only (parent includes DLMM from "
    "2025-01-17); removed the double-count of the independent meteora-dlmm "
    "series present in the source panel (original ~= 1.94-2.00x correct value)"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parent_meteora_series() -> pd.Series:
    payload = json.loads(METEORA_PARENT_RAW.read_text(encoding="utf-8"))
    rows = payload.get("totalDataChart", [])
    s = pd.Series(
        {pd.to_datetime(t, unit="s", utc=True).floor("D"): float(v) for t, v in rows}
    )
    return s


def build_corrected_panel(out_csv: Path | None = None, out_json: Path | None = None) -> pd.DataFrame:
    df = pd.read_csv(paths.PANEL_CSV, parse_dates=["date"])
    if len(df) != 724:
        raise SystemExit(f"STOP: source panel must have 724 rows, found {len(df)}")

    parent = _parent_meteora_series()

    df["daily_volume_usd_original"] = df["daily_volume_usd"]
    df["coverage_status"] = "observed"
    df["correction_reason"] = ""
    df["source_fields"] = df["unit"].map(SOURCE_FIELDS)

    is_met = df["unit"] == "meteora_combined"
    pre_boundary = is_met & (df["date"] < COVERAGE_BOUNDARY)
    post_boundary = is_met & (df["date"] >= COVERAGE_BOUNDARY)

    # pump_ecosystem pre-launch pump_swap zeros are structural (documented upstream)
    is_pump = df["unit"] == "pump_ecosystem"
    df.loc[is_pump & (df["date"] < pd.Timestamp("2025-03-17", tz="UTC")), "coverage_status"] = (
        "observed_structural_zero"
    )

    df.loc[pre_boundary, "coverage_status"] = "missing_coverage_gap"
    df.loc[pre_boundary, "correction_reason"] = REASON_MISSING
    df.loc[post_boundary, "coverage_status"] = "observed_corrected"
    df.loc[post_boundary, "correction_reason"] = REASON_CORRECTED

    corrected = df["daily_volume_usd_original"].astype(float).copy()
    corrected[pre_boundary] = np.nan
    met_post_idx = df.index[post_boundary]
    parent_vals = df.loc[met_post_idx, "date"].map(parent)
    if parent_vals.isna().any():
        raise SystemExit("STOP: parent Meteora series missing a post-boundary date")
    corrected[met_post_idx] = parent_vals.to_numpy()
    df["daily_volume_usd_corrected"] = corrected
    df["log_volume_corrected"] = np.log1p(df["daily_volume_usd_corrected"])

    if out_csv is not None:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_csv, index=False)
    if out_json is not None:
        provenance = {
            "built_by": "src/s5agg/build_corrected_panel.py",
            "locked": "2026-08-14",
            "source_panel": str(paths.PANEL_CSV.relative_to(paths.REPO_ROOT)),
            "source_panel_sha256": _sha256(paths.PANEL_CSV),
            "raw_inputs": {
                "meteora_parent": {
                    "path": str(METEORA_PARENT_RAW.relative_to(paths.REPO_ROOT)),
                    "sha256": _sha256(METEORA_PARENT_RAW),
                },
                "meteora_dlmm_reference_only": {
                    "path": str(METEORA_DLMM_RAW.relative_to(paths.REPO_ROOT)),
                    "sha256": _sha256(METEORA_DLMM_RAW),
                },
            },
            "coverage_boundary": "2025-01-17",
            "rules": {
                "meteora_before_2025-01-17": REASON_MISSING,
                "meteora_from_2025-01-17": REASON_CORRECTED,
                "other_units": "unchanged (coverage audit passed, see coverage_audit_primary_markets.json)",
            },
            "row_counts": {
                "total": int(len(df)),
                "missing_coverage_gap": int(pre_boundary.sum()),
                "observed_corrected": int(post_boundary.sum()),
                "observed": int((df["coverage_status"] == "observed").sum()),
                "observed_structural_zero": int(
                    (df["coverage_status"] == "observed_structural_zero").sum()
                ),
            },
            "audit": "zero_day_audit.md",
        }
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return df


if __name__ == "__main__":
    out = build_corrected_panel(
        paths.EXPERIMENT_DIR / "data" / "solana_dex_daily_did_panel_corrected.csv",
        paths.EXPERIMENT_DIR / "data" / "panel_correction_provenance.json",
    )
    print(f"corrected panel: {len(out)} rows")
