from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq


CHAIN_ID = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
PLATFORM_ID = "pump_fun"
RELEASE = "v1"
BATCH_SIZE = 50_000


def token_id(mint: str) -> str:
    return f"{CHAIN_ID}/token:{mint}"


def parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def as_int(value: Any) -> int | None:
    number = as_float(value)
    return None if number is None else int(number)


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BatchWriter:
    def __init__(self, path: Path, schema: pa.Schema) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.schema = schema
        self.writer = pq.ParquetWriter(path, schema, compression="zstd")
        self.rows: list[dict[str, Any]] = []
        self.count = 0

    def append(self, row: dict[str, Any]) -> None:
        self.rows.append(row)
        if len(self.rows) >= BATCH_SIZE:
            self.flush()

    def flush(self) -> None:
        if not self.rows:
            return
        table = pa.Table.from_pylist(self.rows, schema=self.schema)
        self.writer.write_table(table)
        self.count += len(self.rows)
        self.rows.clear()

    def close(self) -> None:
        self.flush()
        self.writer.close()


COMMON = [
    pa.field("dataset_version", pa.string(), nullable=False),
    pa.field("chain_id", pa.string(), nullable=False),
    pa.field("platform_id", pa.string(), nullable=False),
]

SCHEMAS = {
    "tokens": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("mint", pa.string(), nullable=False),
        pa.field("symbol", pa.string()),
        pa.field("name", pa.string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
        pa.field("token_program", pa.string()),
        pa.field("creator", pa.string()),
    ]),
    "launches": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("mint", pa.string(), nullable=False),
        pa.field("launch_at", pa.timestamp("us", tz="UTC")),
        pa.field("observed_at", pa.timestamp("us", tz="UTC")),
        pa.field("initial_market_cap_sol", pa.float64()),
        pa.field("description_length", pa.int64()),
        pa.field("has_twitter", pa.bool_()),
        pa.field("has_website", pa.bool_()),
        pa.field("has_telegram", pa.bool_()),
        pa.field("social_count", pa.int8()),
        pa.field("source_record_type", pa.string(), nullable=False),
    ]),
    "lifecycle_events": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("mint", pa.string(), nullable=False),
        pa.field("event_type", pa.string(), nullable=False),
        pa.field("event_at", pa.timestamp("us", tz="UTC")),
        pa.field("minutes_from_launch_observed", pa.float64()),
        pa.field("minutes_from_launch_chain", pa.float64()),
        pa.field("final_market_cap_sol", pa.float64()),
        pa.field("detection_lag_minutes", pa.float64()),
        pa.field("source_record_type", pa.string(), nullable=False),
    ]),
    "token_metadata": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("mint", pa.string(), nullable=False),
        pa.field("metadata_status", pa.string()),
        pa.field("metadata_complete", pa.bool_()),
        pa.field("creator", pa.string()),
        pa.field("bonding_curve", pa.string()),
        pa.field("associated_bonding_curve", pa.string()),
        pa.field("pool_address", pa.string()),
        pa.field("token_program", pa.string()),
        pa.field("protocol", pa.string()),
        pa.field("last_trade_at", pa.timestamp("us", tz="UTC")),
        pa.field("ath_market_cap_usd", pa.float64()),
        pa.field("ath_market_cap_at", pa.timestamp("us", tz="UTC")),
        pa.field("current_market_cap_usd", pa.float64()),
        pa.field("total_supply_raw", pa.float64()),
    ]),
    "pool_windows": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("mint", pa.string(), nullable=False),
        pa.field("graduated_at", pa.timestamp("us", tz="UTC")),
        pa.field("horizon_days", pa.int16(), nullable=False),
        pa.field("pool_address", pa.string()),
        pa.field("transaction_proxy_count", pa.int64()),
        pa.field("active_traders", pa.int64()),
        pa.field("volume_usd", pa.float64()),
        pa.field("first_trade_at", pa.timestamp("us", tz="UTC")),
        pa.field("last_trade_at", pa.timestamp("us", tz="UTC")),
        pa.field("signatures_scanned", pa.int64()),
        pa.field("transactions_parsed", pa.int64()),
        pa.field("window_status", pa.string()),
        pa.field("validation_status", pa.string()),
        pa.field("metric_semantics", pa.string(), nullable=False),
    ]),
    "decoded_swaps": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("mint", pa.string(), nullable=False),
        pa.field("graduated_at", pa.timestamp("us", tz="UTC")),
        pa.field("horizon_days", pa.int16(), nullable=False),
        pa.field("transaction_hash", pa.string(), nullable=False),
        pa.field("transaction_index", pa.int64()),
        pa.field("transaction_type", pa.string()),
        pa.field("block_timestamp", pa.timestamp("us", tz="UTC")),
        pa.field("block_number", pa.int64()),
        pa.field("wallet_address", pa.string()),
        pa.field("pair_address", pa.string()),
        pa.field("exchange_name", pa.string()),
        pa.field("bought_token_address", pa.string()),
        pa.field("bought_amount", pa.float64()),
        pa.field("bought_usd_amount", pa.float64()),
        pa.field("sold_token_address", pa.string()),
        pa.field("sold_amount", pa.float64()),
        pa.field("sold_usd_amount", pa.float64()),
        pa.field("total_value_usd", pa.float64()),
        pa.field("source", pa.string()),
    ]),
    "token_horizons": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("mint", pa.string(), nullable=False),
        pa.field("graduated_at", pa.timestamp("us", tz="UTC")),
        pa.field("horizon_days", pa.int16(), nullable=False),
        pa.field("decoded_trade_count", pa.int64()),
        pa.field("decoded_buy_count", pa.int64()),
        pa.field("decoded_sell_count", pa.int64()),
        pa.field("decoded_volume_usd", pa.float64()),
        pa.field("decoded_active_traders", pa.int64()),
        pa.field("first_decoded_trade_at", pa.timestamp("us", tz="UTC")),
        pa.field("last_decoded_trade_at", pa.timestamp("us", tz="UTC")),
        pa.field("window_status", pa.string()),
        pa.field("swaps_fetched", pa.int64()),
        pa.field("pages_fetched", pa.int64()),
        pa.field("is_complete_window", pa.bool_(), nullable=False),
        pa.field("source", pa.string()),
    ]),
    "coverage_ledger": pa.schema(COMMON + [
        pa.field("token_id", pa.string(), nullable=False),
        pa.field("mint", pa.string(), nullable=False),
        pa.field("graduated_at", pa.timestamp("us", tz="UTC")),
        pa.field("metadata_available", pa.bool_(), nullable=False),
        pa.field("pool_address_available", pa.bool_(), nullable=False),
        pa.field("rpc_windows_available", pa.int8(), nullable=False),
        pa.field("decoded_windows_available", pa.int8(), nullable=False),
        pa.field("decoded_swaps_available", pa.bool_(), nullable=False),
        pa.field("decoded_windows_complete", pa.int8(), nullable=False),
        pa.field("coverage_status", pa.string(), nullable=False),
    ]),
}


