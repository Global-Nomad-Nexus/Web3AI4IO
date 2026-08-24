-- Pump.fun creator-fee study: exact launch and migration cohort panel.
-- Treatment activation: 2025-05-13 11:27:06 UTC.
-- Public anticipation begins on 2025-05-08.
-- Gross outcomes use Apr 17 to May 7 and May 14 to Jun 3.
-- Seven-day quality outcomes use Apr 10 to Apr 30 and May 14 to Jun 3.
-- Thirty-day quality outcomes use Mar 18 to Apr 7 and May 14 to Jun 3.

WITH launch_events_raw AS (
    SELECT
        'Pump.fun' AS platform,
        call_block_time AS created_at,
        CAST(call_block_date AS DATE) AS cohort_date,
        CAST(account_mint AS VARCHAR) AS token_id,
        coalesce(
            CAST(creator AS VARCHAR),
            CAST(account_user AS VARCHAR),
            CAST(call_tx_signer AS VARCHAR)
        ) AS creator_id,
        CAST(call_tx_id AS VARCHAR) AS creation_tx
    FROM pumpdotfun_solana.pump_call_create
    WHERE call_block_date BETWEEN DATE '2025-03-18' AND DATE '2025-06-03'

    UNION ALL

    SELECT
        'Moonshot' AS platform,
        call_block_time AS created_at,
        CAST(call_block_date AS DATE) AS cohort_date,
        CAST(account_mint AS VARCHAR) AS token_id,
        CAST(call_tx_signer AS VARCHAR) AS creator_id,
        CAST(call_tx_id AS VARCHAR) AS creation_tx
    FROM moonshot_solana.token_launchpad_call_tokenmint
    WHERE call_block_date BETWEEN DATE '2025-03-18' AND DATE '2025-06-03'
),
launch_events AS (
    SELECT platform, created_at, cohort_date, token_id, creator_id, creation_tx
    FROM (
        SELECT
            *,
            row_number() OVER (
                PARTITION BY platform, token_id
                ORDER BY created_at, creation_tx
            ) AS token_row
        FROM launch_events_raw
        WHERE token_id IS NOT NULL
    )
    WHERE token_row = 1
),
migration_events AS (
    SELECT
        'Pump.fun' AS platform,
        CAST(account_arguments[3] AS VARCHAR) AS token_id,
        min(block_time) AS migrated_at
    FROM solana.instruction_calls
    WHERE executing_account = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
      AND executing_account_prefix = '6E'
      AND bytearray_substring(data, 1, 8) = 0x9beae792ec9ea21e
      AND tx_success = true
      AND block_time >= TIMESTAMP '2025-03-18 00:00:00'
      AND block_time < TIMESTAMP '2025-07-04 00:00:00'
    GROUP BY 1, 2

    UNION ALL

    SELECT
        'Moonshot' AS platform,
        CAST(account_mint AS VARCHAR) AS token_id,
        min(call_block_time) AS migrated_at
    FROM moonshot_solana.token_launchpad_call_migratefunds
    WHERE call_block_date BETWEEN DATE '2025-03-18' AND DATE '2025-07-03'
    GROUP BY 1, 2
),
cohorts AS (
    SELECT
        l.*,
        m.migrated_at,
        CASE
            WHEN m.migrated_at BETWEEN l.created_at AND l.created_at + INTERVAL '7' DAY
            THEN 1 ELSE 0
        END AS graduated_7d,
        CASE
            WHEN m.migrated_at BETWEEN l.created_at AND l.created_at + INTERVAL '30' DAY
            THEN 1 ELSE 0
        END AS graduated_30d
    FROM launch_events AS l
    LEFT JOIN migration_events AS m
        ON l.platform = m.platform
       AND l.token_id = m.token_id
),
daily AS (
    SELECT
        platform,
        cohort_date,
        count(*) AS launches,
        count(DISTINCT creator_id) AS unique_creators,
        sum(graduated_7d) AS graduated_7d,
        avg(CAST(graduated_7d AS DOUBLE)) AS graduation_rate_7d,
        sum(graduated_30d) AS graduated_30d,
        avg(CAST(graduated_30d AS DOUBLE)) AS graduation_rate_30d
    FROM cohorts
    GROUP BY 1, 2
),
date_spine AS (
    SELECT day AS cohort_date
    FROM UNNEST(
        sequence(DATE '2025-03-18', DATE '2025-06-03', INTERVAL '1' DAY)
    ) AS t(day)
),
platforms AS (
    SELECT platform
    FROM (VALUES ('Pump.fun'), ('Moonshot')) AS p(platform)
)
SELECT
    p.platform,
    d.cohort_date,
    CASE
        WHEN d.cohort_date BETWEEN DATE '2025-04-17' AND DATE '2025-05-07' THEN 'pre'
        WHEN d.cohort_date BETWEEN DATE '2025-05-14' AND DATE '2025-06-03' THEN 'post'
        ELSE NULL
    END AS gross_period,
    CASE
        WHEN d.cohort_date BETWEEN DATE '2025-04-10' AND DATE '2025-04-30' THEN 'pre'
        WHEN d.cohort_date BETWEEN DATE '2025-05-14' AND DATE '2025-06-03' THEN 'post'
        ELSE NULL
    END AS quality_7d_period,
    CASE
        WHEN d.cohort_date BETWEEN DATE '2025-03-18' AND DATE '2025-04-07' THEN 'pre'
        WHEN d.cohort_date BETWEEN DATE '2025-05-14' AND DATE '2025-06-03' THEN 'post'
        ELSE NULL
    END AS quality_30d_period,
    coalesce(x.launches, 0) AS launches,
    coalesce(x.unique_creators, 0) AS unique_creators,
    coalesce(x.graduated_7d, 0) AS graduated_7d,
    x.graduation_rate_7d,
    coalesce(x.graduated_30d, 0) AS graduated_30d,
    x.graduation_rate_30d
FROM date_spine AS d
CROSS JOIN platforms AS p
LEFT JOIN daily AS x
    ON d.cohort_date = x.cohort_date
   AND p.platform = x.platform
ORDER BY d.cohort_date, p.platform;
