#!/usr/bin/env python
"""Rebuild all summary artifacts from the long Monte Carlo results.

Acceptance criterion 8.6: everything here is computed ONLY from
results_long.parquet and cohort_time_truth.parquet, never from the
simulation code, so the summary is reproducible from stored outputs.

Usage:
  python summarize.py --results artifacts/results_long.parquet \
      --truth artifacts/cohort_time_truth.parquet --out artifacts

Writes <out>/results_summary.csv, <out>/weight_diagnostics.csv,
<out>/figure_s1.pdf, <out>/figure_s1.png, <out>/summary_check.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

EXP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP_DIR / "src"))

from simplefig import figure_s1  # noqa: E402

METRIC_COLUMNS = [
    "arm", "method", "n_runs", "n_valid", "unestimable_rate",
    "true_att_mean", "bias", "mcse_bias", "relative_bias", "rmse",
    "coverage_95", "mcse_coverage", "false_positive_rate",
    "false_negative_rate", "sign_correctness", "claim_accuracy",
]


def summarize_arm_method(df: pd.DataFrame) -> dict:
    """Metric row for one arm x method slice of the long results."""
    n_runs = len(df)
    unest = df["unestimable"].to_numpy(dtype=bool)
    valid = df.loc[~unest]
    n_valid = len(valid)
    row = {
        "arm": df["arm"].iloc[0],
        "method": df["method"].iloc[0],
        "n_runs": n_runs,
        "n_valid": n_valid,
        "unestimable_rate": float(unest.mean()),
    }
    if n_valid == 0:
        for k in METRIC_COLUMNS:
            row.setdefault(k, np.nan)
        return row

    err = valid["error"].to_numpy(dtype=float)
    true = valid["true_att"].to_numpy(dtype=float)
    est = valid["estimate"].to_numpy(dtype=float)
    covered = valid["covered"].to_numpy(dtype=bool)
    reject = valid["reject_null"].to_numpy(dtype=bool)

    bias = float(np.mean(err))
    cov = float(np.mean(covered))
    true_mean = float(np.mean(true))
    treated_arm = abs(true_mean) > 1e-12

    # Claim: "the treatment has a non-zero effect of this sign".
    # Correct claim: zero arm -> do not reject; treated arm -> reject AND
    # the point estimate has the true sign.
    sign_ok = np.sign(est) == np.sign(true)
    if treated_arm:
        claim_acc = float(np.mean(reject & sign_ok))
        fpr = np.nan
        fnr = float(np.mean(~reject))
        sign_corr = float(np.mean(sign_ok))
        rel_bias = bias / true_mean
    else:
        claim_acc = float(np.mean(~reject))
        fpr = float(np.mean(reject))
        fnr = np.nan
        sign_corr = np.nan
        rel_bias = np.nan

    row.update({
        "true_att_mean": true_mean,
        "bias": bias,
        "mcse_bias": float(np.std(err, ddof=1) / np.sqrt(n_valid)),
        "relative_bias": rel_bias,
        "rmse": float(np.sqrt(np.mean(err**2))),
        "coverage_95": cov,
        "mcse_coverage": float(np.sqrt(cov * (1 - cov) / n_valid)),
        "false_positive_rate": fpr,
        "false_negative_rate": fnr,
        "sign_correctness": sign_corr,
        "claim_accuracy": claim_acc,
    })
    return row


def weight_diagnostics(results: pd.DataFrame) -> pd.DataFrame:
    """TWFE implicit-weighting diagnostic aggregated per arm."""
    tw = results[results["method"] == "twfe"]
    wcols = sorted(c for c in tw.columns if c.startswith("twfe_w_cohort"))
    rows = []
    for arm, g in tw.groupby("arm"):
        row = {
            "arm": arm,
            "n_reps": len(g),
            "neg_weight_sum_treated_mean": float(g["twfe_neg_weight_sum_treated"].mean()),
            "neg_weight_sum_treated_sd": float(g["twfe_neg_weight_sum_treated"].std(ddof=1)),
            "neg_weight_sum_treated_min": float(g["twfe_neg_weight_sum_treated"].min()),
        }
        for c in wcols:
            row[f"{c}_mean"] = float(g[c].mean())
        rows.append(row)
    return pd.DataFrame(rows)


def truth_alignment_check(results: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """Rebuild the overall true ATT per rep from the cell-level truth file
    (supported cells weighted by registered treated creator-day counts) and
    compare to results_long.true_att. Acceptance criterion 8.3."""
    sup = truth[truth["supported"]]
    wsum = sup.groupby(["arm", "rep"])["n_treated_cell"].transform("sum")
    overall = (
        sup.assign(contrib=sup["true_att_cell"] * sup["n_treated_cell"] / wsum)
        .groupby(["arm", "rep"])["contrib"].sum()
        .rename("true_att_rebuilt")
        .reset_index()
    )
    merged = results.merge(overall, on=["arm", "rep"], how="left", validate="many_to_one")
    diff = (merged["true_att"] - merged["true_att_rebuilt"]).abs()
    return {
        "n_rep_method_rows": int(len(merged)),
        "max_abs_diff_true_att": float(diff.max()),
        "aligned": bool(diff.max() < 1e-9),
        "supported_cells_per_rep": int(sup.groupby(["arm", "rep"]).size().mode().iloc[0]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = pd.read_parquet(args.results)
    truth = pd.read_parquet(args.truth)

    summary = pd.DataFrame(
        [summarize_arm_method(g) for (_, _), g in results.groupby(["arm", "method"])]
    )[METRIC_COLUMNS]
    summary.to_csv(out_dir / "results_summary.csv", index=False)

    wd = weight_diagnostics(results)
    wd.to_csv(out_dir / "weight_diagnostics.csv", index=False)

    check = truth_alignment_check(results, truth)
    check["min_valid_runs_per_arm_method"] = int(summary["n_valid"].min())
    (out_dir / "summary_check.json").write_text(json.dumps(check, indent=2) + "\n")

    figure_s1(
        summary[["arm", "method", "bias", "coverage_95"]].to_dict("records"),
        str(out_dir / "figure_s1.pdf"),
        str(out_dir / "figure_s1.png"),
    )

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)
    print(summary.to_string(index=False))
    print("\nweight diagnostics:")
    print(wd.to_string(index=False))
    print("\ntruth alignment check:", json.dumps(check))
    print(f"\nwrote results_summary.csv, weight_diagnostics.csv, "
          f"summary_check.json, figure_s1.pdf/.png under {out_dir}")


if __name__ == "__main__":
    main()