def locate_sources(bundle: Path) -> dict[str, Path]:
    names = {
        "launches": "red_pump_2026_v1_launches.jsonl.gz",
        "outcomes": "red_pump_2026_v1_outcomes.csv.gz",
        "baseline": "red_pump_token_outcomes.csv",
        "metadata": "pumpfun_coin_metadata.csv",
        "pool_windows": "solana_post_migration_pool_windows.csv",
        "swaps": "moralis_token_swaps.csv",
        "horizons": "moralis_decoded_token_outcomes.csv",
        "fetch_status": "moralis_fetch_status.csv",
    }
    result: dict[str, Path] = {}
    for key, name in names.items():
        matches = list(bundle.rglob(name))
        if len(matches) != 1:
            raise RuntimeError(f"Expected one {name}, found {len(matches)}")
        result[key] = matches[0]
    return result


def load_outcomes(path: Path) -> tuple[dict[str, dict[str, str]], Counter[str]]:
    outcomes: dict[str, dict[str, str]] = {}
    quality: Counter[str] = Counter()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            quality["raw_rows"] += 1
            outcome = row.get("outcome", "")
            if outcome not in {"GRADUATED", "TIMEOUT"}:
                quality["malformed_outcome"] += 1
                continue
            minutes = as_float(row.get("minutes_to_outcome"))
            if outcome == "GRADUATED" and (minutes is None or minutes <= 0):
                quality["nonpositive_graduation_time"] += 1
                continue
            mint = row.get("mint", "")
            if not mint:
                quality["missing_mint"] += 1
                continue
            old = outcomes.get(mint)
            if old is None or (old.get("outcome") == "TIMEOUT" and outcome == "GRADUATED"):
                outcomes[mint] = row
    quality["deduped_mints"] = len(outcomes)
    return outcomes, quality


