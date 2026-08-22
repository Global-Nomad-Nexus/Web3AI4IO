-- Shilin H4 data export: early allocation concentration / sniper proxy.
--
-- Required output schema:
-- mint, launch_or_graduated_at, early_window_seconds, early_buyers,
-- early_buy_volume_usd, top1_early_buyer_share, top5_early_buyer_share,
-- top10_early_buyer_share, early_buyer_hhi, first_trade_at, last_early_trade_at
--
-- Dune table names for Pump.fun bonding-curve events change over time.
-- The CTE `pumpfun_buys` should be replaced with the latest decoded Pump.fun
-- program event table or a curated Solana instruction-decoding table.

WITH tokens(mint, launch_or_graduated_at) AS (
    VALUES
    -- ('MINT_ADDRESS', TIMESTAMP '2025-03-20 00:00:00 UTC')
),
pumpfun_buys AS (
    SELECT
        token_mint_address AS mint,
        block_time,
        tx_id,
        trader_id AS buyer,
        amount_usd
    FROM dex_solana.trades
    WHERE project IN ('pump.fun', 'pump')
),
early AS (
    SELECT
        t.mint,
        t.launch_or_graduated_at,
        60 AS early_window_seconds,
        b.buyer,
        SUM(b.amount_usd) AS buyer_volume_usd,
        MIN(b.block_time) AS first_trade_at,
        MAX(b.block_time) AS last_early_trade_at
    FROM tokens t
    JOIN pumpfun_buys b
      ON t.mint = b.mint
     AND b.block_time >= t.launch_or_graduated_at
     AND b.block_time < t.launch_or_graduated_at + INTERVAL '60' second
    GROUP BY 1, 2, 3, 4
),
ranked AS (
    SELECT
        *,
        buyer_volume_usd / NULLIF(SUM(buyer_volume_usd) OVER (PARTITION BY mint), 0) AS buyer_share,
        ROW_NUMBER() OVER (PARTITION BY mint ORDER BY buyer_volume_usd DESC) AS buyer_rank
    FROM early
)
SELECT
    mint,
    MIN(launch_or_graduated_at) AS launch_or_graduated_at,
    60 AS early_window_seconds,
    COUNT(DISTINCT buyer) AS early_buyers,
    SUM(buyer_volume_usd) AS early_buy_volume_usd,
    SUM(CASE WHEN buyer_rank <= 1 THEN buyer_share ELSE 0 END) AS top1_early_buyer_share,
    SUM(CASE WHEN buyer_rank <= 5 THEN buyer_share ELSE 0 END) AS top5_early_buyer_share,
    SUM(CASE WHEN buyer_rank <= 10 THEN buyer_share ELSE 0 END) AS top10_early_buyer_share,
    SUM(POWER(buyer_share, 2)) AS early_buyer_hhi,
    MIN(first_trade_at) AS first_trade_at,
    MAX(last_early_trade_at) AS last_early_trade_at
FROM ranked
GROUP BY 1
ORDER BY mint;
