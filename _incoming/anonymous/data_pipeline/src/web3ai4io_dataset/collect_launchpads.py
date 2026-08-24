from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests


FOURMEME_URL = "https://four.meme/meme-api/v1/public/token/search"
FOURMEME_LIST_TYPES = ("NOR", "NOR_DEX")
SUNPUMP_URL = "https://api-v2.sunpump.meme/pump-api/token"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_json(call: Callable[[], requests.Response], retries: int = 8) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = call()
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") not in (0, None):
                raise RuntimeError(f"API code {payload.get('code')}: {payload.get('msg')}")
            return payload
        except Exception as exc:
            last_error = exc
            time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"Request failed after {retries} attempts: {last_error}")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def finalize_jsonl(parts: list[Path], output: Path, address_fields: tuple[str, ...]) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    source_types: dict[str, set[str]] = {}
    for part in parts:
        if not part.exists():
            continue
        with part.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                address = next((str(row.get(field, "")).strip() for field in address_fields if row.get(field)), "")
                if not address:
                    continue
                key = address.lower()
                source_type = str(row.pop("_source_list_type", ""))
                records[key] = row
                if source_type:
                    source_types.setdefault(key, set()).add(source_type)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for key in sorted(records):
            row = records[key]
            if key in source_types:
                row["source_list_types"] = sorted(source_types[key])
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return {"unique_tokens": len(records), "bytes": output.stat().st_size, "sha256": sha256(output)}


def collect_fourmeme(output: Path, delay: float, max_pages: int) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / "checkpoint.json"
    checkpoint = load_json(checkpoint_path, {})
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    parts: list[Path] = []
    page_counts: dict[str, int] = {}
    for list_type in FOURMEME_LIST_TYPES:
        part = output / f"fourmeme_{list_type.lower()}.jsonl"
        parts.append(part)
        page = int(checkpoint.get(list_type, 0)) + 1
        while page <= max_pages:
            body = {
                "type": "NEW", "listType": list_type, "pageIndex": page, "pageSize": 100,
                "status": "ALL", "sort": "ASC",
            }
            payload = request_json(lambda: session.post(FOURMEME_URL, json=body, timeout=45))
            rows = payload.get("data") or []
            if not isinstance(rows, list):
                raise RuntimeError(f"Unexpected Four.meme data for {list_type} page {page}")
            if not rows:
                checkpoint[f"{list_type}_complete"] = True
                write_json(checkpoint_path, checkpoint)
                break
            append_jsonl(part, [dict(row) | {"_source_list_type": list_type} for row in rows])
            checkpoint[list_type] = page
            write_json(checkpoint_path, checkpoint)
            if page % 100 == 0:
                print(f"fourmeme {list_type}: pages={page} latest_rows={len(rows)}", flush=True)
            page += 1
            time.sleep(delay)
        page_counts[list_type] = int(checkpoint.get(list_type, 0))
    final_path = output / "tokens.jsonl"
    final = finalize_jsonl(parts, final_path, ("tokenAddress",))
    metadata = {
        "source_id": "fourmeme_official_public_token_search",
        "dataset_role": "metadata_validation_only",
        "source_url": FOURMEME_URL,
        "collected_at_utc": utc_now(),
        "request_contract": {"type": "NEW", "status": "ALL", "sort": "ASC", "page_size": 100, "list_types": list(FOURMEME_LIST_TYPES)},
        "limitation": "The API returns at most 1,000 rows per query and is not the full launch universe.",
        "pages": page_counts,
        **final,
    }
    write_json(output / "SOURCE.json", metadata)
    return metadata


def collect_sunpump(output: Path, delay: float, max_pages: int) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / "checkpoint.json"
    checkpoint = load_json(checkpoint_path, {})
    page = int(checkpoint.get("page", 0)) + 1
    part = output / "sunpump_pages.jsonl"
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    while page <= max_pages:
        payload = request_json(lambda: session.get(SUNPUMP_URL, params={"page": page, "size": 50}, timeout=45))
        data = payload.get("data") or {}
        rows = data.get("tokens") or []
        if not isinstance(rows, list):
            raise RuntimeError(f"Unexpected SunPump data on page {page}")
        if not rows:
            checkpoint["complete"] = True
            write_json(checkpoint_path, checkpoint)
            break
        append_jsonl(part, rows)
        checkpoint["page"] = page
        write_json(checkpoint_path, checkpoint)
        if page % 100 == 0:
            print(f"sunpump: pages={page} latest_rows={len(rows)} last_id={rows[-1].get('id')}", flush=True)
        page += 1
        time.sleep(delay)
    final_path = output / "tokens.jsonl"
    final = finalize_jsonl([part], final_path, ("contractAddress", "tokenAddress"))
    metadata = {
        "source_id": "sunpump_official_public_token_list",
        "dataset_role": "metadata_validation_only",
        "source_url": SUNPUMP_URL,
        "collected_at_utc": utc_now(),
        "request_contract": {"page_size": 50, "ordering": "id:ASC"},
        "limitation": "The API returns at most 1,000 rows and is not the full launch universe.",
        "pages": int(checkpoint.get("page", 0)),
        **final,
    }
    write_json(output / "SOURCE.json", metadata)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("platform", choices=("fourmeme", "sunpump"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=0.12)
    parser.add_argument("--max-pages", type=int, default=100_000)
    args = parser.parse_args()
    if args.platform == "fourmeme":
        result = collect_fourmeme(args.output.resolve(), args.delay, args.max_pages)
    else:
        result = collect_sunpump(args.output.resolve(), args.delay, args.max_pages)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
