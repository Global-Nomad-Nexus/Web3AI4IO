-- Shilin H4 extension: holder concentration snapshots after graduation.
--
-- Required output schema:
-- mint, snapshot_horizon_days, holders, top1_holder_share, top10_holder_share,
-- holder_hhi, nakamoto_50_count
--
-- This query is intentionally a schema template because Solana token-balance
-- snapshot tables differ by Dune namespace and may require a paid/API context.

WITH tokens(mint, graduated_at) AS (
    VALUES
    -- ('MINT_ADDRESS', TIMESTAMP '2025-03-20 00:00:00 UTC')
),
horizons AS (
    SELECT 0 AS snapshot_horizon_days
    UNION ALL SELECT 7
    UNION ALL SELECT 30
),
balances AS (
    SELECT
        t.mint,
        h.snapshot_horizon_days,
        b.owner,
        b.amount AS token_balance
    FROM tokens t
    CROSS JOIN horizons h
    JOIN solana_utils.token_balances b
      ON b.token_mint_address = t.mint
     AND b.block_time <= t.graduated_at + h.snapshot_horizon_days * INTERVAL '1' day
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY t.mint, h.snapshot_horizon_days, b.owner
        ORDER BY b.block_time DESC
    ) = 1
),
shares AS (
    SELECT
        *,
        token_balance / NULLIF(SUM(token_balance) OVER (PARTITION BY mint, snapshot_horizon_days), 0) AS holder_share
    FROM balances
    WHERE token_balance > 0
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY mint, snapshot_horizon_days ORDER BY holder_share DESC) AS holder_rank,
        SUM(holder_share) OVER (
            PARTITION BY mint, snapshot_horizon_days
            ORDER BY holder_share DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_share
    FROM shares
)
SELECT
    mint,
    snapshot_horizon_days,
    COUNT(DISTINCT owner) AS holders,
    SUM(CASE WHEN holder_rank <= 1 THEN holder_share ELSE 0 END) AS top1_holder_share,
    SUM(CASE WHEN holder_rank <= 10 THEN holder_share ELSE 0 END) AS top10_holder_share,
    SUM(POWER(holder_share, 2)) AS holder_hhi,
    MIN(CASE WHEN cumulative_share >= 0.50 THEN holder_rank END) AS nakamoto_50_count
FROM ranked
GROUP BY 1, 2
ORDER BY mint, snapshot_horizon_days;
