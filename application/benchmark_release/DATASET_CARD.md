# application Benchmark Release Dataset Card

## Scope

This release covers application's Pump.fun / PumpSwap application arm and the matched
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

- Reproduce application's evidence-ladder claim boundaries.
- Test how model or analyst conclusions change as evidence requirements are
  scaffolded.
- Build follow-on token-launch studies using fixed event, horizon, and
  claim-boundary fields.
- Audit negative, unsupported, or welfare-unidentified outputs as valid
  benchmark results.

## Out-of-Scope Uses

- Do not infer platform-wide welfare gains from proxy activity rows.
- Do not treat matched Base/Clanker rows as a full cross-chain causal
  replication.
- Do not claim a causal Telegram effect from the current matched social-metadata
  design.
- Do not use selected Moralis decoded swaps as full-cohort decoded volume.

## Sources and Coverage

- Solana/PumpSwap rows combine local market panels, RPC validation windows,
  Moralis decoded-sample rows, Dune-rendered extraction paths, and RED-PUMP
  token outcomes.
- Base/Clanker rows use Base on-chain logs, Clanker v4 `TokenCreated` logs,
  Uniswap v4 PoolManager `Swap` logs, and ERC20 `Transfer` logs for holder
  reconstruction. The current release also includes archive/indexer request
  manifests for the expanded Base universe: `13,880` matched token rows and
  `41,640` expected 1/7/30 day token-horizon rows. A resumable smoke-tested
  import ledger validates the path but does not close full 30-day coverage.
- Off-chain covariates include token social metadata plus Discord, sentiment,
  TVL, and RWA context where available.

## Known Limitations

- Full-cohort decoded Solana USD-volume and active-trader outcomes remain a
  registered gap.
- Same-cohort early-wallet concentration is not yet available for all
  PumpSwap tokens.
- The Clanker/Base accepted event has a bounded on-chain outcome sample plus a
  larger full-cohort request manifest and smoke-tested import path. Broader
  archive/indexer swap and transfer coverage is still needed for platform-wide
  Base claims.
- Social metadata is self-reported and may proxy for creator quality or
  promotion effort; the Telegram design is matched and sensitivity-audited but
  not exogenous.

## Licensing and Citation

Code is prepared for MIT release. Generated data tables are prepared for CC BY
4.0 release subject to upstream license compatibility checks. Citation metadata
is in `../CITATION.cff`; a Zenodo DOI is still a release step, not a completed
artifact.
