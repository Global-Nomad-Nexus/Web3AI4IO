"""Regenerate empirical paper figures from archived summaries with the shared theme."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

from paths import ARCHIVED, PAPER, REPRO
from theme import (
    AMBER,
    BLUE,
    GREEN,
    GRID,
    INK,
    LIGHT_AMBER,
    LIGHT_BLUE,
    LIGHT_GREY,
    MUTED,
    RED,
    TEAL,
    apply_style,
)

OUT = PAPER / "figs"
SCOPE = json.loads((REPRO / "scope.json").read_text(encoding="utf-8"))


def save(fig, stem: str, *, svg: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{stem}.pdf")
    fig.savefig(OUT / f"{stem}.png", dpi=300)
    if svg:
        fig.savefig(OUT / f"{stem}.svg")
    plt.close(fig)
    print(f"wrote {stem}")


def read_csv(rel: str) -> pd.DataFrame:
    return pd.read_csv(ARCHIVED / rel)


def load_json(rel: str) -> dict:
    return json.loads((ARCHIVED / rel).read_text(encoding="utf-8"))


def clean_axes(ax, grid_axis="y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.7, alpha=0.85)
    ax.set_axisbelow(True)


def make_teaser() -> None:
    """Generate the conceptual overview from archived evidence objects."""
    sol = load_json("release/solana_core.json")
    base = load_json("release/base_core.json")
    bnb = load_json("release/bnb_core.json")
    tron = load_json("release/tron_core.json")
    ladder = read_csv("application/deterministic_ladder.csv").set_index("rung")
    h1 = load_json("application/h1_rpc_mechanism_summary.json")
    telegram = load_json("application/telegram_mirror_design_summary.json")

    fig, ax = plt.subplots(figsize=(13.5, 6.9))
    ax.set_xlim(0, 13.5)
    ax.set_ylim(0, 6.9)
    ax.axis("off")
    for x in (4.25, 9.25):
        ax.plot([x, x], [0.15, 6.72], color=GRID, linewidth=1.0)

    def heading(x: float, label: str, title: str, subtitle: str, color: str) -> None:
        ax.text(x, 6.58, label, color=color, fontsize=8.2, fontweight="bold")
        ax.text(x + 0.22, 6.56, title, fontsize=13.0, fontweight="bold")
        ax.text(x, 6.30, subtitle, fontsize=7.5, color=MUTED)
        ax.plot([x, x + 0.42], [6.16, 6.16], color=color, linewidth=2.0, solid_capstyle="round")

    heading(0.12, "A", "Evidence infrastructure", "Four chain lifecycle data with explicit observation boundaries.", TEAL)
    heading(4.55, "B", "Three pillar evaluation", "Stakeholders, data resolution, and causal identification.", "#7251B5")
    heading(9.55, "C", "Evidence calibrated interpretation", "Inference narrows activity evidence to bounded stakeholder claims.", RED)

    chain_rows = [
        ("Solana  |  Pump.fun", sol["raw_reproduction"]["deduplicated_terminal_outcomes"], "complete terminal cohort", TEAL, "#E7F4F1"),
        ("Base  |  Clanker", base["tables"]["launches"]["rows"], "launch and pool universe", BLUE, LIGHT_BLUE),
        ("BNB Chain  |  Four.meme", bnb["tables"]["launches"]["rows"], "bounded launch universe", AMBER, LIGHT_AMBER),
        ("TRON  |  SunPump", tron["tables"]["launches"]["rows"], "bounded launch universe", RED, "#FBE9EE"),
    ]
    for i, (name, count, note, color, face) in enumerate(chain_rows):
        y = 5.58 - i * 0.82
        ax.add_patch(FancyBboxPatch((0.22, y - 0.48), 3.72, 0.66, boxstyle="round,pad=0.03,rounding_size=0.10", facecolor=face, edgecolor="none"))
        ax.add_patch(Circle((0.70, y - 0.15), 0.19, facecolor="white", edgecolor=color, linewidth=1.2))
        ax.text(0.70, y - 0.15, name[0], ha="center", va="center", color=color, fontweight="bold", fontsize=8.0)
        ax.text(1.02, y, name, fontsize=7.3, fontweight="bold", color=INK)
        shown = f"{count / 1_000_000:.2f}M" if count >= 1_000_000 else f"{count:,}"
        ax.text(1.02, y - 0.24, shown, fontsize=11.2, fontweight="bold", color=color)
        ax.text(2.02, y - 0.22, note, fontsize=6.6, color=MUTED)

    ax.text(0.22, 2.08, "Evidence layers", fontsize=9.0, fontweight="bold")
    columns = ["Launch", "Pool", "Outcome", "Activity"]
    for j, label in enumerate(columns):
        ax.text(1.66 + 0.62 * j, 1.79, label, ha="center", fontsize=6.4, color=MUTED)
    coverage = [[TEAL, AMBER, TEAL, AMBER], [TEAL, TEAL, GRID, GRID], [TEAL, AMBER, GRID, GRID], [TEAL, AMBER, GRID, GRID]]
    for i, label in enumerate(["Solana", "Base", "BNB", "TRON"]):
        y = 1.48 - i * 0.30
        ax.text(0.22, y, label, va="center", fontsize=7.0, fontweight="bold")
        for j, color in enumerate(coverage[i]):
            ax.add_patch(Circle((1.66 + 0.62 * j, y), 0.085, facecolor=color, edgecolor="#A9BAC7", linewidth=0.5))
    ax.add_patch(FancyBboxPatch((0.22, 0.12), 3.72, 0.33, boxstyle="round,pad=0.02,rounding_size=0.05", facecolor="#EEF5F8", edgecolor="#B9CDD8", linewidth=0.7))
    ax.text(2.08, 0.285, "Comparable representation does not imply a comparable causal sample", ha="center", va="center", fontsize=5.7, fontweight="bold", color="#31546B")

    pillar_specs = [
        (6.95, 5.55, "P1", "Stakeholder\nmetrics", "creator  |  trader  |  platform  |  community", "#D9F2EA", TEAL),
        (5.55, 4.08, "P2", "Data richness\nand frequency", "source  |  unit  |  horizon  |  frequency", LIGHT_BLUE, BLUE),
        (8.28, 4.08, "P3", "Causal\nidentification", "timing  |  comparison  |  diagnostics", LIGHT_AMBER, AMBER),
    ]
    for x, y, p, title, sub, face, edge in pillar_specs:
        ax.add_patch(Circle((x, y), 0.72, facecolor=face, edgecolor=edge, linewidth=1.0))
        ax.text(x, y + 0.34, p, ha="center", fontsize=6.8, color=edge, fontweight="bold")
        ax.text(x, y - 0.05, title, ha="center", va="center", fontsize=6.7, fontweight="bold", linespacing=1.0)
        ax.text(x, y - 0.39, sub, ha="center", fontsize=5.2, color=MUTED)
    ax.plot([6.48, 5.98], [5.0, 4.61], color=GRID, linewidth=1.0)
    ax.plot([7.42, 7.86], [5.0, 4.61], color=GRID, linewidth=1.0)
    ax.plot([6.27, 7.56], [4.08, 4.08], color=GRID, linewidth=1.0)
    ax.add_patch(Circle((6.95, 4.08), 0.42, facecolor="white", edgecolor="#8DA5B3", linewidth=1.0))
    ax.text(6.95, 4.17, "Evidence", ha="center", fontsize=7.0, fontweight="bold")
    ax.text(6.95, 3.96, "contract", ha="center", fontsize=7.0, fontweight="bold")

    ax.text(4.55, 2.95, "Sequential evidence disclosure", fontsize=9.0, fontweight="bold")
    rung_colors = [TEAL, "#CFE5F3", "#CFE5F3", "#FFE5A6", "#F5CBD6", "#E4D8F4", "#CFE5F3", "#7251B5"]
    for i in range(8):
        x = 4.75 + i * 0.56
        if i < 7:
            ax.plot([x + 0.14, x + 0.42], [2.50, 2.50], color=GRID, linewidth=2.2)
        ax.add_patch(Circle((x, 2.50), 0.18, facecolor=rung_colors[i], edgecolor="none"))
        ax.text(x, 2.52, f"L{i}", ha="center", va="center", fontsize=6.2, color="white" if i in (0, 7) else INK, fontweight="bold")

    ax.text(4.55, 1.98, "Known truth stress tests", fontsize=9.0, fontweight="bold")
    tests = [("Staggered", TEAL), ("Timing", RED), ("Four clusters", AMBER), ("Selection", "#C85C88"), ("Aggregation", "#7251B5")]
    for i, (label, color) in enumerate(tests):
        x = 4.85 + i * 0.88
        ax.add_patch(Circle((x, 1.52), 0.14, facecolor="white", edgecolor=color, linewidth=1.2))
        ax.add_patch(Circle((x, 1.52), 0.035, facecolor=color, edgecolor="none"))
        ax.text(x, 1.25, label, ha="center", fontsize=6.1, color=MUTED)
    ax.add_patch(FancyBboxPatch((4.55, 0.22), 4.30, 0.56, boxstyle="round,pad=0.03,rounding_size=0.06", facecolor="#F2ECFA", edgecolor="#D5C6EA", linewidth=0.8))
    ax.text(4.83, 0.50, "AI", ha="center", va="center", fontsize=7.0, color="white", fontweight="bold", bbox={"boxstyle": "round,pad=0.35", "facecolor": "#7251B5", "edgecolor": "none"})
    ax.text(5.22, 0.56, "Structured evidence improves evidence following", fontsize=7.2, fontweight="bold", color="#57417D")
    ax.text(5.22, 0.34, "one model evaluation; method omissions remain", fontsize=6.2, color=MUTED)

    ax.text(9.55, 5.86, "Market level estimate", fontsize=9.2, fontweight="bold")
    l0 = float(ladder.loc["L0", "estimate"])
    l2 = float(ladder.loc["L2", "estimate"])
    l2_lo = float(ladder.loc["L2", "ci95_low"])
    l2_hi = float(ladder.loc["L2", "ci95_high"])
    exact_p = float(ladder.loc["L6", "p_value"])
    y0 = 4.55
    ax.plot([9.88, 12.98], [y0, y0], color="#8DA5B3", linewidth=1.1)
    ax.scatter([10.42, 11.72], [5.18, 4.70], s=95, color=[TEAL, RED], zorder=3)
    ax.plot([10.42, 10.42], [y0, 5.42], color=TEAL, linewidth=1.6)
    ax.errorbar([11.72], [4.70], yerr=[[0.32], [0.35]], color=RED, capsize=5, linewidth=1.5)
    ax.annotate("", xy=(11.57, 4.78), xytext=(10.60, 5.17), arrowprops={"arrowstyle": "->", "color": "#8DA5B3", "lw": 1.0, "connectionstyle": "arc3,rad=0.15"})
    ax.text(10.42, 5.48, "before and after", ha="center", fontsize=6.3, color=MUTED)
    ax.text(10.42, 4.88, f"+{l0:.3f}", ha="center", fontsize=11.0, color=TEAL, fontweight="bold")
    ax.text(11.72, 5.48, "controls and two way FE", ha="center", fontsize=6.3, color=MUTED)
    ax.text(11.72, 5.22, f"+{l2:.3f}", ha="center", fontsize=11.0, color=RED, fontweight="bold")
    ax.text(11.72, 5.02, f"95% CI [{l2_lo:.3f}, {l2_hi:.3f}]", ha="center", fontsize=5.7, color=MUTED)
    ax.add_patch(FancyBboxPatch((9.70, 3.78), 3.24, 0.48, boxstyle="round,pad=0.03,rounding_size=0.06", facecolor="#FFF3F5", edgecolor="#E79AAF", linewidth=0.9))
    ax.text(11.32, 4.08, "CAUSAL EFFECT NOT IDENTIFIED", ha="center", fontsize=8.0, color="#92506A", fontweight="bold")
    ax.text(11.32, 3.88, f"unstable preperiod  |  four clusters  |  exact p = {exact_p:g}", ha="center", fontsize=5.8, color=MUTED)

    ax.text(9.55, 3.28, "Evidence that remains informative", fontsize=9.2, fontweight="bold")
    active = int(h1["full_30d_observed_active_tokens"])
    total = int(h1["post_30d_tokens"])
    att = 100 * float(telegram["matched_att"])
    remaining = [
        (2.63, LIGHT_BLUE, BLUE, "Operational mechanism", f"{active:,} / {total:,}", "observed 30 day transaction proxy activity"),
        (1.73, LIGHT_AMBER, AMBER, "Predictive marker", f"+{att:.3f} pp", "predictive association; causal exposure not established"),
    ]
    for y, face, edge, title, value, note in remaining:
        ax.add_patch(FancyBboxPatch((9.70, y - 0.40), 3.24, 0.67, boxstyle="round,pad=0.03,rounding_size=0.06", facecolor=face, edgecolor=edge, linewidth=0.8))
        ax.text(10.35, y + 0.08, title, fontsize=6.8, fontweight="bold", color="#31546B")
        ax.text(10.35, y - 0.17, value, fontsize=10.2, fontweight="bold", color="#31546B")
        ax.text(10.35, y - 0.31, note, fontsize=5.0, color=MUTED)
    ax.text(9.55, 0.92, "Stakeholder interpretation vector", fontsize=9.2, fontweight="bold")
    stakeholder = [("Creator", "mechanical", "#D9F2EA", TEAL), ("Trader", "unresolved", "#FBE0E7", RED), ("Platform", "venue active", LIGHT_BLUE, BLUE), ("Community", "predictive", "#E9E1F6", "#7251B5")]
    for i, (label, state, face, edge) in enumerate(stakeholder):
        x = 9.70 + i * 0.84
        ax.add_patch(FancyBboxPatch((x, 0.18), 0.70, 0.48, boxstyle="round,pad=0.02,rounding_size=0.04", facecolor=face, edgecolor=edge, linewidth=0.6))
        ax.text(x + 0.35, 0.47, label, ha="center", fontsize=6.4, fontweight="bold")
        ax.text(x + 0.35, 0.28, state, ha="center", fontsize=5.4, color=MUTED)

    save(fig, "teaser_figure", svg=True)


def make_coverage_map() -> None:
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


def panel_label(ax, label: str, title: str) -> None:
    ax.set_title(f"{label}  {title}", loc="left", fontweight="bold", pad=6, fontsize=8.5, linespacing=1.12)


def make_stress_atlas() -> None:
    fig = plt.figure(figsize=(7.1, 5.25))
    outer = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.12], hspace=0.72)
    top = outer[0].subgridspec(1, 3, wspace=0.62)
    bottom = outer[1].subgridspec(1, 2, width_ratios=[1.0, 2.3], wspace=0.62)

    s1 = read_csv("calibration/s1_results_summary.csv")
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
    clean_axes(ax, grid_axis="x")

    s2 = read_csv("calibration/s2_results_summary.csv")
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
    clean_axes(ax, grid_axis="x")
    pos = ax.get_position()
    ax.set_position([pos.x0 - 0.018, pos.y0, pos.width - 0.012, pos.height])

    s3 = read_csv("calibration/s3_results_summary.csv")
    ax = fig.add_subplot(top[0, 2])
    panel_label(ax, "C", "S3: Four-cluster\ninference")
    d = s3[s3["arm"] == "zero"].set_index("method")
    methods = ["crv1_normal", "crv1_t3", "wild_sign_enum", "randomization_inference"]
    labels = ["CRV1 normal", "CRV1 t(3)", "Exact sign", "Randomization"]
    colors = [RED, AMBER, TEAL, BLUE]
    vals = [d.loc[m, "fpr"] for m in methods]
    y = np.arange(4)
    ax.scatter(vals, y, s=56, c=colors, marker="o", zorder=3)
    ax.axvline(0.05, color=INK, linewidth=0.9, linestyle=":")
    for x, yy in zip(vals[:2], y[:2]):
        ax.text(x + 0.004, yy, f"{x:.3f}", va="center", fontsize=7.7)
    ax.text(0.004, 2.18, "min p = 0.125", fontsize=6.6, color=TEAL)
    ax.text(0.004, 3.18, "min p = 0.25", fontsize=6.6, color=BLUE)
    ax.set_yticks(y, labels, fontsize=7.0)
    ax.invert_yaxis()
    ax.set_xlim(-0.004, 0.085)
    ax.set_xlabel("False positive rate", fontsize=7.4)
    clean_axes(ax, grid_axis="x")

    s4 = read_csv("calibration/s4_results_summary.csv")
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

    s5 = read_csv("calibration/s5_results_summary.csv")
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


def make_event_study() -> None:
    d = read_csv("application/event_study_coefficients.csv")
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    pre = d[d["rel_week"] < -0.5]
    post = d[d["rel_week"] >= 0]
    ax.axvspan(-8.6, -0.5, color=LIGHT_GREY, alpha=0.9, zorder=0)
    ax.axvspan(-0.5, 8.6, color=LIGHT_BLUE, alpha=0.55, zorder=0)
    ax.axhline(0, color=INK, linewidth=0.7)
    ax.axvline(-0.5, color=INK, linestyle="--", linewidth=0.8)
    ax.fill_between(pre["rel_week"], pre["ci95_low"], pre["ci95_high"], color=BLUE, alpha=0.18)
    ax.fill_between(post["rel_week"], post["ci95_low"], post["ci95_high"], color=BLUE, alpha=0.22)
    ax.errorbar(pre["rel_week"], pre["coef"], yerr=1.96 * pre["std_error"], fmt="o", color=MUTED, markersize=5.2, capsize=2, zorder=3)
    ax.errorbar(post["rel_week"], post["coef"], yerr=1.96 * post["std_error"], fmt="s", color=BLUE, markersize=5.4, capsize=2, zorder=3)
    flagged = d[d["rel_week"].isin([-8, -3])]
    ax.scatter(flagged["rel_week"], flagged["coef"], s=86, facecolors="none", edgecolors=RED, linewidths=1.4, zorder=4)
    post_mean = float(post.loc[post["rel_week"] != -1, "coef"].mean())
    ax.axhline(post_mean, color=AMBER, linestyle="--", linewidth=1.0)
    ax.text(8.3, post_mean + 0.08, f"post mean +{post_mean:.3f}", color=AMBER, ha="right", fontsize=8.0)
    ax.text(-8.3, 2.45, "PRE-PERIOD", color=MUTED, fontsize=8.2, fontweight="bold")
    ax.text(0.2, 2.45, "POST-PERIOD", color=BLUE, fontsize=8.2, fontweight="bold")
    ax.annotate(
        "pre-trend warning\nweeks -8, -3 exclude zero",
        xy=(-3, float(d.loc[d["rel_week"] == -3, "coef"].iloc[0])),
        xytext=(-6.2, 2.05),
        color=RED,
        fontsize=7.4,
        arrowprops={"arrowstyle": "->", "color": RED, "lw": 0.8},
    )
    ax.set_xlim(-8.7, 8.7)
    ax.set_ylim(-1.35, 2.7)
    ax.set_xlabel("Weeks relative to PumpSwap launch (week -1 omitted)")
    ax.set_ylabel("Coefficient on log(1 + daily volume)")
    clean_axes(ax)
    save(fig, "fig_event_study_shilin")


def make_ladder() -> None:
    d = read_csv("application/deterministic_ladder.csv").set_index("rung")
    rungs = ["L0", "L1", "L2", "L3", "L6"]
    est = [float(d.loc[r, "estimate"]) for r in rungs]
    lo = [float(d.loc[r, "ci95_low"]) if d.loc[r, "ci95_low"] else np.nan for r in rungs]
    hi = [float(d.loc[r, "ci95_high"]) if d.loc[r, "ci95_high"] else np.nan for r in rungs]
    x = np.arange(len(rungs))
    fig, ax = plt.subplots(figsize=(6.6, 3.7))
    bands = [(-0.5, 0.5, LIGHT_BLUE), (0.5, 2.5, LIGHT_GREY), (2.5, 3.5, LIGHT_AMBER), (3.5, 4.5, LIGHT_GREY)]
    labels_top = ["BASELINE", "IDENTIFICATION", "DYNAMICS", "INFERENCE"]
    for (x0, x1, color), lab in zip(bands, labels_top):
        ax.axvspan(x0, x1, color=color, alpha=0.7, zorder=0)
        ax.text((x0 + x1) / 2, 1.42, lab, ha="center", fontsize=7.6, color=BLUE if lab != "DYNAMICS" else AMBER, fontweight="bold")
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.fill_between(x, lo, hi, color=BLUE, alpha=0.16)
    ax.plot(x, est, color=BLUE, linewidth=1.6, marker="o", markersize=6.5, zorder=3)
    ax.annotate(f"dashboard +{est[0]:.3f}", xy=(0, est[0]), xytext=(-0.15, 0.92), color=GREEN, fontsize=7.6)
    ax.annotate("controls cross zero", xy=(2, est[2]), xytext=(1.15, -0.35), color=MUTED, fontsize=7.4)
    ax.annotate(f"dynamic mean +{est[3]:.3f}", xy=(3, est[3]), xytext=(2.55, 1.18), color=AMBER, fontsize=7.5)
    ax.annotate(f"honest interval width = {hi[4]-lo[4]:.3f}", xy=(4, lo[4]), xytext=(2.7, -1.22), color=MUTED, fontsize=7.3)
    ax.set_xticks(x, ["L0\nBefore-after", "L1\n+ comparison", "L2\n+ two-way FE", "L3\nDynamic mean", "L6\nFew-cluster"])
    ax.set_ylabel("Estimate on log(1 + daily volume)")
    ax.set_ylim(-1.55, 1.55)
    ax.set_xlim(-0.55, 4.55)
    clean_axes(ax)
    ax.text(0.0, -1.48, "*L3 uses the dynamic post-event estimate; other rungs use the static market effect.", fontsize=7.0, color=MUTED)
    save(fig, "fig_ladder_decision_flip_shilin")


def make_metric_battery() -> None:
    rows = read_csv("application/result1_stakeholder_metric_battery.csv")
    timeout = 100 * (831290 / 832941)
    conc = 60.1
    risk = 52.4
    active = 5.7
    labels = ["Launch timeout", "Holder concentration", "Excess risk", "Active snapshot"]
    values = [timeout, conc, risk, active]
    colors = [RED, AMBER, AMBER, BLUE]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    y = np.arange(len(labels))[::-1]
    ax.hlines(y, 0, values, color=["#F4C7C3", "#F8E3B0", "#F3D0B0", LIGHT_BLUE], linewidth=10)
    ax.scatter(values, y, s=42, c=colors, zorder=3)
    ax.text(timeout + 1.2, y[0], "99.8%", color=RED, fontweight="bold")
    ax.text(timeout + 1.2, y[0] - 0.28, "831,290 / 832,941 launches", color=MUTED, fontsize=7.2)
    ax.text(conc + 1.5, y[1], "60.1%", color=AMBER, fontweight="bold")
    ax.text(risk + 1.5, y[2], "52.4 pp", color=AMBER, fontweight="bold")
    ax.text(active + 1.5, y[3], "5.7%", color=BLUE, fontweight="bold")
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 112)
    ax.set_xlabel("Observed rate or percentage-point contrast")
    clean_axes(ax, grid_axis="x")
    save(fig, "fig_metric_battery_status_shilin")


def make_frequency() -> None:
    d = read_csv("application/result1_frequency_sensitivity.csv").set_index("layer")
    daily = d.loc["market_daily_twfe"]
    weekly = d.loc["market_weekly_twfe"]
    fig, ax = plt.subplots(figsize=(6.3, 3.5))
    ax.bar(0, float(daily["estimate"]), color="#8AA0B8", width=0.55, zorder=2)
    shift = float(weekly["estimate"]) - float(daily["estimate"])
    ax.bar(1, shift, bottom=float(daily["estimate"]), color=AMBER, width=0.55, zorder=2)
    ax.bar(2, float(weekly["estimate"]), color=BLUE, width=0.55, zorder=2)
    ax.errorbar(0, float(daily["estimate"]), yerr=[[float(daily["estimate"]) - float(daily["ci95_low"])], [float(daily["ci95_high"]) - float(daily["estimate"])]], color=INK, capsize=3, linewidth=1.1)
    ax.errorbar(2, float(weekly["estimate"]), yerr=[[float(weekly["estimate"]) - float(weekly["ci95_low"])], [float(weekly["ci95_high"]) - float(weekly["estimate"])]], color=INK, capsize=3, linewidth=1.1)
    ax.axhline(0, color=INK, linewidth=0.7)
    ax.text(0, float(daily["estimate"]) * 0.45, f"+{float(daily['estimate']):.3f}", ha="center", color="white", fontweight="bold")
    ax.text(1, float(daily["estimate"]) + shift * 0.45, f"+{shift:.3f}", ha="center", color="white", fontweight="bold")
    ax.text(2, float(weekly["estimate"]) * 0.45, f"+{float(weekly['estimate']):.3f}", ha="center", color="white", fontweight="bold")
    ax.set_xticks([0, 1, 2], ["Daily estimate", "Aggregation shift", "Weekly estimate"])
    ax.set_ylabel("Effect on log(1 + volume)")
    ax.set_ylim(-0.18, 1.28)
    clean_axes(ax)
    save(fig, "fig_frequency_sensitivity_shilin")


def make_mechanism() -> None:
    h1 = load_json("application/h1_rpc_mechanism_summary.json")
    fig, ax = plt.subplots(figsize=(6.2, 2.8))
    labels = ["30-day observed\nactivity", "Complete-window\nactivity"]
    nums = [
        int(h1["full_30d_observed_active_tokens"]) / int(h1["post_30d_tokens"]),
        float(h1["complete_30d_active_share"]),
    ]
    counts = [
        f"{int(h1['full_30d_observed_active_tokens']):,} / {int(h1['post_30d_tokens']):,}",
        f"{int(h1['complete_30d_active_tokens']):,} / {int(h1['complete_30d_tokens']):,}",
    ]
    ax.barh([1, 0], nums, color=[TEAL, GREEN], height=0.45)
    for y, val, count in zip([1, 0], nums, counts):
        ax.text(val + 0.015, y, f"{100*val:.1f}%  ({count})", va="center", fontsize=8.2)
    ax.set_xlim(0, 1.35)
    ax.set_yticks([1, 0], labels)
    ax.set_xlabel("Share of graduated tokens")
    clean_axes(ax, grid_axis="x")
    save(fig, "fig_h1_mechanism_audit_shilin")


def make_agentic() -> None:
    d = read_csv("application/agentic_arm_scores.csv")
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    x = np.arange(len(d))
    gap = d["calibration_gap"].abs()
    omit = d["method_omission_rate"]
    ax.plot(x, gap, color=BLUE, marker="o", linewidth=1.7, label="Absolute calibration gap")
    ax.plot(x, omit, color=AMBER, marker="s", linewidth=1.7, label="Method omission rate")
    ax.set_xticks(x, d["rung"])
    ax.set_ylim(0, 0.9)
    ax.set_ylabel("Score")
    ax.legend(frameon=False, loc="upper right")
    clean_axes(ax)
    save(fig, "fig_agentic_scaffold_tradeoff_shilin")


def main() -> None:
    apply_style()
    make_teaser()
    make_coverage_map()
    make_stress_atlas()
    make_event_study()
    make_ladder()
    make_metric_battery()
    make_frequency()
    make_mechanism()
    make_agentic()


if __name__ == "__main__":
    main()
