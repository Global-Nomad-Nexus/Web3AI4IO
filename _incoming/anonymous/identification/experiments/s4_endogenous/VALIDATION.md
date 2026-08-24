# S4 VALIDATION

## Acceptance criteria (plan §9)

1. **Event, chain, files, unit, outcome, estimand, package calls fixed** — ✅
   `design_lock.yaml` written before any formal output; matches
   `experiment_plans/S4_endogenous_adoption_sensitivity.md`; input SHA256 in
   `data_manifest.json`.
2. **Eligible creator count reproducible** — ✅ pipeline recomputes 1,379
   eligible / 1,121 never-v4.1, matching the plan audit; stage counts in
   `sample_flow.csv`.
3. **Adoption probability rises with latent untreated growth** — ✅ test
   `strong_selection_treated_higher_slope` (treated mean `b_i` strictly above
   control at γ=1.5) and `selection_gap_monotone_in_gamma`; at γ=0 assignment
   is independent of `b_i` (`gamma0_assignment_independent_of_slope`).
4. **Oracle fields never enter the estimator dataframe** — ✅ payload carries
   only `(id, t, y, g)`; verified by `test_oracle_leakage` (file inventory,
   byte sizes, round-trip equality, no slope/propensity vectors) and
   `artifacts/oracle_leakage_audit.json`.
5. **Sensitivity grid locked before results and fully reported** — ✅
   `Mbarvec=c(0.5,1,1.5,2), gridPoints=100` in `design_lock.yaml` (predates the
   formal run); all four intervals per replication in
   `artifacts/sensitivity_curves.parquet`.
6. **≥2,000 runs per cell with Monte Carlo uncertainty** — ✅ exactly 2,000
   per cell, 0 unestimable; MCSE columns in `results_summary.csv`.
7. **Test coverage** — ✅ `tests/run_tests.py` (32 checks: γ=0, strong
   selection, oracle leakage, zero effect, share gate, seed determinism,
   cohort proportions, adoption support, payload round-trip, oracle
   de-trending unit test) and `tests/test_r_bridge.R` (deterministic ATT
   recovery for TWFE and CS e=0, universal base period + continuous
   event-time validation, sensitivity nesting in Mbar, finite non-empty
   intervals, broken-support flagged unestimable). All pass.
8. **Fresh rerun rebuilds all results** — ✅ spot rerun of 50 replications
   (γ=1.5, positive) reproduces the formal CSV bitwise (except wall-clock
   `secs`). Full command in `RESULTS.md`.
9. **Method failures reported** — ✅ none occurred (unestimable rate 0; the
   empty-CI guard `empty robust CI (acceptance grid exhausted)` was never
   triggered in the formal run; it is exercised in `test_r_bridge.R`).
10. **No claims about real Clanker effects or method generalization** — ✅
    stated in `RESULTS.md` header and limitations.

## Postprocessing interpretation audit

The original locked `claim_accuracy` remains unchanged. The summarizer also
reports `registered_claim_accuracy` as an explicit alias and adds
`conditional_claim_accuracy_m1`, mean original and Mbar=1 interval widths, and
pre-period slope-test power. The secondary score requires the Mbar=1 interval
to contain zero in the zero arm, or both cover the known 0.20 truth and lie
entirely above zero in the positive arm. It is a sensitivity-qualified metric,
not unconditional identification. Definitions are persisted in
`artifacts/scoring_interpretation.json`.

After this postprocessing addition, `.venv/bin/python tests/run_tests.py
--with-r` passes all 32 Python checks and all 9 R production-path checks. The
formal panels and R estimates were not rerun or altered; summaries and Figure
S4 were rebuilt from `artifacts/results_long.parquet`.

## Stop conditions (plan §10)

None triggered. Eligible 1,379 ≥ 1,000; residual pool 1,121 ≥ 800; R toolchain
approved by the user 2026-08-13; did 2.1.2 / HonestDiD 0.2.8 installed and
verified loadable; official calls accept the generated panels; oracle leakage
audit passes; no shared configuration modified.

## Environment deviations (documented in design_lock.yaml / METHOD.md)

- R 4.6.1 via Homebrew (user-approved); rust/cmake/glpk added as compilation
  requirements of the approved CRAN packages.
- Python 3.12.13 via uv; experiment-local venv with numpy/pandas/pyarrow only.
- R packages live in experiment-local `R/library`; nothing installed to shared
  locations.
- CRAN HonestDiD 0.2.8 does not export `honest_did` and registers no S3
  method; the pipeline calls the identical locked function via
  `HonestDiD:::honest_did.AGGTEobj` (signature verified against 0.2.8).
- Inference mode not fixed by the plan: `att_gt`/`aggte` called with
  `bstrap=FALSE, cband=FALSE` — analytic influence-function SEs, the same IF
  VCV that `honest_did.AGGTEobj` uses internally.
- Static TWFE implemented in base R (within transformation, creator-clustered
  CR1 SE) to avoid unapproved packages.
- Python↔R bridge: raw little-endian binary payloads; no extra R packages.

## Fixed during development (regression-tested)

- Binary payload row/column order mismatch between numpy and R `matrix()`
  silently scrambled creator–time pairing in the first pilot; caught because
  R-side estimates contradicted Python-side naive DID; fixed in
  `dgp.write_batch` and locked by `payload_roundtrip_y/g` tests.
