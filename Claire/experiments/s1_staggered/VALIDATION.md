# VALIDATION — S1 staggered adoption experiment

Validated 2026-08-14 against the acceptance criteria and stop conditions of
`Web3AI4IO/Claire/experiment_plans/S1_staggered_heterogeneous_effects.md`.

## Acceptance criteria (spec §8)

1. **Event, chain, unit, outcome, groups, paths consistent with the spec.** PASS.
   Base (`eip155:8453`) / Clanker / creator-day / `log1p(launch_count)`; cohorts,
   singleton exclusion, pre-activity rule and input paths in `design_lock.yaml` match
   the spec verbatim; audit counts recomputed from the parquet inputs match the
   registered numbers exactly (`data_manifest.json`: 62,618 launches, 54,649/7,969 by
   version, 9,876 creators, 2,274 adopters, 763 ≥1-pre, 453 ≥3-pre, singleton 1,
   452 treated with sizes [100,140,46,47,26,34,34,25], 1,868 never-adopter pool).
2. **Design lock predates formal outputs.** PASS. `design_lock.yaml` locked at
   2026-08-13T13:19:54Z; first formal MC output written 2026-08-13 ~14:24Z
   (`artifacts/run_config.json.completed_at_utc`).
3. **Truth, estimator support, aggregation weights aligned.** PASS. Shared support
   mask (260/260 cells supported every rep); `summarize.py` re-derives the overall
   true ATT from `cohort_time_truth.parquet` alone and compares to
   `results_long.parquet`: max abs diff 5.2e-18 over 12,000 rows
   (`artifacts/summary_check.json`, `aligned: true`).
4. **≥2,000 valid runs per arm with Monte Carlo uncertainty.** PASS. n_valid = 2,000
   for all 6 arm×method cells, unestimable rate 0.0; `mcse_bias` and `mcse_coverage`
   reported for every cell in `artifacts/results_summary.csv`.
5. **Tests cover the five registered areas.** PASS. `python -m unittest discover -s
   tests -v` → 7 tests OK: constant-effect recovery (homogeneous), no-effect zero-arm
   FPR sanity, never-treated-only control path, unsupported-cell exclusion aligned
   across truth and estimators, deterministic 3-cohort 6-day manual-ATT fixture
   (estimates, support and weights checked cell by cell), plus a statsmodels
   cross-check of the hand-rolled TWFE.
6. **Fresh rebuild from raw parquet; summary from long results.** PASS, exercised by
   the main agent: `src/audit.py` and `src/calibrate.py` re-run and regenerate
   `data_manifest.json` / `calibration_summary.json` byte-identical except the
   timestamp; `summarize.py` rebuilds `results_summary.csv`,
   `weight_diagnostics.csv`, `figure_s1.pdf/.png` purely from
   `results_long.parquet` + `cohort_time_truth.parquet`.
7. **No DGP tuning when the modern estimator does not improve.** PASS. The group-time
   ATT estimator shows no improvement (equal bias, ~3.4× RMSE); the DGP and effect
   constants were left untouched and the result is reported as-is (RESULTS.md).
8. **Scope limited to the Clanker-calibrated DGP family.** PASS. Stated explicitly in
   RESULTS.md; no claim about the real v4.1 effect or cross-chain generalization.

## Stop conditions (spec §9) — none triggered

- Creator join unique: `token_id` unique on both sides, 1:1 merge asserted
  (`validate="1:1"`); not triggered.
- Cohorts too small: smallest cohort 25, as registered; not triggered.
- Effect scale outside [0.25, 1.0] outcome SD: 0.27–0.96 SD
  (`calibration_summary.json.scale_gate.blocked: false`); not triggered.
- Estimators cannot align to the estimand: aligned (criterion 3); not triggered.
- Shared-environment modification: none — all writes under
  `Claire/experiments/s1_staggered/`; dependencies installed only in the
  experiment-local `.venv` (Python 3.12.13, numpy/pandas/pyarrow/scipy/statsmodels);
  no git operations.

## Formal run record

- Command: `.venv/bin/python run_mc.py --reps 2000 --out artifacts`
  (3 arms default, 1,999 bootstrap draws, scenario seed 20250826).
- Wall time 1,988.4 s; 12,000 result rows; 1,560,000 truth-cell rows.
- Pilot (25 reps/arm) preserved under `artifacts/pilot/` as pipeline evidence.
- Figure rendering verified by viewing the generated PNG after the full run.
