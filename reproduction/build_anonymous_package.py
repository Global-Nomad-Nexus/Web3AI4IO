"""Build an identity-stripped, self-contained review mirror and backup ZIP."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO.parent
PRIVATE_PAPER = Path(os.environ.get("WEB3AI4IO_PAPER_DIR", WORKSPACE / "paper")).expanduser().resolve()
DIST = REPO / "dist"
OUTPUT = DIST / "anonymous-review"
ZIP_PATH = DIST / "web3ai4io-anonymous-review.zip"

ROOT_FILES = [
    ".gitignore",
    "DATA_CARD.md",
    "Makefile",
    "README.md",
    "REPRODUCIBILITY.md",
    "pyproject.toml",
    "uv.lock",
]

PAPER_FILES = [
    "neurips_2026.tex",
    "neurips_2026.sty",
    "preamble.tex",
    "references.bib",
]

TEXT_NAMES = {"Makefile"}
TEXT_SUFFIXES = {
    ".bib",
    ".cfg",
    ".csv",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".sty",
    ".tex",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

REPLACEMENTS = [
    ("https://github.com/Global-Nomad-Nexus/Web3AI4IO", "https://anonymous.invalid/Web3AI4IO"),
    ("fig_shilin_application_appendix", "fig_application_appendix"),
    ("web3io_claire", "web3io_identification"),
    ("Web3ioClaire", "Web3ioIdentification"),
    ("_shilin", "_application"),
    ("_claire", "_identification"),
    ("Shilin", "application"),
    ("Claire", "identification"),
    ("shilin", "application"),
    ("claire", "identification"),
]

FORBIDDEN_TEXT = [
    re.compile(r"oushilin", re.I),
    re.compile(r"michelangelo", re.I),
    re.compile(r"yutian\.wang", re.I),
    re.compile(r"shilin\.ou", re.I),
    re.compile(r"luyao\.zhang", re.I),
    re.compile(r"dukekunshan", re.I),
    re.compile(r"sunshineluyao", re.I),
    re.compile(r"Global-Nomad-Nexus", re.I),
    re.compile(r"/Users/[A-Za-z0-9._-]+"),
    re.compile(r"/home/[A-Za-z0-9._-]+"),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"hf_[A-Za-z0-9]{10,}"),
]

SKIP_TRACKED_PARTS = {
    ".git",
    ".github",
    ".venv",
    "R",
    "__pycache__",
    "huggingface",
    "node_modules",
}

AGENTIC_V2_SOURCE_FILES = [
    "application/configs/agentic_v2.json",
    "application/configs/agentic_v2_gold.json",
    "application/scripts/configure_agentic_v2_keychain.py",
    "application/scripts/run_agentic_v2.py",
    "application/scripts/run_agentic_v2_all.py",
    "application/scripts/score_agentic_v2.py",
    "application/scripts/verify_agentic_v2.py",
    "application/scripts/reanalyze_agentic_v2_matched.py",
    "application/configs/telegram_replication.json",
    "application/configs/telegram_replication_gold.json",
    "application/scripts/run_telegram_replication.py",
    "application/scripts/score_telegram_replication.py",
    "application/scripts/verify_telegram_replication.py",
    "application/src/trustworthy_launchpads/agentic_v2.py",
    "application/src/trustworthy_launchpads/agentic_v2_providers.py",
    "application/src/trustworthy_launchpads/agentic_v2_scoring.py",
    "application/src/trustworthy_launchpads/telegram_replication.py",
    "application/tests/test_agentic_v2.py",
    "application/tests/test_telegram_replication.py",
]


def safe_reset_output() -> None:
    if OUTPUT.parent != DIST or OUTPUT.name != "anonymous-review":
        raise RuntimeError(f"refusing unsafe output path: {OUTPUT}")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()


def copy_path(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(
            src,
            dest,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                ".DS_Store",
                ".mplconfig",
                "__pycache__",
                "*.pyc",
                "ANONYMITY.md",
                "build_anonymous_package.py",
            ),
        )
    else:
        shutil.copy2(src, dest)


def tracked_files(prefix: str) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", prefix],
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    return [REPO / item.decode() for item in result.stdout.split(b"\0") if item]


def package_relative(path: Path) -> Path:
    return path.relative_to(REPO)


def redact_name(name: str) -> str:
    return (
        name.replace("fig_shilin_application_appendix", "fig_application_appendix")
        .replace("SHILIN", "APPLICATION")
        .replace("Shilin", "application")
        .replace("shilin", "application")
        .replace("CLAIRE", "IDENTIFICATION")
        .replace("Claire", "identification")
        .replace("claire", "identification")
    )


def redact_filenames() -> None:
    files = sorted((path for path in OUTPUT.rglob("*") if path.is_file()), key=lambda path: len(path.parts), reverse=True)
    for path in files:
        new_name = redact_name(path.name)
        if new_name != path.name:
            path.rename(path.with_name(new_name))


def should_copy_tracked(path: Path) -> bool:
    rel = path.relative_to(REPO)
    if any(part in SKIP_TRACKED_PARTS for part in rel.parts):
        return False
    if path.name in {"CITATION.cff", ".DS_Store"}:
        return False
    return True


def transform_text(path: Path) -> None:
    if path.name == "identity_audit.py":
        return
    if path.name not in TEXT_NAMES and path.suffix.lower() not in TEXT_SUFFIXES:
        return
    text = path.read_text(encoding="utf-8", errors="strict")
    text = re.sub(r"/Users/[^/\s\"']+", "<local-home>", text)
    text = re.sub(r"/home/[^/\s\"']+", "<local-home>", text)
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def audit_tree() -> None:
    hits: list[str] = []
    for path in OUTPUT.rglob("*"):
        if not path.is_file():
            continue
        rel_lower = str(path.relative_to(OUTPUT)).lower()
        if "shilin" in rel_lower or "claire" in rel_lower:
            hits.append(f"identifying path: {path.relative_to(OUTPUT)}")
        if path.name == "identity_audit.py":
            continue
        if path.name not in TEXT_NAMES and path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_TEXT:
            if pattern.search(text):
                hits.append(f"{path.relative_to(OUTPUT)} matches /{pattern.pattern}/")
                break
    if hits:
        raise RuntimeError("anonymous package audit failed:\n" + "\n".join(hits))


def write_package_manifest() -> None:
    lines: list[str] = []
    for path in sorted(OUTPUT.rglob("*")):
        if path.is_file() and path.name != "PACKAGE_MANIFEST.sha256":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  {path.relative_to(OUTPUT)}")
    (OUTPUT / "PACKAGE_MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def refresh_reproduction_checksums() -> None:
    """Re-hash review files after identity-only text substitutions."""
    checksum_path = OUTPUT / "reproduction" / "checksums.sha256"
    if not checksum_path.exists():
        return
    lines: list[str] = []
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        _, rel = line.split("  ", 1)
        target = checksum_path.parent / rel
        if not target.exists():
            raise RuntimeError(f"anonymous checksum target missing: {rel}")
        lines.append(f"{hashlib.sha256(target.read_bytes()).hexdigest()}  {rel}")
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_zip() -> None:
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(OUTPUT.rglob("*")):
            if path.is_file():
                archive.write(path, Path(OUTPUT.name) / path.relative_to(OUTPUT))


def main() -> None:
    safe_reset_output()
    for name in ROOT_FILES:
        copy_path(REPO / name, OUTPUT / name)
    copy_path(REPO / "reproduction", OUTPUT / "reproduction")
    for name in PAPER_FILES:
        copy_path(PRIVATE_PAPER / name, OUTPUT / "paper" / name)
    copy_path(PRIVATE_PAPER / "figs", OUTPUT / "paper" / "figs")
    copy_path(PRIVATE_PAPER / "tabs", OUTPUT / "paper" / "tabs")

    for prefix in ("identification", "application", "dataset"):
        for src in tracked_files(prefix):
            if not should_copy_tracked(src):
                continue
            copy_path(src, OUTPUT / package_relative(src))

    # The frozen V2 audit was added after the last repository commit. Include its
    # source explicitly so the anonymous mirror remains complete before staging.
    for rel in AGENTIC_V2_SOURCE_FILES:
        src = REPO / rel
        if src.exists():
            copy_path(src, OUTPUT / rel)

    redact_filenames()
    for path in OUTPUT.rglob("*"):
        if path.is_file():
            transform_text(path)
    refresh_reproduction_checksums()
    audit_tree()
    write_package_manifest()
    write_zip()
    print(f"built {OUTPUT}")
    print(f"built {ZIP_PATH}")


if __name__ == "__main__":
    main()
