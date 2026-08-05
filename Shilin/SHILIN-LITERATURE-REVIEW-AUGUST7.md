# Shilin Literature Review and Top-Conference Assessment

This note reviews the August 7 Shilin revision direction after reading the
teacher feedback, the Shilin replication package, the benchmark release, and
the current manuscript draft. It focuses only on Shilin's Pump.fun / PumpSwap
application arm.

## Bottom Line

The direction is academically reasonable and worth implementing. The strongest
top-conference framing is not "PumpSwap worked." It is:

1. Token launchpads are high-throughput market-design institutions whose public
   claims are usually evaluated by fragile dashboard comparisons.
2. Shilin contributes a reusable evidence-quality benchmark with explicit event
   registries, token-horizon panels, covariates, claim boundaries, and data-gap
   ledgers.
3. The PumpSwap case demonstrates Case A: a naive positive market conclusion
   becomes uncertain after controls, pre-trend checks, honest few-cluster
   inference, and stakeholder metrics.
4. The Telegram/social metadata result is the best current Case B candidate:
   a naive near-null graduation-quality view becomes a strong token-level
   association after stratification and controls. It should be presented as a
   preliminary mirror case, not as a completed causal effect.
5. Clanker/Base is now a bounded accepted cross-chain case because activation,
   adoption denominator, and 1/7/30 day token-horizon outcomes are verified from
   Base public RPC. It should be framed as event-architecture evidence, not as
   full-cohort causal replication.

For a workshop or NeurIPS-style evaluations/datasets submission, this is a
credible path. For a Nature-family venue or a main-conference empirical paper,
the critical missing pieces are a full-cohort or matched cross-chain
replication, a true causal mirror case, and full-cohort decoded token outcomes.

## Literature Positioning

### Token-platform and DeFi empirics

The existing manuscript already has the right foundations: tokenomics and
platform adoption, token financing, DeFi market infrastructure, retail trading,
MEV, and scam-token risk. This supports the move away from a single price or
volume series and toward a lifecycle benchmark. The missing object in that
literature is not another descriptive dashboard; it is a reusable way to score
whether platform-design claims survive stronger evidence.

Recommended paper emphasis:

- Treat the platform rule as the empirical unit, not only the token price.
- Treat graduation, migration, persistence, concentration, and social metadata
  as separate stakeholder outcomes.
- Treat negative, unsupported, and welfare-unidentified findings as benchmark
  outputs.

### Benchmark and dataset contribution

The teacher's three-sheet request is exactly the right conversion from case
study to benchmark. The current Shilin release already implements:

- `events.csv`: accepted/conditional/rejected rule-event registry.
- `metrics_panel.csv`: platform-day, token-horizon, token-wallet, and
  token-cohort rows with claim boundaries.
- `covariates.csv`: token social metadata plus Discord, sentiment, TVL, and
  RWA context.
- supplemental claim-scope, data-gap, mirror-case, cross-chain, and agentic
  panels.

The top-conference value comes from the rejected and conditional rows. They
show that the benchmark measures evidence quality rather than cherry-picking
successful cases.

### Agentic evaluation

General LLM-agent benchmarks such as AgentBench, SWE-bench, and MLAgentBench
evaluate agents in interactive or research-like environments. Shilin's angle is
different and useful: the evaluated object is an agent's evidence behavior when
causal evidence is incrementally scaffolded. This is a good fit for Trustworthy
AI for Good because the failure mode is socially meaningful: an AI assistant can
turn a fragile market pattern into an overconfident policy or welfare claim.

Recommended manuscript sentence:

"Unlike general agent benchmarks that score task completion, our agentic arm
scores evidence behavior: whether an LLM updates from unsupported L0 conclusions
to bounded, stakeholder-specific claims as the ladder adds controls,
diagnostics, and claim-boundary requirements."

### Mirror case

The Telegram/social candidate is directionally strong:

- Overall RED-PUMP graduation: about 0.198%.
- Telegram-linked graduation: about 1.485%.
- No-Telegram graduation: about 0.166%.
- Controlled LPM coefficient for `has_telegram`: about +1.227 percentage
  points with a narrow confidence interval.

