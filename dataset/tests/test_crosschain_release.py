import json
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]


def manifest(chain: str) -> dict:
    return json.loads((ROOT / f"dataset/releases/v1/{chain}_core.json").read_text())


def table_path(chain: str, name: str) -> Path:
    return ROOT / f"data/canonical/v1/{chain}/{name}/part-00000.parquet"


def table(chain: str, name: str, columns: list[str] | None = None):
    return pq.read_table(table_path(chain, name), columns=columns)


def values(chain: str, name: str, column: str):
    return table(chain, name).column(column).combine_chunks()


def assert_unique(chain: str, name: str, column: str) -> None:
    data = values(chain, name, column)
    assert len(data) == pc.count_distinct(data).as_py()


def assert_subset(child, parent) -> None:
    if len(child):
        assert pc.all(pc.is_in(child, value_set=parent)).as_py()


def test_base_release_is_complete_for_declared_window() -> None:
    release = manifest("base")
    assert release["tables"]["tokens"]["rows"] == 62_618
    assert release["tables"]["launches"]["rows"] == 62_618
    assert release["tables"]["protocol_config"]["rows"] == 62_618
    assert release["tables"]["pools"]["rows"] == 62_618
    assert release["tables"]["liquidity_initializations"]["rows"] == 149_921
    assert release["tables"]["lifecycle_events"]["rows"] == 281_921
    coverage = table("base", "coverage_ledger").to_pydict()
    assert set(coverage["coverage_status"]) == {"canonical_core_complete"}
    for field in (
        "creator_status", "protocol_config_status", "pool_mapping_status",
        "pool_initialization_status", "liquidity_initialization_status",
    ):
        assert set(coverage[field]) == {"observed"}
    assert set(coverage["graduation_status"]) == {"not_applicable"}
    assert set(coverage["migration_status"]) == {"not_applicable"}
    assert set(coverage["decoded_swaps_status"]) == {"not_collected_by_policy"}
    assert not any(coverage["decoded_swaps_available"])


def test_phase_four_launch_universes_are_onchain_canonical_core() -> None:
    for chain in ("bnb", "tron"):
        release = manifest(chain)
        token_count = release["tables"]["tokens"]["rows"]
        assert token_count > 0
        assert release["tables"]["launches"]["rows"] == token_count
        assert release["tables"]["protocol_config"]["rows"] == token_count
        assert release["tables"]["coverage_ledger"]["rows"] == token_count
        assert release["canonical_core_coverage"]["launch_universe"] == token_count

        launches = table(chain, "launches", ["coverage_role", "source_id"]).to_pydict()
        assert set(launches["coverage_role"]) == {"canonical_core"}
        assert all("official_public" not in source for source in launches["source_id"])


def test_phase_four_core_identity_is_unique() -> None:
    for chain in ("bnb", "tron"):
        for name, column in (
            ("tokens", "token_id"),
            ("launches", "launch_id"),
            ("protocol_config", "token_id"),
            ("pools", "pool_id"),
            ("liquidity_initializations", "liquidity_event_id"),
            ("lifecycle_events", "lifecycle_event_id"),
            ("token_metadata", "token_id"),
            ("coverage_ledger", "token_id"),
        ):
            assert_unique(chain, name, column)


def test_crosschain_identity_is_unique_and_referentially_complete() -> None:
    for chain in ("base", "bnb", "tron"):
        tokens = values(chain, "tokens", "token_id")
        launches = values(chain, "launches", "token_id")
        coverage = values(chain, "coverage_ledger", "token_id")
        assert len(tokens) == pc.count_distinct(tokens).as_py()
        assert len(launches) == len(tokens)
        assert len(coverage) == len(tokens)
        assert_subset(launches, tokens)
        assert_subset(coverage, tokens)


def test_phase_four_foreign_keys_have_no_orphans() -> None:
    for chain in ("bnb", "tron"):
        tokens = values(chain, "tokens", "token_id")
        pools = values(chain, "pools", "pool_id")
        for name in (
            "protocol_config", "pools", "liquidity_initializations",
            "lifecycle_events", "token_metadata", "coverage_ledger",
        ):
            assert_subset(values(chain, name, "token_id"), tokens)
        assert_subset(values(chain, "liquidity_initializations", "pool_id"), pools)
        lifecycle_pool = pc.drop_null(values(chain, "lifecycle_events", "pool_id"))
        assert_subset(lifecycle_pool, pools)


