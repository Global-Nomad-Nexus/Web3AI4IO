from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "canonical" / "v1" / "solana"


def rows(name: str) -> int:
    return pq.read_metadata(OUTPUT / f"{name}.parquet").num_rows


def test_release_counts() -> None:
    assert rows("tokens") == 832_941
    assert rows("launches") == 832_941
    assert rows("lifecycle_events") == 832_941
    assert rows("token_metadata") == 1_651
    assert rows("pool_windows") == 4_953
    assert rows("decoded_swaps") == 173_102
    assert rows("token_horizons") == 882
    assert rows("coverage_ledger") == 1_651


def test_primary_keys_are_unique() -> None:
    for name, key in (
        ("tokens", "token_id"),
        ("launches", "token_id"),
        ("lifecycle_events", "token_id"),
        ("token_metadata", "token_id"),
        ("coverage_ledger", "token_id"),
    ):
        table = pq.read_table(OUTPUT / f"{name}.parquet", columns=[key])
        values = table[key].to_pylist()
        assert len(values) == len(set(values))


def test_coverage_is_explicit() -> None:
    report = json.loads((OUTPUT / "quality_report.json").read_text())
    statuses = report["solana_core"]["coverage"]["coverage_status"]
    assert statuses == {
        "decoded_lower_bound_page_capped": 294,
        "no_decoded_swap_data": 1_357,
    }


def test_all_tables_use_canonical_chain_id() -> None:
    expected = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
    for path in OUTPUT.glob("*.parquet"):
        table = pq.read_table(path, columns=["chain_id"])
        assert set(table["chain_id"].to_pylist()) == {expected}
