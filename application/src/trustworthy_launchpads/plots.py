"""Paper-ready figures for the application-arm artifacts."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter, PercentFormatter

from .io import CaseConfig, read_market_panel, write_csv


plt.rcParams.update(
    {
        "font.size": 9.5,
        "axes.titlesize": 11,
        "axes.labelsize": 9.5,
        "legend.fontsize": 8.8,
        "figure.dpi": 160,
        "savefig.dpi": 300,
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "semibold",
        "axes.edgecolor": "#4B5563",
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "grid.color": "#E5E7EB",
        "grid.linewidth": 0.7,
        "grid.alpha": 0.85,
        "xtick.color": "#374151",
        "ytick.color": "#374151",
        "text.color": "#111827",
        "axes.labelcolor": "#111827",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)


PALETTE = {
    "navy": "#1F4E79",
    "teal": "#2A9D8F",
    "green": "#287D55",
    "amber": "#E9A93A",
    "orange": "#D97706",
    "red": "#B42318",
    "purple": "#6D597A",
    "slate": "#64748B",
    "gray": "#9CA3AF",
    "ink": "#111827",
    "grid": "#E5E7EB",
}

STATUS_COLORS = {
    "pass": PALETTE["green"],
    "warning": PALETTE["amber"],
    "gap": PALETTE["red"],
}

STATUS_SCORES = {
    "pass": 1.0,
    "warning": 0.5,
    "gap": 0.0,
}

AREA_LABELS = {
    "benchmark_ladder": "Benchmark\nladder",
    "parallel_trends": "Pre-trends",
    "few_cluster_inference": "Few-cluster\ninference",
    "decoded_indexer_outcomes": "Decoded token\noutcomes",
    "rpc_external_validation": "RPC validation",
    "h1_rpc_mechanism_validation": "H1 mechanism\nvalidation",
    "agentic_execution": "Agentic\nexecution",
    "claim_boundary": "Claim\nboundaries",
}

RADAR_DIMENSIONS = [
    "Effect\nmagnitude",
    "Estimate\nprecision",
    "Control /\nFE design",
    "Few-cluster\ncorrection",
    "Conservative\nconclusion",
    "Agent method\ncoverage",
    "Agent calibration\nquality",
]

OBSOLETE_FIGURES = [
    "fig_l0_window_sensitivity_line.png",
    "fig_agentic_evaluation_bars.png",
]


def _save_figure(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _read_table(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _wrap_label(value: object, width: int = 24) -> str:
    return "\n".join(textwrap.wrap(str(value), width=width, break_long_words=False))


def _clean_axis(ax: plt.Axes, *, axis: str = "y") -> None:
    ax.grid(True, axis=axis)
    ax.spines["left"].set_color("#9CA3AF")
    ax.spines["bottom"].set_color("#9CA3AF")
    ax.tick_params(length=3, width=0.7)


def _format_count(value: float, _pos: int | None = None) -> str:
    if abs(value) >= 1000:
        return f"{value / 1000:.1f}k"
    return f"{value:.0f}"


def _format_metric_value(metric: object, value: object) -> str:
    number = float(value)
    if "share" in str(metric).lower():
        return f"{number * 100:.1f}%"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    if number.is_integer():
        return f"{number:.0f}"
    return f"{number:.3g}"


def _decision_color(decision: object) -> str:
    text = str(decision)
    if text in {"yes", "passes_90pct_lower_bound_threshold", "passes_90pct_complete_window_threshold"}:
        return PALETTE["green"]
    if "computed" in text or "sample" in text:
        return PALETTE["teal"]
    if "gap" in text or "flag" in text:
        return PALETTE["red"] if "gap" in text else PALETTE["amber"]
    if "uncertain" in text or "depends" in text:
        return PALETTE["slate"]
    if "risk" in text or "proxy" in text:
        return PALETTE["purple"]
    return PALETTE["navy"]


def plot_event_study(event: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    event = event.sort_values("rel_week")
    ax.axhspan(-0.15, 0.15, color=PALETTE["grid"], alpha=0.45, zorder=0)
    ax.axhline(0, color=PALETTE["ink"], linewidth=0.9)
    ax.axvline(-0.5, color=PALETTE["ink"], linestyle="--", linewidth=0.9)

    segments = [
        ("Pre-event", event.loc[event["rel_week"].lt(-1)], PALETTE["slate"], "o"),
        ("Reference", event.loc[event["rel_week"].eq(-1)], PALETTE["gray"], "s"),
        ("Post-event", event.loc[event["rel_week"].ge(0)], PALETTE["teal"], "D"),
    ]
    for label, part, color, marker in segments:
        if part.empty:
            continue
        ax.errorbar(
            part["rel_week"],
            part["coef"],
            yerr=[part["coef"] - part["ci95_low"], part["ci95_high"] - part["coef"]],
            fmt=marker,
            label=label,
            color=color,
            ecolor=color,
            elinewidth=1.1,
            capsize=3,
            markersize=4.5,
            markeredgecolor="white",
            markeredgewidth=0.7,
            alpha=0.96,
        )

    pre = event.loc[event["rel_week"].lt(-1)].copy()
    significant_pre = pre.loc[(pre["ci95_low"].gt(0)) | (pre["ci95_high"].lt(0))]
    if len(significant_pre):
        ax.scatter(
            significant_pre["rel_week"],
            significant_pre["coef"],
            s=90,
            facecolors="none",
            edgecolors=PALETTE["red"],
            linewidth=1.2,
            zorder=4,
            label="Pre-trend flag",
        )
        ax.annotate(
            "pre-trend risk",
            xy=(float(significant_pre.iloc[0]["rel_week"]), float(significant_pre.iloc[0]["coef"])),
            xytext=(-7.8, 2.15),
            arrowprops={"arrowstyle": "->", "color": PALETTE["red"], "linewidth": 0.8},
            color=PALETTE["red"],
            fontsize=8.5,
        )

    ax.set_xlabel("Event week relative to PumpSwap launch; week -1 omitted")
    ax.set_ylabel("Effect on log(1 + daily volume)")
    ax.set_title("Event-Study Diagnostics: Dynamic Market-Level Effects")
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.16))
    _clean_axis(ax, axis="y")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_ladder(ladder: pd.DataFrame, path: Path) -> None:
    market = ladder.loc[ladder["outcome"].str.contains("volume|dynamic", case=False, na=False)].copy()
    market = market.loc[market["estimate"].notna()]
    market["rung_order"] = market["rung"].str.extract(r"L([0-9]+)").astype(int)
    market = market.sort_values("rung_order", ascending=False)
    fig, ax = plt.subplots(figsize=(8.8, 5.1))
    y = np.arange(len(market))
    x = market["estimate"].astype(float)
    low = market["ci95_low"].astype(float)
    high = market["ci95_high"].astype(float)
    colors = [_decision_color(value) for value in market["worked_decision"]]
    ax.axvspan(-1.4, 0, color=PALETTE["grid"], alpha=0.45, zorder=0)
    ax.axvline(0, color=PALETTE["ink"], linewidth=0.9)
    for idx, row in enumerate(market.itertuples(index=False)):
        ax.plot([float(row.ci95_low), float(row.ci95_high)], [idx, idx], color=colors[idx], linewidth=2.2)
        ax.scatter(float(row.estimate), idx, s=52, color=colors[idx], edgecolor="white", linewidth=0.8, zorder=3)
        ax.text(
            float(row.ci95_high) + 0.07,
            idx,
            str(row.worked_decision).replace("_", " "),
            va="center",
            ha="left",
            fontsize=8.3,
            color=colors[idx],
        )
    labels = [
        f"{row.rung}  {_wrap_label(row.component_added.replace('+ ', ''), 30)}"
        for row in market.itertuples(index=False)
    ]
    ax.set_yticks(y, labels)
    ax.set_xlabel("Estimate in log points")
    ax.set_title("Trustworthiness Ladder: Point Estimates and 95% Intervals")
    ax.set_xlim(min(float(low.min()) - 0.15, -1.5), max(float(high.max()) + 0.55, 1.55))
    _clean_axis(ax, axis="x")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_frequency_sensitivity(frequency: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(9.4, 4.4),
        gridspec_kw={"width_ratios": [1.15, 1.0]},
    )
    market = frequency.loc[frequency["layer"].str.contains("market", na=False)].copy()
    mechanism = frequency.loc[~frequency["layer"].str.contains("market", na=False)].copy()

    ax = axes[0]
    market = market.iloc[::-1].reset_index(drop=True)
    y = np.arange(len(market))
    ax.axvline(0, color=PALETTE["ink"], linewidth=0.9)
    for idx, row in enumerate(market.itertuples(index=False)):
        color = _decision_color(row.decision)
        if pd.notna(row.ci95_low) and pd.notna(row.ci95_high):
            ax.plot([row.ci95_low, row.ci95_high], [idx, idx], color=color, linewidth=2)
        ax.scatter(row.estimate, idx, s=54, color=color, edgecolor="white", linewidth=0.8, zorder=3)
        ax.text(row.estimate, idx + 0.18, f"{row.estimate:.2f}", ha="center", fontsize=8.2)
    ax.set_yticks(y, [_wrap_label(label.replace("_", " "), 22) for label in market["layer"]])
    ax.set_xlabel("Log-volume estimate")
    ax.set_title("A. Aggregation Choice")
    _clean_axis(ax, axis="x")

    ax = axes[1]
    mechanism = mechanism.reset_index(drop=True)
    y = np.arange(len(mechanism))
    values = pd.to_numeric(mechanism["estimate"], errors="coerce")
    bars = ax.barh(
        y,
        values.fillna(0),
        color=[_decision_color(value) for value in mechanism["decision"]],
        alpha=0.88,
        height=0.58,
    )
    for bar, row, value in zip(bars, mechanism.itertuples(index=False), values):
        label = "registered gap" if pd.isna(value) else (f"{value:.1f}" if abs(float(value)) >= 10 else f"{value:.3f}")
        ax.text(
            max(float(value) if pd.notna(value) else 0, 0) + max(float(values.max(skipna=True) or 1) * 0.03, 0.05),
            bar.get_y() + bar.get_height() / 2,
            label,
            va="center",
            fontsize=8.2,
            color=PALETTE["ink"],
        )
    ax.set_yticks(y, [_wrap_label(label.replace("_", " "), 22) for label in mechanism["layer"]])
    ax.set_xlabel("Native metric scale")
    ax.set_title("B. Data-Richness Layer")
    ax.xaxis.set_major_formatter(FuncFormatter(_format_count))
    _clean_axis(ax, axis="x")
    fig.suptitle("Frequency and Data-Richness Sensitivity", y=1.02)
    fig.tight_layout()
    _save_figure(fig, path)


def plot_metric_status(battery: pd.DataFrame, path: Path) -> None:
    data = battery.copy()
    data["dimension_short"] = data["dimension"].astype(str).str.replace(" / ", "\n", regex=False)
    stakeholders = sorted(data["stakeholder"].astype(str).unique())
    dimensions = sorted(data["dimension_short"].astype(str).unique())
    status_palette = {
        "computed": PALETTE["green"],
        "computed_proxy": PALETTE["amber"],
        "computed_extension": PALETTE["navy"],
        "computed_external_validation_sample": PALETTE["teal"],
        "registered_external_validation": PALETTE["purple"],
    }
    status_offsets = {
        "computed": -0.12,
        "computed_proxy": -0.06,
        "computed_extension": 0.0,
        "computed_external_validation_sample": 0.06,
        "registered_external_validation": 0.12,
    }
    fig, ax = plt.subplots(figsize=(8.6, 6.2))
    grouped = (
        data.groupby(["stakeholder", "dimension_short", "status"], as_index=False)
        .size()
        .rename(columns={"size": "metric_count"})
    )
    for _, row in grouped.iterrows():
        status = str(row["status"])
        x = stakeholders.index(str(row["stakeholder"])) + status_offsets.get(status, 0.0)
        y = dimensions.index(str(row["dimension_short"]))
        ax.scatter(
            x,
            y,
            s=130 + 55 * float(row["metric_count"]),
            color=status_palette.get(status, PALETTE["gray"]),
            edgecolor="white",
            linewidth=0.9,
            alpha=0.93,
            zorder=3,
        )
    ax.set_xticks(np.arange(len(stakeholders)), [_wrap_label(label, 16) for label in stakeholders], rotation=20, ha="right")
    ax.set_yticks(np.arange(len(dimensions)), [_wrap_label(label, 22) for label in dimensions])
    ax.set_xlim(-0.6, len(stakeholders) - 0.4)
    ax.set_ylim(-0.6, len(dimensions) - 0.4)
    ax.invert_yaxis()
    ax.set_title("Stakeholder Metric Battery: Coverage by Dimension and Evidence Status")
    ax.grid(True, which="major", axis="both")
    handles = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=color,
            markeredgecolor="white",
            markersize=8,
            label=status.replace("_", " "),
        )
        for status, color in status_palette.items()
        if status in set(data["status"].astype(str))
    ]
    ax.legend(handles=handles, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
    fig.tight_layout()
    _save_figure(fig, path)


def plot_external_validation_rpc(config: CaseConfig, path: Path) -> None:
    source = config.output_root / "external_validation" / "solana_post_migration_pool_windows.csv"
    if not source.exists():
        return
    post = pd.read_csv(source)
    if not len(post):
        return
    complete = (
        post.loc[post["signature_window_status"].astype(str).eq("ok")].copy()
        if "signature_window_status" in post
        else post.copy()
    )
    plot_data = complete if len(complete) else post
    summary = (
        plot_data.groupby("horizon_days", as_index=False)
        .agg(
            active_share=("swap_count", lambda value: float(pd.Series(value).gt(0).mean())),
            median_swaps=("swap_count", "median"),
            p25_swaps=("swap_count", lambda value: float(pd.Series(value).quantile(0.25))),
            p75_swaps=("swap_count", lambda value: float(pd.Series(value).quantile(0.75))),
            tokens=("mint", "nunique"),
        )
        .sort_values("horizon_days")
    )
    post30 = post.loc[post["horizon_days"].eq(30)].copy()
    complete30 = plot_data.loc[plot_data["horizon_days"].eq(30)].copy()
    status_counts = (
        post30["signature_window_status"].astype(str).value_counts()
        if "signature_window_status" in post30
        else pd.Series({"observed": len(post30)})
    )

    fig, axes = plt.subplots(2, 2, figsize=(10.0, 7.0))
    labels = summary["horizon_days"].astype(int).astype(str)
    x = np.arange(len(summary))

    ax = axes[0, 0]
    ax.plot(x, summary["active_share"], color=PALETTE["teal"], marker="o", linewidth=2.2)
    ax.fill_between(x, 0, summary["active_share"], color=PALETTE["teal"], alpha=0.10)
    for xi, value in zip(x, summary["active_share"]):
        ax.text(xi, min(float(value) + 0.025, 0.98), f"{value * 100:.0f}%", ha="center", fontsize=8.4)
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Days after migration")
    ax.set_ylabel("Active share")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("A. Complete-Window Activity")
    _clean_axis(ax, axis="y")

    ax = axes[0, 1]
    yerr = [
        summary["median_swaps"] - summary["p25_swaps"],
        summary["p75_swaps"] - summary["median_swaps"],
    ]
    ax.errorbar(
        x,
        summary["median_swaps"],
        yerr=yerr,
        fmt="o-",
        color=PALETTE["navy"],
        ecolor=PALETTE["slate"],
        capsize=3,
        linewidth=2.0,
    )
    ax.set_xticks(x, labels)
    ax.set_xlabel("Days after migration")
    ax.set_ylabel("Transaction-count proxy")
    ax.yaxis.set_major_formatter(FuncFormatter(_format_count))
    ax.set_title("B. Median Persistence Proxy")
    _clean_axis(ax, axis="y")

    ax = axes[1, 0]
    counts = pd.to_numeric(complete30["swap_count"], errors="coerce").dropna()
    if len(counts):
        ax.hist(np.log1p(counts), bins=28, color=PALETTE["purple"], alpha=0.86, edgecolor="white", linewidth=0.5)
        median = float(np.log1p(counts.median()))
        ax.axvline(median, color=PALETTE["ink"], linestyle="--", linewidth=1.0)
        ax.text(median + 0.08, ax.get_ylim()[1] * 0.88, "median", fontsize=8.4)
    ax.set_xlabel("log(1 + 30d transaction-count proxy)")
    ax.set_ylabel("Complete-window tokens")
    ax.set_title("C. Token-Level Distribution")
    _clean_axis(ax, axis="y")

    ax = axes[1, 1]
    status_labels = [
        "complete" if label == "ok" else "truncated"
        for label in status_counts.index.astype(str)
    ]
    status_colors = [PALETTE["green"] if label == "complete" else PALETTE["amber"] for label in status_labels]
    wedges, texts = ax.pie(
        status_counts.to_numpy(),
        labels=status_labels,
        colors=status_colors,
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.0},
        textprops={"fontsize": 8.5},
    )
    ax.text(0, 0, f"{int(post30['mint'].nunique())}\ntokens", ha="center", va="center", fontsize=10, weight="semibold")
    ax.set_title("D. 30d Window Coverage")

    summary_path = config.tables_dir / "external_validation_summary.json"
    if summary_path.exists():
        import json

        validation = json.loads(summary_path.read_text(encoding="utf-8"))
        title = (
            "Public Solana RPC External Validation: Complete Post-Migration Windows"
            if validation.get("credible_sample_status") == "credible_complete_rpc_post_migration_sample"
            else "Public Solana RPC External Validation: Lower-Bound Post-Migration Activity"
        )
    else:
        title = "Public Solana RPC External Validation: Post-Migration Activity"
    fig.suptitle(title, y=1.01)
    fig.tight_layout()
    _save_figure(fig, path)


def plot_parallel_trends(config: CaseConfig, path: Path) -> None:
    panel = read_market_panel(config)
    collapsed = panel.copy()
    collapsed["group"] = np.where(collapsed["treated"].eq(1), "Pump ecosystem", "Solana DEX controls")
    collapsed = (
        collapsed.groupby(["date", "group"], as_index=False)
        .agg(log_volume=("log_volume", "mean"))
        .sort_values("date")
    )
    wide = collapsed.pivot(index="date", columns="group", values="log_volume").sort_index()
    if {"Pump ecosystem", "Solana DEX controls"}.issubset(wide.columns):
        wide["gap"] = wide["Pump ecosystem"] - wide["Solana DEX controls"]
    fig, axes = plt.subplots(2, 1, figsize=(8.8, 6.2), sharex=True, gridspec_kw={"height_ratios": [2.2, 1.0]})
    ax = axes[0]
    colors = {"Pump ecosystem": PALETTE["teal"], "Solana DEX controls": PALETTE["navy"]}
    for group, group_df in collapsed.groupby("group"):
        ax.plot(group_df["date"], group_df["log_volume"], label=group, linewidth=2.0, color=colors.get(group, PALETTE["slate"]))
    event_date = pd.Timestamp(config.raw["event_date"], tz="UTC")
    ax.axvline(event_date, color=PALETTE["ink"], linestyle="--", linewidth=0.9)
    ax.set_ylabel("log(1 + daily volume)")
    ax.set_title("Parallel-Trends Screen: Pump Ecosystem vs Solana DEX Controls")
    ax.legend(frameon=False, loc="upper left")
    _clean_axis(ax, axis="y")

    ax = axes[1]
    if "gap" in wide:
        ax.plot(wide.index, wide["gap"], color=PALETTE["purple"], linewidth=1.6)
        ax.fill_between(wide.index, 0, wide["gap"], color=PALETTE["purple"], alpha=0.12)
    ax.axhline(0, color=PALETTE["ink"], linewidth=0.8)
    ax.axvline(event_date, color=PALETTE["ink"], linestyle="--", linewidth=0.9)
    ax.set_ylabel("Treated-control gap")
    ax.set_xlabel("Date")
    _clean_axis(ax, axis="y")
    fig.autofmt_xdate()
    fig.tight_layout()
    _save_figure(fig, path)


def plot_market_protocol_volume_lines(config: CaseConfig, path: Path) -> None:
    panel = read_market_panel(config)
    weekly = (
        panel.groupby(["calendar_week", "unit"], as_index=False)
        .agg(week_start=("date", "min"), mean_log_volume=("log_volume", "mean"))
        .sort_values(["unit", "week_start"])
    )
    if weekly.empty:
        return

    labels = {
        "pump_ecosystem": "Pump ecosystem",
        "raydium": "Raydium",
        "orca": "Orca",
        "meteora_combined": "Meteora",
    }
    colors = {
        "pump_ecosystem": PALETTE["teal"],
        "raydium": PALETTE["navy"],
        "orca": PALETTE["orange"],
        "meteora_combined": PALETTE["purple"],
    }
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    for unit, unit_df in weekly.groupby("unit", sort=False):
        is_treated = unit == "pump_ecosystem"
        ax.plot(
            unit_df["week_start"],
            unit_df["mean_log_volume"],
            label=labels.get(unit, str(unit)),
            color=colors.get(unit, "#4B5563"),
            linewidth=2.5 if is_treated else 1.55,
            alpha=1.0 if is_treated else 0.78,
        )
    event_date = pd.Timestamp(config.raw["event_date"], tz="UTC")
    ax.axvline(event_date, color=PALETTE["ink"], linestyle="--", linewidth=0.9, label="PumpSwap launch")
    ax.set_xlabel("Week")
    ax.set_ylabel("Weekly mean log(1 + daily volume)")
    ax.set_title("Protocol-Level Market Activity Trajectories")
    ax.legend(frameon=False, ncol=2)
    _clean_axis(ax, axis="y")
    fig.autofmt_xdate()
    fig.tight_layout()
    _save_figure(fig, path)


def _build_radar_profiles(config: CaseConfig, ladder: pd.DataFrame) -> pd.DataFrame:
    selected_rungs = ["L0", "L2", "L6"]
    selected = ladder.loc[ladder["rung"].astype(str).isin(selected_rungs)].copy()
    selected["rung_order"] = selected["rung"].map({rung: idx for idx, rung in enumerate(selected_rungs)})
    selected = selected.sort_values("rung_order")
    agent_scores = _read_table(config.tables_dir / "agentic_arm_scores.csv")
    if selected.empty:
        return pd.DataFrame()

    selected["estimate_abs"] = pd.to_numeric(selected["estimate"], errors="coerce").abs()
    selected["ci_width"] = pd.to_numeric(selected["ci95_high"], errors="coerce") - pd.to_numeric(selected["ci95_low"], errors="coerce")
    max_effect = float(selected["estimate_abs"].max() or 1.0)
    min_width = float(selected.loc[selected["ci_width"].gt(0), "ci_width"].min() or 1.0)

    rows: list[dict[str, object]] = []
    profile_labels = {
        "L0": "L0 naive before-after",
        "L2": "L2 TWFE DiD",
        "L6": "L6 wild-cluster DiD",
    }
    for _, row in selected.iterrows():
        rung = str(row["rung"])
        agent = agent_scores.loc[agent_scores["rung"].astype(str).eq(rung)] if not agent_scores.empty else pd.DataFrame()
        method_omission = float(agent.iloc[0]["method_omission_rate"]) if len(agent) else np.nan
        calibration_gap = float(agent.iloc[0]["calibration_gap"]) if len(agent) else np.nan
        effect = float(row["estimate_abs"]) if pd.notna(row["estimate_abs"]) else 0.0
        ci_width = float(row["ci_width"]) if pd.notna(row["ci_width"]) and float(row["ci_width"]) > 0 else np.nan
        scores = [
            ("Effect\nmagnitude", effect / max_effect if max_effect else 0.0, f"|estimate|={effect:.4f} log points"),
            ("Estimate\nprecision", min_width / ci_width if pd.notna(ci_width) and ci_width > 0 else 0.0, f"CI width={ci_width:.4f}" if pd.notna(ci_width) else "CI width unavailable"),
            ("Control /\nFE design", 1.0 if rung in {"L2", "L6"} else 0.0, str(row.get("method", ""))),
            ("Few-cluster\ncorrection", 1.0 if rung == "L6" else 0.0, str(row.get("method", ""))),
            (
                "Conservative\nconclusion",
                0.0 if str(row.get("worked_decision", "")) == "yes" else 1.0,
                f"worked_decision={row.get('worked_decision', '')}",
            ),
            (
                "Agent method\ncoverage",
                1.0 - method_omission if pd.notna(method_omission) else 0.0,
                f"method_omission_rate={method_omission:.3f}" if pd.notna(method_omission) else "agent score unavailable",
            ),
            (
                "Agent calibration\nquality",
                max(0.0, 1.0 - abs(calibration_gap)) if pd.notna(calibration_gap) else 0.0,
                f"calibration_gap={calibration_gap:.3f}" if pd.notna(calibration_gap) else "agent score unavailable",
            ),
        ]
        for dimension, score, basis in scores:
            rows.append(
                {
                    "profile": profile_labels.get(rung, rung),
                    "rung": rung,
                    "dimension": dimension.replace("\n", " "),
                    "score": float(np.clip(score, 0.0, 1.0)),
                    "evidence_basis": basis,
                }
            )
    profile_df = pd.DataFrame(rows)
    write_csv(config.tables_dir / "radar_evidence_profiles.csv", profile_df)
    return profile_df


def plot_readiness_radar(config: CaseConfig, path: Path) -> None:
    ladder = _read_table(config.tables_dir / "deterministic_ladder.csv")
    if ladder.empty:
        return
    profiles = _build_radar_profiles(config, ladder)
    if profiles.empty:
        return
    labels = RADAR_DIMENSIONS
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False)
    closed_angles = np.concatenate([angles, [angles[0]]])

    fig, ax = plt.subplots(figsize=(6.6, 6.6), subplot_kw={"projection": "polar"})
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    style = {
        "L0 naive before-after": {"color": "#B45309", "linestyle": ":", "alpha": 0.12},
        "L2 TWFE DiD": {"color": "#1D4ED8", "linestyle": "-", "alpha": 0.15},
        "L6 wild-cluster DiD": {"color": "#287D55", "linestyle": "--", "alpha": 0.11},
    }
    for profile, profile_df in profiles.groupby("profile", sort=False):
        values = profile_df["score"].astype(float).to_numpy()
        closed_values = np.concatenate([values, [values[0]]])
        spec = style.get(profile, {"color": "#4B5563", "linestyle": "-", "alpha": 0.1})
        ax.plot(
            closed_angles,
            closed_values,
            color=spec["color"],
            linestyle=spec["linestyle"],
            linewidth=2.0,
            label=profile,
        )
        ax.fill(closed_angles, closed_values, color=spec["color"], alpha=float(spec["alpha"]))
        ax.scatter(angles, values, color=spec["color"], s=28, zorder=3, edgecolor="white", linewidth=0.7)
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.0, 0.5, 1.0])
    ax.set_yticklabels(["0", "0.5", "1"], fontsize=8)
    ax.grid(color="#CBD5E1", alpha=0.7)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.2), ncol=1, frameon=False)
    ax.set_title("Actual Pipeline-Rung Radar: L0, L2, and L6", pad=20)
    _save_figure(fig, path)


def plot_readiness_status_bar(config: CaseConfig, path: Path) -> None:
    audit = _read_table(config.tables_dir / "paper_readiness_audit.csv")
    if audit.empty:
        return
    audit = audit.assign(
        label=lambda df: df["area"].map(AREA_LABELS).fillna(df["area"]).str.replace("\n", " ", regex=False),
        score=lambda df: df["status"].map(STATUS_SCORES).fillna(0.0).astype(float),
    )

    fig, ax = plt.subplots(figsize=(9.4, 4.4))
    x = np.arange(len(audit))
    colors = audit["status"].map(STATUS_COLORS).fillna(PALETTE["gray"])
    ax.bar(x, np.ones(len(audit)), color=colors, alpha=0.92, width=0.72)
    ax.set_ylim(0, 1.25)
    ax.set_xticks(x, [_wrap_label(label, 14) for label in audit["label"]], rotation=0)
    ax.set_yticks([])
    ax.set_title("Readiness Audit: Pass, Warning, and Gap Components")
    ax.grid(False)
    for idx, row in enumerate(audit.itertuples(index=False)):
        ax.text(
            idx,
            0.50,
            str(row.status).upper(),
            ha="center",
            va="center",
            fontsize=8.4,
            color="white" if row.status in {"pass", "gap"} else PALETTE["ink"],
            weight="semibold",
        )
        ax.text(idx, 1.07, f"{float(row.score):.1f}", ha="center", va="bottom", fontsize=8.0, color=PALETTE["slate"])
    handles = [
        plt.Line2D([0], [0], marker="s", color="none", markerfacecolor=color, markersize=8, label=status)
        for status, color in STATUS_COLORS.items()
    ]
    ax.legend(handles=handles, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=3)
    fig.tight_layout()
    _save_figure(fig, path)


def _ordered_agent_scores(config: CaseConfig) -> pd.DataFrame:
    scores = _read_table(config.tables_dir / "agentic_arm_scores.csv")
    if scores.empty:
        return pd.DataFrame()
    return scores.assign(rung_order=scores["rung"].str.extract(r"L([0-9]+)").astype(float)).sort_values("rung_order")


def plot_agentic_method_omission_bar(config: CaseConfig, path: Path) -> None:
    scores = _ordered_agent_scores(config)
    if scores.empty:
        return
    x = np.arange(len(scores))
    labels = scores["rung"].tolist()

    fig, ax = plt.subplots(figsize=(7.8, 4.3))
    y = scores["method_omission_rate"].astype(float)
    ax.plot(x, y, color=PALETTE["orange"], linewidth=1.8)
    ax.scatter(x, y, color=PALETTE["orange"], s=58, edgecolor="white", linewidth=0.8, zorder=3)
    ax.fill_between(x, 0, y, color=PALETTE["orange"], alpha=0.10)
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Trustworthiness ladder rung")
    ax.set_ylabel("Method omission rate")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("Agentic Execution: Method Omissions by Rung")
    _clean_axis(ax, axis="y")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_agentic_calibration_gap_bar(config: CaseConfig, path: Path) -> None:
    scores = _ordered_agent_scores(config)
    if scores.empty:
        return
    x = np.arange(len(scores))
    labels = scores["rung"].tolist()

    fig, ax = plt.subplots(figsize=(7.8, 4.3))
    calibration = scores["calibration_gap"].astype(float)
    colors = [PALETTE["red"] if value < 0 else PALETTE["green"] for value in calibration]
    ax.axhline(0, color=PALETTE["ink"], linewidth=0.9)
    ax.vlines(x, 0, calibration, color=colors, linewidth=2.2)
    ax.scatter(x, calibration, color=colors, s=58, edgecolor="white", linewidth=0.8, zorder=3)
    ax.set_xticks(x, labels)
    max_abs = max(float(calibration.abs().max()), 0.1)
    ax.set_ylim(-max_abs * 1.18, max_abs * 0.22)
    ax.set_xlabel("Trustworthiness ladder rung")
    ax.set_ylabel("Calibration gap")
    ax.set_title("Agentic Execution: Overconfidence Gap by Rung")
    _clean_axis(ax, axis="y")
    fig.tight_layout()
    _save_figure(fig, path)


def _rpc_validation_data(config: CaseConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame]:
    source = config.output_root / "external_validation" / "solana_post_migration_pool_windows.csv"
    post = _read_table(source)
    if post.empty:
        return post, post, pd.DataFrame(), pd.Series(dtype=float), pd.DataFrame()
    complete = (
        post.loc[post["signature_window_status"].astype(str).eq("ok")].copy()
        if "signature_window_status" in post
        else post.copy()
    )
    plot_data = complete if len(complete) else post
    summary = (
        plot_data.groupby("horizon_days", as_index=False)
        .agg(
            active_share=("swap_count", lambda value: float(pd.Series(value).gt(0).mean())),
            median_swaps=("swap_count", "median"),
            p25_swaps=("swap_count", lambda value: float(pd.Series(value).quantile(0.25))),
            p75_swaps=("swap_count", lambda value: float(pd.Series(value).quantile(0.75))),
            tokens=("mint", "nunique"),
        )
        .sort_values("horizon_days")
    )
    post30 = post.loc[post["horizon_days"].eq(30)].copy()
    complete30 = plot_data.loc[plot_data["horizon_days"].eq(30)].copy()
    status_counts = (
        post30["signature_window_status"].astype(str).value_counts()
        if "signature_window_status" in post30
        else pd.Series({"observed": len(post30)})
    )
    return post, plot_data, summary, status_counts, complete30


def plot_rpc_active_share_single(config: CaseConfig, path: Path) -> None:
    _, _, summary, _, _ = _rpc_validation_data(config)
    if summary.empty:
        return
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    x = np.arange(len(summary))
    labels = summary["horizon_days"].astype(int).astype(str)
    ax.plot(x, summary["active_share"], color=PALETTE["teal"], marker="o", linewidth=2.2)
    ax.fill_between(x, 0, summary["active_share"], color=PALETTE["teal"], alpha=0.10)
    for xi, value in zip(x, summary["active_share"]):
        ax.text(xi, min(float(value) + 0.025, 0.98), f"{value * 100:.0f}%", ha="center", fontsize=8.4)
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Days after migration")
    ax.set_ylabel("Active share")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("Complete-Window Post-Migration Activity")
    _clean_axis(ax, axis="y")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_rpc_median_persistence_single(config: CaseConfig, path: Path) -> None:
    _, _, summary, _, _ = _rpc_validation_data(config)
    if summary.empty:
        return
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    x = np.arange(len(summary))
    labels = summary["horizon_days"].astype(int).astype(str)
    yerr = [
        summary["median_swaps"] - summary["p25_swaps"],
        summary["p75_swaps"] - summary["median_swaps"],
    ]
    ax.errorbar(
        x,
        summary["median_swaps"],
        yerr=yerr,
        fmt="o-",
        color=PALETTE["navy"],
        ecolor=PALETTE["slate"],
        capsize=3,
        linewidth=2.0,
    )
    ax.set_xticks(x, labels)
    ax.set_xlabel("Days after migration")
    ax.set_ylabel("Transaction-count proxy")
    ax.yaxis.set_major_formatter(FuncFormatter(_format_count))
    ax.set_title("Median Post-Migration Persistence Proxy")
    _clean_axis(ax, axis="y")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_rpc_token_distribution_single(config: CaseConfig, path: Path) -> None:
    _, _, _, _, complete30 = _rpc_validation_data(config)
    if complete30.empty:
        return
    counts = pd.to_numeric(complete30["swap_count"], errors="coerce").dropna()
    if counts.empty:
        return
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    ax.hist(np.log1p(counts), bins=28, color=PALETTE["purple"], alpha=0.86, edgecolor="white", linewidth=0.5)
    median = float(np.log1p(counts.median()))
    ax.axvline(median, color=PALETTE["ink"], linestyle="--", linewidth=1.0)
    ax.text(median + 0.08, ax.get_ylim()[1] * 0.88, "median", fontsize=8.4)
    ax.set_xlabel("log(1 + 30d transaction-count proxy)")
    ax.set_ylabel("Complete-window tokens")
    ax.set_title("Token-Level 30d Activity Distribution")
    _clean_axis(ax, axis="y")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_rpc_window_coverage_single(config: CaseConfig, path: Path) -> None:
    post, _, _, status_counts, _ = _rpc_validation_data(config)
    if post.empty or status_counts.empty:
        return
    post30 = post.loc[post["horizon_days"].eq(30)].copy()
    fig, ax = plt.subplots(figsize=(5.3, 4.4))
    status_labels = ["complete" if label == "ok" else "truncated" for label in status_counts.index.astype(str)]
    status_colors = [PALETTE["green"] if label == "complete" else PALETTE["amber"] for label in status_labels]
    ax.pie(
        status_counts.to_numpy(),
        labels=status_labels,
        colors=status_colors,
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.0},
        textprops={"fontsize": 8.8},
    )
    ax.text(0, 0, f"{int(post30['mint'].nunique())}\ntokens", ha="center", va="center", fontsize=10, weight="semibold")
    ax.set_title("30d RPC Window Coverage")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_frequency_market_single(frequency: pd.DataFrame, path: Path) -> None:
    market = frequency.loc[frequency["layer"].str.contains("market", na=False)].copy()
    if market.empty:
        return
    market = market.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    y = np.arange(len(market))
    ax.axvline(0, color=PALETTE["ink"], linewidth=0.9)
    for idx, row in enumerate(market.itertuples(index=False)):
        color = _decision_color(row.decision)
        if pd.notna(row.ci95_low) and pd.notna(row.ci95_high):
            ax.plot([row.ci95_low, row.ci95_high], [idx, idx], color=color, linewidth=2)
        ax.scatter(row.estimate, idx, s=54, color=color, edgecolor="white", linewidth=0.8, zorder=3)
        ax.text(row.estimate, idx + 0.18, f"{row.estimate:.2f}", ha="center", fontsize=8.2)
    ax.set_yticks(y, [_wrap_label(label.replace("_", " "), 22) for label in market["layer"]])
    ax.set_xlabel("Log-volume estimate")
    ax.set_title("Market-Level Frequency Sensitivity")
    _clean_axis(ax, axis="x")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_frequency_data_richness_single(frequency: pd.DataFrame, path: Path) -> None:
    mechanism = frequency.loc[~frequency["layer"].str.contains("market", na=False)].copy()
    if mechanism.empty:
        return
    mechanism = mechanism.reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(6.8, 4.3))
    y = np.arange(len(mechanism))
    values = pd.to_numeric(mechanism["estimate"], errors="coerce")
    bars = ax.barh(
        y,
        values.fillna(0),
        color=[_decision_color(value) for value in mechanism["decision"]],
        alpha=0.88,
        height=0.58,
    )
    max_value = float(values.max(skipna=True) or 1)
    for bar, row, value in zip(bars, mechanism.itertuples(index=False), values):
        label = "registered gap" if pd.isna(value) else (f"{value:.1f}" if abs(float(value)) >= 10 else f"{value:.3f}")
        ax.text(
            max(float(value) if pd.notna(value) else 0, 0) + max(max_value * 0.03, 0.05),
            bar.get_y() + bar.get_height() / 2,
            label,
            va="center",
            fontsize=8.2,
            color=PALETTE["ink"],
        )
    ax.set_yticks(y, [_wrap_label(label.replace("_", " "), 22) for label in mechanism["layer"]])
    ax.set_xlabel("Native metric scale")
    ax.set_title("Token and Mechanism Data-Richness Layer")
    ax.xaxis.set_major_formatter(FuncFormatter(_format_count))
    _clean_axis(ax, axis="x")
    fig.tight_layout()
    _save_figure(fig, path)


def _h1_audit_table(config: CaseConfig) -> pd.DataFrame:
    return _read_table(config.tables_dir / "h1_rpc_mechanism_causal_audit.csv")


def plot_h1_activity_placebo_single(config: CaseConfig, path: Path) -> None:
    audit = _h1_audit_table(config)
    if audit.empty:
        return
    share_rows = audit.loc[
        audit["claim_id"].isin(
            [
                "H1-rpc-full-observed-lower-bound-activity",
                "H1-rpc-complete-window-activity",
                "H1-rpc-temporal-placebo-violation-rate",
            ]
        )
    ].copy()
    if share_rows.empty:
        return
    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    labels = ["All-token lower bound", "Complete windows", "Temporal violations"]
    y = np.arange(len(share_rows))
    for idx, row in enumerate(share_rows.itertuples(index=False)):
        color = _decision_color(row.decision)
        ax.plot([row.ci95_low, row.ci95_high], [idx, idx], color=color, linewidth=2.4)
        ax.scatter(row.estimate, idx, color=color, s=58, edgecolor="white", linewidth=0.8, zorder=3)
        label_x = min(max(float(row.estimate), 0.055), 0.945)
        label_y = idx + (0.18 if float(row.estimate) > 0.02 else -0.22)
        ax.text(label_x, label_y, f"{row.estimate * 100:.2f}%", ha="center", fontsize=8.2)
    ax.axvline(0.90, color=PALETTE["slate"], linestyle="--", linewidth=0.8)
    ax.set_yticks(y, labels)
    ax.set_xlim(-0.03, 1.03)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("H1 Activity and Temporal Placebo Shares")
    ax.set_xlabel("Share with 95% interval")
    _clean_axis(ax, axis="x")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_h1_persistence_intensity_single(config: CaseConfig, path: Path) -> None:
    audit = _h1_audit_table(config)
    row_df = audit.loc[audit["claim_id"].eq("H1-rpc-complete-window-transaction-median")]
    if row_df.empty:
        return
    row = row_df.iloc[0]
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.barh([0], [float(row["estimate"])], color=PALETTE["navy"], alpha=0.88, height=0.45)
    ax.errorbar(
        [float(row["estimate"])],
        [0],
        xerr=[
            [float(row["estimate"]) - float(row["ci95_low"])],
            [float(row["ci95_high"]) - float(row["estimate"])],
        ],
        fmt="none",
        ecolor=PALETTE["ink"],
        capsize=3,
        linewidth=1.1,
    )
    ax.text(float(row["estimate"]) + 40, 0, f"{float(row['estimate']):.0f}", va="center", fontsize=9)
    ax.set_yticks([0], ["Complete 30d windows"])
    ax.set_xlabel("Median transaction-count proxy")
    ax.xaxis.set_major_formatter(FuncFormatter(_format_count))
    ax.set_title("H1 Complete-Window Persistence Intensity")
    _clean_axis(ax, axis="x")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_h1_temporal_ordering_single(config: CaseConfig, path: Path) -> None:
    audit = _h1_audit_table(config)
    row_df = audit.loc[audit["claim_id"].eq("H1-rpc-first-trade-timing")]
    if row_df.empty:
        return
    row = row_df.iloc[0]
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.errorbar(
        [float(row["estimate"])],
        [0],
        xerr=[
            [float(row["estimate"]) - float(row["ci95_low"])],
            [float(row["ci95_high"]) - float(row["estimate"])],
        ],
        fmt="o",
        color=PALETTE["teal"],
        ecolor=PALETTE["teal"],
        capsize=3,
        markersize=6,
        markeredgecolor="white",
        markeredgewidth=0.8,
    )
    ax.text(float(row["estimate"]) + 0.04, 0.10, f"{float(row['estimate']):.3f}s", fontsize=9)
    ax.axvline(0, color=PALETTE["ink"], linewidth=0.8)
    ax.set_yticks([0], ["First pool transaction"])
    ax.set_xlabel("Seconds after graduation")
    ax.set_title("H1 Temporal Ordering Check")
    _clean_axis(ax, axis="x")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_h1_claim_boundary_single(config: CaseConfig, path: Path) -> None:
    audit = _h1_audit_table(config)
    if audit.empty:
        return
    status_rows = audit.loc[
        audit["claim_id"].isin(
            [
                "H1-rpc-complete-window-activity",
                "H1-decoded-usd-trade-outcomes",
                "H4-early-wallet-event-time-outcomes",
            ]
        )
    ].copy()
    if status_rows.empty:
        return
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    status_labels = ["H1 mechanism", "Decoded USD trades", "H4 early wallets"]
    y = np.arange(len(status_rows))
    status_colors = [_decision_color(value) for value in status_rows["decision"]]
    ax.barh(y, np.ones(len(status_rows)), color=status_colors, alpha=0.92, height=0.55)
    for idx, row in enumerate(status_rows.itertuples(index=False)):
        display_decision = "pass" if str(row.decision).startswith("passes_") else str(row.decision).replace("_", " ")
        ax.text(
            0.5,
            idx,
            display_decision,
            ha="center",
            va="center",
            fontsize=8.8,
            color="white" if "gap" in str(row.decision) else PALETTE["ink"],
        )
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_yticks(y, status_labels)
    ax.set_title("H1/H4 Claim Boundary")
    ax.grid(False)
    fig.tight_layout()
    _save_figure(fig, path)


def _token_activity_data(config: CaseConfig) -> pd.DataFrame:
    source = config.output_root / "external_validation" / "h1_rpc_token_level_outcomes.csv"
    tokens = _read_table(source)
    if tokens.empty or "swap_count_30d" not in tokens:
        return pd.DataFrame()
    data = tokens.copy()
    data["graduated_at"] = pd.to_datetime(
        data.get("graduated_at_30d", data.get("graduated_at")),
        utc=True,
        errors="coerce",
    )
    data["month"] = data["graduated_at"].dt.floor("D").dt.tz_localize(None)
    data["status"] = np.where(pd.to_numeric(data.get("complete_30d"), errors="coerce").eq(1), "complete", "truncated")
    data["swap_count_30d"] = pd.to_numeric(data["swap_count_30d"], errors="coerce")
    return data


def plot_token_coverage_by_date_single(config: CaseConfig, path: Path) -> None:
    data = _token_activity_data(config)
    if data.empty:
        return
    daily = data.groupby(["month", "status"], as_index=False).size().pivot(index="month", columns="status", values="size").fillna(0)
    for col in ["complete", "truncated"]:
        if col not in daily:
            daily[col] = 0
    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    ax.stackplot(
        daily.index,
        daily["complete"],
        daily["truncated"],
        colors=[PALETTE["green"], PALETTE["amber"]],
        alpha=0.82,
        labels=["complete", "truncated"],
    )
    locator = mdates.AutoDateLocator(minticks=4, maxticks=7)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    ax.set_xlabel("Graduation date")
    ax.set_ylabel("Tokens")
    ax.set_title("Token Coverage by Graduation Date")
    ax.legend(frameon=False, loc="upper left")
    _clean_axis(ax, axis="y")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_token_persistence_survival_single(config: CaseConfig, path: Path) -> None:
    data = _token_activity_data(config)
    if data.empty:
        return
    complete_counts = data.loc[data["status"].eq("complete"), "swap_count_30d"].dropna().sort_values()
    if complete_counts.empty:
        return
    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    survival = 1 - np.arange(1, len(complete_counts) + 1) / len(complete_counts)
    ax.step(np.log1p(complete_counts), survival, where="post", color=PALETTE["navy"], linewidth=2.0)
    q25, median, q75 = complete_counts.quantile([0.25, 0.5, 0.75])
    for value, label in [(q25, "Q1"), (median, "median"), (q75, "Q3")]:
        ax.axvline(np.log1p(value), color=PALETTE["slate"], linestyle="--", linewidth=0.8)
        ax.text(np.log1p(value) + 0.03, 0.88, label, rotation=90, va="top", fontsize=8)
    ax.set_ylim(0, 1.02)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel("log(1 + 30d transaction-count proxy)")
    ax.set_ylabel("Share of complete tokens above threshold")
    ax.set_title("Complete-Window Persistence Survival")
    _clean_axis(ax, axis="y")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_h1_mechanism_audit(config: CaseConfig, path: Path) -> None:
    audit = _read_table(config.tables_dir / "h1_rpc_mechanism_causal_audit.csv")
    if audit.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(10.4, 7.0))

    ax = axes[0, 0]
    share_rows = audit.loc[
        audit["claim_id"].isin(
            [
                "H1-rpc-full-observed-lower-bound-activity",
                "H1-rpc-complete-window-activity",
                "H1-rpc-temporal-placebo-violation-rate",
            ]
        )
    ].copy()
    labels = ["All-token lower bound", "Complete windows", "Temporal violations"]
    y = np.arange(len(share_rows))
    for idx, row in enumerate(share_rows.itertuples(index=False)):
        color = _decision_color(row.decision)
        ax.plot([row.ci95_low, row.ci95_high], [idx, idx], color=color, linewidth=2.4)
        ax.scatter(row.estimate, idx, color=color, s=58, edgecolor="white", linewidth=0.8, zorder=3)
        label_x = min(max(float(row.estimate), 0.055), 0.945)
        label_y = idx + (0.18 if float(row.estimate) > 0.02 else -0.22)
        ax.text(label_x, label_y, f"{row.estimate * 100:.2f}%", ha="center", fontsize=8.2)
    ax.axvline(0.90, color=PALETTE["slate"], linestyle="--", linewidth=0.8)
    ax.set_yticks(y, labels)
    ax.set_xlim(-0.03, 1.03)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("A. Activity and Placebo Shares")
    ax.set_xlabel("Share with 95% interval")
    _clean_axis(ax, axis="x")

    ax = axes[0, 1]
    median_row = audit.loc[audit["claim_id"].eq("H1-rpc-complete-window-transaction-median")]
    if len(median_row):
        row = median_row.iloc[0]
        ax.barh([0], [float(row["estimate"])], color=PALETTE["navy"], alpha=0.88, height=0.45)
        ax.errorbar(
            [float(row["estimate"])],
            [0],
            xerr=[
                [float(row["estimate"]) - float(row["ci95_low"])],
                [float(row["ci95_high"]) - float(row["estimate"])],
            ],
            fmt="none",
            ecolor=PALETTE["ink"],
            capsize=3,
            linewidth=1.1,
        )
        ax.text(float(row["estimate"]) + 40, 0, f"{float(row['estimate']):.0f}", va="center", fontsize=9)
    ax.set_yticks([0], ["Complete 30d windows"])
    ax.set_xlabel("Median transaction-count proxy")
    ax.xaxis.set_major_formatter(FuncFormatter(_format_count))
    ax.set_title("B. Persistence Intensity")
    _clean_axis(ax, axis="x")

    ax = axes[1, 0]
    lag_row = audit.loc[audit["claim_id"].eq("H1-rpc-first-trade-timing")]
    if len(lag_row):
        row = lag_row.iloc[0]
        ax.errorbar(
            [float(row["estimate"])],
            [0],
            xerr=[
                [float(row["estimate"]) - float(row["ci95_low"])],
                [float(row["ci95_high"]) - float(row["estimate"])],
            ],
            fmt="o",
            color=PALETTE["teal"],
            ecolor=PALETTE["teal"],
            capsize=3,
            markersize=6,
            markeredgecolor="white",
            markeredgewidth=0.8,
        )
        ax.text(float(row["estimate"]) + 0.04, 0.10, f"{float(row['estimate']):.3f}s", fontsize=9)
    ax.axvline(0, color=PALETTE["ink"], linewidth=0.8)
    ax.set_yticks([0], ["First pool transaction"])
    ax.set_xlabel("Seconds after graduation")
    ax.set_title("C. Temporal Ordering")
    _clean_axis(ax, axis="x")

    ax = axes[1, 1]
    status_rows = audit.loc[
        audit["claim_id"].isin(
            [
                "H1-rpc-complete-window-activity",
                "H1-decoded-usd-trade-outcomes",
                "H4-early-wallet-event-time-outcomes",
            ]
        )
    ].copy()
    status_labels = ["H1 mechanism", "Decoded USD trades", "H4 early wallets"]
    y = np.arange(len(status_rows))
    status_colors = [_decision_color(value) for value in status_rows["decision"]]
    ax.barh(y, np.ones(len(status_rows)), color=status_colors, alpha=0.92, height=0.55)
    for idx, row in enumerate(status_rows.itertuples(index=False)):
        display_decision = "pass" if str(row.decision).startswith("passes_") else str(row.decision).replace("_", " ")
        ax.text(
            0.5,
            idx,
            display_decision,
            ha="center",
            va="center",
            fontsize=8.8,
            color="white" if "gap" in str(row.decision) else PALETTE["ink"],
        )
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_yticks(y, status_labels)
    ax.set_title("D. Claim Boundary")
    ax.grid(False)

    fig.suptitle("H1 RPC Mechanism Audit: Strong Venue Activation, Bounded Claim", y=1.01)
    fig.tight_layout()
    _save_figure(fig, path)


def plot_token_activity_distribution(config: CaseConfig, path: Path) -> None:
    source = config.output_root / "external_validation" / "h1_rpc_token_level_outcomes.csv"
    tokens = _read_table(source)
    if tokens.empty or "swap_count_30d" not in tokens:
        return
    data = tokens.copy()
    data["graduated_at"] = pd.to_datetime(
        data.get("graduated_at_30d", data.get("graduated_at")),
        utc=True,
        errors="coerce",
    )
    data["month"] = data["graduated_at"].dt.floor("D").dt.tz_localize(None)
    data["status"] = np.where(pd.to_numeric(data.get("complete_30d"), errors="coerce").eq(1), "complete", "truncated")
    data["swap_count_30d"] = pd.to_numeric(data["swap_count_30d"], errors="coerce")

    fig, axes = plt.subplots(1, 2, figsize=(10.0, 4.4))

    ax = axes[0]
    daily = data.groupby(["month", "status"], as_index=False).size().pivot(index="month", columns="status", values="size").fillna(0)
    for col in ["complete", "truncated"]:
        if col not in daily:
            daily[col] = 0
    ax.stackplot(
        daily.index,
        daily["complete"],
        daily["truncated"],
        colors=[PALETTE["green"], PALETTE["amber"]],
        alpha=0.82,
        labels=["complete", "truncated"],
    )
    ax.set_xlabel("Graduation date")
    ax.set_ylabel("Tokens")
    ax.set_title("A. Coverage by Graduation Date")
    locator = mdates.AutoDateLocator(minticks=4, maxticks=7)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    ax.legend(frameon=False, loc="upper left")
    _clean_axis(ax, axis="y")

    ax = axes[1]
    complete_counts = data.loc[data["status"].eq("complete"), "swap_count_30d"].dropna().sort_values()
    if len(complete_counts):
        survival = 1 - np.arange(1, len(complete_counts) + 1) / len(complete_counts)
        ax.step(np.log1p(complete_counts), survival, where="post", color=PALETTE["navy"], linewidth=2.0)
        q25, median, q75 = complete_counts.quantile([0.25, 0.5, 0.75])
        for value, label in [(q25, "Q1"), (median, "median"), (q75, "Q3")]:
            ax.axvline(np.log1p(value), color=PALETTE["slate"], linestyle="--", linewidth=0.8)
            ax.text(np.log1p(value) + 0.03, 0.88, label, rotation=90, va="top", fontsize=8)
    ax.set_ylim(0, 1.02)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel("log(1 + 30d transaction-count proxy)")
    ax.set_ylabel("Share of complete tokens above threshold")
    ax.set_title("B. Complete-Window Persistence Survival")
    _clean_axis(ax, axis="y")

    fig.suptitle("Token-Level Post-Migration Activity Distribution", y=1.02)
    fig.tight_layout()
    _save_figure(fig, path)


def plot_ladder_decision_flip(config: CaseConfig, ladder: pd.DataFrame, path: Path) -> None:
    focus = ladder.loc[ladder["rung"].isin(["L0", "L1", "L2", "L4", "L6", "L7"])].copy()
    focus = focus.loc[focus["estimate"].notna()].copy()
    if focus.empty:
        return
    focus["order"] = focus["rung"].str.extract(r"L([0-9]+)").astype(int)
    focus = focus.sort_values("order")
    x = np.arange(len(focus))

    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    ax.axhline(0, color=PALETTE["ink"], linewidth=0.9)
    ax.plot(x, focus["estimate"], color=PALETTE["navy"], linewidth=1.8, zorder=2)
    for idx, row in enumerate(focus.itertuples(index=False)):
        color = _decision_color(row.worked_decision)
        ax.plot([idx, idx], [row.ci95_low, row.ci95_high], color=color, linewidth=2.4, zorder=1)
        ax.scatter(idx, row.estimate, s=66, color=color, edgecolor="white", linewidth=0.8, zorder=3)
        ax.text(
            idx,
            row.ci95_high + 0.10,
            str(row.worked_decision).replace("_", "\n"),
            ha="center",
            va="bottom",
            fontsize=8.0,
            color=color,
        )
    ax.set_xticks(x, focus["rung"])
    ax.set_ylabel("Estimate in log points")
    ax.set_xlabel("Trustworthiness ladder rung")
    ax.set_title("Naive-to-Trustworthy Conclusion Flip")
    ax.set_ylim(min(float(focus["ci95_low"].min()) - 0.25, -1.55), max(float(focus["ci95_high"].max()) + 0.45, 1.55))
    _clean_axis(ax, axis="y")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_paired_case_ladder(config: CaseConfig, ladder: pd.DataFrame, path: Path) -> None:
    mirror_path = config.project_root / "benchmark_release" / "data" / "mirror_case_ladder.csv"
    mirror = _read_table(mirror_path)
    if mirror.empty or ladder.empty:
        return

    def ladder_row(rung: str) -> pd.Series:
        rows = ladder.loc[ladder["rung"].eq(rung)]
        return rows.iloc[0] if len(rows) else pd.Series(dtype=object)

    def mirror_row(rung: str) -> pd.Series:
        rows = mirror.loc[mirror["rung"].eq(rung)]
        return rows.iloc[0] if len(rows) else pd.Series(dtype=object)

    def as_float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("nan")

    def fmt_log(value: object) -> str:
        number = as_float(value)
        return "n/a" if np.isnan(number) else f"{number:+.3f}"

    def fmt_pp(value: object) -> str:
        number = as_float(value)
        return "n/a" if np.isnan(number) else f"{number * 100:+.3f} pp"

    def fmt_pct(value: object) -> str:
        number = as_float(value)
        return "n/a" if np.isnan(number) else f"{number * 100:.3f}%"

    def color_for(decision: object) -> str:
        text = str(decision).lower()
        if "yes" in text or "supported" in text or "credible" in text or "stratified" in text:
            return PALETTE["green"]
        if "near_null" in text or "nothing" in text:
            return PALETTE["gray"]
        if "uncertain" in text or "depends" in text:
            return PALETTE["slate"]
        if "flag" in text or "strict" in text or "confounding" in text:
            return PALETTE["amber"]
        if "risk" in text:
            return PALETTE["purple"]
        return PALETTE["teal"]

    stages = [
        "Naive read",
        "Comparison /\nstrata",
        "Controls /\nmodel",
        "Outcome\ndepth",
        "Diagnostic\nscreen",
        "Inference /\nsensitivity",
        "Claim\nboundary",
    ]

    a0, a1, a2, a3, a4, a6, a7 = [ladder_row(rung) for rung in ["L0", "L1", "L2", "L3", "L4", "L6", "L7"]]
    b0, b1, b2, b3, b5, b4, b6 = [mirror_row(rung) for rung in ["B0", "B1", "B2", "B3", "B5", "B4", "B6"]]

    case_a = [
        ("L0", "yes", fmt_log(a0.get("estimate")), a0.get("worked_decision", "")),
        ("L1", "uncertain", fmt_log(a1.get("estimate")), a1.get("worked_decision", "")),
        ("L2", "uncertain", fmt_log(a2.get("estimate")), a2.get("worked_decision", "")),
        ("L3", "dynamic yes", fmt_log(a3.get("estimate")), a3.get("worked_decision", "")),
        ("L4", "pretrend flag", "", a4.get("worked_decision", "")),
        ("L6", "few-cluster uncertain", f"p={as_float(a6.get('p_value')):.3f}", a6.get("worked_decision", "")),
        ("L7", "stakeholder bounded", "", a7.get("worked_decision", "")),
    ]
    case_b = [
        ("B0", "near null", fmt_pct(b0.get("estimate")), b0.get("decision", "")),
        ("B1", "stratified signal", fmt_pp(as_float(b1.get("estimate"))), b1.get("decision", "")),
        ("B2", "controlled support", fmt_pp(as_float(b2.get("estimate"))), b2.get("decision", "")),
        ("B3", "mechanism depth", "", b3.get("decision", "")),
        ("B5", "timing strict", "", b5.get("decision", "")),
        ("B4", "matched support", fmt_pp(as_float(b4.get("estimate"))), b4.get("decision", "")),
        ("B6", "supported, not causal", "", b6.get("decision", "")),
    ]

    fig, ax = plt.subplots(figsize=(12.2, 4.8))
    x = np.arange(len(stages))
    rows = [
        ("Case A: PumpSwap market", 1.0, case_a, "naive yes -> trustworthy uncertain", PALETTE["navy"]),
        ("Case B: Telegram metadata", 0.0, case_b, "naive nothing happened -> supported matched signal", PALETTE["teal"]),
    ]

    for _, y, points, summary, line_color in rows:
        ax.plot(x, np.full_like(x, y, dtype=float), color=PALETTE["grid"], linewidth=3.0, zorder=0)
        ax.annotate(
            "",
            xy=(len(stages) - 0.18, y),
            xytext=(0.08, y),
            arrowprops={"arrowstyle": "->", "color": line_color, "linewidth": 1.5},
            zorder=1,
        )
        for idx, (rung, decision_label, value_label, decision_key) in enumerate(points):
            color = color_for(decision_key or decision_label)
            ax.scatter(idx, y, s=260, marker="o", color=color, edgecolor="white", linewidth=1.2, zorder=3)
            main_label = f"{rung}\n{decision_label}"
            if value_label:
                main_label = f"{main_label}\n{value_label}"
            ax.text(
                idx,
                y + (0.14 if y > 0 else -0.14),
                main_label,
                ha="center",
                va="bottom" if y > 0 else "top",
                fontsize=7.4,
                color=PALETTE["ink"],
                linespacing=1.05,
            )
        ax.text(
            len(stages) + 0.16,
            y,
            "\n".join(textwrap.wrap(summary, width=31, break_long_words=False)),
            ha="left",
            va="center",
            fontsize=8.8,
            weight="semibold",
            color=line_color,
            bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": line_color, "linewidth": 0.8},
        )

    ax.set_yticks([1.0, 0.0], [rows[0][0], rows[1][0]])
    ax.set_xticks(x, stages)
    ax.set_xlim(-0.45, len(stages) + 1.95)
    ax.set_ylim(-0.55, 1.55)
    ax.set_title("Paired Evidence Ladder: Opposite Conclusion Revisions")
    ax.set_xlabel("Common evidence requirement")
    ax.text(
        0.5,
        -0.22,
        "Case B is a supported matched predictive/mechanism signal, not a causal Telegram effect without an exogenous exposure shock.",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=8.3,
        color=PALETTE["slate"],
    )
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout()
    _save_figure(fig, path)


def plot_rpc_deepening_gain(config: CaseConfig, path: Path) -> None:
    baseline = _read_json(config.tables_dir / "external_validation_2page_baseline_stats.json")
    current = _read_json(config.tables_dir / "external_validation_summary.json")
    if not baseline or not current:
        return
    rows = [
        ("Complete tokens", baseline.get("post_30d_complete_tokens"), current.get("post_30d_complete_tokens"), "higher"),
        ("Complete share", baseline.get("share_30d_complete"), current.get("share_30d_post_windows_complete"), "higher"),
        (
            "Median complete 30d tx",
            baseline.get("complete_median_30d_pool_tx_count"),
            current.get("median_complete_30d_pool_tx_count"),
            "higher",
        ),
        ("Truncated tokens", baseline.get("post_30d_truncated_tokens"), current.get("post_30d_truncated_tokens"), "lower"),
        (
            "Truncated-zero observed",
            baseline.get("truncated_zero_observed_tokens"),
            current.get("post_30d_truncated_zero_observed_tokens"),
            "lower",
        ),
    ]
    data = pd.DataFrame(rows, columns=["metric", "baseline", "current", "direction"]).dropna()
    if data.empty:
        return
    data["relative_change"] = (data["current"].astype(float) - data["baseline"].astype(float)) / data["baseline"].astype(float)
    data["beneficial_change"] = np.where(data["direction"].eq("lower"), -data["relative_change"], data["relative_change"])
    data = data.iloc[::-1].reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    y = np.arange(len(data))
    colors = [PALETTE["green"] if value >= 0 else PALETTE["red"] for value in data["beneficial_change"]]
    ax.axvline(0, color=PALETTE["ink"], linewidth=0.9)
    ax.barh(y, data["beneficial_change"], color=colors, alpha=0.88, height=0.58)
    for idx, row in enumerate(data.itertuples(index=False)):
        raw = f"{_format_metric_value(row.metric, row.baseline)} -> {_format_metric_value(row.metric, row.current)}"
        pct = f"{row.beneficial_change * 100:+.0f}%"
        xpos = row.beneficial_change + (0.035 if row.beneficial_change >= 0 else -0.035)
        ax.text(
            xpos,
            idx,
            f"{pct}   ({raw})",
            va="center",
            ha="left" if row.beneficial_change >= 0 else "right",
            fontsize=8.5,
            color=PALETTE["ink"],
        )
    ax.set_yticks(y, data["metric"])
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel("Beneficial relative change from 2-page baseline to Helius-deepened run")
    ax.set_title("Data-Depth Gain: What the Helius Run Added")
    ax.set_xlim(min(-0.06, float(data["beneficial_change"].min()) * 1.18), max(0.72, float(data["beneficial_change"].max()) * 1.23))
    _clean_axis(ax, axis="x")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_horizon_ridgeline(config: CaseConfig, path: Path) -> None:
    post = _read_table(config.output_root / "external_validation" / "solana_post_migration_pool_windows.csv")
    if post.empty:
        return
    complete = post.loc[post["signature_window_status"].astype(str).eq("ok")].copy()
    if complete.empty:
        return
    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    bins = np.linspace(0, np.log1p(complete["swap_count"].max()), 46)
    horizons = [1, 7, 30]
    colors = {1: PALETTE["teal"], 7: PALETTE["navy"], 30: PALETTE["purple"]}
    offsets = {1: 2.0, 7: 1.0, 30: 0.0}
    for horizon in horizons:
        values = np.log1p(pd.to_numeric(complete.loc[complete["horizon_days"].eq(horizon), "swap_count"], errors="coerce").dropna())
        if values.empty:
            continue
        hist, edges = np.histogram(values, bins=bins, density=True)
        mids = (edges[:-1] + edges[1:]) / 2
        if hist.max() > 0:
            hist = hist / hist.max() * 0.78
        base = offsets[horizon]
        ax.fill_between(mids, base, base + hist, color=colors[horizon], alpha=0.35)
        ax.plot(mids, base + hist, color=colors[horizon], linewidth=1.5)
        median = np.log1p(float(np.median(np.expm1(values))))
        ax.axvline(median, ymin=(base + 0.03) / 3.05, ymax=(base + 0.76) / 3.05, color=colors[horizon], linestyle="--", linewidth=0.9)
        ax.text(0.25, base + 0.25, f"{horizon}d", va="center", fontsize=9.5, color=colors[horizon], weight="semibold")
    ax.set_yticks([])
    ax.set_xlabel("log(1 + transaction-count proxy), complete windows")
    ax.set_title("Post-Migration Activity Distribution Shifts Across Horizons")
    _clean_axis(ax, axis="x")
    fig.tight_layout()
    _save_figure(fig, path)


def plot_readiness_gap_heatmap(config: CaseConfig, path: Path) -> None:
    audit = _read_table(config.tables_dir / "paper_readiness_audit.csv")
    if audit.empty:
        return
    status_to_score = {"gap": 0.0, "warning": 0.5, "pass": 1.0}
    audit = audit.copy()
    audit["label"] = audit["area"].map(AREA_LABELS).fillna(audit["area"]).str.replace("\n", " ", regex=False)
    matrix = audit[["label", "status"]].copy()
    fig, ax = plt.subplots(figsize=(8.6, 3.4))
    scores = np.array([[status_to_score.get(status, 0.0) for status in matrix["status"]]])
    cmap = LinearSegmentedColormap.from_list(
        "readiness_status",
        [PALETTE["red"], PALETTE["amber"], PALETTE["green"]],
    )
    ax.imshow(scores, aspect="auto", cmap=cmap, vmin=0, vmax=1)
    ax.set_xticks(np.arange(len(matrix)), [_wrap_label(label, 14) for label in matrix["label"]], rotation=25, ha="right")
    ax.set_yticks([0], ["Evidence status"])
    for idx, status in enumerate(matrix["status"]):
        ax.text(
            idx,
            0,
            str(status).upper(),
            ha="center",
            va="center",
            fontsize=7.8,
            color="white" if status in {"pass", "gap"} else PALETTE["ink"],
            weight="semibold",
        )
    ax.set_title("Readiness Heatmap: Contribution Strengths and Remaining Gaps")
    ax.grid(False)
    fig.tight_layout()
    _save_figure(fig, path)


def plot_agentic_scaffold_tradeoff(config: CaseConfig, path: Path) -> None:
    scores = _ordered_agent_scores(config)
    if scores.empty:
        return
    scores = scores.copy()
    scores["abs_calibration_gap"] = scores["calibration_gap"].astype(float).abs()
    scores["x"] = scores["method_omission_rate"].astype(float)
    scores["y"] = scores["abs_calibration_gap"].astype(float)
    grouped = (
        scores.groupby(["x", "y"], as_index=False)
        .agg(
            rungs=("rung", lambda values: "/".join(values.astype(str))),
            mean_rung_order=("rung_order", "mean"),
        )
        .sort_values("mean_rung_order")
    )
    fig, ax = plt.subplots(figsize=(6.8, 5.0))
    scatter = ax.scatter(
        grouped["x"],
        grouped["y"],
        s=90,
        c=grouped["mean_rung_order"],
        cmap="viridis",
        edgecolor="white",
        linewidth=0.8,
        zorder=3,
    )
    label_offsets = {
        "L0/L2": (-0.012, 0.020, "right"),
        "L4": (0.012, 0.020, "left"),
        "L6": (0.012, 0.012, "left"),
        "L1": (0.012, 0.012, "left"),
    }
    for row in grouped.itertuples(index=False):
        dx, dy, ha = label_offsets.get(row.rungs, (0.012, 0.012, "left"))
        ax.text(row.x + dx, row.y + dy, row.rungs, fontsize=8.3, ha=ha)
    ordered = scores.sort_values("rung_order")
    ax.plot(ordered["x"], ordered["y"], color=PALETTE["slate"], alpha=0.45, linewidth=1.0, zorder=1)
    ax.set_xlabel("Method omission rate")
    ax.set_ylabel("Absolute calibration gap")
    ax.set_xlim(0.25, max(float(scores["x"].max()) + 0.09, 0.75))
    ax.set_ylim(0.25, max(float(scores["y"].max()) + 0.10, 0.9))
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("Agentic Scaffold Tradeoff: Method Coverage vs Calibration")
    _clean_axis(ax, axis="both")
    fig.colorbar(scatter, ax=ax, label="Mean rung order", fraction=0.046, pad=0.04)
    fig.tight_layout()
    _save_figure(fig, path)


def plot_research_contribution_matrix(config: CaseConfig, path: Path) -> None:
    summary = _read_json(config.tables_dir / "paper_readiness_summary.json")
    audit = _read_table(config.tables_dir / "paper_readiness_audit.csv")
    if audit.empty:
        return
    status = dict(zip(audit["area"], audit["status"]))
    rows = [
        ("C1 ladder benchmark", ["benchmark_ladder", "rpc_external_validation", "few_cluster_inference", "agentic_execution", "decoded_indexer_outcomes"]),
        ("C2 stakeholder battery", ["claim_boundary", "rpc_external_validation", "claim_boundary", "agentic_execution", "decoded_indexer_outcomes"]),
        (
            "C3 token-level mechanism",
            ["h1_rpc_mechanism_validation", "rpc_external_validation", "claim_boundary", "agentic_execution", "decoded_indexer_outcomes"],
        ),
        ("C4 AI evaluation arm", ["agentic_execution", "benchmark_ladder", "claim_boundary", "agentic_execution", "decoded_indexer_outcomes"]),
        ("C5 open-science audit", ["claim_boundary", "rpc_external_validation", "few_cluster_inference", "agentic_execution", "decoded_indexer_outcomes"]),
    ]
    cols = ["Artifact", "Data depth", "Causal rigor", "AI scaffold", "Decoded USD"]
    status_to_score = {"gap": 0.0, "warning": 0.5, "pass": 1.0}
    matrix = np.array([[status_to_score.get(status.get(area, "gap"), 0.0) for area in areas] for _, areas in rows])
    fig, ax = plt.subplots(figsize=(8.4, 5.0))
    cmap = LinearSegmentedColormap.from_list(
        "contribution",
        [PALETTE["red"], PALETTE["amber"], PALETTE["green"]],
    )
    ax.imshow(matrix, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(np.arange(len(cols)), cols)
    ax.set_yticks(np.arange(len(rows)), [row[0] for row in rows])
    labels = {0.0: "gap", 0.5: "warn", 1.0: "pass"}
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = float(matrix[i, j])
            ax.text(
                j,
                i,
                labels.get(value, f"{value:.1f}"),
                ha="center",
                va="center",
                fontsize=8.6,
                color="white" if value in {0.0, 1.0} else PALETTE["ink"],
                weight="semibold",
            )
    readiness = str(summary.get("readiness_label", ""))
    ax.set_title("Research Contribution Matrix: Strengths and Gaps")
    if readiness:
        ax.set_xlabel(f"Current status: {readiness.replace('_', ' ')}")
    ax.grid(False)
    fig.tight_layout()
    _save_figure(fig, path)


def make_all_figures(
    config: CaseConfig,
    ladder: pd.DataFrame,
    event: pd.DataFrame,
    frequency: pd.DataFrame,
    battery: pd.DataFrame,
) -> None:
    for name in OBSOLETE_FIGURES:
        (config.figures_dir / name).unlink(missing_ok=True)
    plot_parallel_trends(config, config.figures_dir / "fig_parallel_trends.png")
    plot_event_study(event, config.figures_dir / "fig_event_study.png")
    plot_ladder(ladder, config.figures_dir / "fig_ablation_ladder.png")
    plot_frequency_sensitivity(frequency, config.figures_dir / "fig_frequency_sensitivity.png")
    plot_metric_status(battery, config.figures_dir / "fig_metric_battery_status.png")
    plot_external_validation_rpc(config, config.figures_dir / "fig_external_validation_rpc.png")
    plot_readiness_radar(config, config.figures_dir / "fig_readiness_radar.png")
    plot_readiness_status_bar(config, config.figures_dir / "fig_readiness_status_bar.png")
    plot_market_protocol_volume_lines(config, config.figures_dir / "fig_market_protocol_volume_lines.png")
    plot_agentic_method_omission_bar(config, config.figures_dir / "fig_agentic_method_omission_bar.png")
    plot_agentic_calibration_gap_bar(config, config.figures_dir / "fig_agentic_calibration_gap_bar.png")
    plot_h1_mechanism_audit(config, config.figures_dir / "fig_h1_mechanism_audit.png")
    plot_token_activity_distribution(config, config.figures_dir / "fig_token_activity_distribution.png")
    plot_frequency_market_single(frequency, config.figures_dir / "fig_frequency_market_twfe_single.png")
    plot_frequency_data_richness_single(frequency, config.figures_dir / "fig_frequency_data_richness_single.png")
    plot_rpc_active_share_single(config, config.figures_dir / "fig_rpc_active_share_single.png")
    plot_rpc_median_persistence_single(config, config.figures_dir / "fig_rpc_median_persistence_single.png")
    plot_rpc_token_distribution_single(config, config.figures_dir / "fig_rpc_token_distribution_single.png")
    plot_rpc_window_coverage_single(config, config.figures_dir / "fig_rpc_window_coverage_single.png")
    plot_h1_activity_placebo_single(config, config.figures_dir / "fig_h1_activity_placebo_single.png")
    plot_h1_persistence_intensity_single(config, config.figures_dir / "fig_h1_persistence_intensity_single.png")
    plot_h1_temporal_ordering_single(config, config.figures_dir / "fig_h1_temporal_ordering_single.png")
    plot_h1_claim_boundary_single(config, config.figures_dir / "fig_h1_claim_boundary_single.png")
    plot_token_coverage_by_date_single(config, config.figures_dir / "fig_token_coverage_by_date_single.png")
    plot_token_persistence_survival_single(config, config.figures_dir / "fig_token_persistence_survival_single.png")
    plot_ladder_decision_flip(config, ladder, config.figures_dir / "fig_ladder_decision_flip.png")
    plot_paired_case_ladder(config, ladder, config.figures_dir / "fig_paired_case_ladder.png")
    plot_rpc_deepening_gain(config, config.figures_dir / "fig_rpc_deepening_gain.png")
    plot_horizon_ridgeline(config, config.figures_dir / "fig_horizon_ridgeline.png")
    plot_readiness_gap_heatmap(config, config.figures_dir / "fig_readiness_gap_heatmap.png")
    plot_agentic_scaffold_tradeoff(config, config.figures_dir / "fig_agentic_scaffold_tradeoff.png")
    plot_research_contribution_matrix(config, config.figures_dir / "fig_research_contribution_matrix.png")
