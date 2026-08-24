"""Local inventory for no-key public data extensions."""

from __future__ import annotations

import csv
import gzip
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .io import CaseConfig, file_sha256, write_csv, write_json


FREE_PUBLIC_ROOT = Path("data_sources") / "free_public"


def _source_metadata(path: Path) -> dict[str, str]:
    parts = set(path.parts)
    if "solarchive" in parts:
        return {
            "source_name": "SolArchive / HuggingFace mirror",
            "license": "CC-BY-4.0",
            "provenance": "https://huggingface.co/datasets/solarchive/solarchive and https://solarchive.org/",
            "paper_role": "Solana-wide public token/account/transaction universe for background coverage and reproducibility checks.",
        }
    if "red_cohort" in parts:
        return {
            "source_name": "RED-COHORT-2026-v1",
            "license": "CC-BY-4.0",
            "provenance": "https://zenodo.org/records/20978742",
            "paper_role": "Early-wallet and persistent-cohort evidence for the H4 concentration/sniper validation layer.",
        }
    if "huggingface" in parts or "pump_fun_meme_token_dataset.csv" in path.name:
        return {
            "source_name": "HuggingFace pump-fun-meme-token-dataset",
            "license": "CC-BY-NC-4.0",
            "provenance": "https://huggingface.co/datasets/muhammetakkurt/pump-fun-meme-token-dataset",
            "paper_role": "Pump.fun metadata/text extension for broader launchpad descriptive checks, not a main causal outcome.",
        }
    return {
        "source_name": "unclassified_free_public_asset",
        "license": "see_source",
        "provenance": "",
        "paper_role": "registered local public-data extension",
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _count_lines(path: Path) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    mode = "rt" if path.suffix == ".gz" else "r"
    with opener(path, mode, encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def _csv_shape(path: Path) -> dict[str, Any]:
    try:
        rows = 0
        columns: list[str] = []
        unique_mints: set[str] = set()
        mint_column = ""
        for chunk in pd.read_csv(path, chunksize=50_000, low_memory=False):
            rows += len(chunk)
            if not columns:
                columns = [str(col) for col in chunk.columns]
                for candidate in ["mint", "mint_address", "address", "token_address"]:
                    if candidate in chunk.columns:
                        mint_column = candidate
                        break
            if mint_column:
                unique_mints.update(chunk[mint_column].dropna().astype(str).tolist())
        return {
            "status": "read_with_pandas",
            "rows": rows,
            "columns": len(columns),
            "column_names": columns,
            "mint_column": mint_column,
            "unique_mints": len(unique_mints) if mint_column else None,
        }
    except Exception as exc:  # pragma: no cover - fallback for malformed public CSVs
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
        return {
            "status": "header_only_fallback",
            "error": str(exc),
            "columns": len(header),
            "column_names": header,
        }


def _red_cohort_summary(root: Path) -> dict[str, Any]:
    zip_path = root / "red_cohort" / "RED-COHORT-2026-v1.zip"
    extracted_root = root / "red_cohort" / "extracted"
    summary: dict[str, Any] = {
        "zip_present": zip_path.exists(),
        "zip_path": str(zip_path),
        "extracted_root": str(extracted_root),
        "files": [],
    }
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path) as archive:
                summary["zip_status"] = "valid_zip"
                summary["files"] = [
                    {"filename": info.filename, "compressed_size": info.compress_size, "file_size": info.file_size}
                    for info in archive.infolist()
                    if not info.is_dir()
                ]
        except zipfile.BadZipFile as exc:
            summary["zip_status"] = "invalid_zip"
            summary["zip_error"] = str(exc)
    cohorts = next(extracted_root.rglob("sniper_cohorts.jsonl"), None) if extracted_root.exists() else None
    intra = (
        next(extracted_root.rglob("sniper_cohorts_intra.jsonl.gz"), None)
        if extracted_root.exists()
        else None
    )
    descriptive_stats = (
        next(extracted_root.rglob("table3_descriptive_stats.csv"), None)
        if extracted_root.exists()
        else None
    )
    size_distribution = (
        next(extracted_root.rglob("table2_size_distribution.csv"), None)
        if extracted_root.exists()
        else None
    )
    if cohorts:
        summary["sniper_cohorts_rows"] = _count_lines(cohorts)
        summary["sniper_cohorts_path"] = str(cohorts)
    if intra:
        summary["sniper_cohorts_intra_rows"] = _count_lines(intra)
        summary["sniper_cohorts_intra_path"] = str(intra)
    if descriptive_stats:
        stats_df = pd.read_csv(descriptive_stats)
        summary["descriptive_stats"] = {
            str(row["metric"]): float(row["value"]) for row in stats_df.to_dict(orient="records")
        }
        summary["descriptive_stats_path"] = str(descriptive_stats)
    if size_distribution:
        size_df = pd.read_csv(size_distribution)
        summary["size_distribution"] = size_df.to_dict(orient="records")
        summary["size_distribution_path"] = str(size_distribution)
    return summary


def _red_cohort_overlap_audit(config: CaseConfig, root: Path) -> dict[str, Any]:
    """Audit whether RED-COHORT mints overlap the current RED-PUMP outcome window."""

    red_path = config.source_path("red_pump_token_outcomes", required=False)
    extracted_root = root / "red_cohort" / "extracted"
    intra = (
        next(extracted_root.rglob("sniper_cohorts_intra.jsonl.gz"), None)
        if extracted_root.exists()
        else None
    )
    cohorts = next(extracted_root.rglob("sniper_cohorts.jsonl"), None) if extracted_root.exists() else None
    summary = {
        "status": "not_available",
        "red_pump_path": str(red_path),
        "red_cohort_intra_path": str(intra) if intra else "",
        "red_cohort_cohorts_path": str(cohorts) if cohorts else "",
        "red_pump_mints": 0,
        "red_cohort_intra_mints": 0,
        "red_cohort_intra_overlap_mints": 0,
        "red_cohort_mints_hit": 0,
        "red_cohort_mints_hit_overlap": 0,
        "claim_boundary": (
            "If overlap is zero or sparse, RED-COHORT is an external H4 mechanism validation sample, "
            "not a joined token-level outcome design for the current RED-PUMP window."
        ),
    }
    if not red_path.exists() or not intra:
        return summary

    red_mints = set(pd.read_csv(red_path, usecols=["mint"])["mint"].dropna().astype(str))
    intra_mints: set[str] = set()
    intra_overlap: set[str] = set()
    with gzip.open(intra, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            mint = str(json.loads(line).get("mint", ""))
            if not mint:
                continue
            intra_mints.add(mint)
            if mint in red_mints:
                intra_overlap.add(mint)

    hit_mints: set[str] = set()
    hit_overlap: set[str] = set()
    if cohorts:
        with cohorts.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                payload = json.loads(line)
                for hit in payload.get("mints_hit", []) or []:
                    mint = str(hit.get("mint", ""))
                    if not mint:
                        continue
                    hit_mints.add(mint)
                    if mint in red_mints:
                        hit_overlap.add(mint)

    summary.update(
        {
            "status": "computed_overlap_audit",
            "red_pump_mints": len(red_mints),
            "red_cohort_intra_mints": len(intra_mints),
            "red_cohort_intra_overlap_mints": len(intra_overlap),
            "red_cohort_mints_hit": len(hit_mints),
            "red_cohort_mints_hit_overlap": len(hit_overlap),
            "overlap_share_intra": len(intra_overlap) / len(intra_mints) if intra_mints else 0.0,
            "overlap_share_mints_hit": len(hit_overlap) / len(hit_mints) if hit_mints else 0.0,
        }
    )
    write_csv(config.tables_dir / "red_cohort_red_pump_overlap.csv", pd.DataFrame([summary]))
    return summary


def _solarchive_summary(root: Path) -> dict[str, Any]:
    sol_root = root / "solarchive"
    summary: dict[str, Any] = {
        "root": str(sol_root),
        "present": sol_root.exists(),
        "parquet_reader": "not_required_for_inventory",
    }
    tokens_index = sol_root / "tokens_index.json"
    txs_index = sol_root / "txs_index.json"
    if tokens_index.exists():
        data = _read_json(tokens_index)
        parts = data.get("partitions", [])
        summary["token_partition_count"] = len(parts)
        summary["token_partition_first"] = parts[0].get("partition") if parts else None
        summary["token_partition_last"] = parts[-1].get("partition") if parts else None
        summary["token_index_updated_at"] = data.get("updated_at")
    if txs_index.exists():
        data = _read_json(txs_index)
        parts = data.get("partitions", [])
        summary["transaction_partition_count_in_hf_index"] = len(parts)
        summary["transaction_partition_first_in_hf_index"] = parts[0].get("partition") if parts else None
        summary["transaction_partition_last_in_hf_index"] = parts[-1].get("partition") if parts else None
        summary["transaction_index_updated_at"] = data.get("updated_at")
    summary["downloaded_token_parquet_files"] = sorted(
        str(path.relative_to(root)) for path in (sol_root / "tokens").glob("*.parquet")
    )
    return summary


def _hf_meme_summary(root: Path) -> dict[str, Any]:
    path = root / "huggingface" / "pump_fun_meme_token_dataset.csv"
    summary: dict[str, Any] = {"present": path.exists(), "path": str(path)}
    if path.exists():
        summary.update(_csv_shape(path))
    return summary


def scan_free_public_assets(config: CaseConfig) -> pd.DataFrame:
    """Scan downloaded no-key public datasets and write reproducibility ledgers."""

    root = config.project_root / FREE_PUBLIC_ROOT
    rows: list[dict[str, Any]] = []
    if root.exists():
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            metadata = _source_metadata(path.relative_to(root))
            rows.append(
                {
                    **metadata,
                    "relative_path": str(path.relative_to(config.project_root)),
                    "bytes": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
            )
    inventory = pd.DataFrame(rows)
    write_csv(config.tables_dir / "free_public_data_inventory.csv", inventory)

    bytes_by_source: dict[str, int] = defaultdict(int)
    files_by_source: dict[str, int] = defaultdict(int)
    for row in rows:
        bytes_by_source[str(row["source_name"])] += int(row["bytes"])
        files_by_source[str(row["source_name"])] += 1
    summary = {
        "status": "computed_free_public_local_inventory",
        "root": str(root),
        "total_files": len(rows),
        "total_bytes": sum(int(row["bytes"]) for row in rows),
        "files_by_source": dict(sorted(files_by_source.items())),
        "bytes_by_source": dict(sorted(bytes_by_source.items())),
        "solarchive": _solarchive_summary(root),
        "red_cohort": _red_cohort_summary(root),
        "red_cohort_red_pump_overlap": _red_cohort_overlap_audit(config, root),
        "hf_meme_token_dataset": _hf_meme_summary(root),
        "claim_boundary": (
            "These files extend public-data coverage and H4 mechanism validation. They do not replace "
            "decoded token-level PumpSwap 1/7/30d USD trade outcomes from Dune or another full indexer."
        ),
    }
    write_json(config.tables_dir / "free_public_data_summary.json", summary)
    return inventory
