# Claire

Claire's code for the Web3AI4IO project. Bulk data stay on Hugging Face. Internal Chinese plans and reports stay in the local workspace archive and are not part of this tree.

## Contents

* `src/web3io_claire/` rule-event analysis, registry helpers, and deterministic ladder checks
* `queries/` Dune SQL used to build the Pump and Moonshot diagnostic panel
* `schemas/` platform-day and token-cohort contracts
* `data_expansion/scripts/` coverage and source-bundle audits
* `experiments/s1_staggered` through `experiments/s5_aggregation` known-truth stress-test source
* `scripts/make_main_paper_figures.py` main-text figure export

Each stress test keeps `src/`, `tests/`, `design_lock.yaml`, `METHOD.md`, `RESULTS.md`, and `VALIDATION.md`. Generated `artifacts/` directories, local virtual environments, and the S4 R library are not committed.

## Run the rule-event checks

```text
PYTHONPATH=src python3 -m web3io_claire.analyze_h0
PYTHONPATH=src python3 -m web3io_claire.analyze_h3
PYTHONPATH=src python3 -m web3io_claire.crosscheck_ladder
PYTHONPATH=src python3 -m unittest discover -s tests
```

The accepted Pump and Moonshot extract is `data/pump_moonshot_cohort_panel.csv`, produced by `queries/03_pump_moonshot_cohort_panel.sql`.
