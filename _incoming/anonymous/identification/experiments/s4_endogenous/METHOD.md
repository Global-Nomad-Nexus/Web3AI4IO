# S4 METHOD — endogenous adoption sensitivity (Base Clanker v4.1)

Semi-synthetic method evaluation locked by `design_lock.yaml`. Not an estimate of
any real Clanker v4.1 effect; conclusions are restricted to the
Clanker-calibrated DGP family.

## Pipeline

1. **Calibration** (`src/s4_endogenous/calibrate.py`)
   - Inputs (SHA256 in `data_manifest.json`): `launches`, `protocol_config`,
     `coverage_ledger` under `data/canonical/v1/base/`.
   - Join `token_id`; creator from `protocol_config.creator`; versions restricted
     to `v4.0_mev_or_hook` / `v4.1_mev_or_hook`.
   - Eligible creators: ≥3 launches in the 21-day calibration pre-period
     2025-08-18..2025-09-07 → **1,379** (matches the plan audit).
   - Never-v4.1: no `v4.1_mev_or_hook` launch in the full observed window
     2025-08-18..2025-10-01 → **1,121** (matches the plan audit).
   - Outcome `y = log1p(daily launch count)` on the eligible × 21-day panel.
     Two-way fixed effects: creator intercepts, weekday effects (mean-zero).
     Per-creator OLS of `y − weekday` on `[1, t−9.5]` gives baseline `a_i` and
     latent pretrend slope `b_i`; residuals `r_i` (21-vector).
   - Residual pool: `r_i` of the 1,121 never-v4.1 creators.
   - Cohort proportions: empirical first-v4.1 distribution of eligible creators
     over 2025-09-24..2025-10-01: sizes 60, 78, 26, 22, 15, 17, 22, 16 (sum 256).
     (The S1-rule variant — ≥3 v4.0 launches before first v4.1 — is reported in
     `calibration_summary.json` for reference only.)

2. **DGP** (`src/s4_endogenous/dgp.py`), per replication:
   - Pseudo panel: 60 days, day 0 = Monday 2025-08-18 (weekday alignment).
   - `y0[i,d] = a_i + weekday[d] + b_i·(d−9.5) + resid60[i,d]`, where `resid60`
     is a never-v4.1 residual block drawn with replacement, circularly shifted,
     tiled to 60 days.
   - Propensity `p_i = logit⁻¹(α + γ·z(b_i))`; α solved by bisection so
     `mean(p_i) = 0.40`. Treated share gate [0.35, 0.45]; on violation only α is
     adjusted and assignment redrawn once (never triggered in the formal run).
   - Treated creators draw cohort k ∝ empirical proportions; adoption day
     24+k (k=0..7). Every cohort has event-time −7..7 support.
   - Arms: zero (no injection) / positive (+0.20 log from adoption day).
   - Seeds: `sha256("S4|<gamma>|<arm>|<rep>")` → uint32 → `numpy.PCG64`.
   - Oracle fields `b_i, p_i, y0, treated, adopt, true_ATT` are kept in Python;
     the estimator payload contains only `(id, t, y, g)` (binary float64/int32).

3. **Estimation** (`R/estimate_batch.R`, one Rscript call per 50-replication batch,
   `parallel::mclapply` over replications):
   - Static TWFE: base-R two-way within transformation, single post indicator,
     cluster-robust SE by creator (CR1 correction).
   - Callaway–Sant'Anna: `did::att_gt` 2.1.2 with locked parameters
     `control_group="nevertreated", base_period="universal", est_method="reg",
     anticipation=0, panel=TRUE`; then
     `aggte(type="dynamic", min_e=-7, max_e=7, balance_e=7)`; event-time-0 ATT.
     Inference mode (not fixed by the plan): `bstrap=FALSE, cband=FALSE` on both
     calls — pointwise analytic influence-function standard errors, the same IF
     representation `honest_did.AGGTEobj` uses internally; deterministic, no
     bootstrap Monte Carlo error in SEs. Point estimates are unaffected.
   - Sensitivity: `HonestDiD` 0.2.8,
     `honest_did(es, e=0, type="relative_magnitude", Mbarvec=c(0.5,1,1.5,2),
     gridPoints=100)`. Note: in CRAN 0.2.8 the generic is not exported
     (verified: `honest_did` and `honest_did.AGGTEobj` exist in the package
     namespace but are absent from its export list), so the pipeline calls the
     identical function as `HonestDiD:::honest_did`. Primary deviation
     `Mbar=1`. Robust value = smallest Mbar in the registered grid whose
     interval contains 0 (`Inf` if none ≤ 2).
   - Diagnostics: event-time leads e=−7..−2; pretrend joint Wald test on the
     leads using the influence-function VCV exactly as
     `honest_did.AGGTEobj` constructs it (`crossprod(IF)/n²`); pre-period
     slope-difference t-test (per-creator slopes over t=1..23).
   - Locked validation before estimation: universal base period support
     (`g−1 ≥ 1` per cohort) and continuous event-time coefficients −7..7;
     violations mark the replication `unestimable` (no algorithm swap).

4. **Scoring & summary** (`src/s4_endogenous/summarize.py`, rules in
   `claim_scoring.yaml`): point claims from the original (Mbar=0) 95% CI;
   procedure claims from the Mbar=1 robust interval; MCSEs reported for bias
   and all rates. The locked conservative score is retained unchanged. A
   secondary `conditional_claim_accuracy_m1` separately records whether the
   Mbar=1 interval covers the known simulation truth and makes the correct sign
   classification. It is a sensitivity-qualified metric, not unconditional
   causal identification. Definitions are written to
   `artifacts/scoring_interpretation.json`.

## Environment

- Python 3.12.13 (uv-managed), experiment-local venv: numpy 2.5.2, pandas 3.0.5,
  pyarrow 25.0.1 — the only Python packages, per plan.
- R 4.6.1 (Homebrew, user-approved 2026-08-13). Experiment-local library
  `R/library`: did 2.1.2, HonestDiD 0.2.8, plus CRAN-resolved dependencies.
  System build tools required by those dependencies: rust, cmake, glpk
  (Homebrew). No shared project configuration was modified.
- Python↔R bridge: raw little-endian binary payloads + CSV meta; no extra R
  packages.

## Formal run

- 6 cells: γ ∈ {0, 0.75, 1.5} × arms {zero, positive}; 2,000 replications each.
- Reproduce: see the fresh rerun command in `RESULTS.md`.
