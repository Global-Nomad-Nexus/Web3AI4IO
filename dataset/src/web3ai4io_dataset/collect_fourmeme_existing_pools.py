from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from web3ai4io_dataset.collect_fourmeme_events import DEFAULT_RPC_URL, Rpc, append, write_json


PANCAKE_V2_FACTORY = "0xca143ce32fe78f1f7019d7d551a6402fc5350c73"
WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
NATIVE_BNB = "0x0000000000000000000000000000000000000000"
GET_PAIR_SELECTOR = "e6a43905"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def call_data(base: str, quote: str) -> str:
    return "0x" + GET_PAIR_SELECTOR + base[2:].lower().rjust(64, "0") + quote[2:].lower().rjust(64, "0")


def normalized_quote(quote: str) -> str:
    return WBNB if quote.lower() == NATIVE_BNB else quote.lower()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lifecycle", type=Path, required=True)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL)
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot_block = int(json.loads(args.boundary.read_text())["snapshot_block"])
    previous = load_jsonl(output) if output.exists() else []
    done = {
        row["token_address"].lower()
        for row in previous
        if row.get("mapping_status") == "observed" and row.get("normalized_quote_address") == normalized_quote(row["quote_address"])
    }
    pending = [
        row for row in load_jsonl(args.lifecycle)
        if row["event_name"] == "LiquidityAdded" and not row.get("pool_address") and row["token_address"].lower() not in done
    ]
    rpc = Rpc(args.rpc_url)
    observed = 0
    zero = 0
    for start in range(0, len(pending), args.batch_size):
        batch = pending[start:start + args.batch_size]
        calls = [
            ("eth_call", [{"to": PANCAKE_V2_FACTORY, "data": call_data(row["token_address"], normalized_quote(row["quote_address"]))}, hex(snapshot_block)])
            for row in batch
        ]
        results = rpc.batch(calls)
        decoded = []
        for row, result in zip(batch, results):
            pool = "0x" + result[-40:].lower()
            exists = int(pool, 16) != 0
            observed += int(exists)
            zero += int(not exists)
            quote = normalized_quote(row["quote_address"])
            currencies = sorted((row["token_address"].lower(), quote))
            decoded.append({
                "token_address": row["token_address"].lower(),
                "quote_address": row["quote_address"].lower(),
                "normalized_quote_address": quote,
                "pool_address": pool if exists else None,
                "currency0": currencies[0],
                "currency1": currencies[1],
                "factory_address": PANCAKE_V2_FACTORY,
                "observation_block": snapshot_block,
                "mapping_status": "observed" if exists else "not_collected",
                "source_method": "PancakeV2Factory.getPair(base,quote)",
            })
        append(output, decoded)
        completed = min(start + len(batch), len(pending))
        if completed % 500 == 0 or completed == len(pending):
            print(f"fourmeme existing pools: completed={completed}/{len(pending)} observed={observed} zero={zero}", flush=True)
    rows = load_jsonl(output)
    metadata = {
        "source_id": "fourmeme_pancake_v2_getpair_snapshot",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "rpc_url": args.rpc_url,
        "factory_address": PANCAKE_V2_FACTORY,
        "snapshot_block": snapshot_block,
        "rows": len(rows),
        "observed": sum(row["mapping_status"] == "observed" for row in rows),
        "not_collected": sum(row["mapping_status"] == "not_collected" for row in rows),
        "sha256": sha256(output),
    }
    write_json(output.with_name("EXISTING_POOL_SOURCE.json"), metadata)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
