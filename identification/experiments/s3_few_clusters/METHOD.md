# METHOD — S3 few-platform-clusters inference experiment

Spec (authoritative): `Web3AI4IO/identification/experiment_plans/S3_few_platform_clusters.md`,
including the 2026-08-13 scale-rule revision (修订记录). Status: **RUN COMPLETE**.

## Input data and evidence metadata

- Panel: `Web3AI4IO/data/external/pumpswap/20260810/bundle/01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local/data/processed/solana_dex_daily_did_panel.csv`,
  sha256 `d5cb9629c51f2781100362a130843bbaffaf26bc2dea4e4d12de1fa9697e3853`,
  matching the bundle's `FILE_MANIFEST_SHA256.txt` (see `data_manifest.json`).
- Event config `.../application/configs/pumpswap_case.json` and registry
  `.../benchmark_release/data/events.csv` confirm event date 2025-03-20 UTC,
  cluster column `unit`, event ID `PUMP_PUMPSWAP_MIGRATION_20250320`.
- No old joint synthetic outputs were read; no source data was modified.

## Panel validation (all PASS — `panel_validation.json`)

724 rows = 4 units (`pump_ecosystem`, `raydium`, `orca`, `meteora_combined`)
× 181 days, `rel_day` −90..90, one calendar date per `rel_day`, no duplicate
unit-days, no missing `log_volume`. Script: `src/validate_panel.py`.

## DGP (spec §3)

1. Pre-period fit on the 360 real rows with `rel_day` ∈ [−90, −1]: OLS of
   `log_volume` on 4 unit dummies (no intercept) + 6 weekday dummies (Monday
   reference), rank 10. Residuals `u_it = y − unitFE_i − weekday_{d(t)}`
   retain the common day shock `xi_t` by construction; block-bootstrapping
   the 4-vectors `u_t` therefore preserves contemporaneous cross-market
   dependence (`src/dgp.py::load_dgp_components`).
2. Untreated synthetic panel for `rel_day` ∈ [−60, 29] (90 days × 4 units):
   `Y0_it = unitFE_i + weekday_eff[weekday(t)] + u*_it`, where `u*` is a
   7-day moving-block bootstrap over the 90 pre-period residual day-vectors
   (13 block starts, uniform on 0..83, truncated to 90 days) and the weekday
   of a synthetic `rel_day` is the weekday of the real panel date at that
   `rel_day` (`src/dgp.py::build_y0_panel`).
3. Treatment assignment is fixed by arm design, hence independent of the
   resampled blocks. Per-rep RNG stream:
   `np.random.default_rng(np.random.SeedSequence([arm_seed, rep_id]))`.
4. Per rep, `artifacts/rep_construction.parquet` records the assignment,
   injected effect, true 30-day ATT (= the injected constant), the RNG
   descriptor, and the 13 block-start indices — sufficient to reconstruct
   the exact Y0 panel.

Known DGP feature (honest reporting, spec §8.8): the real
`meteora_combined` series contains seven pre-period days with
`log_volume = 0` (≈ \$1 volume placeholders at `rel_day` −90, −89, −85, −73,
−71, −67, −64) followed by a ramp from ≈17 to ≈23 in log volume. The unit
FE + weekday model cannot absorb this, so meteora's pre-period residuals
have SD 5.60 (vs 0.57–0.92 for the other units) with a strong trend. The
block bootstrap propagates these block-level shifts into the synthetic
untreated panels. This is the spec-mandated DGP applied to the real panel,
not an implementation choice; its consequences for the placebo
`meteora_combined` assignment are reported in RESULTS.md.

## Scale metric and scale check (spec §3, revised 2026-08-13)

`s_ATT` = sampling SD (ddof=1) of the null 30-day DiD estimator (TWFE
treated-post coefficient, unit FE + day FE, window `rel_day` −60..29),
estimated from a seeded zero-arm pilot: **2,000 replications, seed
20260813**, assignment `pump_ecosystem`, same DGP/estimator/window as the
full run (`src/run_experiment.py::_pilot`).

