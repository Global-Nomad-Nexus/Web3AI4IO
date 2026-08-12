from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from web3ai4io_dataset.collect_fourmeme_events import (
    DEFAULT_RPC_URL,
    PAIR_CREATED_TOPIC,
    POOL_CREATED_V3_TOPIC,
    Rpc,
    address,
    append,
    uint,
    write_json,
)


PANCAKE_V2_FACTORY = "0xca143ce32fe78f1f7019d7d551a6402fc5350c73"
PANCAKE_V3_FACTORY = "0x0bfbcf9fa4f9c56b0f40a671ad40e0805a091865"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_rows(path: Path) -> list[dict[str, Any]]:
    rows = [
        row
        for row in load_jsonl(path)
        if row.get("event_name") == "LiquidityAdded"
        and row.get("pool_address")
        and row.get("pair_created_log_index") is None
    ]
    tokens = [row["token_address"].lower() for row in rows]
    if len(tokens) != len(set(tokens)):
        raise RuntimeError("Historical initialization targets contain duplicate token addresses")
    return rows


def factory_spec(row: dict[str, Any]) -> tuple[str, str, str]:
    version = row.get("amm_version")
    if version == "pancake_v2":
        return PANCAKE_V2_FACTORY, PAIR_CREATED_TOPIC, version
    if version == "pancake_v3":
        return PANCAKE_V3_FACTORY, POOL_CREATED_V3_TOPIC, version
    raise RuntimeError(f"Unsupported AMM version for {row['token_address']}: {version!r}")


def concurrent_rpc_batches(
    rpc_url: str,
    batches: list[list[tuple[str, list[Any]]]],
    workers: int,
) -> list[list[Any]]:
    def execute(calls: list[tuple[str, list[Any]]]) -> list[Any]:
        return Rpc(rpc_url).batch(calls)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(execute, batches))


