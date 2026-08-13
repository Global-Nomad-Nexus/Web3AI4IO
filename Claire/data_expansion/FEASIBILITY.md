# Phase 1 Data Feasibility

This memo covers collection only. It does not authorize or run causal estimation.

## Solana decoded outcomes

1. Target is 1,651 graduated Pump.fun tokens at 1, 7, and 30 day fixed horizons.
2. Shilin has proxy coverage for all 1,651 tokens, but those rows are transaction count proxies rather than decoded USD volume or wallet outcomes.
3. Moralis covers 294 tokens and 882 token horizon rows. The collection used 29,400 compute units, selected tokens by high RPC activity, limited each token horizon to two pages, and stopped at its declared budget. This is a selected and potentially truncated sample.
4. A simple continuation for the remaining 1,357 tokens, three horizons, and at most two pages would require about 407,100 compute units if every request costs 50 units. More pages would increase the requirement. Moralis documents 50 compute units for the relevant Solana token swap endpoint and a current free allowance on its pricing pages. [Moralis Data API pricing](https://docs.moralis.com/data-api/pricing) [Moralis plans](https://developers.moralis.com/pricing/)
5. Helius documents 50 credits for `getTransactionsForAddress`. Shilin already scanned about 19.48 million signatures. Even the optimistic 1,000 signatures per response lower bound is about 974,100 credits before transaction parsing. Helius currently documents a one million credit free plan, so a complete decoded reconstruction has almost no safety margin. [Helius credit costs](https://www.helius.dev/docs/billing/credits) [Helius pricing](https://www.helius.dev/pricing)
6. Dune has a registered full cohort query path but no completed export. The current free plan documents 2,500 monthly credits and usage based execution pricing. Actual cost requires a bounded query pilot with an API key. [Dune billing](https://docs.dune.com/api-reference/overview/billing) [Dune credits](https://docs.dune.com/resources/credits-billing/how-credits-work)
7. Final decision: do not claim complete decoded Solana coverage. Preserve Shilin's decoded snapshot as validation data only and do not continue decoded swap collection.

## Telegram activity

1. Git history contains complete launch metadata for the 1,651 graduated validation tokens.
2. Among them, 301 records contain a Telegram value and 296 normalize to a public handle. These map to 290 unique channels because some handles are reused across tokens. This defines the eligible graduated token frame. It does not represent the full 832,941 launch universe.
3. Shilin's released `telegram_present` field is static self reported metadata. It is not message volume, views, membership, sentiment, or exposure timing.
4. Telegram documents that `messages.getHistory` is available to user accounts and not bots. Access also depends on channel visibility and account permissions. [Telegram messages.getHistory](https://core.telegram.org/method/messages.getHistory) [Telegram channels](https://core.telegram.org/api/channel)
5. Decision: collect actual activity only for public channels with explicit provenance. Required raw fields are channel handle, message id, timestamp, views when exposed, forwards when exposed, replies when exposed, edit timestamp, and collection status. Private groups, deleted channels, invite only links, user identities, and message bodies are excluded from the default dataset.
6. Blocker: MTProto application credentials and a user session are not configured. A web preview collector could only be a bounded availability pilot because it is not a stable complete history interface.

## Base Clanker

1. The launch universe is fixed at 62,618 unique Clanker TokenCreated rows covering 2025 08 18 through 2025 10 01 UTC.
2. Launch acquisition is closed and was not repeated during canonical core enrichment.
3. The official Base public endpoint supplied PoolManager Initialize and launch transaction ModifyLiquidity events for the fixed pool IDs.
4. All 62,618 pools have exactly one observed Initialize event and at least one positive initial liquidity addition.
5. The raw core snapshot contains 219,303 events: 62,618 Initialize and 156,685 ModifyLiquidity rows.
6. Of the ModifyLiquidity rows, 149,921 have positive liquidity delta and 6,764 are zero delta position pokes. No negative delta appears in a launch transaction.
7. Transaction, block, hook, and currency pair reconciliation has zero mismatches.
8. Swap, Transfer, holder, and trading outcome acquisition is closed by policy and is not part of Phase 3.

## Paid action gate

No paid bulk collection has started. Any paid run must state provider, exact endpoint, target rows, page cap, request cap, estimated units, estimated monetary cost, stop condition, and reusable raw artifact path before execution.
