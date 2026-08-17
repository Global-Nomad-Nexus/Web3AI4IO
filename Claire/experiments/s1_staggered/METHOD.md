# METHOD — S1 Base Clanker v4.1 staggered adoption (semi-synthetic)

Design-locked spec: `Web3AI4IO/Claire/experiment_plans/S1_staggered_heterogeneous_effects.md`.
Lock file: `design_lock.yaml` (written 2026-08-13T13:19:54Z, before any formal output).
This is a semi-synthetic method evaluation, not an estimate of the real Clanker v4.1 effect.

## 1. Event and data

Event anchor: Clanker v4.1 MEV module rollout on Base (`eip155:8453`); first v4.1 launch
2025-08-26 20:41:57 UTC. Observed window 2025-08-18..2025-10-01.

Inputs (SHA256 in `data_manifest.json`, recomputed by `src/audit.py`):

- `data/canonical/v1/base/launches/part-00000.parquet` (62,618 rows)
- `data/canonical/v1/base/protocol_config/part-00000.parquet` (62,618 rows)
- `data/canonical/v1/base/coverage_ledger/part-00000.parquet`
- `data_pipeline/releases/v1/base_core.json`

Join key `token_id`, unique on both sides (asserted with `validate="1:1"` in
`src/panel.py:load_panel`). Creator from `protocol_config.creator`, launch time from
`launches.launch_at` (UTC), version from `protocol_config.protocol_version`, restricted to
`v4.0_mev_or_hook` / `v4.1_mev_or_hook` (drops nothing; all rows qualify).

Recomputed audit counts (match the registered expectations exactly):
62,618 launches (54,649 v4.0 / 7,969 v4.1); 9,876 creators; 2,274 adopters;
763 adopters with >=1 pre v4.0 launch; 453 with >=3 pre v4.0 launches; singleton cohort
2025-08-29 (1 creator) excluded; 452 treated creators in 8 daily cohorts
2025-09-24..2025-10-01 with sizes 100, 140, 46, 47, 26, 34, 34, 25; 7,602 never adopters;
1,868 never adopters eligible (>=3 launches in the shared pre-period
2025-08-18..2025-09-23). Full funnel: `artifacts/sample_flow.csv`.

## 2. Groups

- Treated cohorts: first v4.1 launch date in 2025-09-24..2025-10-01 (8 daily cohorts, never merged).
- Pre-activity rule: >=3 v4.0 launches strictly before the first v4.1 (timestamp level).
  No post-treatment launch requirement (would screen on post-treatment outcomes).
- Never adopters: only v4.0 launches in the 45-day window, >=3 launches in the shared
  pre-period; these 1,868 creators form the calibration and resampling pool.

## 3. Semi-synthetic DGP (`src/dgp.py`, `src/calibration.py`)

Real data supplies only the staggered timing, cohort sizes, and the never-adopter activity
distribution. Real post-adoption outcomes are never used as untreated truth.

- Panel: 60-day creator-day pseudo panel; relative adoption days 24..31 (daily spacing
  identical to the real cohorts); cohort sizes = empirical counts; 452 treated +
  1,356 simulated never-treated controls per replication (3:1, `CONTROL_RATIO` in
  `src/mc.py` — a design choice the spec leaves open).
- Resampling: stratified by pre-period launch-rate quintile over the 1,868-creator pool
  (largest-remainder allocation, uniform with replacement within stratum).
- Hurdle count model, both layers estimated from never adopters only:
  layer 1 activity `Bernoulli(clip(p_i * act_mult_dow))`; layer 2 count given active
  `1 + Poisson(lambda - 1)` so `E[count | active] = lambda` exactly, with
  `lambda = mu_i * cnt_mult_dow * exp(injected log effect)`.
  Calendar pattern = day-of-week multipliers (the 45-day empirical pattern extends
  cleanly to 60 days; panel day 0 anchored to the weekday of 2025-08-18).
  Treatment shifts the count layer only, never the activity layer.
- Arms (registered constants, not tunable):
  zero — no effect; homogeneous — log effect 0.20 on all post-adoption days;
  heterogeneous — exposure effects 0.10 (days 0-2), 0.20 (3-6), 0.35 (7+) plus cohort
  modifiers 0.07, 0.05, 0.03, 0.01, -0.01, -0.03, -0.05, -0.07 (early to late).
- Scale gate (`calibration_summary.json`): untreated log1p outcome SD = 0.3648 over pool
  creator-days; registered effects are 0.27-0.96 SD, inside [0.25, 1.0] — gate passed.

