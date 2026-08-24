"""Monte Carlo driver for experiment S3 (few platform clusters).

Spec: Web3AI4IO/identification/experiment_plans/S3_few_platform_clusters.md
(revised scale rule, 2026-08-13).

Phases:
  1. Seeded zero-arm pilot (>= 2,000 reps, seed PILOT_SEED) to estimate
     s_ATT, the sampling SD of the null 30-day DiD estimator (treated-post
     TWFE coefficient, window rel_day -60..29, assignment pump_ecosystem).
  2. Scale check: 0.20 must lie in [0.25, 1.0] x s_ATT. On failure, write
     calibration_summary.json with status SCALE_BLOCKER and stop (spec
     sec. 3/9).
  3. Full run: zero / low_power (0.20) / moderate (0.5 x s_ATT) arms,
     10,000 reps each, four inference methods.

Writes: calibration_summary.json, artifacts/results_long.parquet,
artifacts/results_summary.csv, artifacts/null_pvalue_diagnostics.csv,
artifacts/sign_enumeration.csv, artifacts/treatment_permutations.csv,
artifacts/rep_construction.parquet, artifacts/run_metadata.json.

Run from the experiment root:
  .venv/bin/python -m src.run_experiment
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src import estimator as est
from src.dgp import (
    N_DAYS,
    N_UNITS,
    build_y0_panel,
    inject_effect,
    load_dgp_components,
    rep_rng,
)
from src.validate_panel import EXPECTED_UNITS, EXPERIMENT_ROOT

PILOT_SEED = 20260813
N_PILOT = 2_000
ARM_SEEDS = {"zero": 20260813001, "low_power": 20260813002, "moderate": 20260813003}
N_REPS = 10_000
LOW_POWER_EFFECT = 0.20
SCALE_WINDOW = (0.25, 1.0)
ALPHA = 0.05
CHUNK = 1_000
TREATED_IDX = EXPECTED_UNITS.index("pump_ecosystem")  # 0

ARTIFACTS = EXPERIMENT_ROOT / "artifacts"

METHODS = ["crv1_normal", "crv1_t3", "wild_sign_enum", "randomization_inference"]


def _pilot(comp, fit) -> np.ndarray:
    """Seeded zero-arm pilot: DiD point estimates under the sharp null."""
    out = np.empty(N_PILOT)
    for rep in range(N_PILOT):
        y0, _ = build_y0_panel(comp, rep_rng(PILOT_SEED, rep))
        out[rep] = est.estimate_did(y0.reshape(-1, 1), fit)["beta"][0]
    return out


def _method_rows(arm: str, rep_ids: np.ndarray, assignment: str,
                 method: str, estimate, se, t, p, true_att: float,
                 injected: float) -> pd.DataFrame:
    n = len(rep_ids)
    if method == "crv1_normal":
        crit = est.CRIT_NORMAL
    elif method == "crv1_t3":
        crit = est.CRIT_T3
    else:
        crit = None
    ci_lo = estimate - crit * se if crit is not None else np.full(n, np.nan)
    ci_hi = estimate + crit * se if crit is not None else np.full(n, np.nan)
    return pd.DataFrame({
        "arm": arm,
        "rep_id": rep_ids,
        "assignment": assignment,
        "method": method,
        "estimate": estimate,
        "se": se,
        "t_stat": t,
        "p_value": p,
        "ci_lower": ci_lo,
        "ci_upper": ci_hi,
        "ci_available": crit is not None,
        "reject_05": p < ALPHA,
        "injected_effect": injected,
        "true_att": true_att,
    })


def _run_arm(comp, fits, arm: str, effect: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run one arm; returns (long results, per-rep construction records)."""
    seed = ARM_SEEDS[arm]
    rows: list[pd.DataFrame] = []
    construction: list[dict] = []
    for start in range(0, N_REPS, CHUNK):
        rep_ids = np.arange(start, min(start + CHUNK, N_REPS))
        R = len(rep_ids)
        Y = np.empty((N_DAYS * N_UNITS, R))
        for j, rep in enumerate(rep_ids):
            y0, starts = build_y0_panel(comp, rep_rng(seed, int(rep)))
            Y[:, j] = inject_effect(y0, TREATED_IDX, effect).reshape(-1)
            construction.append({
                "arm": arm, "rep_id": int(rep),
                "treated_unit": EXPECTED_UNITS[TREATED_IDX],
                "injected_effect": effect, "true_att": effect,
                "rng": f"SeedSequence([{seed}, {int(rep)}])",
                **{f"block_start_{k:02d}": int(s) for k, s in enumerate(starts)},
            })
        assignments = range(N_UNITS) if arm == "zero" else [TREATED_IDX]
        betas = {}
        for a in assignments:
            obs = est.estimate_did(Y, fits[a])
            betas[a] = obs["beta"]
            p_norm = est.pvalue_crv1_normal(obs["t"])
            p_t3 = est.pvalue_crv1_t3(obs["t"])
            p_wild, _ = est.wild_sign_enum_pvalues(Y, fits[a], obs=obs)
            name = EXPECTED_UNITS[a]
            for method, p in [("crv1_normal", p_norm), ("crv1_t3", p_t3),
                              ("wild_sign_enum", p_wild)]:
                rows.append(_method_rows(
                    arm, rep_ids, name, method, obs["beta"], obs["se"],
                    obs["t"], p, true_att=effect, injected=effect))
        if arm == "zero":
            beta_mat = np.stack([betas[a] for a in range(N_UNITS)])  # (4, R)
            p_ri = est.randomization_pvalues(beta_mat, observed_idx=TREATED_IDX)
            rows.append(_method_rows(
                arm, rep_ids, EXPECTED_UNITS[TREATED_IDX],
                "randomization_inference", betas[TREATED_IDX],
                np.full(R, np.nan), np.full(R, np.nan), p_ri,
                true_att=effect, injected=effect))
    return pd.concat(rows, ignore_index=True), pd.DataFrame(construction)


