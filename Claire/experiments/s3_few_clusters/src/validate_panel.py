"""Panel validation + pre-period residual scale descriptives for experiment S3.

Spec: Web3AI4IO/Claire/experiment_plans/S3_few_platform_clusters.md

Scale-rule revision (2026-08-13): the operative scale metric is s_ATT, the
sampling SD of the null 30-day DiD estimator, estimated by a seeded pilot in
src/run_experiment.py and recorded in calibration_summary.json. The
pre-period residual SD reported here is retained as a descriptive statistic
(and as the record of why the first run stopped under the superseded rule);
it no longer gates execution.

This script regenerates:
  - panel_validation.json  (panel balance + descriptive residual scale)
  - data_manifest.json     (input paths + sha256, cross-checked against the
                            bundle's FILE_MANIFEST_SHA256.txt)

Run from the experiment root:
  .venv/bin/python -m src.validate_panel
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EXPERIMENT_ROOT.parents[2]  # Web3AI4IO/
BUNDLE = REPO_ROOT / "data/external/shilin/20260810/bundle"

PANEL_CSV = (
    BUNDLE
    / "01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local"
    / "data/processed/solana_dex_daily_did_panel.csv"
)
CASE_JSON = BUNDLE / "Web3AI4IO/Shilin/configs/pumpswap_case.json"
EVENTS_CSV = BUNDLE / "Web3AI4IO/Shilin/benchmark_release/data/events.csv"
BUNDLE_MANIFEST = BUNDLE / "FILE_MANIFEST_SHA256.txt"

EXPECTED_UNITS = ["pump_ecosystem", "raydium", "orca", "meteora_combined"]
EXPECTED_ROWS = 724
EXPECTED_DAYS_PER_UNIT = 181
REL_DAY_MIN, REL_DAY_MAX = -90, 90
PRE_PERIOD = (-90, -1)  # inclusive, used for the FE/weekday fit
INJECTED_EFFECT = 0.20
SCALE_WINDOW = (0.25, 1.0)  # acceptable range for effect / residual SD


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fit_preperiod(df: pd.DataFrame) -> pd.DataFrame:
    """OLS of log_volume on unit FE + weekday dummies, pre-period rows only.

    Coding: 4 unit dummies (no global intercept) + 6 weekday dummies
    (Monday=0 dropped). The fitted combination unitFE + weekday is invariant
    to the dropped-level choice; residuals u_it = y - unitFE - weekday keep
    the common day shock by construction.
    """
    pre = df[(df.rel_day >= PRE_PERIOD[0]) & (df.rel_day <= PRE_PERIOD[1])].copy()
    pre["date"] = pd.to_datetime(pre["date_str"])
    pre["weekday"] = pre["date"].dt.dayofweek
    x_unit = pd.get_dummies(pre["unit"])[EXPECTED_UNITS].astype(float)
    x_wd = pd.get_dummies(pre["weekday"]).astype(float)
    for d in range(7):
        if d not in x_wd.columns:
            x_wd[d] = 0.0
    x_wd = x_wd[sorted(x_wd.columns)].drop(columns=[0])
    X = np.column_stack([x_unit.values, x_wd.values])
    y = pre["log_volume"].values
    beta, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    pre["u"] = y - X @ beta
    pre.attrs["rank"] = int(rank)
    return pre


def scale_check(pre: pd.DataFrame) -> dict:
    """SD of pre-period residuals, pooled over units and days (ddof=1).

    Reported alongside alternative definitions so the stop decision does not
    hinge on one convention. The check uses the primary definition:
    sample SD of the 360 pooled residuals u_it, ddof=1.
    """
    u = pre["u"].values
    xi = pre.groupby("rel_day")["u"].transform("mean")
    v = (pre["u"] - xi).values
    variants = {
        "pooled_u_ddof1": float(u.std(ddof=1)),
        "pooled_u_ddof0": float(u.std(ddof=0)),
        "pooled_u_df_corrected_n_minus_rank": float(
            np.sqrt((u**2).sum() / (len(u) - pre.attrs["rank"]))
        ),
        "within_u_minus_common_shock_ddof1": float(v.std(ddof=1)),
        "mean_per_unit_sd_ddof1": float(pre.groupby("unit")["u"].std(ddof=1).mean()),
        "common_shock_xi_t_ddof1": float(
            pre.assign(xi=xi).groupby("rel_day")["xi"].first().std(ddof=1)
        ),
    }
    sd_primary = variants["pooled_u_ddof1"]
    ratio = INJECTED_EFFECT / sd_primary
    ok = SCALE_WINDOW[0] <= ratio <= SCALE_WINDOW[1]
    return {
        "primary_definition": (
            "sample SD (ddof=1) of the 360 pooled pre-period residuals "
            "u_it = log_volume - unit_FE - weekday_effect, fit on rel_day in "
            "[-90, -1] with 4 unit dummies + 6 weekday dummies (Monday dropped)"
        ),
        "injected_effect": INJECTED_EFFECT,
        "required_sd_interval_for_pass": [
            INJECTED_EFFECT / SCALE_WINDOW[1],
            INJECTED_EFFECT / SCALE_WINDOW[0],
        ],
        "residual_sd_variants": variants,
        "ratio_effect_over_sd_primary": ratio,
        "required_ratio_interval": list(SCALE_WINDOW),
        "pass": bool(ok),
    }


def validate_panel(df: pd.DataFrame) -> dict:
    checks = {}
    checks["n_rows"] = {"expected": EXPECTED_ROWS, "observed": int(len(df)),
                        "pass": len(df) == EXPECTED_ROWS}
    units = sorted(df["unit"].unique().tolist())
    checks["units"] = {"expected": EXPECTED_UNITS, "observed": units,
                       "pass": set(units) == set(EXPECTED_UNITS)}
    per_unit = df.groupby("unit")["rel_day"].agg(["count", "min", "max"])
    checks["days_per_unit"] = {
        "expected": EXPECTED_DAYS_PER_UNIT,
        "observed": {u: int(per_unit.loc[u, "count"]) for u in EXPECTED_UNITS},
        "pass": bool((per_unit["count"] == EXPECTED_DAYS_PER_UNIT).all()),
    }
    checks["rel_day_range"] = {
        "expected": [REL_DAY_MIN, REL_DAY_MAX],
        "observed": [int(df.rel_day.min()), int(df.rel_day.max())],
        "pass": df.rel_day.min() == REL_DAY_MIN and df.rel_day.max() == REL_DAY_MAX,
    }
    checks["duplicate_unit_day"] = {
        "expected": 0,
        "observed": int(df.duplicated(["unit", "rel_day"]).sum()),
        "pass": not df.duplicated(["unit", "rel_day"]).any(),
    }
    checks["missing_log_volume"] = {
        "expected": 0,
        "observed": int(df.log_volume.isna().sum()),
        "pass": not df.log_volume.isna().any(),
    }
    dates_per_rel_day = df.groupby("rel_day")["date_str"].nunique()
    checks["one_date_per_rel_day"] = {
        "expected": True, "observed": bool((dates_per_rel_day == 1).all()),
        "pass": bool((dates_per_rel_day == 1).all()),
    }
    return checks


def main() -> None:
    df = pd.read_csv(PANEL_CSV)
    panel_checks = validate_panel(df)
    panel_ok = all(c["pass"] for c in panel_checks.values())

    pre = fit_preperiod(df)
    scale = scale_check(pre)

    # Data manifest with sha256, cross-checked against the bundle manifest.
    inputs = {
        "panel_csv": PANEL_CSV,
        "case_config_json": CASE_JSON,
        "events_csv": EVENTS_CSV,
    }
    bundle_hashes = {}
    if BUNDLE_MANIFEST.exists():
        for line in BUNDLE_MANIFEST.read_text().splitlines():
            parts = line.split()
            if len(parts) == 2:
                bundle_hashes[parts[1]] = parts[0]
    manifest = {"generated_by": "src/validate_panel.py", "inputs": {}}
    for name, path in inputs.items():
        digest = sha256_of(path)
        entry = {"path": str(path), "sha256": digest, "exists": path.exists()}
        match = [k for k, v in bundle_hashes.items() if v == digest]
        entry["matches_bundle_FILE_MANIFEST_SHA256"] = bool(match)
        if match:
            entry["bundle_manifest_entry"] = match[0]
        manifest["inputs"][name] = entry

    result = {
        "spec": "Web3AI4IO/Claire/experiment_plans/S3_few_platform_clusters.md",
        "generated_by": "src/validate_panel.py",
        "panel_checks": panel_checks,
        "panel_valid": panel_ok,
        "preperiod_fit": {
            "window_rel_day": list(PRE_PERIOD),
            "n_obs": int(len(pre)),
            "regressor_rank": pre.attrs["rank"],
        },
        "scale_check": scale,
        "scale_check_note": (
            "Descriptive only under the 2026-08-13 spec revision: the "
            "pre-period residual SD rule is superseded by the s_ATT pilot "
            "rule; the operative scale check is calibration_summary.json. "
            "The 'pass' field above records the old rule's verdict "
            "(0.20/SD = 0.0695), which triggered the first run's blocker."
        ),
        "status": "OK" if panel_ok else "PANEL_INVALID",
    }

    def _json_default(o):
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        raise TypeError(f"not JSON serializable: {type(o)}")

    out_val = EXPERIMENT_ROOT / "panel_validation.json"
    out_man = EXPERIMENT_ROOT / "data_manifest.json"
    out_val.write_text(json.dumps(result, indent=2, default=_json_default) + "\n")
    out_man.write_text(json.dumps(manifest, indent=2, default=_json_default) + "\n")
    print(f"wrote {out_val}")
    print(f"wrote {out_man}")
    print(f"status: {result['status']}")
    print(f"primary residual SD: {scale['residual_sd_variants']['pooled_u_ddof1']:.6f}")
    print(f"0.20 / SD = {scale['ratio_effect_over_sd_primary']:.6f} "
          f"(required in {SCALE_WINDOW})")


if __name__ == "__main__":
    main()
