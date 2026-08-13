# Claire study handoff

This folder is Claire's independent contribution. It does not use the abandoned MVP as a baseline, data source, event source, result source, or prior.

## Current conclusion

Pump.fun creator fees became economically active at 2025-05-13 11:27:06 UTC. The event is verified by finalized Solana records and a positive creator-vault transfer in the next block. The May 12 support upgrade is rejected as activation because a verified trade transferred zero lamports to its creator vault.

H0 asks whether the rule bundle increases gross market thickness more than quality-adjusted thickness. LaunchLab is rejected because it began operating too close to treatment. Moonshot supplies an exact diagnostic comparison but fails the causal control gate because of concurrent product changes and competitor interference. The diagnostic panel therefore does not identify a causal H0 effect. The seven-day launch-minus-migration contrast is 0.182 log points with 95 percent interval from -0.174 to 0.539, so the registered joint H0 criterion is not met. An eight-date in-time placebo gives a two-sided randomization p value of 0.111 for the short-window Pump launch break.

H3 is partially identified at the mechanism level. Verified trades show positive gross transfers to creator vaults after activation. Trader net welfare and platform incidence remain unidentified. The estimand is the reduced-form creator-fee rule bundle, not an isolated creator subsidy.

## Data and code

The accepted extract is `data/pump_moonshot_cohort_panel.csv`, produced by `queries/03_pump_moonshot_cohort_panel.sql`. Pump migrations use raw instruction discriminator `0x9beae792ec9ea21e` because the decoded migrate table is incomplete. Analysis outputs are in `artifacts/`.

From this folder, run:

```text
PYTHONPATH=src python3 -m web3io_claire.analyze_h0
PYTHONPATH=src python3 -m web3io_claire.analyze_h3
PYTHONPATH=src python3 -m web3io_claire.crosscheck_ladder
PYTHONPATH=src python3 -m unittest discover -s tests
```

`k3_subagent_audit.py` is optional and external. It reads `KIMI_CODING_PLAN` from the environment first, with a local API file available only for the original workstation. It requests exact model `k3-256k`, sets high reasoning, and has no model fallback. Its completed output is `artifacts/k3_subagent_audit.json`.

## Paper handoff

The clean standalone contribution is `manuscript/claire_contribution.tex` and compiles independently with the shared bibliography. The same verified content is now integrated into the active shared manuscript `manuscript/neurips_2026.tex`. It contains the related-work strand, H0, H3, Method Pillar 3, the independent benchmark design, Result 2, sequential-event handling, the naive rerun, and the rule-event L0 through L7 ladder.

The deterministic decision cells in `manuscript/tabs/tab_arms.tex` and `manuscript/tabs/tab_ablation.tex` agree exactly for L0 through L7. Snapshot copies under `paper_tables/` make the executable audit portable when this folder is published without the paper source. The output is `artifacts/deterministic_crosscheck.json`.

## Remaining research boundary

A causal H0 estimate requires a comparison that passes concurrent-shock and interference gates, or a new set of at least three comparable mandatory events across three platforms. A full H3 behavioral result requires counterfactual trader costs, liquidity or quality response, platform revenue, and retention. These are evidence gaps, not missing prose.