def find_first_code_blocks(rpc_url: str, rows: list[dict[str, Any]], batch_size: int, workers: int) -> dict[str, int]:
    states = {
        row["token_address"].lower(): {
            "pool": row["pool_address"].lower(),
            "low": 0,
            "high": int(row["block_number"]),
        }
        for row in rows
    }
    values = list(states.values())
    initial_batches = [values[start:start + batch_size] for start in range(0, len(values), batch_size)]
    initial_results = concurrent_rpc_batches(rpc_url, [
        [("eth_getCode", [item["pool"], hex(item["high"])]) for item in batch]
        for batch in initial_batches
    ], workers)
    for batch, results in zip(initial_batches, initial_results):
        for item, code in zip(batch, results):
            if code == "0x":
                raise RuntimeError(f"Pool has no code at lifecycle block: {item['pool']} block={item['high']}")

    round_number = 0
    while True:
        active = [item for item in values if item["low"] < item["high"]]
        if not active:
            break
        round_number += 1
        active_batches = [active[start:start + batch_size] for start in range(0, len(active), batch_size)]
        mids_by_batch = [[(item["low"] + item["high"]) // 2 for item in batch] for batch in active_batches]
        result_batches = concurrent_rpc_batches(rpc_url, [
            [
                ("eth_getCode", [item["pool"], hex(mid)])
                for item, mid in zip(batch, mids)
            ]
            for batch, mids in zip(active_batches, mids_by_batch)
        ], workers)
        for batch, mids, results in zip(active_batches, mids_by_batch, result_batches):
            for item, mid, code in zip(batch, mids, results):
                if code == "0x":
                    item["low"] = mid + 1
                else:
                    item["high"] = mid
        print(f"fourmeme pool history: code-search round={round_number} unresolved={sum(item['low'] < item['high'] for item in values)}", flush=True)
    return {
        token: int(item["low"])
        for token, item in states.items()
    }


def decode_candidate(log: dict[str, Any], version: str) -> dict[str, Any]:
    topics = [value.lower() for value in log["topics"]]
    data = bytes.fromhex(log["data"][2:])
    result: dict[str, Any] = {
        "currency0": "0x" + topics[1][-40:],
        "currency1": "0x" + topics[2][-40:],
        "creation_transaction_hash": log["transactionHash"].lower(),
        "creation_block_number": int(log["blockNumber"], 16),
        "creation_transaction_index": int(log["transactionIndex"], 16),
        "creation_log_index": int(log["logIndex"], 16),
    }
    if version == "pancake_v2":
        result["pool_address"] = address(data, 0)
        result["pair_index"] = str(uint(data, 1))
        result["fee"] = None
        result["tick_spacing"] = None
    else:
        result["pool_address"] = address(data, 1)
        result["pair_index"] = None
        result["fee"] = int(topics[3], 16)
        result["tick_spacing"] = int.from_bytes(data[:32], "big", signed=True)
    return result


def collect_initializations(
    rpc_url: str,
    rows: list[dict[str, Any]],
    first_code_blocks: dict[str, int],
    output: Path,
    batch_size: int,
    workers: int,
) -> None:
    done = {row["token_address"].lower() for row in load_jsonl(output)} if output.exists() else set()
    pending = [row for row in rows if row["token_address"].lower() not in done]
    row_batches = [pending[start:start + batch_size] for start in range(0, len(pending), batch_size)]
    calls_by_batch: list[list[tuple[str, list[Any]]]] = []
    specs_by_batch: list[list[tuple[str, str, str]]] = []
    for batch in row_batches:
        calls: list[tuple[str, list[Any]]] = []
        specs: list[tuple[str, str, str]] = []
        for row in batch:
            spec = factory_spec(row)
            specs.append(spec)
            factory, topic, _ = spec
            block = first_code_blocks[row["token_address"].lower()]
            calls.append(("eth_getLogs", [{
                "address": factory,
                "fromBlock": hex(block),
                "toBlock": hex(block),
                "topics": [topic],
            }]))
        calls_by_batch.append(calls)
        specs_by_batch.append(specs)
    result_batches = concurrent_rpc_batches(rpc_url, calls_by_batch, workers)
    completed = 0
    for batch, results, specs in zip(row_batches, result_batches, specs_by_batch):
        decoded_rows: list[dict[str, Any]] = []
        for row, logs, spec in zip(batch, results, specs):
            factory, topic, version = spec
            token = row["token_address"].lower()
            expected_pool = row["pool_address"].lower()
            candidates = []
            for log in logs:
                topics = [value.lower() for value in log.get("topics") or []]
                if not topics or topics[0] != topic:
                    continue
                candidate = decode_candidate(log, version)
                if token not in {candidate["currency0"], candidate["currency1"]}:
                    continue
                candidates.append(candidate)
            exact = [candidate for candidate in candidates if candidate["pool_address"] == expected_pool]
            if len(exact) > 1:
                raise RuntimeError(f"Multiple exact factory initialization events for pool {expected_pool}")
            base = {
                "token_address": token,
                "lifecycle_transaction_hash": row["transaction_hash"].lower(),
                "lifecycle_block_number": int(row["block_number"]),
                "lifecycle_log_index": int(row["log_index"]),
                "expected_pool_address": expected_pool,
                "amm_version": version,
                "factory_address": factory,
                "factory_event_topic": topic,
                "pool_first_code_block": first_code_blocks[token],
                "source_method": "archive_eth_getCode_binary_search_then_factory_event",
            }
            if exact:
                decoded_rows.append(base | exact[0] | {
                    "pool_address_matches_lifecycle": True,
                    "initialization_status": "observed",
                })
            else:
                decoded_rows.append(base | {
                    "pool_address": None,
                    "currency0": None,
                    "currency1": None,
                    "creation_transaction_hash": None,
                    "creation_block_number": None,
                    "creation_transaction_index": None,
                    "creation_log_index": None,
                    "pair_index": None,
                    "fee": None,
                    "tick_spacing": None,
                    "pool_address_matches_lifecycle": False,
                    "initialization_status": "not_collected",
                    "factory_event_candidates_at_first_code_block": len(candidates),
                })
        append(output, decoded_rows)
        completed += len(batch)
        print(f"fourmeme pool history: event-lookup completed={completed}/{len(pending)}", flush=True)


def enrich_creation_timestamps(path: Path, rpc_url: str, batch_size: int, workers: int) -> None:
    rows = load_jsonl(path)
    blocks = sorted({int(row["creation_block_number"]) for row in rows if row.get("creation_block_number") is not None})
    block_batches = [blocks[start:start + batch_size] for start in range(0, len(blocks), batch_size)]
    result_batches = concurrent_rpc_batches(rpc_url, [
        [("eth_getBlockByNumber", [hex(block), False]) for block in batch]
        for batch in block_batches
    ], workers)
    timestamps: dict[int, int] = {}
    for batch, results in zip(block_batches, result_batches):
        timestamps.update({block: int(header["timestamp"], 16) for block, header in zip(batch, results)})
    for row in rows:
        block = row.get("creation_block_number")
        row["creation_block_timestamp_unix"] = timestamps.get(int(block)) if block is not None else None
    replacement = path.with_name(f".{path.name}.timestamps")
    with replacement.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    replacement.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lifecycle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timestamps-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.timestamps_only:
        enrich_creation_timestamps(output, args.rpc_url, args.batch_size, args.workers)
        source_path = output.with_name("HISTORICAL_POOL_INITIALIZATIONS_SOURCE.json")
        source = json.loads(source_path.read_text()) if source_path.exists() else {}
        source["block_timestamp_enrichment"] = "eth_getBlockByNumber at each creation block"
        source["sha256"] = sha256(output)
        write_json(source_path, source)
        return
    rows = target_rows(args.lifecycle)
    first_code_blocks = find_first_code_blocks(args.rpc_url, rows, args.batch_size, args.workers)
    collect_initializations(args.rpc_url, rows, first_code_blocks, output, args.batch_size, args.workers)
    enrich_creation_timestamps(output, args.rpc_url, args.batch_size, args.workers)
    result = load_jsonl(output)
    expected_tokens = {row["token_address"].lower() for row in rows}
    result_tokens = {row["token_address"].lower() for row in result}
    if result_tokens != expected_tokens or len(result) != len(rows):
        raise RuntimeError(f"Output coverage mismatch: targets={len(rows)} rows={len(result)} unique={len(result_tokens)}")
    observed = [row for row in result if row["initialization_status"] == "observed"]
    if any(not row["pool_address_matches_lifecycle"] for row in observed):
        raise RuntimeError("Observed initialization contains a pool-address mismatch")
    metadata = {
        "source_id": "fourmeme_pancake_pool_historical_initializations",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "rpc_url": args.rpc_url,
        "selection": "LiquidityAdded with pool_address and without pair_created_log_index",
        "source_method": "archive eth_getCode binary search followed by exact-block factory event lookup",
        "factories": {
            "pancake_v2": {"address": PANCAKE_V2_FACTORY, "event_topic": PAIR_CREATED_TOPIC},
            "pancake_v3": {"address": PANCAKE_V3_FACTORY, "event_topic": POOL_CREATED_V3_TOPIC},
        },
        "rows": len(result),
        "observed": len(observed),
        "not_collected": sum(row["initialization_status"] == "not_collected" for row in result),
        "pool_address_matches_lifecycle": sum(bool(row["pool_address_matches_lifecycle"]) for row in result),
        "amm_versions": {
            version: sum(row["amm_version"] == version for row in result)
            for version in ("pancake_v2", "pancake_v3")
        },
        "sha256": sha256(output),
    }
    write_json(output.with_name("HISTORICAL_POOL_INITIALIZATIONS_SOURCE.json"), metadata)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
