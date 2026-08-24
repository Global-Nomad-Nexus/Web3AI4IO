"""Regenerate the nine paper figures from archived evidence and the shared theme.

Empirical values are read from ``reproduction/archived``. Figure 1 is rendered
from ``reproduction/figures/teaser_pipeline.yaml``, which is also compiled into
an editable Draw.io master. The file is JSON-compatible YAML so the standard
library can load it without PyYAML.
"""

from __future__ import annotations

import json
import re
import sys
import textwrap
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

from paths import ARCHIVED, PAPER, REPRO
from theme import (
    APPENDIX_MAX_HEIGHT_IN,
    BOUNDARY,
    COVERAGE_WIDTH_IN,
    DIVIDER,
    FULL_WIDTH_IN,
    INK,
    LABEL_PT,
    LEGEND_PT,
    LIGHT_BOUNDARY,
    LIGHT_PRIMARY,
    LIGHT_SECONDARY,
    LIGHT_STATUS,
    METRIC_MAX_HEIGHT_IN,
    MUTED,
    PAIR_WIDTH_IN,
    PANEL_PT,
    PRIMARY,
    SECONDARY,
    STATUS,
    STRESS_WIDTH_IN,
    SURFACE,
    TICK_PT,
    WHITE,
    apply_theme,
    clean_axes,
    export_figure,
    panel_label,
)

OUT = PAPER / "figs"
FIGURES = REPRO / "figures"
SPEC_PATH = FIGURES / "teaser_pipeline.yaml"
DRAWIO_PATH = FIGURES / "teaser_figure.drawio"
SCOPE = json.loads((REPRO / "scope.json").read_text(encoding="utf-8"))
DECISION_LABEL = {
    "yes": "affirmative",
    "no_or_uncertain": "uncertain",
    "pretrend_flagged": "pretrend risk",
    "retail_risk_higher": "heterogeneous",
    "depends_on_stakeholder": "stakeholder-specific",
}
DECISION_COLOR = {
    "affirmative": SECONDARY,
    "uncertain": STATUS,
    "pretrend risk": BOUNDARY,
    "heterogeneous": STATUS,
    "stakeholder-specific": PRIMARY,
}


def read_csv(rel: str) -> pd.DataFrame:
    return pd.read_csv(ARCHIVED / rel)


def load_json(rel: str) -> dict:
    return json.loads((ARCHIVED / rel).read_text(encoding="utf-8"))


def save(fig, stem: str) -> None:
    export_figure(fig, OUT, stem)
    plt.close(fig)
    print(f"wrote {stem}")


