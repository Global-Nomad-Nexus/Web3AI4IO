"""Scan the anonymous review surfaces for identity leaks."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import ARCHIVED, GENERATED, PAPER, REPO

FORBIDDEN = [
    re.compile(r"oushilin", re.I),
    re.compile(r"michelangelo", re.I),
    re.compile(r"yutian\.wang", re.I),
    re.compile(r"shilin\.ou", re.I),
    re.compile(r"luyao\.zhang", re.I),
    re.compile(r"dukekunshan", re.I),
    re.compile(r"sunshineluyao", re.I),
    re.compile(r"/Users/[A-Za-z0-9._-]+"),
    re.compile(r"kl41r3"),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"hf_[A-Za-z0-9]{10,}"),
]

SKIP_DIR_NAMES = {".git", ".venv", "__pycache__", "R", "library", "node_modules"}
SKIP_SUFFIXES = {
    ".png",
    ".pdf",
    ".parquet",
    ".npz",
    ".bin",
    ".jpg",
    ".aux",
    ".log",
    ".fls",
    ".fdb_latexmk",
    ".out",
    ".bbl",
    ".blg",
    ".synctex.gz",
}
SKIP_NAMES = {"identity_audit.py"}
REVIEW_ROOTS = [PAPER, ARCHIVED, GENERATED, REPO / "reproduction"]


def iter_files(root: Path):
    if not root.exists():
        return
    for path in root.rglob("*"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.name in SKIP_NAMES:
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield path


def main() -> int:
    hits: list[str] = []
    for root in REVIEW_ROOTS:
        for path in iter_files(root):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pattern in FORBIDDEN:
                if pattern.search(text):
                    rel = path
                    hits.append(f"{rel}: matches /{pattern.pattern}/")
                    break
    if hits:
        print("IDENTITY AUDIT FAILED")
        for hit in hits:
            print(f"  - {hit}")
        return 1
    print("IDENTITY AUDIT PASSED for paper/, reproduction/archived/, and generated tables.")
    print("Working-tree directory names Claire/ and Shilin/ remain in the private repository and must be renamed in the anonymous mirror.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
