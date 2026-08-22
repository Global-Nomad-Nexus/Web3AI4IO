# application

application's application-arm code for the Pump.fun and PumpSwap study: market DiD ladder, mechanism checks, stakeholder metrics, and L0 through L7 prompts.

Generated result tables, figures, and benchmark CSVs stay in the local working copy and are not part of this GitHub tree. The unified four-chain dataset is published on Hugging Face as [kl41r3/web3ai4io-multichain-launchpad](https://huggingface.co/datasets/kl41r3/web3ai4io-multichain-launchpad).

## Layout

```text
application/
  configs/                     Case configuration
  data_sources/                Dune SQL templates and compact public-data notes
  prompts/                     L0-L7 agentic-evaluation prompts
  scripts/                     Runners for analysis, validation, and release rebuild
  src/trustworthy_launchpads/  Analysis modules
  tests/                       Integrity tests (skip when local tables are absent)
  benchmark_release/           Schema and dataset-card text, without generated sheets
```

## Reproduce

```text
cd application
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests
```

To rebuild local artifacts from a full data checkout, point `configs/pumpswap_case.json` at that checkout and run `scripts/run_all.py`. See `DATA_LICENSE.md` for data licensing and `benchmark_release/SCHEMA_CONTRACT.md` for the release sheet contract.