def common() -> dict[str, Any]:
    return {"dataset_version": RELEASE, "chain_id": CHAIN_ID, "platform_id": PLATFORM_ID}


def build_baseline(paths: dict[str, Path], output: Path) -> dict[str, Any]:
    outcomes, outcome_quality = load_outcomes(paths["outcomes"])
    writers = {name: BatchWriter(output / f"{name}.parquet", SCHEMAS[name]) for name in ("tokens", "launches", "lifecycle_events")}
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    with gzip.open(paths["launches"], "rt", encoding="utf-8") as handle:
        for line in handle:
            counts["launch_rows"] += 1
            launch = json.loads(line)
            mint = launch.get("mint", "")
            if not mint or mint in seen:
                counts["duplicate_or_missing_launch_mint"] += 1
                continue
            seen.add(mint)
            outcome = outcomes.get(mint)
            if outcome is None:
                counts["launches_without_terminal_outcome"] += 1
                continue
            tid = token_id(mint)
            created_at = parse_timestamp(launch.get("created_timestamp"))
            observed_at = parse_timestamp(launch.get("seenAt"))
            flags = [as_bool(launch.get(key)) for key in ("has_twitter", "has_website", "has_telegram")]
            base = common()
            writers["tokens"].append(base | {
                "token_id": tid, "mint": mint, "symbol": launch.get("symbol"), "name": launch.get("name"),
                "created_at": created_at, "token_program": None, "creator": None,
            })
            writers["launches"].append(base | {
                "token_id": tid, "mint": mint, "launch_at": created_at, "observed_at": observed_at,
                "initial_market_cap_sol": as_float(launch.get("initial_market_cap_sol")),
                "description_length": as_int(launch.get("description_length")),
                "has_twitter": flags[0], "has_website": flags[1], "has_telegram": flags[2],
                "social_count": sum(flags), "source_record_type": "red_pump_launch",
            })
            event = outcome.get("outcome", "").lower()
            writers["lifecycle_events"].append(base | {
                "token_id": tid, "mint": mint, "event_type": event,
                "event_at": parse_timestamp(outcome.get("graduated_at")),
                "minutes_from_launch_observed": as_float(outcome.get("minutes_to_outcome")),
                "minutes_from_launch_chain": as_float(outcome.get("minutes_to_outcome_chain")),
                "final_market_cap_sol": as_float(outcome.get("final_market_cap_sol")),
                "detection_lag_minutes": as_float(outcome.get("detection_lag_min")),
                "source_record_type": "red_pump_terminal_outcome",
            })
            counts[event] += 1
    for writer in writers.values():
        writer.close()
    counts["unique_launch_mints"] = len(seen)
    counts["joined_rows"] = writers["tokens"].count
    return {"outcomes": dict(outcome_quality), "baseline": dict(counts)}


def csv_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def build_metadata(path: Path, output: Path) -> tuple[dict[str, dict[str, Any]], int]:
    writer = BatchWriter(output / "token_metadata.parquet", SCHEMAS["token_metadata"])
    by_mint: dict[str, dict[str, Any]] = {}
    for row in csv_rows(path):
        mint = row["mint"]
        record = common() | {
            "token_id": token_id(mint), "mint": mint, "metadata_status": row.get("metadata_status"),
            "metadata_complete": as_bool(row.get("complete")), "creator": row.get("creator") or None,
            "bonding_curve": row.get("bonding_curve") or None,
            "associated_bonding_curve": row.get("associated_bonding_curve") or None,
            "pool_address": row.get("pool_address") or None, "token_program": row.get("token_program") or None,
            "protocol": row.get("protocol") or None, "last_trade_at": parse_timestamp(row.get("last_trade_at")),
            "ath_market_cap_usd": as_float(row.get("ath_market_cap")),
            "ath_market_cap_at": parse_timestamp(row.get("ath_market_cap_at")),
            "current_market_cap_usd": as_float(row.get("usd_market_cap")),
            "total_supply_raw": as_float(row.get("total_supply")),
        }
        by_mint[mint] = record
        writer.append(record)
    writer.close()
    return by_mint, writer.count


