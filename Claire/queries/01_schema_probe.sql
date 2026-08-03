-- Dune schema gate for the Pump.fun creator-fee study.
-- Run this query before estimating any effect. It returns metadata only.

WITH candidate_tables AS (
    SELECT
        table_schema,
        table_name,
        column_name,
        data_type,
        ordinal_position
    FROM information_schema.columns
    WHERE (
        table_schema IN (
            'pumpdotfun_solana',
            'pumpswap_solana',
            'raydium_launchlab_v1',
            'raydium_solana'
        )
        OR lower(table_name) LIKE '%launchpad%'
        OR lower(table_name) LIKE '%launchlab%'
    )
    AND (
        lower(column_name) IN (
            'block_time',
            'call_block_time',
            'block_slot',
            'call_block_slot',
            'tx_id',
            'call_tx_id',
            'trader_id',
            'call_tx_signer',
            'platform_name',
            'token_bought_address',
            'token_sold_address',
            'account_base_token_mint',
            'account_mint',
            'amount_usd'
        )
        OR lower(column_name) LIKE '%creator%'
        OR lower(column_name) LIKE '%initialize%'
        OR lower(column_name) LIKE '%migrate%'
    )
)
SELECT *
FROM candidate_tables
ORDER BY table_schema, table_name, ordinal_position;