def _mc_se(p: float, n: int) -> float:
    return float(np.sqrt(p * (1 - p) / n))


def _summarize(long: pd.DataFrame) -> pd.DataFrame:
    """Per arm x method metrics on the pump_ecosystem assignment."""
    main = long[long.assignment == EXPECTED_UNITS[TREATED_IDX]]
    out = []
    for (arm, method), g in main.groupby(["arm", "method"]):
        n = len(g)
        n_fail = int((~np.isfinite(g.p_value)).sum())
        rej = float(g.reject_05.mean())
        rec = {
            "arm": arm, "method": method, "n_reps": n, "n_failures": n_fail,
            "failure_rate": n_fail / n,
            "rejection_rate_05": rej, "mc_se_rejection": _mc_se(rej, n),
            "fpr": rej if arm == "zero" else np.nan,
            "power": rej if arm != "zero" else np.nan,
            "fnr": 1 - rej if arm != "zero" else np.nan,
            "claim_accuracy": (1 - rej) if arm == "zero" else rej,
            "p_value_mean": float(g.p_value.mean()),
            "p_value_median": float(g.p_value.median()),
        }
        if g.ci_available.all():
            cov = ((g.ci_lower <= g.true_att) & (g.true_att <= g.ci_upper)).mean()
            rec["ci_coverage"] = float(cov)
            rec["ci_mean_width"] = float((g.ci_upper - g.ci_lower).mean())
            rec["mc_se_coverage"] = _mc_se(float(cov), n)
        else:
            rec["ci_coverage"] = np.nan
            rec["ci_mean_width"] = np.nan
            rec["mc_se_coverage"] = np.nan
        out.append(rec)
    summ = pd.DataFrame(out)
    # Calibration gain and power loss relative to the baseline method.
    base = summ[summ.method == "crv1_normal"].set_index("arm")
    summ["calibration_gain_vs_baseline"] = summ.apply(
        lambda r: (base.loc["zero", "fpr"] - r.fpr)
        if r.arm == "zero" else np.nan, axis=1)
    summ["power_loss_vs_baseline"] = summ.apply(
        lambda r: (base.loc[r.arm, "power"] - r.power)
        if r.arm != "zero" else np.nan, axis=1)
    return summ


def _null_diagnostics(long: pd.DataFrame) -> pd.DataFrame:
    """Zero-arm p-value distributions per method x assignment (incl. placebo)."""
    zero = long[long.arm == "zero"]
    qs = [0.0, 0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.0]
    out = []
    for (method, assignment), g in zero.groupby(["method", "assignment"]):
        p = g.p_value.values
        unique_p = np.sort(np.unique(p))
        attainable = (",".join(f"{v:.6g}" for v in unique_p)
                      if len(unique_p) <= 32 else "continuous")
        rec = {"method": method, "assignment": assignment, "n_reps": len(p),
               "frac_le_05": float((p <= ALPHA).mean()),
               "frac_le_10": float((p <= 0.10).mean()),
               "n_distinct_p_values": len(unique_p),
               "attainable_p_values": attainable}
        for q in qs:
            rec[f"q{int(q*100):02d}"] = float(np.quantile(p, q))
        out.append(rec)
    return pd.DataFrame(out)


