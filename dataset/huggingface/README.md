---
pretty_name: Web3AI4IO Multi Chain Launchpad Dataset
license: cc-by-4.0
task_categories:
  - tabular-classification
  - time-series-forecasting
language:
  - en
tags:
  - web3
  - blockchain
  - solana
  - base
  - bnb-chain
  - tron
  - launchpads
---

# Web3AI4IO Multi Chain Launchpad Dataset

## Dataset summary

This dataset provides an extensible, provenance aware launchpad data foundation across Solana Pump.fun and PumpSwap, Base Clanker, BNB Chain Four.meme, and TRON SunPump.

The release separates chain source data, versioned canonical tables, schemas, release manifests, and explicit coverage ledgers. It is designed as reusable research infrastructure rather than as the input to one specific causal experiment.

## Included scope

1. Solana canonical token outcomes and lifecycle data reconstructed from the accepted RED PUMP source cohort.
2. Base Clanker launch, protocol configuration, Uniswap v4 pool initialization, and initial liquidity data for the declared 2025 08 18 through 2025 10 01 UTC window.
3. BNB Chain Four.meme TokenManager launch and lifecycle data through snapshot block 115,357,949 with 20 confirmations.
4. TRON SunPump confirmed contract events scanned through TronGrid fingerprint exhaustion at 2026 08 11 23:39:08 UTC.
5. Common schemas, coverage ledgers, release manifests, and SHA256 evidence.

## Excluded scope

This release does not add offchain event packs, Discord or Telegram message data, TVL panels, RWA data, experiment specific panels, or causal estimation outputs.

Official platform API metadata and canonical `token_metadata` tables are not included in this first onchain release. Their documented local use does not expand the Hugging Face publication scope.

Decoded trading and holder data are not collected for Base, BNB Chain, or TRON. The delivered Solana decoded swap snapshot is preserved as page capped validation data and must not be treated as complete coverage.

## Canonical tables

The project-level event layer adds `event_registry` and `event_evidence`, together with a flat `events.csv` export. These tables distinguish accepted, conditional, and rejected rule-event candidates. Canonical chain coverage does not by itself make a chain eligible for event-aligned inference.

Crosschain releases use the following common tables where applicable:

1. `tokens`
2. `launches`
3. `protocol_config`
4. `pools`
5. `liquidity_initializations`
6. `lifecycle_events`
7. `token_metadata`
8. `token_state_snapshots`
9. `coverage_ledger`

The Solana release also preserves bounded pool transaction proxy windows and the delivered decoded swap validation snapshot.

## Coverage semantics

1. `observed` means directly observed inside the declared source boundary.
2. `processed_zero_rows` means an applicable targeted query completed with no qualifying row.
3. `not_collected` means the mechanism may apply but was not observed or acquired.
4. `not_applicable` means the mechanism does not apply to the currently represented protocol state.
5. `not_collected_by_policy` means acquisition was intentionally excluded.

Users should consult `coverage_ledger` before analysis.

## Release counts

1. Solana contains 832,941 terminal token outcomes, including 1,651 graduated tokens.
2. Base contains 62,618 Clanker launches and pools.
3. BNB Chain contains 1,593,679 Four.meme launches and 15,403 observed pool and initial liquidity records.
4. TRON contains 104,548 SunPump launches and 1,831 observed pool and initial liquidity records.

These denominators represent different protocol entities and source boundaries and are not directly comparable experiment samples.

## Reproducibility

The companion Git repository contains builders, schemas, source registries, release manifests, acceptance records, and tests. Every published file is listed in the release manifest with its size and SHA256 digest.

The final local validation suite passed 14 tests covering identity uniqueness, foreign keys, row counts, source roles, coverage states, and excluded table checks.

## License and citation

This dataset is released under the Creative Commons Attribution 4.0 International license (`CC BY 4.0`). Citation metadata will be added when the associated paper has a stable public identifier.
