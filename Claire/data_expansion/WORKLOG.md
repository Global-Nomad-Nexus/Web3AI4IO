# Data Expansion Worklog

## 2026 08 10

1. Created branch `claire/date-expansion-v1` from `origin/main`.
2. Confirmed macOS ARM64, Python 3.13, `uv 0.7.19`, and 159 GiB available disk space.
3. Created isolated environment `Shilin/.venv` and installed the existing Shilin package and dependencies.
4. Confirmed that the current shell exposes no Dune, Moralis, Helius, Bitquery, Telegram, or Base archive credential variable names.
5. Searched Claire's home directory for the missing RED PUMP, market, Discord, TVL, and RWA processed files. No copies were found.
6. Confirmed scope is data acquisition, provenance, schema, and quality control only. No Difference in Differences analysis will be run.
7. Recovered 1,651 Pump.fun metadata JSON records from Git commit `783c911` without restoring deleted files into the working tree.
8. Extracted 301 nonempty Telegram URLs and 296 normalized public handles. The handle coverage is 17.93 percent of the graduated cohort.
9. Verified that `https://mainnet.base.org` returns the known historical Clanker `TokenCreated` log at block 34,725,785.
10. Verified a 10,000 block Base query returning 586 `TokenCreated` logs from the official public endpoint.
11. Ran a 24 control token, one day Base pilot. It returned 72 ERC20 Transfer rows and no PoolManager Swap rows.
12. Ran a one treated token, one day Base pilot. It returned 10 ERC20 Transfer rows and 4 PoolManager Swap rows.
13. Found that Shilin's Base scripts import `requests` without declaring it in either dependency file. Installed it only in the isolated environment for the pilot.
14. Stopped an inefficient 24 treated token pilot after confirming that batching tokens spread across a month expands the query span to roughly 1.29 million blocks.
15. Prepared a DeepSeek V4 Flash manifest review with no fallback, but did not send internal files because external data transfer approval was not explicit enough for the safety gate.
16. Resolved 296 eligible token level Telegram handles to 290 unique channels and wrote a collection frame that preserves the many tokens to one channel mapping.
17. Added the missing `requests` runtime dependency to Shilin's declared environment.
18. Added a 25,000 block default launch locality limit to the Base backfill batcher and verified that distant launches split into separate batches.
19. Extended the treated Base one day pilot to six tokens. It now contains 20 Swap rows and 54 Transfer rows, with five of six tokens showing observed Swap activity.
20. Received the 1.0 GB Shilin reproducibility bundle and verified all 2,174 supplied SHA256 entries.
21. Moved the immutable bundle from Downloads to `data/external/shilin/20260810/bundle` without changing its internal relative layout.
22. Ran the bundled artifact checker and all 25 unit tests successfully.
23. Audited the delivered raw and processed tables. The bundle closes the RED PUMP and upstream offchain provenance gaps but does not close decoded Solana or full Base outcome coverage.
24. Sent only compact audit metadata to `deepseek-v4-flash` under the approved scope. The successful review used the requested model with fallback disabled.
25. Created an independent Python 3.11 dataset build environment with `uv`, PyArrow, DuckDB, and pytest.
26. Rebuilt the RED PUMP baseline directly from the raw gzip sources into typed Parquet tables.
27. Reproduced exactly 832,941 terminal token outcomes, including 1,651 graduated and 831,290 timeout tokens.
28. Compared all 832,941 canonical mint and outcome pairs against Shilin's processed baseline with zero mismatches.
29. Built eight Solana canonical tables covering tokens, launches, lifecycle events, graduated metadata, pool proxy windows, delivered decoded swaps, horizon summaries, and per token coverage.
30. Preserved 173,102 delivered decoded swap rows for 294 tokens as lower bounds. No row with a page cap is labelled as a complete observation window.
31. Added versioned schemas, a source registry, exact source and output SHA256 digests, a release manifest, and automated acceptance tests.
32. Passed all four Solana release tests and `git diff --check`.
33. Probed the current Pump.fun historical trade endpoint and received a retired endpoint response. Current documentation requires JWT authentication.
34. Confirmed that the Moralis token swap endpoint requires an API key and cursor pagination. No configured Moralis, Helius, Dune, or BigQuery credential is available in the current environment.
35. Evaluated the newly published Pumpfun Memecoin Corpus. Its stated data period begins on 2026 06 09, so it cannot fill the RED PUMP cohort beginning on 2026 05 08.
36. Accepted the Moralis pagination limitation and ended further decoded Solana swap acquisition.
37. Classified Shilin's delivered decoded swap snapshot as validation data only and documented its permitted and prohibited uses in `data_pipeline/SHILIN_LIMITATION.md`.
38. Extended the official Base public RPC scan to the complete declared 2025 08 18 through 2025 10 01 UTC window and decoded 62,618 unique Clanker TokenCreated events.
39. Built the Base canonical launch core with tokens, launches, metadata placeholders, state snapshot placeholders, and per token coverage evidence.
40. Collected 1,000 Four.meme records and 1,000 SunPump records from their official public APIs.
41. Verified that both official list APIs stop after 1,000 rows and classified both snapshots as metadata validation only.
42. Added a common crosschain schema and deterministic builders for Base, BNB Chain, and TRON.
43. Preserved the no decoded swaps policy for every newly added chain.
44. Reopened Phase 3 because the launch table alone did not satisfy the Base canonical core requirement.
45. Treated the existing 62,618 Clanker TokenCreated rows as a fixed universe and did not repeat launch acquisition.
46. Queried only Uniswap v4 PoolManager Initialize and ModifyLiquidity topics for those fixed pool IDs and original launch transactions.
47. Collected 219,303 Base pool core events: 62,618 pool initializations and 156,685 initial liquidity position modifications.
48. Verified one unique Initialize event and at least one positive initial liquidity event for all 62,618 pools, with zero transaction, block, hook, or currency pair mismatches.
49. Corrected the canonical distinction between a Uniswap v4 `pool_id` and a pool contract address.
50. Added protocol configuration, pools, liquidity initialization, and lifecycle event canonical tables.
51. Added explicit `observed`, `processed_zero_rows`, `not_collected`, `not_applicable`, and `not_collected_by_policy` coverage semantics.
52. Split 156,685 launch transaction ModifyLiquidity events into 149,921 positive initial liquidity additions and 6,764 zero delta liquidity position pokes.
53. Reclassified the two 1,000 row official API snapshots as metadata enrichment subsets only rather than launch universe sources.
54. Scanned the Four.meme TokenManager contracts through BNB Chain archive RPC to the recorded snapshot block and collected 1,593,679 unique `TokenCreate` events: 5,570 V1 and 1,588,109 V2.
55. Collected 106 Four.meme V1 `TradeStop` and 15,403 V2 `LiquidityAdded` lifecycle events without collecting purchase, sale, transfer, decoded trading, swap, or holder data.
56. Scanned the SunPump contract through TronGrid fingerprint pagination to exhaustion and collected 104,548 `TokenCreate`, 1,831 `TokenLaunched`, and one `NewImplementation` event.
57. Kept receipt enrichment and Phase 4 canonical construction open until their integrity checks and acceptance tests finished.
58. Completed SunPump receipt enrichment for all 104,548 TokenCreate, 1,831 TokenLaunched, and one NewImplementation records with no duplicate event identities.
59. Completed Four.meme receipt enrichment for 15,403 LiquidityAdded events across Pancake V2 and V3, including 701 archive verified historical pool initialization events.
60. Built canonical releases with 1,593,679 BNB launches and 104,548 TRON launches. Official API rows remain metadata subsets only.
61. Passed all 14 crosschain and Solana release tests and generated the compact Phase 4 integrity summary with accepted=true.
