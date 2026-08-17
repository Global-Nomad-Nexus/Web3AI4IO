# Web3AI4IO Data Pipeline

## Event layer

The project-level event layer is built from reviewed registry records and traceable evidence:

```text
data_pipeline/.venv/bin/python data_pipeline/scripts/build_events.py
```

It writes canonical `event_registry` and `event_evidence` Parquet tables under `data/canonical/v1/events/`, plus the teacher-facing `data/release/v1/events.csv`. Event eligibility is deliberately separate from chain coverage. In v1, Base has one accepted first-observed module-adoption event, Solana has one conditional registered event boundary, and BNB Chain and TRON remain rejected event candidates despite having canonical chain datasets.

This package builds an extensible multi chain launchpad dataset. It separates immutable external sources, canonical tables, coverage evidence, and experiment specific derived datasets. The published tables live on Hugging Face. This directory keeps builders, schemas, tests, and release manifests.

## Current accepted scope

1. Phase 1 builds the canonical Shilin baseline and reproduces the RED PUMP cleaning path.
2. Phase 2 builds the Solana Pump.fun and PumpSwap core dataset.
3. Phase 3 builds the complete applicable Base Clanker canonical core for the declared 2025 08 18 through 2025 10 01 UTC window.
4. Phase 4 expands the common crosschain schema with complete paginated onchain launch universes and accepted canonical core releases for BNB Chain Four.meme and TRON SunPump.
5. Offchain event packs remain outside the current acceptance scope.

## Storage layers

1. Immutable source bundles live under `data/external/`.
2. Generated Parquet tables live under `data/canonical/` and are excluded from Git.
3. Versioned schemas, source registries, build code, quality reports, and release manifests remain in Git.

## Build

From the repository root:

```text
data_pipeline/.venv/bin/python data_pipeline/scripts/build_solana_core.py
data_pipeline/.venv/bin/python data_pipeline/scripts/build_crosschain_core.py
PYTHONPATH=data_pipeline/src data_pipeline/.venv/bin/python -m pytest data_pipeline/tests
```

The build writes `data/canonical/v1/solana/quality_report.json`. This report includes source and table SHA256 digests, exact row counts, and decoded swap coverage status.

## Data semantics

`pool_windows.transaction_proxy_count` is derived from bounded Solana RPC signature scans. It is not a decoded swap count. `decoded_swaps` and `token_horizons` preserve the delivered Moralis data and its page cap status. Use `coverage_ledger` before any downstream analysis.

The decoded swap snapshot is validation data only. The project will preserve Shilin's delivered state and will not collect additional decoded Solana swaps. See `SHILIN_LIMITATION.md`.

The crosschain release uses nine common tables: `tokens`, `launches`, `protocol_config`, `pools`, `liquidity_initializations`, `lifecycle_events`, `token_metadata`, `token_state_snapshots`, and `coverage_ledger`.

Base is authoritative inside its declared scan window. Every one of the 62,618 fixed launches has observed creator and protocol configuration, one observed PoolManager Initialize event, and at least one observed positive launch transaction ModifyLiquidity event. Bonding curve graduation and migration are `not_applicable` for this direct Uniswap v4 launch mechanism. Decoded swaps, holder data, and trading outcomes are `not_collected_by_policy`.

Four.meme launch coverage comes from BNB Chain archive RPC contract events. The collected universe contains 1,593,679 unique `TokenCreate` events, split into 5,570 V1 and 1,588,109 V2 events, plus 106 `TradeStop` and 15,403 `LiquidityAdded` lifecycle events.

SunPump launch coverage comes from TronGrid contract events scanned to fingerprint exhaustion. The collected source contains 104,548 `TokenCreate`, 1,831 `TokenLaunched`, and one `NewImplementation` event.

The two 1,000 row official API snapshots are metadata enrichment subsets only. They do not define either launch universe or any chain level denominator. The canonical releases contain 1,593,679 BNB launches and 104,548 TRON launches. Receipt enrichment and canonical table generation passed the Phase 4 acceptance tests. Decoded trading, holder, and swap data are not collected for either chain.
