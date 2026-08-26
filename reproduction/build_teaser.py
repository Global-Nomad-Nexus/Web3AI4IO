"""Export the original teaser SVG as a cropped, A4-width vector PDF."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

from paths import PAPER, REPRO


ORIGINAL_SVG = REPRO / "figures" / "teaser_figure_original.svg"
PRINT_SOURCE = REPRO / "figures" / "teaser_figure_print.html"
CHROME_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/chromium"),
    Path("/usr/bin/chromium-browser"),
)


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def find_chrome() -> Path:
    configured = os.environ.get("CHROME_BIN")
    candidates = ((Path(configured),) if configured else ()) + CHROME_CANDIDATES
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    for name in ("google-chrome", "chromium", "chromium-browser"):
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved)
    raise FileNotFoundError("Chrome/Chromium is required for vector SVG-to-PDF export; set CHROME_BIN")


def render_vector_pdf(output_pdf: Path) -> None:
    if not ORIGINAL_SVG.exists() or not PRINT_SOURCE.exists():
        raise FileNotFoundError("Original SVG and print HTML are required")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            str(find_chrome()),
            "--headless=new",
            "--disable-gpu",
            "--allow-file-access-from-files",
            "--no-pdf-header-footer",
            f"--print-to-pdf={output_pdf}",
            PRINT_SOURCE.resolve().as_uri(),
        ]
    )


def export_previews(vector_pdf: Path, output_dir: Path) -> None:
    shutil.copy2(ORIGINAL_SVG, output_dir / "teaser_figure.svg")
    shutil.copy2(ORIGINAL_SVG, output_dir / "teaser_figure_a4.svg")
    run(
        [
            "pdftocairo",
            "-png",
            "-singlefile",
            "-r",
            "300",
            str(vector_pdf),
            str(output_dir / "teaser_figure"),
        ]
    )
    shutil.copy2(output_dir / "teaser_figure.png", output_dir / "teaser_figure_a4.png")


def verify_cropped_a4_width(path: Path) -> None:
    result = subprocess.run(["pdfinfo", str(path)], check=True, capture_output=True, text=True)
    match = re.search(r"Page size:\s+([0-9.]+) x ([0-9.]+) pts", result.stdout)
    if not match:
        raise RuntimeError(f"Could not verify PDF page size: {path}")
    width, height = map(float, match.groups())
    if abs(width - 841.89) > 2 or abs(height - 430.08) > 2:
        raise RuntimeError(f"Expected cropped A4-width canvas, found {width:.2f} x {height:.2f} pt")

    image_rows = subprocess.run(
        ["pdfimages", "-list", str(path)], check=True, capture_output=True, text=True
    ).stdout.splitlines()[2:]
    if len(image_rows) > 2:
        raise RuntimeError("Vector check failed: the PDF contains unexpected raster image regions")
    fonts = subprocess.run(
        ["pdffonts", str(path)], check=True, capture_output=True, text=True
    ).stdout.splitlines()[2:]
    extracted = subprocess.run(
        ["pdftotext", str(path), "-"], check=True, capture_output=True, text=True
    ).stdout
    if not fonts or "Evidence infrastructure" not in extracted:
        raise RuntimeError("Vector check failed: searchable text or embedded fonts are missing")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paper-dir",
        type=Path,
        default=PAPER,
        help="Manuscript directory that contains figs/",
    )
    return parser.parse_args()


def build_teaser(paper_dir: Path = PAPER) -> None:
    output_dir = paper_dir.resolve() / "figs"
    output_dir.mkdir(parents=True, exist_ok=True)
    manuscript_pdf = output_dir / "teaser_figure.pdf"
    render_vector_pdf(manuscript_pdf)
    verify_cropped_a4_width(manuscript_pdf)
    shutil.copy2(manuscript_pdf, output_dir / "teaser_figure_a4.pdf")
    export_previews(manuscript_pdf, output_dir)
    print(f"wrote cropped A4-width vector teaser exports to {output_dir}")


if __name__ == "__main__":
    build_teaser(parse_args().paper_dir)