def load_spec(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _style_value(style: str, key: str, default: str = "") -> str:
    match = re.search(rf"(?:^|;){re.escape(key)}=([^;]+)", style)
    return match.group(1) if match else default


def validate_drawio(path: Path) -> list[str]:
    errors: list[str] = []
    tree = ET.parse(path)
    cells = tree.findall(".//mxCell")
    ids = [cell.get("id", "") for cell in cells]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate mxCell IDs")
    id_set = set(ids)
    for cell in cells:
        cell_id = cell.get("id", "<missing>")
        parent = cell.get("parent")
        if parent and parent not in id_set:
            errors.append(f"{cell_id}: missing parent {parent}")
        if cell.get("vertex") == "1":
            if not re.sub(r"<[^>]+>", "", cell.get("value") or "").strip():
                errors.append(f"{cell_id}: empty node label")
            geometry = cell.find("mxGeometry")
            if geometry is None:
                errors.append(f"{cell_id}: missing geometry")
            else:
                for key in ("width", "height"):
                    try:
                        if float(geometry.get(key, "0")) <= 0:
                            errors.append(f"{cell_id}: invalid {key}")
                    except ValueError:
                        errors.append(f"{cell_id}: nonnumeric {key}")
        if cell.get("edge") == "1":
            for key in ("source", "target"):
                endpoint = cell.get(key)
                if endpoint not in id_set:
                    errors.append(f"{cell_id}: dangling {key} {endpoint}")
        size = _style_value(cell.get("style", ""), "fontSize")
        if size:
            try:
                if float(size) < 8:
                    errors.append(f"{cell_id}: fontSize {size} below 8 pt")
            except ValueError:
                errors.append(f"{cell_id}: invalid fontSize {size}")
    return errors


def _node_style(node: dict) -> str:
    role = node.get("role", "surface")
    fills = {
        "surface": SURFACE,
        "primary": PRIMARY,
        "secondary": LIGHT_SECONDARY,
        "status": LIGHT_STATUS,
        "boundary": LIGHT_BOUNDARY,
    }
    fonts = {
        "surface": INK,
        "primary": WHITE,
        "secondary": INK,
        "status": INK,
        "boundary": BOUNDARY,
    }
    fill = fills.get(role, SURFACE)
    font = fonts.get(role, INK)
    stroke = PRIMARY if role == "primary" else INK
    width = "2.2" if node.get("type") in {"model", "decision"} else "1.4"
    shape = "rhombus;" if node.get("type") == "decision" else "rounded=1;"
    return (
        f"{shape}whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth={width};fontColor={font};fontSize=9;fontFamily=Arial;"
        "align=center;verticalAlign=middle;spacing=6;"
    )


def _edge_style(kind: str) -> str:
    dashed = kind in {"control", "feedback", "optional"}
    color = STATUS if kind in {"control", "feedback"} else INK
    return (
        "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;"
        f"html=1;endArrow=block;endFill=1;strokeWidth=1.6;strokeColor={color};"
        f"dashed={1 if dashed else 0};fontSize=8;fontFamily=Arial;fontColor={INK};"
        "labelBackgroundColor=#FFFFFF;"
    )


def build_drawio(spec: dict, output: Path) -> None:
    figure = spec["figure"]
    diagram = ET.Element("diagram", {"id": figure["id"], "name": figure.get("title", "Pipeline")})
    model = ET.SubElement(
        diagram,
        "mxGraphModel",
        {
            "dx": "1200",
            "dy": "800",
            "grid": "1",
            "gridSize": "10",
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": str(figure.get("width", 1280)),
            "pageHeight": str(figure.get("height", 400)),
            "math": "0",
            "shadow": "0",
        },
    )
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    for node in spec.get("nodes", []):
        label = escape(str(node["label"])).replace("\n", "<br/>")
        detail = escape(str(node.get("detail") or "")).replace("\n", "<br/>")
        if detail:
            value = f"<b>{label}</b><br/>{detail}"
        else:
            value = f"<b>{label}</b>"
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": node["id"],
                "value": value,
                "style": _node_style(node),
                "vertex": "1",
                "parent": "1",
            },
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            {
                "x": str(node["x"]),
                "y": str(node["y"]),
                "width": str(node["width"]),
                "height": str(node["height"]),
                "as": "geometry",
            },
        )
    for edge in spec.get("edges", []):
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": edge["id"],
                "value": escape(str(edge.get("label") or "")),
                "style": _edge_style(edge.get("kind", "data")),
                "edge": "1",
                "parent": "1",
                "source": edge["source"],
                "target": edge["target"],
            },
        )
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
    mxfile = ET.Element(
        "mxfile",
        {
            "host": "app.diagrams.net",
            "modified": datetime.now(timezone.utc).isoformat(),
            "agent": "academic-pipeline-viz",
            "version": "local",
            "type": "device",
        },
    )
    mxfile.append(diagram)
    tree = ET.ElementTree(mxfile)
    ET.indent(tree, space="  ")
    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output, encoding="utf-8", xml_declaration=True)


