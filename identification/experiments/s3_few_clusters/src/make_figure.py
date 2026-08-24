"""Figure for experiment S3: zero-arm p-value distributions + power bars.

Reads artifacts/results_long.parquet and artifacts/results_summary.csv
(produced by src/run_experiment.py) and writes artifacts/figure_s3.pdf and
artifacts/figure_s3.png.

Run from the experiment root:
  .venv/bin/python -m src.make_figure
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.run_experiment import ARTIFACTS, EXPECTED_UNITS, TREATED_IDX

METHOD_LABELS = {
    "crv1_normal": "Baseline: CRV1 + normal crit",
    "crv1_t3": "Comparator A: CRV1 + t(3) crit",
    "wild_sign_enum": "Comparator B: wild sign enum (16)",
    "randomization_inference": "Reference: randomization (4)",
}


def main() -> None:
    long = pd.read_parquet(ARTIFACTS / "results_long.parquet")
    summary = pd.read_csv(ARTIFACTS / "results_summary.csv")
    main_unit = EXPECTED_UNITS[TREATED_IDX]

    fig, axes = plt.subplots(
        2, 4, figsize=(13, 6), gridspec_kw={"height_ratios": [1, 1]})

    # Top row: zero-arm p-value histograms (pump_ecosystem assignment).
    zero = long[(long.arm == "zero") & (long.assignment == main_unit)]
    for j, (method, label) in enumerate(METHOD_LABELS.items()):
        ax = axes[0, j]
        p = zero.loc[zero.method == method, "p_value"].values
        bins = np.linspace(0, 1, 21)
        ax.hist(p, bins=bins, color="steelblue", edgecolor="white")
        ax.axvline(0.05, color="crimson", ls="--", lw=1)
        unif = len(p) / (len(bins) - 1)
        ax.axhline(unif, color="grey", ls=":", lw=1)
        fpr = (p < 0.05).mean()
        ax.set_title(f"{label}\nFPR@0.05 = {fpr:.4f}", fontsize=8)
        ax.set_xlim(0, 1)
        if j == 0:
            ax.set_ylabel("zero arm: reps")
        ax.set_xlabel("p-value", fontsize=8)

    # Bottom row: rejection rates — zero (FPR) and injected arms (power).
    ax = axes[1, 0]
    methods = list(METHOD_LABELS)
    x = np.arange(len(methods))
    width = 0.27
    for k, (arm, color, tag) in enumerate([
            ("zero", "grey", "zero (FPR, target 0.05)"),
            ("low_power", "darkorange", "low_power (0.20)"),
            ("moderate", "seagreen", "moderate (0.5 x s_ATT)")]):
        vals = []
        for m in methods:
            hit = summary[(summary.arm == arm) & (summary.method == m)]
            vals.append(float(hit["rejection_rate_05"].iloc[0])
                        if len(hit) else np.nan)
        ax.bar(x + (k - 1) * width, vals, width, label=tag, color=color)
    ax.axhline(0.05, color="crimson", ls="--", lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(["CRV1\nnormal", "CRV1\nt(3)", "wild\nenum", "random.\ninf"],
                       fontsize=8)
    ax.set_ylabel("rejection rate @ 0.05")
    ax.set_ylim(0, 1.0)
    ax.legend(fontsize=7, loc="upper right")
    ax.set_title("Rejection rates by arm and method", fontsize=9)

    # Bottom middle: CI coverage (methods with CIs only).
    ax = axes[1, 1]
    ci_methods = ["crv1_normal", "crv1_t3"]
    xc = np.arange(len(ci_methods))
    for k, (arm, color) in enumerate(
            [("zero", "grey"), ("low_power", "darkorange"),
             ("moderate", "seagreen")]):
        vals = [float(summary[(summary.arm == arm) & (summary.method == m)]
                      ["ci_coverage"].iloc[0]) for m in ci_methods]
        ax.bar(xc + (k - 1) * width, vals, width, label=arm, color=color)
    ax.axhline(0.95, color="crimson", ls="--", lw=1)
    ax.set_xticks(xc)
    ax.set_xticklabels(["CRV1 normal", "CRV1 t(3)"], fontsize=8)
    ax.set_ylabel("95% CI coverage of true ATT")
    ax.set_ylim(0, 1.05)
    ax.set_title("CI coverage (nominal 0.95)", fontsize=9)

    # Bottom right two panels: zero-arm estimate distributions.
    ax = axes[1, 2]
    est0 = zero.loc[zero.method == "crv1_normal", "estimate"].values
    ax.hist(est0, bins=60, color="steelblue")
    ax.axvline(0.20, color="darkorange", ls="--", lw=1, label="low_power effect")
    ax.set_title("Zero-arm DiD estimates\n(s_ATT = SD of this dist.)", fontsize=9)
    ax.legend(fontsize=7)
    ax.set_xlabel("estimated ATT", fontsize=8)

    ax = axes[1, 3]
    ax.axis("off")
    txt = (
        "S3 few-cluster inference (G = 4)\n"
        "Panel-calibrated DGP: 7-day moving-block\n"
        "bootstrap of PumpSwap pre-period residuals.\n"
        "10,000 reps per arm; zero arm also\n"
        "evaluates all 4 treated identities.\n"
        "Attainable p: wild enum multiples of 2/16;\n"
        "randomization {0.25, 0.5, 0.75, 1}."
    )
    ax.text(0.0, 0.95, txt, va="top", fontsize=8, family="monospace")

    fig.suptitle("S3: few-platform-cluster inference on the PumpSwap panel", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(ARTIFACTS / "figure_s3.pdf")
    fig.savefig(ARTIFACTS / "figure_s3.png", dpi=200)
    print(f"wrote {ARTIFACTS / 'figure_s3.pdf'} and .png")


if __name__ == "__main__":
    main()
