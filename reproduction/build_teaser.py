"""Build the standalone LaTeX/TikZ teaser from canonical scope metadata."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from paths import GENERATED, PAPER, REPRO


FIGURE_SOURCE = REPRO / "figures" / "teaser_figure.tex"
BUILD_DIR = REPRO / "build" / "teaser"
COUNT_MACROS = GENERATED / "teaser_counts.tex"
OUTPUT_DIR = PAPER / "figs"


def tex_number(value: int) -> str:
    """Format an integer with nonbreaking TeX thousands separators."""
    return f"{value:,}".replace(",", "{,}")


def write_count_macros() -> None:
    scope = json.loads((REPRO / "scope.json").read_text(encoding="utf-8"))
    by_chain = {row["chain"]: row for row in scope["chains"]}
    required = ("Solana", "Base", "BNB", "TRON")
    missing = [chain for chain in required if chain not in by_chain]
    if missing:
        raise ValueError(f"scope.json is missing teaser chains: {missing}")

    names = {"Solana": "Solana", "Base": "Base", "BNB": "BNB", "TRON": "Tron"}
    lines = ["% Generated from reproduction/scope.json. Do not edit by hand."]
    for chain in required:
        row = by_chain[chain]
        prefix = names[chain]
        lines.extend(
            [
                rf"\newcommand{{\{prefix}Core}}{{{tex_number(int(row['core_units']))}}}",
                rf"\newcommand{{\{prefix}Lifecycle}}{{{tex_number(int(row['lifecycle_units']))}}}",
            ]
        )
    GENERATED.mkdir(parents=True, exist_ok=True)
    COUNT_MACROS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def build_teaser() -> None:
    write_count_macros()
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    run(
        [
            "latexmk",
            "-pdf",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-outdir={BUILD_DIR}",
            FIGURE_SOURCE.name,
        ],
        cwd=FIGURE_SOURCE.parent,
    )

    built_pdf = BUILD_DIR / "teaser_figure.pdf"
    output_pdf = OUTPUT_DIR / "teaser_figure.pdf"
    output_svg = OUTPUT_DIR / "teaser_figure.svg"
    output_png_stem = OUTPUT_DIR / "teaser_figure"
    shutil.copy2(built_pdf, output_pdf)
    run(["pdftocairo", "-svg", str(output_pdf), str(output_svg)])
    run(
        [
            "pdftocairo",
            "-png",
            "-singlefile",
            "-r",
            "300",
            str(output_pdf),
            str(output_png_stem),
        ]
    )
    print("wrote teaser_figure (LaTeX/TikZ PDF, SVG, PNG)")


if __name__ == "__main__":
    build_teaser()
