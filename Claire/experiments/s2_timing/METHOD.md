# S2 method: announcement vs activation timing (semi-synthetic)

Status: **completed** under the plan-owner amendment of 2026-08-13 (post effect
0.15 log primary, 0.10 log robustness; the original 0.20 failed the mandated
scale gate and was replaced by the owner, not by the agent; the scale-window
rule itself is unchanged). The anticipation-interval effect keeps the plan's
0.08/0.20 = 0.4 ratio to the post effect (0.06 / 0.04 log).

## Design (locked in `design_lock.yaml`)

Event `PUMP_CREATOR_FEE_20250513` (Solana, Pump.fun). Announcement 2025-05-08
(first public documentation), verified onchain activation 2025-05-13 11:27:06 UTC.
Unit: platform-day. Treated series: Pump.fun; comparison series: Moonshot
(diagnostic noise-calibration only, never claimed as a causal control).

- Clean pre: 2025-04-17..2025-05-07 (21 days per platform)
- Announcement interval (real setting, gap = 5): 2025-05-08..2025-05-12
- Partial activation day 2025-05-13 dropped at daily frequency
- Clean post / estimand window: 2025-05-14..2025-06-03 (21 days)

## DGP (`src/s2_timing/dgp.py`)

Only clean-pre observed data calibrates the untreated process. Per platform and
outcome, weekday cell means of `log1p(outcome)` (equivalent to OLS on weekday
fixed effects) over the 21 pre days; residuals form the paired daily residual
vector (Pump, Moonshot). A circular 7-day moving-block bootstrap of the paired
vector (preserving same-day correlation) generates untreated potential outcomes
for 2025-04-17..2025-06-03. Arms:

- `zero`: no injected effect
- `no_anticipation`: Pump +effect log from 2025-05-13 onward
- `anticipation`: Pump +0.4×effect on announcement..2025-05-12, +effect from
  2025-05-13 onward
- Announcement gap grid: synthetic announcement 3/5/7/10 days before activation
  (5 = real setting); estimator-side clean pre ends the day before the
  synthetic announcement; Moonshot effect always zero (interference disabled)

## Estimand and estimators (`src/s2_timing/estimators.py`)

Target: average log ATT over the 21 post days (2025-05-14..2025-06-03). All
methods regress `d_t = log1p(Pump) - log1p(Moonshot)` on intercept + weekday FE
+ `beta*post_t` with Newey-West HAC lag 7 (batched over replications):

1. **Naive announcement**: `post_t = 1` from the announcement day; counts the
   announcement–activation interval (and 2025-05-13) as post.
2. **Verified activation**: `post_t = 1` only 2025-05-14..2025-06-03;
   announcement interval kept as pre (contaminated under true anticipation);
   2025-05-13 dropped.
3. **Activation + anticipation gate**: HAC-7 Wald test of the announcement
   interval vs clean-pre weekday-adjusted mean difference; `p < 0.05` ⇒
   decision `unidentified` (no estimate); otherwise the point estimate uses
   clean pre + clean post only, announcement interval fully excluded.

## Monte Carlo (`src/s2_timing/run_mc.py`)

2 outcomes × 2 effect sizes × 4 gaps × 3 arms × 3 methods, 2,000 replications
per cell (96,000 total), deterministic per-cell seeds (base 20260513). Metrics:
bias, RMSE, coverage, FPR/FNR, sign correctness, claim accuracy, attenuation
ratio, anticipation classification accuracy, gate rejection rate, unidentified
rate, Monte Carlo standard errors. Outputs: `artifacts/results_long.parquet`
(per-rep), `artifacts/results_summary.csv`, `artifacts/timing_gate_diagnostics.csv`,
`artifacts/figure_s2.pdf/.png` (`src/s2_timing/make_figure.py`).

## Tests (`tests/test_s2_timing.py`, 6 passed)

Same-day announcement (gap 0, gate cannot fire), partial activation-day
handling, no-anticipation arm path, true-anticipation arm path, paired
7-day moving-block bootstrap (block structure + same-day pair preservation),
and estimator sanity (verified/gate unbiased, naive attenuated).

## Fresh rerun command

```bash
cd Claire/experiments/s2_timing
uv venv --python 3.12 .venv   # if missing
uv pip install --python .venv/bin/python numpy pandas scipy statsmodels pyarrow matplotlib pytest
.venv/bin/python -m pytest tests/ -q
.venv/bin/python src/s2_timing/run_mc.py        # ~1 min, rebuilds artifacts
.venv/bin/python src/s2_timing/make_figure.py
.venv/bin/python src/s2_timing/calibrate.py     # input + scale-gate audit, exit 0 under approved effects? (see note)
```

Note: `calibrate.py` still encodes the original 0.20 gate and exits 1 against
it — it is retained as the audit trail of the stop decision. The approved
effects pass the same window: 0.15 → 0.861/0.915 and 0.10 → 0.574/0.610
(launches / unique creators, ratio to paired-diff residual SD).
