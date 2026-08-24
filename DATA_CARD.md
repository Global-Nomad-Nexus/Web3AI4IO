# Data card

## Scope

Web3AI4IO v1 is a provenance-aware launchpad dataset covering Pump.fun and PumpSwap on Solana, Clanker on Base, Four.meme on BNB Chain, and SunPump on TRON.

The release separates immutable inputs, canonical tables, and deterministic builders. Nine common tables are used where applicable, plus an event registry and event-evidence table.

During anonymous review the bulk dataset is a withheld review artifact, not for distribution. After acceptance the public copy is the Hugging Face dataset named in the camera-ready version.

## Provenance

| Chain | Source | Membership rule | Window |
|---|---|---|---|
| Solana | RED PUMP terminal outcomes and launches | Deduplicated terminal outcomes | 2026-05-08 to 2026-06-10 UTC |
| Base | Clanker TokenCreated events plus PoolManager core | Declared scan window | 2025-08-18 to 2025-10-01 UTC |
| BNB Chain | Four.meme manager `TokenCreate` events | Verified manager-deployment and snapshot block coverage | Snapshot 2026-08-12; block 40,138,454 to 115,357,949 |
| TRON | SunPump TronGrid contract events | Confirmed fingerprint pagination to exhaustion | 2024-08-09 to 2026-08-11 UTC |

Builders, schemas, and SHA-256 digests are in `dataset/`. The event layer is `dataset/events/v1/` and `dataset/releases/v1/events_core.json`.

## Coverage states

- `observed`: directly observed inside the declared source boundary
- `processed_zero_rows`: an applicable query completed with no qualifying row
- `not_collected`: the mechanism may apply but was not acquired
- `not_applicable`: the mechanism does not apply
- `not_collected_by_policy`: acquisition was intentionally excluded

Missingness is interpreted relative to the acquisition process and the claim under study. An unobserved transition at a finite snapshot is not recoded as a structural zero.

## Counts in the current snapshot

- Solana: 832,941 terminal outcomes, 1,651 graduations, 831,290 timeouts
- Base: 62,618 launches and pools
- BNB Chain: 1,593,679 launches, 15,403 observed pools
- TRON: 104,548 launches, 1,831 observed pools
- Events: 4 candidates, 6 evidence records (1 accepted, 1 conditional, 2 rejected)

These denominators are different protocol entities. They are not pooled causal samples.

## Lifecycle definitions

Solana terminal state is graduation or timeout in the RED PUMP cohort. Base bonding-curve graduation is `not_applicable` for the represented Uniswap v4 launch mechanism. BNB and TRON pool counts are observed `LiquidityAdded` / `TokenLaunched` events, not complete terminal-outcome cohorts.

## Missingness and exclusions

Official API metadata snapshots are 1,000-row enrichment subsets and never define a universe. Decoded Solana swaps cover 294 of 1,651 graduated tokens and are page-capped validation data. Decoded trading, holder, and swap layers are not collected for Base, BNB Chain, or TRON. Offchain message dumps, Discord, and TVL panels are outside the release.

BNB canonical `launch_at` contains invalid zero timestamps and values inconsistent with the snapshot. Membership uses verified block coverage. Records with invalid timestamps are excluded from temporal analysis.

## Event eligibility versus chain coverage

Canonical launch data do not make a chain eligible for causal alignment. The v1 event layer registers PumpSwap migration as a conditional Solana boundary, Clanker v4.1 first-observed module adoption as an accepted Base reconstruction, and BNB and TRON as rejected event candidates. The creator-fee analysis is a separate application with verified activation and no accepted platform control.

## Licenses and ethics

Released tables use CC BY 4.0. Onchain public data contain no offchain personal identifiers in the canonical tables. Do not attempt to deanonymize wallet holders. The anonymous manuscript must not distribute the bulk dataset or author-identifying repository links.

## Limitations

The release is a construction and coverage artifact. It does not identify aggregate welfare, pooled cross-chain treatment effects, or complete decoded trading histories.
