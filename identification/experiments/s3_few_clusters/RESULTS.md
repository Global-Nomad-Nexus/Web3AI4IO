# RESULTS — S3 few-platform-clusters inference experiment

Spec: `Web3AI4IO/identification/experiment_plans/S3_few_platform_clusters.md`
(2026-08-13 revision). All numbers below were computed by
`src/run_experiment.py` (10,000 reps per arm; sources:
`artifacts/results_summary.csv`, `artifacts/null_pvalue_diagnostics.csv`,
`calibration_summary.json`). Claim boundary: PumpSwap-panel-calibrated
inference evaluation only — nothing here is a statement about the real
PumpSwap treatment effect.

## Scale check (revised s_ATT rule) — PASS

- Pilot: 2,000 zero-arm reps, seed 20260813, assignment `pump_ecosystem`,
  same DGP/estimator/window as the full run.
- **s_ATT = 0.706190** (pilot mean estimate 0.00499, consistent with an
  unbiased null estimator).
- 0.20 / s_ATT = **0.2832 ∈ [0.25, 1.0] → PASS**. The first run's blocker
  under the superseded residual-SD rule is lifted by the spec revision.
- Moderate arm effect = 0.5 × s_ATT = **0.353095** (fixed constant).

## Headline: zero-arm calibration (assignment `pump_ecosystem`)

| method | FPR @0.05 | MC SE | 95% CI coverage | mean CI width |
|---|---|---|---|---|
| baseline CRV1 + normal crit | **0.0646** | 0.0025 | 0.9354 | 2.353 |
| comparator A: CRV1 + t(3) crit | **0.0259** | 0.0016 | 0.9741 | 3.820 |
| comparator B: wild sign enum (16) | **0.0000** | 0.0000 | not_available | — |
| reference: randomization inference (4) | **0.0000** | 0.0000 | not_available | — |

- The baseline **does over-reject**: 6.46% vs the nominal 5% (≈ 5.9 Monte
  Carlo SEs above target). The CRV1 SE understates the true sampling SD of
  the estimator (E[SE] ≈ 0.60 vs SD(β̂) = 0.72 in the full zero arm), and its 95% CI
  under-covers at 93.5%.
- t(3) critical values correct too far: FPR 2.59%, CI over-covers at 97.4%.
- Wild sign enumeration and randomization inference have FPR exactly 0 —
  structurally: with 4 clusters the minimum attainable two-sided p is
  2/16 = 0.125 (wild) and 0.25 (randomization), so neither can ever reject
  at α = 0.05. Their zero FPR is a discreteness property, not evidence of
  superior calibration at finer α.

## Headline: power (assignment `pump_ecosystem`)

| arm (true ATT) | baseline | CRV1 + t(3) | wild enum | randomization |
|---|---|---|---|---|
| low_power (0.20 = 0.28·s_ATT) | **0.1289** (MC SE 0.0034) | 0.0541 (0.0023) | 0.0000 | n/a |
| moderate (0.353 = 0.5·s_ATT) | **0.2162** (MC SE 0.0041) | 0.1048 (0.0031) | 0.0000 | n/a |

Calibration gain vs baseline (zero arm): t(3) +0.0387; wild/RI +0.0646.
Power loss vs baseline: t(3) −0.0748 (low_power) and −0.1114 (moderate);
wild/RI lose all power at α = 0.05 by discreteness. Claim accuracy (zero:
correct non-rejection; injected: correct rejection) equals 1 − FPR and
power respectively and is tabulated in `results_summary.csv`.

## Honest reporting (spec §8.8)

1. CRV1 + normal crit over-rejects only mildly on the scientific target
   assignment (6.5% vs 5%). The few-cluster problem is real but not
   dramatic for `pump_ecosystem` treated.
2. The wild sign enumeration "improves" calibration only in the trivial
   sense that it can never reject at 5% with 4 clusters (smallest
   attainable p = 0.125). Reporting its FPR = 0 as a success would be
   misleading; it buys exactness at coarser α (e.g. α = 0.10 is also
   unattainable; the first attainable level is 0.125) at the cost of all
   power at conventional levels. Randomization inference over 4
   assignments is even coarser (min p = 0.25).
3. The moderate arm (0.5 × s_ATT) is still a low-power setting for every
   method: baseline power 21.6%. With residual SD ≈ 2.88 pooled (0.57–0.92
   within the three quieter units), even a 0.35-log-point effect over 30
   post days is hard to detect with 4 clusters.

## Placebo rotations (zero arm, all 4 treated identities)

FPR @0.05 per treated identity, baseline / t(3) (wild and RI are 0
everywhere by discreteness):

| treated identity | baseline CRV1+normal | CRV1+t(3) |
|---|---|---|
| pump_ecosystem | 0.0646 | 0.0259 |
| raydium | 0.0960 | 0.0368 |
| orca | 0.0652 | 0.0259 |
| meteora_combined | **0.9357** | **0.8968** |

The `meteora_combined` placebo collapses because the real meteora series
contains seven pre-period days with `log_volume = 0` (\$1-volume
placeholders, rel_day −90..−64) followed by a ramp from ≈17 to ≈23 in log
volume. Its pre-period residuals have SD 5.60 (vs 0.57–0.92 for the other
units) with block-level shifts that the 7-day moving-block bootstrap
propagates into the synthetic panels. The estimator stays unbiased
(E[β̂] ≈ +0.015 over reps) but CRV1 with one dominant cluster fails
completely: E[SE] = 0.091 vs true SD(β̂) = 2.000 (500-rep check; reproduced
with statsmodels, FPR 0.90 on 100 reps). Per spec §5.4 we do not interpret
this placebo as a real counterfactual event; it documents that no
4-cluster method calibrates a hypothetical meteora-treated design under
this panel's residual process.

## Artifacts

- `artifacts/results_long.parquet` — 190,000 rows: rep × method ×
  assignment (zero arm: methods 1–3 × 4 assignments + RI; injected arms:
  methods 1–3 × `pump_ecosystem`), with estimate, SE, t, p, CI bounds
  (NaN = not_available), reject_05, injected effect, true ATT.
- `artifacts/results_summary.csv` — per arm × method metrics incl. MC SEs,
  calibration gain, power loss, failure rate (0 everywhere).
- `artifacts/null_pvalue_diagnostics.csv` — zero-arm p-value quantiles,
  frac ≤ 0.05/0.10, distinct/attainable p-values, per method × assignment.
- `artifacts/sign_enumeration.csv` — 16 Rademacher vectors (cluster order
  `pump_ecosystem, raydium, orca, meteora_combined`).
- `artifacts/treatment_permutations.csv` — 4 treated-identity assignments.
- `artifacts/rep_construction.parquet` — per-rep RNG descriptor + 13
  block-start indices (full Y0 reconstruction).
- `artifacts/run_metadata.json` — seeds, effects, s_ATT, runtime.
- `artifacts/figure_s3.pdf` / `.png` — zero-arm p-value histograms,
  rejection-rate bars by arm, CI coverage, zero-arm estimate distribution.
- `calibration_summary.json` — revised scale check (status OK).

## Runtime

Pilot 0.08 s + full run 1.53 s ≈ **1.6 s total** (single process, Apple
Silicon), versus the 30-minute budget — the closed-form vectorized
estimator makes 30,000 reps × (1 fit + 16 wild refits [+ 4 RI fits in the
zero arm]) trivially cheap. Tests: 17 passed (see VALIDATION.md).
