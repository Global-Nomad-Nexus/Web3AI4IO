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

## V2 three-model evidence audit

The V2 audit is additive: it leaves the legacy prompts/results and the five Monte
Carlo stress tests unchanged. It compares GPT-5.6 Terra, DeepSeek-V4-Pro, and a
local `qwen3:14b` model using blind cumulative M0--M7 evidence blocks, a complete
2^4 L4--L7 factorial design, and positive/negative leakage controls.

Never paste API keys into source files or command arguments. Revoke any key that
has appeared in a chat or log, then expose replacement credentials only through
`OPENAI_API_KEY` and `DEEPSEEK_API_KEY` in the process environment.
An OpenAI-compatible institutional gateway can be selected at runtime with
`OPENAI_BASE_URL`; the adapter requires HTTPS and appends `/v1/responses` when
the supplied value is only a host/base URL. The repository retains the official
OpenAI endpoint as its default and never stores the gateway credential.

```text
make agentic-v2-dry-run   # registers exactly 714 calls; contacts no provider
make agentic-v2-smoke     # one local Qwen cell
make agentic-v2-run       # resumable registered run; paid API calls
make agentic-v2-score
make agentic-v2-verify
make agentic-v2-all       # tests -> resumable full run -> score -> verify
```

`make agentic-v2-all` prints a registry snapshot every 30 seconds. It is safe to
interrupt and run again: completed `ok` calls are retained, while an interrupted
`running` cell is retried. On macOS it can read missing provider variables from
`launchctl` or macOS Keychain without printing their values. Configure Keychain
once with `make agentic-v2-configure`; remove all stored V2 credentials with
`make agentic-v2-clear-credentials` (both Keychain and `launchctl`).

Runtime requests and responses are stored below `artifacts/agentic_v2/`, which is
git-ignored. `make reproduce` never invokes the V2 providers.

The registered Ollama context is 8,192 tokens. The longest current prompt plus
the full 2,400-token generation budget fits inside that window, while remaining
feasible on the 16 GB reference machine used for the local smoke test. The
`qwen3:14b` digest is checked before every executed batch.

DeepSeek-V4-Pro uses a 12,000-token ceiling because high-thinking tokens and the
final JSON share `max_tokens`. Its archived `estimated_cost_usd` is deliberately
conservative: all input is priced as a cache miss and current peak rates are used,
so the value is an upper bound rather than a claim about the provider invoice.

## Matched-cell inference and Telegram replication

`make agentic-v2-matched` recomputes the primary factorial intervals from the
archived 714-call score table. It matches each factor-present cell to the
factor-absent cell with the other three bits held fixed, resamples the eight
backgrounds and then the ten calls within each selected cell, and treats the
three models as a fixed equally weighted panel. The original call-level
bootstrap remains a descriptive sensitivity output.

The targeted Telegram replication uses the same three backends and schema-aware
provider layer but only two preregistered conditions and ten calls per cell:

```text
make telegram-audit-dry-run  # registers exactly 60 calls; no provider contact
make telegram-audit-run      # resumable fixed run
make telegram-audit-score    # scores and creates the parsed release archive
make telegram-audit-verify
```

Only aggregate Telegram design evidence is sent to providers. The prompt builder
does not read or transmit the archived `claim_boundary` fields. Raw provider JSON
stays in the ignored local artifact; the reproduction archive contains parsed
outputs, registries, scores, hashes, and the explicit fixed-panel scope note.
