"""Calibration object for the S1 semi-synthetic DGP.

Estimated from eligible never-adopter creators only (both hurdle layers):
  layer 1: per-creator activity probability (empirical active-day share over
           the 45-day window) + day-of-week activity multipliers
  layer 2: per-creator mean launch count given active + day-of-week count
           multipliers
Strata: pre-period (2025-08-18..2025-09-23) launch-rate quintiles.

Day-of-week (not per-calendar-day) multipliers are used so the 45-day
empirical calendar pattern extends cleanly to the 60-day pseudo panel;
panel day 0 is anchored to the weekday of 2025-08-18 (Monday).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from panel import WINDOW_DAYS, eligible_never_adopters, load_panel, never_adopter_strata

PANEL_ANCHOR_WEEKDAY = pd.Timestamp("2025-08-18").weekday()  # Monday = 0


@dataclass
class Calibration:
    pool_p_active: np.ndarray  # per pool creator, P(active on a day)
    pool_mu_count: np.ndarray  # per pool creator, E[count | active]
    pool_stratum: np.ndarray  # per pool creator, quintile 0..4
    act_mult_dow: np.ndarray  # shape (7,), mean 1
    cnt_mult_dow: np.ndarray  # shape (7,), mean 1
    outcome_sd: float  # SD of log1p count over pool creator-days
    n_pool: int

    def dow(self, n_days: int) -> np.ndarray:
        return (PANEL_ANCHOR_WEEKDAY + np.arange(n_days)) % 7


def build_calibration(df: pd.DataFrame | None = None) -> Calibration:
    if df is None:
        df = load_panel()
    never_ids = eligible_never_adopters(df)
    strata = never_adopter_strata(df, never_ids)

    sub = df[df["creator"].isin(never_ids)]
    counts = sub.groupby(["creator", "date"]).size().rename("n").reset_index()
    grid = pd.MultiIndex.from_product(
        [pd.Index(never_ids, name="creator"), WINDOW_DAYS], names=["creator", "date"]
    )
    panel = counts.set_index(["creator", "date"]).reindex(grid, fill_value=0).reset_index()
    panel["dow"] = panel["date"].dt.weekday.to_numpy()
    panel["active"] = panel["n"] > 0

    y = np.log1p(panel["n"].to_numpy(dtype=float))
    outcome_sd = float(y.std(ddof=1))

    p_active = panel.groupby("creator")["active"].mean().reindex(never_ids).to_numpy()
    mu_count = (
        panel[panel["active"]].groupby("creator")["n"].mean().reindex(never_ids).to_numpy()
    )

    p_day = panel.groupby("dow")["active"].mean()
    act_mult = (p_day / p_day.mean()).reindex(range(7)).to_numpy()
    mu_day = panel[panel["active"]].groupby("dow")["n"].mean()
    cnt_mult = (mu_day / mu_day.mean()).reindex(range(7)).to_numpy()

    return Calibration(
        pool_p_active=p_active.astype(float),
        pool_mu_count=mu_count.astype(float),
        pool_stratum=strata.reindex(never_ids).to_numpy(dtype=int),
        act_mult_dow=act_mult.astype(float),
        cnt_mult_dow=cnt_mult.astype(float),
        outcome_sd=outcome_sd,
        n_pool=len(never_ids),
    )


def stratified_draw(cal: Calibration, n: int, rng: np.random.Generator) -> np.ndarray:
    """Indices into the never-adopter pool, stratified by launch-rate quintile.

    Stratum allocations follow the pool composition (largest remainder);
    sampling within a stratum is uniform with replacement.
    """
    strata = cal.pool_stratum
    counts = np.bincount(strata, minlength=5)
    raw = counts / counts.sum() * n
    alloc = np.floor(raw).astype(int)
    remainder = n - alloc.sum()
    if remainder > 0:
        order = np.argsort(-(raw - alloc))
        alloc[order[:remainder]] += 1
    out = []
    for s in range(5):
        idx = np.flatnonzero(strata == s)
        if alloc[s] > 0:
            out.append(rng.choice(idx, size=alloc[s], replace=True))
    draw = np.concatenate(out)
    rng.shuffle(draw)
    return draw
