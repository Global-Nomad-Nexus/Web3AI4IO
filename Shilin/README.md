# Shilin Replication Package: Pump.fun / PumpSwap Application Arm

This folder contains Shilin's code and artifacts for the paper:

*Trustworthy Causal Inference for Token Launch Platforms: An Interdisciplinary Approach of Platform Economics, Causal Econometrics, and AI Evaluation.*

The paper itself stays on Overleaf. This folder is for code, data interfaces, generated tables, figures, and agentic-evaluation scaffolds.

## Scope

Shilin owns the Pump.fun/PumpSwap application arm:

- Related work strand: empirical evidence on token platforms.
- H1: migration friction and post-graduation persistence.
- H4: allocation concentration and retail harm.
- Method Pillar 1: stakeholder metric battery.
- Method Pillar 2: data richness and frequency.
- Result 1: application-layer metrics, frequency analysis, and naive rerun.
- Agentic execution arm: prompts, run schema, scoring, and `tab_arms` agentic columns.

Claire's staggered cross-chain DiD design is not implemented here, except for compatible interfaces in the ladder.

## What This Code Does

The pipeline upgrades the earlier MVP into a benchmark-style replication package:

1. Runs a deterministic L0-L7 ablation ladder.
2. Computes Result 1 stakeholder metrics from RED-PUMP, market panels, Discord, and RWA extensions.
3. Performs daily-vs-weekly and market-vs-token frequency sensitivity checks.
4. Runs event-study pretrend diagnostics.
5. Adds a PyFixest `feols` DiD cross-check for the naive and unit/date fixed-effect specifications.
6. Adds a self-contained Pump.fun token risk snapshot using the HuggingFace `Pumpdotstudio/pump-fun-sentiment-100k` sample, deduplicated to one latest snapshot per mint.
7. Runs exact Rademacher wild-cluster bootstrap over the four protocol units.
8. Generates Overleaf-ready tables locally; the `.tex` outputs stay outside this GitHub package.
9. Runs L0-L7 agentic prompts with DeepSeek repeated runs and scores conclusion reliability.
10. Renders full 1,651-token Dune SQL for decoded indexer exports and computes a public-Solana-RPC validation sample.

## Run

The current local machine already has a working virtual environment in the upstream MVP folder. From the paper root:

```bash
/Users/oushilin/Desktop/SRS/01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local/.venv/bin/python Shilin/scripts/run_all.py
/Users/oushilin/Desktop/SRS/01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local/.venv/bin/python Shilin/scripts/run_agentic_deepseek.py --overwrite
/Users/oushilin/Desktop/SRS/01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local/.venv/bin/python Shilin/scripts/run_dune_token_exports.py --max-tokens 0
/Users/oushilin/Desktop/SRS/01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local/.venv/bin/python Shilin/scripts/run_solana_external_validation.py --max-tokens 300 --sample-strategy evenly_spaced --page-limit 20 --max-pages 1 --post-tx-limit-per-token 0 --early-tx-limit-per-token 0 --resume
/Users/oushilin/Desktop/SRS/01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local/.venv/bin/python Shilin/scripts/download_free_public_data.py --include all
/Users/oushilin/Desktop/SRS/01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local/.venv/bin/python Shilin/scripts/run_all.py
/Users/oushilin/Desktop/SRS/01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local/.venv/bin/python Shilin/scripts/check_artifacts.py
```

On a fresh machine:

```bash
cd Shilin
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/run_all.py
.venv/bin/python scripts/run_agentic_deepseek.py --env-file /path/to/local/.env --overwrite
.venv/bin/python scripts/run_dune_token_exports.py --max-tokens 0
.venv/bin/python scripts/run_solana_external_validation.py --max-tokens 300 --resume
.venv/bin/python scripts/download_free_public_data.py --include all
.venv/bin/python scripts/run_all.py
.venv/bin/python scripts/check_artifacts.py
```

If a Dune key becomes available, validate with a tiny sample before running larger exports:

```bash
export DUNE_API_KEY=...
.venv/bin/python scripts/run_dune_token_exports.py --max-tokens 1 --execute --only post_migration --performance medium
```

For a larger attempt, use chunking and a credit cap. Stop when Dune returns account/datapoint limits; do not keep retrying the same request.

```bash
.venv/bin/python scripts/run_dune_token_exports.py --max-tokens 0 --sample-strategy first --execute --only post_migration --performance medium --chunk-size 10 --max-total-credits 1700 --resume
```

If a Helius RPC key becomes available, set `HELIUS_API_KEY` or `SOLANA_RPC_URL` before running `scripts/run_solana_external_validation.py`; the script records only the provider class, not the secret.

Edit `configs/pumpswap_case.json` if the upstream MVP data root changes.

## Main Outputs

Tables:

