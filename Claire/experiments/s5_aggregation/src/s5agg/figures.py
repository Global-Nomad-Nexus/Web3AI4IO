"""Figure for S5 (5-arm revision, locked 2026-08-14).

Panel A: Thursday bias (bars, four non-zero arm cells) and zero-arm RMSE
(diamonds) by method. Panel B: effect attenuation (mean/truth, scale-free)
by weekday offset for each method x temporal profile; the substantive family
is drawn solid, the calibration family faint dotted — the two families are
reported separately, never pooled.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import paths

ARM_LABELS = {
    "zero": "zero",
    "substantive_transient": "substantive 0.30, transient",
    "substantive_persistent": "substantive 0.30, persistent",
    "calibration_transient": "calibration 0.5xSD_null, transient",
    "calibration_persistent": "calibration 0.5xSD_null, persistent",
}
NONZERO_ARMS = [a for a in ARM_LABELS if a != "zero"]
METHOD_LABELS = {
    "daily": "daily DiD",
    "naive_weekly": "naive weekly",
    "exposure_weekly": "exposure-weighted weekly",
    "aligned_weekly": "event-aligned 7-day",
}
WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def make_figure(results_summary: pd.DataFrame, out_base: Path):
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))

    # --- panel A: bias by method x non-zero arm at Thursday; zero-arm RMSE ---
    ax = axes[0]
    thu = results_summary[results_summary["offset"] == 0]
    width = 0.19
    xs = np.arange(len(paths.METHODS))
    for i, arm in enumerate(NONZERO_ARMS):
        sub = thu[thu["arm"] == arm].set_index("method").loc[paths.METHODS]
        ax.bar(
            xs + (i - 1.5) * width,
            sub["bias"],
            width,
            yerr=1.96 * sub["mcse_bias"],
            label=ARM_LABELS[arm],
            alpha=0.85,
        )
    zero = thu[thu["arm"] == "zero"].set_index("method").loc[paths.METHODS]
    ax.scatter(
        xs, zero["rmse"], marker="D", color="black", zorder=5, s=18,
        label="zero arm RMSE",
    )
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels([METHOD_LABELS[m] for m in paths.METHODS], rotation=15, ha="right")
    ax.set_ylabel("bias / RMSE vs seven-day ATT truth")
    ax.set_title("A. Thursday primary (offset 0)")
    ax.legend(fontsize=6.5, ncol=2)

    # --- panel B: attenuation vs weekday offset, method x profile ---
    ax = axes[1]
    colors = {"daily": "C0", "naive_weekly": "C2", "exposure_weekly": "C4", "aligned_weekly": "C7"}
    for method in paths.METHODS:
        for profile, ls in [("transient", "-"), ("persistent", "--")]:
            for family, alpha, lw in [("substantive", 1.0, 1.6), ("calibration", 0.45, 1.0)]:
                sub = (
                    results_summary[
                        (results_summary["arm"] == f"{family}_{profile}")
                        & (results_summary["method"] == method)
                    ]
                    .sort_values("offset")
                )
                ax.plot(
                    sub["offset"],
                    sub["effect_attenuation"],
                    ls,
                    marker="o" if family == "substantive" else None,
                    ms=3,
                    color=colors[method],
                    alpha=alpha,
                    lw=lw,
                    label=(
                        f"{METHOD_LABELS[method]}, {profile}"
                        if family == "substantive"
                        else None
                    ),
                )
    ax.axhline(1.0, color="grey", lw=0.8)
    labels = [WEEKDAY_SHORT[(3 + k) % 7] for k in range(7)]
    ax.set_xticks(range(7))
    ax.set_xticklabels([f"{k}\n{lab}" for k, lab in zip(range(7), labels)], fontsize=8)
    ax.set_xlabel("weekday offset k (event weekday)")
    ax.set_ylabel("effect attenuation (mean estimate / truth)")
    ax.set_title("B. Weekday-alignment sensitivity\n(solid = substantive, faint dotted = calibration)", fontsize=9)
    ax.legend(fontsize=6.5, ncol=2)

    fig.suptitle(
        "S5 temporal aggregation — PumpSwap-panel-calibrated aggregation evaluation "
        "(3-market primary: pump vs raydium + orca)",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(out_base.with_suffix(".pdf"))
    fig.savefig(out_base.with_suffix(".png"), dpi=200)
    plt.close(fig)
