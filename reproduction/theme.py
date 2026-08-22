"""Shared visual system for every empirical chart and diagram."""

from __future__ import annotations

import matplotlib as mpl

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

CHAIN_COLORS = {
    "solana": BLUE,
    "base": TEAL,
    "bnb": AMBER,
    "tron": PURPLE,
}

EVIDENCE_COLORS = {
    "observed": TEAL,
    "bounded": AMBER,
    "uncollected": "#9AA4B2",
    "excluded": "white",
    "accepted": GREEN,
    "conditional": AMBER,
    "rejected": "#9AA4B2",
    "supported": GREEN,
    "not_identified": RED,
    "predictive": AMBER,
}

STAKEHOLDER_COLORS = {
    "creators": TEAL,
    "traders": BLUE,
    "platform": PURPLE,
    "community": AMBER,
    "host": INK,
}

PLATFORM_COLORS = {
    "pump.fun": BLUE,
    "pumpswap": TEAL,
    "clanker": GREEN,
    "four.meme": AMBER,
    "sunpump": PURPLE,
    "raydium": "#4C78A8",
    "orca": "#F58518",
    "meteora": "#54A24B",
}


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