- Pilot: mean estimate 0.00499, **s_ATT = 0.706190**
- Scale check: 0.20 / s_ATT = **0.2832 ∈ [0.25, 1.0] → PASS**
- Moderate arm effect fixed at 0.5 × s_ATT = **0.353095**

All values recorded in `calibration_summary.json` and `design_lock.yaml`.
The superseded residual-SD rule (SD = 2.8784, ratio 0.0695, blocker of the
first run) is retained in `panel_validation.json` for traceability only.

## Point estimator and inference methods (spec §4)

TWFE DiD on `rel_day` ∈ [−60, 29] (360 obs): `log_volume ~ unit FE +
calendar-day FE + treated-post`, rank K = 94 (4 unit + 89 day dummies + 1
treated-post). CRV1 clustered by unit, G = 4, Stata small-sample factor
(G/(G−1))·((N−1)/(N−K)) = (4/3)·(359/266) = 1.7994987. Closed-form numpy,
vectorized across replications (`src/estimator.py`); agreement with
statsmodels `OLS.fit(cov_type="cluster", use_correction=True)` on β, SE, t
for all 4 assignments is enforced by `tests/test_simulation.py`.

1. `crv1_normal` — CRV1 SE, normal crit 1.9599640; 95% CI = β̂ ± crit·SE.
2. `crv1_t3` — CRV1 SE, t(3) crit 3.1824463; 95% CI likewise.
3. `wild_sign_enum` — restricted wild cluster sign enumeration: sharp-null
   residuals from the no-treated-post fit, all 16 Rademacher sign vectors
   enumerated (no sampling), two-sided p = share of |t*| ≥ |t_obs|. By the
   s → −s symmetry the 16 vectors yield 8 distinct |t*|, so attainable
   two-sided p ∈ {2/16, 4/16, …, 1} and the minimum attainable p is 0.125.
   CI = `not_available` (sharp-null p only, spec §4).
4. `randomization_inference` — zero arm only: two-sided p over the DiD
   point estimates under all 4 treated-identity assignments, attainable
   p ∈ {0.25, 0.5, 0.75, 1.0}, minimum 0.25. CI = `not_available`.

## Arms and replications (spec §6)

| arm | injected effect (rel_day 0..29, `pump_ecosystem`) | reps | seed |
|---|---|---|---|
| zero | none; methods 1–3 evaluated under all 4 rotated treated identities per rep | 10,000 | 20260813001 |
| low_power | 0.20 | 10,000 | 20260813002 |
| moderate | 0.3530948174041942 (= 0.5 × s_ATT) | 10,000 | 20260813003 |

Metrics per arm × method (`artifacts/results_summary.csv`): rejection rate
@0.05 with Monte Carlo SE √(p(1−p)/R), FPR (zero), power and FNR (injected
arms), CI coverage and mean width (methods 1–2), claim accuracy (zero:
correct non-rejection; injected: correct rejection), p-value mean/median,
failure rate (non-finite results; 0 everywhere), calibration gain vs
baseline (zero-arm FPR reduction) and power loss vs baseline. Zero-arm
p-value distributions per method × assignment, including the three placebo
identities, are in `artifacts/null_pvalue_diagnostics.csv`.

## Claim boundary

PumpSwap-panel-calibrated few-cluster inference evaluation only. No
statement is made about the real PumpSwap causal effect, and placebo
treated identities on control markets are not interpreted as real events
(spec §5, §8.9).

## Fresh rerun command

```bash
cd Web3AI4IO/identification/experiments/s3_few_clusters
# one-time environment (already present):
#   uv venv --python 3.12 .venv
#   uv pip install --python .venv/bin/python numpy pandas scipy statsmodels pyarrow pytest matplotlib
.venv/bin/python -m src.validate_panel   # panel_validation.json + data_manifest.json
.venv/bin/python -m src.run_experiment   # pilot, scale check, 3 arms x 10,000 reps, all artifacts
.venv/bin/python -m src.make_figure      # artifacts/figure_s3.pdf/.png
.venv/bin/python -m pytest tests/ -q     # 17 tests
```

Everything rebuilds from the input CSV alone (plus the two evidence
metadata files for the manifest). Total simulation runtime ≈ 1.6 s.