def make_teaser() -> None:
    spec = load_spec(SPEC_PATH)
    build_drawio(spec, DRAWIO_PATH)
    errors = validate_drawio(DRAWIO_PATH)
    if errors:
        raise ValueError("Draw.io validation failed: " + "; ".join(errors))
    print(f"wrote {DRAWIO_PATH.relative_to(REPRO)} (Draw.io validation PASS)")

    figure = spec["figure"]
    width, height = float(figure["width"]), float(figure["height"])
    fig_h = FULL_WIDTH_IN * height / width
    fig, ax = plt.subplots(figsize=(FULL_WIDTH_IN, fig_h))
    ax.set_xlim(0, width)
    ax.set_ylim(height, 0)
    ax.axis("off")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.98, bottom=0.02)

    nodes = {node["id"]: node for node in spec["nodes"]}
    role_face = {
        "surface": (SURFACE, INK, DIVIDER),
        "primary": (PRIMARY, WHITE, PRIMARY),
        "secondary": (LIGHT_SECONDARY, INK, SECONDARY),
        "status": (LIGHT_STATUS, INK, STATUS),
        "boundary": (LIGHT_BOUNDARY, BOUNDARY, BOUNDARY),
    }

    def port(node: dict, side: str) -> tuple[float, float]:
        x, y, w, h = node["x"], node["y"], node["width"], node["height"]
        if side == "e":
            return x + w, y + h / 2
        if side == "w":
            return x, y + h / 2
        raise ValueError(side)

    for edge in spec["edges"]:
        source, target = nodes[edge["source"]], nodes[edge["target"]]
        x1, y1 = port(source, "e")
        x2, y2 = port(target, "w")
        kind = edge.get("kind", "data")
        color = STATUS if kind == "control" else INK
        ls = (0, (3.5, 2.2)) if kind == "control" else "-"
        mid = (x1 + x2) / 2
        ax.plot([x1 + 2, mid], [y1, y1], color=color, lw=1.15, linestyle=ls, solid_capstyle="butt")
        ax.plot([mid, mid], [y1, y2], color=color, lw=1.15, linestyle=ls, solid_capstyle="butt")
        ax.annotate(
            "",
            xy=(x2 - 4, y2),
            xytext=(mid, y2),
            arrowprops={"arrowstyle": "-|>", "color": color, "lw": 1.15},
        )

    for node in spec["nodes"]:
        face, text_color, edge_color = role_face[node["role"]]
        x, y, w, h = node["x"], node["y"], node["width"], node["height"]
        if node["type"] == "annotation":
            ax.add_patch(Rectangle((x, y), w, h, facecolor=SURFACE, edgecolor=DIVIDER, linewidth=0.8))
            ax.text(x + w / 2, y + h / 2, node["label"], ha="center", va="center", fontsize=TICK_PT, color=INK, fontstyle="italic")
            continue
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0.3,rounding_size=12",
                facecolor=face,
                edgecolor=edge_color,
                linewidth=1.6 if node["role"] == "primary" else 1.1,
            )
        )
        ax.text(
            x + w / 2,
            y + h / 2,
            node["label"],
            ha="center",
            va="center",
            color=text_color,
            fontsize=8.2,
            fontweight="bold",
            linespacing=1.2,
        )
    save(fig, "teaser_figure")


def _fmt_count(value: int) -> str:
    return f"{value:,}"


