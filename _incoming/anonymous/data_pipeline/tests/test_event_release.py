import csv
import hashlib
import json
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

from web3ai4io_dataset.build_events import build


ROOT = Path(__file__).resolve().parents[2]
EVENTS = ROOT / "data/canonical/v1/events/event_registry.parquet"
EVIDENCE = ROOT / "data/canonical/v1/events/event_evidence.parquet"
PUBLIC = ROOT / "data/release/v1/events.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_event_release_builds_deterministically() -> None:
    build(ROOT)
    first = {path: sha256(path) for path in (EVENTS, EVIDENCE, PUBLIC)}
    build(ROOT)
    assert first == {path: sha256(path) for path in (EVENTS, EVIDENCE, PUBLIC)}


def test_event_registry_has_valid_eligibility_and_evidence() -> None:
    events = pq.read_table(EVENTS)
    evidence = pq.read_table(EVIDENCE)
    assert events.num_rows == 4
    assert evidence.num_rows == 6
    assert pc.count_distinct(events["event_id"]).as_py() == events.num_rows
    assert pc.count_distinct(evidence["evidence_id"]).as_py() == evidence.num_rows
    assert set(events["eligibility_status"].to_pylist()) == {"accepted", "conditional", "rejected"}
    assert set(evidence["event_id"].to_pylist()).issubset(set(events["event_id"].to_pylist()))
    rows = events.to_pylist()
    for row in rows:
        if row["eligibility_status"] == "rejected":
            assert row["rejection_reason"]
        if row["eligibility_status"] == "accepted":
            assert row["activation_at"] is not None


def test_clanker_activation_matches_canonical_base_launch() -> None:
    events = pq.read_table(EVENTS).to_pylist()
    event = next(row for row in events if row["event_id"] == "CLANKER_V41_MODULE_FIRST_OBSERVED_BASE_20250826")
    assert event["eligibility_status"] == "accepted"
    assert event["event_aliases"] == "CLANKER_SNIPER_DECAY_V41_BASE_20250826"
    assert event["announcement_at"] is None
    assert event["anticipation_start_at"] is None


def test_bnb_and_tron_coverage_is_not_promoted_to_event_evidence() -> None:
    events = pq.read_table(EVENTS).to_pylist()
    by_chain = {row["chain_id"]: row for row in events}
    for chain in ("eip155:56", "tron:mainnet"):
        assert by_chain[chain]["eligibility_status"] == "rejected"
        assert by_chain[chain]["activation_at"] is None
        assert by_chain[chain]["evidence_status"] == "canonical_chain_coverage_only"


def test_public_events_csv_matches_teacher_facing_contract() -> None:
    with PUBLIC.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "event_id", "platform_id", "chain_id", "rule_family",
        "announcement_timestamp_utc", "activation_timestamp_utc",
        "activation_evidence", "activation_transaction_hash",
        "next_block_verification", "anticipation_boundary_utc",
        "concurrent_shocks", "comparison_unit_status", "eligibility_status",
        "rejection_reason", "hypothesis_tags", "claim_boundary",
    }
    assert len(rows) == 4
    assert required.issubset(rows[0])
    assert not any(row["eligibility_status"] == "accepted" and not row["activation_evidence"] for row in rows)


def test_event_manifest_records_current_hashes() -> None:
    manifest = json.loads((ROOT / "data_pipeline/releases/v1/events_core.json").read_text())
    assert manifest["events"]["sha256"] == sha256(EVENTS)
    assert manifest["event_evidence"]["sha256"] == sha256(EVIDENCE)
    assert manifest["public_events_csv"]["sha256"] == sha256(PUBLIC)


def test_next_block_verification_is_not_overstated() -> None:
    evidence = pq.read_table(EVIDENCE).to_pylist()
    activation = next(row for row in evidence if row["evidence_id"] == "clanker_v41_first_observed_module_launch")
    assert activation["next_block_verification"] == "not_performed"
