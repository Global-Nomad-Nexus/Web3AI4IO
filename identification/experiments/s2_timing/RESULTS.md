# S2 results: announcement vs activation timing

Semi-synthetic Monte Carlo, 2 outcomes × 2 effect sizes (0.15 primary /
0.10 robustness log) × 4 announcement gaps (3/5/7/10 days) × 3 arms × 3
methods, **2,000 replications per cell, 96,000 total**. Effects are the
plan-owner-approved amendment (2026-08-13) after the original 0.20 failed the
scale gate; anticipation-interval effect = 0.4× post effect. All numbers below
are simulation evidence about the **timing protocol**, calibrated on
Pump/Moonshot clean-pre noise — they say nothing about any real treatment
effect, and Moonshot is not claimed as a causal control.

## 1. Headline: misdating treatment to the announcement attenuates the estimate

Launches, primary effect, gap = 5 (the real setting), no-anticipation arm:

| Method | Bias | Attenuation ratio | Claim accuracy |
|---|---|---|---|
| Naive announcement | **-0.028** | **0.814** | 0.578 |
| Verified activation | -0.001 | 0.996 | 0.764 |
| Activation + gate | +0.005 | 1.032 | 0.757 |

Counting the 5 announcement-interval days as post dilutes the 21-day estimate
by ~19% (≈ 5/26 of the window carries no effect, as expected mechanically).
Verified activation removes this bias almost completely.

## 2. Anticipation arm: verified timing still helps; the gate helps least

Launches, primary effect, anticipation arm (0.06 log on 05-08..05-12):

| Gap | Naive att. | Verified att. | Gate att. |
|---|---|---|---|
| 3 | 0.931 | 0.955 | 0.960 |
| 5 | 0.890 | 0.928 | 0.958 |
| 7 | 0.849 | 0.875 | 0.906 |
| 10 | 0.814 | 0.839 | 0.872 |

Attenuation grows with the announcement gap for every method. Verified
activation is contaminated by keeping the anticipation interval in the pre
period; the gate's clean-pre/clean-post-only estimate recovers more of the
effect at short gaps (0.96 at gaps 3–5) but degrades at long gaps, where its
high unidentified rate (see §3) selects a non-representative subset of
replications. Secondary outcome (unique creators, gap 5): naive 0.907 /
verified 0.944 / gate 0.974 — same ordering.

## 3. The anticipation gate does not work at this noise level

Gate rejection rates (timing_gate_diagnostics.csv), launches, primary effect:

| Gap | Zero arm | No-anticipation | Anticipation (true positive) |
|---|---|---|---|
| 3 | 0.498 | 0.487 | 0.460 |
| 5 | 0.434 | 0.439 | 0.444 |
| 7 | 0.398 | 0.382 | 0.450 |
| 10 | 0.326 | 0.317 | 0.420 |

The prescribed HAC-7 Wald gate fires at 32–50% **even with no anticipation**,
and its true-positive rate (0.42–0.46) is barely different from its
false-positive rate — anticipation classification is near chance, and 33–50%
of replications are declared `unidentified`. Root cause, verified against
statsmodels (agreement to 5 decimals): at T ≈ 26 with a short, high-leverage
interval dummy (leverage 0.40), residual-based HAC-7 understates the gate
coefficient's SE by ≈ 2.4× (true SD 0.115 vs mean SE 0.047; plain OLS SE
matches the true SD). The pre-registered exclusion window therefore does **not**
reliably isolate anticipation under the calibrated noise; the gate's apparent
bias advantage in §2 comes at the cost of discarding up to half of all
replications for the wrong reason.

## 4. Caveat: HAC-7 inference undercovers for all methods

95% CI coverage is 0.79–0.89 and zero-arm FPR is 0.11–0.21 across all methods
(nominal 0.95 / 0.05). This is a small-sample property of the mandated
Newey-West lag-7 + normal-critical-value inference at T ≈ 42–47 under the
calibrated residual process (implementation cross-checked against
statsmodels). It inflates FPR and claim-error rates uniformly, so it does not
alter the method rankings above, but absolute coverage/FPR targets are not met
by any method.

## 5. Robustness effect (0.10 log)

Same patterns with lower power: gap-5 launches no-anticipation attenuation
0.813 (naive) / 0.999 (verified) / 1.038 (gate); anticipation arm
0.896 / 0.930 / 0.989; FNR rises to 0.50–0.61. Gate false-rejection remains
0.31–0.46 across arms.

## 6. Answers to the research questions

1. **How much attenuation from misdating treatment to the announcement?**
   ≈ 19% at the real 5-day gap (ratio 0.81), rising to ≈ 19–19% at 10 days
   (0.81); smaller when anticipation is present because the interval then
   carries part of the effect (0.89 at gap 5).
2. **Does verified activation fix it?** Yes for point estimates: bias ≈ 0
   without anticipation (ratio ≈ 1.00) and ≈ −7% with anticipation (0.93).
3. **Does the pre-registered exclusion window isolate anticipation?** No — the
   HAC-7 gate is near-chance at this noise level and discards 33–50% of
   replications as `unidentified` regardless of the truth.
4. **Coverage failure?** Systematic: 0.79–0.89 coverage for every method,
   driven by small-sample HAC-7 behavior, not by the timing choice.

Artifacts: `artifacts/results_long.parquet` (288,000 per-rep rows),
`artifacts/results_summary.csv` (144 cells), `artifacts/timing_gate_diagnostics.csv`,
`artifacts/figure_s2.pdf/.png`. Reproduction: see `METHOD.md` §Fresh rerun.