def build_pool_windows(path: Path, output: Path) -> tuple[Counter[str], int]:
    writer = BatchWriter(output / "pool_windows.parquet", SCHEMAS["pool_windows"])
    by_mint: Counter[str] = Counter()
    for row in csv_rows(path):
        mint = row["mint"]
        writer.append(common() | {
            "token_id": token_id(mint), "mint": mint, "graduated_at": parse_timestamp(row.get("graduated_at")),
            "horizon_days": as_int(row.get("horizon_days")), "pool_address": row.get("pool_address") or None,
            "transaction_proxy_count": as_int(row.get("swap_count")), "active_traders": as_int(row.get("active_traders")),
            "volume_usd": as_float(row.get("volume_usd")), "first_trade_at": parse_timestamp(row.get("first_trade_at")),
            "last_trade_at": parse_timestamp(row.get("last_trade_at")), "signatures_scanned": as_int(row.get("signatures_scanned")),
            "transactions_parsed": as_int(row.get("transactions_parsed")), "window_status": row.get("signature_window_status") or None,
            "validation_status": row.get("validation_status") or None,
            "metric_semantics": "pool transaction proxy; not decoded swaps",
        })
        by_mint[mint] += 1
    writer.close()
    return by_mint, writer.count


def build_swaps(path: Path, output: Path) -> tuple[set[str], int]:
    writer = BatchWriter(output / "decoded_swaps.parquet", SCHEMAS["decoded_swaps"])
    mints: set[str] = set()
    for row in csv_rows(path):
        mint = row["mint"]
        mints.add(mint)
        writer.append(common() | {
            "token_id": token_id(mint), "mint": mint, "graduated_at": parse_timestamp(row.get("graduated_at")),
            "horizon_days": as_int(row.get("horizon_days")), "transaction_hash": row["transaction_hash"],
            "transaction_index": as_int(row.get("transaction_index")), "transaction_type": row.get("transaction_type") or None,
            "block_timestamp": parse_timestamp(row.get("block_timestamp")), "block_number": as_int(row.get("block_number")),
            "wallet_address": row.get("wallet_address") or None, "pair_address": row.get("pair_address") or None,
            "exchange_name": row.get("exchange_name") or None, "bought_token_address": row.get("bought_token_address") or None,
            "bought_amount": as_float(row.get("bought_amount")), "bought_usd_amount": as_float(row.get("bought_usd_amount")),
            "sold_token_address": row.get("sold_token_address") or None, "sold_amount": as_float(row.get("sold_amount")),
            "sold_usd_amount": as_float(row.get("sold_usd_amount")), "total_value_usd": as_float(row.get("total_value_usd")),
            "source": row.get("source") or None,
        })
    writer.close()
    return mints, writer.count


def build_horizons(path: Path, output: Path) -> tuple[dict[str, list[dict[str, Any]]], int]:
    writer = BatchWriter(output / "token_horizons.parquet", SCHEMAS["token_horizons"])
    by_mint: dict[str, list[dict[str, Any]]] = {}
    for row in csv_rows(path):
        mint = row["mint"]
        status = row.get("moralis_window_status") or ""
        record = common() | {
            "token_id": token_id(mint), "mint": mint, "graduated_at": parse_timestamp(row.get("graduated_at")),
            "horizon_days": as_int(row.get("horizon_days")), "decoded_trade_count": as_int(row.get("decoded_trade_count")),
            "decoded_buy_count": as_int(row.get("decoded_buy_count")), "decoded_sell_count": as_int(row.get("decoded_sell_count")),
            "decoded_volume_usd": as_float(row.get("decoded_volume_usd")),
            "decoded_active_traders": as_int(row.get("decoded_active_traders")),
            "first_decoded_trade_at": parse_timestamp(row.get("first_decoded_trade_at")),
            "last_decoded_trade_at": parse_timestamp(row.get("last_decoded_trade_at")), "window_status": status,
            "swaps_fetched": as_int(row.get("moralis_swaps_fetched")), "pages_fetched": as_int(row.get("moralis_pages_fetched")),
            "is_complete_window": status == "ok", "source": row.get("source") or None,
        }
        by_mint.setdefault(mint, []).append(record)
        writer.append(record)
    writer.close()
    return by_mint, writer.count


