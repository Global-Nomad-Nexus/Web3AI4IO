"""Figure S2: timing-method performance, primary effect 0.15, launches."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = EXPERIMENT_ROOT / "artifacts"

METHOD_LABELS = {
    "naive_announcement": "Naive announcement",
    "verified_activation": "Verified activation",
    "activation_plus_anticipation_gate": "Activation + gate",
}
ARM_LABELS = {"zero": "Zero", "no_anticipation": "No anticipation", "anticipation": "Anticipation"}
COLORS = {"naive_announcement": "#c0392b", "verified_activation": "#e67e22",
          "activation_plus_anticipation_gate": "#2471a3"}


def main() -> None:
    df = pd.read_csv(ARTIFACTS / "results_summary.csv")
    d = df[(df.outcome == "launches") & (df.effect_label == "primary")]
    arms = ["zero", "no_anticipation", "anticipation"]
    methods = list(METHOD_LABELS)

    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.5))
    x = range(len(arms))

    ax = axes[0, 0]
    for j, m in enumerate(methods):
        sub = d[(d.method == m) & (d.gap == 5)].set_index("arm").loc[arms]
        ax.errorbar([i + (j - 1) * 0.22 for i in x], sub.bias, yerr=1.96 * sub.bias_mcse,
                    fmt="o", color=COLORS[m], label=METHOD_LABELS[m], capsize=3)
    ax.axhline(0, color="k", lw=0.8, ls="--")
    ax.set_xticks(list(x), [ARM_LABELS[a] for a in arms])
    ax.set_ylabel("Bias (log)")
    ax.set_title("(a) Bias by arm, gap = 5 days")
    ax.legend(fontsize=8)

    ax = axes[0, 1]
    for j, m in enumerate(methods):
        sub = d[(d.method == m) & (d.gap == 5)].set_index("arm").loc[arms]
        ax.errorbar([i + (j - 1) * 0.22 for i in x], sub.coverage, yerr=1.96 * sub.coverage_mcse,
                    fmt="o", color=COLORS[m], capsize=3)
    ax.axhline(0.95, color="k", lw=0.8, ls="--")
    ax.set_xticks(list(x), [ARM_LABELS[a] for a in arms])
    ax.set_ylabel("95% CI coverage")
    ax.set_title("(b) Coverage by arm, gap = 5 days")
    ax.set_ylim(0, 1.05)

    ax = axes[1, 0]
    for m in methods:
        sub = d[(d.method == m) & (d.arm == "anticipation")].sort_values("gap")
        ax.plot(sub.gap, sub.attenuation_ratio, "o-", color=COLORS[m], label=METHOD_LABELS[m])
    ax.axhline(1.0, color="k", lw=0.8, ls="--")
    ax.set_xlabel("Announcement gap (days before activation)")
    ax.set_ylabel("Attenuation ratio (est / true)")
    ax.set_title("(c) Attenuation vs gap, anticipation arm")
    ax.legend(fontsize=8)
    ax.set_xticks([3, 5, 7, 10])

    ax = axes[1, 1]
    gate = d[d.method == "activation_plus_anticipation_gate"]
    for a in arms:
        sub = gate[gate.arm == a].sort_values("gap")
        ax.plot(sub.gap, sub.gate_rejection_rate, "o-", label=ARM_LABELS[a])
    ax.axhline(0.05, color="k", lw=0.8, ls="--")
    ax.set_xlabel("Announcement gap (days before activation)")
    ax.set_ylabel("Gate rejection rate (p < 0.05)")
    ax.set_title("(d) Anticipation gate behaviour")
    ax.legend(fontsize=8)
    ax.set_xticks([3, 5, 7, 10])
    ax.set_ylim(0, 1.05)

    fig.suptitle("Figure S2. Announcement vs activation timing, semi-synthetic Pump.fun/Moonshot\n"
                 "launches, primary effect 0.15 log, 2,000 replications per cell", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(ARTIFACTS / "figure_s2.pdf")
    fig.savefig(ARTIFACTS / "figure_s2.png", dpi=200)
    print("wrote figure_s2.pdf/.png")


if __name__ == "__main__":
    main()
