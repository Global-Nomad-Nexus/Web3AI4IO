from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


POOL_MANAGER = "0x498581ff718922c3f8e6a244956af099b2652b2b"
INITIALIZE_TOPIC = "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"
MODIFY_LIQUIDITY_TOPIC = "0xf208f4912782fd25c7f114ca3723a2d5dd6f3bcc3ac8db5af63baa85f711d5ec"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def rpc_logs(endpoint: str, start: int, end: int, pool_ids: list[str], retries: int) -> list[dict[str, Any]]:
    query = {
        "fromBlock": hex(start),
        "toBlock": hex(end),
        "address": POOL_MANAGER,
        "topics": [[INITIALIZE_TOPIC, MODIFY_LIQUIDITY_TOPIC], pool_ids],
    }
    error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.post(
                endpoint,
                json={"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [query]},
                timeout=90,
            )
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(str(payload["error"]))
            return payload["result"]
        except Exception as exc:
            error = exc
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"Pool core query failed for blocks {start} to {end}: {error}")


def address(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def word(data: str, index: int) -> int:
    return int(data[2 + 64 * index : 2 + 64 * (index + 1)], 16)


def signed(value: int, bits: int = 256) -> int:
    return value - (1 << bits) if value >= 1 << (bits - 1) else value


def decode(log: dict[str, Any], token: dict[str, str]) -> dict[str, Any]:
    topic = log["topics"][0].lower()
    base = {
        "token_id": token["token_id"].lower(),
        "pool_id": token["pool_id"].lower(),
        "block_number": int(log["blockNumber"], 16),
        "block_timestamp_unix": int(log.get("blockTimestamp", "0x0"), 16),
        "transaction_hash": log["transactionHash"].lower(),
        "log_index": int(log["logIndex"], 16),
        "pool_manager": POOL_MANAGER,
        "source_endpoint": "Base public JSON-RPC eth_getLogs",
    }
    if topic == INITIALIZE_TOPIC:
        return base | {
            "event_type": "pool_initialized",
            "currency0": address(log["topics"][2]),
            "currency1": address(log["topics"][3]),
            "fee": word(log["data"], 0),
            "tick_spacing": signed(word(log["data"], 1)),
            "hooks": address("0x" + f"{word(log['data'], 2):064x}"),
            "sqrt_price_x96": str(word(log["data"], 3)),
            "initial_tick": signed(word(log["data"], 4)),
        }
    return base | {
        "event_type": "initial_liquidity_modified",
        "sender": address(log["topics"][2]),
        "tick_lower": signed(word(log["data"], 0)),
        "tick_upper": signed(word(log["data"], 1)),
        "liquidity_delta": str(signed(word(log["data"], 2))),
        "salt": "0x" + log["data"][2 + 64 * 3 : 2 + 64 * 4],
    }


def load_launches(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {"token_id", "pool_id", "block_number", "transaction_hash"}
    if not rows or not required.issubset(rows[0]):
        raise RuntimeError(f"Launch file must include {sorted(required)}")
    return rows


def normalize_legacy_int24(path: Path) -> None:
    temporary = path.with_suffix(".normalized.jsonl")
    changed = False
    with path.open(encoding="utf-8") as source, temporary.open("w", encoding="utf-8") as target:
        for line in source:
            row = json.loads(line)
            value = row.get("initial_tick")
            if row.get("event_type") == "pool_initialized" and isinstance(value, int) and value > 1 << 255:
                row["initial_tick"] = value - (1 << 256) + (1 << 24)
                changed = True
            target.write(json.dumps(row, separators=(",", ":")) + "\n")
    if changed:
        temporary.replace(path)
    else:
        temporary.unlink()


def collect(launches_path: Path, output: Path, endpoint: str, block_chunk: int, retries: int) -> dict[str, Any]:
    launches = load_launches(launches_path)
    by_block: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in launches:
        by_block[int(row["block_number"])].append(row)
    first = min(by_block)
    last = max(by_block)
    output.mkdir(parents=True, exist_ok=True)
    events_path = output / "pool_core_events.jsonl"
    checkpoint_path = output / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {}
    start = max(first, int(checkpoint.get("last_completed_block", first - 1)) + 1)
    mode = "a" if events_path.exists() and start > first else "w"
    with events_path.open(mode, encoding="utf-8") as handle:
        while start <= last:
            end = min(start + block_chunk - 1, last)
            cohort = [row for block in range(start, end + 1) for row in by_block.get(block, [])]
            if cohort:
                lookup = {row["pool_id"].lower(): row for row in cohort}
                logs = rpc_logs(endpoint, start, end, sorted(lookup), retries)
                kept = 0
                for log in logs:
                    pool_id = log["topics"][1].lower()
                    token = lookup.get(pool_id)
                    if token is None:
                        continue
                    if log["transactionHash"].lower() != token["transaction_hash"].lower():
                        continue
                    handle.write(json.dumps(decode(log, token), separators=(",", ":")) + "\n")
                    kept += 1
                handle.flush()
                print(f"blocks={start}:{end} launches={len(cohort)} logs={len(logs)} kept={kept}", flush=True)
            checkpoint = {"last_completed_block": end, "launch_universe_rows": len(launches)}
            write_json(checkpoint_path, checkpoint)
            start = end + 1
    normalize_legacy_int24(events_path)
    rows = sum(1 for _ in events_path.open(encoding="utf-8"))
    metadata = {
        "source_id": "base_pool_manager_launch_core_events",
        "dataset_role": "canonical_core",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "method": "eth_getLogs",
        "contract": POOL_MANAGER,
        "topics": {"Initialize": INITIALIZE_TOPIC, "ModifyLiquidity": MODIFY_LIQUIDITY_TOPIC},
        "scope": "Only pools and launch transactions already present in the fixed 62,618 launch universe.",
        "exclusions": ["TokenCreated recollection", "Swap", "Transfer", "holder data", "trading outcomes"],
        "rows": rows,
        "sha256": sha256(events_path),
    }
    write_json(output / "SOURCE.json", metadata)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launches", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default="https://mainnet.base.org")
    parser.add_argument("--block-chunk", type=int, default=5_000)
    parser.add_argument("--retries", type=int, default=6)
    args = parser.parse_args()
    result = collect(args.launches.resolve(), args.output.resolve(), args.endpoint, args.block_chunk, args.retries)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
