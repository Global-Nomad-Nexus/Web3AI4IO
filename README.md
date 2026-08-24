# Web3AI4IO

Code and schemas for a provenance-aware launchpad study: four-chain dataset construction, identification checks, real applications, calibrated experiments, and paper-artifact reproduction.

Bulk tables are not stored in this Git tree. The public dataset is `kl41r3/web3ai4io-multichain-launchpad` on Hugging Face.

## Quick start

```text
uv sync --frozen
make reproduce
```

This regenerates empirical tables and figures from archived summaries, writes the artifact manifest and checksums, and checks manuscript numbers. It does not re-query chain data or call a model API.

| Command | Output |
|---|---|
| `make reproduce` | archived summaries, tables, figures, checksums, tests |
| `make figures` | empirical charts in `../paper/figs` |
| `make tables` | `tab_data_scope.tex` and `tab_claim_evidence.tex` |
| `make paper` | compile the adjacent manuscript |
| `make verify` | files, checksums, sample counts, identity scan |
| `make all` | reproduce then compile |

See `REPRODUCIBILITY.md` and `DATA_CARD.md`.

## Layout

```text
dataset/           builders, schemas, event layer, release manifests
identification/    event registry, design checks, S1–S5 experiments
application/       PumpSwap applications, prompts, and plots
reproduction/      paper tables, figures, manifest, and tests
data/              local source pointers; generated tables are gitignored
```

Paper source lives at `../paper/` and is not part of this repository.

## Dataset build

With local source bundles present:

```text
dataset/.venv/bin/python dataset/scripts/build_solana_core.py
dataset/.venv/bin/python dataset/scripts/build_crosschain_core.py
dataset/.venv/bin/python dataset/scripts/build_events.py
PYTHONPATH=dataset/src dataset/.venv/bin/python -m pytest dataset/tests
```

Canonical Parquet output is written under `data/canonical/`. See `dataset/README.md`.
