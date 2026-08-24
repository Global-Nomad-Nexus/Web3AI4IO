from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENTS = ROOT / "Web3AI4IO" / "Claire" / "experiments"
OUT = ROOT / "paper" / "figs"

INK = "#17212B"
MUTED = "#667085"
GRID = "#D9E1E8"
BLUE = "#2166AC"
TEAL = "#16827A"
GREEN = "#2A8C68"
AMBER = "#E39D26"
RED = "#C84B3A"
PURPLE = "#7251B5"
LIGHT_BLUE = "#E8F1F8"
LIGHT_TEAL = "#E7F4F1"
LIGHT_AMBER = "#FFF4DC"
LIGHT_RED = "#FBE9E5"
LIGHT_GREY = "#F1F3F5"


def apply_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 10.5,
            "axes.labelsize": 9.5,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "legend.fontsize": 8.3,
            "axes.edgecolor": INK,
            "axes.labelcolor": INK,
            "text.color": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "axes.linewidth": 0.8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.04,
        }
    )


def save(fig: mpl.figure.Figure, stem: str) -> None:
    fig.savefig(OUT / f"{stem}.pdf")
    fig.savefig(OUT / f"{stem}.png", dpi=300)
    plt.close(fig)


def rounded_box(ax, xy, width, height, face, edge, title, lines=(), title_color=INK):
    x, y = xy
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.025",
        linewidth=1.0,
        facecolor=face,
        edgecolor=edge,
    )
    ax.add_patch(box)
    ax.text(
        x + width / 2,
        y + height * 0.72,
        title,
        ha="center",
        va="center",
        fontweight="bold",
        fontsize=8.3,
        color=title_color,
    )
    if lines:
        ax.text(
            x + width / 2,
            y + height * 0.34,
            "\n".join(lines),
            ha="center",
            va="center",
            fontsize=6.8,
            color=MUTED,
            linespacing=1.25,
        )
    return box


def make_data_layer_demo() -> None:
    fig, ax = plt.subplots(figsize=(7.1, 2.85))
    ax.set_xlim(-1.55, 6.05)
    ax.set_ylim(-0.8, 4.75)
    ax.axis("off")
    ax.text(
        0,
        1.025,
        "Coverage remains chain specific after standardization",
        fontsize=10.8,
        fontweight="bold",
        transform=ax.transAxes,
    )

    columns = [
        "Launch\nuniverse",
        "Pool and\nliquidity",
        "Terminal\noutcome",
        "Activity\noutcomes",
        "Metadata",
        "Event design\nstatus",
    ]
    rows = [
        "Solana\nPump.fun",
        "Base\nClanker",
        "BNB Chain\nFour.meme",
        "TRON\nSunPump",
    ]
    for j, label in enumerate(columns):
        ax.text(j + 0.5, 4.25, label, ha="center", va="center", fontsize=8.4, fontweight="bold")
    for i, label in enumerate(rows):
        ax.text(-0.12, 3.5 - i, label, ha="right", va="center", fontsize=8.8, fontweight="bold")

    cells = [
        [
            ("observed", "832,941\noutcomes"),
            ("bounded", "1,651\ngraduated"),
            ("observed", "terminal\nstate"),
            ("bounded", "294 decoded\ntokens"),
            ("excluded", "outside\nrelease"),
            ("conditional", "conditional"),
        ],
        [
            ("observed", "62,618\nlaunches"),
            ("observed", "62,618\npools"),
            ("missing", "not\ncollected"),
            ("missing", "not\ncollected"),
            ("excluded", "outside\nrelease"),
            ("accepted", "accepted"),
        ],
        [
            ("observed", "1,593,679\nlaunches"),
            ("bounded", "15,403\npools"),
            ("missing", "not\ncollected"),
            ("missing", "not\ncollected"),
            ("excluded", "outside\nrelease"),
            ("rejected", "rejected"),
        ],
        [
            ("observed", "104,548\nlaunches"),
            ("bounded", "1,831\npools"),
            ("missing", "not\ncollected"),
            ("missing", "not\ncollected"),
            ("excluded", "outside\nrelease"),
            ("rejected", "rejected"),
        ],
    ]
    styles = {
        "observed": (TEAL, "white", ""),
        "bounded": (LIGHT_AMBER, INK, ""),
        "missing": (LIGHT_GREY, MUTED, ""),
        "excluded": ("white", MUTED, "///"),
        "accepted": (GREEN, "white", ""),
        "conditional": (AMBER, "white", ""),
        "rejected": ("#9AA4B2", "white", ""),
    }
    for i, row in enumerate(cells):
        y = 3.05 - i
        for j, (status, label) in enumerate(row):
            face, txt, hatch = styles[status]
            rect = Rectangle(
                (j + 0.07, y),
                0.86,
                0.88,
                facecolor=face,
                edgecolor="white" if status in {"observed", "accepted", "conditional", "rejected"} else GRID,
                linewidth=0.9,
                hatch=hatch,
            )
            ax.add_patch(rect)
            ax.text(j + 0.50, y + 0.44, label, ha="center", va="center", fontsize=7.7, color=txt)

    legend = [
        (TEAL, "Observed"),
        (LIGHT_AMBER, "Bounded or selected"),
        (LIGHT_GREY, "Not collected"),
        ("white", "Excluded by release policy"),
    ]
    legend_positions = [(-0.02, -0.28), (2.95, -0.28), (-0.02, -0.60), (2.95, -0.60)]
    for idx, (color, label) in enumerate(legend):
        x, y = legend_positions[idx]
        rect = Rectangle(
            (x, y),
            0.18,
            0.18,
            facecolor=color,
            edgecolor=GRID,
            hatch="///" if idx == 3 else "",
        )
        ax.add_patch(rect)
        ax.text(x + 0.25, y + 0.09, label, va="center", fontsize=7.4, color=MUTED)

    save(fig, "fig_data_layer_coverage_map")


