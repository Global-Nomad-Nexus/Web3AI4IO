# Base Clanker Pool Core Source

This source enriches the fixed 62,618 row Clanker launch universe. It does not repeat the TokenCreated scan.

The collector queries the Base Uniswap v4 PoolManager only for pool IDs and launch transactions already present in the launch universe. It retains `Initialize` and launch transaction `ModifyLiquidity` events. It excludes Swap, Transfer, holder, and trading outcome data.

The raw checkpointed snapshot is stored under `snapshot/` and excluded from Git. The tracked source metadata records its contract, topics, exact scope, exclusions, row count, and SHA256 digest after collection.
