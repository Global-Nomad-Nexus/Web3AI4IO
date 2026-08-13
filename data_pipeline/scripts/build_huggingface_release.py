#!/usr/bin/env python3
"""Build a file-level manifest for the unified onchain and canonical HF dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and not any(part in {".venv", "__pycache__", ".pytest_cache"} for part in path.parts):
            yield path


def canonical_files(root: Path) -> Iterable[Path]:
    for path in files(root):
        if "token_metadata" not in path.parts and not path.name.startswith("token_metadata."):
            yield path


def add_tree(entries: list[dict], repo: Path, source: Path, destination: str, role: str) -> None:
    for path in files(source):
        relative = path.relative_to(source).as_posix()
        entries.append({
            "source_path": path.relative_to(repo).as_posix(),
            "dataset_path": f"{destination}/{relative}",
            "role": role,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })


def add_canonical_tree(entries: list[dict], repo: Path, source: Path, destination: str) -> None:
    for path in canonical_files(source):
        relative = path.relative_to(source).as_posix()
        entries.append({
            "source_path": path.relative_to(repo).as_posix(),
            "dataset_path": f"{destination}/{relative}",
            "role": "canonical_onchain_core",
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })


def add_file(entries: list[dict], repo: Path, source: Path, destination: str, role: str) -> None:
    entries.append({
        "source_path": source.relative_to(repo).as_posix(),
        "dataset_path": destination,
        "role": role,
        "bytes": source.stat().st_size,
        "sha256": sha256(source),
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("data_pipeline/huggingface/release_manifest.json"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    entries: list[dict] = []

    add_canonical_tree(entries, repo, repo / "data/canonical/v1", "canonical/v1")
    add_tree(entries, repo, repo / "data/external/base/20260811", "external/base/20260811", "onchain_source")
    add_tree(entries, repo, repo / "data/external/fourmeme/20260811/onchain", "external/bnb_fourmeme/20260811/onchain", "onchain_source")
    sunpump = repo / "data/external/sunpump/20260811/snapshot"
    for name in (
        "ONCHAIN_SOURCE.json",
        "onchain_core.jsonl",
        "tokencreate_checkpoint.json",
        "tokencreate_index.jsonl",
        "tokenlaunched_checkpoint.json",
        "tokenlaunched_index.jsonl",
        "newimplementation_checkpoint.json",
        "newimplementation_index.jsonl",
    ):
        add_file(entries, repo, sunpump / name, f"external/tron_sunpump/20260811/onchain/{name}", "onchain_source")

    solana_bundle = repo / "data/external/shilin/20260810/bundle/01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local/data/raw"
    for name in (
        "red_pump_2026_v1_launches.jsonl.gz",
        "red_pump_2026_v1_outcomes.csv.gz",
        "red_pump_results.json",
        "red_pump_SCHEMA.md",
        "red_pump_README.md",
        "SHA256SUMS",
    ):
        add_file(entries, repo, solana_bundle / name, f"external/solana/red_pump/{name}", "onchain_source")

    delivered = repo / "data/external/shilin/20260810/bundle/Web3AI4IO/Shilin/artifacts/external_validation"
    for name in (
        "solana_post_migration_pool_windows.csv",
        "moralis_token_swaps.csv",
        "moralis_decoded_token_outcomes.csv",
    ):
        add_file(entries, repo, delivered / name, f"external/solana/validation/{name}", "onchain_validation")

    for path in (
        repo / "data_pipeline/source_registry.json",
        repo / "data_pipeline/schemas/v1/schema_registry.json",
        repo / "data_pipeline/schemas/v1/crosschain_schema_registry.json",
        repo / "data_pipeline/releases/v1/solana_core.json",
        repo / "data_pipeline/releases/v1/base_core.json",
        repo / "data_pipeline/releases/v1/bnb_core.json",
        repo / "data_pipeline/releases/v1/tron_core.json",
    ):
        add_file(entries, repo, path, f"metadata/{path.name}", "schema_or_manifest")

    duplicates = [entry["dataset_path"] for entry in entries]
    if len(duplicates) != len(set(duplicates)):
        raise RuntimeError("Duplicate dataset paths in release manifest")
    result = {
        "release": "v1",
        "dataset_scope": "unified four chain onchain and canonical dataset",
        "offchain_event_packs_included": False,
        "files": entries,
        "file_count": len(entries),
        "total_bytes": sum(entry["bytes"] for entry in entries),
    }
    output = repo / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": output.relative_to(repo).as_posix(), "files": len(entries), "bytes": result["total_bytes"]}))


if __name__ == "__main__":
    main()
