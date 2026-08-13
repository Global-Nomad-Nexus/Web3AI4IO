#!/usr/bin/env python3
"""Audit data expansion coverage without running causal estimators."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "Claire" / "data_expansion" / "artifacts"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def span(rows: list[dict[str, str]], columns: tuple[str, ...]) -> tuple[str, str]:
    values = [row.get(column, "") for column in columns for row in rows if row.get(column, "")]
    return (min(values), max(values)) if values else ("", "")


def unique(rows: list[dict[str, str]], column: str) -> int:
    return len({row.get(column, "") for row in rows if row.get(column, "")})


def record(
    *,
    workstream: str,
    dataset: str,
    path: Path,
    unit: str,
    target_entities: int,
    entity_column: str,
    time_columns: tuple[str, ...],
    status: str,
    blocker: str,
    filters: dict[str, str] | None = None,
) -> dict[str, object]:
    rows = read_csv(path)
    if filters:
        rows = [row for row in rows if all(row.get(key, "") == value for key, value in filters.items())]
    observed = unique(rows, entity_column) if entity_column else len(rows)
    start, end = span(rows, time_columns)
    coverage = round(100 * observed / target_entities, 4) if target_entities else 0.0
    return {
        "workstream": workstream,
        "dataset": dataset,
        "unit": unit,
        "target_entities": target_entities,
        "observed_entities": observed,
        "row_count": len(rows),
        "entity_coverage_pct": coverage,
        "time_start": start,
        "time_end": end,
        "status": status,
        "source_path": str(path.relative_to(ROOT)),
        "source_sha256": sha256(path) if path.exists() else "",
        "blocker": blocker,
    }


def main() -> None:
    shilin = ROOT / "Shilin"
    records = [
        record(
            workstream="solana",
            dataset="rpc_pool_windows",
            path=shilin / "artifacts/external_validation/solana_post_migration_pool_windows.csv",
            unit="token_horizon",
            target_entities=1651,
            entity_column="mint",
            time_columns=("graduated_at", "first_trade_at", "last_trade_at"),
            status="proxy_complete",
            blocker="Not decoded USD volume or active trader data.",
        ),
        record(
            workstream="solana",
            dataset="moralis_decoded_sample",
            path=shilin / "artifacts/external_validation/moralis_decoded_token_outcomes.csv",
            unit="token_horizon",
            target_entities=1651,
            entity_column="mint",
            time_columns=("graduated_at", "first_decoded_trade_at", "last_decoded_trade_at"),
            status="selected_partial",
            blocker="Selected high activity sample and page limit lower bounds.",
        ),
        record(
            workstream="solana",
            dataset="dune_decoded_export",
            path=shilin / "artifacts/external_validation/dune_post_migration_trades.csv",
            unit="token_horizon",
            target_entities=1651,
            entity_column="mint",
            time_columns=("graduated_at", "first_trade_at", "last_trade_at"),
            status="missing",
            blocker="Dune credential and execution budget unavailable.",
        ),
        record(
            workstream="telegram",
            dataset="released_static_metadata",
            path=shilin / "benchmark_release/data/covariates.csv",
            unit="token",
            target_entities=832941,
            entity_column="token_id",
            time_columns=("timestamp_utc",),
            status="graduated_subset_only",
            blocker="Only binary link presence for the 1,651 validation tokens is released.",
            filters={"covariate_family": "token_social_metadata"},
        ),
        record(
            workstream="telegram",
            dataset="recovered_graduated_identifiers",
            path=ROOT / "Claire/data_expansion/artifacts/pump_metadata_git_history.csv",
            unit="token",
            target_entities=1651,
            entity_column="mint",
            time_columns=("created_timestamp_utc",),
            status="metadata_complete_activity_missing",
            blocker="Only 296 rows normalize to public handles; no message activity has been collected.",
        ),
        record(
            workstream="base",
            dataset="clanker_token_created_committed",
            path=shilin / "artifacts/external_validation/clanker_base_token_created.csv",
            unit="token_creation_log",
            target_entities=61080,
            entity_column="token_id",
            time_columns=("block_timestamp_utc",),
            status="bounded_scan_committed",
            blocker="The reported 61,080 row discovery universe is not committed as raw logs.",
        ),
        record(
            workstream="base",
            dataset="clanker_horizon_outcomes",
            path=shilin / "artifacts/external_validation/clanker_base_token_horizons.csv",
            unit="token_horizon",
            target_entities=13880,
            entity_column="token_id",
            time_columns=("launch_timestamp_utc", "first_trade_at", "last_trade_at"),
            status="bounded_sample",
            blocker="Archive swap and transfer coverage is incomplete.",
        ),
        record(
            workstream="base",
            dataset="clanker_full_manifest",
            path=shilin / "benchmark_release/data/clanker_base_full_cohort_manifest.csv",
            unit="token",
            target_entities=13880,
            entity_column="token_id",
            time_columns=("launch_timestamp_utc",),
            status="manifest_complete_outcomes_missing",
            blocker="Manifest completeness is not outcome coverage.",
        ),
        record(
            workstream="base",
            dataset="public_rpc_control_pilot",
            path=ROOT / "Claire/data_expansion/artifacts/base_pilot_coverage.csv",
            unit="token_log_type",
            target_entities=13880,
            entity_column="token_id",
            time_columns=(),
            status="one_day_pilot",
            blocker="Twenty four control tokens only; zero PoolManager Swap rows require interpretation.",
        ),
        record(
            workstream="base",
            dataset="public_rpc_treated_pilot",
            path=ROOT / "Claire/data_expansion/artifacts/base_pilot_treated_coverage.csv",
            unit="token_log_type",
            target_entities=6940,
            entity_column="token_id",
            time_columns=(),
            status="one_day_pilot",
            blocker="One treated token only; batching must be redesigned before scale up.",
        ),
    ]

    OUT.mkdir(parents=True, exist_ok=True)
    columns = list(records[0])
    with (OUT / "coverage_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)
    (OUT / "coverage_audit.json").write_text(
        json.dumps({"records": records}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"records": len(records), "output": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
