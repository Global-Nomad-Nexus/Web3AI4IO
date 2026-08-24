from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


VERSION = "v1"
ELIGIBILITY = {"accepted", "conditional", "rejected"}

EVENT_SCHEMA = pa.schema([
    pa.field("dataset_version", pa.string(), nullable=False),
    pa.field("event_id", pa.string(), nullable=False),
    pa.field("event_aliases", pa.string()),
    pa.field("event_type", pa.string(), nullable=False),
    pa.field("platform_id", pa.string(), nullable=False),
    pa.field("chain_id", pa.string(), nullable=False),
    pa.field("rule_family", pa.string(), nullable=False),
    pa.field("rule_change", pa.string(), nullable=False),
    pa.field("announcement_at", pa.timestamp("us", tz="UTC")),
    pa.field("activation_at", pa.timestamp("us", tz="UTC")),
    pa.field("anticipation_start_at", pa.timestamp("us", tz="UTC")),
    pa.field("concurrent_shocks", pa.string()),
    pa.field("comparison_unit_status", pa.string(), nullable=False),
    pa.field("eligibility_status", pa.string(), nullable=False),
    pa.field("rejection_reason", pa.string()),
    pa.field("hypothesis_tags", pa.string(), nullable=False),
    pa.field("claim_boundary", pa.string(), nullable=False),
    pa.field("evidence_status", pa.string(), nullable=False),
])

EVIDENCE_SCHEMA = pa.schema([
    pa.field("dataset_version", pa.string(), nullable=False),
    pa.field("evidence_id", pa.string(), nullable=False),
    pa.field("event_id", pa.string(), nullable=False),
    pa.field("evidence_type", pa.string(), nullable=False),
    pa.field("evidence_role", pa.string(), nullable=False),
    pa.field("observed_at", pa.timestamp("us", tz="UTC")),
    pa.field("block_number", pa.int64()),
    pa.field("transaction_hash", pa.string()),
    pa.field("next_block_verification", pa.string(), nullable=False),
    pa.field("verification_status", pa.string(), nullable=False),
    pa.field("supports_eligibility", pa.string(), nullable=False),
    pa.field("source_id", pa.string(), nullable=False),
    pa.field("source_path", pa.string(), nullable=False),
    pa.field("source_sha256", pa.string(), nullable=False),
    pa.field("evidence_detail", pa.string(), nullable=False),
    pa.field("claim_boundary", pa.string(), nullable=False),
])

