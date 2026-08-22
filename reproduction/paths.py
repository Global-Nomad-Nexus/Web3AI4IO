"""Canonical paths for the Role B reproducibility package."""

from __future__ import annotations

from pathlib import Path

REPRO = Path(__file__).resolve().parent
REPO = REPRO.parent
WORKSPACE = REPO.parent
PAPER = REPO / "paper" if (REPO / "paper").exists() else WORKSPACE / "paper"
ARCHIVED = REPRO / "archived"
GENERATED = REPRO / "generated"
CHECKSUMS = REPRO / "checksums.sha256"
MANIFEST = REPRO / "artifact_manifest.csv"
