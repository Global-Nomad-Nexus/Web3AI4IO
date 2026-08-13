# Web3AI4IO Four Phase Data Expansion Report

## Executive summary

This work converts the project from an experiment specific MVP into an extensible, provenance aware, four chain launchpad dataset. The accepted architecture now covers Solana Pump.fun and PumpSwap, Base Clanker, BNB Chain Four.meme, and TRON SunPump. The work is limited to source preservation, canonical data construction, lifecycle coverage, and quality control. It does not run Difference in Differences or any other causal experiment.

The four phases are complete within their declared boundaries. Solana preserves the delivered decoded swap snapshot as validation data rather than extending its page capped collection. Base is complete for the declared 2025 08 18 through 2025 10 01 UTC Clanker window. BNB Chain and TRON use onchain event acquisition to avoid the 1,000 row limits of their official metadata APIs. All 14 automated release tests pass.

## Project objective and design principles

The objective is to build a reusable dataset that future researchers can extend, rather than a dataset shaped around one planned experiment. The design follows five principles.

1. Launch universes come from authoritative or explicitly bounded onchain sources.
2. Immutable external inputs are separated from generated canonical tables.
3. Official platform APIs may enrich metadata but cannot silently define a chain universe when pagination is capped.
4. Every applicable core field has an explicit coverage state.
5. Decoded trading, swap, and holder collection is excluded unless separately approved and documented.

The storage model separates three layers. Immutable source artifacts live under `data/external/`. Generated Parquet tables live under `data/canonical/`. Schemas, source registries, collection and build code, release manifests, quality reports, and acceptance records live under `data_pipeline/`.

## Phase 1: Shilin bundle integration and reproducibility validation

Phase 1 preserves the supplied reproducibility bundle as an immutable validation source. All 2,174 supplied SHA256 entries were verified and the bundled test suite passed. The raw RED PUMP cleaning path reproduced 832,941 canonical terminal outcomes from 833,171 raw rows, consisting of 1,651 graduated tokens and 831,290 timeout tokens. Cleaning removed 215 malformed outcome rows and one nonpositive graduation time, then removed 14 duplicate terminal observations by mint. The source period 2026 05 08 through 2026 06 10 refers to the launch and terminal outcome observation period represented in the delivered RED PUMP files.

The canonical result was compared against Shilin's processed baseline across all 832,941 mint and outcome pairs, with zero mismatches. This phase establishes a reproducible baseline without attempting to reconstruct or improve Shilin's decoded swap acquisition.

The delivered Moralis snapshot contains 173,102 decoded swap rows for 294 of 1,651 graduated tokens. Most token horizons reached the configured page limit, so those windows remain lower bounds and validation data only. No further decoded Solana swap collection is planned. This limitation is recorded in `data_pipeline/SHILIN_LIMITATION.md`.

## Phase 2: Solana canonical core

Phase 2 converts the accepted Shilin baseline into typed canonical tables with stable identifiers, source provenance, SHA256 digests, and per token coverage records. The release includes tokens, launches, lifecycle events, graduated metadata, bounded pool transaction proxy windows, delivered decoded swaps, decoded horizon summaries, and a coverage ledger.

The 1, 7, and 30 day RPC window values are explicitly labelled transaction proxies and are not presented as decoded swap counts. Page capped Moralis windows are never labelled complete. Exact source and output digests are stored in `data_pipeline/releases/v1/solana_core.json`.

## Phase 3: Base Clanker canonical core

Phase 3 uses the existing 62,618 Clanker `TokenCreated` records as a fixed launch universe. Launches were not recollected. The accepted window is 2025 08 18 00:00:00 through 2025 10 01 23:59:59 UTC.

The release retains creator, message sender, protocol version, hook, MEV module, locker, paired token, starting tick, and extension supply as observed protocol configuration. Every token maps to one unique Uniswap v4 `pool_id`. Because a Uniswap v4 pool ID is not a deployed pool contract, `pool_address` remains null by design.

