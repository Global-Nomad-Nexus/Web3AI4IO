#!/usr/bin/env python3
"""Download no-key public data extensions used by Shilin's application arm."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.free_public import scan_free_public_assets
from trustworthy_launchpads.io import load_config, write_json


DOWNLOADS = {
    "solarchive": [
        (
            "https://huggingface.co/datasets/solarchive/solarchive/resolve/main/index.json",
            "solarchive/index.json",
        ),
        (
            "https://huggingface.co/datasets/solarchive/solarchive/resolve/main/tokens/index.json",
            "solarchive/tokens_index.json",
        ),
        (
            "https://huggingface.co/datasets/solarchive/solarchive/resolve/main/txs/index.json",
            "solarchive/txs_index.json",
        ),
        (
            "https://huggingface.co/datasets/solarchive/solarchive/resolve/main/schemas/transactions.json",
            "solarchive/transactions_schema.json",
        ),
        (
            "https://huggingface.co/datasets/solarchive/solarchive/resolve/main/schemas/tokens.json",
            "solarchive/tokens_schema.json",
        ),
        (
            "https://huggingface.co/datasets/solarchive/solarchive/resolve/main/tokens/2025-03/000000000000.parquet",
            "solarchive/tokens/solarchive_tokens_2025-03.parquet",
        ),
        (
            "https://huggingface.co/datasets/solarchive/solarchive/resolve/main/tokens/2025-12/000000000000.parquet",
            "solarchive/tokens/solarchive_tokens_2025-12.parquet",
        ),
    ],
    "red_cohort": [
        (
            "https://zenodo.org/records/20978742/files/RED-COHORT-2026-v1.zip?download=1",
            "red_cohort/RED-COHORT-2026-v1.zip",
        )
    ],
    "hf_meme": [
        (
            "https://huggingface.co/datasets/muhammetakkurt/pump-fun-meme-token-dataset/resolve/main/pump_fun_memetoken_dataset.csv",
            "huggingface/pump_fun_meme_token_dataset.csv",
        )
    ],
}


def _download(url: str, destination: Path, *, overwrite: bool = False) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0 and not overwrite:
        return {"url": url, "path": str(destination), "status": "already_present", "bytes": destination.stat().st_size}
    with tempfile.NamedTemporaryFile(delete=False, dir=str(destination.parent)) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with urllib.request.urlopen(url, timeout=120) as response, tmp_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        tmp_path.replace(destination)
        return {"url": url, "path": str(destination), "status": "downloaded", "bytes": destination.stat().st_size}
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _extract_red_cohort(root: Path) -> dict[str, object]:
    zip_path = root / "red_cohort" / "RED-COHORT-2026-v1.zip"
    extracted_root = root / "red_cohort" / "extracted"
    if not zip_path.exists():
        return {"status": "zip_missing", "path": str(zip_path)}
    extracted_root.mkdir(parents=True, exist_ok=True)
    extracted_files = []
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                target = (extracted_root / info.filename).resolve()
                if not str(target).startswith(str(extracted_root.resolve())):
                    raise ValueError(f"Unsafe path inside RED-COHORT zip: {info.filename}")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                extracted_files.append(str(target.relative_to(root)))
    except zipfile.BadZipFile as exc:
        return {"status": "invalid_zip", "path": str(zip_path), "error": str(exc)}
    return {"status": "extracted", "path": str(extracted_root), "files": extracted_files}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs" / "pumpswap_case.json"))
    parser.add_argument(
        "--include",
        nargs="+",
        choices=["all", "solarchive", "red_cohort", "hf_meme"],
        default=["solarchive", "red_cohort", "hf_meme"],
        help="Free public sources to download. Defaults to all current no-key sources.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Re-download files that already exist.")
    parser.add_argument("--no-extract", action="store_true", help="Do not extract the RED-COHORT zip.")
    args = parser.parse_args()

    config = load_config(args.config)
    root = config.project_root / "data_sources" / "free_public"
    selected = set(DOWNLOADS) if "all" in args.include else set(args.include)

    records = []
    for group in ["solarchive", "red_cohort", "hf_meme"]:
        if group not in selected:
            continue
        for url, relative_path in DOWNLOADS[group]:
            records.append(_download(url, root / relative_path, overwrite=args.overwrite))

    extraction = {"status": "not_requested"}
    if "red_cohort" in selected and not args.no_extract:
        extraction = _extract_red_cohort(root)

    inventory = scan_free_public_assets(config)
    write_json(
        config.tables_dir / "free_public_data_download_summary.json",
        {
            "status": "completed_no_key_public_downloads",
            "selected_groups": sorted(selected),
            "download_records": records,
            "red_cohort_extraction": extraction,
            "inventory_rows": int(len(inventory)),
        },
    )
    print(f"Downloaded/scanned {len(inventory)} free-public files under {root}")


if __name__ == "__main__":
    main()
