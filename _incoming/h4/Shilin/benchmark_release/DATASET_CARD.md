# Shilin Benchmark Release Dataset Card

## Scope

This release covers Shilin's Pump.fun / PumpSwap application arm and the matched
Clanker/Base cross-chain validation case. It is designed as a reusable
evidence-quality benchmark for token-launch platform claims, not as a complete
welfare dataset.

## Primary Tables

- `data/events.csv`: rule-event registry with accepted, rejected, and
  conditional rows.
- `data/metrics_panel.csv`: platform-day, token-horizon, token-wallet, and
  token-cohort outcomes at registered horizons.
- `data/covariates.csv`: token social metadata and off-chain context.

## Intended Uses

- Reproduce Shilin's evidence-ladder claim boundaries.
- Test how model or analyst conclusions change as evidence requirements are
  scaffolded.
- Build follow-on token-launch studies using fixed event, horizon, and
  claim-boundary fields.
- Audit negative, unsupported, or welfare-unidentified outputs as valid
  benchmark results.
- Reproduce the paired Case A/Case B ladder in which the same evidence stages
  move a naive positive market claim to uncertainty and a naive near-null
  social-metadata read to a supported matched signal.
- Audit H4 early-wallet proxy evidence with explicit buyer/holder
  classification boundaries.
- Compare model behavior under registered agentic scaffold ablations, including
  no-API local Ollama models.

## Out-of-Scope Uses

- Do not infer platform-wide welfare gains from proxy activity rows.
- Do not treat matched Base/Clanker rows as a full cross-chain causal
  replication.
- Do not claim a causal Telegram effect from the current matched social-metadata
  design.
- Do not describe the paired Case B row as a causal effect; it is a supported
  matched predictive/mechanism signal until an exogenous exposure shock exists.
- Do not use selected Moralis decoded swaps as full-cohort decoded volume.
- Do not treat the 10-token early-wallet proxy sample as all-token H4 causal
  evidence.
- Do not interpret agentic scaffold-ablation differences as causal prompt
  treatment effects.

## Sources and Coverage

- Solana/PumpSwap rows combine local market panels, RPC validation windows,
  Moralis decoded-sample rows, Dune-rendered extraction paths, RED-PUMP token
  outcomes, and a bounded early-wallet decoded-proxy sample. The current H4
  early-wallet sample covers 10 tokens, 298 parsed early pool transactions, and
  101 conservative buyer/seller/holder proxy classifications.
- Base/Clanker rows use Base on-chain logs, Clanker v4 `TokenCreated` logs,
  Uniswap v4 PoolManager `Swap` logs, and ERC20 `Transfer` logs for holder
  reconstruction. The current release also includes archive/indexer request
  manifests for the expanded Base universe: `13,880` matched token rows and
  `41,640` expected 1/7/30 day token-horizon rows. A resumable smoke-tested
  import ledger validates the path but does not close full 30-day coverage.
- Off-chain covariates include token social metadata plus Discord, sentiment,
  TVL, and RWA context where available.
- Agentic rows include L0-L7 prompt scores plus registered multi-model scaffold
  ablations across DeepSeek and local Ollama models.

## Known Limitations

- Full-cohort decoded Solana USD-volume and active-trader outcomes remain a
  registered gap.
- Same-cohort decoded early-wallet buyer/holder classification is not yet
  available for all 1,651 PumpSwap tokens.
- The Clanker/Base accepted event has a bounded on-chain outcome sample plus a
  larger full-cohort request manifest and smoke-tested import path. Broader
  archive/indexer swap and transfer coverage is still needed for platform-wide
  Base claims.
- `data/full_cohort_coverage_audit.csv` tracks the exact processed-unit share
  that blocks platform-wide Base causal replication.
- Social metadata is self-reported and may proxy for creator quality or
  promotion effort; the Telegram design is matched and sensitivity-audited but
  not exogenous.
- Multi-model agentic ablation coverage is real but still partial; it supports
  robustness auditing, not a universal claim about every model family.

## Licensing and Citation

Code is prepared for MIT release. Generated data tables are prepared for CC BY
4.0 release subject to upstream license compatibility checks. Citation metadata
is in `../CITATION.cff`. `zenodo_metadata.json` is prepared for deposit, but a
Zenodo DOI is still a release step, not a completed artifact.