All 62,618 pools have one observed PoolManager `Initialize` event in the original launch transaction and at least one observed positive `ModifyLiquidity` event. The canonical release contains 62,618 pool initialization records and 149,921 positive initial liquidity position records. A launch transaction may create more than one liquidity position with different tick ranges, so initial liquidity rows can exceed pool rows without duplication. A further 6,764 zero delta calls are preserved as `liquidity_position_poked`, following the PoolManager definition of a zero delta call as a poke.

Clanker v4 launches directly into Uniswap v4, so bonding curve graduation and migration are `not_applicable`. Decoded swaps, holder data, and trading outcomes are `not_collected_by_policy`.

## Phase 4: BNB Chain Four.meme and TRON SunPump

### BNB Chain Four.meme

The Four.meme launch universe comes from BNB Chain archive RPC scans of TokenManager `TokenCreate` events through snapshot block 115,357,949, selected with 20 confirmations. The V1 manager is `0xec4549cadce5da21df6e6422d448034b5233bfbc`, deployed at block 40,138,454. The V2 manager is `0x5c952063c7fc8610ffdb798152d69f0b9550762b`, deployed at block 41,983,675. The universe contains 1,593,679 unique launches, split into 5,570 V1 and 1,588,109 V2 records. The finalized source record was written at 2026 08 12 01:06:03 UTC.

Lifecycle acquisition found 106 V1 `TradeStop` events and 15,403 V2 `LiquidityAdded` events. Receipt enrichment identified both Pancake V2 and Pancake V3 mechanisms. All 15,403 `LiquidityAdded` records have observed pool mappings, pool initializations, and initial liquidity amounts. For 701 pools that existed before the lifecycle transaction, archive state binary search located the first code block and the exact historical factory event; all 701 pool addresses matched the lifecycle pool.

The 106 V1 `TradeStop` events correspond to 106 unique tokens and 106 unique transactions. They are retained literally because the event only records that the manager stopped platform trading for the token and does not encode the destination pool or prove a graduation or migration mechanism. Pool mapping, initialization, graduation, and migration therefore remain `not_collected` rather than being inferred.

The Four.meme official token search API was collected at 2026 08 11 00:42:56 UTC using 100 row pages, ascending order, and the NOR and NOR_DEX list types. It stopped at 1,000 unique rows. Of these, 999 addresses belong to the onchain launch universe and enter canonical metadata. The raw snapshot SHA256 is `4dc796c6167a013e779b00b456459ce701769089828669aae73581f48fb1f9ee`. The API never defines launch membership or a chain denominator.

### TRON SunPump

The SunPump universe comes from confirmed TronGrid events for contract `TTfvyrAz86hbZk5iDpKD78pqLGgi8C7AAw`, using `meta.fingerprint` pagination until the fingerprint is absent while all other query parameters remain fixed. The source record was written at 2026 08 11 23:39:08 UTC. TokenCreate required 523 pages, TokenLaunched required 10 pages, and NewImplementation required one page. The resulting scan contains 104,548 `TokenCreate`, 1,831 `TokenLaunched`, and one `NewImplementation` event. TronGrid did not provide a single fixed end block in the source metadata, so the reproducible boundary is confirmed event pagination exhaustion at that recorded collection time.

Receipt enrichment observes pool creation and initial liquidity for all 1,831 launched tokens. Pool mappings and raw amounts are decoded from the TokenLaunched transaction receipts, including the corresponding pair creation and liquidity mint logs. Canonical uniqueness and referential integrity tests reject duplicate identifiers and require every liquidity pool identifier to exist in the pool table. The proxy implementation history is mapped by launch block, allowing each token to retain the observed implementation version. The SunPump official token API was collected at 2026 08 11 00:48:26 UTC using 50 row pages ordered by ascending ID. It stopped at 1,000 unique rows and has SHA256 `716a3a7076e0a3e8d9dde5c5117af74f2d97c6b5fdc19265f870d3f39424c138`. It contributes metadata only and does not define the universe.

### Phase 4 exclusions

`TokenPurchase`, `TokenSale`, `TokenPurchased`, `TokenSold`, ERC20 or TRC20 transfers, decoded trading, decoded swaps, and holder data are outside this phase. No canonical decoded trading, trade, holder, or holder balance table was generated. `token_state_snapshots` is empty for BNB Chain and TRON.

