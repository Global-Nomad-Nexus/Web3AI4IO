# VALIDATION — S3 few-platform-clusters inference experiment

Spec acceptance criteria (§8) and how each is met. Test suite:
`.venv/bin/python -m pytest tests/ -q` → **17 passed** (2026-08-13).

## Acceptance criteria mapping (spec §8)

1. **Exactly four named Solana market clusters and 724 input rows** —
   `panel_validation.json` (`status: OK`, all panel checks PASS);
   `tests/test_validation.py::test_panel_balance`.
2. **Event date, window, outcome, treated identity fixed** —
   `design_lock.yaml` (event 2025-03-20 UTC, window rel_day −60..29,
   outcome `log_volume`, treated `pump_ecosystem`); constants in
   `src/dgp.py` / `src/estimator.py`.
3. **Cluster unit and assignment unit are both the market** — CRV1 clusters
   by `unit` (G = 4); assignments rotate treated identity across the same
   four markets (`artifacts/treatment_permutations.csv`).
4. **4 permutations and 16 sign vectors complete and unique** —
   `tests/test_simulation.py::test_sign_vectors_16_unique`,
   `::test_treatment_permutations_4_unique`, plus on-disk artifact
   cross-checks (`test_sign_enumeration_csv_matches_code`,
   `test_treatment_permutations_csv_matches_code`).
5. **≥10,000 runs per arm with Monte Carlo uncertainty** — exactly 10,000
   reps per arm; `results_summary.csv` reports `mc_se_rejection` and
   `mc_se_coverage` (√(p(1−p)/R)) for every row.
6. **Tests cover panel balance, sharp null, sign enumeration, permutation
   count, seed reproducibility, p-value discreteness** — see test inventory
   below.
7. **Fresh rerun rebuilds all results from the input CSV** — command in
   METHOD.md; verified 2026-08-13 by re-running
   `src.validate_panel` + `src.run_experiment` + `src.make_figure` +
   pytest end-to-end (bit-identical artifacts; total ≈ 1.6 s simulation
   time).
8. **Honest reporting if CRV1 doesn't over-reject or wild doesn't
   improve** — RESULTS.md §"Honest reporting": baseline over-rejects only
   mildly (6.46% vs 5%) on the main assignment; wild/RI FPR = 0 is
   structural discreteness (min attainable p 0.125 / 0.25), reported as
   such, with total power loss at α = 0.05 stated explicitly.
9. **Claim boundary: PumpSwap-panel-calibrated inference evaluation
   only** — stated in METHOD.md and RESULTS.md; placebo rotations are not
   interpreted as real events.

## Test inventory (17 tests, all passing)

`tests/test_validation.py` (5):
- `test_panel_balance` — 724 rows, 4 named units × 181 days, rel_day
  −90..90, no duplicates/missing, one date per rel_day.
- `test_preperiod_fit_shape_and_rank` — 360 obs, design rank 10.
- `test_residuals_orthogonal_to_regressors` — OLS sanity of the pre-period
  fit.
- `test_residual_scale_descriptive_deterministic` — residual-SD
  descriptives reproduce (SD = 2.8784); old-rule verdict recorded for
  traceability, no longer gating.
- `test_validation_script_output_matches_recomputed` — on-disk
  `panel_validation.json` (status OK) matches recomputation.

`tests/test_simulation.py` (12):
- `test_sign_vectors_16_unique` — 16 unique Rademacher vectors over 4
  clusters.
- `test_treatment_permutations_4_unique` — 4 unique treated identities.
- `test_sign_enumeration_csv_matches_code` /
  `test_treatment_permutations_csv_matches_code` — artifacts match code
  constants.
- `test_seed_reproducibility` — same (arm_seed, rep_id) → identical panel
  and block starts; different rep_id → different panel.
- `test_assignment_independent_of_blocks` — bootstrap stream does not
  depend on the treated identity.
- `test_sharp_null_imposition` — null residuals orthogonal to the null
  design; all-plus sign vector reproduces the observed t; |t*| symmetric
  under s → −s.
- `test_wild_pvalue_discreteness` — wild p-values are multiples of 1/16
  with minimum 2/16.
- `test_randomization_pvalue_discreteness` — RI p-values ∈ {0.25, 0.5,
  0.75, 1.0}.
- `test_fastpath_matches_statsmodels` — closed-form β, SE (Stata factor),
  t match `statsmodels` OLS + `cov_cluster` (rel. tol 1e-8) for all 4
  assignments; df_resid = 360 − 94.
- `test_synthetic_panel_shape_and_injection` — 90×4 panel, 13 block starts
  in [0, 83], injection hits exactly rows 60..89 of the treated unit.
- `test_pilot_reproduces_recorded_s_att` — re-running the seeded pilot
  (2,000 reps, seed 20260813) reproduces the s_ATT recorded in
  `calibration_summary.json` to rel. tol 1e-9.

## Independent cross-checks performed during the run

- statsmodels reproduction of the placebo `meteora_combined` zero-arm FPR:
  0.90 over 100 reps (fast path: 0.926 over 500 reps, 0.9357 over 10,000)
  — confirms the placebo calibration collapse is estimator behavior under
  the spec DGP, not a fast-path bug. E[β̂] ≈ +0.015 (unbiased); E[SE] =
  0.091 vs SD(β̂) = 2.000.
- Zero-arm estimate distribution for `pump_ecosystem` is centered at 0
  (full-run mean 0.0046, pilot mean 0.0050) with SD 0.7216 (full run,
  10,000 reps) vs s_ATT = 0.7062 (pilot, 2,000 reps, independent seed) —
  internal consistency between pilot and full run within Monte Carlo
  variation.

## Input integrity

`data_manifest.json`: input panel sha256
`d5cb9629c51f2781100362a130843bbaffaf26bc2dea4e4d12de1fa9697e3853` matches
the bundle `FILE_MANIFEST_SHA256.txt`; evidence metadata files
(`pumpswap_case.json`, `events.csv`) hashed likewise. No source data,
manuscript, Wiki, shared dependencies, or git history were modified; all
writes are confined to `identification/experiments/s3_few_clusters/`.
