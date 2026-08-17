# Web3AI4IO

Code and schemas for the Web3AI4IO multi-chain launchpad dataset and the paper's evaluation workflows.

The public data release is the Hugging Face dataset [kl41r3/web3ai4io-multichain-launchpad](https://huggingface.co/datasets/kl41r3/web3ai4io-multichain-launchpad). This GitHub repository does not host bulk tables, source JSONL files, or experiment artifacts.

## Layout

* `data_pipeline/` builds and validates the unified four-chain release, including the project-level event layer.
* `Claire/` contains Claire's analysis code, data-expansion provenance scripts, and S1 through S5 stress-test source.
* `Shilin/` contains Shilin's application-arm code, prompts, and tests.
* `data/` holds local immutable inputs and generated canonical tables. Those files are gitignored and published on Hugging Face.

Paper source lives outside this repository.

## Build and test the data pipeline

From the repository root:

```text
data_pipeline/.venv/bin/python data_pipeline/scripts/build_solana_core.py
data_pipeline/.venv/bin/python data_pipeline/scripts/build_crosschain_core.py
data_pipeline/.venv/bin/python data_pipeline/scripts/build_events.py
PYTHONPATH=data_pipeline/src data_pipeline/.venv/bin/python -m pytest data_pipeline/tests
```

Canonical Parquet output is written under `data/canonical/`. See `data_pipeline/README.md` for coverage semantics and `data_pipeline/SHILIN_LIMITATION.md` for the decoded-swap boundary.
