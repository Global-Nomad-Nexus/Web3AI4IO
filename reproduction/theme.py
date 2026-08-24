"""Scholar Blue 1.1.0 visual system for every paper figure."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
from matplotlib import font_manager
from matplotlib.text import Text

THEME_NAME = "Scholar Blue"
THEME_VERSION = "1.1.0"
FONT_FAMILY = "Arial"

INK = "#18324A"
SURFACE = "#F5F7FB"
PRIMARY = "#184D77"
SECONDARY = "#128078"
STATUS = "#D48448"
BOUNDARY = "#C2413A"
DIVIDER = "#CBD5E1"
MUTED = "#526577"
WHITE = "#FFFFFF"

LIGHT_PRIMARY = "#E6EEF4"
LIGHT_SECONDARY = "#E3F1EF"
LIGHT_STATUS = "#F8EBDD"
LIGHT_BOUNDARY = "#F7E5E3"

# NeurIPS 2026 workshop geometry from paper/neurips_2026.sty.
PAPER_TEXTWIDTH_IN = 5.5
PAPER_TEXTHEIGHT_IN = 9.0
FULL_WIDTH_IN = PAPER_TEXTWIDTH_IN
COVERAGE_WIDTH_IN = 0.84 * PAPER_TEXTWIDTH_IN
STRESS_WIDTH_IN = 0.98 * PAPER_TEXTWIDTH_IN
PAIR_WIDTH_IN = 0.49 * PAPER_TEXTWIDTH_IN
METRIC_MAX_HEIGHT_IN = 0.15 * PAPER_TEXTHEIGHT_IN
APPENDIX_MAX_HEIGHT_IN = 0.16 * PAPER_TEXTHEIGHT_IN

TICK_PT = 8.0
LEGEND_PT = 8.0
LABEL_PT = 9.0
PANEL_PT = 10.5
MINIMUM_PT = 8.0
PNG_DPI = 300

ARIAL_REGULAR = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
ARIAL_BOLD = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
ARIAL_ITALIC = Path("/System/Library/Fonts/Supplemental/Arial Italic.ttf")
ARIAL_BOLD_ITALIC = Path("/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf")


def register_arial() -> None:
    """Register the macOS Arial family so PDF export can embed TrueType fonts."""
    missing = [path for path in (ARIAL_REGULAR, ARIAL_BOLD) if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Arial is required for paper figures but was not found: "
            + ", ".join(str(path) for path in missing)
        )
    for path in (ARIAL_REGULAR, ARIAL_BOLD, ARIAL_ITALIC, ARIAL_BOLD_ITALIC):
        if path.exists():
            font_manager.fontManager.addfont(str(path))


def apply_theme() -> None:
    register_arial()
    mpl.rcParams.update(
        {
            "font.family": FONT_FAMILY,
            "font.sans-serif": [FONT_FAMILY],
            "font.size": TICK_PT,
            "axes.titlesize": PANEL_PT,
            "axes.labelsize": LABEL_PT,
            "xtick.labelsize": TICK_PT,
            "ytick.labelsize": TICK_PT,
            "legend.fontsize": LEGEND_PT,
            "axes.edgecolor": INK,
            "axes.labelcolor": INK,
            "text.color": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "axes.linewidth": 0.8,
            "lines.linewidth": 1.6,
            "grid.color": DIVIDER,
            "grid.linewidth": 0.55,
            "grid.alpha": 0.65,
            "legend.frameon": False,
            "figure.facecolor": WHITE,
            "axes.facecolor": WHITE,
            "savefig.facecolor": WHITE,
            "savefig.edgecolor": WHITE,
            "savefig.bbox": None,
            "savefig.pad_inches": 0.02,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "pdf.use14corefonts": False,
        }
    )


def clean_axes(ax, grid_axis: str = "y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if grid_axis:
        ax.grid(axis=grid_axis, color=DIVIDER, linewidth=0.55, alpha=0.65)
        other = "x" if grid_axis == "y" else "y"
        ax.grid(False, axis=other)
    else:
        ax.grid(False)
    ax.set_axisbelow(True)


def panel_label(ax, letter: str, title: str = "") -> None:
    """Place a bold uppercase panel letter, with an optional short title."""
    label = letter if not title else f"{letter}  {title}"
    ax.set_title(label, loc="left", fontsize=PANEL_PT, fontweight="bold", pad=4, color=INK)


def assert_legibility(fig, minimum_pt: float = MINIMUM_PT) -> None:
    violations: list[str] = []
    for item in fig.findobj(match=lambda artist: isinstance(artist, Text)):
        if not item.get_visible() or not str(item.get_text()).strip():
            continue
        size = float(item.get_fontsize())
        if size + 1e-9 < minimum_pt:
            snippet = str(item.get_text()).replace("\n", " ")[:48]
            violations.append(f"{size:g} pt: {snippet!r}")
    if violations:
        raise ValueError("Final-size legibility gate failed: " + "; ".join(violations))


def export_figure(fig, output_dir: Path, stem: str) -> None:
    """Write PDF, SVG, and 300 dpi PNG at the figure's designed size."""
    assert_legibility(fig)
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_dir / f"{stem}.pdf")
    fig.savefig(output_dir / f"{stem}.svg")
    fig.savefig(output_dir / f"{stem}.png", dpi=PNG_DPI)
