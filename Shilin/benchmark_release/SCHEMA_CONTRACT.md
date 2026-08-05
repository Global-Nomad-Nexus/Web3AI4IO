# Shilin Release Schema Contract

Every primary table must include `event_id` and `claim_boundary`. Every
computed row must preserve enough provenance to prevent proxy or sample evidence
from being upgraded into causal evidence.

## `events.csv`

Required fields:

- `event_id`
- `platform`
- `chain`
- `rule_family`
- `activation_timestamp_utc`
- `activation_evidence_type`
- `comparison_unit_status`
- `eligibility_status`
- `hypothesis_tags`
- `claim_boundary`
- `source_artifact`

Allowed `eligibility_status` values:

- `accepted`
- `conditional`
- `rejected`

## `metrics_panel.csv`

Required fields:

- `event_id`
- `timestamp_utc`
- `unit_id`
- `unit_type`
- `platform`
- `chain`
- `scale`
- `frequency`
- `claim_boundary`
- `source_layer`
- `status`

Fixed horizon token rows should use `horizon_days` in `{1, 7, 30}` whenever the
source layer supports those windows. Missing values are permitted only when the
row unit is not a fixed-horizon unit or the data-gap ledger records the missing
field.

Holder reconstruction rows should populate `holder_concentration_top10` and
`holder_count` when ERC20 or wallet-level logs are available. These fields are
descriptive concentration outcomes, not welfare or causal harm estimates.

## `covariates.csv`

Required fields:

- `event_id`
- `timestamp_utc`
- `unit_id`
- `unit_type`
- `platform`
- `chain`
- `frequency`
- `covariate_family`
- `claim_boundary`
- `source_layer`
- `status`

Covariates are never treatments unless the corresponding `events.csv` row
defines an accepted rule event and the claim-scope ledger allows the claim.

## Supplemental Mirror Tables

`telegram_mirror_design.csv`, `telegram_mirror_balance.csv`, and
`telegram_mirror_matched_cells.csv` are supplemental design diagnostics. They
may support a matched predictive/mechanism claim only when their
`claim_boundary` fields are preserved. They must not be merged into a causal
Telegram treatment claim without an accepted social-attention event or stronger
event-time exposure design.

## Supplemental Base Full-Cohort Tables

`clanker_base_full_cohort_manifest.csv` is the matched Base universe to be
filled by archive/indexer data. It must preserve `token_id`, `cohort_side`,
`cohort_match_id`, `launch_block`, `pool_id`, `paired_token`,
`max_horizon_end_block`, `swap_query_key`, `transfer_query_key`, and
`claim_boundary`.

`clanker_base_full_cohort_pool_query_bounds.csv` and
`clanker_base_full_cohort_transfer_query_bounds.csv` specify log-query bounds.
They are request contracts, not outcomes. Each row must include
`contract_address`, `from_block`, `to_block`, `topic0`, and
`required_import_columns`.

`clanker_base_full_cohort_expected_horizons.csv` defines the 1/7/30 day rows
that should exist after imports are validated. A platform-wide Base causal
replication claim is blocked until these expected rows are filled by swap and
transfer imports and holder reconstruction passes coverage checks.

`clanker_base_full_cohort_import_coverage.csv` records resumable backfill
coverage. `processed_zero_rows` is a valid result for a queried unit, but only
processed coverage for both `poolmanager_swaps` and `erc20_transfers` can close
the full-cohort gap.

`clanker_base_causal_diagnostics.csv` reports matched-pair differences for the
currently covered Base sample. Its `sample_status` and `claim_boundary` fields
must remain bounded unless the full-cohort import coverage is complete.