def test_all_crosschain_tables_share_common_dimensions() -> None:
    for chain in ("base", "bnb", "tron"):
        for name in (
            "tokens", "launches", "protocol_config", "pools", "liquidity_initializations",
            "lifecycle_events", "token_metadata", "token_state_snapshots", "coverage_ledger",
        ):
            fields = set(pq.read_schema(table_path(chain, name)).names)
            assert {"dataset_version", "chain_id", "platform_id"}.issubset(fields)


def test_base_pool_core_is_onchain_complete_and_positive() -> None:
    launches = table("base", "launches").to_pydict()
    pools = table("base", "pools").to_pydict()
    liquidity = table("base", "liquidity_initializations").to_pydict()
    assert len(set(launches["pool_id"])) == 62_618
    assert set(pools["pool_id"]) == set(launches["pool_id"])
    assert set(pools["mapping_status"]) == {"observed"}
    assert set(pools["initialization_status"]) == {"observed"}
    assert all(int(value) > 0 for value in liquidity["liquidity_delta_raw"])
    assert set(liquidity["pool_id"]) == set(pools["pool_id"])


def test_phase_four_coverage_uses_explicit_three_state_semantics() -> None:
    allowed = {"observed", "not_collected", "not_applicable"}
    conditional_fields = (
        "pool_mapping_status", "pool_initialization_status",
        "liquidity_initialization_status", "graduation_status", "migration_status",
    )
    for chain in ("bnb", "tron"):
        coverage = table(chain, "coverage_ledger", [
            "token_id", "creator_status", "protocol_config_status",
            "pool_mapping_status", "pool_initialization_status",
            "liquidity_initialization_status", "graduation_status",
            "migration_status", "coverage_status",
        ]).to_pydict()
        assert set(coverage["creator_status"]) == {"observed"}
        assert set(coverage["protocol_config_status"]) == {"observed"}
        for field in conditional_fields:
            assert set(coverage[field]).issubset(allowed)
        assert set(coverage["coverage_status"]).issubset(
            {"canonical_core_complete", "canonical_core_partial"}
        )

        pool_tokens = set(table(chain, "pools").column("token_id").to_pylist())
        liquidity_tokens = set(
            table(chain, "liquidity_initializations").column("token_id").to_pylist()
        )
        for token_id, mapping, initialization, liquidity, migration in zip(
            coverage["token_id"], coverage["pool_mapping_status"],
            coverage["pool_initialization_status"],
            coverage["liquidity_initialization_status"], coverage["migration_status"],
        ):
            assert (mapping == "observed") == (token_id in pool_tokens)
            assert (initialization == "observed") == (token_id in pool_tokens)
            assert (liquidity == "observed") == (token_id in liquidity_tokens)
            assert (migration == "observed") == (token_id in pool_tokens)


def test_phase_four_official_api_is_metadata_enrichment_only() -> None:
    expected_metadata_sources = {
        "bnb": "fourmeme_official_public_token_search",
        "tron": "sunpump_official_public_token_list",
    }
    for chain in ("bnb", "tron"):
        tokens = values(chain, "tokens", "token_id")
        metadata = table(chain, "token_metadata")
        metadata_tokens = metadata.column("token_id").combine_chunks()
        assert_subset(metadata_tokens, tokens)
        assert 0 < metadata.num_rows < len(tokens)
        assert set(metadata.column("source_id").to_pylist()).issubset(
            {expected_metadata_sources[chain]}
        )
        assert manifest(chain)["tables"]["token_metadata"]["rows"] == metadata.num_rows
        assert manifest(chain)["tables"]["tokens"]["rows"] == len(tokens)


def test_phase_four_trading_and_holder_data_are_not_collected() -> None:
    forbidden_tables = {"decoded_swaps", "holders", "holder_balances", "trades", "trading"}
    for chain in ("bnb", "tron"):
        chain_root = ROOT / f"data/canonical/v1/{chain}"
        assert forbidden_tables.isdisjoint(path.name for path in chain_root.iterdir())
        assert table(chain, "token_state_snapshots").num_rows == 0
        coverage = table(chain, "coverage_ledger", [
            "decoded_swaps_available", "state_snapshot_available",
            "decoded_swaps_status", "holder_data_status", "trading_data_status",
        ]).to_pydict()
        assert not any(coverage["decoded_swaps_available"])
        assert not any(coverage["state_snapshot_available"])
        assert set(coverage["decoded_swaps_status"]) == {"not_collected"}
        assert set(coverage["holder_data_status"]) == {"not_collected"}
        assert set(coverage["trading_data_status"]) == {"not_collected"}
