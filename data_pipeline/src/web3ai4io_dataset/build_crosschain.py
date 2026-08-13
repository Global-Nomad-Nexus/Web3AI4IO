from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import pyarrow as pa
import pyarrow.parquet as pq


VERSION = "v1"
BASE_CHAIN = "eip155:8453"
BNB_CHAIN = "eip155:56"
TRON_CHAIN = "tron:mainnet"
WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
ZERO_EVM_ADDRESS = "0x0000000000000000000000000000000000000000"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def timestamp(value: Any, milliseconds: bool = False) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).replace(".", "", 1).isdigit():
            number = float(value)
            if milliseconds:
                number /= 1000
            return datetime.fromtimestamp(number, tz=timezone.utc)
        text = str(value).replace("Z", "+00:00")
        result = datetime.fromisoformat(text)
        return (result if result.tzinfo else result.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def integer(value: Any) -> int | None:
    value = number(value)
    return None if value is None else int(value)


def boolean(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes"}


COMMON = [
    pa.field("dataset_version", pa.string(), nullable=False),
    pa.field("chain_id", pa.string(), nullable=False),
    pa.field("platform_id", pa.string(), nullable=False),
]

SCHEMAS = {
    "tokens": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("address", pa.string(), nullable=False),
        pa.field("symbol", pa.string()),
        pa.field("name", pa.string()),
        pa.field("creator", pa.string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
        pa.field("decimals", pa.int16()),
        pa.field("total_supply_raw", pa.string()),
        pa.field("source_id", pa.string(), nullable=False),
        pa.field("source_record_id", pa.string()),
    ]),
    "launches": pa.schema(COMMON + [
        pa.field("launch_id", pa.string(), nullable=False),
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("launch_at", pa.timestamp("us", tz="UTC")),
        pa.field("block_number", pa.int64()),
        pa.field("transaction_hash", pa.string()),
        pa.field("log_index", pa.int64()),
        pa.field("factory_or_manager", pa.string()),
        pa.field("pool_id", pa.string()),
        pa.field("pool_address", pa.string()),
        pa.field("paired_token", pa.string()),
        pa.field("protocol_version", pa.string()),
        pa.field("launch_status", pa.string()),
        pa.field("source_id", pa.string(), nullable=False),
        pa.field("coverage_role", pa.string(), nullable=False),
    ]),
    "protocol_config": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("creator", pa.string()),
        pa.field("message_sender", pa.string()),
        pa.field("starting_tick", pa.int64()),
        pa.field("pool_hook", pa.string()),
        pa.field("pool_hook_label", pa.string()),
        pa.field("locker", pa.string()),
        pa.field("mev_module", pa.string()),
        pa.field("mev_module_label", pa.string()),
        pa.field("extensions_supply_raw", pa.string()),
        pa.field("protocol_version", pa.string()),
        pa.field("manager_address", pa.string()),
        pa.field("implementation_address", pa.string()),
        pa.field("token_index", pa.int64()),
        pa.field("request_id", pa.string()),
        pa.field("launch_fee_raw", pa.string()),
        pa.field("version_status", pa.string(), nullable=False),
        pa.field("module_status", pa.string(), nullable=False),
        pa.field("observation_status", pa.string(), nullable=False),
        pa.field("source_id", pa.string(), nullable=False),
    ]),
    "pools": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("pool_id", pa.string(), nullable=False),
        pa.field("pool_address", pa.string()),
        pa.field("pool_manager", pa.string()),
        pa.field("currency0", pa.string()),
        pa.field("currency1", pa.string()),
        pa.field("fee_hundredths_bip", pa.int64()),
        pa.field("tick_spacing", pa.int64()),
        pa.field("hooks", pa.string()),
        pa.field("sqrt_price_x96", pa.string()),
        pa.field("initial_tick", pa.int64()),
        pa.field("initialized_at", pa.timestamp("us", tz="UTC")),
        pa.field("initialization_transaction_hash", pa.string()),
        pa.field("initialization_log_index", pa.int64()),
        pa.field("mapping_status", pa.string(), nullable=False),
        pa.field("initialization_status", pa.string(), nullable=False),
        pa.field("source_id", pa.string(), nullable=False),
    ]),
    "liquidity_initializations": pa.schema(COMMON + [
        pa.field("liquidity_event_id", pa.string(), nullable=False),
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("pool_id", pa.string(), nullable=False),
        pa.field("event_at", pa.timestamp("us", tz="UTC")),
        pa.field("block_number", pa.int64()),
        pa.field("transaction_hash", pa.string()),
        pa.field("log_index", pa.int64()),
        pa.field("sender", pa.string()),
        pa.field("tick_lower", pa.int64()),
        pa.field("tick_upper", pa.int64()),
        pa.field("liquidity_delta_raw", pa.string()),
        pa.field("amount0_raw", pa.string()),
        pa.field("amount1_raw", pa.string()),
        pa.field("initialization_type", pa.string()),
        pa.field("salt", pa.string()),
        pa.field("observation_status", pa.string(), nullable=False),
        pa.field("source_id", pa.string(), nullable=False),
    ]),
    "lifecycle_events": pa.schema(COMMON + [
        pa.field("lifecycle_event_id", pa.string(), nullable=False),
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("pool_id", pa.string()),
        pa.field("event_type", pa.string(), nullable=False),
        pa.field("event_at", pa.timestamp("us", tz="UTC")),
        pa.field("block_number", pa.int64()),
        pa.field("transaction_hash", pa.string()),
        pa.field("log_index", pa.int64()),
        pa.field("observation_status", pa.string(), nullable=False),
        pa.field("source_id", pa.string(), nullable=False),
    ]),
    "token_metadata": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("description", pa.string()),
        pa.field("image_url", pa.string()),
        pa.field("website_url", pa.string()),
        pa.field("twitter_url", pa.string()),
        pa.field("telegram_url", pa.string()),
        pa.field("category", pa.string()),
        pa.field("source_id", pa.string(), nullable=False),
    ]),
    "token_state_snapshots": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("observed_at", pa.timestamp("us", tz="UTC")),
        pa.field("status", pa.string()),
        pa.field("progress_percent", pa.float64()),
        pa.field("price_native", pa.float64()),
        pa.field("market_cap_native", pa.float64()),
        pa.field("market_cap_usd", pa.float64()),
        pa.field("volume_24h_native", pa.float64()),
        pa.field("volume_24h_usd", pa.float64()),
        pa.field("holder_count", pa.int64()),
        pa.field("pool_address", pa.string()),
        pa.field("source_id", pa.string(), nullable=False),
        pa.field("coverage_role", pa.string(), nullable=False),
    ]),
    "coverage_ledger": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("launch_available", pa.bool_(), nullable=False),
        pa.field("metadata_available", pa.bool_(), nullable=False),
        pa.field("state_snapshot_available", pa.bool_(), nullable=False),
        pa.field("decoded_swaps_available", pa.bool_(), nullable=False),
        pa.field("creator_status", pa.string(), nullable=False),
        pa.field("protocol_config_status", pa.string(), nullable=False),
        pa.field("pool_mapping_status", pa.string(), nullable=False),
        pa.field("pool_initialization_status", pa.string(), nullable=False),
        pa.field("liquidity_initialization_status", pa.string(), nullable=False),
        pa.field("graduation_status", pa.string(), nullable=False),
        pa.field("migration_status", pa.string(), nullable=False),
        pa.field("decoded_swaps_status", pa.string(), nullable=False),
        pa.field("holder_data_status", pa.string(), nullable=False),
        pa.field("trading_data_status", pa.string(), nullable=False),
        pa.field("coverage_status", pa.string(), nullable=False),
        pa.field("limitation", pa.string()),
    ]),
}


