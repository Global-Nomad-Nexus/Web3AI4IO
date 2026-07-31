-- Auto-rendered by Shilin/scripts/run_dune_token_exports.py.
-- Outcome: token-level Pump.fun/PumpSwap post-migration persistence.
-- Expected rows for full export: 1,651 tokens x 3 horizons = 4,953 rows.

WITH graduated(mint, graduated_at) AS (
    VALUES
        ('DaFLwap1y6gdCtRcP9nWANHHARtSdF4a3NRDh4jcpump', CAST(from_iso8601_timestamp('2026-05-08T22:36:53.113000Z') AS timestamp)),
        ('Dd667TvuCArUmTMhejtwyXxaLPo1tqQEXbGrcehpump', CAST(from_iso8601_timestamp('2026-05-09T03:21:53.195000Z') AS timestamp)),
        ('FrXWa62SJc3NYX3yhGtdcVFw4RJ6UQ4FAN3N1iVcpump', CAST(from_iso8601_timestamp('2026-05-09T11:33:53.359000Z') AS timestamp)),
        ('31eo8y4rLj1AsYXjofkANu9hjavCDUiqLxuV6oxgpump', CAST(from_iso8601_timestamp('2026-05-09T11:39:53.392000Z') AS timestamp)),
        ('35v5d5NSnu9eynU4atXAf1G2cmRWps1G4ZmXmwYGpump', CAST(from_iso8601_timestamp('2026-05-09T12:39:53.409000Z') AS timestamp)),
        ('AaieEQp1S2KcPKxob1CRUYSeHRQ9dLJyYEKcCbJpump', CAST(from_iso8601_timestamp('2026-05-09T14:12:53.453000Z') AS timestamp)),
        ('5HZjTTkctgEWSWC76LkRK4ATjZuPm9wXFLHJJcNgpump', CAST(from_iso8601_timestamp('2026-05-10T03:39:53.628000Z') AS timestamp)),
        ('H58iGucz1atKdKNLs1vnsNmLcPDQa9acMgQsaceLpump', CAST(from_iso8601_timestamp('2026-05-10T04:48:53.620000Z') AS timestamp)),
        ('48vV4wziVfaz5T75J9rvqCFwSPrPodHtkn3CPTfjpump', CAST(from_iso8601_timestamp('2026-05-10T05:15:53.626000Z') AS timestamp)),
        ('24hTZu4B7QoxKjGo1R6AKqdhkWE3sYoHFiTXJJwJpump', CAST(from_iso8601_timestamp('2026-05-10T05:18:53.653000Z') AS timestamp))
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
    WHERE t.block_month >= DATE '2026-05-01'
      AND t.block_month <= DATE '2026-06-01'
      AND t.block_date >= DATE '2026-05-08'
      AND t.block_date <= DATE '2026-06-09'
      AND (
          t.token_bought_mint_address IN (SELECT mint FROM graduated)
          OR t.token_sold_mint_address IN (SELECT mint FROM graduated)
      )
      AND t.block_time >= CAST(from_iso8601_timestamp('2026-05-08T22:36:53.113000Z') AS timestamp)
      AND t.block_time < CAST(from_iso8601_timestamp('2026-06-09T05:18:53.653000Z') AS timestamp)
      AND t.block_time >= g.graduated_at
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
        t.mint,
        DATE_TRUNC('day', t.block_time) AS trade_day,
        COUNT(*) AS swaps
    FROM token_trades t
    GROUP BY 1, 2
),
reactivation AS (
    SELECT
        d.mint,
        MAX(CASE WHEN d.trade_day >= DATE_TRUNC('day', g.graduated_at + INTERVAL '7' day) THEN 1 ELSE 0 END) AS reactivated_after_7d
    FROM daily_activity d
    JOIN graduated g ON d.mint = g.mint
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
