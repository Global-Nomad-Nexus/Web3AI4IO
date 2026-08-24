#!/usr/bin/env python3
"""Run a bounded, read only Base historical JSON RPC capability probe."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "identification" / "data_expansion" / "artifacts"
FACTORY = "0xe85a59c628f7d27878aceb4bf3b35733630083a9"
TOKEN_CREATED_TOPIC = "0x9299d1d1a88d8e1abdc591ae7a167a6bc63a8f17d695804e9091ee33aa89fb67"
KNOWN_BLOCK = 34_725_785
KNOWN_TRANSACTION = "0x5c076d1967b9f4873d36191321ccf015015b48687d0f176c6ad7091a84551985"


def rpc(url: str, method: str, params: list[object], timeout: int) -> dict[str, object]:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "Web3AI4IO-data-audit/1.0"},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
        return {
            "ok": "result" in body,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "result": body.get("result"),
            "error": body.get("error"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "result": None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--range-blocks", type=int, default=1)
    args = parser.parse_args()

    if args.range_blocks < 1:
        raise ValueError("--range-blocks must be positive")
    block_hex = hex(KNOWN_BLOCK)
    to_block_hex = hex(KNOWN_BLOCK + args.range_blocks - 1)
    chain = rpc(args.rpc_url, "eth_chainId", [], args.timeout)
    block = rpc(args.rpc_url, "eth_getBlockByNumber", [block_hex, False], args.timeout)
    logs = rpc(
        args.rpc_url,
        "eth_getLogs",
        [{"fromBlock": block_hex, "toBlock": to_block_hex, "address": FACTORY, "topics": [TOKEN_CREATED_TOPIC]}],
        args.timeout,
    )
    log_rows = logs.get("result") if isinstance(logs.get("result"), list) else []
    known_transaction_found = any(
        str(row.get("transactionHash", "")).lower() == KNOWN_TRANSACTION for row in log_rows
        if isinstance(row, dict)
    )
    result = {
        "probe_timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider_label": args.label,
        "rpc_url": args.rpc_url,
        "probe_scope": "chain id, one historical block, bounded historical TokenCreated logs",
        "known_block": KNOWN_BLOCK,
        "range_blocks": args.range_blocks,
        "known_transaction": KNOWN_TRANSACTION,
        "chain_id": chain,
        "historical_block": block,
        "historical_token_created_logs": {
            **logs,
            "result": None,
            "row_count": len(log_rows),
            "known_transaction_found": known_transaction_found,
        },
        "archive_log_probe_passed": bool(logs["ok"] and known_transaction_found),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / f"base_rpc_probe_{args.label}.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output.relative_to(ROOT)), "archive_log_probe_passed": result["archive_log_probe_passed"], "log_rows": len(log_rows), "error": logs["error"]}, indent=2))


if __name__ == "__main__":
    main()
