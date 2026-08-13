# Phase 1 and Phase 2 Acceptance

## Acceptance boundary

This release integrates the Shilin reproducibility bundle as the immutable baseline and builds the Solana Pump.fun and PumpSwap canonical core. It does not run DiD experiments and does not begin the Base expansion.

## Required tables

1. `tokens`: canonical token identity and creation metadata.
2. `launches`: launch observations and source level social indicators.
3. `lifecycle_events`: cleaned graduated or timeout terminal events.
4. `token_metadata`: metadata for the graduated cohort.
5. `pool_windows`: bounded Solana RPC pool transaction proxy windows.
6. `decoded_swaps`: delivered Moralis decoded swap rows.
7. `token_horizons`: delivered decoded horizon aggregates.
8. `coverage_ledger`: one row per graduated token with explicit coverage state.

## Mandatory quality gates

1. The raw RED PUMP cleaning must reproduce exactly 832,941 token outcomes and 1,651 graduated tokens.
2. Primary identifiers must be unique in all entity level tables.
3. All tables must use one canonical Solana chain identifier and stable token identifiers.
4. The 1, 7, and 30 day RPC rows must be labelled as transaction proxies, not decoded swaps.
5. Page capped Moralis windows must remain lower bounds and must not be labelled complete.
6. Every generated table and every source input must have a SHA256 digest in the release quality report.

## Known coverage boundary

The Shilin bundle contains decoded Moralis swaps for 294 of 1,651 graduated tokens. Most delivered windows reached the configured page limit. Therefore the canonical dataset preserves these rows as lower bound observations and validation data only. The project accepts this limitation and will not collect additional decoded Solana swaps. See `SHILIN_LIMITATION.md`.

## Observed release result

1. Raw outcome rows: 833,171.
2. Canonical token outcomes: 832,941.
3. Graduated tokens: 1,651.
4. Timeout tokens: 831,290.
5. Graduated token metadata rows: 1,651.
6. Pool proxy window rows: 4,953.
7. Delivered decoded swap rows: 173,102 across 294 tokens.
8. Delivered decoded horizon rows: 882.
9. Baseline identity and outcome mismatches against Shilin processed data: zero across 832,941 rows.
10. Automated tests: 4 passed.

Exact table digests are stored in `data_pipeline/releases/v1/solana_core.json`.