def read_summary(folder: str) -> pd.DataFrame:
    return pd.read_csv(EXPERIMENTS / folder / "artifacts" / "results_summary.csv")


def panel_label(ax, label: str, title: str) -> None:
    ax.set_title(
        f"{label}  {title}",
        loc="left",
        fontweight="bold",
        pad=6,
        fontsize=8.5,
        linespacing=1.12,
    )


def clean_axes(ax, grid_axis="x") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.7, alpha=0.85)
    ax.set_axisbelow(True)


def make_stress_test_demo() -> None:
    fig = plt.figure(figsize=(7.1, 5.25))
    outer = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.12], hspace=0.72)
    top = outer[0].subgridspec(1, 3, wspace=0.62)
    bottom = outer[1].subgridspec(1, 2, width_ratios=[1.0, 2.3], wspace=0.62)

    s1 = read_summary("s1_staggered")
    ax = fig.add_subplot(top[0, 0])
    panel_label(ax, "A", "S1: Staggered\nheterogeneity")
    arm_order = ["zero", "homogeneous", "heterogeneous"]
    method_style = {"twfe": (BLUE, "o", "TWFE"), "cs_att": (AMBER, "s", "Group time ATT")}
    for method, (color, marker, label) in method_style.items():
        d = s1[s1["method"] == method].set_index("arm").loc[arm_order]
        y = np.arange(3) + (0.09 if method == "twfe" else -0.09)
        ax.errorbar(
            1000 * d["bias"],
            y,
            xerr=1000 * 1.96 * d["mcse_bias"],
            fmt=marker,
            color=color,
            markerfacecolor="white" if method == "cs_att" else color,
            markersize=5.2,
            linewidth=1.2,
            capsize=2,
            label=label,
        )
    ax.axvline(0, color=INK, linewidth=0.8)
    ax.set_yticks(range(3), ["Zero", "Homogeneous", "Heterogeneous"])
    ax.set_xlabel(r"Bias, $\times 10^{-3}$ (95% MC interval)", fontsize=7.4)
    ax.set_xlim(-1.2, 1.2)
    ax.legend(frameon=False, loc="upper left", fontsize=7.0)
    ax.text(0.98, 0.04, "Both near zero", transform=ax.transAxes, ha="right", color=GREEN, fontsize=7.0)
    clean_axes(ax)

    s2 = read_summary("s2_timing")
    ax = fig.add_subplot(top[0, 1])
    panel_label(ax, "B", "S2: Activation\ntiming")
    d = s2[
        (s2["outcome"] == "launches")
        & (s2["effect_label"] == "primary")
        & (s2["gap"] == 5)
        & (s2["arm"] == "no_anticipation")
        & s2["method"].isin(["naive_announcement", "verified_activation"])
    ].set_index("method")
    vals = [d.loc["naive_announcement", "attenuation_ratio"], d.loc["verified_activation", "attenuation_ratio"]]
    ax.plot(vals, [0, 0], color=GRID, linewidth=4, solid_capstyle="round")
    ax.scatter(vals[0], 0, s=70, color=RED, marker="o", zorder=3)
    ax.scatter(vals[1], 0, s=75, color=TEAL, marker="D", zorder=3)
    ax.axvline(1.0, color=INK, linewidth=0.9, linestyle=":")
    ax.text(vals[0], 0.11, f"{vals[0]:.3f}", ha="center", color=RED, fontweight="bold")
    ax.text(vals[1], 0.11, f"{vals[1]:.3f}", ha="center", color=TEAL, fontweight="bold")
    ax.text(vals[0], -0.105, "Announcement", ha="center", color=RED, fontsize=7.6)
    ax.text(vals[1], -0.105, "Activation", ha="center", color=TEAL, fontsize=7.6)
    ax.text(0.02, 0.06, "Gate rejection: 32% to 50%", transform=ax.transAxes, fontsize=6.8, color=MUTED)
    ax.set_xlim(0.72, 1.03)
    ax.set_ylim(-0.22, 0.25)
    ax.set_yticks([])
    ax.set_xlabel("Recovered effect / truth", fontsize=7.4)
    clean_axes(ax)
    # Give Panel B a little more separation from Panel C at final paper scale.
    pos = ax.get_position()
    ax.set_position([pos.x0 - 0.018, pos.y0, pos.width - 0.012, pos.height])

    s3 = read_summary("s3_few_clusters")
    ax = fig.add_subplot(top[0, 2])
    panel_label(ax, "C", "S3: Four-cluster\ninference")
    d = s3[s3["arm"] == "zero"].set_index("method")
    methods = ["crv1_normal", "crv1_t3", "wild_sign_enum", "randomization_inference"]
    labels = ["CRV1 normal", "CRV1 t(3)", "Exact sign", "Randomization"]
    colors = [RED, AMBER, TEAL, BLUE]
    vals = [d.loc[m, "fpr"] for m in methods]
    y = np.arange(4)
    ax.scatter(vals, y, s=56, c=colors, marker="o", zorder=3)
    ax.axvline(0.05, color=INK, linewidth=0.9, linestyle=":", label="Nominal 0.05")
    for x, yy in zip(vals[:2], y[:2]):
        ax.text(x + 0.004, yy, f"{x:.3f}", va="center", fontsize=7.7)
    ax.text(0.004, 2.18, "min p = 0.125", fontsize=6.6, color=TEAL)
    ax.text(0.004, 3.18, "min p = 0.25", fontsize=6.6, color=BLUE)
    ax.set_yticks(y, labels, fontsize=7.0)
    ax.invert_yaxis()
    ax.set_xlim(-0.004, 0.085)
    ax.set_xlabel("False positive rate", fontsize=7.4)
    ax.legend(frameon=False, loc="lower right", fontsize=6.8)
    clean_axes(ax)

    s4 = read_summary("s4_endogenous")
    ax = fig.add_subplot(bottom[0, 0])
    panel_label(ax, "D", "S4: Endogenous\nadoption")
    d = s4[s4["arm"] == "positive"].sort_values("gamma")
    ax.plot(d["gamma"], d["bias_twfe"], color=RED, marker="o", linewidth=1.8, label="Static TWFE")
    ax.plot(d["gamma"], d["bias_cs"], color=BLUE, marker="s", markerfacecolor="white", linewidth=1.8, label="Group time ATT")
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.set_xticks(d["gamma"], ["None", "Moderate", "Strong"])
    ax.set_xlabel("Selection severity")
    ax.set_ylabel("Bias")
    ax.set_ylim(-0.04, 0.78)
    ax.legend(frameon=False, loc="upper left", fontsize=7.0)
    ax.text(0.98, 0.55, "TWFE: 0.707", transform=ax.transAxes, ha="right", color=RED, fontsize=7.0)
    clean_axes(ax, grid_axis="y")

    s5 = read_summary("s5_aggregation")
    ax = fig.add_subplot(bottom[0, 1])
    panel_label(ax, "E", "S5: Temporal aggregation")
    d = s5[s5["arm"] == "substantive_transient"].copy()
    methods = ["daily", "naive_weekly", "exposure_weekly", "aligned_weekly"]
    method_labels = ["Daily", "Naive calendar", "Exposure weighted", "Event aligned"]
    weekdays = ["Thu", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"]
    mat = np.full((len(methods), 7), np.nan)
    for i, method in enumerate(methods):
        for j in range(7):
            row = d[(d["method"] == method) & (d["offset"] == j)]
            if not row.empty:
                mat[i, j] = row.iloc[0]["effect_attenuation"]
    norm = TwoSlopeNorm(vmin=0.38, vcenter=1.0, vmax=1.20)
    im = ax.imshow(mat, cmap="PuOr_r", norm=norm, aspect="auto")
    ax.set_xticks(range(7), weekdays)
    ax.set_yticks(range(4), method_labels, fontsize=7.2)
    ax.tick_params(axis="x", rotation=0)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            value = mat[i, j]
            rgba = im.cmap(im.norm(value))
            luminance = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=7.8, color="white" if luminance < 0.52 else INK)
    ax.add_patch(Rectangle((-0.49, -0.49), 0.98, 3.98, fill=False, edgecolor=INK, linewidth=1.7))
    cbar = fig.colorbar(im, ax=ax, orientation="horizontal", fraction=0.10, pad=0.18, aspect=35)
    cbar.set_label("Recovered effect divided by truth")
    cbar.set_ticks([0.4, 0.7, 1.0, 1.2])

    save(fig, "fig_stress_test_atlas")


def main() -> None:
    apply_style()
    make_data_layer_demo()
    make_stress_test_demo()


if __name__ == "__main__":
    main()
