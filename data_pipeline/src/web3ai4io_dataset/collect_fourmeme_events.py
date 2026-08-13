from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_RPC_URL = "https://bsc.rpc.sentio.xyz"
DEFAULT_STATE_RPC_URL = "https://bsc-mainnet.public.blastapi.io"
PAIR_CREATED_TOPIC = "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
MINT_TOPIC = "0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f"
POOL_CREATED_V3_TOPIC = "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
MINT_V3_TOPIC = "0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde"
WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
NATIVE_BNB = "0x0000000000000000000000000000000000000000"
MANAGERS = (
    {
        "version": "v1",
        "address": "0xec4549cadce5da21df6e6422d448034b5233bfbc",
        "deployment_block": 40_138_454,
        "token_create_topic": "0x396d5e902b675b032348d3d2e9517ee8f0c4a926603fbc075d3d282ff00cad20",
        "lifecycle_event": "TradeStop",
        "lifecycle_topic": "0x8f9ab4bd7eff0d085f91575d50cd83f97aa5258e24ded7630d4fd6739e857132",
        "fields": 8,
    },
    {
        "version": "v2",
        "address": "0x5c952063c7fc8610ffdb798152d69f0b9550762b",
        "deployment_block": 41_983_675,
        "token_create_topic": "0x396d5e902b675b032348d3d2e9517ee8f0c4a926603fbc075d3d282ff00cad20",
        "lifecycle_event": "LiquidityAdded",
        "lifecycle_topic": "0xc18aa71171b358b706fe3dd345299685ba21a5316c66ffa9e319268b033c44b0",
        "fields": 8,
    },
)