## 4. Estimand and truth (`src/truth.py`)

Target: equal-weight ATT over all supported treated creator-days, on the `log1p(count)`
scale. A cohort-time cell is supported iff >=1 treated creator and >=1 never-treated
creator have observed outcomes on both day t and base day g-1; unsupported cells are
excluded from the truth AND both estimators (shared mask, acceptance 8.3). With the fully
simulated 60-day panel there are no missing outcomes, so all 260 cells
(sum over cohorts of 60 - g) are supported in every replication.

True cell ATT is computed analytically from the generating intensities:
`E[log1p(Y)] = p_active * E[log(2 + J)]`, `J ~ Poisson(lambda - 1)`, evaluated by
truncated Poisson summation (`scipy.special.gammaln`); the per-cell truth is the mean of
`E[log1p(Y(1))] - E[log1p(Y(0))]` over the cell's treated creators. Overall truth
aggregates cells by registered treated creator-day counts — identical weights to the
estimators. `summarize.py` re-derives the overall truth from
`cohort_time_truth.parquet` alone and asserts agreement with `results_long.parquet`
(max abs diff 3.5e-18 in the pilot).

## 5. Estimators (`src/estimators.py`)

- Static TWFE: `log1p(count) ~ post + creator FE + calendar-day FE`, hand-rolled by
  alternating-projection demeaning (bincount-based), cluster-robust (CR1) SE by creator.
  Cross-checked against a statsmodels dummy regression in the test suite. Implicit
  per-observation weights `w = D~ / sum(D~^2)` are aggregated per cohort as the
  Goodman-Bacon style diagnostic (`weight_diagnostics.csv`): the weights are
  deterministic given the fixed panel structure; negative implicit weight mass on treated
  observations sums to -1.0 (positive mass +2.0).
- Group-time ATT (Callaway-Sant'Anna style, unconditional, no covariates): base period
  day g-1, control group = same-day never-treated only (not-yet-treated never used).
  `ATT(g,t)` = DiD of group means; aggregated strictly by registered treated creator-day
  cell counts. SE from the per-creator influence function of the aggregate; CI from a
  creator-level multiplier bootstrap, 1,999 Rademacher draws, vectorized as one
  matrix product (percentile interval).

## 6. Monte Carlo design (`run_mc.py`, `src/mc.py`)

2,000 replications per arm. Seeds: `SeedSequence([20250826])` -> spawn 3 (arms) ->
spawn 2,000 (replications); three-level independent streams. Per replication and method,
`results_long.parquet` stores estimate, SE, CI, true overall ATT, error, coverage,
rejection, support size, unestimable flag, and TWFE weight diagnostics.

Metrics (`summarize.py`, rebuilt only from the stored parquet outputs): bias, MCSE of
bias (`sd(error)/sqrt(n)`), relative bias (treated arms only), RMSE, 95% coverage with
its binomial MCSE, false-positive rate (zero arm: P(reject)), false-negative rate
(treated arms: P(no reject)), sign correctness (treated arms: P(sign(estimate) =
sign(truth))), claim accuracy (zero arm: P(no reject); treated arms: P(reject AND
correct sign)), unestimable rate.

## 7. Environment and deviations

Python 3.12.13 in the experiment-local `.venv` (created with `uv`); locked dependencies
numpy, pandas, pyarrow, scipy, statsmodels — nothing else, no shared project files
touched. Consequence: `figure_s1.pdf/.png` are rendered by `src/simplefig.py`, a
stdlib-only vector-PDF writer plus a zlib/struct PNG rasterizer sharing one canvas.

Deviations from the spec: none in design. Open choices the spec leaves free, fixed here:
3:1 control-to-treated ratio in the simulated panel; day-of-week (rather than
per-calendar-day) multipliers for the calendar pattern; percentile bootstrap CI for the
group-time ATT with the IF-based SE reported alongside.

## 8. Fresh rerun

From `Web3AI4IO/Claire/experiments/s1_staggered/`:

```bash
uv venv --python 3.12 .venv   # once; then:
uv pip install --python .venv/bin/python numpy pandas pyarrow scipy statsmodels
.venv/bin/python src/audit.py          # -> data_manifest.json
.venv/bin/python src/calibrate.py      # -> calibration_summary.json
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python run_mc.py --reps 2000 --out artifacts
.venv/bin/python summarize.py --results artifacts/results_long.parquet \
    --truth artifacts/cohort_time_truth.parquet --out artifacts
.venv/bin/python src/sample_flow.py    # -> artifacts/sample_flow.csv
```
