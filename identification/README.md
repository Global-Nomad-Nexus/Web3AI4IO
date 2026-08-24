# Identification

Event registry, activation-evidence checks, and five known-truth experiments (S1–S5).

Bulk data stay on Hugging Face. Generated experiment `artifacts/` directories are not committed.

## Contents

* `src/web3ai4io_identification/` rule-event analysis and registry helpers
* `queries/` Dune SQL for the Pump and Moonshot diagnostic panel
* `schemas/` platform-day and token-cohort contracts
* `experiments/s1_staggered` through `experiments/s5_aggregation` calibrated experiment source
* `scripts/make_main_paper_figures.py` legacy figure entry; canonical generation is `reproduction/generate_figures.py`

Each experiment keeps `src/`, `tests/`, `design_lock.yaml`, `METHOD.md`, `RESULTS.md`, and `VALIDATION.md`.

## Run the rule-event checks

```text
PYTHONPATH=src python3 -m web3ai4io_identification.analyze_h0
PYTHONPATH=src python3 -m web3ai4io_identification.analyze_h3
PYTHONPATH=src python3 -m web3ai4io_identification.crosscheck_ladder
PYTHONPATH=src python3 -m unittest discover -s tests
```