def write_table(path: Path, rows: Iterable[dict[str, Any]], schema: pa.Schema) -> int:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(materialized, schema=schema), path, compression="zstd")
    return len(materialized)


class BatchedParquetSink:
    def __init__(self, output: Path, batch_size: int = 5_000) -> None:
        self.output = output
        self.batch_size = batch_size
        self.buffers: dict[str, list[dict[str, Any]]] = {name: [] for name in SCHEMAS}
        self.writers: dict[str, pq.ParquetWriter] = {}
        self.counts = {name: 0 for name in SCHEMAS}
        self.temporary_paths: dict[str, Path] = {}
        for name in SCHEMAS:
            target = output / name / "part-00000.parquet"
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.tmp")
            temporary.unlink(missing_ok=True)
            self.temporary_paths[name] = temporary

    def __call__(self, table_name: str, row: dict[str, Any]) -> None:
        buffer = self.buffers[table_name]
        buffer.append(row)
        self.counts[table_name] += 1
        if len(buffer) >= self.batch_size:
            self._flush(table_name)

    def _flush(self, table_name: str) -> None:
        buffer = self.buffers[table_name]
        if not buffer:
            return
        writer = self.writers.get(table_name)
        if writer is None:
            writer = pq.ParquetWriter(
                self.temporary_paths[table_name],
                SCHEMAS[table_name],
                compression="zstd",
            )
            self.writers[table_name] = writer
        writer.write_table(pa.Table.from_pylist(buffer, schema=SCHEMAS[table_name]))
        buffer.clear()

    def finish(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for table_name in SCHEMAS:
            self._flush(table_name)
            writer = self.writers.get(table_name)
            temporary = self.temporary_paths[table_name]
            if writer is not None:
                writer.close()
            else:
                pq.write_table(
                    pa.Table.from_pylist([], schema=SCHEMAS[table_name]),
                    temporary,
                    compression="zstd",
                )
            target = self.output / table_name / "part-00000.parquet"
            temporary.replace(target)
            result[table_name] = {"rows": self.counts[table_name], "sha256": sha256(target)}
        self.writers.clear()
        return result

    def abort(self) -> None:
        for writer in self.writers.values():
            writer.close()
        self.writers.clear()
        for temporary in self.temporary_paths.values():
            temporary.unlink(missing_ok=True)


def common(chain: str, platform: str) -> dict[str, str]:
    return {"dataset_version": VERSION, "chain_id": chain, "platform_id": platform}


def evm_token_id(chain: str, address: str) -> str:
    return f"{chain}/token:{address.lower()}"


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return list(iter_jsonl(path))


def build_base(source: Path, pool_events_path: Path | None) -> dict[str, list[dict[str, Any]]]:
    source_id = "base_public_rpc_clanker_token_created"
    pool_source_id = "base_pool_manager_launch_core_events"
    with source.open(newline="", encoding="utf-8") as handle:
        raw = list(csv.DictReader(handle))
    raw.sort(key=lambda row: (integer(row["block_number"]) or 0, integer(row["log_index"]) or 0))
    tables = {name: [] for name in SCHEMAS}
    pool_events = load_jsonl(pool_events_path) if pool_events_path and pool_events_path.exists() else []
    initialize_by_pool = {row["pool_id"]: row for row in pool_events if row["event_type"] == "pool_initialized"}
    liquidity_by_pool: dict[str, list[dict[str, Any]]] = {}
    for event in pool_events:
        if event["event_type"] == "initial_liquidity_modified":
            liquidity_by_pool.setdefault(event["pool_id"], []).append(event)
    seen: set[str] = set()
    for row in raw:
        address = row["token_id"].lower()
        token = evm_token_id(BASE_CHAIN, address)
        if token in seen:
            continue
        seen.add(token)
        base = common(BASE_CHAIN, "clanker")
        created = timestamp(row.get("block_timestamp_utc"))
        tables["tokens"].append(base | {
            "token_id": token, "address": address, "symbol": None, "name": None,
            "creator": row.get("token_admin") or None, "created_at": created, "decimals": None,
            "total_supply_raw": row.get("extensions_supply_raw") or None, "source_id": source_id,
            "source_record_id": row.get("event_id") or None,
        })
        tables["launches"].append(base | {
            "launch_id": f"{token}/launch:{row['transaction_hash'].lower()}:{row['log_index']}",
            "token_id": token, "launch_at": created, "block_number": integer(row.get("block_number")),
            "transaction_hash": row.get("transaction_hash"), "log_index": integer(row.get("log_index")),
            "factory_or_manager": "0xe85a59c628f7d27878aceb4bf3b35733630083a9",
            "pool_id": row.get("pool_id") or None, "pool_address": None,
            "paired_token": row.get("paired_token") or None,
            "protocol_version": row.get("clanker_version_class") or None,
            "launch_status": "created", "source_id": source_id, "coverage_role": "authoritative_window",
        })
        tables["protocol_config"].append(base | {
            "token_id": token, "creator": row.get("token_admin") or None,
            "message_sender": row.get("msg_sender") or None, "starting_tick": integer(row.get("starting_tick")),
            "pool_hook": row.get("pool_hook") or None, "pool_hook_label": row.get("pool_hook_label") or None,
            "locker": row.get("locker") or None, "mev_module": row.get("mev_module") or None,
            "mev_module_label": row.get("mev_module_label") or None,
            "extensions_supply_raw": row.get("extensions_supply_raw") or None,
            "protocol_version": row.get("clanker_version_class") or None,
            "manager_address": "0xe85a59c628f7d27878aceb4bf3b35733630083a9",
            "implementation_address": None, "token_index": None, "request_id": None,
            "launch_fee_raw": None, "version_status": "observed", "module_status": "observed",
            "observation_status": "observed", "source_id": source_id,
        })
        pool_id = row["pool_id"].lower()
        initialized = initialize_by_pool.get(pool_id)
        liquidities = sorted(liquidity_by_pool.get(pool_id, []), key=lambda event: event["log_index"])
        positive_liquidities = [event for event in liquidities if int(event["liquidity_delta"]) > 0]
        init_at = timestamp(initialized.get("block_timestamp_unix")) if initialized else None
        tables["pools"].append(base | {
            "token_id": token, "pool_id": pool_id,
            "pool_manager": initialized.get("pool_manager") if initialized else "0x498581ff718922c3f8e6a244956af099b2652b2b",
            "currency0": initialized.get("currency0") if initialized else None,
            "currency1": initialized.get("currency1") if initialized else None,
            "fee_hundredths_bip": integer(initialized.get("fee")) if initialized else None,
            "tick_spacing": integer(initialized.get("tick_spacing")) if initialized else None,
            "hooks": initialized.get("hooks") if initialized else None,
            "sqrt_price_x96": initialized.get("sqrt_price_x96") if initialized else None,
            "initial_tick": integer(initialized.get("initial_tick")) if initialized else None,
            "initialized_at": init_at,
            "initialization_transaction_hash": initialized.get("transaction_hash") if initialized else None,
            "initialization_log_index": integer(initialized.get("log_index")) if initialized else None,
            "mapping_status": "observed", "initialization_status": "observed" if initialized else "processed_zero_rows",
            "source_id": pool_source_id if initialized else source_id,
        })
        tables["lifecycle_events"].append(base | {
            "lifecycle_event_id": f"{token}/lifecycle:token_created:{row['transaction_hash']}:{row['log_index']}",
            "token_id": token, "pool_id": pool_id, "event_type": "token_created", "event_at": created,
            "block_number": integer(row.get("block_number")), "transaction_hash": row.get("transaction_hash"),
            "log_index": integer(row.get("log_index")), "observation_status": "observed", "source_id": source_id,
        })
        if initialized:
            tables["lifecycle_events"].append(base | {
                "lifecycle_event_id": f"{token}/lifecycle:pool_initialized:{initialized['transaction_hash']}:{initialized['log_index']}",
                "token_id": token, "pool_id": pool_id, "event_type": "pool_initialized", "event_at": init_at,
                "block_number": integer(initialized.get("block_number")),
                "transaction_hash": initialized.get("transaction_hash"), "log_index": integer(initialized.get("log_index")),
                "observation_status": "observed", "source_id": pool_source_id,
            })
        for event in liquidities:
            event_at = timestamp(event.get("block_timestamp_unix"))
            event_id = f"{token}/liquidity:{event['transaction_hash']}:{event['log_index']}"
            if int(event["liquidity_delta"]) > 0:
                tables["liquidity_initializations"].append(base | {
                    "liquidity_event_id": event_id, "token_id": token, "pool_id": pool_id, "event_at": event_at,
                    "block_number": integer(event.get("block_number")), "transaction_hash": event.get("transaction_hash"),
                    "log_index": integer(event.get("log_index")), "sender": event.get("sender"),
                    "tick_lower": integer(event.get("tick_lower")), "tick_upper": integer(event.get("tick_upper")),
                    "liquidity_delta_raw": event.get("liquidity_delta"), "salt": event.get("salt"),
                    "observation_status": "observed", "source_id": pool_source_id,
                })
            tables["lifecycle_events"].append(base | {
                "lifecycle_event_id": event_id, "token_id": token, "pool_id": pool_id,
                "event_type": "initial_liquidity_added" if int(event["liquidity_delta"]) > 0 else "liquidity_position_poked",
                "event_at": event_at, "block_number": integer(event.get("block_number")),
                "transaction_hash": event.get("transaction_hash"), "log_index": integer(event.get("log_index")),
                "observation_status": "observed", "source_id": pool_source_id,
            })
        tables["coverage_ledger"].append(base | {
            "token_id": token, "launch_available": True, "metadata_available": False,
            "state_snapshot_available": False, "decoded_swaps_available": False,
            "creator_status": "observed", "protocol_config_status": "observed",
            "pool_mapping_status": "observed",
            "pool_initialization_status": "observed" if initialized else "processed_zero_rows",
            "liquidity_initialization_status": "observed" if positive_liquidities else "processed_zero_rows",
            "graduation_status": "not_applicable", "migration_status": "not_applicable",
            "decoded_swaps_status": "not_collected_by_policy", "holder_data_status": "not_collected_by_policy",
            "trading_data_status": "not_collected_by_policy",
            "coverage_status": "canonical_core_complete" if initialized and liquidities else "canonical_core_partial",
            "limitation": "Core covers the declared launch window. Clanker v4 launches directly into Uniswap v4, so bonding curve graduation and migration are not applicable. Trading outcomes are excluded by policy.",
        })
    return tables


def metadata_index(path: Path | None, field: str) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    return {str(row[field]).lower(): row for row in load_jsonl(path) if row.get(field)}


def build_fourmeme(
    source: Path,
    lifecycle_path: Path,
    metadata_path: Path | None,
    existing_pool_path: Path | None = None,
    historical_pool_path: Path | None = None,
    sink: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    source_id = "fourmeme_bsc_archive_rpc_contract_events"
    lifecycle_source_id = "fourmeme_bsc_lifecycle_receipts"
    metadata_source_id = "fourmeme_official_public_token_search"
    tables = {name: [] for name in SCHEMAS}
    metadata = metadata_index(metadata_path, "tokenAddress")
    lifecycle_rows = load_jsonl(lifecycle_path) if lifecycle_path.exists() else []
    lifecycle_by_token = {row["token_address"].lower(): row for row in lifecycle_rows}
    existing_pool_rows = load_jsonl(existing_pool_path) if existing_pool_path and existing_pool_path.exists() else []
    existing_pool_by_token = {
        row["token_address"].lower(): row
        for row in existing_pool_rows
        if row.get("mapping_status") == "observed" and row.get("pool_address")
    }
    historical_pool_rows = load_jsonl(historical_pool_path) if historical_pool_path and historical_pool_path.exists() else []
    historical_pool_by_token = {
        row["token_address"].lower(): row
        for row in historical_pool_rows
        if row.get("initialization_status") == "observed" and row.get("pool_address_matches_lifecycle")
    }

    def emit(table_name: str, output_row: dict[str, Any]) -> None:
        if sink is None:
            tables[table_name].append(output_row)
        else:
            sink(table_name, output_row)

    for row in iter_jsonl(source):
        address = row["token_address"].lower()
        token = evm_token_id(BNB_CHAIN, address)
        base = common(BNB_CHAIN, "four_meme")
        created = timestamp(row.get("launch_time_unix"))
        lifecycle = lifecycle_by_token.get(address)
        historical_pool = historical_pool_by_token.get(address)
        existing_pool = existing_pool_by_token.get(address)
        pool = (lifecycle.get("pool_address") if lifecycle else None) or (existing_pool.get("pool_address") if existing_pool else None)
        quote = None
        if lifecycle:
            quote = lifecycle.get("quote_address")
            if quote and quote.lower() == ZERO_EVM_ADDRESS:
                quote = WBNB
            if existing_pool:
                quote = existing_pool.get("normalized_quote_address") or quote
        api = metadata.get(address)
        emit("tokens", base | {
            "token_id": token, "address": address, "symbol": row.get("symbol"), "name": row.get("name"),
            "creator": row.get("creator"), "created_at": created, "decimals": None,
            "total_supply_raw": row.get("total_supply_raw"), "source_id": source_id,
            "source_record_id": row.get("request_id"),
        })
        emit("launches", base | {
            "launch_id": f"{token}/launch:{row['transaction_hash']}:{row['log_index']}",
            "token_id": token, "launch_at": created, "block_number": integer(row.get("block_number")),
            "transaction_hash": row.get("transaction_hash"), "log_index": integer(row.get("log_index")),
            "factory_or_manager": row.get("manager_address"), "pool_id": pool, "pool_address": pool,
            "paired_token": quote,
            "protocol_version": row.get("manager_version"), "launch_status": "created",
            "source_id": source_id, "coverage_role": "canonical_core",
        })
        emit("protocol_config", base | {
            "token_id": token, "creator": row.get("creator"), "message_sender": None,
            "starting_tick": None, "pool_hook": None, "pool_hook_label": None, "locker": None,
            "mev_module": None, "mev_module_label": None, "extensions_supply_raw": row.get("total_supply_raw"),
            "protocol_version": row.get("manager_version"), "manager_address": row.get("manager_address"),
            "implementation_address": None, "token_index": None, "request_id": row.get("request_id"),
            "launch_fee_raw": row.get("launch_fee_raw"), "version_status": "observed",
            "module_status": "not_applicable", "observation_status": "observed", "source_id": source_id,
        })
        emit("lifecycle_events", base | {
            "lifecycle_event_id": f"{token}/lifecycle:token_created:{row['transaction_hash']}:{row['log_index']}",
            "token_id": token, "pool_id": pool, "event_type": "token_created", "event_at": created,
            "block_number": integer(row.get("block_number")), "transaction_hash": row.get("transaction_hash"),
            "log_index": integer(row.get("log_index")), "observation_status": "observed", "source_id": source_id,
        })
        if lifecycle:
            lifecycle_at = timestamp(lifecycle.get("block_timestamp_unix"))
            event_type = "liquidity_added" if lifecycle["event_name"] == "LiquidityAdded" else "trade_stopped"
            emit("lifecycle_events", base | {
                "lifecycle_event_id": f"{token}/lifecycle:{event_type}:{lifecycle['transaction_hash']}:{lifecycle['log_index']}",
                "token_id": token, "pool_id": pool, "event_type": event_type, "event_at": lifecycle_at,
                "block_number": integer(lifecycle.get("block_number")), "transaction_hash": lifecycle.get("transaction_hash"),
                "log_index": integer(lifecycle.get("log_index")), "observation_status": "observed",
                "source_id": lifecycle_source_id,
            })
            if pool:
                pool_mapping_source = lifecycle_source_id if lifecycle.get("pool_address") else "fourmeme_pancake_v2_getpair_snapshot"
                pair_created = lifecycle.get("pair_created_log_index") is not None or historical_pool is not None
                pool_initialized_at = lifecycle_at if lifecycle.get("pair_created_log_index") is not None else timestamp(historical_pool.get("creation_block_timestamp_unix")) if historical_pool else None
                pool_initialization_tx = lifecycle.get("transaction_hash") if lifecycle.get("pair_created_log_index") is not None else historical_pool.get("creation_transaction_hash") if historical_pool else None
                pool_initialization_log = lifecycle.get("pair_created_log_index") if lifecycle.get("pair_created_log_index") is not None else historical_pool.get("creation_log_index") if historical_pool else None
                pool_initialization_source = lifecycle_source_id if lifecycle.get("pair_created_log_index") is not None else "fourmeme_pancake_pool_historical_initializations"
                emit("pools", base | {
                    "token_id": token, "pool_id": pool, "pool_address": pool, "pool_manager": None,
                    "currency0": lifecycle.get("currency0") or (existing_pool.get("currency0") if existing_pool else None),
                    "currency1": lifecycle.get("currency1") or (existing_pool.get("currency1") if existing_pool else None),
                    "fee_hundredths_bip": integer(lifecycle.get("fee_hundredths_bip") or (historical_pool.get("fee") if historical_pool else None)),
                    "tick_spacing": integer(lifecycle.get("tick_spacing") or (historical_pool.get("tick_spacing") if historical_pool else None)),
                    "hooks": None, "sqrt_price_x96": None,
                    "initial_tick": None, "initialized_at": pool_initialized_at,
                    "initialization_transaction_hash": pool_initialization_tx,
                    "initialization_log_index": integer(pool_initialization_log),
                    "mapping_status": "observed", "initialization_status": "observed" if pair_created else "not_collected",
                    "source_id": pool_initialization_source if pair_created else pool_mapping_source,
                })
                if pair_created:
                    emit("lifecycle_events", base | {
                        "lifecycle_event_id": f"{token}/lifecycle:pool_initialized:{pool_initialization_tx}:{pool_initialization_log}",
                        "token_id": token, "pool_id": pool, "event_type": "pool_initialized",
                        "event_at": pool_initialized_at,
                        "block_number": integer(lifecycle.get("block_number")) if lifecycle.get("pair_created_log_index") is not None else integer(historical_pool.get("creation_block_number")),
                        "transaction_hash": pool_initialization_tx, "log_index": integer(pool_initialization_log),
                        "observation_status": "observed", "source_id": pool_initialization_source,
                    })
            if pool and lifecycle["event_name"] == "LiquidityAdded":
                amount0 = lifecycle.get("amount0_raw")
                amount1 = lifecycle.get("amount1_raw")
                liquidity_log_index = lifecycle.get("liquidity_mint_log_index")
                liquidity_sender = lifecycle.get("liquidity_sender")
                initialization_type = f"{lifecycle.get('amm_version', 'pancake_v2')}_mint"
                if amount0 is None and existing_pool:
                    base_is_currency0 = address == existing_pool.get("currency0")
                    amount0 = lifecycle.get("offers_raw") if base_is_currency0 else lifecycle.get("funds_raw")
                    amount1 = lifecycle.get("funds_raw") if base_is_currency0 else lifecycle.get("offers_raw")
                    liquidity_log_index = lifecycle.get("log_index")
                    initialization_type = "fourmeme_liquidity_added"
                emit("liquidity_initializations", base | {
                    "liquidity_event_id": f"{token}/liquidity:{lifecycle['transaction_hash']}:{liquidity_log_index}",
                    "token_id": token, "pool_id": pool, "event_at": lifecycle_at,
                    "block_number": integer(lifecycle.get("block_number")), "transaction_hash": lifecycle.get("transaction_hash"),
                    "log_index": integer(liquidity_log_index), "sender": liquidity_sender,
                    "tick_lower": None, "tick_upper": None, "liquidity_delta_raw": None, "salt": None,
                    "amount0_raw": amount0, "amount1_raw": amount1,
                    "initialization_type": initialization_type, "observation_status": "observed",
                    "source_id": lifecycle_source_id,
                })
                emit("lifecycle_events", base | {
                    "lifecycle_event_id": f"{token}/lifecycle:initial_liquidity_added:{lifecycle['transaction_hash']}:{liquidity_log_index}",
                    "token_id": token, "pool_id": pool, "event_type": "initial_liquidity_added", "event_at": lifecycle_at,
                    "block_number": integer(lifecycle.get("block_number")), "transaction_hash": lifecycle.get("transaction_hash"),
                    "log_index": integer(liquidity_log_index), "observation_status": "observed", "source_id": lifecycle_source_id,
                })
        if api:
            emit("token_metadata", base | {
                "token_id": token, "description": None, "image_url": api.get("img"), "website_url": None,
                "twitter_url": None, "telegram_url": None, "category": api.get("tag"), "source_id": metadata_source_id,
            })
        applicable = bool(lifecycle)
        mapped = bool(pool)
        pool_initialized = bool(lifecycle and (lifecycle.get("pair_created_log_index") is not None or historical_pool is not None))
        liquid = bool(lifecycle and lifecycle["event_name"] == "LiquidityAdded" and pool)
        v2_graduation = bool(lifecycle and lifecycle["event_name"] == "LiquidityAdded")
        emit("coverage_ledger", base | {
            "token_id": token, "launch_available": True, "metadata_available": bool(api),
            "state_snapshot_available": False, "decoded_swaps_available": False,
            "creator_status": "observed", "protocol_config_status": "observed",
            "pool_mapping_status": "observed" if mapped else "not_applicable" if not applicable else "not_collected",
            "pool_initialization_status": "observed" if pool_initialized else "not_applicable" if not applicable else "not_collected",
            "liquidity_initialization_status": "observed" if liquid else "not_applicable" if not applicable else "not_collected",
            "graduation_status": "observed" if v2_graduation else "not_applicable" if not applicable else "not_collected",
            "migration_status": "observed" if mapped else "not_applicable" if not applicable else "not_collected",
            "decoded_swaps_status": "not_collected", "holder_data_status": "not_collected",
            "trading_data_status": "not_collected",
            "coverage_status": "canonical_core_complete" if not applicable or (mapped and pool_initialized and liquid) else "canonical_core_partial",
            "limitation": "TokenCreate and declared lifecycle events are fully scanned. TradeStop is retained as a literal V1 event and is not relabelled as graduation without stronger contract semantics. Trading and holder datasets are outside scope.",
        })
    return tables


def build_sunpump(source: Path, metadata_path: Path | None) -> dict[str, list[dict[str, Any]]]:
    source_id = "sunpump_trongrid_contract_events"
    metadata_source_id = "sunpump_official_public_token_list"
    manager = "TTfvyrAz86hbZk5iDpKD78pqLGgi8C7AAw"
    tables = {name: [] for name in SCHEMAS}
    metadata = metadata_index(metadata_path, "contractAddress")
    rows = load_jsonl(source)
    creates = [row for row in rows if row["event_name"] == "TokenCreate"]
    launched = {row["token_address"]: row for row in rows if row["event_name"] == "TokenLaunched"}
    upgrades = sorted((row for row in rows if row["event_name"] == "NewImplementation"), key=lambda row: row["block_number"])
    if not upgrades:
        raise RuntimeError("SunPump proxy implementation history is missing")
    for row in creates:
        address = row["token_address"]
        token = f"{TRON_CHAIN}/token:{address}"
        base = common(TRON_CHAIN, "sunpump")
        created = timestamp(row.get("block_timestamp"), milliseconds=True)
        lifecycle = launched.get(address)
        pool = lifecycle.get("pool_address") if lifecycle else None
        api = metadata.get(address.lower())
        implementation = upgrades[0]["old_implementation"]
        for upgrade in upgrades:
            if upgrade["block_number"] > row["block_number"]:
                break
            implementation = upgrade["new_implementation"]
        tables["tokens"].append(base | {
            "token_id": token, "address": address, "symbol": api.get("symbol") if api else None,
            "name": api.get("name") if api else None, "creator": row.get("creator"), "created_at": created,
            "decimals": integer(api.get("decimals")) if api else None,
            "total_supply_raw": str(api["totalSupply"]) if api and api.get("totalSupply") is not None else None,
            "source_id": source_id, "source_record_id": str(row.get("token_index")),
        })
        tables["launches"].append(base | {
            "launch_id": f"{token}/launch:{row['transaction_id']}:{row['event_index']}", "token_id": token,
            "launch_at": created, "block_number": integer(row.get("block_number")),
            "transaction_hash": row.get("transaction_id"), "log_index": integer(row.get("event_index")),
            "factory_or_manager": manager, "pool_id": pool, "pool_address": pool, "paired_token": "TRX",
            "protocol_version": implementation, "launch_status": "launched" if lifecycle else "created",
            "source_id": source_id, "coverage_role": "canonical_core",
        })
        tables["protocol_config"].append(base | {
            "token_id": token, "creator": row.get("creator"), "message_sender": None,
            "starting_tick": None, "pool_hook": None, "pool_hook_label": None, "locker": None,
            "mev_module": None, "mev_module_label": None, "extensions_supply_raw": None,
            "protocol_version": implementation, "manager_address": manager, "implementation_address": implementation,
            "token_index": integer(row.get("token_index")), "request_id": None, "launch_fee_raw": None,
            "version_status": "observed", "module_status": "not_applicable",
            "observation_status": "observed", "source_id": source_id,
        })
        tables["lifecycle_events"].append(base | {
            "lifecycle_event_id": f"{token}/lifecycle:token_created:{row['transaction_id']}:{row['event_index']}",
            "token_id": token, "pool_id": pool, "event_type": "token_created", "event_at": created,
            "block_number": integer(row.get("block_number")), "transaction_hash": row.get("transaction_id"),
            "log_index": integer(row.get("event_index")), "observation_status": "observed", "source_id": source_id,
        })
        if lifecycle:
            launched_at = timestamp(lifecycle.get("block_timestamp"), milliseconds=True)
            tables["lifecycle_events"].append(base | {
                "lifecycle_event_id": f"{token}/lifecycle:token_launched:{lifecycle['transaction_id']}:{lifecycle['event_index']}",
                "token_id": token, "pool_id": pool, "event_type": "token_launched", "event_at": launched_at,
                "block_number": integer(lifecycle.get("block_number")), "transaction_hash": lifecycle.get("transaction_id"),
                "log_index": integer(lifecycle.get("event_index")), "observation_status": "observed", "source_id": source_id,
            })
            if pool:
                tables["pools"].append(base | {
                    "token_id": token, "pool_id": pool, "pool_address": pool, "pool_manager": None,
                    "currency0": lifecycle.get("currency0"), "currency1": lifecycle.get("currency1"),
                    "fee_hundredths_bip": None, "tick_spacing": None, "hooks": None, "sqrt_price_x96": None,
                    "initial_tick": None, "initialized_at": launched_at,
                    "initialization_transaction_hash": lifecycle.get("transaction_id"),
                    "initialization_log_index": integer(lifecycle.get("pair_created_event_index")),
                    "mapping_status": "observed", "initialization_status": "observed", "source_id": source_id,
                })
                tables["lifecycle_events"].append(base | {
                    "lifecycle_event_id": f"{token}/lifecycle:pool_initialized:{lifecycle['transaction_id']}:{lifecycle['pair_created_event_index']}",
                    "token_id": token, "pool_id": pool, "event_type": "pool_initialized", "event_at": launched_at,
                    "block_number": integer(lifecycle.get("block_number")), "transaction_hash": lifecycle.get("transaction_id"),
                    "log_index": integer(lifecycle.get("pair_created_event_index")), "observation_status": "observed", "source_id": source_id,
                })
            if pool and "amount0_raw" in lifecycle:
                tables["liquidity_initializations"].append(base | {
                    "liquidity_event_id": f"{token}/liquidity:{lifecycle['transaction_id']}:{lifecycle['liquidity_mint_event_index']}",
                    "token_id": token, "pool_id": pool, "event_at": launched_at,
                    "block_number": integer(lifecycle.get("block_number")), "transaction_hash": lifecycle.get("transaction_id"),
                    "log_index": integer(lifecycle.get("liquidity_mint_event_index")), "sender": None,
                    "tick_lower": None, "tick_upper": None, "liquidity_delta_raw": None, "salt": None,
                    "amount0_raw": lifecycle.get("amount0_raw"), "amount1_raw": lifecycle.get("amount1_raw"),
                    "initialization_type": "sunswap_v2_mint", "observation_status": "observed", "source_id": source_id,
                })
                tables["lifecycle_events"].append(base | {
                    "lifecycle_event_id": f"{token}/lifecycle:initial_liquidity_added:{lifecycle['transaction_id']}:{lifecycle['liquidity_mint_event_index']}",
                    "token_id": token, "pool_id": pool, "event_type": "initial_liquidity_added", "event_at": launched_at,
                    "block_number": integer(lifecycle.get("block_number")), "transaction_hash": lifecycle.get("transaction_id"),
                    "log_index": integer(lifecycle.get("liquidity_mint_event_index")), "observation_status": "observed", "source_id": source_id,
                })
        if api:
            tables["token_metadata"].append(base | {
                "token_id": token, "description": api.get("description"), "image_url": api.get("logoUrl"),
                "website_url": api.get("websiteUrl"), "twitter_url": api.get("twitterUrl"),
                "telegram_url": api.get("telegramUrl"), "category": api.get("tokenFlag"), "source_id": metadata_source_id,
            })
        applicable = bool(lifecycle)
        mapped = bool(pool)
        liquid = bool(lifecycle and "amount0_raw" in lifecycle)
        tables["coverage_ledger"].append(base | {
            "token_id": token, "launch_available": True, "metadata_available": bool(api),
            "state_snapshot_available": False, "decoded_swaps_available": False,
            "creator_status": "observed", "protocol_config_status": "observed",
            "pool_mapping_status": "observed" if mapped else "not_applicable" if not applicable else "not_collected",
            "pool_initialization_status": "observed" if mapped else "not_applicable" if not applicable else "not_collected",
            "liquidity_initialization_status": "observed" if liquid else "not_applicable" if not applicable else "not_collected",
            "graduation_status": "observed" if applicable else "not_applicable",
            "migration_status": "observed" if mapped else "not_applicable" if not applicable else "not_collected",
            "decoded_swaps_status": "not_collected", "holder_data_status": "not_collected",
            "trading_data_status": "not_collected",
            "coverage_status": "canonical_core_complete" if not applicable or (mapped and liquid) else "canonical_core_partial",
            "limitation": "TokenCreate, TokenLaunched, and NewImplementation are fully fingerprint paginated. Historical implementation is mapped by launch block. Modular launch configuration is not applicable. Trading and holder datasets are outside scope.",
        })
    return tables


def build_release(
    name: str,
    source: Path,
    output: Path,
    tables: dict[str, list[dict[str, Any]]],
    auxiliary_sources: list[Path],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for table_name, rows in tables.items():
        target = output / table_name / "part-00000.parquet"
        count = write_table(target, rows, SCHEMAS[table_name])
        result[table_name] = {"rows": count, "sha256": sha256(target)}
    manifest = {
        "release": VERSION,
        "release_name": name,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(source), "rows": sum(1 for _ in source.open(encoding="utf-8")) - (1 if source.suffix == ".csv" else 0), "sha256": sha256(source)},
        "tables": result,
    }
    manifest["auxiliary_sources"] = [
        {"path": str(path), "rows": sum(1 for _ in path.open(encoding="utf-8")), "sha256": sha256(path)}
        for path in auxiliary_sources if path.exists()
    ]
    manifest["canonical_core_coverage"] = summarize_coverage(
        tables["coverage_ledger"], len(tables["tokens"])
    )
    return manifest


def empty_coverage_summary(launch_universe: int = 0) -> dict[str, int]:
    return {
        "launch_universe": launch_universe,
        "creator_observed": 0,
        "protocol_config_observed": 0,
        "pool_mapping_observed": 0,
        "pool_mapping_not_collected": 0,
        "pool_mapping_not_applicable": 0,
        "pool_initialization_observed": 0,
        "liquidity_initialization_observed": 0,
        "graduation_observed": 0,
        "graduation_not_collected": 0,
        "graduation_not_applicable": 0,
        "migration_observed": 0,
        "migration_not_collected": 0,
        "migration_not_applicable": 0,
        "decoded_swaps_not_collected": 0,
    }


def update_coverage_summary(summary: dict[str, int], row: dict[str, Any]) -> None:
    summary["creator_observed"] += row["creator_status"] == "observed"
    summary["protocol_config_observed"] += row["protocol_config_status"] == "observed"
    summary["pool_mapping_observed"] += row["pool_mapping_status"] == "observed"
    summary["pool_mapping_not_collected"] += row["pool_mapping_status"] == "not_collected"
    summary["pool_mapping_not_applicable"] += row["pool_mapping_status"] == "not_applicable"
    summary["pool_initialization_observed"] += row["pool_initialization_status"] == "observed"
    summary["liquidity_initialization_observed"] += row["liquidity_initialization_status"] == "observed"
    summary["graduation_observed"] += row["graduation_status"] == "observed"
    summary["graduation_not_collected"] += row["graduation_status"] == "not_collected"
    summary["graduation_not_applicable"] += row["graduation_status"] == "not_applicable"
    summary["migration_observed"] += row["migration_status"] == "observed"
    summary["migration_not_collected"] += row["migration_status"] == "not_collected"
    summary["migration_not_applicable"] += row["migration_status"] == "not_applicable"
    summary["decoded_swaps_not_collected"] += row["decoded_swaps_status"].startswith("not_collected")


def summarize_coverage(rows: Iterable[dict[str, Any]], launch_universe: int) -> dict[str, int]:
    summary = empty_coverage_summary(launch_universe)
    for row in rows:
        update_coverage_summary(summary, row)
    return summary


def build_fourmeme_release(
    source: Path,
    lifecycle_path: Path,
    metadata_path: Path | None,
    existing_pool_path: Path | None,
    historical_pool_path: Path | None,
    output: Path,
    auxiliary_sources: list[Path],
) -> dict[str, Any]:
    parquet_sink = BatchedParquetSink(output)
    coverage = empty_coverage_summary()

    def sink(table_name: str, row: dict[str, Any]) -> None:
        parquet_sink(table_name, row)
        if table_name == "coverage_ledger":
            update_coverage_summary(coverage, row)

    try:
        build_fourmeme(source, lifecycle_path, metadata_path, existing_pool_path, historical_pool_path, sink=sink)
        table_results = parquet_sink.finish()
    except BaseException:
        parquet_sink.abort()
        raise
    coverage["launch_universe"] = table_results["tokens"]["rows"]
    return {
        "release": VERSION,
        "release_name": "bnb",
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(source),
            "rows": table_results["tokens"]["rows"],
            "sha256": sha256(source),
        },
        "tables": table_results,
        "auxiliary_sources": [
            {"path": str(path), "rows": sum(1 for _ in path.open(encoding="utf-8")), "sha256": sha256(path)}
            for path in auxiliary_sources if path.exists()
        ],
        "canonical_core_coverage": coverage,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    repo = args.repo.resolve()
    base_source = repo / "data/external/base/20260811/onchain/clanker_base_token_created.csv"
    base_pool = repo / "data/external/base/20260811/snapshot/pool_core_events.jsonl"
    bnb_root = repo / "data/external/fourmeme/20260811"
    tron_root = repo / "data/external/sunpump/20260811/snapshot"
    releases = repo / "data_pipeline/releases/v1"
    releases.mkdir(parents=True, exist_ok=True)
    configs = [
        ("base", base_source, repo / "data/canonical/v1/base", build_base(base_source, base_pool), [base_pool]),
        ("tron", tron_root / "onchain_core.jsonl", repo / "data/canonical/v1/tron",
         build_sunpump(tron_root / "onchain_core.jsonl", tron_root / "tokens.jsonl"),
         [tron_root / "ONCHAIN_SOURCE.json", tron_root / "tokens.jsonl"]),
    ]
    for name, source, output, tables, auxiliaries in configs:
        manifest = build_release(name, source, output, tables, auxiliaries)
        manifest["source"]["path"] = source.relative_to(repo).as_posix()
        for auxiliary in manifest["auxiliary_sources"]:
            auxiliary["path"] = Path(auxiliary["path"]).relative_to(repo).as_posix()
        (releases / f"{name}_core.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"release": name, "tables": manifest["tables"]}, indent=2))

    bnb_source = bnb_root / "onchain/onchain_launches.jsonl"
    bnb_auxiliaries = [
        bnb_root / "onchain/ONCHAIN_SOURCE.json",
        bnb_root / "onchain/lifecycle_core.jsonl",
        bnb_root / "onchain/existing_pool_mappings_v2.jsonl",
        bnb_root / "onchain/historical_pool_initializations.jsonl",
        bnb_root / "snapshot/tokens.jsonl",
    ]
    bnb_manifest = build_fourmeme_release(
        bnb_source,
        bnb_root / "onchain/lifecycle_core.jsonl",
        bnb_root / "snapshot/tokens.jsonl",
        bnb_root / "onchain/existing_pool_mappings_v2.jsonl",
        bnb_root / "onchain/historical_pool_initializations.jsonl",
        repo / "data/canonical/v1/bnb",
        bnb_auxiliaries,
    )
    bnb_manifest["source"]["path"] = bnb_source.relative_to(repo).as_posix()
    for auxiliary in bnb_manifest["auxiliary_sources"]:
        auxiliary["path"] = Path(auxiliary["path"]).relative_to(repo).as_posix()
    (releases / "bnb_core.json").write_text(json.dumps(bnb_manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"release": "bnb", "tables": bnb_manifest["tables"]}, indent=2))


if __name__ == "__main__":
    main()
