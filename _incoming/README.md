# Union incoming overlay

This directory is the scavenger overlay created before cleanup.

- `LIVE_ADD` files were copied into the live Role B tree.
- `CONFLICT_KEEP_ROLEB` files differ from Role B; Role B remains live, the other copy is here.
- `anonymous/` is the identity-neutral review tree with `paper/` removed.
- `role-b-current/` snapshots Role B Shilin source that later cleanup may replace with h4 supersets.

Paper source is excluded by decision: it remains in its own repository outside this Git tree.