def make_coverage_map() -> None:
    sol = load_json("release/solana_core.json")
    base = load_json("release/base_core.json")
    bnb = load_json("release/bnb_core.json")
    tron = load_json("release/tron_core.json")
    events = {item["platform_id"]: item["eligibility_status"] for item in load_json("release/event_registry.json")["events"]}
    chain_names = {row["chain"]: f"{row['chain']}\n{row['platform']}" for row in SCOPE["chains"]}

    # Coverage states follow the Figure 2 caption in paper/neurips_2026.tex
    # (observed, bounded or selected, uncollected, release-excluded) plus
    # event_registry.json eligibility_status. Counts come from release JSON.
    rows = [
        {
            "label": chain_names["Solana"],
            "cells": [
                ("observed", _fmt_count(sol["raw_reproduction"]["deduplicated_terminal_outcomes"])),
                ("bounded", f"{_fmt_count(sol['raw_reproduction']['graduated_tokens'])}\ngraduated"),
                ("observed", "terminal\nstate"),
                ("bounded", f"{_fmt_count(sol['decoded_coverage']['tokens_with_delivered_decoded_swaps'])}\ndecoded"),
                ("excluded", "outside\nrelease"),
                (events["pump_fun_pumpswap"], events["pump_fun_pumpswap"]),
            ],
        },
        {
            "label": chain_names["Base"],
            "cells": [
                ("observed", _fmt_count(base["tables"]["launches"]["rows"])),
                ("observed", _fmt_count(base["tables"]["pools"]["rows"])),
                ("uncollected", "not\ncollected"),
                ("uncollected", "not\ncollected"),
                ("excluded", "outside\nrelease"),
                (events["clanker"], events["clanker"]),
            ],
        },
        {
            "label": chain_names["BNB"],
            "cells": [
                ("observed", _fmt_count(bnb["tables"]["launches"]["rows"])),
                ("bounded", _fmt_count(bnb["tables"]["pools"]["rows"])),
                ("uncollected", "not\ncollected"),
                ("uncollected", "not\ncollected"),
                ("excluded", "outside\nrelease"),
                (events["four_meme"], events["four_meme"]),
            ],
        },
        {
            "label": chain_names["TRON"],
            "cells": [
                ("observed", _fmt_count(tron["tables"]["launches"]["rows"])),
                ("bounded", _fmt_count(tron["tables"]["pools"]["rows"])),
                ("uncollected", "not\ncollected"),
                ("uncollected", "not\ncollected"),
                ("excluded", "outside\nrelease"),
                (events["sunpump"], events["sunpump"]),
            ],
        },
    ]
    columns = [
        "Launch\nuniverse",
        "Pool or\nliquidity",
        "Terminal\noutcome",
        "Activity\noutcomes",
        "Metadata",
        "Event\ndesign",
    ]
    styles = {
        "observed": (PRIMARY, WHITE, "", PRIMARY),
        "bounded": (LIGHT_STATUS, INK, "", STATUS),
        "uncollected": (SURFACE, MUTED, "", DIVIDER),
        "excluded": (WHITE, MUTED, "///", DIVIDER),
        "accepted": (SECONDARY, WHITE, "", SECONDARY),
        "conditional": (STATUS, INK, "", STATUS),
        "rejected": (LIGHT_BOUNDARY, BOUNDARY, "xx", BOUNDARY),
    }
    fig, ax = plt.subplots(figsize=(COVERAGE_WIDTH_IN, 2.55))
    ax.set_xlim(-1.55, 6.12)
    ax.set_ylim(-0.72, 4.55)
    ax.axis("off")
    fig.subplots_adjust(left=0.02, right=0.99, top=0.97, bottom=0.02)
    for j, label in enumerate(columns):
        ax.text(j + 0.5, 4.18, label, ha="center", va="center", fontsize=TICK_PT, fontweight="bold", color=INK)
    for i, row in enumerate(rows):
        y = 3.12 - i
        ax.text(-0.10, y + 0.42, row["label"], ha="right", va="center", fontsize=TICK_PT, fontweight="bold", color=INK)
        for j, (status, label) in enumerate(row["cells"]):
            face, text, hatch, edge = styles[status]
            ax.add_patch(
                Rectangle(
                    (j + 0.07, y),
                    0.86,
                    0.84,
                    facecolor=face,
                    edgecolor=edge,
                    linewidth=0.7,
                    hatch=hatch,
                )
            )
            ax.text(j + 0.50, y + 0.42, label, ha="center", va="center", fontsize=TICK_PT, color=text)
    legend = [
        (PRIMARY, "", "Observed"),
        (LIGHT_STATUS, "", "Bounded or selected"),
        (SURFACE, "", "Uncollected"),
        (WHITE, "///", "Release-excluded"),
    ]
    for j, (color, hatch, label) in enumerate(legend):
        x = -1.48 + (j % 2) * 3.55
        y = -0.22 if j < 2 else -0.56
        ax.add_patch(Rectangle((x, y), 0.18, 0.18, facecolor=color, edgecolor=DIVIDER, linewidth=0.6, hatch=hatch))
        ax.text(x + 0.24, y + 0.09, label, va="center", fontsize=TICK_PT, color=MUTED)
    save(fig, "fig_data_layer_coverage_map")