- `artifacts/tables/deterministic_ladder.csv`
- `artifacts/tables/l0_window_sensitivity.csv`
- `artifacts/tables/event_study_coefficients_shilin.csv`
- `artifacts/tables/pretrend_diagnostics.json`
- `artifacts/tables/wild_cluster_bootstrap.json`
- `artifacts/tables/result1_frequency_sensitivity.csv`
- `artifacts/tables/result1_stakeholder_metric_battery.csv`
- `artifacts/tables/data_availability_ledger.csv`
- `artifacts/tables/claim_scope_ledger.csv`
- `artifacts/tables/hf_pump_risk_snapshot_summary.json`
- `artifacts/tables/external_validation_summary.json`
- `artifacts/tables/dune_indexer_export_summary.json`
- `artifacts/tables/free_public_data_inventory.csv`
- `artifacts/tables/free_public_data_summary.json`
- `artifacts/tables/free_public_data_download_summary.json`
- `artifacts/tables/pyfixest_did_crosscheck.csv`
- `artifacts/tables/agentic_prompt_manifest.csv`
- `artifacts/tables/agentic_arm_scores.csv`
- `artifacts/tables/paper_readiness_audit.csv`
- `artifacts/tables/paper_readiness_summary.json`
- `artifacts/tables/radar_evidence_profiles.csv`

Figures:

- `artifacts/figures/fig_parallel_trends_shilin.png`
- `artifacts/figures/fig_event_study_shilin.png`
- `artifacts/figures/fig_ablation_ladder_shilin.png`
- `artifacts/figures/fig_frequency_sensitivity_shilin.png`
- `artifacts/figures/fig_metric_battery_status_shilin.png`
- `artifacts/figures/fig_external_validation_rpc_shilin.png`
- `artifacts/figures/fig_readiness_radar_shilin.png`
- `artifacts/figures/fig_readiness_status_bar_shilin.png`
- `artifacts/figures/fig_market_protocol_volume_lines_shilin.png`
- `artifacts/figures/fig_agentic_method_omission_bar_shilin.png`
- `artifacts/figures/fig_agentic_calibration_gap_bar_shilin.png`

Overleaf-ready `.tex` tables are intentionally not committed here. Regenerate them locally with `scripts/run_all.py` when updating the paper.

External validation artifacts:

- `artifacts/external_validation/pumpfun_coin_metadata.csv`
- `artifacts/external_validation/solana_post_migration_pool_windows.csv`
- `artifacts/external_validation/solana_early_wallet_concentration.csv`
- `artifacts/external_validation/solana_parsed_transaction_proxies.csv`
- `artifacts/external_validation/dune_graduated_tokens.csv`
- `artifacts/external_validation/dune_sql/rendered_pumpswap_post_migration_trades.sql`
- `artifacts/external_validation/dune_sql/rendered_pumpswap_early_wallets.sql`

The current generated external-validation artifact is a Helius-backed RPC run over all 1,651 graduated RED-PUMP tokens. It has 1,651/1,651 Pump.fun metadata matches, 1,651/1,651 pool addresses, and 4,953 token-horizon post-migration rows. In the 30-day horizon, 762 tokens have complete signature windows, the complete-window active share is 100.0%, and the median complete-window transaction-count proxy is 826. Across the full 1,651-token cohort, 1,636 tokens have at least one observed 30-day pool transaction, giving a conservative observed lower-bound active share of 99.09%. These counts remain RPC signature-level proxies: 889 30-day windows are still pagination-truncated, and decoded USD volume, active trader counts, trade direction, and early-wallet concentration require a decoded indexer. The rendered Dune SQL covers all 1,651 graduated tokens. Dune API execution was tested successfully on tiny samples, but the account-level datapoint limit stopped the full post-migration export before a usable full Dune CSV was downloaded.

## Free Public Data Extension

To reduce dependence on paid indexer APIs, `scripts/download_free_public_data.py` downloads and verifies no-key public data under `data_sources/free_public/`. The current local run registers 27 files and 112.7 MiB of public assets:

- SolArchive / HuggingFace mirror: Solana-wide token metadata partitions and schemas, including local token snapshot parquet files for `2025-03` and `2025-12`. The HuggingFace token index covers 63 monthly token partitions from `2020-10` through `2025-12`. The HuggingFace transaction index currently ends at `2022-04-30`, so it is useful for archive infrastructure and schema planning but not yet a free substitute for 2025 PumpSwap post-migration swap windows.
- RED-COHORT-2026-v1 from Zenodo: a valid local ZIP plus extracted files for 1,012 persistent Pump.fun sniper cohorts and 20,163 intra-launch first-buyer-window observations. This is the strongest free extension for H4, because it directly targets early-wallet concentration and persistent cohort behavior.
- HuggingFace `pump-fun-meme-token-dataset`: a 106,113-row CSV covering 98,175 unique Pump.fun mint addresses with launch metadata, creator, social links, timestamps, market-cap fields, and Raydium pool fields. It extends the launch-universe and social-metadata coverage, but is not treated as a main causal outcome.

These free assets strengthen the data-coverage and H4 validation layers, and their file sizes and SHA256 hashes are recorded in `artifacts/tables/free_public_data_inventory.csv`. They do not replace decoded token-level PumpSwap `1/7/30d` USD trade outcomes from Dune or another full Solana indexer; that boundary is intentionally preserved in the claim ledger.