This is not yet a causal effect because social links can proxy for project
quality, community effort, or creator sophistication. However, it is a valid
preliminary Case B because the ladder changes the evidence status in the
opposite direction from Case A:

- Case A: naive yes -> trustworthy uncertain.
- Case B: naive near-null -> adjusted association with a clear claim boundary.

The top-conference upgrade is to find an exogenous attention or platform-design
event that shifts community metadata, then rerun the same ladder on token
1/7/30 day outcomes.

### Cross-chain case

Clanker/Base is a better Shilin cross-chain case than an unrelated second chain
because it maps to the same schema:

- rule family: trader protection / MEV protection;
- event unit: deployment or default-configuration change;
- token unit: Base ERC-20 launch;
- outcome horizons: 1/7/30 day activity, buy/sell counts, active traders,
  early-wallet concentration;
- claim boundary: the bounded accepted sample verifies event architecture and
  horizons, but not platform-wide causal effects.

The current implementation now passes the event-architecture gates for a bounded
sample:

- activation timestamp: first observed v4.1 MEV-module `TokenCreated` log at
  `2025-08-26T20:41:57Z`;
- on-chain evidence: Base transaction
  `0x5c076d1967b9f4873d36191321ccf015015b48687d0f176c6ad7091a84551985`;
- adoption denominator: 23,033 Clanker v4 token-launch logs in the search
  window, with 2 v4.1 rows;
- comparison units: nearest v4.0 control and first v4.1 treated bounded sample;
- token horizons: 1/7/30 day Uniswap v4 PoolManager swap outcomes.

The remaining top-conference gap is scale and design: this is not yet a matched
or full-cohort Base replication with holder-level outcomes.

Four.meme/BNB and SunPump/TRON remain useful backups, but they should not be the
primary Shilin extension unless their event-date and token-horizon data are
cleaner than Clanker's.

## Implementation Checklist

Completed in this revision:

- Extended `metrics_panel.csv` to expose buy/sell counts and first/last trade
  timestamps when the evidence layer supports them.
- Added token-wallet early-window rows when same-cohort early-wallet samples
  are present.
- Added `mirror_case_ladder.csv` to turn Telegram/social metadata into a
  rung-by-rung preliminary Case B.
- Implemented bounded Clanker/Base on-chain validation and moved it from
  candidate to accepted event-architecture evidence.
- Added manuscript text for agentic evidence behavior, societal impact, the
  preliminary mirror case, and limitations.

Still needed for top-tier claims:

- Full-cohort decoded 1/7/30 day outcomes for all graduated tokens.
- Same-cohort early-wallet concentration joined to downstream outcomes.
- A scaled non-Solana matched or full-cohort replication beyond the bounded
  Clanker/Base accepted event.
- A causal version of Case B, ideally based on an exogenous attention,
  protection, or launch-design shock.

## Sources Checked

- Bitquery Pump.fun to PumpSwap lifecycle documentation:
  https://docs.bitquery.io/docs/blockchain/Solana/Pumpfun/pump-fun-to-pump-swap/
- Pump.fun fee documentation:
  https://pump.fun/docs/fees
- The Block on Pump.fun BOOST and graduation-rate changes:
  https://www.theblock.co/post/409815/pump-fun-token-graduation-rate-jumps-boost-changes-launch-incentives
- Clanker documentation repository:
  https://github.com/clanker-devco/DOCS
- Clanker v4 contracts:
  https://github.com/clanker-devco/v4-contracts
- Bitquery Base Clanker API documentation:
  https://docs.bitquery.io/docs/blockchain/Base/base-clanker-api/
- Uniswap v4 deployments:
  https://developers.uniswap.org/docs/protocols/v4/deployments
- AgentBench:
  https://arxiv.org/abs/2308.03688
- SWE-bench:
  https://arxiv.org/abs/2310.06770
- MLAgentBench:
  https://arxiv.org/abs/2310.03302