def make_stress_atlas() -> None:
    fig = plt.figure(figsize=(STRESS_WIDTH_IN, 4.85))
    gs = fig.add_gridspec(
        2,
        6,
        height_ratios=[1.0, 1.18],
        hspace=0.62,
        wspace=0.95,
        left=0.09,
        right=0.98,
        top=0.92,
        bottom=0.08,
    )
    ax_a = fig.add_subplot(gs[0, 0:2])
    ax_b = fig.add_subplot(gs[0, 2:4])
    ax_c = fig.add_subplot(gs[0, 4:6])
    ax_d = fig.add_subplot(gs[1, 0:2])
    ax_e = fig.add_subplot(gs[1, 2:6])

    s1 = read_csv("calibration/s1_results_summary.csv")
    ax = ax_a
    panel_label(ax, "A", "TWFE vs CS")
    arms = ["zero", "homogeneous", "heterogeneous"]
    for method, color, marker, label, offset, filled in [
        ("twfe", PRIMARY, "o", "TWFE", 0.08, True),
        ("cs_att", SECONDARY, "s", "CS ATT", -0.08, False),
    ]:
        data = s1[s1["method"] == method].set_index("arm").loc[arms]
        y = np.arange(3) + offset
        ax.errorbar(
            1000 * data["bias"],
            y,
            xerr=1000 * 1.96 * data["mcse_bias"],
            fmt=marker,
            color=color,
            markerfacecolor=color if filled else WHITE,
            markersize=5.0,
            capsize=2,
            label=label,
        )
    ax.axvline(0, color=INK, linewidth=0.8)
    ax.set_yticks(range(3), ["Zero", "Homog.", "Heterog."])
    ax.set_xlabel("Bias (x 10^-3)")
    ax.set_xlim(-1.25, 1.25)
    ax.text(-1.18, 2.18, "TWFE", color=PRIMARY, fontsize=TICK_PT, fontweight="bold")
    ax.text(-1.18, 1.78, "CS", color=SECONDARY, fontsize=TICK_PT, fontweight="bold")
    clean_axes(ax, "x")

    s2 = read_csv("calibration/s2_results_summary.csv")
    ax = ax_b
    panel_label(ax, "B", "Timing")
    data = s2[
        (s2["outcome"] == "launches")
        & (s2["effect_label"] == "primary")
        & (s2["gap"] == 5)
        & (s2["arm"] == "no_anticipation")
    ].set_index("method")
    vals = [
        float(data.loc["naive_announcement", "attenuation_ratio"]),
        float(data.loc["verified_activation", "attenuation_ratio"]),
    ]
    ax.plot(vals, [0, 0], color=DIVIDER, linewidth=4.5, solid_capstyle="round")
    ax.scatter([vals[0]], [0], s=48, c=[BOUNDARY], marker="o", zorder=3)
    ax.scatter([vals[1]], [0], s=52, c=[SECONDARY], marker="D", zorder=3)
    ax.axvline(1.0, color=INK, linewidth=0.8, linestyle=":")
    ax.text(vals[0], 0.14, f"{vals[0]:.3f}", ha="center", color=BOUNDARY, fontweight="bold", fontsize=TICK_PT)
    ax.text(vals[1], 0.14, f"{vals[1]:.3f}", ha="center", color=SECONDARY, fontweight="bold", fontsize=TICK_PT)
    ax.text(vals[0], -0.15, "Announce", ha="center", color=BOUNDARY, fontsize=TICK_PT)
    ax.text(vals[1], -0.15, "Activate", ha="center", color=SECONDARY, fontsize=TICK_PT)
    gates = s2.loc[
        (s2["method"] == "activation_plus_anticipation_gate")
        & (s2["arm"].isin(["zero", "no_anticipation"]))
        & s2["gate_rejection_rate"].notna(),
        "gate_rejection_rate",
    ]
    ax.text(
        0.02,
        0.90,
        f"Gate {100 * float(gates.min()):.0f}–{100 * float(gates.max()):.0f}%",
        transform=ax.transAxes,
        fontsize=TICK_PT,
        color=MUTED,
    )
    ax.set_xlim(0.72, 1.04)
    ax.set_ylim(-0.24, 0.24)
    ax.set_yticks([])
    ax.set_xlabel("Recovered effect / truth")
    clean_axes(ax, "x")

    s3 = read_csv("calibration/s3_results_summary.csv")
    ax = ax_c
    panel_label(ax, "C", "Four clusters")
    data = s3[s3["arm"] == "zero"].set_index("method")
    methods = ["crv1_normal", "crv1_t3", "wild_sign_enum", "randomization_inference"]
    labels = ["CRV1 N", "t(3)", "Exact sign", "Rand."]
    colors = [BOUNDARY, STATUS, SECONDARY, PRIMARY]
    markers = ["o", "^", "D", "s"]
    filled = [True, True, False, False]
    values = [float(data.loc[m, "fpr"]) for m in methods]
    y = np.arange(4)
    for yy, value, color, marker, fill, lab in zip(y, values, colors, markers, filled, labels):
        ax.scatter([value], [yy], s=42, color=color, marker=marker, facecolors=color if fill else WHITE, edgecolors=color, zorder=3)
        if value > 0.04:
            ax.text(0.002, yy, lab, va="center", ha="left", fontsize=TICK_PT, color=INK)
        else:
            ax.text(value + 0.006, yy, lab, va="center", ha="left", fontsize=TICK_PT, color=INK)
    ax.axvline(0.05, color=INK, linewidth=0.8, linestyle=":")
    ax.set_yticks(y, [])
    ax.invert_yaxis()
    ax.set_xlim(-0.004, 0.09)
    ax.set_xlabel("False-positive rate")
    clean_axes(ax, "x")

    s4 = read_csv("calibration/s4_results_summary.csv")
    ax = ax_d
    panel_label(ax, "D", "Selection")
    data = s4[s4["arm"] == "positive"].sort_values("gamma")
    ax.plot(data["gamma"], data["bias_twfe"], color=BOUNDARY, marker="o", label="Static TWFE")
    ax.plot(data["gamma"], data["bias_cs"], color=PRIMARY, marker="s", markerfacecolor=WHITE, label="CS ATT")
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.set_xticks(data["gamma"], ["None", "Moderate", "Strong"])
    ax.set_xlabel("Selection severity")
    ax.set_ylabel("Bias")
    ax.set_ylim(-0.04, 0.80)
    ax.legend(loc="upper left", fontsize=TICK_PT, handlelength=1.2)
    clean_axes(ax)

    s5 = read_csv("calibration/s5_results_summary.csv")
    ax = ax_e
    panel_label(ax, "E", "Aggregation")
    data = s5[s5["arm"] == "substantive_transient"]
    methods = ["daily", "naive_weekly", "exposure_weekly", "aligned_weekly"]
    labels = ["Daily", "Naive", "Exposure", "Aligned"]
    weekdays = ["Thu", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"]
    matrix = np.full((4, 7), np.nan)
    for i, method in enumerate(methods):
        for j in range(7):
            row = data[(data["method"] == method) & (data["offset"] == j)]
            if not row.empty:
                matrix[i, j] = row.iloc[0]["effect_attenuation"]
    cmap = LinearSegmentedColormap.from_list("scholar_diverging", [BOUNDARY, WHITE, PRIMARY])
    norm = TwoSlopeNorm(vmin=0.38, vcenter=1.0, vmax=1.20)
    image = ax.imshow(matrix, cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(7), weekdays)
    ax.set_yticks(range(4), labels)
    for i in range(4):
        for j in range(7):
            value = matrix[i, j]
            rgba = image.cmap(image.norm(value))
            luminance = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=TICK_PT, color=WHITE if luminance < 0.50 else INK)
    ax.add_patch(Rectangle((-0.5, -0.5), 1.0, 4.0, fill=False, edgecolor=INK, linewidth=1.3))
    colorbar = fig.colorbar(image, ax=ax, orientation="horizontal", fraction=0.10, pad=0.18, aspect=32)
    colorbar.set_label("Recovered effect / truth", fontsize=LABEL_PT)
    colorbar.set_ticks([0.4, 0.7, 1.0, 1.2])
    colorbar.ax.tick_params(labelsize=TICK_PT)
    save(fig, "fig_stress_test_atlas")


