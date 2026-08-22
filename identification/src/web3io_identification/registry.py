from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


REQUIRED_COLUMNS = (
    "event_id",
    "platform",
    "chain",
    "event_family",
    "rule_change",
    "effective_at_utc",
    "first_party_source_url",
    "onchain_activation_ref",
    "treatment_direction",
    "primary_outcomes_available",
    "candidate_controls",
    "anticipation_days",
    "concurrent_events",
    "repeat_event_group",
    "status",
    "exclusion_reason",
    "notes",
)

ACCEPTED_STATUSES = {"accepted", "accepted_staggered"}
REJECTED_STATUSES = {"rejected_main_did", "out_of_identification_primary_scope"}


@dataclass(frozen=True)
class GateSummary:
    total_events: int
    accepted_events: int
    accepted_platforms: int
    accepted_families: dict[str, int]
    staggered_gate_passes: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "total_events": self.total_events,
            "accepted_events": self.accepted_events,
            "accepted_platforms": self.accepted_platforms,
            "accepted_families": self.accepted_families,
            "staggered_gate_passes": self.staggered_gate_passes,
        }


def _validate_timestamp(value: str, event_id: str) -> None:
    if not value:
        return
    if not value.endswith("Z"):
        raise ValueError(f"{event_id}: effective_at_utc must end in Z")
    datetime.fromisoformat(value.removesuffix("Z") + "+00:00")


def load_registry(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REQUIRED_COLUMNS:
            raise ValueError("event_registry.csv columns do not match the registered schema")
        rows = list(reader)

    ids: set[str] = set()
    for row in rows:
        event_id = row["event_id"]
        if not event_id:
            raise ValueError("Every registry row requires event_id")
        if event_id in ids:
            raise ValueError(f"Duplicate event_id: {event_id}")
        ids.add(event_id)
        _validate_timestamp(row["effective_at_utc"], event_id)
        if not row["first_party_source_url"].startswith("https://"):
            raise ValueError(f"{event_id}: first_party_source_url must be HTTPS")
        if row["status"] in ACCEPTED_STATUSES:
            missing = [
                field
                for field in (
                    "effective_at_utc",
                    "onchain_activation_ref",
                    "candidate_controls",
                    "primary_outcomes_available",
                )
                if not row[field]
            ]
            if missing:
                raise ValueError(f"{event_id}: accepted event missing {', '.join(missing)}")
        if row["status"] in REJECTED_STATUSES and not (row["exclusion_reason"] or row["notes"]):
            raise ValueError(f"{event_id}: rejected event requires a reason")
    return rows


def summarize_gate(rows: Iterable[dict[str, str]]) -> GateSummary:
    rows = list(rows)
    accepted = [row for row in rows if row["status"] in ACCEPTED_STATUSES]
    platforms = {row["platform"] for row in accepted}
    families: dict[str, int] = {}
    for row in accepted:
        families[row["event_family"]] = families.get(row["event_family"], 0) + 1
    comparable_family_exists = any(count >= 3 for count in families.values())
    return GateSummary(
        total_events=len(rows),
        accepted_events=len(accepted),
        accepted_platforms=len(platforms),
        accepted_families=families,
        staggered_gate_passes=(len(platforms) >= 3 and comparable_family_exists),
    )


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    rows = load_registry(root / "event_registry.csv")
    print(json.dumps(summarize_gate(rows).as_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
