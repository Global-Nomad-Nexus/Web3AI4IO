# Verified Bundle Inventory

## Integrity and reproducibility

1. The supplied SHA256 manifest lists 2,174 files. Every listed file passed verification before relocation.
2. The bundled `check_artifacts.py` completed successfully.
3. All 25 bundled unit tests passed using the local isolated Python environment.

## Solana baseline now available

1. Raw RED PUMP launches contain 860,213 rows and 860,194 unique mints from 2026 05 08 through 2026 06 10.
2. Raw RED PUMP outcomes contain 833,171 rows and known malformed CSV values documented by the source schema.
3. The cleaned lifecycle table contains 832,941 unique mints, including 831,290 timeouts and 1,651 graduations.
4. The Dune input table contains all 1,651 graduated mints with creation and graduation timestamps.
5. Solana RPC proxy coverage contains 4,953 rows for all 1,651 graduated tokens at 1, 7, and 30 day horizons.
6. Moralis raw swaps contain 173,102 rows for 294 tokens. Of 882 token horizon requests, 876 are marked `page_limit_reached_lower_bound` and only 6 are marked complete.
7. The Dune post migration export is empty.

## Base baseline now available

1. The delivered `TokenCreated` table contains 36,798 unique launches from 2025 08 18 through 2025 09 06.
2. The delivered file does not contain the reported 61,080 row discovery scan through 2025 10 01.
3. The matched manifest contains 13,880 unique tokens, split equally between 6,940 treated and 6,940 controls.
4. Computed horizon outcomes remain limited to 12 tokens and 36 rows.

## Offchain baseline now available

1. The cleaned RED PUMP table contains binary Telegram, Twitter, website, social count, description length, and launch metadata fields for 832,941 tokens.
2. The raw launch dataset contains 21,100 rows with `has_telegram=true`, while the cleaned matched lifecycle table supports the reported 20,270 Telegram present tokens after outcome cleaning and deduplication.
3. Full token level Telegram URLs or handles are not included in RED PUMP. Git recovered metadata supplies URLs only for 301 graduated tokens and 290 unique channels.
4. Discord sentiment contains 6,892 protocol day rows for seven protocols from 2019 through 2023.
5. The Discord and TVL extension contains 4,372 rows for five protocols from 2020 through 2023.
6. These Discord sources do not overlap the 2026 RED PUMP launch window and should remain contextual data rather than token linked community activity.

## Remaining core gaps

1. Full decoded Solana trading outcomes for the 1,651 graduated tokens.
2. Full Base launch discovery raw logs and complete 1, 7, and 30 day Swap and Transfer coverage for the 13,880 token manifest.
3. Four.meme on BNB Chain and SunPump on TRON have no core tables yet.
4. Actual timestamped offchain activity remains absent and should be collected only after the event registry identifies relevant channels and windows.
