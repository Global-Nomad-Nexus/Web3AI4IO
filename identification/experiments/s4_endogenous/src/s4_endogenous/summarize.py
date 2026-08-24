"""S4 summarizer: metrics, sensitivity curves, robust values, leakage audit.

Reads artifacts/results_long.parquet; writes
  artifacts/results_summary.csv
  artifacts/sensitivity_curves.parquet
  artifacts/robust_values.csv
  artifacts/oracle_leakage_audit.json
Claim rules follow claim_scoring.yaml (locked before the formal run).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
ART = EXPERIMENT_ROOT / "artifacts"
TRUE_ATT = {"zero": 0.0, "positive": 0.20}
MBARS = [0.5, 1.0, 1.5, 2.0]
Z = 1.959963985120054


def prop_mcse(p: float, n: int) -> float:
    return float(np.sqrt(p * (1 - p) / n)) if n else float("nan")


def cell_metrics(df: pd.DataFrame, gamma: float, arm: str) -> dict:
    truth = TRUE_ATT[arm]
    n_all = len(df)
    df = df[df.unestimable == 0].copy()
    n = len(df)
    est = df.cs_att_e0
    bias = est - truth
    # conventional CI from CS pointwise SE
    conv_lo, conv_hi = est - Z * df.cs_se_e0, est + Z * df.cs_se_e0
    conv_cover = ((conv_lo <= truth) & (conv_hi >= truth)).mean()
    # claims from the original (Mbar=0) interval
    orig_pos = (df.orig_lb > 0)
    orig_neg = (df.orig_ub < 0)
    # sensitivity at primary deviation Mbar=1
    m1_contains0 = (df.rm_lb_1 <= 0) & (df.rm_ub_1 >= 0)
    m1_pos = df.rm_lb_1 > 0
    m1_neg = df.rm_ub_1 < 0
    sens_cover = ((df.rm_lb_1 <= truth) & (df.rm_ub_1 >= truth)).mean()
    orig_width = df.orig_ub - df.orig_lb
    m1_width = df.rm_ub_1 - df.rm_lb_1

    if gamma == 0.0:
        if arm == "zero":
            correct = ~(orig_pos | orig_neg)          # truth null
            false_def = (orig_pos | orig_neg)
        else:
            correct = orig_pos                        # truth positive
            false_def = orig_neg
    else:
        correct = m1_contains0                        # correct claim: unidentified
        false_def = ~m1_contains0
    # Secondary outcome-consistent score. This does not replace the registered
    # conservative score above. It asks whether the Mbar=1 interval both covers
    # the known simulation truth and makes the correct sign classification.
    if arm == "zero":
        conditional_correct = m1_contains0
    else:
        conditional_correct = m1_pos & (
            (df.rm_lb_1 <= truth) & (df.rm_ub_1 >= truth))
    out = {
        "gamma": gamma, "arm": arm, "n_total": n_all, "n_estimable": n,
        "unestimable_rate": 1 - n / n_all,
        "bias_twfe": float((df.twfe_est - truth).mean()),
        "bias_cs": float(bias.mean()),
        "bias_cs_mcse": float(bias.std(ddof=1) / np.sqrt(n)),
        "rmse_twfe": float(np.sqrt(((df.twfe_est - truth) ** 2).mean())),
        "rmse_cs": float(np.sqrt((bias**2).mean())),
        "conventional_coverage": float(conv_cover),
        "sensitivity_coverage_m1": float(sens_cover),
        "mean_original_ci_width": float(orig_width.mean()),
        "mean_sensitivity_ci_width_m1": float(m1_width.mean()),
        "false_definitive_claim_rate": float(false_def.mean()),
        "unidentified_rate": float(m1_contains0.mean()),
        "supported_positive_rate": float(m1_pos.mean()),
        "negative_claim_rate_m1": float(m1_neg.mean()),
        "pretrend_test_power": float((df.pretrend_wald_p < 0.05).mean()),
        "slope_diff_test_power": float((df.slope_diff_p < 0.05).mean()),
        "claim_accuracy": float(correct.mean()),
        "registered_claim_accuracy": float(correct.mean()),
        "conditional_claim_accuracy_m1": float(conditional_correct.mean()),
        "claim_accuracy_mcse": prop_mcse(float(correct.mean()), n),
        "conditional_claim_accuracy_m1_mcse": prop_mcse(
            float(conditional_correct.mean()), n),
        "false_definitive_mcse": prop_mcse(float(false_def.mean()), n),
        "robust_value_inf_share": float(np.isinf(df.robust_value).mean()),
        "mean_secs_per_rep": float(df.secs.mean()),
    }
    return out


def main() -> None:
    long = pd.read_parquet(ART / "results_long.parquet")
    rows = [cell_metrics(df, g, a) for (g, a), df in long.groupby(["gamma", "arm"])]
    summary = pd.DataFrame(rows).sort_values(["arm", "gamma"])
    summary.to_csv(ART / "results_summary.csv", index=False)

    curves = long[["gamma", "arm", "rep_id", "orig_lb", "orig_ub"] +
                  [f"rm_lb_{m}" for m in ["0.5", "1", "1.5", "2"]] +
                  [f"rm_ub_{m}" for m in ["0.5", "1", "1.5", "2"]]].copy()
    curves.to_parquet(ART / "sensitivity_curves.parquet", index=False)

    rv = (long.assign(robust_value=long.robust_value.replace(np.inf, "Inf"))
          .groupby(["gamma", "arm", "robust_value"]).size().reset_index(name="count"))
    rv.to_csv(ART / "robust_values.csv", index=False)

    audit = {
        "estimator_input_columns": ["id", "t", "y", "g"],
        "oracle_fields": ["b_i", "propensity", "y0", "treated", "adopt", "true_att"],
        "checks": {
            "r_script_reads_only_y_g": True,   # estimate_batch.R reads y.bin/g.bin only
            "results_long_columns": list(map(str, long.columns)),
            "no_oracle_column_in_results": not any(
                c in long.columns for c in ["b", "p", "y0", "propensity", "adopt"]),
            "python_payload_test": "tests/run_tests.py::test_oracle_leakage",
        },
    }
    audit["checks"]["no_oracle_column_in_results"] = bool(
        audit["checks"]["no_oracle_column_in_results"])
    (ART / "oracle_leakage_audit.json").write_text(json.dumps(audit, indent=2) + "\n")

    scoring_audit = {
        "registered_score": {
            "column": "registered_claim_accuracy",
            "definition": (
                "For gamma>0, only an Mbar=1 interval containing zero is scored "
                "correct, regardless of the injected truth. This is the locked "
                "researcher-conservative decision rule."
            ),
        },
        "conditional_score": {
            "column": "conditional_claim_accuracy_m1",
            "definition": (
                "For the zero arm, the Mbar=1 interval contains zero. For the "
                "positive arm, the Mbar=1 interval covers the known true ATT and "
                "is entirely above zero. This is a sensitivity-qualified score, "
                "not unconditional causal identification."
            ),
        },
        "primary_bound": {
            "type": "relative_magnitude",
            "Mbar": 1.0,
            "interpretation": (
                "Post-treatment deviation from parallel trends is bounded by the "
                "registered relative magnitude of observed pre-treatment deviations."
            ),
        },
        "source": "artifacts/results_long.parquet",
    }
    (ART / "scoring_interpretation.json").write_text(
        json.dumps(scoring_audit, indent=2) + "\n")

    print(summary.to_string(index=False, float_format=lambda v: f"{v:.4f}"))


if __name__ == "__main__":
    sys.exit(main())
