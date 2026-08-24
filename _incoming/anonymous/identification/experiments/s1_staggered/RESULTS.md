# RESULTS — S1 Base Clanker v4.1 staggered adoption (semi-synthetic)

Formal run: 3 arms × 2,000 replications, all 12,000 arm×method runs valid
(unestimable rate 0.0). Wall time 1,988 s. Run config: `artifacts/run_config.json`;
per-replication rows: `artifacts/results_long.parquet`; metrics:
`artifacts/results_summary.csv` (rebuilt from the long results only, by `summarize.py`).

Scope (acceptance 8.8): conclusions apply to this Clanker-calibrated DGP family only.
Nothing here is an estimate of the real Clanker v4.1 effect, and nothing generalizes
across chains or platforms.

## Headline result

Under staggered adoption with effects that grow in exposure time and vary by cohort,
**static TWFE does not materially mis-aggregate the overall ATT in this DGP family**:
its bias stays ≤ 3.2% of the truth in relative terms with ~95% coverage, while the
group-time ATT estimator is equally unbiased but ~3.4× noisier (RMSE 0.0174–0.0176 vs
0.0051–0.0052) and therefore far less powerful. Per acceptance criterion 8.7, the
modern estimator shows no improvement here; the DGP was not tuned, and the result is
reported as-is.

Why TWFE does not break down (evidence: `artifacts/weight_diagnostics.csv`): its
implicit per-cohort weight shares (0.216, 0.305, 0.102, 0.105, 0.059, 0.078, 0.078,
0.058) closely track the registered treated creator-day cell-count shares (0.236,
0.321, 0.103, 0.102, 0.055, 0.069, 0.067, 0.048), and the registered heterogeneity is
symmetric — cohort modifiers sum to zero by construction and the exposure profile is
common across cohorts — so the weighted average TWFE recovers is nearly the registered
equal-weight ATT. The negative implicit weight mass on treated observations is large
(-1.0 against +2.0 positive mass), i.e. the Goodman-Bacon pathology is present at the
weight level, but in this design it does not translate into bias for the aggregate
estimand.

## Metrics per arm × method (n = 2,000 each)

### Zero arm (true ATT = 0)

| method | bias (MCSE) | RMSE | coverage 95 | FPR | claim accuracy |
|---|---|---|---|---|---|
| TWFE | -0.000442 (0.000112) | 0.0050 | 0.941 | 0.059 | 0.941 |
| CS-ATT | +0.000097 (0.000392) | 0.0175 | 0.936 | 0.064 | 0.936 |

### Homogeneous arm (true ATT = 0.008370)

| method | bias (MCSE) | relative bias | RMSE | coverage 95 | FNR | sign correct | claim accuracy |
|---|---|---|---|---|---|---|---|
| TWFE | +0.000266 (0.000116) | +3.2% | 0.0052 | 0.950 | 0.608 | 0.957 | 0.392 |
| CS-ATT | +0.000016 (0.000388) | +0.2% | 0.0174 | 0.9375 | 0.883 | 0.695 | 0.112 |

### Heterogeneous arm (true ATT = 0.014877)

| method | bias (MCSE) | relative bias | RMSE | coverage 95 | FNR | sign correct | claim accuracy |
|---|---|---|---|---|---|---|---|
| TWFE | +0.000038 (0.000115) | +0.3% | 0.0051 | 0.955 | 0.183 | 0.999 | 0.817 |
| CS-ATT | +0.000348 (0.000394) | +2.3% | 0.0176 | 0.9375 | 0.820 | 0.813 | 0.179 |

## Secondary findings

- Both estimators are essentially unbiased for the overall ATT in all arms; largest
  absolute relative bias is 3.2% (TWFE, homogeneous), within 2.3 MCSE of zero.
- Coverage is close to but slightly below nominal for CS-ATT (0.936–0.938; binomial
  MCSE 0.005) — the percentile multiplier bootstrap under-covers by ~1–1.5 points.
  TWFE coverage straddles nominal (0.941–0.955). Zero-arm FPR is slightly above 5%
  for both (0.059 TWFE, 0.064 CS-ATT).
- Power: the injected effects are small on the log1p scale (true overall ATT
  0.0084–0.0149 vs per-rep estimator SD ~0.005 TWFE / ~0.018 CS-ATT), so false-negative
  rates are high — but TWFE detects the heterogeneous-arm effect in 81.7% of
  replications vs 18.0% for CS-ATT. The group-time estimator pays a large variance
  penalty for using only day g−1 as base period and never-treated controls.
- The variance gap, not bias, is what differentiates the two estimators in this DGP
  family: sign correctness and claim accuracy track RMSE closely.

## Figure

`artifacts/figure_s1.pdf` / `.png`: bias and 95% coverage by arm and method
(rendered stdlib-only, see METHOD.md §7).
