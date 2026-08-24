# Web3AI4IO

Code, schemas, and the review reproducibility package for the Web3AI4IO launchpad study.

Bulk tables are not stored in this GitHub tree. During anonymous review the dataset is a withheld artifact. After de-anonymization the public copy is the Hugging Face dataset named in the camera-ready paper.

## Five-minute quick start

```text
uv sync --frozen
make reproduce
```

This installs the locked reviewer environment, regenerates empirical tables and figures from archived summaries, writes the artifact manifest and checksums, and checks manuscript numbers and archived model outputs. It does not re-query chain data or call a model API. See `REPRODUCIBILITY.md` and `DATA_CARD.md`.

| Command | Output |
|---|---|
| `make reproduce` | archived summaries, tables, figures, checksums, tests |
| `make figures` | empirical charts in `../paper/figs` |
| `make tables` | `paper/tabs/tab_data_scope.tex` and `tab_claim_evidence.tex` |
| `make paper` | compile the anonymous manuscript |
| `make verify` | files, checksums, sample counts, identity scan |
| `make all` | reproduce then compile |

## Layout

* `reproduction/` Role B control plane: shared theme, archived summaries, generated tables, `generate_figures.py`, manifest, tests
* `data_pipeline/` builders, schemas, event layer, and release manifests
* `Claire/` identification-arm analysis, S1 through S5 source, and experiment figure scripts
* `Shilin/` application-arm analysis, `src/trustworthy_launchpads/plots.py`, prompts, and tests
* `data/` local immutable inputs and generated canonical tables (gitignored)

Paper source lives at `../paper/` and is not part of this repository.

## Data pipeline

From the repository root, with local source bundles present:

```text
data_pipeline/.venv/bin/python data_pipeline/scripts/build_solana_core.py
data_pipeline/.venv/bin/python data_pipeline/scripts/build_crosschain_core.py
data_pipeline/.venv/bin/python data_pipeline/scripts/build_events.py
PYTHONPATH=data_pipeline/src data_pipeline/.venv/bin/python -m pytest data_pipeline/tests
```

Canonical Parquet output is written under `data/canonical/`. See `data_pipeline/README.md` for coverage semantics.