## Canonical schema and coverage semantics

The common crosschain release contains nine tables.

1. `tokens`
2. `launches`
3. `protocol_config`
4. `pools`
5. `liquidity_initializations`
6. `lifecycle_events`
7. `token_metadata`
8. `token_state_snapshots`
9. `coverage_ledger`

Coverage states are evidence claims rather than generic missing values.

1. `observed` means the field or event was directly observed within the declared source boundary.
2. `processed_zero_rows` means an applicable query completed with no qualifying record.
3. `not_collected` means the mechanism may apply but the field was not observed or acquired.
4. `not_applicable` means the mechanism does not apply to the currently represented protocol state. This includes both structural nonapplicability and snapshot state nonapplicability; downstream users should use the protocol and lifecycle fields to distinguish them.
5. `not_collected_by_policy` means acquisition was intentionally excluded.

For BNB Chain and TRON, a token without an observed lifecycle transition is marked `not_applicable` for pool and migration fields in its currently observed created state. This is a snapshot state, not evidence that the mechanism can never apply. `processed_zero_rows` is reserved for a completed entity targeted query that returned no qualifying record; it is not used to represent the absence of a later lifecycle transition from a finite event snapshot. Future snapshots may append later lifecycle observations.

## Accepted release results

| Chain and platform | Canonical universe and unit | Lifecycle or pool evidence | Metadata and auxiliary evidence | Declared boundary |
| --- | --- | --- | --- | --- |
| Solana Pump.fun and PumpSwap | 832,941 terminal token outcomes | 1,651 graduated tokens; 4,953 token by horizon transaction proxy rows | 1,651 graduated metadata rows; 173,102 delivered decoded swap rows for 294 tokens | Launch and terminal observation period 2026 05 08 through 2026 06 10 |
| Base Clanker | 62,618 launch records | 62,618 pools; 149,921 initial liquidity positions | No metadata enrichment in this release | 2025 08 18 through 2025 10 01 UTC |
| BNB Chain Four.meme | 1,593,679 launch records | 15,403 pools; 15,403 initial liquidity records | 999 metadata rows within the onchain universe | Deployment blocks through snapshot block 115,357,949 with 20 confirmations |
| TRON SunPump | 104,548 launch records | 1,831 pools; 1,831 initial liquidity records | 1,000 metadata rows within the onchain universe | Confirmed TronGrid fingerprint exhaustion at 2026 08 11 23:39:08 UTC |

The Solana denominator is a terminal outcome cohort while the other three denominators are launch records. These counts describe different protocol entities and declared boundaries. They are not directly comparable experiment samples without an explicit downstream design.

## Quality assurance and reproducibility

The release tests validate primary key uniqueness, foreign key integrity, common dimensions, manifest driven row counts, coverage states, API metadata subset rules, and the absence of excluded trading and holder tables. The test sources are `data_pipeline/tests/test_solana_release.py` and `data_pipeline/tests/test_crosschain_release.py`. The final suite result is 14 passed.

Every release manifest records source paths, source row counts, source SHA256 values, table row counts, table SHA256 values, and coverage summaries. `Claire/data_expansion/artifacts/phase4_integrity_summary.json` independently verifies manifest counts and hashes.

From the repository root, the accepted build and tests are reproduced with:

```text
data_pipeline/.venv/bin/python data_pipeline/scripts/build_solana_core.py
data_pipeline/.venv/bin/python data_pipeline/scripts/build_crosschain_core.py
data_pipeline/.venv/bin/pytest data_pipeline/tests
```

## Known boundaries and future extension

1. Shilin's decoded Solana swaps remain incomplete, page capped validation data.
2. Base is complete only inside its declared scan window, not for all historical Clanker deployments.
3. BNB Chain and TRON metadata are incomplete enrichment subsets.
4. Nontransitioned tokens may transition after the recorded snapshot.
5. No causal experiment or DiD result is part of these four phases.
6. Offchain event packs remain a later layer and should be collected only for events selected by an explicit experiment design.

The next research step can identify candidate events and build event specific offchain packs without changing the canonical chain universes. This preserves the intended separation between reusable foundational data and experiment specific derived data.
