# S4 RESULTS — endogenous adoption sensitivity (Base Clanker v4.1 calibration)

Semi-synthetic method evaluation per `design_lock.yaml`. This is **not** an
estimate of any real Clanker v4.1 effect, and results do not generalize beyond
the Clanker-calibrated DGP family.

Setup: 1,379 eligible creators (≥3 launches in 2025-08-18..2025-09-07), 60-day
pseudo panels, adoption probability `logit⁻¹(α + γ·z(b_i))` with creator latent
pretrend `b_i`, 8 staggered cohorts (days 24–31, empirical proportions),
true event-time-0 ATT = 0 (zero arm) / 0.20 (positive arm), 2,000 replications
per cell, 0 unestimable replications, 0 batch failures.

## Main results (2,000 reps per cell; MCSE of rates ≈ 0.005–0.011)

| γ | arm | bias TWFE | bias CS e=0 | conv. cover | sens. cover (Mbar=1) | pretrend power | unidentified rate | registered claim accuracy |
|---|-----|-----------|-------------|-------------|----------------------|----------------|-------------------|----------------|
| 0    | positive | −0.0005 | 0.0004 | 0.944 | 1.000 | 0.048 | 0.0055 | 1.000 |
| 0    | zero     |  0.0004 | 0.0003 | 0.956 | 0.999 | 0.048 | 0.9990 | 0.956 |
| 0.75 | positive |  0.4652 | 0.0165 | 0.909 | 0.999 | 0.768 | 0.0050 | 0.005 |
| 0.75 | zero     |  0.4644 | 0.0164 | 0.919 | 1.000 | 0.758 | 0.9995 | 0.9995 |
| 1.5  | positive |  0.7066 | 0.0262 | 0.837 | 0.999 | 0.991 | 0.0060 | 0.006 |
| 1.5  | zero     |  0.7067 | 0.0254 | 0.855 | 0.998 | 0.988 | 0.9975 | 0.9975 |

Full metric set (RMSE, MCSEs, supported-positive rate, robust-value shares) in
`artifacts/results_summary.csv`.

## Findings

1. **Pipeline calibration is clean.** At γ=0 the Callaway–Sant'Anna event-time-0
   estimator is unbiased (bias ≤ 0.0004, MCSE 0.0006), conventional coverage is
   94.4–95.6% against nominal 95%, and the pretrend Wald test size is 4.8%
   against nominal 5%.
2. **Static TWFE confounds latent growth with the treatment effect.** Under
   moderate/strong selection its bias is +0.47 / +0.71 — 2.3×–3.5× the injected
   effect. The staggered DiD estimator with universal base period differences
   out most of it (bias +0.017 / +0.026), because selection operates on the
   *slope* and a one-period change only inherits `b_i`, not the accumulated
   level gap.
3. **Residual selection bias still degrades conventional inference.** CS
   conventional coverage falls to 0.909 (γ=0.75) and 0.837 (γ=1.5) in the
   positive arm.
4. **The registered HonestDiD grid is conservative in coverage but rarely
   answers `unidentified` here.** Mbar=1 intervals cover the truth in
   ≥99.8% of replications across all cells. In the positive arm the Mbar=1
   interval excludes zero in 99.4 to 99.5% of replications even under strong
   selection, so under the locked researcher-conservative claim rule
   registered claim accuracy is about 0.005. This score is a property of the
   decision rule, not an empirical interval-accuracy metric; see Scoring
   interpretation below.
   In the zero arm the same procedure answers `unidentified` in ≥99.75% of
   replications — the desired behavior.
5. **Robust values.** In the γ=1.5 positive arm, 54% of replications still
   exclude zero at Mbar=2 (`robust_value = Inf`); the induced pre-trend
   deviation from this selection mechanism is small relative to the registered
   deviation multipliers.
6. **Diagnostics have power against this violation.** The pre-period
   slope-difference t-test rejects in 100% of γ>0 replications; the pretrend
   joint Wald test power is 0.76 (γ=0.75) and 0.99 (γ=1.5). Under this DGP,
   endogenous adoption on latent growth is *visible* in pre-trends — a plan
   caveat stands that non-rejection would not have implied parallel trends.

## Method failures

None. 12,000/12,000 replications estimable; no empty-CI or support failures.

## Scoring interpretation

The locked `claim_accuracy` is a researcher-conservative score: for every
`gamma>0` cell it treats `unidentified` as the only correct answer. It therefore
scores an Mbar=1 interval that covers the true 0.20 and lies entirely above zero
as incorrect. This score is retained for preregistration fidelity, but it is not
an empirical accuracy measure for HonestDiD.

The secondary `conditional_claim_accuracy_m1` asks a different question. In the
zero arm, does the Mbar=1 interval contain zero? In the positive arm, does it
cover the known 0.20 truth and lie entirely above zero? Under moderate and strong
selection this conditional score is 0.9995/0.9975 in the zero arm and
0.9935/0.9930 in the positive arm. These are sensitivity-qualified claims under
the registered Mbar=1 bound, not unconditional causal identification. Exact
definitions are in `artifacts/scoring_interpretation.json`.

## Fresh rerun

```bash
cd Web3AI4IO/Claire/experiments/s4_endogenous
rm -rf artifacts/mc artifacts/results_long.parquet   # force recompute (batches checkpoint)
.venv/bin/python src/s4_endogenous/calibrate.py
.venv/bin/python src/s4_endogenous/run_mc.py --all --reps 2000 --batch-size 50 --ncores 9
.venv/bin/python src/s4_endogenous/summarize.py
R_LIBS=$PWD/R/library Rscript R/make_figure.R "$PWD"
```

Determinism verified: a fresh 50-replication batch of the γ=1.5/positive cell
reproduced the formal run's outputs bitwise (only per-rep wall-clock `secs`
differs). Runtime ≈ 24 core-seconds per replication (~95 min per cell on 9
cores).
