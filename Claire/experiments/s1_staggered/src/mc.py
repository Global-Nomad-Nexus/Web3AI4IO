"""Monte Carlo replication driver for the S1 experiment.

One replication: simulate the 60-day pseudo panel (hurdle DGP), compute true
cohort-time ATT from the generating intensities on the shared support, and
run both estimators (static TWFE, CS-style group-time ATT). Seeds use
three-level independent streams: SeedSequence(scenario_seed) -> spawn per arm
-> spawn per replication.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from calibration import Calibration
from dgp import ARMS, simulate_panel
from estimators import cs_att_estimate, twfe_estimate
from truth import build_cell_grid, cell_true_att, overall_true_att, support_mask

SCENARIO_SEED = 20250826  # registered in design_lock.yaml
N_BOOT = 1999
CONTROL_RATIO = 3  # simulated never-treated controls per treated creator


@dataclass
class RepOutput:
    rows: list[dict]  # one row per method
    truth_cells: list[dict]  # one row per cohort-time cell


def arm_seed_sequence(arm: str, scenario_seed: int = SCENARIO_SEED) -> np.random.SeedSequence:
    root = np.random.SeedSequence([scenario_seed])
    arm_index = ARMS.index(arm)
    return root.spawn(len(ARMS))[arm_index]


def run_replication(
    cal: Calibration,
    arm: str,
    rep: int,
    rep_rng: np.random.Generator,
    cohort_sizes: list[int],
    adoption_days: list[int],
    n_days: int = 60,
    n_boot: int = N_BOOT,
    n_control: int | None = None,
) -> RepOutput:
    if n_control is None:
        n_control = CONTROL_RATIO * int(sum(cohort_sizes))
    t0 = time.perf_counter()

    panel = simulate_panel(cal, cohort_sizes, adoption_days, arm, rep_rng, n_control, n_days)
    grid = build_cell_grid(cohort_sizes, adoption_days, n_days)
    mask = support_mask(panel.y, panel.cohort, grid)

    cell_att_true = cell_true_att(panel, grid)
    true_overall = overall_true_att(cell_att_true, grid, mask)

    twfe = twfe_estimate(
        panel.y, panel.cohort, panel.adoption_day,
        support=mask, grid=grid, n_cohorts=len(cohort_sizes),
    )
    cs = cs_att_estimate(panel.y, panel.cohort, grid, mask, rep_rng, n_boot=n_boot)

    elapsed = time.perf_counter() - t0

    def method_row(method: str, est: float, se: float, lo: float, hi: float,
                   unestimable: bool, extra: dict) -> dict:
        covered = bool(lo <= true_overall <= hi) if not unestimable else False
        reject = bool((lo > 0) or (hi < 0)) if not unestimable else False
        row = {
            "arm": arm,
            "rep": rep,
            "method": method,
            "estimate": est,
            "se": se,
            "ci_lo": lo,
            "ci_hi": hi,
            "true_att": true_overall,
            "error": est - true_overall if not unestimable else np.nan,
            "covered": covered,
            "reject_null": reject,
            "n_supported_cells": int(mask.sum()),
            "unestimable": bool(unestimable),
            "elapsed_sec": elapsed,
        }
        row.update(extra)
        return row

    rows = [
        method_row("twfe", twfe.estimate, twfe.se, twfe.ci_lo, twfe.ci_hi,
                   twfe.unestimable, {
                       "twfe_neg_weight_sum_treated": twfe.neg_weight_sum_treated,
                       **{f"twfe_w_cohort{c}": twfe.cohort_weight_share[c]
                          for c in range(len(cohort_sizes))},
                   }),
        method_row("cs_att", cs.estimate, cs.se, cs.ci_lo, cs.ci_hi,
                   cs.unestimable, {}),
    ]

    truth_cells = [
        {
            "arm": arm,
            "rep": rep,
            "cohort": int(grid.cohort[k]),
            "day": int(grid.day[k]),
            "relative_day": int(grid.day[k] - adoption_days[grid.cohort[k]]),
            "n_treated_cell": int(grid.n_treated[k]),
            "supported": bool(mask[k]),
            "true_att_cell": float(cell_att_true[k]),
        }
        for k in range(len(grid.cohort))
    ]
    return RepOutput(rows=rows, truth_cells=truth_cells)


def rep_rng(arm: str, rep: int, n_reps: int, scenario_seed: int = SCENARIO_SEED) -> np.random.Generator:
    seq = arm_seed_sequence(arm, scenario_seed).spawn(n_reps)[rep]
    return np.random.default_rng(seq)
