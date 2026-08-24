# Data Expansion Schema Contract

## Common provenance fields

Every processed dataset must include `source_provider`, `source_endpoint_or_query`, `collected_at_utc`, `collection_run_id`, `source_status`, and `claim_boundary`. Raw files must be immutable within a run and receive a SHA256 hash in the source manifest or coverage report.

## Solana decoded swaps

1. Raw unit is one decoded swap leg identified by `transaction_signature`, `instruction_index`, and `inner_instruction_index` where available.
2. Required identifiers are `mint`, `pool_address`, `wallet`, `block_time_utc`, `side`, `token_amount`, `quote_amount`, `quote_mint`, and `amount_usd`.
3. Aggregated unit is `mint` by `horizon_days`, where `horizon_days` is one of 1, 7, or 30 and the window starts at `graduated_at_utc`.
4. Required aggregates are `decoded_trade_count`, `decoded_volume_usd`, `decoded_active_traders`, `decoded_buyer_count`, `decoded_seller_count`, `first_decoded_trade_at`, `last_decoded_trade_at`, `pages_fetched`, `cursor_remaining`, and `coverage_status`.
5. A row is complete only when pagination is exhausted through the horizon end. Page capped rows must be labeled lower bounds.

## Telegram activity

1. Eligibility unit is `mint` to `telegram_handle` in `telegram_collection_frame.csv`.
2. Raw activity unit is `telegram_handle` by `message_id`.
3. Required activity fields are `message_timestamp_utc`, `views`, `forwards`, `replies`, `edit_timestamp_utc`, `is_service_message`, and `collection_status`.
4. Message text, usernames, phone numbers, member lists, and private invite content are excluded by default.
5. Aggregate unit is `telegram_handle` by UTC day. Required aggregates are `message_count`, `view_sum`, `view_median`, `forward_sum`, `reply_sum`, `active_hours`, and `coverage_status`.
6. Token linkage is many to one. Channel observations are joined back to every linked mint without duplicating channel totals during channel level summaries.

## Base Clanker logs

1. Launch unit is one Clanker v4 `TokenCreated` log identified by `transaction_hash` and `log_index`.
2. Pool mapping unit is one token to one Uniswap v4 `pool_id`. A pool ID is not a pool contract address.
3. Pool initialization unit is one PoolManager Initialize log identified by `transaction_hash`, `log_index`, and `pool_id`.
4. Initial liquidity unit is one launch transaction PoolManager ModifyLiquidity log with positive `liquidity_delta`.
5. A launch transaction ModifyLiquidity log with zero delta is a position poke and remains a lifecycle event, not a liquidity addition.
6. Required protocol configuration includes creator, message sender, version class, hook, hook label, MEV module, MEV module label, locker, paired token, starting tick, and extension supply.
7. Required query provenance includes block bounds, PoolManager address, event topics, fixed pool filter, transaction reconciliation, endpoint, retries, completion status, and SHA256 digest.
8. Swap, Transfer, holder, and trading outcome data are excluded from this phase.

## Missingness states

Use explicit states `observed`, `processed_zero_rows`, `not_collected`, `not_applicable`, and `not_collected_by_policy` in canonical coverage. Source acquisition ledgers may additionally use `credential_blocked`, `query_failed`, and `page_capped_lower_bound`. Empty numeric values must not be converted to zero unless `processed_zero_rows` is established for the full query bound.
