# identification Data Expansion

This directory tracks the data expansion requested after the 4 August revision.
It does not run Difference in Differences or any other causal estimator.

## Expansion objective

1. Preserve application's decoded Solana outcomes as validation data only. Do not continue decoded swap collection.
2. Defer offchain activity collection until experiment events are identified.
3. Complete the applicable Base Clanker canonical core without collecting swap, transfer, holder, or trading outcomes.
4. Record provenance, licensing, hashes, selection, missingness, and coverage before any experiment is designed.

## Later chain expansion

Four.meme on BNB Chain now has a complete archive RPC `TokenCreate` universe through the recorded snapshot block: 1,593,679 unique launches, including 5,570 V1 and 1,588,109 V2 events. The collected lifecycle sources contain 106 `TradeStop` and 15,403 `LiquidityAdded` events.

SunPump on TRON now has a TronGrid contract event universe scanned through fingerprint exhaustion: 104,548 `TokenCreate`, 1,831 `TokenLaunched`, and one `NewImplementation` event.

Each official API contributes a 1,000 row metadata enrichment subset only. It does not determine launch membership or chain level denominators. Receipt enrichment and the Phase 4 canonical build are complete and accepted for declared core events. Decoded trading, holder, and swap data are excluded.

## Storage policy

Large raw responses and resumable caches live under `raw/` and `cache/` and are ignored by Git. The repository stores acquisition code, query definitions, source manifests, hashes, compact processed tables, and coverage reports.

Credentialed or paid bulk collection must not start until a feasibility and cost report has been reviewed. Public and no key endpoints may be used for bounded probes and reproducible acquisition.

## Current state

The verified application bundle is stored under `data/external/application/20260810/bundle`. The reproducible Solana canonical release is generated under `data/canonical/v1/solana`. Versioned code, schemas, source definitions, and the compact release manifest live under `data_pipeline/`.

The raw RED PUMP baseline and graduated metadata are complete for the delivered cohort. The bundle contains 173,102 decoded rows for 294 of 1,651 graduated tokens, and most delivered windows reached a page limit. These rows are retained as validation data only. `coverage_ledger` records this explicitly, and no additional decoded Solana swap collection is planned.

The Base canonical core fixes the 62,618 launch universe and adds complete observed creator, protocol configuration, pool mapping, pool initialization, and positive initial liquidity coverage. Bonding curve graduation and migration are not applicable to this direct Uniswap v4 launch mechanism. Decoded swaps, holder data, and trading outcomes are excluded by policy.

Run the coverage audit from the repository root:

```text
python3 identification/data_expansion/scripts/audit_coverage.py
```

The script writes `identification/data_expansion/artifacts/coverage_audit.csv` and `coverage_audit.json`.

Required units, keys, completeness, and missingness states are in `SCHEMA_CONTRACT.md`. Solana canonical tables can be reproduced with `data_pipeline/scripts/build_solana_core.py`. Base, BNB Chain, and TRON canonical tables can be reproduced with `data_pipeline/scripts/build_crosschain_core.py`.
