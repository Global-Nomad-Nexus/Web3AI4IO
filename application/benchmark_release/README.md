# application Benchmark Release

This directory is application's release candidate for the Web3AI4IO benchmark after the August 7 revision plan. It only covers the Pump.fun / PumpSwap application arm and does not include identification's semi-synthetic suite.

## Primary Sheets

| Sheet | Role |
|---|---|
| `data/events.csv` | Rule-event and candidate-event registry for application's case, including Solana PumpSwap, accepted matched Clanker/Base, and rejected candidates. |
| `data/metrics_panel.csv` | Platform-day, token-horizon, and token-cohort metrics with fixed horizons and claim boundaries. |
| `data/covariates.csv` | Token social metadata plus Discord, sentiment, TVL, and RWA context rows. |

Every row carries `event_id` and a `claim_boundary` field so users can join across sheets without losing the evidence limit.

## Supplemental Sheets

| Sheet | Role |
|---|---|
| `data/claim_scope_ledger.csv` | Allowed and forbidden claims for H1, H4, mirror-case, and cross-chain extensions. |
| `data/data_gap_ledger.csv` | Machine-readable blockers such as full-cohort decoded USD outcomes and same-cohort early-wallet H4 evidence. |
| `data/mirror_case_candidates.csv` | application's current mirror-case scan. The Telegram heterogeneity case is a credible matched signal but not causal yet. |
| `data/mirror_case_ladder.csv` | A rung-by-rung Case B ladder for the Telegram/social metadata candidate. |
| `data/telegram_mirror_design.csv` | Matched-design, timing-gate, sensitivity, and selected token-horizon diagnostics for Telegram metadata. |
| `data/telegram_mirror_balance.csv` | Full and matched covariate balance diagnostics for the Telegram design. |
| `data/telegram_mirror_matched_cells.csv` | Matched launch-day and metadata cells supporting the Telegram design. |
| `data/cross_chain_event_candidates.csv` | Base, BNB, and TRON next-event candidates for cross-chain external validity. |
| `data/clanker_base_full_cohort_manifest.csv` | Matched Base token universe for archive/indexer expansion. |
| `data/clanker_base_full_cohort_pool_query_bounds.csv` | PoolManager Swap query bounds for every matched Base token row. |
| `data/clanker_base_full_cohort_transfer_query_bounds.csv` | ERC20 Transfer query bounds for full holder reconstruction. |
| `data/clanker_base_full_cohort_expected_horizons.csv` | Expected 1/7/30 day Base token-horizon rows after import. |
| `data/clanker_base_full_cohort_import_contract.csv` | Required swap/transfer import columns and consumer command. |
| `data/clanker_base_full_cohort_import_coverage.csv` | Resumable backfill coverage for PoolManager swaps and ERC20 transfers. |
| `data/clanker_base_causal_diagnostics.csv` | Matched-pair Base v4.1 versus v4.0 diagnostics for the currently covered sample. |
| `data/teacher_requirements_alignment_application.csv` | application-only audit against Luyao's revision requirements. |
| `data/agentic_evaluation_panel.csv` | L0-L7 agentic scores merged with deterministic ladder outputs and prompt hashes. |
| `data/data_dictionary.csv` | Core field definitions. |

## Release Documentation

| File | Role |
|---|---|
| `DATASET_CARD.md` | Intended uses, out-of-scope claims, sources, coverage, and limitations. |
| `SCHEMA_CONTRACT.md` | Required fields and claim-boundary invariants for primary sheets. |

## Current application Direction

The main PumpSwap case remains Case A: naive "yes" becomes trustworthy "uncertain" after controls, pretrend screening, few-cluster inference, and stakeholder boundaries.

The strongest mirror-case candidate is Telegram/social metadata. A market-only view sees an overall graduation rate of only about `0.198%`, but token-level stratification shows Telegram-linked tokens graduate at about `1.485%` versus `0.166%` without Telegram. The matched design supports 20,227 Telegram tokens, estimates a matched ATT of about `0.945` percentage points with CI `[0.738, 1.152]`, and records an E-value of `5.02`. It remains non-causal until an exogenous attention shock, comparable event, or stronger event-time design is available.

The cross-chain registry now accepts a matched Clanker/Base event: the first observed Clanker v4.1 MEV/sniper-protection TokenCreated log on Base at `2025-08-26T20:41:57Z`, transaction `0x5c076d1967b9f4873d36191321ccf015015b48687d0f176c6ad7091a84551985`. The bounded on-chain outcome run contains a 12-token, 36-row matched sample with Uniswap v4 PoolManager swap outcomes and ERC20 Transfer-log holder concentration. The expanded TokenCreated discovery scan covers `61,080` Clanker v4 launches and `6,940` v4.1 rows through `2025-10-01T03:22:27Z`. The release also includes a full-cohort archive/indexer manifest with `13,880` matched token rows and `41,640` expected 1/7/30 day horizon rows, plus a resumable backfill ledger. The current ledger contains `30` swap import rows and `100` transfer import rows after merging the accepted sample and smoke-tested units. This is accepted as event architecture and comparable-horizon evidence, not as platform-wide causal replication until the 30-day swap and transfer manifests are filled by archive/indexer data. Four.meme on BNB and SunPump on TRON are retained as discovery candidates.

## Rebuild

From `application/`:

```bash
python3 scripts/build_benchmark_release.py
python3 -m unittest discover -s tests
```

## Licensing

Code remains under the repository MIT license. Data tables in this release are intended for CC BY 4.0 release, subject to upstream dataset license compatibility documented in the source ledgers.
