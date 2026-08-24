"""Panel loading and validation for the S5 experiment (revision 2026-08-14).

Two-level validation per the locked missing-data policy:
  * source-panel requirement: the corrected panel still carries all
    724 rows / 4 units x 181 days of the source panel, with original values
    and correction provenance preserved;
  * primary analysis: exactly 3 markets (pump_ecosystem, raydium, orca) x
    181 days = 543 rows, fully observed and definition-consistent over the
    registered window. Meteora is excluded from the primary specification;
    its corrected series (missing before 2025-01-17) feeds only the
    restricted-window sensitivity.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from . import paths


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_corrected_panel(csv_path=None) -> pd.DataFrame:
    csv_path = csv_path or paths.CORRECTED_PANEL_CSV
    df = pd.read_csv(csv_path)
    df["date_parsed"] = pd.to_datetime(df["date_str"])
    return df


def validate_corrected_panel(df: pd.DataFrame) -> dict:
    """Validate the corrected panel (source requirement + primary subset)."""
    event = pd.Timestamp(paths.EVENT_DATE)
    checks = {}

    checks["row_count_724"] = bool(len(df) == 724)
    checks["units_exact"] = sorted(df["unit"].unique()) == sorted(paths.SOURCE_UNITS)
    per_unit = df.groupby("unit").size()
    checks["days_per_unit_181"] = bool(
        (per_unit == 181).all() and len(per_unit) == len(paths.SOURCE_UNITS)
    )

    rel_ok = True
    date_ok = True
    for unit in paths.SOURCE_UNITS:
        sub = df[df["unit"] == unit].sort_values("rel_day")
        rel_ok &= bool((sub["rel_day"].to_numpy() == np.arange(-90, 91)).all())
        expected_dates = event + pd.to_timedelta(sub["rel_day"], unit="D")
        date_ok &= bool((sub["date_parsed"].to_numpy() == expected_dates.to_numpy()).all())
    checks["rel_day_range_minus90_90"] = bool(rel_ok)
    checks["date_consistent_with_event_2025_03_20"] = bool(date_ok)
    checks["event_date_is_thursday"] = bool(event.weekday() == 3)

    checks["provenance_columns_present"] = bool(
        {
            "daily_volume_usd_original",
            "daily_volume_usd_corrected",
            "log_volume_corrected",
            "coverage_status",
            "correction_reason",
            "source_fields",
        }.issubset(df.columns)
    )
    checks["original_values_preserved"] = bool(
        (df["daily_volume_usd_original"] == df["daily_volume_usd"]).all()
    )

    boundary = pd.Timestamp(paths.COVERAGE_BOUNDARY)
    met = df[df["unit"] == paths.METEORA]
    met_pre = met[met["date_parsed"] < boundary]
    met_post = met[met["date_parsed"] >= boundary]
    checks["meteora_missing_exactly_before_boundary"] = bool(
        met_pre["daily_volume_usd_corrected"].isna().all()
        and (met_pre["coverage_status"] == "missing_coverage_gap").all()
        and len(met_pre) == 28  # 2024-12-20 .. 2025-01-16
    )
    checks["meteora_observed_corrected_from_boundary"] = bool(
        met_post["daily_volume_usd_corrected"].notna().all()
        and (met_post["coverage_status"] == "observed_corrected").all()
        and len(met_post) == 153
    )

    prim = df[df["unit"].isin(paths.UNITS)]
    checks["primary_rows_543"] = bool(len(prim) == 3 * 181)
    checks["primary_no_missing_corrected"] = bool(
        prim["daily_volume_usd_corrected"].notna().all()
    )
    checks["primary_no_zero_volume_days"] = bool(
        (prim["daily_volume_usd_corrected"] > 0).all()
    )
    checks["primary_corrected_equals_original"] = bool(
        (prim["daily_volume_usd_corrected"] == prim["daily_volume_usd_original"]).all()
    )
    checks["log_volume_corrected_consistent"] = bool(
        np.isfinite(prim["log_volume_corrected"]).all()
        and (
            np.abs(
                np.log1p(prim["daily_volume_usd_corrected"])
                - prim["log_volume_corrected"]
            ).max()
            < 1e-9
        )
    )

    checks["all_passed"] = bool(all(checks.values()))
    return {
        "panel_csv": str(paths.CORRECTED_PANEL_CSV),
        "panel_csv_sha256": sha256_of(paths.CORRECTED_PANEL_CSV),
        "source_panel_csv": str(paths.PANEL_CSV),
        "n_rows": int(len(df)),
        "units": sorted(df["unit"].unique().tolist()),
        "primary_units": paths.UNITS,
        "primary_rows": int(len(prim)),
        "rel_day_min": int(df["rel_day"].min()),
        "rel_day_max": int(df["rel_day"].max()),
        "event_date": paths.EVENT_DATE,
        "event_weekday": "Thursday",
        "checks": checks,
    }


def load_validated_panel(out_json=None):
    """Load the corrected panel, validate, optionally write panel_validation.json.

    Returns (primary_df, report): primary_df is the 543-row, 3-market primary
    analysis panel with `log_volume` set to the corrected log volume.
    """
    df = load_corrected_panel()
    report = validate_corrected_panel(df)
    if out_json is not None:
        with open(out_json, "w") as f:
            json.dump(report, f, indent=2)
    if not report["checks"]["all_passed"]:
        failed = [k for k, v in report["checks"].items() if not v]
        raise SystemExit("STOP (plan S10): panel validation failed: " + ", ".join(failed))
    prim = df[df["unit"].isin(paths.UNITS)].copy()
    prim["log_volume"] = prim["log_volume_corrected"]
    prim["daily_volume_usd"] = prim["daily_volume_usd_corrected"]
    return prim, report


def load_sensitivity_panel():
    """Meteora-including panel for the restricted-window sensitivity ONLY.

    Returns the corrected panel restricted to the locked sensitivity
    calibration window (2025-01-17 .. 2025-03-19, rel_day -62..-1) with all
    four markets; no bootstrap block may cross the coverage boundary, which
    the window start enforces by construction.
    """
    df = load_corrected_panel()
    start = pd.Timestamp(paths.SENSITIVITY_CAL_START)
    end = pd.Timestamp(paths.SENSITIVITY_CAL_END)
    sub = df[(df["date_parsed"] >= start) & (df["date_parsed"] <= end)].copy()
    if sub["daily_volume_usd_corrected"].isna().any():
        raise SystemExit("STOP: sensitivity window contains missing corrected values")
    sub["log_volume"] = sub["log_volume_corrected"]
    sub["daily_volume_usd"] = sub["daily_volume_usd_corrected"]
    return sub


def write_data_manifest(out_path) -> dict:
    manifest = {
        "experiment": "S5_temporal_aggregation",
        "event_id": paths.EVENT_ID,
        "event_date": paths.EVENT_DATE,
        "source_panel": {
            "path": str(paths.PANEL_CSV.relative_to(paths.REPO_ROOT)),
            "sha256": sha256_of(paths.PANEL_CSV),
            "expected_rows": 724,
            "note": "immutable upstream bundle, never modified",
        },
        "corrected_panel": {
            "path": str(paths.CORRECTED_PANEL_CSV.relative_to(paths.REPO_ROOT)),
            "sha256": sha256_of(paths.CORRECTED_PANEL_CSV),
            "provenance": str(paths.CORRECTED_PROVENANCE_JSON.relative_to(paths.REPO_ROOT)),
        },
        "evidence_metadata": [
            {"path": str(p.relative_to(paths.REPO_ROOT)), "sha256": sha256_of(p)}
            for p in paths.EVIDENCE_FILES
        ],
        "units": paths.UNITS,
        "treated": paths.TREATED,
        "controls": paths.CONTROLS,
        "meteora_status": "excluded from primary; restricted-window sensitivity only",
        "outcome": "log_volume (corrected)",
        "reproducibility": {
            "seed_y0": paths.SEED_Y0,
            "seed_bootstrap": paths.SEED_BOOT,
            "seed_sd_null": paths.SEED_SDNULL,
            "seed_fidelity": paths.SEED_FID,
            "note": "all outputs rebuild from the source CSV via run.sh",
        },
    }
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest
