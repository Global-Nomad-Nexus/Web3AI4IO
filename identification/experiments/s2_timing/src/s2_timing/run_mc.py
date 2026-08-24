"""Formal Monte Carlo for the S2 timing experiment.

Cells: 2 outcomes x 2 effect sizes (0.15 primary, 0.10 robustness) x
4 announcement gaps (3/5/7/10 days) x 3 arms x 3 methods, 2,000 reps each.
Writes artifacts/results_long.parquet, artifacts/results_summary.csv and
artifacts/timing_gate_diagnostics.csv.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s2_timing.dgp import ARMS, EFFECTS, GAPS, OUTCOMES, calibrate, simulate  # noqa: E402
from s2_timing.estimators import METHODS, Z_CRIT, method_samples, run_methods  # noqa: E402

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
PANEL = EXPERIMENT_ROOT.parents[1] / "data" / "pump_moonshot_cohort_panel.csv"
ARTIFACTS = EXPERIMENT_ROOT / "artifacts"
N_REP = 2000
BASE_SEED = 20260513


def prop_mcse(p: float, n: int) -> float:
    return float(np.sqrt(p * (1 - p) / n))


def summarize_cell(outcome, effect_label, effect, gap, arm, results) -> tuple[list[dict], list[dict]]:
    tau = 0.0 if arm == "zero" else effect
    long_rows, summ_rows = [], []
    for method in METHODS:
        r = results[method]
        beta, se = r["beta"], r["se"]
        ok = ~np.isnan(beta)
        gate_p = r.get("gate_p", np.full(len(beta), np.nan))
        unidentified = r.get("unidentified", np.zeros(len(beta), dtype=bool))
        tstat = np.where(ok, beta / se, np.nan)
        rejected = ok & (np.abs(tstat) > Z_CRIT)
        covered = ok & (np.abs(beta - tau) <= Z_CRIT * se)

        for i in range(len(beta)):
            long_rows.append({
                "outcome": outcome, "effect_label": effect_label, "effect": effect,
                "gap": gap, "arm": arm, "rep": i, "method": method,
                "beta": beta[i], "se": se[i], "tstat": tstat[i],
                "rejected": bool(rejected[i]), "covered": bool(covered[i]),
                "gate_p": gate_p[i],
                "decision": "unidentified" if unidentified[i] else "identified",
            })

        n, n_ok = len(beta), int(ok.sum())
        b, s = beta[ok], se[ok]
        row = {
            "outcome": outcome, "effect_label": effect_label, "effect": effect,
            "gap": gap, "arm": arm, "method": method, "true_tau": tau,
            "n_rep": n, "n_identified": n_ok,
            "bias": float(b.mean() - tau), "bias_mcse": float(b.std(ddof=1) / np.sqrt(n_ok)),
            "rmse": float(np.sqrt(np.mean((b - tau) ** 2))),
            "coverage": float(covered[ok].mean()), "coverage_mcse": prop_mcse(covered[ok].mean(), n_ok),
            "fpr": float(rejected[ok].mean()) if arm == "zero" else np.nan,
            "fnr": float((~rejected[ok]).mean()) if arm != "zero" else np.nan,
            "sign_correctness": float((b > 0).mean()) if arm != "zero" else np.nan,
            "claim_accuracy": float((~rejected[ok]).mean()) if arm == "zero"
            else float((rejected[ok] & (beta[ok] > 0)).mean()),
            "claim_accuracy_mcse": prop_mcse(
                float((~rejected[ok]).mean()) if arm == "zero"
                else float((rejected[ok] & (beta[ok] > 0)).mean()), n_ok),
            "attenuation_ratio": float(b.mean() / tau) if tau else np.nan,
            "unidentified_rate": float(unidentified.mean()),
            "gate_rejection_rate": float((gate_p < 0.05).mean()) if method == METHODS[2] else np.nan,
            "anticipation_classification_accuracy": np.nan,
        }
        if method == METHODS[2]:
            fired = gate_p < 0.05
            row["anticipation_classification_accuracy"] = float(
                fired.mean() if arm == "anticipation" else (~fired).mean())
        summ_rows.append(row)
    return long_rows, summ_rows


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    long_rows, summ_rows = [], []
    for oi, outcome in enumerate(OUTCOMES):
        cal = calibrate(PANEL, outcome)
        for ei, (effect_label, effect) in enumerate(EFFECTS.items()):
            for gap in GAPS:
                days_samples = None
                for ai, arm in enumerate(ARMS):
                    seed = BASE_SEED + oi * 100_000 + ei * 10_000 + gap * 1_000 + ai * 100
                    rng = np.random.default_rng(seed)
                    D, days = simulate(cal, gap, arm, effect, N_REP, rng)
                    if days_samples is None:
                        days_samples = method_samples(days, gap)
                    results = run_methods(D, days_samples)
                    lr, sr = summarize_cell(outcome, effect_label, effect, gap, arm, results)
                    long_rows.extend(lr)
                    summ_rows.extend(sr)
                    print(f"done {outcome} {effect_label} gap={gap} arm={arm}", flush=True)

    long_df = pd.DataFrame(long_rows)
    summ_df = pd.DataFrame(summ_rows)
    long_df.to_parquet(ARTIFACTS / "results_long.parquet", index=False)
    summ_df.to_csv(ARTIFACTS / "results_summary.csv", index=False)

    gate = summ_df[summ_df.method == METHODS[2]][[
        "outcome", "effect_label", "effect", "gap", "arm",
        "gate_rejection_rate", "unidentified_rate",
        "anticipation_classification_accuracy"]].copy()
    mean_p = (long_df[long_df.method == METHODS[2]]
              .groupby(["outcome", "effect_label", "gap", "arm"]).gate_p.mean()
              .rename("mean_gate_p").reset_index())
    gate = gate.merge(mean_p, on=["outcome", "effect_label", "gap", "arm"])
    gate.to_csv(ARTIFACTS / "timing_gate_diagnostics.csv", index=False)
    print(f"wrote {len(long_df)} long rows, {len(summ_df)} summary rows")


if __name__ == "__main__":
    main()
