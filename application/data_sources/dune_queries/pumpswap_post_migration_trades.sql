-- Application-arm H1 data export: post-migration persistence for graduated Pump.fun tokens.
--
-- Required output schema:
-- mint, graduated_at, horizon_days, swap_count, active_traders, volume_usd,
-- first_trade_at, last_trade_at, inactivity_gap_hours, reactivated_after_7d
--
-- Usage:
-- 1. Generate or paste a graduated token CTE with columns (mint, graduated_at).
-- 2. Verify Dune's latest dex_solana.trades schema before running.
-- 3. Export CSV to application/data/external/dune_post_migration_trades.csv.

WITH graduated(mint, graduated_at) AS (
    VALUES
    -- ('MINT_ADDRESS', TIMESTAMP '2025-03-20 00:00:00 UTC')
),
token_trades AS (
    SELECT
        g.mint,
        g.graduated_at,
        t.block_time,
        t.tx_id,
        t.trader_id,
        t.amount_usd
    FROM dex_solana.trades t
    JOIN graduated g
      ON t.token_bought_mint_address = g.mint
      OR t.token_sold_mint_address = g.mint
    WHERE t.block_time >= g.graduated_at
      AND t.block_time < g.graduated_at + INTERVAL '30' day
),
horizons AS (
    SELECT 1 AS horizon_days
    UNION ALL SELECT 7
    UNION ALL SELECT 30
),
by_horizon AS (
    SELECT
        g.mint,
        g.graduated_at,
        h.horizon_days,
        COUNT(DISTINCT t.tx_id) AS swap_count,
        COUNT(DISTINCT t.trader_id) AS active_traders,
        COALESCE(SUM(t.amount_usd), 0) AS volume_usd,
        MIN(t.block_time) AS first_trade_at,
        MAX(t.block_time) AS last_trade_at
    FROM graduated g
    CROSS JOIN horizons h
    LEFT JOIN token_trades t
      ON t.mint = g.mint
     AND t.block_time < g.graduated_at + h.horizon_days * INTERVAL '1' day
    GROUP BY 1, 2, 3
),
daily_activity AS (
    SELECT
        mint,
        DATE_TRUNC('day', block_time) AS trade_day,
        COUNT(*) AS swaps
    FROM token_trades
    GROUP BY 1, 2
),
reactivation AS (
    SELECT
        mint,
        MAX(CASE WHEN trade_day >= DATE_TRUNC('day', graduated_at + INTERVAL '7' day) THEN 1 ELSE 0 END) AS reactivated_after_7d
    FROM (
        SELECT d.mint, g.graduated_at, d.trade_day
        FROM daily_activity d
        JOIN graduated g ON d.mint = g.mint
    )
    GROUP BY 1
)
SELECT
    b.mint,
    b.graduated_at,
    b.horizon_days,
    b.swap_count,
    b.active_traders,
    b.volume_usd,
    b.first_trade_at,
    b.last_trade_at,
    DATE_DIFF('hour', b.first_trade_at, b.last_trade_at) AS inactivity_gap_hours,
    COALESCE(r.reactivated_after_7d, 0) AS reactivated_after_7d
FROM by_horizon b
LEFT JOIN reactivation r ON b.mint = r.mint
ORDER BY b.mint, b.horizon_days;
