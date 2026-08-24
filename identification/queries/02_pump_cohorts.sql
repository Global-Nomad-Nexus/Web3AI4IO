-- Pump.fun creation cohorts and fixed-horizon graduation outcomes.
-- Source logic follows Dune's official pumpdotfun_solana base-trades model.

WITH params AS (
    SELECT
        TIMESTAMP '2025-04-17 00:00:00' AS extract_start,
        TIMESTAMP '2025-06-03 23:59:59' AS cohort_end
),
creates AS (
    SELECT
        call.block_time AS created_at_utc,
        call.block_slot AS created_slot,
        call.tx_id AS creation_tx,
        call.tx_signer AS creator_id,
        call.account_arguments[1] AS token_id
    FROM solana.instruction_calls AS call
    CROSS JOIN params
    WHERE call.executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND call.executing_account_prefix = '6E'
      AND bytearray_substring(call.data, 1, 8) = 0x181ec828051c0777
      AND call.tx_success = true
      AND call.block_time BETWEEN params.extract_start AND params.cohort_end
),
migrations AS (
    SELECT
        call.block_time AS migrated_at_utc,
        call.block_slot AS migrated_slot,
        call.tx_id AS migration_tx,
        call.account_arguments[3] AS token_id
    FROM solana.instruction_calls AS call
    CROSS JOIN params
    WHERE call.executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND call.executing_account_prefix = '6E'
      AND bytearray_substring(call.data, 1, 8) = 0x9beae792ec9ea21e
      AND call.tx_success = true
      AND call.block_time BETWEEN params.extract_start AND params.cohort_end + INTERVAL '30' DAY
)
SELECT
    'Pump.fun' AS platform,
    'Solana' AS chain,
    CAST(c.token_id AS VARCHAR) AS token_id,
    CAST(c.creator_id AS VARCHAR) AS creator_id,
    c.created_at_utc,
    CAST(date_trunc('day', c.created_at_utc) AS DATE) AS cohort_date_utc,
    m.migrated_at_utc,
    CASE
        WHEN c.created_at_utc > current_timestamp - INTERVAL '7' DAY THEN NULL
        ELSE coalesce(m.migrated_at_utc <= c.created_at_utc + INTERVAL '7' DAY, false)
    END AS graduated_7d,
    CASE
        WHEN c.created_at_utc > current_timestamp - INTERVAL '30' DAY THEN NULL
        ELSE coalesce(m.migrated_at_utc <= c.created_at_utc + INTERVAL '30' DAY, false)
    END AS graduated_30d,
    c.creation_tx,
    m.migration_tx
FROM creates AS c
LEFT JOIN migrations AS m USING (token_id);
