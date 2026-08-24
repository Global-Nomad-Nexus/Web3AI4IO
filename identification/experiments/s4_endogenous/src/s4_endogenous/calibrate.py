"""S4 calibration: rebuild the eligible creator sample and DGP inputs.

Reads the three locked canonical parquet inputs, rebuilds the eligible
creator sample (>=3 launches in the 21-day calibration pre-period), estimates
creator baselines, weekday effects and per-creator linear pretrends on
log1p(launch count), and extracts the never-v4.1 residual block pool used by
the semi-synthetic DGP.

Writes, under the experiment root:
  data_manifest.json         input SHA256 + structural checks
  sample_flow.csv            stage-by-stage row/creator counts
  calibration_summary.json   all calibration numbers used by the DGP
  artifacts/calibration.npz  a_i, b_i, weekday effects, residual pool

Exits non-zero when a structural check fails.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = EXPERIMENT_ROOT.parents[2] / "data" / "canonical" / "v1" / "base"

LAUNCHES = DATA_ROOT / "launches" / "part-00000.parquet"
PROTOCOL_CONFIG = DATA_ROOT / "protocol_config" / "part-00000.parquet"
COVERAGE_LEDGER = DATA_ROOT / "coverage_ledger" / "part-00000.parquet"

OBSERVED_WINDOW = ("2025-08-18", "2025-10-01")
PRE_PERIOD = ("2025-08-18", "2025-09-07")  # 21 days
MIN_PRE_LAUNCHES = 3
ACCEPTED_VERSIONS = ("v4.0_mev_or_hook", "v4.1_mev_or_hook")
COHORT_WINDOW = ("2025-09-24", "2025-10-01")
TBAR = 9.5  # centering of the 21-day pre trend axis

EXPECTED = {"eligible": 1379, "never_v41": 1121}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_launches() -> pd.DataFrame:
    la = pd.read_parquet(LAUNCHES, columns=["token_id", "launch_at", "protocol_version"])
    pc = pd.read_parquet(PROTOCOL_CONFIG, columns=["token_id", "creator"])
    df = la.merge(pc, on="token_id", how="left", validate="m:1")
    if df["creator"].isna().any():
        raise RuntimeError("creator join produced nulls")
    df["date"] = df["launch_at"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    df = df[df["protocol_version"].isin(ACCEPTED_VERSIONS)]
    return df


def build_sample(df: pd.DataFrame) -> dict:
    obs = df[(df.date >= OBSERVED_WINDOW[0]) & (df.date <= OBSERVED_WINDOW[1])]
    pre = obs[(obs.date <= PRE_PERIOD[1])]

    pre_counts = pre.groupby("creator").size()
    eligible = np.array(sorted(pre_counts[pre_counts >= MIN_PRE_LAUNCHES].index))

    v41_users = set(obs.loc[obs.protocol_version == "v4.1_mev_or_hook", "creator"])
    never_mask = np.array([c not in v41_users for c in eligible])
    never_creators = eligible[never_mask]

    first_v41 = (
        obs[obs.protocol_version == "v4.1_mev_or_hook"]
        .groupby("creator")["date"].min()
    )
    first_v41_elig = first_v41[first_v41.index.isin(eligible)]
    in_window = first_v41_elig[
        (first_v41_elig >= COHORT_WINDOW[0]) & (first_v41_elig <= COHORT_WINDOW[1])
    ]
    cohort_sizes = in_window.groupby(in_window.dt.strftime("%Y-%m-%d")).size()
    # also record the S1-style rule (>=3 v4.0 launches before first v4.1) for transparency
    v40_counts_pre_first = []
    for c, d0 in in_window.items():
        sub = obs[(obs.creator == c) & (obs.date < d0) &
                  (obs.protocol_version == "v4.0_mev_or_hook")]
        v40_counts_pre_first.append(len(sub) >= MIN_PRE_LAUNCHES)
    cohort_sizes_s1_rule = in_window[pd.array(v40_counts_pre_first)]
    cohort_sizes_s1_rule = cohort_sizes_s1_rule.groupby(
        cohort_sizes_s1_rule.dt.strftime("%Y-%m-%d")).size()

    return {
        "obs": obs,
        "eligible": eligible,
        "never_creators": never_creators,
        "cohort_sizes": cohort_sizes,
        "cohort_sizes_s1_rule": cohort_sizes_s1_rule,
    }


def estimate_panel_params(obs: pd.DataFrame, eligible: np.ndarray,
                          never_creators: np.ndarray) -> dict:
    """Two-way FE weekday effects + per-creator intercept/slope on log1p counts."""
    pre = obs[(obs.creator.isin(eligible)) & (obs.date <= PRE_PERIOD[1])]
    days = pd.date_range(PRE_PERIOD[0], PRE_PERIOD[1], freq="D")
    counts = (
        pre.groupby(["creator", "date"]).size().unstack(fill_value=0)
        .reindex(index=eligible, columns=days, fill_value=0)
    )
    y = np.log1p(counts.to_numpy(dtype=np.float64))  # creators x 21
    n_creators, n_days = y.shape
    dow = days.weekday.to_numpy()

    # balanced two-way FE: creator mean, then weekday mean of the remainder
    alpha_fe = y.mean(axis=1, keepdims=True)
    resid1 = y - alpha_fe
    w_full = np.zeros(n_days)
    for d in range(7):
        w_full[dow == d] = resid1[:, dow == d].mean()
    w_full -= w_full.mean()

    # per-creator OLS of (y - weekday) on [1, t - TBAR]
    x = np.arange(n_days, dtype=np.float64) - TBAR
    yw = y - w_full[None, :]
    b = (yw * x[None, :]).sum(axis=1) / (x**2).sum()
    a = (yw - b[:, None] * x[None, :]).mean(axis=1)
    r = yw - a[:, None] - b[:, None] * x[None, :]

    never_idx = np.where(np.isin(eligible, never_creators))[0]
    return {
        "days": days,
        "weekday_effects": {str(int(d)): float(w_full[dow == d][0]) for d in range(7)},
        "weekday_by_day": w_full,
        "a": a,
        "b": b,
        "resid_pool": r[never_idx],
        "y_sd_pooled": float(y.std(ddof=1)),
        "resid_sd": float(r.std(ddof=1)),
    }


def main() -> int:
    (EXPERIMENT_ROOT / "artifacts").mkdir(exist_ok=True)
    df = load_launches()
    sample = build_sample(df)
    obs = sample["obs"]
    eligible = sample["eligible"]
    never_creators = sample["never_creators"]
    cohort_sizes = sample["cohort_sizes"]

    params = estimate_panel_params(obs, eligible, never_creators)

    cov = pd.read_parquet(COVERAGE_LEDGER)
    coverage_checks = {
        "rows": int(len(cov)),
        "launch_available_all": bool(cov["launch_available"].all()),
        "metadata_available_all": bool(cov["metadata_available"].all()),
        "creator_status_values": cov["creator_status"].value_counts().to_dict(),
        "coverage_status_values": cov["coverage_status"].value_counts().to_dict(),
    }

    checks = {
        "eligible_matches_audit": int(len(eligible)) == EXPECTED["eligible"],
        "never_v41_matches_audit": int(len(never_creators)) == EXPECTED["never_v41"],
        "cohort_window_days": int(len(cohort_sizes)) == 8,
        "coverage_launch_available": coverage_checks["launch_available_all"],
    }

    np.savez(
        EXPERIMENT_ROOT / "artifacts" / "calibration.npz",
        a=params["a"], b=params["b"],
        weekday_by_day=params["weekday_by_day"],
        resid_pool=params["resid_pool"],
        eligible=eligible, never_creators=never_creators,
    )

    manifest = {
        "experiment": "s4_endogenous",
        "inputs": {
            str(p.relative_to(EXPERIMENT_ROOT.parents[2])): {
                "sha256": sha256(p),
                "rows": int(pd.read_parquet(p).shape[0]) if p != COVERAGE_LEDGER else coverage_checks["rows"],
            }
            for p in [LAUNCHES, PROTOCOL_CONFIG, COVERAGE_LEDGER]
        },
        "structural_checks": checks,
        "coverage_ledger": coverage_checks,
    }
    (EXPERIMENT_ROOT / "data_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    flow = pd.DataFrame([
        ("launches_rows_accepted_versions", int(len(df)), ""),
        ("observed_window_rows", int(len(obs)), f"{OBSERVED_WINDOW[0]}..{OBSERVED_WINDOW[1]}"),
        ("observed_window_creators", int(obs.creator.nunique()), ""),
        ("pre_period_rows", int(len(obs[obs.date <= PRE_PERIOD[1]])), f"{PRE_PERIOD[0]}..{PRE_PERIOD[1]}"),
        ("eligible_creators", int(len(eligible)), f">={MIN_PRE_LAUNCHES} launches in pre-period"),
        ("never_v41_creators", int(len(never_creators)), "no v4.1 launch in observed window"),
        ("cohort_creators_0924_1001", int(cohort_sizes.sum()), "eligible, first v4.1 in cohort window"),
    ], columns=["stage", "n", "rule"])
    flow.to_csv(EXPERIMENT_ROOT / "sample_flow.csv", index=False)

    summary = {
        "experiment": "s4_endogenous",
        "pre_period": list(PRE_PERIOD),
        "observed_window": list(OBSERVED_WINDOW),
        "eligible_creators": int(len(eligible)),
        "never_v41_creators": int(len(never_creators)),
        "audit_expectations": EXPECTED,
        "cohort_sizes_eligible": {k: int(v) for k, v in cohort_sizes.items()},
        "cohort_proportions": [float(v / cohort_sizes.sum()) for v in cohort_sizes],
        "cohort_sizes_s1_rule_for_reference": {k: int(v) for k, v in sample["cohort_sizes_s1_rule"].items()},
        "weekday_effects": params["weekday_effects"],
        "baseline_a": {"mean": float(params["a"].mean()), "sd": float(params["a"].std(ddof=1)),
                       "q05": float(np.quantile(params["a"], 0.05)),
                       "q95": float(np.quantile(params["a"], 0.95))},
        "latent_slope_b": {"mean": float(params["b"].mean()), "sd": float(params["b"].std(ddof=1)),
                           "q05": float(np.quantile(params["b"], 0.05)),
                           "q95": float(np.quantile(params["b"], 0.95))},
        "residual_pool": {"creators": int(params["resid_pool"].shape[0]),
                          "days": int(params["resid_pool"].shape[1]),
                          "sd": params["resid_sd"]},
        "outcome_sd_pooled": params["y_sd_pooled"],
        "effect_scale": {"injected_log_effect": 0.20,
                         "effect_over_resid_sd": 0.20 / params["resid_sd"],
                         "effect_over_outcome_sd": 0.20 / params["y_sd_pooled"]},
        "structural_checks": checks,
    }
    (EXPERIMENT_ROOT / "calibration_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(json.dumps({k: summary[k] for k in
                      ["eligible_creators", "never_v41_creators", "cohort_sizes_eligible",
                       "latent_slope_b", "effect_scale", "structural_checks"]}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
