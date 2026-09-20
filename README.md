<div align="center">

# Web3AI4IO

### Trustworthy AI and Causal Inference for Token Launch Platforms

<p>
  <a href="docs/publications/web3ai4io-paper-neurips2026.pdf"><img alt="Read the paper" src="https://img.shields.io/badge/Paper-PDF-8B1E3F?style=for-the-badge"></a>
  <a href="docs/publications/README.md"><img alt="Publication archive" src="https://img.shields.io/badge/Publication_Archive-Details-4B5563?style=for-the-badge"></a>
  <a href="https://huggingface.co/datasets/kl41r3/web3ai4io-multichain-launchpad"><img alt="Hugging Face dataset" src="https://img.shields.io/badge/Dataset-Hugging_Face-FFD21E?style=for-the-badge"></a>
</p>

<p>
  <a href="#research-overview">Overview</a> ·
  <a href="#research-output">Paper</a> ·
  <a href="#reproducibility">Reproducibility</a> ·
  <a href="#repository-structure">Repository</a>
</p>

</div>

---

## Research overview

Web3AI4IO is a provenance-aware research artifact for studying token launch platforms across heterogeneous blockchain ecosystems. It combines four-chain dataset construction, entity and event identification checks, empirical applications, calibrated experiments, and manuscript-artifact verification under a shared evidence contract.

The repository preserves chain-specific evidence boundaries instead of treating Solana, Base, BNB Chain, and TRON data as directly interchangeable. Bulk tables are hosted separately on Hugging Face to keep the Git repository focused on schemas, code, compact summaries, and reproducibility materials.

## Research output

| Output | Description | Access |
|---|---|:---:|
| Manuscript | *Trustworthy AI and Causal Inference for Token Launch Platforms: Evidence, Stakeholders, and Market Design* | [PDF](docs/publications/web3ai4io-paper-neurips2026.pdf) |
| Publication archive | Compilation notes and manuscript provenance | [Open](docs/publications/README.md) |
| Public dataset | `kl41r3/web3ai4io-multichain-launchpad` | [Hugging Face](https://huggingface.co/datasets/kl41r3/web3ai4io-multichain-launchpad) |

## Reproducibility

```text
uv sync --frozen
make reproduce
```

This regenerates empirical tables and figures from archived summaries, writes the artifact manifest and checksums, and checks manuscript numbers. It does not re-query chain data or call a model API.

| Command | Output |
|---|---|
| `make reproduce` | Archived summaries, tables, figures, checksums, and tests |
| `make figures` | Empirical charts in `../paper/figs` |
| `make tables` | `tab_data_scope.tex` and `tab_claim_evidence.tex` |
| `make paper` | Compile the adjacent manuscript |
| `make verify` | Check files, checksums, sample counts, and identity controls |
| `make all` | Reproduce the artifact, then compile the manuscript |

See [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) and [`DATA_CARD.md`](DATA_CARD.md) for the full protocol.

## Repository structure

```text
dataset/           builders, schemas, event layer, release manifests
identification/    event registry, design checks, S1–S5 experiments
application/       PumpSwap applications, prompts, and plots
reproduction/      paper tables, figures, manifest, and tests
data/              local source pointers; generated tables are gitignored
docs/publications/ compiled manuscript and publication notes
```

With local source bundles present, rebuild the canonical dataset with:

```text
dataset/.venv/bin/python dataset/scripts/build_solana_core.py
dataset/.venv/bin/python dataset/scripts/build_crosschain_core.py
dataset/.venv/bin/python dataset/scripts/build_events.py
PYTHONPATH=dataset/src dataset/.venv/bin/python -m pytest dataset/tests
```

Canonical Parquet output is written under `data/canonical/`. See [`dataset/README.md`](dataset/README.md) for the schema and build details.
