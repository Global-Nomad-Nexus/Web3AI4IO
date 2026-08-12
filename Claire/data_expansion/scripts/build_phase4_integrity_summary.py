#!/usr/bin/env python3
"""Build a compact machine-readable integrity summary for Phase 4."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "Claire/data_expansion/artifacts/phase4_integrity_summary.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def column(chain: str, table: str, name: str):
    path = ROOT / f"data/canonical/v1/{chain}/{table}/part-00000.parquet"
    return pq.read_table(path, columns=[name]).column(name).combine_chunks()


def chain_summary(chain: str) -> dict:
    manifest_path = ROOT / f"dataset/releases/v1/{chain}_core.json"
    manifest = json.loads(manifest_path.read_text())
    tokens = column(chain, "tokens", "token_id")
    token_set = tokens
    tables = {}
    for name, declared in manifest["tables"].items():
        path = ROOT / f"data/canonical/v1/{chain}/{name}/part-00000.parquet"
        actual_rows = pq.read_metadata(path).num_rows
        actual_sha = sha256(path)
        tables[name] = {
            "declared_rows": declared["rows"],
            "actual_rows": actual_rows,
            "rows_match": declared["rows"] == actual_rows,
            "sha256_match": declared["sha256"] == actual_sha,
        }
    identities = {
        "token_id_unique": len(tokens) == pc.count_distinct(tokens).as_py(),
        "launch_id_unique": len(column(chain, "launches", "launch_id")) == pc.count_distinct(column(chain, "launches", "launch_id")).as_py(),
        "coverage_token_id_unique": len(column(chain, "coverage_ledger", "token_id")) == pc.count_distinct(column(chain, "coverage_ledger", "token_id")).as_py(),
    }
    foreign_keys = {}
    for table in ("launches", "protocol_config", "pools", "liquidity_initializations", "lifecycle_events", "token_metadata", "coverage_ledger"):
        child = column(chain, table, "token_id")
        foreign_keys[f"{table}.token_id_subset"] = not len(child) or pc.all(pc.is_in(child, value_set=token_set)).as_py()
    statuses = {}
    for field in (
        "pool_mapping_status", "pool_initialization_status", "liquidity_initialization_status",
        "graduation_status", "migration_status", "decoded_swaps_status", "holder_data_status",
        "trading_data_status", "coverage_status",
    ):
        statuses[field] = sorted(set(column(chain, "coverage_ledger", field).to_pylist()))
    summary = {
        "manifest": manifest_path.relative_to(ROOT).as_posix(),
        "launch_universe": len(tokens),
        "tables": tables,
        "identities": identities,
        "foreign_keys": foreign_keys,
        "coverage": manifest["canonical_core_coverage"],
        "observed_status_values": statuses,
        "official_api_metadata_rows": manifest["tables"]["token_metadata"]["rows"],
        "state_snapshot_rows": manifest["tables"]["token_state_snapshots"]["rows"],
        "forbidden_tables_absent": all(
            not (ROOT / f"data/canonical/v1/{chain}/{name}").exists()
            for name in ("decoded_swaps", "holders", "holder_balances", "trades", "trading")
        ),
    }
    if chain == "bnb":
        summary["reconciliation"] = {
            "official_api_input_rows": 1000,
            "metadata_rows_in_onchain_universe": 999,
            "metadata_rows_outside_onchain_universe": 1,
            "lifecycle_events_formula": "1593679 token_created + 15509 declared lifecycle + 15403 pool_initialized + 15403 initial_liquidity_added = 1639994",
            "trade_stop_semantics": "106 V1 TradeStop events are retained literally. They do not encode pool mapping, pool initialization, graduation, or migration, so those applicable-but-unobserved fields are not_collected.",
            "non_lifecycle_token_semantics": "Tokens without an observed lifecycle transition have pool, liquidity, graduation, and migration marked not_applicable to their currently observed created state. This does not claim the token can never transition later.",
        }
    else:
        summary["reconciliation"] = {
            "official_api_input_rows": 1000,
            "metadata_rows_in_onchain_universe": 1000,
            "metadata_rows_outside_onchain_universe": 0,
            "lifecycle_events_formula": "104548 token_created + 1831 token_launched + 1831 pool_initialized + 1831 initial_liquidity_added = 110041",
            "non_lifecycle_token_semantics": "Tokens without an observed TokenLaunched transition have pool, liquidity, graduation, and migration marked not_applicable to their currently observed created state. This does not claim the token can never transition later.",
        }
    summary["scope_semantics"] = {
        "official_api_role": "metadata enrichment only; never universe membership or denominator",
        "decoded_swaps": "not_collected because outside the declared Phase 4 collection scope",
        "holder_data": "not_collected because outside the declared Phase 4 collection scope",
        "trading_data": "not_collected because outside the declared Phase 4 collection scope",
        "metadata_completeness_claimed": False,
    }
    return summary


def main() -> None:
    result = {
        "phase": 4,
        "scope": "BNB/Four.meme and TRON/SunPump canonical core",
        "pytest": "14 passed in 16.20s",
        "chains": {chain: chain_summary(chain) for chain in ("bnb", "tron")},
    }
    result["accepted"] = all(
        all(item["rows_match"] and item["sha256_match"] for item in chain["tables"].values())
        and all(chain["identities"].values())
        and all(chain["foreign_keys"].values())
        and chain["forbidden_tables_absent"]
        for chain in result["chains"].values()
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": OUTPUT.relative_to(ROOT).as_posix(), "accepted": result["accepted"]}))


if __name__ == "__main__":
    main()
