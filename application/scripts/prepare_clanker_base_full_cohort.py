#!/usr/bin/env python3
"""Prepare the Clanker/Base full-cohort archive/indexer request manifest.

This script deliberately stops short of claiming full-cohort outcomes. It turns
the expanded TokenCreated discovery scan into query-bounded manifests that can
be sent to Dune, Bitquery, Birdeye, an archive RPC job, or another indexer. Once
the exported swap and transfer CSVs are available, run_clanker_base_validation.py
can ingest them through --swap-import and --transfer-import.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from run_clanker_base_validation import (
    CLANKER_EVENT_ID,
    EXTERNAL,
    SWAP_TOPIC,
    TABLES,
    TOKEN_CREATED_TOPIC,
    TRANSFER_TOPIC,
    UNISWAP_V4_POOL_MANAGER_BASE,
    load_swap_indexer_import,
    load_token_created_csv,
    load_transfer_indexer_import,
    select_cohort,
)


DEFAULT_HORIZONS = [1, 7, 30]

MANIFEST_COLUMNS = [
    "event_id",
    "token_id",
    "cohort_side",
    "clanker_version_class",
    "cohort_match_id",
    "match_distance_blocks",
    "launch_block",
    "launch_timestamp_utc",
    "launch_transaction_hash",
    "pool_id",
    "paired_token",
    "token_admin",
    "msg_sender",
    "pool_hook",
    "pool_hook_label",
    "mev_module",
    "mev_module_label",
    "horizon_1d_end_block",
    "horizon_7d_end_block",
    "horizon_30d_end_block",
    "max_horizon_days",
    "max_horizon_end_block",
    "swap_query_key",
    "transfer_query_key",
    "claim_boundary",
]

QUERY_COLUMNS = [
    "event_id",
    "query_type",
    "unit_id",
    "contract_address",
    "from_block",
    "to_block",
    "topic0",
    "topic1",
    "expected_rows_source",
    "required_import_columns",
    "claim_boundary",
]

EXPECTED_HORIZON_COLUMNS = [
    "event_id",
    "unit_id",
    "token_id",
    "cohort_side",
    "pool_id",
    "horizon_days",
    "launch_block",
    "cutoff_block",
    "requires_swap_coverage",
    "requires_transfer_coverage",
    "claim_boundary",
]

COVERAGE_COLUMNS = [
    "coverage_type",
    "unit_id",
    "token_id",
    "pool_id",
    "cohort_side",
    "from_block",
    "to_block",
    "observed_rows",
    "coverage_status",
    "collected_at_utc",
    "source_layer",
]


def write_csv(path: Path, df: pd.DataFrame, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is not None:
        for column in columns:
            if column not in df.columns:
                df[column] = ""
        df = df[columns]
    df = df.where(pd.notna(df), "")
    df.to_csv(path, index=False)


def parse_horizons(value: str) -> list[int]:
    horizons = sorted({int(part.strip()) for part in value.split(",") if part.strip()})
    if not horizons:
        raise RuntimeError("At least one horizon is required.")
    return horizons


def filter_created(created: pd.DataFrame, start_block: int | None, end_block: int | None) -> pd.DataFrame:
    out = created.copy()
    out["block_number"] = pd.to_numeric(out["block_number"], errors="coerce")
    if start_block is not None:
        out = out.loc[out["block_number"].ge(start_block)]
    if end_block is not None:
        out = out.loc[out["block_number"].le(end_block)]
    out = out.dropna(subset=["block_number"]).copy()
    if out.empty:
        raise RuntimeError("No TokenCreated rows remain after applying block bounds.")
    return out.sort_values(["block_number", "log_index"]).reset_index(drop=True)


def build_manifest(cohort: pd.DataFrame, horizons: list[int], blocks_per_day: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    max_horizon = max(horizons)
    for _, token in cohort.iterrows():
        launch_block = int(token["block_number"])
        row = {
            "event_id": CLANKER_EVENT_ID,
            "token_id": str(token["token_id"]).lower(),
            "cohort_side": token.get("cohort_side", ""),
            "clanker_version_class": token.get("clanker_version_class", ""),
            "cohort_match_id": token.get("cohort_match_id", ""),
            "match_distance_blocks": token.get("match_distance_blocks", ""),
            "launch_block": launch_block,
            "launch_timestamp_utc": token.get("block_timestamp_utc", ""),
            "launch_transaction_hash": token.get("transaction_hash", ""),
            "pool_id": str(token["pool_id"]).lower(),
            "paired_token": str(token.get("paired_token", "")).lower(),
            "token_admin": str(token.get("token_admin", "")).lower(),
            "msg_sender": str(token.get("msg_sender", "")).lower(),
            "pool_hook": str(token.get("pool_hook", "")).lower(),
            "pool_hook_label": token.get("pool_hook_label", ""),
            "mev_module": str(token.get("mev_module", "")).lower(),
            "mev_module_label": token.get("mev_module_label", ""),
            "max_horizon_days": max_horizon,
            "max_horizon_end_block": launch_block + max_horizon * blocks_per_day + 2_000,
            "swap_query_key": f"swap:{str(token['pool_id']).lower()}:{launch_block}",
            "transfer_query_key": f"transfer:{str(token['token_id']).lower()}:{launch_block}",
            "claim_boundary": (
                "Full-cohort manifest row only. Outcomes become computable after archive/indexer swap and "
                "ERC20 Transfer coverage is imported and validated."
            ),
        }
        for horizon in horizons:
            row[f"horizon_{horizon}d_end_block"] = launch_block + horizon * blocks_per_day + 2_000
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=MANIFEST_COLUMNS)


def build_query_bounds(manifest: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    swap_rows: list[dict[str, Any]] = []
    transfer_rows: list[dict[str, Any]] = []
    for _, row in manifest.iterrows():
        swap_rows.append(
            {
                "event_id": CLANKER_EVENT_ID,
                "query_type": "uniswap_v4_poolmanager_swap",
                "unit_id": row["swap_query_key"],
                "contract_address": UNISWAP_V4_POOL_MANAGER_BASE,
                "from_block": int(row["launch_block"]),
                "to_block": int(row["max_horizon_end_block"]),
                "topic0": SWAP_TOPIC,
                "topic1": row["pool_id"],
                "expected_rows_source": "archive/indexer logs table filtered by PoolManager address and pool_id topic",
                "required_import_columns": "pool_id,sender,block_number,timestamp_unix,timestamp_utc,transaction_hash,amount0_raw,amount1_raw",
                "claim_boundary": "Query-bound request row; not outcome evidence until imported rows pass coverage checks.",
            }
        )
        transfer_rows.append(
            {
                "event_id": CLANKER_EVENT_ID,
                "query_type": "erc20_transfer",
                "unit_id": row["transfer_query_key"],
                "contract_address": row["token_id"],
                "from_block": int(row["launch_block"]),
                "to_block": int(row["max_horizon_end_block"]),
                "topic0": TRANSFER_TOPIC,
                "topic1": "",
                "expected_rows_source": "archive/indexer logs table filtered by token contract address and Transfer topic",
                "required_import_columns": "token_id,from_address,to_address,block_number,log_index,transaction_hash,amount_raw",
                "claim_boundary": "Query-bound request row; needed for holder reconstruction, not outcome evidence by itself.",
            }
        )
    return pd.DataFrame(swap_rows).reindex(columns=QUERY_COLUMNS), pd.DataFrame(transfer_rows).reindex(columns=QUERY_COLUMNS)


def build_expected_horizons(manifest: pd.DataFrame, horizons: list[int], blocks_per_day: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, token in manifest.iterrows():
        launch_block = int(token["launch_block"])
        for horizon in horizons:
            rows.append(
                {
                    "event_id": CLANKER_EVENT_ID,
                    "unit_id": f"{token['token_id']}:{horizon}d:base_full_cohort_expected",
                    "token_id": token["token_id"],
                    "cohort_side": token["cohort_side"],
                    "pool_id": token["pool_id"],
                    "horizon_days": horizon,
                    "launch_block": launch_block,
                    "cutoff_block": launch_block + horizon * blocks_per_day + 2_000,
                    "requires_swap_coverage": True,
                    "requires_transfer_coverage": True,
                    "claim_boundary": "Expected token-horizon row; filled only after archive/indexer imports are validated.",
                }
            )
    return pd.DataFrame(rows).reindex(columns=EXPECTED_HORIZON_COLUMNS)


def build_import_contract() -> pd.DataFrame:
    rows = [
        {
            "import_name": "token_created",
            "required_columns": (
                "event_id,block_number,block_timestamp_utc,block_timestamp_unix,transaction_hash,log_index,"
                "token_id,token_admin,msg_sender,pool_id,paired_token,pool_hook,mev_module,clanker_version_class"
            ),
            "accepted_aliases": "Use run_clanker_base_validation.py --token-created-import when exporting the same canonical schema.",
            "consumer_command": "python3 scripts/prepare_clanker_base_full_cohort.py --token-created <csv>",
            "claim_boundary": "Launch universe only; not swap or holder evidence.",
        },
        {
            "import_name": "poolmanager_swaps",
            "required_columns": "pool_id,sender,block_number,timestamp_unix,timestamp_utc,transaction_hash,amount0_raw,amount1_raw",
            "accepted_aliases": "poolId,pool,pool_address; trader,caller,tx_from,origin; block,blockNumber; tx_hash,transactionHash,hash",
            "consumer_command": (
                "python3 scripts/run_clanker_base_validation.py --reuse-token-created --selection-mode full-window "
                "--tokens-per-side 0 --swap-import <swaps.csv> --transfer-import <transfers.csv>"
            ),
            "claim_boundary": "Needed for active traders, buy/sell, volume, first/last trade, and early sender concentration.",
        },
        {
            "import_name": "erc20_transfers",
            "required_columns": "token_id,from_address,to_address,block_number,log_index,transaction_hash,amount_raw",
            "accepted_aliases": "token,contract_address,address,currency; from,fromAddress,sender; to,toAddress,recipient; block,blockNumber",
            "consumer_command": (
                "python3 scripts/run_clanker_base_validation.py --reuse-token-created --selection-mode full-window "
                "--tokens-per-side 0 --swap-import <swaps.csv> --transfer-import <transfers.csv>"
            ),
            "claim_boundary": "Needed for holder count and top-10 holder concentration at fixed horizons.",
        },
    ]
    return pd.DataFrame(rows)


def build_optional_coverage(
    manifest: pd.DataFrame,
    swap_import_path: Path | None,
    transfer_import_path: Path | None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    swaps = load_swap_indexer_import(swap_import_path) if swap_import_path else pd.DataFrame()
    transfers = load_transfer_indexer_import(transfer_import_path) if transfer_import_path else pd.DataFrame()
    for _, token in manifest.iterrows():
        from_block = int(token["launch_block"])
        to_block = int(token["max_horizon_end_block"])
        pool_id = str(token["pool_id"]).lower()
        token_id = str(token["token_id"]).lower()
        if not swaps.empty:
            observed_swaps = swaps.loc[
                swaps["pool_id"].astype(str).str.lower().eq(pool_id)
                & pd.to_numeric(swaps["block_number"], errors="coerce").between(from_block, to_block)
            ]
            rows.append(
                {
                    "coverage_type": "poolmanager_swaps",
                    "unit_id": token["swap_query_key"],
                    "token_id": token_id,
                    "pool_id": pool_id,
                    "cohort_side": token["cohort_side"],
                    "from_block": from_block,
                    "to_block": to_block,
                    "observed_rows": len(observed_swaps),
                    "coverage_status": "import_rows_observed" if len(observed_swaps) else "no_import_rows_observed",
                }
            )
        if not transfers.empty:
            observed_transfers = transfers.loc[
                transfers["token_id"].astype(str).str.lower().eq(token_id)
                & pd.to_numeric(transfers["block_number"], errors="coerce").between(from_block, to_block)
            ]
            rows.append(
                {
                    "coverage_type": "erc20_transfers",
                    "unit_id": token["transfer_query_key"],
                    "token_id": token_id,
                    "pool_id": pool_id,
                    "cohort_side": token["cohort_side"],
                    "from_block": from_block,
                    "to_block": to_block,
                    "observed_rows": len(observed_transfers),
                    "coverage_status": "import_rows_observed" if len(observed_transfers) else "no_import_rows_observed",
                }
            )
    return pd.DataFrame(rows).reindex(columns=COVERAGE_COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-created", default=str(EXTERNAL / "clanker_base_token_created.csv"))
    parser.add_argument("--start-block", type=int, default=None)
    parser.add_argument("--end-block", type=int, default=None)
    parser.add_argument("--horizons", default="1,7,30")
    parser.add_argument("--blocks-per-day", type=int, default=43_500)
    parser.add_argument("--tokens-per-side", type=int, default=0)
    parser.add_argument(
        "--selection-mode",
        choices=["matched", "full-window"],
        default="full-window",
        help="full-window selects all v4.1 rows in the filtered TokenCreated scan.",
    )
    parser.add_argument("--swap-import", default="")
    parser.add_argument("--transfer-import", default="")
    parser.add_argument("--output-dir", default=str(EXTERNAL))
    args = parser.parse_args()

    token_created_path = Path(args.token_created).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    horizons = parse_horizons(args.horizons)
    created = filter_created(load_token_created_csv(token_created_path), args.start_block, args.end_block)
    cohort, activation, selection_summary = select_cohort(
        created,
        args.tokens_per_side,
        selection_mode=args.selection_mode,
    )
    manifest = build_manifest(cohort, horizons, args.blocks_per_day)
    swap_bounds, transfer_bounds = build_query_bounds(manifest)
    expected_horizons = build_expected_horizons(manifest, horizons, args.blocks_per_day)
    import_contract = build_import_contract()
    coverage = build_optional_coverage(
        manifest,
        Path(args.swap_import).expanduser().resolve() if args.swap_import else None,
        Path(args.transfer_import).expanduser().resolve() if args.transfer_import else None,
    )

    manifest_path = output_dir / "clanker_base_full_cohort_manifest.csv"
    swap_bounds_path = output_dir / "clanker_base_full_cohort_pool_query_bounds.csv"
    transfer_bounds_path = output_dir / "clanker_base_full_cohort_transfer_query_bounds.csv"
    expected_horizons_path = output_dir / "clanker_base_full_cohort_expected_horizons.csv"
    import_contract_path = output_dir / "clanker_base_full_cohort_import_contract.csv"
    coverage_path = output_dir / "clanker_base_full_cohort_import_coverage.csv"
    summary_path = TABLES / "clanker_base_full_cohort_manifest_summary.json"

    write_csv(manifest_path, manifest, MANIFEST_COLUMNS)
    write_csv(swap_bounds_path, swap_bounds, QUERY_COLUMNS)
    write_csv(transfer_bounds_path, transfer_bounds, QUERY_COLUMNS)
    write_csv(expected_horizons_path, expected_horizons, EXPECTED_HORIZON_COLUMNS)
    write_csv(import_contract_path, import_contract)
    if not coverage.empty or not coverage_path.exists():
        write_csv(coverage_path, coverage, COVERAGE_COLUMNS)

    counts = Counter(created["clanker_version_class"])
    summary = {
        "event_id": CLANKER_EVENT_ID,
        "status": "full_cohort_manifest_ready_needs_archive_indexer",
        "token_created_source": str(token_created_path),
        "token_created_rows": int(len(created)),
        "version_class_counts": dict(counts),
        "activation_timestamp_utc": activation.get("block_timestamp_utc", ""),
        "activation_transaction_hash": activation.get("transaction_hash", ""),
        "selection": selection_summary,
        "cohort_tokens": int(manifest["token_id"].nunique()),
        "treated_tokens": int(manifest.loc[manifest["cohort_side"].eq("post_v4_1_treated"), "token_id"].nunique()),
        "control_tokens": int(manifest.loc[manifest["cohort_side"].eq("pre_v4_0_control"), "token_id"].nunique()),
        "expected_horizon_rows": int(len(expected_horizons)),
        "pool_query_rows": int(len(swap_bounds)),
        "transfer_query_rows": int(len(transfer_bounds)),
        "horizons": horizons,
        "blocks_per_day": args.blocks_per_day,
        "coverage_rows": int(len(coverage)),
        "claim_boundary": (
            "This is the full-cohort archive/indexer request manifest, not full-cohort outcome evidence. "
            "A platform-wide causal replication claim requires imported swap and transfer logs to cover the "
            "manifest and then pass fixed-horizon metric reconstruction."
        ),
        "next_command_after_import": (
            "python3 scripts/run_clanker_base_validation.py --reuse-token-created --selection-mode full-window "
            "--tokens-per-side 0 --swap-import <swaps.csv> --transfer-import <transfers.csv>"
        ),
        "outputs": {
            "manifest": str(manifest_path.relative_to(EXTERNAL.parent.parent)),
            "pool_query_bounds": str(swap_bounds_path.relative_to(EXTERNAL.parent.parent)),
            "transfer_query_bounds": str(transfer_bounds_path.relative_to(EXTERNAL.parent.parent)),
            "expected_horizons": str(expected_horizons_path.relative_to(EXTERNAL.parent.parent)),
            "import_contract": str(import_contract_path.relative_to(EXTERNAL.parent.parent)),
            "import_coverage": str(coverage_path.relative_to(EXTERNAL.parent.parent)),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(
        "Clanker/Base full-cohort manifest written: "
        f"cohort_tokens={summary['cohort_tokens']} treated={summary['treated_tokens']} "
        f"controls={summary['control_tokens']} expected_horizon_rows={summary['expected_horizon_rows']}"
    )


if __name__ == "__main__":
    main()
