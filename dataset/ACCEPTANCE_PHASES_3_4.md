# Acceptance Record for Phases 3 and 4

## Decision

Phase 3 is complete for all applicable canonical core fields in the declared Base Clanker scan window. Phase 4 is complete for the current Four.meme and SunPump contracts, including onchain launch universes, receipt enrichment, canonical table generation, coverage validation, and acceptance tests.

## Phase 3 Base Clanker

1. Source is the Base public JSON RPC `TokenCreated` event scan.
2. Coverage is 2025 08 18 00:00:00 through 2025 10 01 23:59:59 UTC.
3. The fixed universe contains 62,618 unique tokens and 62,618 launch records. Launches were not recollected.
4. Creator, message sender, protocol version, hook, MEV module, locker, paired token, starting tick, and extension supply are retained as observed protocol configuration.
5. Every launch maps to one unique Uniswap v4 `pool_id`. A v4 pool ID is not a contract address, so `pool_address` remains null.
6. Every pool has exactly one observed PoolManager Initialize event in its original launch transaction.
7. Every pool has at least one observed positive ModifyLiquidity event in its original launch transaction.
8. The release contains 62,618 pool initialization rows and 149,921 positive initial liquidity position rows.
9. Another 6,764 zero delta ModifyLiquidity events are retained as `liquidity_position_poked`, following the PoolManager definition of a zero delta call as a poke.
10. The lifecycle table contains 281,921 observed events: token creation, pool initialization, initial liquidity addition, and liquidity position pokes.
11. Bonding curve graduation and migration are `not_applicable` because these Clanker v4 tokens launch directly into Uniswap v4 pools.
12. Decoded swaps, holder data, and trading outcomes are `not_collected_by_policy`.
13. Empty metadata and state snapshot tables preserve the common schema without inventing unavailable observations.

## Phase 4 BNB Chain and TRON

1. Four.meme launch acquisition uses BNB Chain archive RPC `TokenCreate` events rather than the official list API.
2. The Four.meme universe contains 1,593,679 unique launches: 5,570 V1 and 1,588,109 V2.
3. Directly observed Four.meme lifecycle sources contain 106 `TradeStop` and 15,403 `LiquidityAdded` events.
4. SunPump launch acquisition uses TronGrid contract events with fingerprint pagination continued until the fingerprint is absent.
5. The SunPump source contains 104,548 `TokenCreate`, 1,831 `TokenLaunched`, and one `NewImplementation` event.
6. The Four.meme and SunPump official API snapshots each contain 1,000 records and are metadata enrichment subsets only.
7. Official API rows do not define launch membership or chain level denominators.
8. Receipt enrichment and common canonical table generation are complete. BNB contains 15,403 observed pool mappings, pool initializations, and initial liquidity records. TRON contains 1,831 of each.
9. Token purchase, sale, transfer, decoded trading, holder, and swap data are not collected.
10. All 14 release tests pass, including uniqueness, foreign keys, coverage states, metadata subset semantics, and excluded table checks.

## Coverage state semantics

1. `observed` means the applicable field or event was directly observed in the declared source scope.
2. `processed_zero_rows` means an applicable query completed with no qualifying record.
3. `not_collected` means the mechanism may apply but acquisition is incomplete.
4. `not_applicable` means the protocol does not have that mechanism.
5. `not_collected_by_policy` means the field is intentionally excluded.

No Base field that was merely uncollected is represented as nonexistent.

## Phase 4 acquisition finding

The 1,000 row limits apply only to the official metadata APIs. They were bypassed for launch membership by scanning Four.meme `TokenCreate` events through a BNB Chain archive RPC and SunPump contract events through TronGrid fingerprint pagination. The official APIs remain useful only for metadata enrichment. Onchain receipt enrichment and canonical mapping are complete, and all 14 release tests pass.

## Reproducibility

Run:

```text
dataset/.venv/bin/python dataset/scripts/build_crosschain_core.py
dataset/.venv/bin/pytest dataset/tests
```

Release manifests record source row counts, source SHA256 digests, output row counts, and output SHA256 digests.

## Acceptance boundary

The four chain architecture covers Solana, Base, BNB Chain, and TRON. Base canonical core is complete inside its declared launch window. BNB Chain and TRON have accepted canonical core releases independent of their capped metadata APIs. Offchain event packs remain a later phase and should be collected only for identified experiment events.