## Current Findings

The current deterministic ladder produces the conclusion-flip pattern required by the paper's benchmark framing:

- L0 before-after means conclude that PumpSwap "worked": Pump ecosystem log volume increases by about `0.669` log points.
- L1/L2 add controls and fixed effects; the estimate is about `0.412` log points but the confidence interval includes zero.
- L4 flags pretrend risk, so the dynamic market-level event-study should not be read as clean causal evidence.
- L6 exact wild-cluster inference over four protocol units widens uncertainty substantially and yields a non-significant result.
- L5 audits the H4 proxy layer with real latest-token-snapshot holder concentration and source-coded risk fields from the HuggingFace Pump.fun sentiment/risk sample.
- L7 reframes the conclusion as stakeholder-dependent rather than simply yes/no.

Result 1 currently computes RED-PUMP token-level graduation, timeout, time-to-graduation, social-metadata heterogeneity, Pump.fun holder-concentration/risk proxies, token market-activity proxies, a RED-COHORT early-wallet/sniper-cohort validation metric, Discord extension, and RWA extension. The HF token snapshot is deduplicated to the latest record per mint before token-level summaries are computed. The no-key RED-COHORT download adds 1,012 persistent sniper cohorts, 2,965 unique cohort wallets, 5,411 strict cohort-touched mints, 153 high-tier cohorts, and median first-buyer rank 3.55 to the H4 mechanism battery. The RED-COHORT/RED-PUMP overlap audit records 0 overlapping mints in the current windows, so RED-COHORT is treated as external H4 mechanism validation, not as a joined causal outcome sample. The package now also includes a generated H1 RPC mechanism-causal audit: the all-token observed 30-day activity lower bound is 99.09% (Wilson 95% CI [98.51%, 99.45%]), the complete-window active share is 100.0% (Wilson 95% CI [99.50%, 100.0%]), the complete-window median transaction-count proxy is 826 (bootstrap 95% CI [730.0, 941.0]), and there are zero temporal-order violations. This supports the bounded claim that PumpSwap operated as a post-migration liquidity venue for graduated tokens. Dune or another decoded indexer remains necessary before reporting USD-volume, active-trader, price-quality, welfare, or same-cohort early-wallet H4 causal effects.

## Claim Boundary and External Validation

The current code is self-contained for the Shilin application claim. It supports:

- A market-level benchmark showing how naive and trustworthy pipelines diverge.
- A token-level H1 proxy using real market-activity, liquidity, and bonding-progress latest snapshots.
- A Helius/Solana RPC H1 mechanism audit showing post-migration pool activation and persistence for the 1,651-token graduated cohort.
- A token-level H4 proxy using real top-holder concentration, holder-concentration labels, and high/critical source-coded risk labels.
- A claim-scope ledger that states what the evidence allows and forbids.

The next version can strengthen mechanism timing through executed Dune/Solana indexer exports:

- H1 event-time validation: token-level post-migration `1/7/30d` decoded swap count, active trader count, USD volume, inactivity, and reactivation for all 1,651 graduated tokens.
- H4 event-time validation: early-wallet concentration and sniper proxies from decoded first-window trades rather than public-RPC lower bounds.
- Indexer execution: `scripts/run_dune_token_exports.py --execute` once `DUNE_API_KEY` is available, or `scripts/run_solana_external_validation.py --resume --max-tokens 0` with a high-throughput Helius/Solana RPC endpoint.

SQL templates are provided in `data_sources/dune_queries/`, and full rendered SQL files are generated under `artifacts/external_validation/dune_sql/`. They remain the path to decoded Dune `dex_solana.trades` USD-volume validation; the current included validation sample uses Pump.fun metadata and public Solana RPC.

## Academic-Standard Design Choices

- All outputs are generated by `scripts/run_all.py`; manual copy-paste numbers are avoided.
- The config file is hashed and recorded in `artifacts/run_manifest.json`.
- Each ladder rung uses a common schema.
- PyFixest is used as the package-level DiD cross-check for the naive and TWFE market specifications.
- The data-availability ledger separates computed metrics from required new exports.
- The claim-scope ledger prevents overclaiming from proxies.
- The readiness audit records which evidence components are pass, warning, or gap before submission-level claims are made.
- The figure set includes multiple academic plot types: event-study and parallel-trends lines, a four-protocol market-trajectory line chart, robustness/error-bar plots, a multi-profile radar comparing the actual L0/L2/L6 pipeline rungs, readiness bars, separate agentic-evaluation bars, and Solana RPC validation summaries.
- Agentic prompts are versioned and hashed before model runs are reported; raw DeepSeek responses are saved without API keys.
- Dune/indexer values are not imputed or simulated; their role is external validation.

## Overleaf Boundary

The paper source and generated `.tex` tables stay in Overleaf/local working folders, not in this repository. This package keeps the code, data interfaces, generated non-LaTeX artifacts, and figures needed to reproduce Shilin's application arm.
