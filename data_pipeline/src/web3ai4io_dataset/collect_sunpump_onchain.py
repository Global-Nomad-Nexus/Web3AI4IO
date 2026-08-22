from __future__ import annotations

import argparse
import hashlib
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


CONTRACT = "TTfvyrAz86hbZk5iDpKD78pqLGgi8C7AAw"
EVENTS_URL = f"https://api.trongrid.io/v1/contracts/{CONTRACT}/events"
TXINFO_URL = "https://api.trongrid.io/walletsolidity/gettransactioninfobyid"
RECEIPT_RPC_URL = "https://tron.rpc.sentio.xyz"
CONTRACT_HEX = "c22dd1b7bc7574e94563c8282f64b065bc07b2fa"
TOKEN_CREATE_TOPIC = "1ff0a01c8968e3551472812164f233abb579247de887db8cbb18281c149bee7a"
TOKEN_LAUNCHED_TOPIC = "2ab676eef3f76f1bd4e765a352c6cd81e62702f7ad3d363291c8b60582a45250"
NEW_IMPLEMENTATION_TOPIC = "d604de94d45953f9138079ec1b82d533cb2160c906d1076d1f7ed54befbca97a"
PAIR_CREATED_TOPIC = "0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
MINT_TOPIC = "4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f"
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
THREAD_LOCAL = threading.local()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tron_base58(hex_address: str) -> str:
    raw = bytes.fromhex("41" + hex_address[-40:].lower())
    checksum = hashlib.sha256(hashlib.sha256(raw).digest()).digest()[:4]
    number = int.from_bytes(raw + checksum, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = BASE58_ALPHABET[remainder] + encoded
    leading = len(raw + checksum) - len((raw + checksum).lstrip(b"\0"))
    return "1" * leading + encoded


def request_json(method: str, url: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None, retries: int = 20) -> dict[str, Any]:
    error: Exception | None = None
    for attempt in range(retries):
        try:
            session = getattr(THREAD_LOCAL, "session", None)
            if session is None:
                session = requests.Session()
                THREAD_LOCAL.session = session
            response = session.request(method, url, params=params, json=body, timeout=60)
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", 0) or 0)
                time.sleep(max(retry_after, min(5 * (attempt + 1), 60)) + random.random())
                raise RuntimeError("rate_limited")
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            error = exc
            if str(exc) != "rate_limited":
                time.sleep(min(1.5 ** attempt, 30) + random.random())
    raise RuntimeError(f"Request failed after {retries} attempts: {error}")


def append_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def collect_event_index(output: Path, event_name: str, delay: float) -> dict[str, Any]:
    target = output / f"{event_name.lower()}_index.jsonl"
    checkpoint_path = output / f"{event_name.lower()}_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {}
    fingerprint = checkpoint.get("fingerprint")
    pages = int(checkpoint.get("pages", 0))
    rows = int(checkpoint.get("rows", 0))
    if checkpoint.get("complete"):
        return checkpoint
    while True:
        params: dict[str, Any] = {
            "event_name": event_name,
            "only_confirmed": "true",
            "order_by": "block_timestamp,asc",
            "limit": 200,
        }
        if fingerprint:
            params["fingerprint"] = fingerprint
        payload = request_json("GET", EVENTS_URL, params=params)
        batch = payload.get("data") or []
        if batch:
            append_rows(target, batch)
            rows += len(batch)
        pages += 1
        fingerprint = (payload.get("meta") or {}).get("fingerprint")
        checkpoint = {"event_name": event_name, "pages": pages, "rows": rows, "fingerprint": fingerprint, "complete": not bool(fingerprint)}
        write_json(checkpoint_path, checkpoint)
        print(f"sunpump {event_name}: pages={pages} rows={rows}", flush=True)
        if not fingerprint:
            return checkpoint
        time.sleep(delay)


def word(data: str, index: int) -> str:
    return data[64 * index : 64 * (index + 1)]


def rpc_receipts(events: list[dict[str, Any]], retries: int = 10) -> list[dict[str, Any]]:
    payload = [
        {"jsonrpc": "2.0", "id": index, "method": "eth_getTransactionReceipt", "params": ["0x" + event["transaction_id"]]}
        for index, event in enumerate(events)
    ]
    error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.post(RECEIPT_RPC_URL, json=payload, timeout=120)
            response.raise_for_status()
            rows = response.json()
            by_id = {row["id"]: row for row in rows}
            results = []
            for index in range(len(events)):
                row = by_id[index]
                if row.get("error") or not row.get("result"):
                    raise RuntimeError(str(row.get("error") or "missing_receipt"))
                results.append(row["result"])
            return results
        except Exception as exc:
            error = exc
            time.sleep(min(1.6 ** attempt, 30) + random.random())
    raise RuntimeError(f"Receipt batch failed: {error}")


def clean_hex(value: str) -> str:
    return value[2:] if value.startswith("0x") else value


def decode_transaction(event: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    txid = event["transaction_id"]
    logs = info.get("log") or []
    if not logs:
        logs = info.get("logs") or []
    expected_topic = {
        "TokenCreate": TOKEN_CREATE_TOPIC,
        "TokenLaunched": TOKEN_LAUNCHED_TOPIC,
        "NewImplementation": NEW_IMPLEMENTATION_TOPIC,
    }[event["event_name"]]
    matching = [log for log in logs if clean_hex(log.get("address", "")).lower() == CONTRACT_HEX and clean_hex(log.get("topics", [""])[0]).lower() == expected_topic]
    if len(matching) != 1:
        raise RuntimeError(f"Expected one {event['event_name']} log in {txid}, found {len(matching)}")
    log = matching[0]
    topic = clean_hex(log["topics"][0]).lower()
    index = int(event["event_index"])
    base = {
        "event_name": event["event_name"],
        "block_number": int(event["block_number"]),
        "block_timestamp": int(event["block_timestamp"]),
        "transaction_id": txid,
        "event_index": index,
        "contract_address": CONTRACT,
        "receipt_result": "SUCCESS" if info.get("status") in ("0x1", 1, None) else str(info.get("status")),
    }
    if event["event_name"] == "TokenCreate":
        if topic != TOKEN_CREATE_TOPIC:
            raise RuntimeError(f"Unexpected TokenCreate topic in {txid}: {topic}")
        data = clean_hex(log.get("data", ""))
        return base | {
            "token_address": tron_base58(word(data, 0)),
            "token_address_hex": "41" + word(data, 0)[-40:],
            "token_index": int(word(data, 1), 16),
            "creator": tron_base58(word(data, 2)),
            "creator_hex": "41" + word(data, 2)[-40:],
        }
    if event["event_name"] == "NewImplementation":
        if topic != NEW_IMPLEMENTATION_TOPIC:
            raise RuntimeError(f"Unexpected NewImplementation topic in {txid}: {topic}")
        data = clean_hex(log.get("data", ""))
        return base | {
            "old_implementation": tron_base58(word(data, 0)),
            "old_implementation_hex": "41" + word(data, 0)[-40:],
            "new_implementation": tron_base58(word(data, 1)),
            "new_implementation_hex": "41" + word(data, 1)[-40:],
        }
    if topic != TOKEN_LAUNCHED_TOPIC:
        raise RuntimeError(f"Unexpected TokenLaunched topic in {txid}: {topic}")
    token_hex = "41" + clean_hex(log["topics"][1])[-40:]
    result = base | {"token_address": tron_base58(token_hex[2:]), "token_address_hex": token_hex}
    for position, candidate in enumerate(logs):
        candidate_topic = clean_hex(candidate.get("topics", [""])[0]).lower()
        if candidate_topic == PAIR_CREATED_TOPIC:
            token0_hex = "41" + clean_hex(candidate["topics"][1])[-40:]
            token1_hex = "41" + clean_hex(candidate["topics"][2])[-40:]
            if token_hex in {token0_hex, token1_hex}:
                pair_hex = "41" + word(clean_hex(candidate.get("data", "")), 0)[-40:]
                result |= {
                    "pool_address": tron_base58(pair_hex[2:]),
                    "pool_address_hex": pair_hex,
                    "currency0": tron_base58(token0_hex[2:]),
                    "currency1": tron_base58(token1_hex[2:]),
                    "pair_created_event_index": position,
                }
        if candidate_topic == MINT_TOPIC and result.get("pool_address_hex", "")[2:] == clean_hex(candidate.get("address", "")).lower():
            result |= {
                "liquidity_mint_event_index": position,
                "amount0_raw": str(int(word(clean_hex(candidate.get("data", "")), 0), 16)),
                "amount1_raw": str(int(word(clean_hex(candidate.get("data", "")), 1), 16)),
            }
    return result


def decode_indexes(output: Path, workers: int, batch_size: int) -> dict[str, Any]:
    target = output / "onchain_core.jsonl"
    done: set[tuple[str, str]] = set()
    if target.exists():
        with target.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                done.add((row["event_name"], row["transaction_id"]))
    indexed: list[dict[str, Any]] = []
    for event_name in ("TokenCreate", "TokenLaunched", "NewImplementation"):
        path = output / f"{event_name.lower()}_index.jsonl"
        with path.open(encoding="utf-8") as handle:
            indexed.extend(json.loads(line) for line in handle if line.strip())
    pending = [row for row in indexed if (row["event_name"], row["transaction_id"]) not in done]
    group_size = batch_size * workers
    for start in range(0, len(pending), group_size):
        group = pending[start:start + group_size]
        batches = [group[index:index + batch_size] for index in range(0, len(group), batch_size)]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            receipt_batches = list(pool.map(rpc_receipts, batches))
        decoded = []
        for batch, receipts in zip(batches, receipt_batches):
            decoded.extend(decode_transaction(event, receipt) for event, receipt in zip(batch, receipts))
        append_rows(target, decoded)
        print(f"sunpump txinfo: completed={min(start + len(group), len(pending))}/{len(pending)}", flush=True)
    rows = []
    with target.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return {
        "rows": len(rows),
        "token_create_rows": sum(row["event_name"] == "TokenCreate" for row in rows),
        "token_launched_rows": sum(row["event_name"] == "TokenLaunched" for row in rows),
        "new_implementation_rows": sum(row["event_name"] == "NewImplementation" for row in rows),
        "launched_with_pool_mapping": sum(row["event_name"] == "TokenLaunched" and bool(row.get("pool_address")) for row in rows),
        "launched_with_liquidity_mint": sum(row["event_name"] == "TokenLaunched" and "amount0_raw" in row for row in rows),
        "sha256": sha256(target),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--page-delay", type=float, default=0.15)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    indexes = {name: collect_event_index(output, name, args.page_delay) for name in ("TokenCreate", "TokenLaunched", "NewImplementation")}
    decoded = decode_indexes(output, args.workers, args.batch_size)
    metadata = {
        "source_id": "sunpump_trongrid_contract_events",
        "dataset_role": "canonical_core",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "contract": CONTRACT,
        "event_endpoint": EVENTS_URL,
        "pagination": "meta.fingerprint with all other query parameters held constant",
        "only_confirmed": True,
        "receipt_enrichment_rpc": RECEIPT_RPC_URL,
        "indexes": indexes,
        "decoded": decoded,
        "metadata_enrichment_source": "SunPump official public token API capped at 1,000 rows",
        "exclusions": ["TokenPurchased", "TokenSold", "holder data", "decoded trading"],
    }
    write_json(output / "ONCHAIN_SOURCE.json", metadata)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
