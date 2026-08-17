"""Semi-synthetic DGP for experiment S3 (few platform clusters).

Spec: Web3AI4IO/Claire/experiment_plans/S3_few_platform_clusters.md (sec. 3,
revised 2026-08-13).

Construction:
  1. Fit log_volume on 4 unit FE + weekday dummies (Monday reference) using
     the 360 real rows with rel_day in [-90, -1]. Residuals
     u_it = y - unitFE_i - weekday_{d(t)} retain the common day shock xi_t by
     construction, so resampling whole day-vectors u_t = (u_1t..u_4t)
     preserves contemporaneous cross-market dependence.
  2. Untreated synthetic panel for rel_day in [-60, 29] (90 days x 4 units):
     Y0_it = unitFE_i + weekday_{d(t)} + u*_it, where u* is a 7-day
     moving-block bootstrap over the 90 pre-period residual day-vectors and
     the weekday of a synthetic rel_day is the weekday of the real panel date
     at that rel_day.
  3. Treatment assignment is drawn independently of the resampled blocks
     (here assignments are fixed by arm design, which is trivially
     independent of the bootstrap RNG stream).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.validate_panel import PANEL_CSV, EXPECTED_UNITS, fit_preperiod

N_UNITS = 4
SYNTH_REL_DAY_MIN, SYNTH_REL_DAY_MAX = -60, 29  # estimation window, inclusive
N_DAYS = SYNTH_REL_DAY_MAX - SYNTH_REL_DAY_MIN + 1  # 90
POST_START_ROW = 60  # row index of rel_day = 0 inside the window
BLOCK_LEN = 7
N_PRE_DAYS = 90  # rel_day -90..-1


@dataclass(frozen=True)
class DGPComponents:
    """Fixed quantities estimated once from the real panel."""

    unit_fe: np.ndarray          # (4,) unit fixed effects, EXPECTED_UNITS order
    weekday_eff: np.ndarray      # (7,) weekday effects, Monday (0) = reference 0
    resid_matrix: np.ndarray     # (90, 4) pre-period residuals u_it, day-major
    weekday_of_row: np.ndarray   # (90,) weekday (0=Mon) for rel_day -60..29
    unit_fe_table: dict          # unit name -> FE, for documentation


def load_dgp_components() -> DGPComponents:
    """Fit the pre-period model on the real panel and extract components."""
    df = pd.read_csv(PANEL_CSV)
    pre = fit_preperiod(df)  # rel_day -90..-1, columns include u and weekday

    # Unit FE + weekday effects: recompute the fitted decomposition so that
    # fitted = unit_fe[unit] + weekday_eff[weekday], Monday reference = 0.
    pre = pre.copy()
    x_unit = pd.get_dummies(pre["unit"])[EXPECTED_UNITS].astype(float)
    x_wd = pd.get_dummies(pre["weekday"]).astype(float)
    for d in range(7):
        if d not in x_wd.columns:
            x_wd[d] = 0.0
    x_wd = x_wd[sorted(x_wd.columns)].drop(columns=[0])
    X = np.column_stack([x_unit.values, x_wd.values])
    beta, _, rank, _ = np.linalg.lstsq(X, pre["log_volume"].values, rcond=None)
    if rank != 10:
        raise RuntimeError(f"pre-period design rank {rank} != 10")
    unit_fe = beta[:N_UNITS]
    weekday_eff = np.zeros(7)
    weekday_eff[1:] = beta[N_UNITS:]

    # Residual day-vectors, day-major over rel_day -90..-1.
    resid = (
        pre.sort_values(["rel_day", "unit"])
        .pivot(index="rel_day", columns="unit", values="u")
        [EXPECTED_UNITS]
        .values
    )
    if resid.shape != (N_PRE_DAYS, N_UNITS):
        raise RuntimeError(f"residual matrix shape {resid.shape}")
    if not np.isfinite(resid).all():
        raise RuntimeError("non-finite pre-period residuals")

    # Weekday of each synthetic rel_day from the real panel date mapping.
    day_map = (
        df[["rel_day", "date_str"]]
        .drop_duplicates()
        .assign(date=lambda d: pd.to_datetime(d["date_str"]))
    )
    day_map["weekday"] = day_map["date"].dt.dayofweek
    wd = day_map.set_index("rel_day")["weekday"]
    weekday_of_row = np.array(
        [int(wd.loc[r]) for r in range(SYNTH_REL_DAY_MIN, SYNTH_REL_DAY_MAX + 1)]
    )

    return DGPComponents(
        unit_fe=unit_fe,
        weekday_eff=weekday_eff,
        resid_matrix=resid,
        weekday_of_row=weekday_of_row,
        unit_fe_table=dict(zip(EXPECTED_UNITS, unit_fe.tolist())),
    )


def moving_block_bootstrap(
    rng: np.random.Generator, resid_matrix: np.ndarray, n_days: int = N_DAYS,
    block_len: int = BLOCK_LEN,
) -> tuple[np.ndarray, np.ndarray]:
    """7-day moving-block bootstrap of residual day-vectors.

    Returns (u_star (n_days, 4), block_starts (n_blocks,)). Blocks are
    consecutive day-vectors drawn with replacement; start indices are uniform
    over {0, ..., n_pre - block_len}. The last partial block is truncated, so
    n_blocks = ceil(n_days / block_len).
    """
    n_pre = resid_matrix.shape[0]
    n_blocks = -(-n_days // block_len)  # ceil
    starts = rng.integers(0, n_pre - block_len + 1, size=n_blocks)
    rows = np.concatenate(
        [resid_matrix[s : s + block_len] for s in starts], axis=0
    )[:n_days]
    return rows, starts


def rep_rng(arm_seed: int, rep_id: int) -> np.random.Generator:
    """Independent, fully recorded RNG stream per replication."""
    return np.random.default_rng(np.random.SeedSequence([arm_seed, rep_id]))


def build_y0_panel(
    comp: DGPComponents, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """One untreated synthetic panel, day-major (90 days x 4 units).

    Y0_it = unitFE_i + weekday_eff[weekday(rel_day t)] + u*_it.
    Returns (Y0 (90, 4), block_starts) so the panel is exactly reconstructable
    from (arm_seed, rep_id, block_starts).
    """
    u_star, starts = moving_block_bootstrap(rng, comp.resid_matrix)
    y0 = (
        comp.unit_fe[None, :]
        + comp.weekday_eff[comp.weekday_of_row][:, None]
        + u_star
    )
    return y0, starts


def inject_effect(y0: np.ndarray, treated_idx: int, effect: float) -> np.ndarray:
    """Constant log effect on rel_day 0..29 (rows 60..89) of the treated unit."""
    y = y0.copy()
    if effect != 0.0:
        y[POST_START_ROW:, treated_idx] += effect
    return y
