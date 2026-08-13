#!/usr/bin/env python3
"""Recover public Pump.fun metadata from a historical Git tree."""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import tarfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_COMMIT = "783c911"
ARCHIVE_PATH = "Shilin/artifacts/external_validation/raw_coin_metadata"
OUT = ROOT / "Claire" / "data_expansion" / "artifacts"


def timestamp_utc(value: object) -> str:
    if value in (None, ""):
        return ""
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return ""
    if timestamp > 10_000_000_000:
        timestamp /= 1000
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_telegram(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("@"):
        return text[1:].split("/")[0].split("?")[0]
    candidate = text if "://" in text else f"https://{text}"
    parsed = urlparse(candidate)
    if parsed.netloc.lower() in {"t.me", "telegram.me", "telegram.dog", "www.t.me"}:
        segments = [segment for segment in parsed.path.split("/") if segment]
        if segments and segments[0] not in {"joinchat", "share", "addstickers", "proxy"}:
            return segments[0].lstrip("@+")
    return ""


def load_archive(commit: str) -> tuple[list[dict[str, object]], dict[str, int]]:
    process = subprocess.run(
        ["git", "archive", "--format=tar", commit, ARCHIVE_PATH],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    rows: list[dict[str, object]] = []
    key_counts: dict[str, int] = {}
    with tarfile.open(fileobj=io.BytesIO(process.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            payload = json.load(handle)
            for key, value in payload.items():
                if value not in (None, "", [], {}):
                    key_counts[key] = key_counts.get(key, 0) + 1
            telegram = payload.get("telegram", "")
            rows.append(
                {
                    "mint": payload.get("mint", Path(member.name).stem),
                    "created_timestamp_utc": timestamp_utc(payload.get("created_timestamp")),
                    "complete": payload.get("complete", ""),
                    "pool_address": payload.get("pool_address", ""),
                    "telegram_raw": telegram,
                    "telegram_handle": normalize_telegram(telegram),
                    "twitter": payload.get("twitter", ""),
                    "website": payload.get("website", ""),
                    "source_commit": commit,
                    "source_path": member.name,
                }
            )
    return rows, key_counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", default=DEFAULT_COMMIT)
    args = parser.parse_args()

    rows, key_counts = load_archive(args.commit)
    rows.sort(key=lambda row: str(row["mint"]))
    OUT.mkdir(parents=True, exist_ok=True)
    output_csv = OUT / "pump_metadata_git_history.csv"
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    handle_counts = Counter(str(row["telegram_handle"]).lower() for row in rows if row["telegram_handle"])
    telegram_rows = []
    for row in rows:
        handle = str(row["telegram_handle"]).lower()
        if not handle:
            continue
        telegram_rows.append(
            {
                "mint": row["mint"],
                "created_timestamp_utc": row["created_timestamp_utc"],
                "telegram_handle": handle,
                "telegram_raw": row["telegram_raw"],
                "tokens_linked_to_handle": handle_counts[handle],
                "collection_status": "not_started",
                "source_commit": args.commit,
            }
        )
    telegram_output = OUT / "telegram_collection_frame.csv"
    with telegram_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(telegram_rows[0]))
        writer.writeheader()
        writer.writerows(telegram_rows)

    summary = {
        "source_commit": args.commit,
        "source_tree": ARCHIVE_PATH,
        "rows": len(rows),
        "unique_mints": len({row["mint"] for row in rows}),
        "created_time_start_utc": min(row["created_timestamp_utc"] for row in rows if row["created_timestamp_utc"]),
        "created_time_end_utc": max(row["created_timestamp_utc"] for row in rows if row["created_timestamp_utc"]),
        "telegram_raw_nonempty": sum(bool(row["telegram_raw"]) for row in rows),
        "telegram_handle_valid": sum(bool(row["telegram_handle"]) for row in rows),
        "telegram_unique_handles": len(handle_counts),
        "twitter_nonempty": sum(bool(row["twitter"]) for row in rows),
        "website_nonempty": sum(bool(row["website"]) for row in rows),
        "nonempty_field_counts": dict(sorted(key_counts.items())),
        "output_csv": str(output_csv.relative_to(ROOT)),
        "telegram_collection_frame": str(telegram_output.relative_to(ROOT)),
    }
    output_json = OUT / "pump_metadata_git_history_summary.json"
    output_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