def graduated_from_events(path: Path) -> dict[str, datetime | None]:
    table = pq.read_table(path, columns=["mint", "event_type", "event_at"])
    result: dict[str, datetime | None] = {}
    for row in table.to_pylist():
        if row["event_type"] == "graduated":
            result[row["mint"]] = row["event_at"]
    return result


def build_coverage(output: Path, metadata: dict[str, dict[str, Any]], pools: Counter[str], swaps: set[str], horizons: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    graduated = graduated_from_events(output / "lifecycle_events.parquet")
    writer = BatchWriter(output / "coverage_ledger.parquet", SCHEMAS["coverage_ledger"])
    status_counts: Counter[str] = Counter()
    for mint, graduated_at in graduated.items():
        hs = horizons.get(mint, [])
        complete = sum(bool(row["is_complete_window"]) for row in hs)
        if not hs:
            status = "no_decoded_swap_data"
        elif complete == len(hs) == 3:
            status = "decoded_complete_1_7_30d"
        else:
            status = "decoded_lower_bound_page_capped"
        status_counts[status] += 1
        meta = metadata.get(mint)
        writer.append(common() | {
            "token_id": token_id(mint), "mint": mint, "graduated_at": graduated_at,
            "metadata_available": meta is not None, "pool_address_available": bool(meta and meta.get("pool_address")),
            "rpc_windows_available": pools[mint], "decoded_windows_available": len(hs),
            "decoded_swaps_available": mint in swaps, "decoded_windows_complete": complete, "coverage_status": status,
        })
    writer.close()
    return {"rows": writer.count, "coverage_status": dict(status_counts)}


def table_stats(output: Path) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for path in sorted(output.glob("*.parquet")):
        metadata = pq.read_metadata(path)
        stats[path.stem] = {"rows": metadata.num_rows, "columns": metadata.num_columns, "sha256": file_sha256(path), "bytes": path.stat().st_size}
    return stats


def write_schema_registry(repo: Path) -> None:
    target = repo / "dataset" / "schemas" / RELEASE
    target.mkdir(parents=True, exist_ok=True)
    registry = {}
    for name, schema in SCHEMAS.items():
        registry[name] = [{"name": field.name, "type": str(field.type), "nullable": field.nullable} for field in schema]
    (target / "schema_registry.json").write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build(repo: Path, bundle: Path, output: Path) -> dict[str, Any]:
    paths = locate_sources(bundle)
    staging = output.with_name(output.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    write_schema_registry(repo)
    quality = build_baseline(paths, staging)
    metadata, metadata_rows = build_metadata(paths["metadata"], staging)
    pools, pool_rows = build_pool_windows(paths["pool_windows"], staging)
    swaps, swap_rows = build_swaps(paths["swaps"], staging)
    horizons, horizon_rows = build_horizons(paths["horizons"], staging)
    coverage = build_coverage(staging, metadata, pools, swaps, horizons)
    quality["solana_core"] = {
        "metadata_rows": metadata_rows, "pool_window_rows": pool_rows, "decoded_swap_rows": swap_rows,
        "decoded_swap_mints": len(swaps), "token_horizon_rows": horizon_rows, "token_horizon_mints": len(horizons),
        "coverage": coverage,
    }
    quality["tables"] = table_stats(staging)
    quality["sources"] = {key: {"path": str(path.relative_to(repo)), "sha256": file_sha256(path), "bytes": path.stat().st_size} for key, path in paths.items()}
    (staging / "quality_report.json").write_text(json.dumps(quality, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if output.exists():
        shutil.rmtree(output)
    staging.rename(output)
    return quality


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    bundle = (args.bundle or repo / "data" / "external" / "pumpswap" / "20260810" / "bundle").resolve()
    output = (args.output or repo / "data" / "canonical" / RELEASE / "solana").resolve()
    quality = build(repo, bundle, output)
    print(json.dumps({"output": str(output), "tables": quality["tables"], "coverage": quality["solana_core"]["coverage"]}, indent=2))


if __name__ == "__main__":
    main()
