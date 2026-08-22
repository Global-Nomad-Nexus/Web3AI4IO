# application Data Limitation

## Scope

This note documents the status and permitted use of the decoded Solana swap data supplied in the application reproducibility bundle.

## Pagination limitation

The delivered Moralis collection contains 173,102 decoded swap rows for 294 of the 1,651 graduated Pump.fun tokens. It also contains 882 token horizon summaries covering 1, 7, and 30 day windows.

The associated fetch status table shows that 876 of the 882 token horizon requests ended with `page_limit_reached_lower_bound`. Only six requests ended with `ok`. A remaining cursor means that more pages existed when collection stopped. Therefore the delivered trade counts, volume, wallet counts, buy and sell counts, and first or last observed trade timestamps are lower bounds for page capped windows.

The observed 173,102 rows also contain repeated transactions across nested horizons. They must not be interpreted as 173,102 unique cohort wide swaps without applying the transaction identity and horizon semantics.

## Permitted use

The decoded swap files are retained exactly as supplied by application and normalized into the canonical release without imputing missing pages or tokens.

They are validation data only. Appropriate uses include schema validation, pipeline tests, field interpretation, bounded spot checks, and comparisons between decoded swaps and RPC transaction proxies.

They are not suitable for estimating cohort wide trade volume, active trader counts, survival, retention, treatment effects, or complete 1, 7, and 30 day outcomes.

## Project decision

The data expansion project accepts this limitation. It will not continue collecting decoded Solana swaps. application's delivered files remain the final decoded swap snapshot for this project.

Future canonical releases must preserve the following rules:

1. Keep the raw application files immutable.
2. Label page capped observations as lower bounds.
3. Label the dataset role as validation only.
4. Do not promote RPC transaction proxies to decoded swap metrics.
5. Do not treat missing tokens or pages as zero activity.
6. Do not use this validation sample as the primary outcome source for experiments.

## Canonical status

The canonical `decoded_swaps` and `token_horizons` tables preserve the application snapshot. The `coverage_ledger` records 294 tokens as `decoded_lower_bound_page_capped` and 1,357 tokens as `no_decoded_swap_data`. No additional decoded swap acquisition is planned.
