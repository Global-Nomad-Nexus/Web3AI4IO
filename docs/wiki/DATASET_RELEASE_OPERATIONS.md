# Dataset Release Operations

This page records internal publication decisions and operational checks. It is not part of the public research report.

## Branch decision

`joint/benchmark-v2` is abandoned. Its six branch only commits belong to an earlier benchmark and semi synthetic direction that is no longer the active release path. The branch should be deleted locally and remotely after the current work is committed and pushed on `claire/date-expansion-v1`.

The active release branch is `claire/date-expansion-v1`, based on `origin/main`.

## Git publication boundary

Git contains code, tests, schemas, manifests, acceptance records, public reports, compact audit summaries, and small provenance metadata. Bulk JSONL, Parquet, immutable source bundles, raw snapshots, and generated canonical tables are excluded.

Never use an unchecked `git add .`. Before staging, confirm that no file larger than 10 MB is newly added unless explicitly approved.

The tracked Base Clanker launch CSV is historical repository content. Its expanded working copy belongs in the unified dataset release rather than the new Git commit. The Git builder should reference the external dataset copy or a local resolved data path before staging.

## Unified Hugging Face dataset

The Hugging Face dataset is one overall Web3AI4IO dataset. It should not create a separately branded Shilin dataset. The unified onchain and canonical data include Solana, Base, BNB Chain, and TRON.

The first data release should include:

1. Versioned canonical tables for all four chains.
2. Onchain source inputs required to reproduce the canonical releases.
3. Source manifests, schema registries, SHA256 values, and coverage ledgers.
4. The supplied onchain Solana data used by the canonical build.

Offchain event packs, social channel collections, experiment specific offchain data, and local pilot raw data remain unpublished and unchanged.

The dataset repository must have a dataset card, license decision, version or revision tag, file manifest, and Git commit reference. After upload, Git release manifests should record the Hugging Face repository, immutable revision, paths, and hashes.

## Internal validation

The final local suite passed 14 tests. The compact Phase 4 audit reconciles row counts, table hashes, identity uniqueness, foreign keys, coverage states, metadata subset semantics, and excluded table checks.

An additional compact review was sent to the explicitly requested `deepseek-v4-flash` model with fallback disabled. The review input was limited to release manifests, onchain source summaries, and the compact integrity artifact. The returned model matched exactly and the final review recorded `acceptance=true`. This model review is supplementary and does not replace the deterministic tests.

## Credentials and remote actions

GitHub uses the configured `origin` SSH remote. Hugging Face CLI authentication is not currently configured in the workspace. The user may need to create or provide access to a Hugging Face account and approve the dataset repository name, visibility, and license.

Remote deletion of `joint/benchmark-v2`, creation of the Hugging Face repository, bulk upload, Git commit, and Git push are material external actions and should be verified immediately after execution.
