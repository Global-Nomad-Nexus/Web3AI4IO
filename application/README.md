# Application

Pump.fun and PumpSwap application code: market DiD ladder, mechanism checks, stakeholder metrics, and L0–L7 prompts.

Generated tables, figures, and benchmark CSVs stay local and are not part of this Git tree. The four-chain dataset is `kl41r3/web3ai4io-multichain-launchpad` on Hugging Face.

## Layout

```text
application/
  configs/                     Case configuration
  data_sources/                Dune SQL templates and compact public-data notes
  prompts/                     L0–L7 evaluation prompts
  scripts/                     Analysis, validation, and release rebuild
  src/trustworthy_launchpads/  Analysis modules, including plots.py
  tests/                       Integrity tests (skip when local tables are absent)
  benchmark_release/           Schema and dataset-card text
```

## Tests

```text
cd application
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests
```

To rebuild local artifacts from a full data checkout, point `configs/pumpswap_case.json` at that checkout and run `scripts/run_all.py`.
