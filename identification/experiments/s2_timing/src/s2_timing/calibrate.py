"""S2 calibration and scale-gate check.

Rebuilds the clean-pre calibration for the Pump.fun creator-fee timing
experiment and evaluates the mandated effect-scale gate:

    stop if log effect 0.20 is not within [0.25, 1.0] x pre residual SD

The residual process is the one the semi-synthetic DGP would bootstrap:
per-platform OLS of log1p(outcome) on weekday fixed effects over the clean
pre period (2025-04-17..2025-05-07), then the paired Pump-minus-Moonshot
daily residual difference.

Writes calibration_summary.json and data_manifest.json next to this file's
experiment root. Exits non-zero when the scale gate blocks the formal run.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
IDENTIFICATION_ROOT = EXPERIMENT_ROOT.parents[1]

PANEL = IDENTIFICATION_ROOT / "data" / "pump_moonshot_cohort_panel.csv"
REGISTRY = IDENTIFICATION_ROOT / "event_registry.csv"
EVIDENCE = IDENTIFICATION_ROOT / "event_activation_evidence.md"
CONTRACT = IDENTIFICATION_ROOT / "data_contract.md"

EVENT_ID = "PUMP_CREATOR_FEE_20250513"
ANNOUNCEMENT_DATE = "2025-05-08"
ACTIVATION_UTC = "2025-05-13T11:27:06Z"
CLEAN_PRE = ("2025-04-17", "2025-05-07")
CLEAN_POST = ("2025-05-14", "2025-06-03")
UPGRADE_TX = "4NK8jLTKV6rwPTLsNWHejfbJrnYuJERp3z3sJGhzuPzezVvp4e7FCz4BKAnnomdJFVqNgVNQMz67P6NBdgNNYvGm"
FIRST_PAYMENT_TX = "5rj8FxQ8z2aTnwCiFgXxZTkveSiSUjm7nBnBcadiZg9LacP3XjkFjxjxssMw27FAZ9S5YUfpgDGRzFuLhqWLGAzs"

OUTCOMES = ["launches", "unique_creators"]
PLATFORMS = ["Pump.fun", "Moonshot"]
EFFECT = 0.20
SCALE_BOUNDS = (0.25, 1.0)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_inputs() -> dict:
    checks = {}
    registry = pd.read_csv(REGISTRY)
    row = registry[registry.event_id == EVENT_ID]
    checks["registry_has_event"] = len(row) == 1
    if len(row) == 1:
        r = row.iloc[0]
        checks["registry_activation_matches"] = r["effective_at_utc"] == ACTIVATION_UTC
        checks["registry_upgrade_tx_matches"] = UPGRADE_TX in r["onchain_activation_ref"]
        checks["registry_payment_tx_matches"] = FIRST_PAYMENT_TX in r["onchain_activation_ref"]
        checks["registry_anticipation_days"] = int(r["anticipation_days"]) == 5
    evidence_text = EVIDENCE.read_text()
    checks["evidence_upgrade_tx_present"] = UPGRADE_TX in evidence_text
    checks["evidence_payment_tx_present"] = FIRST_PAYMENT_TX in evidence_text
    checks["evidence_activation_time_present"] = "2025-05-13" in evidence_text and "11:27:06" in evidence_text
    checks["evidence_announcement_present"] = "2025-05-08" in evidence_text

    panel = pd.read_csv(PANEL, parse_dates=["cohort_date"])
    gross = panel[panel.gross_period.isin(["pre", "post"])]
    checks["panel_rows_total"] = int(len(panel))
    by = gross.groupby(["gross_period", "platform"]).size()
    for period, (start, end), days in [("pre", CLEAN_PRE, 21), ("post", CLEAN_POST, 21)]:
        for plat in PLATFORMS:
            checks[f"panel_{period}_{plat}_days"] = int(by.get((period, plat), 0)) == days
        dates = sorted(gross[gross.gross_period == period].cohort_date.dt.strftime("%Y-%m-%d").unique())
        checks[f"panel_{period}_window"] = dates[0] == start and dates[-1] == end and len(dates) == days
    checks["panel_no_anticipation_rows"] = not panel.cohort_date.between(
        pd.Timestamp(ANNOUNCEMENT_DATE), pd.Timestamp("2025-05-13")
    ).any()
    return checks


def calibrate() -> dict:
    panel = pd.read_csv(PANEL, parse_dates=["cohort_date"])
    pre = panel[panel.gross_period == "pre"].copy()
    pre["wd"] = pre.cohort_date.dt.weekday

    summary = {}
    for outcome in OUTCOMES:
        pre["y"] = np.log1p(pre[outcome])
        resids = {}
        for plat in PLATFORMS:
            sub = pre[pre.platform == plat]
            X = sm.add_constant(pd.get_dummies(sub.wd, prefix="wd", drop_first=True).astype(float))
            fit = sm.OLS(sub.y, X).fit()
            resids[plat] = dict(zip(sub.cohort_date, fit.resid))
        dates = sorted(resids["Pump.fun"])
        pump = np.array([resids["Pump.fun"][t] for t in dates])
        moon = np.array([resids["Moonshot"][t] for t in dates])
        diff = pump - moon
        sd_diff = float(diff.std(ddof=1))
        ratio = EFFECT / sd_diff
        summary[outcome] = {
            "n_pre_days_per_platform": int(len(dates)),
            "pump_resid_sd": float(pump.std(ddof=1)),
            "moonshot_resid_sd": float(moon.std(ddof=1)),
            "paired_diff_resid_sd": sd_diff,
            "paired_diff_same_day_correlation": float(np.corrcoef(pump, moon)[0, 1]),
            "effect": EFFECT,
            "effect_over_diff_resid_sd": float(ratio),
            "scale_gate_bounds": list(SCALE_BOUNDS),
            "scale_gate_pass": bool(SCALE_BOUNDS[0] <= ratio <= SCALE_BOUNDS[1]),
        }
    return summary


def main() -> int:
    checks = check_inputs()
    calibration = calibrate()
    gate_pass_all = all(v["scale_gate_pass"] for v in calibration.values())
    inputs_ok = all(v is True for k, v in checks.items() if isinstance(v, bool))

    manifest = {
        "experiment": "s2_timing",
        "inputs": {
            str(p.relative_to(IDENTIFICATION_ROOT)): {"sha256": sha256(p)}
            for p in [PANEL, REGISTRY, EVIDENCE, CONTRACT]
        },
        "input_checks": checks,
        "inputs_ok": inputs_ok,
    }
    (EXPERIMENT_ROOT / "data_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    summary = {
        "experiment": "s2_timing",
        "event_id": EVENT_ID,
        "calibration_sample": {"clean_pre": list(CLEAN_PRE), "clean_post": list(CLEAN_POST)},
        "model": "per-platform OLS of log1p(outcome) on weekday fixed effects, clean pre only",
        "residual_process": "paired Pump-minus-Moonshot daily residual difference (the series the DGP block-bootstraps)",
        "outcomes": calibration,
        "scale_gate": {
            "rule": "stop unless 0.25 <= effect / pre residual SD <= 1.0",
            "pass_all_outcomes": gate_pass_all,
            "decision": "proceed" if (gate_pass_all and inputs_ok) else "STOP: scale blocker",
            "note": "Effect must not be modified by the agent (plan section 3). "
                    "Alternative SD conventions (pooled 0.121/0.117, Pump-only 0.100/0.070, "
                    "Moonshot-only 0.142/0.153) move the ratio further above 1, not below it.",
        },
    }
    (EXPERIMENT_ROOT / "calibration_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(json.dumps(summary["scale_gate"], indent=2))
    return 0 if (gate_pass_all and inputs_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
