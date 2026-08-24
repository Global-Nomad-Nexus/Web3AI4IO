# Pump.fun creator fee activation evidence

Status: activation timing verified, comparison design not yet accepted, 2026-08-02

The Pump.fun creator-fee event became economically active on 2025-05-13 at approximately 11:27:06 UTC. The May 12 date in the rollout document marks a support upgrade, not the first verified positive creator-fee payment.

The first public commit adding the creator-fee documentation was `e2b66e4fce2fc130955912315167dc41e56956ad` at 2025-05-08 15:49:08 UTC. The registered anticipation window is therefore five calendar days. Observations from May 8 through activation are excluded from clean pre-period comparisons rather than treated as evidence of no anticipation.

The first-party rollout document states that creator-fee support would deploy on May 12, 2025 at 11:00 UTC and identifies Pump program `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`. Its IDL defines the Global PDA from seed `global`, the `creator_fee_basis_points` field, and the creator vault passed to buy and sell instructions. The derived Global PDA is `4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf`. The upgradeable program points to ProgramData account `B5MvUwXdiW1NMM6QFFD3ssPKBujD4zMohncbM73Z2BQu`.

Solana finalized RPC records program upgrade `3stKU43sVghcQLcqRuJC5q5KEWv3Fhps9o3HpUpkjCurnXJQA5BbUJdpqjwopL8od94JbchyrmhYmvmUEM4DKmq7` at slot 339514928, 2025-05-12 11:26:54 UTC. A successful sell seven minutes later, `4LaTdtwcr8VB1A4ECFUBnRuVyDy9qQkjJYCUxJep5KdhkyqngXWTZmun2aa8kg92Cg1BJ5EbxWviGXjkhZaqmjtQ`, passed a creator vault but changed its lamport balance by zero. This shows that program support alone did not establish a positive creator subsidy.

Solana finalized RPC records a second program upgrade, `4NK8jLTKV6rwPTLsNWHejfbJrnYuJERp3z3sJGhzuPzezVvp4e7FCz4BKAnnomdJFVqNgVNQMz67P6NBdgNNYvGm`, at slot 339733401, 2025-05-13 11:27:06 UTC. In the next block at the same recorded second, transaction `5rj8FxQ8z2aTnwCiFgXxZTkveSiSUjm7nBnBcadiZg9LacP3XjkFjxjxssMw27FAZ9S5YUfpgDGRzFuLhqWLGAzs` executed Pump buy and sell instructions and increased the sell-side creator vault by 10,732 lamports. Later verified sell `3tKA31gUXkN2cQb4JLD7wNUAUqVKZDY45Zoq8j7bQMkYuNmhcPkuGSrtvNAf1b9BEqaQUSokfGcmnqmj7adXviFu` increased its creator vault by 216,573 lamports. These balance deltas independently verify economic activation.

Sources and method:

1. First-party rollout: https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_CREATOR_FEE_README.md
2. First-party IDL: https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump.json
3. First public documentation commit: https://github.com/pump-fun/pump-public-docs/commit/e2b66e4fce2fc130955912315167dc41e56956ad
4. Solana finalized JSON RPC methods: `getAccountInfo`, `getSignaturesForAddress`, `getTransaction`, and `getBlock` against `https://api.mainnet-beta.solana.com`.
5. PDA derivation used the IDL seed and Pump program address. Transaction validation matched the Pump instruction discriminator and compared the creator-vault entry in `preBalances` and `postBalances`.

This evidence accepts the activation time only. It does not establish parallel trends, a valid comparison platform, a common outcome schema, or a causal effect.
