# Reproducibility

This package reproduces the empirical tables, charts, checksums, and manuscript number checks from archived summaries. It does not re-run the Monte Carlo experiments or call a model API.

## Hardware and runtime

- Language: Python 3.11 or newer
- Extra packages: `reproduction/requirements.txt`
- Expected runtime for `make reproduce`: under five minutes on a laptop
- Full S1 through S5 Monte Carlo reruns are optional, take hours to days, and are not required to regenerate the paper artifacts

## Five-minute path

```text
uv sync --frozen
make reproduce
```

`make reproduce` archives identity-stripped summaries and 80 raw model responses, regenerates empirical LaTeX tables, regenerates empirical figures into `paper/figs` in the review mirror or `../paper/figs` in the private workspace, writes `reproduction/artifact_manifest.csv` and `reproduction/checksums.sha256`, traces manuscript numbers, and runs the statistic tests.

## Commands

| Command | What it does |
|---|---|
| `make archive` | Copy and redact summary artifacts into `reproduction/archived/` |
| `make tables` | Generate `tab_data_scope.tex` and `tab_claim_evidence.tex` from archived files |
| `make figures` | Regenerate empirical PDF/PNG figures with the shared theme |
| `make verify` | Checksums, sample counts, manuscript tokens, identity scan, unit tests |
| `make paper` | Compile `paper/neurips_2026.tex` in the mirror or the adjacent private paper tree |
| `make all` | `reproduce` then `paper` |

## Data

Canonical tables live on the withheld review dataset during anonymous submission and on Hugging Face after de-anonymization. Local processed snapshots, when present, are under `data/canonical/v1/` and are listed with SHA-256 digests in `data_pipeline/releases/v1/` and `data_pipeline/huggingface/release_manifest.json`.

Acquisition of raw chain data requires RPC and API credentials and is not part of `make reproduce`. See `DATA_CARD.md`.

## AI evaluation

Archived objects:

- `reproduction/archived/application/prompts/`
- `reproduction/archived/application/agent_runs.csv`
- `reproduction/archived/application/agentic_arm_scores.csv`
- `reproduction/archived/application/agentic_prompt_manifest.csv`
- `reproduction/archived/application/raw_responses/` with 80 verbatim API response objects
- `reproduction/archived/application/agent_provenance.json`

The requests used the `deepseek-chat` alias, temperature 0, and ten runs per rung. Every archived API response identifies the returned model as `deepseek-v4-flash`. The current prompt templates do not reconstruct the scored runtime payload hashes, and the exact runtime payload was not archived. Raw outputs and scores can be audited without API credentials, but the original request payloads cannot be independently repeated.

## Known-truth experiments

S1 through S5 source, locks, and tests remain under `Claire/experiments/`. Headline summaries used by the paper are archived under `reproduction/archived/calibration/`. Optional full reruns:

```text
Claire/experiments/s1_staggered/run_mc.py
Claire/experiments/s2_timing/src/s2_timing/run_mc.py
Claire/experiments/s3_few_clusters/src/run_experiment.py
Claire/experiments/s4_endogenous/src/s4_endogenous/run_mc.py
Claire/experiments/s5_aggregation/src/s5agg/runner.py
```

S4 also requires the local R library, which is not part of the anonymous package.

## Validity boundary

Reproduction from archived summaries confirms that reported tables, charts, and manuscript numbers match the stored artifacts. It does not re-estimate the observational designs or re-query chain data.
