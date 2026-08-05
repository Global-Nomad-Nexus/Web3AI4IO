# Shilin August 7 Revision Plan

This note records the Shilin-only revision path after the latest teacher feedback. It is scoped to the Pump.fun / PumpSwap application arm.

## What Is Complete as of August 4, 2026

1. Built a Shilin-only benchmark release under `benchmark_release/`.
2. Generated the three primary sheets requested for a reusable benchmark:
   - `events.csv`
   - `metrics_panel.csv`
   - `covariates.csv`
3. Added supplemental ledgers for:
   - claim scope
   - data gaps
   - mirror-case candidates
   - cross-chain candidates
   - agentic evaluation scores
4. Added `DATA_LICENSE.md` for CC BY 4.0 data-release intent and `CITATION.cff` for citation metadata.
5. Added tests so the release keeps claim boundaries and remains Shilin-only.
6. Re-ran the Telegram mirror and public-shock designs:
   - `scripts/run_telegram_mirror_design.py --bootstrap-reps 500 --seed 20260729`
   - `scripts/run_telegram_exposure_design.py --refresh-public-candidates`
7. Re-ran the accepted Clanker/Base bounded validation through the import-compatible path:
   - `scripts/run_clanker_base_validation.py --reuse-token-created --selection-mode full-window --tokens-per-side 0 --start-block 34350000 --end-block 35200000 --swap-import artifacts/external_validation/clanker_base_pool_swaps_raw.csv --transfer-import artifacts/external_validation/clanker_base_token_transfers_raw.csv`
8. Rebuilt the Clanker/Base full-cohort archive/indexer manifest and partial coverage ledger:
   - `scripts/prepare_clanker_base_full_cohort.py --token-created artifacts/external_validation/clanker_base_token_created.csv --selection-mode full-window --tokens-per-side 0`
   - `scripts/backfill_clanker_base_full_cohort_logs.py --collect none --merge-existing-raw-sample`
9. Re-ran Base matched-pair diagnostics, rebuilt the benchmark release, and passed all Shilin tests:
   - `scripts/run_clanker_base_causal_diagnostics.py`
   - `scripts/build_benchmark_release.py`
   - `scripts/check_artifacts.py`
   - `python3 -m unittest discover -s tests -v`

## Top-Conference Direction

The paper should stop reading as a single crypto case study and start reading as a reusable evidence-quality benchmark. Shilin's part should make three points.

First, the PumpSwap case is Case A: naive "yes" becomes trustworthy "uncertain." This is valuable because the ladder changes a decision, not only a standard error.

Second, the mirror case should come from token-level heterogeneity rather than another aggregate market-volume result. The best current candidate is Telegram/social metadata. Overall RED-PUMP graduation is only about `0.198%`, which looks close to a null quality result. Telegram-linked tokens graduate at about `1.485%`, compared with `0.166%` without Telegram. The matched design now supports `20,227` Telegram tokens and estimates a matched ATT of about `0.945` percentage points with a launch-day cluster bootstrap CI of roughly `[0.738, 1.152]` percentage points. The timing audit keeps the claim boundary strict: this is a credible predictive/mechanism-supported mirror signal, not a causal Telegram effect without exogenous exposure timing.

Third, cross-chain generalizability is no longer only a candidate registry. Clanker on Base now passes Shilin's bounded activation and comparison gates as `CLANKER_SNIPER_DECAY_V41_BASE_20250826`: the first observed v4.1 MEV/sniper-protection token launch is verified at `2025-08-26T20:41:57Z` in transaction `0x5c076d1967b9f4873d36191321ccf015015b48687d0f176c6ad7091a84551985`, with a 12-token matched sample and 36 fixed-horizon rows. The full-cohort path is registered but not complete: it enumerates `13,880` matched token rows and `41,640` expected 1/7/30 day rows, but platform-wide Base causal replication still requires archive/indexer swap and transfer coverage. Four.meme on BNB and SunPump on TRON remain discovery backups.

## Status Against Concrete Modifications

1. Extend `metrics_panel.csv` with full-cohort decoded token outcomes:
   - `volume_usd`
   - `active_traders`
   - `buy_count`
   - `sell_count`
   - `first_trade_at`
   - `last_trade_at`
   - `holder_concentration_top10`
   - Status: schema and covered-sample rows are complete. Solana full-cohort decoded USD/trader outcomes remain blocked by Dune datapoint limits or equivalent indexer credentials. Base full-cohort manifests are complete, but only bounded/imported rows are decoded today.

2. Turn the Telegram mirror candidate into a real ladder case:
   - join token social covariates to 1/7/30 day decoded outcomes;
   - define treated or high-attention cohorts before looking at effects;
   - compare naive overall graduation, social-stratified graduation, and controlled token-horizon estimates;
   - keep the claim as mechanism or association if project-quality confounding remains.
   - Status: completed as a credible matched mirror signal with timing and sensitivity diagnostics. It is intentionally not labeled causal because the public-shock scan found `0` supported in-window shocks.

3. Validate one Base candidate:
   - verify Clanker rule activation or default adoption from first-party release plus on-chain contract/factory calls;
   - build token launch cohorts before and after activation;
   - compute early-wallet concentration and 7/30 day persistence;
   - mark the event accepted only if activation, comparison, and outcome gates pass.
   - Status: completed for a bounded matched Base sample. The event is accepted as on-chain cross-chain evidence, while full-cohort causal replication remains a registered gap.

4. Surface agentic evaluation in the manuscript:
   - add one abstract sentence on the principal agentic finding;
   - place a per-rung agent decision-path figure near the evidence ladder;
   - explain that the evaluated object is the agent's evidence behavior;
   - report which scaffold requirements reduce unsupported L0 conclusions.
   - Status: release panel exists for single-model L0-L7 evidence-behavior scoring. Top-conference extension should add multi-model reruns and scaffold ablations, but Shilin's current package already includes the agentic panel and manuscript-ready wording.

5. Keep societal-impact framing concrete:
   - retail-user protection in permissionless token markets;
   - risks of overstating welfare effects;
   - SDG 8 and SDG 10;
   - open benchmark data as a public good for researchers and regulators;
   - negative and welfare-unidentified outputs as valid benchmark outcomes.
   - Status: added to `SHILIN-REPORT.md` and tracked in `teacher_requirements_alignment_shilin.csv`; joint paper text still needs synchronization.

## Current Blockers

1. Dune full-indexer export is still blocked by account datapoint limits.
2. Moralis decoded sample is credible but selected toward high-activity tokens.
3. RED-COHORT currently has zero mint overlap with RED-PUMP outcomes, so H4 remains external mechanism validation.
4. Telegram/social metadata is a strong mirror case but not yet a causal mirror case because the public-shock scan found no supported in-window exogenous exposure event.
5. Clanker/Base has passed bounded activation/comparison gates, but full 30-day platform-wide causal replication needs archive/indexer exports or a credentialed archive RPC endpoint. A live public Base endpoint retry on August 4, 2026 failed on historical `eth_getLogs` with an archive-token requirement, so the accepted sample was rerun through the import-compatible raw-log path.
