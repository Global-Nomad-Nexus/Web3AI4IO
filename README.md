# Web3AI4IO

This repository is the active implementation and data workspace for the Web3AI4IO project.

## Repository structure

* `Claire/` contains Claire's research contribution, audits, and data expansion provenance.
* `Shilin/` contains Shilin's research contribution and delivered artifacts.
* `data/` contains the unified project data. Immutable inputs live in `data/external/`, and generated normalized tables live in `data/canonical/`.
* `data_pipeline/` contains the code, schemas, tests, and release manifests that build and publish the unified data.

`data_pipeline/` is project level infrastructure implemented by Claire. It integrates Shilin supplied source data and constructs the unified Web3AI4IO release. Its repository root placement indicates project scope, not joint code authorship.

The active paper source is maintained outside this Git repository under the workspace level `manuscript/` directory.