CSV_FIELDS = [
    "event_id", "event_aliases", "event_type", "platform_id", "chain_id",
    "rule_family", "rule_change", "announcement_timestamp_utc",
    "activation_timestamp_utc", "activation_evidence", "activation_transaction_hash",
    "next_block_verification", "anticipation_boundary_utc", "concurrent_shocks",
    "comparison_unit_status", "eligibility_status", "rejection_reason",
    "hypothesis_tags", "claim_boundary", "evidence_status",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_text(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_rows(path: Path, key: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != VERSION:
        raise ValueError(f"Unsupported schema version in {path}")
    return payload[key]


def verify_base_activation(repo: Path, evidence: list[dict[str, Any]]) -> None:
    target = next(row for row in evidence if row["evidence_id"] == "clanker_v41_first_observed_module_launch")
    launches = pq.read_table(
        repo / "data/canonical/v1/base/launches/part-00000.parquet",
        columns=["block_number", "transaction_hash", "launch_at"],
    )
    match = pc.and_(
        pc.equal(launches["block_number"], target["block_number"]),
        pc.equal(launches["transaction_hash"], target["transaction_hash"]),
    )
    rows = launches.filter(match)
    if rows.num_rows != 1:
        raise ValueError("Clanker activation transaction must occur exactly once in canonical Base launches")
    observed = rows["launch_at"][0].as_py()
    if observed != parse_timestamp(target["observed_at"]):
        raise ValueError("Clanker activation timestamp disagrees with canonical Base launches")


def validate(repo: Path, events: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
    event_ids = [row["event_id"] for row in events]
    evidence_ids = [row["evidence_id"] for row in evidence]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("Duplicate event_id")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("Duplicate evidence_id")
    by_event: dict[str, list[dict[str, Any]]] = {event_id: [] for event_id in event_ids}
    source_registry = json.loads((repo / "dataset/source_registry.json").read_text(encoding="utf-8"))
    source_ids = {row["source_id"] for row in source_registry["sources"]}
    for row in evidence:
        if row["event_id"] not in by_event:
            raise ValueError(f"Orphan evidence event_id: {row['event_id']}")
        if row["supports_eligibility"] not in ELIGIBILITY:
            raise ValueError(f"Invalid evidence eligibility: {row['supports_eligibility']}")
        if row["source_id"] not in source_ids:
            raise ValueError(f"Unregistered evidence source_id: {row['source_id']}")
        source = repo / row["source_path"]
        if not source.is_file():
            raise ValueError(f"Missing evidence source: {row['source_path']}")
        row["source_sha256"] = sha256(source)
        by_event[row["event_id"]].append(row)
    for row in events:
        status = row["eligibility_status"]
        if status not in ELIGIBILITY:
            raise ValueError(f"Invalid event eligibility: {status}")
        if status == "rejected" and not row.get("rejection_reason"):
            raise ValueError(f"Rejected event lacks reason: {row['event_id']}")
        if status == "accepted":
            if not row.get("activation_at"):
                raise ValueError(f"Accepted event lacks activation time: {row['event_id']}")
            accepted_activation = [
                item for item in by_event[row["event_id"]]
                if item["supports_eligibility"] == "accepted" and item["evidence_role"] == "activation_boundary"
            ]
            if not accepted_activation:
                raise ValueError(f"Accepted event lacks accepted activation evidence: {row['event_id']}")
        if not by_event[row["event_id"]]:
            raise ValueError(f"Event lacks evidence rows: {row['event_id']}")
    verify_base_activation(repo, evidence)


def materialize(events: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> tuple[pa.Table, pa.Table]:
    event_rows = []
    for row in events:
        converted = dict(row)
        converted["dataset_version"] = VERSION
        for field in ("announcement_at", "activation_at", "anticipation_start_at"):
            converted[field] = parse_timestamp(converted.get(field))
        event_rows.append(converted)
    evidence_rows = []
    for row in evidence:
        converted = dict(row)
        converted["dataset_version"] = VERSION
        converted["observed_at"] = parse_timestamp(converted.get("observed_at"))
        evidence_rows.append(converted)
    return (
        pa.Table.from_pylist(event_rows, schema=EVENT_SCHEMA),
        pa.Table.from_pylist(evidence_rows, schema=EVIDENCE_SCHEMA),
    )


def export_csv(path: Path, event_table: pa.Table, evidence_table: pa.Table) -> None:
    events = event_table.to_pylist()
    evidence_by_event: dict[str, list[dict[str, Any]]] = {}
    for row in evidence_table.to_pylist():
        evidence_by_event.setdefault(row["event_id"], []).append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for event in events:
            activation = [item for item in evidence_by_event[event["event_id"]] if item["evidence_role"] == "activation_boundary"]
            primary = activation[0] if activation else evidence_by_event[event["event_id"]][0]
            writer.writerow({
                "event_id": event["event_id"],
                "event_aliases": event["event_aliases"] or "",
                "event_type": event["event_type"],
                "platform_id": event["platform_id"],
                "chain_id": event["chain_id"],
                "rule_family": event["rule_family"],
                "rule_change": event["rule_change"],
                "announcement_timestamp_utc": utc_text(event["announcement_at"]),
                "activation_timestamp_utc": utc_text(event["activation_at"]),
                "activation_evidence": primary["evidence_detail"],
                "activation_transaction_hash": primary["transaction_hash"] or "",
                "next_block_verification": primary["next_block_verification"],
                "anticipation_boundary_utc": utc_text(event["anticipation_start_at"]),
                "concurrent_shocks": event["concurrent_shocks"] or "",
                "comparison_unit_status": event["comparison_unit_status"],
                "eligibility_status": event["eligibility_status"],
                "rejection_reason": event["rejection_reason"] or "",
                "hypothesis_tags": event["hypothesis_tags"],
                "claim_boundary": event["claim_boundary"],
                "evidence_status": event["evidence_status"],
            })


def build(repo: Path) -> dict[str, Any]:
    registry_path = repo / "dataset/events/v1/event_registry.json"
    evidence_path = repo / "dataset/events/v1/event_evidence.json"
    events = load_rows(registry_path, "events")
    evidence = load_rows(evidence_path, "evidence")
    validate(repo, events, evidence)
    event_table, evidence_table = materialize(events, evidence)
    canonical = repo / "data/canonical/v1/events"
    canonical.mkdir(parents=True, exist_ok=True)
    event_output = canonical / "event_registry.parquet"
    evidence_output = canonical / "event_evidence.parquet"
    pq.write_table(event_table, event_output, compression="zstd")
    pq.write_table(evidence_table, evidence_output, compression="zstd")
    csv_output = repo / "data/release/v1/events.csv"
    export_csv(csv_output, event_table, evidence_table)
    result = {
        "release": VERSION,
        "events": {
            "rows": event_table.num_rows,
            "eligibility_counts": {
                status: sum(row["eligibility_status"] == status for row in events)
                for status in sorted(ELIGIBILITY)
            },
            "sha256": sha256(event_output),
        },
        "event_evidence": {"rows": evidence_table.num_rows, "sha256": sha256(evidence_output)},
        "public_events_csv": {"rows": event_table.num_rows, "sha256": sha256(csv_output)},
        "source_registry_sha256": sha256(registry_path),
        "source_evidence_sha256": sha256(evidence_path),
        "claim_boundary": "This release registers event eligibility and evidence. It does not itself produce event-aligned metrics or causal estimates.",
    }
    manifest = repo / "dataset/releases/v1/events_core.json"
    manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(build(args.repo.resolve()), indent=2))


if __name__ == "__main__":
    main()
