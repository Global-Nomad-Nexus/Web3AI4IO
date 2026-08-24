# S2 validation

## Input and scope checks (reproducible via `src/s2_timing/calibrate.py`)

| # | Check | Result |
|---|---|---|
| 1 | Registry contains exactly one `PUMP_CREATOR_FEE_20250513` row | PASS |
| 2 | Registry `effective_at_utc` = 2025-05-13T11:27:06Z | PASS |
| 3 | Registry onchain ref contains upgrade tx `4NK8jLTK…vGm` | PASS |
| 4 | Registry onchain ref contains first payment tx `5rj8FxQ8…zs` | PASS |
| 5 | Registry `anticipation_days` = 5 (announcement 2025-05-08) | PASS |
| 6 | Evidence file contains both transactions and 2025-05-13 11:27:06 UTC | PASS |
| 7 | Evidence file records 2025-05-08 first public documentation | PASS |
| 8 | Panel = 156 platform-day rows | PASS |
| 9 | Clean pre 2025-04-17..2025-05-07 complete, 21 d per platform | PASS |
| 10 | Clean post 2025-05-14..2025-06-03 complete, 21 d per platform | PASS |
| 11 | No panel rows inside 2025-05-08..2025-05-13 | PASS |
| 12 | Original 0.20 effect vs scale gate [0.25, 1.0]× pre residual SD | FAIL (1.148 / 1.220) → stopped, reported |
| 13 | Approved effects vs same gate: 0.15 → 0.861/0.915; 0.10 → 0.574/0.610 | PASS |

## Implementation verification

- OLS + Newey-West HAC lag 7 cross-checked against `statsmodels` HAC on
  multiple reps: coefficient and SE agreement to 5 decimal places (both the
  treatment regression and the gate regression).
- Gate-coefficient sampling SD vs mean HAC SE measured directly (ratio 2.44 at
  T=26) and plain-OLS SE checked against the analytic iid variance — the
  gate's high false-rejection rate is a property of the prescribed procedure,
  not of the implementation.
- Tests: `pytest tests/ -q` → **6 passed**, covering same-day announcement
  (gap 0, gate cannot fire), partial activation-day dropping, no-anticipation
  arm path, true-anticipation arm path, paired 7-day moving-block bootstrap
  (block structure and same-day pair preservation), and estimator sanity.

## Acceptance criteria (plan section 8)

1. Event dates, transactions, files, outcomes, windows as specified — PASS
2. Only clean-pre data calibrate the untreated process — PASS
3. Announcement / activation / anticipation as independent fields — PASS
   (`timing_evidence_map.json`)
4. All methods estimate the same 21-day target (2025-05-14..2025-06-03) — PASS
5. ≥ 2,000 runs per cell with MC standard errors — PASS (2,000 × 48 cells;
   `bias_mcse`, `coverage_mcse`, `claim_accuracy_mcse` reported)
6. Tests cover the five mandated scenarios — PASS (6 tests)
7. Fresh rerun rebuilds results — PASS (deterministic per-cell seeds; rerun
   reproduces `results_summary.csv` byte-identically)
8. No tuning of gap or effect after seeing results — PASS (effects are the
   plan-owner amendment, fixed before the first formal run; verified-timing
   improvement reported as-is, including the gate's failure)
9. Conclusions limited to the Pump/Moonshot-calibrated timing protocol — PASS
   (no real treatment-effect claim; Moonshot never called a causal control)

## Stop-condition audit (plan section 9)

- Panel dates complete; evidence matches registry; clean pre (21 d) sufficient
  for the 7-day block bootstrap; no shared-environment modification
  (experiment-local `.venv` only; shared inputs read-only, sha256 in
  `data_manifest.json`); no old joint/archive synthetic results read.

## Fresh rerun

```bash
cd identification/experiments/s2_timing
.venv/bin/python -m pytest tests/ -q          # 6 passed
.venv/bin/python src/s2_timing/run_mc.py      # ~8 s, rebuilds artifacts
.venv/bin/python src/s2_timing/make_figure.py
```

Last rerun: artifacts deleted and regenerated; `results_summary.csv`
byte-identical to the previous run.
