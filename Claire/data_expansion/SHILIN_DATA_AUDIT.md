# Shilin Data Audit

## What is actually present

1. Solana market context has 724 daily platform rows from 2024 12 20 through 2025 06 18 across Pump.fun, Raydium, Orca, and Meteora.
2. The RED PUMP lifecycle summary reports 832,941 Pump.fun token launches from 2026 05 08 through 2026 06 10. The upstream token table is absent from this repository and from Claire's machine.
3. The graduated validation cohort has 1,651 Solana tokens. RPC proxy outcomes have 4,953 token horizon rows at 1, 7, and 30 days.
4. Moralis decoded outcomes have 294 tokens and 882 token horizon rows at 1, 7, and 30 days. The raw decoded swap table has 173,102 rows before deduplication and 57,743 unique decoded swaps.
5. Base has a committed 36,798 row Clanker `TokenCreated` scan between 2025 08 18 and 2025 09 06. Shilin reports a larger 61,080 launch discovery universe through 2025 10 01, but the larger raw table is absent.
6. The Base matched manifest has 13,880 tokens, split into 6,940 treated and 6,940 controls. It defines 41,640 expected rows at 1, 7, and 30 days. Only 12 tokens and 36 horizon rows currently contain computed outcomes.
7. The released combined metrics panel contains 6,630 rows, of which 6,594 are Solana and 36 are Base. Its time range is 2024 12 20 through 2026 06 10. This combined range mixes daily market rows and fixed token horizons and must not be described as one continuous panel.

## How offchain data was selected

1. Telegram is a launch metadata indicator from the RED PUMP source. The full source reportedly contains 20,270 Telegram present tokens and 812,671 Telegram absent tokens. Matching retained 20,227 Telegram present tokens and 586,581 controls using launch day, Twitter presence, website presence, initial market cap decile, and description bin.
2. This selection is not an exposure design. The same association appears within five minutes of launch, which points to preexisting project quality or promotion confounding.
3. In the released 1,651 graduated subset, 301 tokens have Telegram metadata. Git recovery identifies 301 raw URLs, 296 normalized token level handles, and 290 unique channels.
4. Discord, sentiment, TVL, and RWA rows are derived extensions linked by `event_id`. Their claimed upstream files are absent from Claire's machine. They should be treated as nonreproducible derived context until raw provenance is recovered.
5. The HuggingFace Pump.fun metadata source has 106,113 snapshots and 98,175 unique mints. It is a broader metadata and text source, not a time series of community activity.

## Main data defects

1. Several availability ledgers say upstream files are available because they existed on Shilin's original absolute path. They are not available in this checkout.
2. Empty CSV files for Dune trades, Dune early wallets, parsed transaction proxies, and early wallet concentration are schema placeholders, not observations.
3. Solana RPC fields named `active_traders` and `volume_usd` are zero or proxy values where transactions were not decoded. They cannot substitute for decoded outcomes.
4. Moralis coverage is selected by high RPC activity, differs materially from uncovered tokens, and is capped at two pages per token horizon.
5. Static Telegram presence and actual Telegram attention are different data generating processes and require separate schemas.