def main() -> None:
    t0 = time.perf_counter()
    ARTIFACTS.mkdir(exist_ok=True)
    comp = load_dgp_components()
    fits = [est.precompute(a) for a in range(N_UNITS)]

    # --- Phase 1+2: pilot and revised scale check ---
    pilot_estimates = _pilot(comp, fits[TREATED_IDX])
    s_att = float(pilot_estimates.std(ddof=1))
    ratio = LOW_POWER_EFFECT / s_att
    scale_pass = SCALE_WINDOW[0] <= ratio <= SCALE_WINDOW[1]
    calibration = {
        "spec": "Web3AI4IO/identification/experiment_plans/S3_few_platform_clusters.md",
        "generated_by": "src/run_experiment.py",
        "scale_rule_revision": "2026-08-13",
        "scale_metric": {
            "name": "s_ATT",
            "definition": (
                "sampling SD (ddof=1) of the null 30-day DiD estimator: "
                "TWFE treated-post coefficient, unit FE + day FE, window "
                "rel_day -60..29, CRV1 by unit; estimated from a seeded "
                "zero-arm pilot with the same DGP/estimator/window"
            ),
            "pilot_seed": PILOT_SEED,
            "pilot_replications": N_PILOT,
            "pilot_assignment": EXPECTED_UNITS[TREATED_IDX],
            "pilot_estimate_mean": float(pilot_estimates.mean()),
            "s_att": s_att,
        },
        "scale_check": {
            "injected_effect_low_power": LOW_POWER_EFFECT,
            "ratio_effect_over_s_att": ratio,
            "required_ratio_interval": list(SCALE_WINDOW),
            "pass": bool(scale_pass),
        },
        "moderate_effect": 0.5 * s_att,
        "status": "OK" if scale_pass else "SCALE_BLOCKER",
    }
    if not scale_pass:
        (EXPERIMENT_ROOT / "calibration_summary.json").write_text(
            json.dumps(calibration, indent=2) + "\n")
        print(f"SCALE_BLOCKER: 0.20 / s_ATT = {ratio:.4f} not in {SCALE_WINDOW}")
        return
    moderate_effect = float(0.5 * s_att)
    t_pilot = time.perf_counter()

    # --- Phase 3: full run ---
    effects = {"zero": 0.0, "low_power": LOW_POWER_EFFECT,
               "moderate": moderate_effect}
    long_parts, construction_parts = [], []
    for arm, effect in effects.items():
        long_df, constr_df = _run_arm(comp, fits, arm, effect)
        long_parts.append(long_df)
        construction_parts.append(constr_df)
        print(f"arm {arm}: {len(long_df)} result rows")
    long = pd.concat(long_parts, ignore_index=True)
    construction = pd.concat(construction_parts, ignore_index=True)

    summary = _summarize(long)
    diagnostics = _null_diagnostics(long)

    # --- Artifacts ---
    long.to_parquet(ARTIFACTS / "results_long.parquet", index=False)
    construction.to_parquet(ARTIFACTS / "rep_construction.parquet", index=False)
    summary.to_csv(ARTIFACTS / "results_summary.csv", index=False)
    diagnostics.to_csv(ARTIFACTS / "null_pvalue_diagnostics.csv", index=False)
    pd.DataFrame(est.SIGN_VECTORS.astype(int), columns=EXPECTED_UNITS).assign(
        vector_id=lambda d: d.index).to_csv(
        ARTIFACTS / "sign_enumeration.csv", index=False)
    pd.DataFrame({"assignment_id": range(N_UNITS),
                  "treated_unit": EXPECTED_UNITS}).to_csv(
        ARTIFACTS / "treatment_permutations.csv", index=False)

    t_end = time.perf_counter()
    calibration["runtime_seconds"] = {
        "pilot": t_pilot - t0, "full_run": t_end - t_pilot, "total": t_end - t0}
    (EXPERIMENT_ROOT / "calibration_summary.json").write_text(
        json.dumps(calibration, indent=2) + "\n")
    (ARTIFACTS / "run_metadata.json").write_text(json.dumps({
        "generated_by": "src/run_experiment.py",
        "pilot_seed": PILOT_SEED, "n_pilot": N_PILOT,
        "arm_seeds": ARM_SEEDS, "n_reps_per_arm": N_REPS,
        "effects": effects, "s_att": s_att,
        "runtime_seconds": calibration["runtime_seconds"],
        "runtime_iso_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=2) + "\n")

    print(f"s_ATT = {s_att:.6f} (pilot seed {PILOT_SEED}, {N_PILOT} reps)")
    print(f"0.20 / s_ATT = {ratio:.4f} in {SCALE_WINDOW}: PASS")
    print(f"moderate effect = 0.5 x s_ATT = {moderate_effect:.6f}")
    print(f"runtime: pilot {t_pilot - t0:.1f}s, full {t_end - t_pilot:.1f}s")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