def make_event_study() -> None:
    data = read_csv("application/event_study_coefficients.csv")
    fig, ax = plt.subplots(figsize=(PAIR_WIDTH_IN, 2.45))
    fig.subplots_adjust(left=0.22, right=0.97, top=0.82, bottom=0.21)
    pre = data[(data["rel_week"] < 0) & (data["rel_week"] != -1)]
    post = data[data["rel_week"] >= 0]
    ax.axvspan(-8.6, -0.5, color=SURFACE, zorder=0)
    ax.axvspan(-0.5, 8.6, color=LIGHT_PRIMARY, alpha=0.7, zorder=0)
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.axvline(-0.5, color=INK, linestyle="--", linewidth=0.8)
    ax.fill_between(pre["rel_week"], pre["ci95_low"], pre["ci95_high"], color=MUTED, alpha=0.18, linewidth=0)
    ax.fill_between(post["rel_week"], post["ci95_low"], post["ci95_high"], color=PRIMARY, alpha=0.16, linewidth=0)
    ax.errorbar(
        pre["rel_week"],
        pre["coef"],
        yerr=[pre["coef"] - pre["ci95_low"], pre["ci95_high"] - pre["coef"]],
        fmt="o",
        color=MUTED,
        markersize=4.2,
        capsize=1.6,
        label="Pre",
        zorder=3,
    )
    ax.errorbar(
        post["rel_week"],
        post["coef"],
        yerr=[post["coef"] - post["ci95_low"], post["ci95_high"] - post["coef"]],
        fmt="s",
        color=PRIMARY,
        markersize=4.2,
        capsize=1.6,
        label="Post",
        zorder=3,
    )
    flagged = pre[(pre["ci95_low"] > 0) | (pre["ci95_high"] < 0)]
    ax.scatter(
        flagged["rel_week"],
        flagged["coef"],
        s=64,
        facecolors="none",
        edgecolors=BOUNDARY,
        linewidths=1.3,
        zorder=4,
        label="Pretrend",
    )
    ax.set_xlim(-8.8, 8.8)
    ax.set_ylim(-1.4, 2.75)
    ax.set_xticks([-8, -4, 0, 4, 8])
    ax.set_xlabel("Weeks relative to PumpSwap launch")
    ax.set_ylabel("Coef. on log(1+volume)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.24), ncol=3, fontsize=TICK_PT, handlelength=1.1, columnspacing=0.7, handletextpad=0.3)
    clean_axes(ax)
    save(fig, "fig_event_study")


def make_ladder() -> None:
    data = read_csv("application/deterministic_ladder.csv").set_index("rung")
    rungs = ["L0", "L1", "L2", "L4", "L6"]
    estimates = np.array([float(data.loc[r, "estimate"]) for r in rungs])
    low = np.array([float(data.loc[r, "ci95_low"]) for r in rungs])
    high = np.array([float(data.loc[r, "ci95_high"]) for r in rungs])
    decisions = [DECISION_LABEL[str(data.loc[r, "worked_decision"])] for r in rungs]
    x = np.arange(len(rungs))
    fig, ax = plt.subplots(figsize=(PAIR_WIDTH_IN, 2.35))
    fig.subplots_adjust(left=0.22, right=0.97, top=0.96, bottom=0.28)
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.errorbar(
        x,
        estimates,
        yerr=[estimates - low, high - estimates],
        fmt="none",
        ecolor=PRIMARY,
        capsize=2.5,
        linewidth=1.2,
        zorder=2,
    )
    short = {"affirmative": "aff.", "uncertain": "unc.", "pretrend risk": "pretrend"}
    for xx, yy, decision in zip(x, estimates, decisions):
        color = DECISION_COLOR[decision]
        filled = decision == "affirmative"
        ax.scatter(
            [xx],
            [yy],
            s=36,
            color=color,
            marker="o" if filled else "D",
            facecolors=color if filled else WHITE,
            edgecolors=color,
            linewidths=1.2,
            zorder=3,
        )
        ax.text(xx, -1.48, short[decision], ha="center", va="top", fontsize=TICK_PT, color=color, fontweight="bold")
    ax.set_xticks(x, rungs)
    ax.set_ylabel("Estimate on log(1+volume)")
    ax.set_xlim(-0.45, 4.45)
    ax.set_ylim(-1.78, 1.55)
    clean_axes(ax)
    save(fig, "fig_ladder_decision_flip")


def _metric_percent(row: pd.Series, key: str) -> float:
    match = re.search(rf"{re.escape(key)} ([0-9.]+)%", str(row["value_label"]))
    if not match:
        raise ValueError(f"Could not parse {key!r} from {row['value_label']!r}")
    return float(match.group(1))


def make_metric_battery() -> None:
    table = read_csv("application/result1_stakeholder_metric_battery.csv").set_index("metric")
    sol = load_json("release/solana_core.json")
    timeout_n = int(sol["raw_reproduction"]["timeout_tokens"])
    timeout_d = int(sol["raw_reproduction"]["deduplicated_terminal_outcomes"])
    specs = [
        (
            "Timeout",
            100 * timeout_n / timeout_d,
            "%",
            f"{timeout_n:,}/{timeout_d:,}",
            BOUNDARY,
        ),
        (
            "High concentration",
            _metric_percent(table.loc["Holder concentration snapshot"], "high-conc rate"),
            "%",
            "holder snapshot",
            STATUS,
        ),
        (
            "Risk premium",
            100 * float(table.loc["Risk premium of high-concentration tokens", "value"]),
            " pp",
            "retail traders",
            BOUNDARY,
        ),
        (
            "Active snapshot",
            100 * float(table.loc["Token market-activity persistence proxy", "value"]),
            "%",
            "latest snapshot",
            PRIMARY,
        ),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(PAIR_WIDTH_IN, METRIC_MAX_HEIGHT_IN - 0.02))
    fig.subplots_adjust(left=0.03, right=0.99, top=0.96, bottom=0.04, wspace=0.08, hspace=0.12)
    for ax, (title, value, unit, note, color) in zip(axes.ravel(), specs):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.add_patch(Rectangle((0.05, 0.08), 0.90, 0.84, facecolor=SURFACE, edgecolor=DIVIDER, linewidth=0.7))
        ax.text(0.5, 0.78, title, ha="center", va="top", fontsize=TICK_PT, color=MUTED)
        ax.text(0.5, 0.48, f"{value:.1f}{unit}", ha="center", va="center", fontsize=10.0, fontweight="bold", color=color)
        ax.text(0.5, 0.20, note, ha="center", va="center", fontsize=TICK_PT, color=INK)
    save(fig, "fig_metric_battery_status")


def make_frequency() -> None:
    data = read_csv("application/result1_frequency_sensitivity.csv").set_index("layer")
    rows = data.loc[["market_daily_twfe", "market_weekly_twfe"]]
    values = rows["estimate"].to_numpy(float)
    low = rows["ci95_low"].to_numpy(float)
    high = rows["ci95_high"].to_numpy(float)
    fig, ax = plt.subplots(figsize=(PAIR_WIDTH_IN, METRIC_MAX_HEIGHT_IN - 0.02))
    fig.subplots_adjust(left=0.34, right=0.97, top=0.92, bottom=0.38)
    y = np.array([1, 0])
    colors = [PRIMARY, STATUS]
    markers = ["o", "s"]
    filled = [True, False]
    for value, lo, hi, yy, color, marker, fill in zip(values, low, high, y, colors, markers, filled):
        ax.plot([lo, hi], [yy, yy], color=color, linewidth=1.6, solid_capstyle="round")
        ax.scatter(
            [value],
            [yy],
            s=42,
            marker=marker,
            color=color,
            facecolors=color if fill else WHITE,
            edgecolors=color,
            zorder=3,
        )
        ax.text(value, yy + 0.22, f"{value:+.3f}", ha="center", fontsize=TICK_PT, fontweight="bold", color=color)
    ax.axvline(0, color=INK, linewidth=0.8)
    ax.set_yticks(y, ["Daily\nprotocol", "Weekly\nprotocol"])
    ax.set_xlabel("log(1+volume) estimate, 95% CI")
    ax.set_xlim(-0.35, 1.62)
    ax.set_ylim(-0.45, 1.55)
    clean_axes(ax, "x")
    save(fig, "fig_frequency_sensitivity")


def make_mechanism() -> None:
    data = load_json("application/h1_rpc_mechanism_summary.json")
    values = [
        int(data["full_30d_observed_active_tokens"]) / int(data["post_30d_tokens"]),
        float(data["complete_30d_active_share"]),
    ]
    counts = [
        f"{int(data['full_30d_observed_active_tokens']):,}/{int(data['post_30d_tokens']):,}",
        f"{int(data['complete_30d_active_tokens']):,}/{int(data['complete_30d_tokens']):,}",
    ]
    fig, ax = plt.subplots(figsize=(PAIR_WIDTH_IN, APPENDIX_MAX_HEIGHT_IN - 0.02))
    fig.subplots_adjust(left=0.38, right=0.99, top=0.92, bottom=0.32)
    y = [1, 0]
    ax.barh(y, values, color=[PRIMARY, SECONDARY], height=0.46, hatch=["", "//"])
    for yy, value, count in zip(y, values, counts):
        ax.text(1.03, yy, f"{100 * value:.1f}%\n({count})", va="center", ha="left", fontsize=TICK_PT, fontweight="bold", color=INK)
    ax.set_xlim(0, 1.78)
    ax.set_yticks(y, ["30-day observed\nactivity", "Complete-window\nactivity"])
    ax.set_xlabel("Share of graduated tokens")
    clean_axes(ax, "x")
    save(fig, "fig_h1_mechanism_audit")


def make_agentic() -> None:
    data = read_csv("application/agentic_arm_scores.csv")
    x = np.arange(len(data))
    fig, ax = plt.subplots(figsize=(PAIR_WIDTH_IN, APPENDIX_MAX_HEIGHT_IN - 0.02))
    fig.subplots_adjust(left=0.18, right=0.98, top=0.78, bottom=0.32)
    ax.plot(x, data["calibration_gap"].abs(), color=PRIMARY, marker="o", markersize=4.4, label="Calibration gap")
    ax.plot(
        x,
        data["method_omission_rate"],
        color=STATUS,
        marker="s",
        markersize=4.4,
        markerfacecolor=WHITE,
        linestyle="--",
        label="Omission rate",
    )
    ax.set_xticks(x, data["rung"])
    ax.set_ylim(0, 0.92)
    ax.set_ylabel("Score")
    ax.set_xlabel("Evidence ladder rung")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.34), ncol=2, fontsize=TICK_PT, handlelength=1.5, columnspacing=0.9)
    clean_axes(ax)
    save(fig, "fig_agentic_scaffold_tradeoff")


def main() -> None:
    apply_theme()
    OUT.mkdir(parents=True, exist_ok=True)
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
