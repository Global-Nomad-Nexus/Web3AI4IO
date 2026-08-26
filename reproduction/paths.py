"""Canonical paths for the paper reproduction package."""

from __future__ import annotations

import os
from pathlib import Path

REPRO = Path(__file__).resolve().parent
REPO = REPRO.parent
WORKSPACE = REPO.parent
_paper_override = os.environ.get("WEB3AI4IO_PAPER_DIR")
PAPER = (
    Path(_paper_override).expanduser().resolve()
    if _paper_override
    else (REPO / "paper" if (REPO / "paper").exists() else WORKSPACE / "paper")
)
ARCHIVED = REPRO / "archived"
GENERATED = REPRO / "generated"
CHECKSUMS = REPRO / "checksums.sha256"
MANIFEST = REPRO / "artifact_manifest.csv"