class Rpc:
    def __init__(self, url: str) -> None:
        self.url = url
        self.session = requests.Session()
        self.request_id = 0

    def call(self, method: str, params: list[Any], retries: int = 8) -> Any:
        error: Exception | None = None
        for attempt in range(retries):
            try:
                self.request_id += 1
                response = self.session.post(
                    self.url,
                    json={"jsonrpc": "2.0", "method": method, "params": params, "id": self.request_id},
                    timeout=90,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("error"):
                    raise RuntimeError(json.dumps(payload["error"], separators=(",", ":")))
                return payload["result"]
            except Exception as exc:
                error = exc
                time.sleep(min(1.6 ** attempt, 30))
        raise RuntimeError(f"RPC {method} failed: {error}")

    def batch(self, calls: list[tuple[str, list[Any]]], retries: int = 8) -> list[Any]:
        error: Exception | None = None
        for attempt in range(retries):
            try:
                payload = []
                ids: list[int] = []
                for method, params in calls:
                    self.request_id += 1
                    ids.append(self.request_id)
                    payload.append({"jsonrpc": "2.0", "method": method, "params": params, "id": self.request_id})
                response = self.session.post(self.url, json=payload, timeout=120)
                response.raise_for_status()
                rows = response.json()
                if not isinstance(rows, list):
                    raise RuntimeError(f"Expected batch response, got {type(rows).__name__}")
                by_id = {row["id"]: row for row in rows}
                results = []
                for request_id in ids:
                    row = by_id[request_id]
                    if row.get("error"):
                        raise RuntimeError(json.dumps(row["error"], separators=(",", ":")))
                    results.append(row["result"])
                return results
            except Exception as exc:
                error = exc
                time.sleep(min(1.6 ** attempt, 30))
        raise RuntimeError(f"RPC batch failed: {error}")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def append(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_code_block(rpc: Rpc, contract: str, high: int) -> int:
    if rpc.call("eth_getCode", [contract, hex(high)]) == "0x":
        raise RuntimeError(f"No code at snapshot block for {contract}")
    low = 0
    while low < high:
        mid = (low + high) // 2
        if rpc.call("eth_getCode", [contract, hex(mid)]) == "0x":
            low = mid + 1
        else:
            high = mid
    return low


def word(data: bytes, index: int) -> bytes:
    return data[index * 32:(index + 1) * 32]


def uint(data: bytes, index: int) -> int:
    return int.from_bytes(word(data, index), "big")


def address(data: bytes, index: int) -> str:
    return "0x" + word(data, index)[-20:].hex()


def dynamic_string(data: bytes, head_index: int) -> str:
    offset = uint(data, head_index)
    if offset + 32 > len(data):
        raise ValueError(f"invalid dynamic string offset {offset}")
    length = int.from_bytes(data[offset:offset + 32], "big")
    if offset + 32 + length > len(data):
        raise ValueError(f"invalid dynamic string length {length}")
    return data[offset + 32:offset + 32 + length].decode("utf-8", errors="replace")


def log_identity(log: dict[str, Any]) -> dict[str, Any]:
    return {
        "block_number": int(log["blockNumber"], 16),
        "transaction_hash": log["transactionHash"].lower(),
        "transaction_index": int(log["transactionIndex"], 16),
        "log_index": int(log["logIndex"], 16),
    }


def decode_token_create(log: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    data = bytes.fromhex(log["data"][2:])
    if len(data) < int(spec["fields"]) * 32:
        raise ValueError(f"short TokenCreate data: {len(data)} bytes")
    return log_identity(log) | {
        "event_name": "TokenCreate",
        "manager_version": spec["version"],
        "manager_address": spec["address"],
        "creator": address(data, 0),
        "token_address": address(data, 1),
        "request_id": str(uint(data, 2)),
        "name": dynamic_string(data, 3),
        "symbol": dynamic_string(data, 4),
        "total_supply_raw": str(uint(data, 5)),
        "launch_time_unix": uint(data, 6),
        "launch_fee_raw": str(uint(data, 7)) if spec["fields"] == 8 else None,
    }


def decode_lifecycle(log: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    data = bytes.fromhex(log["data"][2:])
    row = log_identity(log) | {
        "event_name": spec["lifecycle_event"],
        "manager_version": spec["version"],
        "manager_address": spec["address"],
    }
    if spec["lifecycle_event"] == "TradeStop":
        row["token_address"] = address(data, 0)
    else:
        row |= {
            "token_address": address(data, 0),
            "offers_raw": str(uint(data, 1)),
            "quote_address": address(data, 2),
            "funds_raw": str(uint(data, 3)),
        }
    return row


def scan_manager(
    rpc: Rpc,
    output: Path,
    spec: dict[str, Any],
    start_block: int,
    snapshot_block: int,
    chunk_size: int,
    batch_windows: int,
) -> dict[str, Any]:
    stem = f"{spec['version']}_core_events"
    create_target = output / f"{spec['version']}_tokencreate.jsonl"
    lifecycle_target = output / f"{spec['version']}_{spec['lifecycle_event'].lower()}.jsonl"
    checkpoint_path = output / f"{stem}_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {}
    if checkpoint.get("complete") and int(checkpoint.get("snapshot_block", -1)) == snapshot_block:
        return checkpoint
    current = int(checkpoint.get("next_block", start_block))
    creates_total = int(checkpoint.get("token_create_rows", 0))
    lifecycle_total = int(checkpoint.get("lifecycle_rows", 0))
    size = int(checkpoint.get("chunk_size", chunk_size))
    while current <= snapshot_block:
        windows: list[tuple[int, int]] = []
        cursor = current
        for _ in range(batch_windows):
            if cursor > snapshot_block:
                break
            end = min(cursor + size - 1, snapshot_block)
            windows.append((cursor, end))
            cursor = end + 1
        topics = [[spec["token_create_topic"], spec["lifecycle_topic"]]]
        calls = [("eth_getLogs", [{"address": spec["address"], "fromBlock": hex(start), "toBlock": hex(end), "topics": topics}]) for start, end in windows]
        try:
            batches = rpc.batch(calls, retries=3)
        except RuntimeError:
            if size <= 100:
                raise
            size = max(100, size // 2)
            print(f"fourmeme {stem}: reduce_chunk={size}", flush=True)
            continue
        create_rows: list[dict[str, Any]] = []
        lifecycle_rows: list[dict[str, Any]] = []
        for logs in batches:
            for log in logs:
                topic = log["topics"][0].lower()
                if topic == spec["token_create_topic"]:
                    create_rows.append(decode_token_create(log, spec))
                elif topic == spec["lifecycle_topic"]:
                    lifecycle_rows.append(decode_lifecycle(log, spec))
                else:
                    raise RuntimeError(f"Unexpected topic {topic} for {spec['version']}")
        append(create_target, create_rows)
        append(lifecycle_target, lifecycle_rows)
        creates_total += len(create_rows)
        lifecycle_total += len(lifecycle_rows)
        current = windows[-1][1] + 1
        checkpoint = {
            "manager_version": spec["version"],
            "manager_address": spec["address"],
            "deployment_block": start_block,
            "snapshot_block": snapshot_block,
            "next_block": current,
            "chunk_size": size,
            "batch_windows": batch_windows,
            "token_create_rows": creates_total,
            "lifecycle_rows": lifecycle_total,
            "complete": current > snapshot_block,
        }
        write_json(checkpoint_path, checkpoint)
        if create_rows or lifecycle_rows or current % 1_000_000 < size * batch_windows:
            print(f"fourmeme {stem}: through={windows[-1][1]} creates={creates_total} lifecycle={lifecycle_total}", flush=True)
    checkpoint["token_create_sha256"] = sha256(create_target)
    checkpoint["lifecycle_sha256"] = sha256(lifecycle_target) if lifecycle_target.exists() else None
    write_json(checkpoint_path, checkpoint)
    return checkpoint


def enrich_lifecycle_receipts(
    rpc: Rpc,
    output: Path,
    batch_size: int,
    refresh_incomplete: bool = False,
    refresh_v3_config: bool = False,
) -> dict[str, Any]:
    target = output / "lifecycle_core.jsonl"
    done: set[tuple[str, int]] = set()
    if target.exists():
        retained: list[dict[str, Any]] = []
        with target.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if refresh_incomplete and row.get("event_name") == "LiquidityAdded" and not row.get("pool_address"):
                    continue
                if refresh_v3_config and row.get("amm_version") == "pancake_v3":
                    continue
                retained.append(row)
                done.add((row["transaction_hash"], row["log_index"]))
        if refresh_incomplete or refresh_v3_config:
            replacement = target.with_name(f".{target.name}.refresh")
            with replacement.open("w", encoding="utf-8") as handle:
                for row in retained:
                    handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            replacement.replace(target)
    pending: list[dict[str, Any]] = []
    for spec in MANAGERS:
        path = output / f"{spec['version']}_{spec['lifecycle_event'].lower()}.jsonl"
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                pending.extend(row for line in handle if line.strip() for row in [json.loads(line)] if (row["transaction_hash"], row["log_index"]) not in done)
    block_timestamps: dict[int, int] = {}
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        receipts = rpc.batch([("eth_getTransactionReceipt", [row["transaction_hash"]]) for row in batch])
        missing_blocks = sorted({int(row["block_number"]) for row in batch} - set(block_timestamps))
        headers = rpc.batch([("eth_getBlockByNumber", [hex(block), False]) for block in missing_blocks]) if missing_blocks else []
        block_timestamps.update({block: int(header["timestamp"], 16) for block, header in zip(missing_blocks, headers)})
        decoded: list[dict[str, Any]] = []
        for row, receipt in zip(batch, receipts):
            result = dict(row)
            result["block_timestamp_unix"] = block_timestamps[int(row["block_number"])]
            token = row["token_address"].lower()
            receipt_logs = receipt.get("logs") or []
            for log in receipt_logs:
                topics = [value.lower() for value in log.get("topics") or []]
                if not topics:
                    continue
                if topics[0] == PAIR_CREATED_TOPIC and token in {"0x" + topics[1][-40:], "0x" + topics[2][-40:]}:
                    data = bytes.fromhex(log["data"][2:])
                    result |= {
                        "pool_address": address(data, 0),
                        "currency0": "0x" + topics[1][-40:],
                        "currency1": "0x" + topics[2][-40:],
                        "pair_created_log_index": int(log["logIndex"], 16),
                        "amm_version": "pancake_v2",
                    }
                if topics[0] == POOL_CREATED_V3_TOPIC and token in {"0x" + topics[1][-40:], "0x" + topics[2][-40:]}:
                    data = bytes.fromhex(log["data"][2:])
                    result |= {
                        "pool_address": address(data, 1),
                        "currency0": "0x" + topics[1][-40:],
                        "currency1": "0x" + topics[2][-40:],
                        "pair_created_log_index": int(log["logIndex"], 16),
                        "amm_version": "pancake_v3",
                        "fee_hundredths_bip": int(topics[3], 16),
                        "tick_spacing": int.from_bytes(data[:32], "big", signed=True),
                    }
                if topics[0] == MINT_TOPIC and result.get("pool_address") == log["address"].lower():
                    data = bytes.fromhex(log["data"][2:])
                    result |= {
                        "liquidity_mint_log_index": int(log["logIndex"], 16),
                        "liquidity_sender": "0x" + topics[1][-40:] if len(topics) > 1 else None,
                        "amount0_raw": str(uint(data, 0)),
                        "amount1_raw": str(uint(data, 1)),
                    }
                if topics[0] == MINT_V3_TOPIC and result.get("pool_address") == log["address"].lower():
                    data = bytes.fromhex(log["data"][2:])
                    result |= {
                        "liquidity_mint_log_index": int(log["logIndex"], 16),
                        "liquidity_sender": address(data, 0),
                        "amount0_raw": str(uint(data, 2)),
                        "amount1_raw": str(uint(data, 3)),
                    }
            if row.get("event_name") == "LiquidityAdded" and not result.get("pool_address"):
                mint_candidates = []
                for log in receipt_logs:
                    topics = [value.lower() for value in log.get("topics") or []]
                    if topics and topics[0] in {MINT_TOPIC, MINT_V3_TOPIC}:
                        mint_candidates.append((log, topics[0]))
                if len(mint_candidates) == 1:
                    mint_log, mint_topic = mint_candidates[0]
                    quote = row.get("quote_address", "").lower()
                    quote = WBNB if quote == NATIVE_BNB else quote
                    currencies = sorted((token, quote))
                    data = bytes.fromhex(mint_log["data"][2:])
                    is_v3 = mint_topic == MINT_V3_TOPIC
                    result |= {
                        "pool_address": mint_log["address"].lower(),
                        "currency0": currencies[0],
                        "currency1": currencies[1],
                        "liquidity_mint_log_index": int(mint_log["logIndex"], 16),
                        "liquidity_sender": address(data, 0) if is_v3 else ("0x" + mint_log["topics"][1][-40:] if len(mint_log["topics"]) > 1 else None),
                        "amount0_raw": str(uint(data, 2 if is_v3 else 0)),
                        "amount1_raw": str(uint(data, 3 if is_v3 else 1)),
                        "amm_version": "pancake_v3" if is_v3 else "pancake_v2",
                        "pool_mapping_method": "receipt_unique_mint",
                    }
            decoded.append(result)
        append(target, decoded)
        completed = min(start + len(batch), len(pending))
        if completed % 500 == 0 or completed == len(pending):
            print(f"fourmeme lifecycle receipts: completed={completed}/{len(pending)}", flush=True)
    rows = []
    if target.exists():
        with target.open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    return {
        "rows": len(rows),
        "with_pool_mapping": sum(bool(row.get("pool_address")) for row in rows),
        "with_liquidity_mint": sum("amount0_raw" in row for row in rows),
        "sha256": sha256(target) if target.exists() else None,
    }


def finalize(output: Path, rpc_url: str, snapshot_block: int, deployments: dict[str, int], scans: list[dict[str, Any]], lifecycle: dict[str, Any]) -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {}
    for spec in MANAGERS:
        path = output / f"{spec['version']}_tokencreate.jsonl"
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                token = row["token_address"].lower()
                if token in rows:
                    raise RuntimeError(f"Duplicate TokenCreate for {token}")
                rows[token] = row
    target = output / "onchain_launches.jsonl"
    with target.open("w", encoding="utf-8") as handle:
        for row in sorted(rows.values(), key=lambda value: (value["block_number"], value["log_index"])):
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    metadata = {
        "source_id": "fourmeme_bsc_archive_rpc_contract_events",
        "dataset_role": "canonical_core",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "rpc_url": rpc_url,
        "snapshot_block": snapshot_block,
        "deployment_blocks": deployments,
        "contracts": [{key: spec[key] for key in ("version", "address", "lifecycle_event")} for spec in MANAGERS],
        "scans": scans,
        "unique_token_creates": len(rows),
        "onchain_launches_sha256": sha256(target),
        "lifecycle_receipts": lifecycle,
        "metadata_enrichment_source": "Four.meme official public API capped at 1,000 rows",
        "exclusions": ["TokenPurchase", "TokenSale", "Transfer", "holder data", "decoded trading"],
    }
    write_json(output / "ONCHAIN_SOURCE.json", metadata)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL)
    parser.add_argument("--state-rpc-url", default=DEFAULT_STATE_RPC_URL)
    parser.add_argument("--chunk-size", type=int, default=10_000)
    parser.add_argument("--batch-windows", type=int, default=20)
    parser.add_argument("--receipt-batch-size", type=int, default=50)
    parser.add_argument("--refresh-incomplete-lifecycle", action="store_true")
    parser.add_argument("--refresh-v3-config", action="store_true")
    parser.add_argument("--receipts-only", action="store_true")
    parser.add_argument("--confirmations", type=int, default=20)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rpc = Rpc(args.rpc_url)
    if args.receipts_only:
        boundary = json.loads((output / "scan_boundary.json").read_text())
        snapshot_block = int(boundary["snapshot_block"])
        deployments = {key: int(value) for key, value in boundary["deployment_blocks"].items()}
        scans = [json.loads((output / f"{spec['version']}_core_events_checkpoint.json").read_text()) for spec in MANAGERS]
        lifecycle = enrich_lifecycle_receipts(
            rpc, output, args.receipt_batch_size,
            args.refresh_incomplete_lifecycle, args.refresh_v3_config,
        )
        print(json.dumps(finalize(output, args.rpc_url, snapshot_block, deployments, scans, lifecycle), indent=2))
        return
    snapshot_block = int(rpc.call("eth_blockNumber", []), 16) - args.confirmations
    state_rpc = Rpc(args.state_rpc_url)
    deployments = {spec["version"]: first_code_block(state_rpc, spec["address"], snapshot_block) for spec in MANAGERS}
    expected = {spec["version"]: spec["deployment_block"] for spec in MANAGERS}
    if deployments != expected:
        raise RuntimeError(f"Deployment boundary changed: observed={deployments} expected={expected}")
    write_json(output / "scan_boundary.json", {"snapshot_block": snapshot_block, "confirmations": args.confirmations, "deployment_blocks": deployments, "state_rpc_url": args.state_rpc_url})
    scans: list[dict[str, Any]] = []
    for spec in MANAGERS:
        scans.append(scan_manager(rpc, output, spec, deployments[spec["version"]], snapshot_block, args.chunk_size, args.batch_windows))
    lifecycle = enrich_lifecycle_receipts(
        rpc, output, args.receipt_batch_size,
        args.refresh_incomplete_lifecycle, args.refresh_v3_config,
    )
    print(json.dumps(finalize(output, args.rpc_url, snapshot_block, deployments, scans, lifecycle), indent=2))


if __name__ == "__main__":
    main()
