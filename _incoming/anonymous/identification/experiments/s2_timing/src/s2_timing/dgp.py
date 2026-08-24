"""Semi-synthetic DGP for the S2 announcement/activation timing experiment.

Calibration uses ONLY the observed clean pre period (2025-04-17..2025-05-07):
per-platform weekday cell means of log1p(outcome) (equivalent to OLS on
weekday fixed effects) and the paired daily residual vectors, which are
resampled with a circular 7-day moving-block bootstrap so same-day
Pump/Moonshot dependence is preserved.

Approved injected effects (plan-owner amendment 2026-08-13): post effect
0.15 log (primary) and 0.10 log (robustness); the anticipation-interval
effect keeps the plan's 0.08/0.20 = 0.4 ratio to the post effect.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

SIM_START = dt.date(2025, 4, 17)
SIM_END = dt.date(2025, 6, 3)
CLEAN_PRE_END = dt.date(2025, 5, 7)
ACTIVATION = dt.date(2025, 5, 13)
POST_START = dt.date(2025, 5, 14)
BLOCK = 7
ANTICIPATION_RATIO = 0.4  # plan: 0.08 interval vs 0.20 post

EFFECTS = {"primary": 0.15, "robustness": 0.10}
GAPS = [3, 5, 7, 10]  # announcement = ACTIVATION - gap days; 5 is the real setting
ARMS = ["zero", "no_anticipation", "anticipation"]
OUTCOMES = ["launches", "unique_creators"]
PLATFORMS = ["Pump.fun", "Moonshot"]


def sim_days() -> list[dt.date]:
    n = (SIM_END - SIM_START).days + 1
    return [SIM_START + dt.timedelta(days=i) for i in range(n)]


def announcement_date(gap: int) -> dt.date:
    return ACTIVATION - dt.timedelta(days=gap)


@dataclass
class Calibration:
    outcome: str
    pre_dates: list[dt.date]          # 21 clean-pre days
    resid: np.ndarray                 # (21, 2) paired residuals [Pump, Moonshot]
    weekday_mean: dict[int, float]    # per platform
    diff_resid_sd: float

    def mean_matrix(self, days: list[dt.date]) -> np.ndarray:
        """(T, 2) untreated mean of log1p(outcome) per platform."""
        out = np.zeros((len(days), 2))
        for p, plat in enumerate(PLATFORMS):
            wm = self.weekday_mean[plat]
            for t, d in enumerate(days):
                out[t, p] = wm[d.weekday()]
        return out


def calibrate(panel_path, outcome: str) -> Calibration:
    panel = pd.read_csv(panel_path, parse_dates=["cohort_date"])
    pre = panel[panel.gross_period == "pre"].copy()
    pre["y"] = np.log1p(pre[outcome])
    pre_dates = sorted(d.date() for d in pre.cohort_date.unique())
    weekday_mean = {}
    resid = np.zeros((len(pre_dates), 2))
    for p, plat in enumerate(PLATFORMS):
        sub = pre[pre.platform == plat]
        wm = sub.groupby(sub.cohort_date.dt.weekday).y.mean().to_dict()
        weekday_mean[plat] = wm
        vals = dict(zip(sub.cohort_date.dt.date, sub.y))
        for i, d in enumerate(pre_dates):
            resid[i, p] = vals[d] - wm[d.weekday()]
    diff = resid[:, 0] - resid[:, 1]
    return Calibration(outcome, pre_dates, resid, weekday_mean, float(diff.std(ddof=1)))


def bootstrap_indices(n_pre: int, n_days: int, n_rep: int, rng: np.random.Generator) -> np.ndarray:
    """Circular moving-block bootstrap indices, (n_rep, n_days) into 0..n_pre-1."""
    n_blocks = int(np.ceil(n_days / BLOCK))
    starts = rng.integers(0, n_pre, size=(n_rep, n_blocks))
    idx = (starts[:, :, None] + np.arange(BLOCK)) % n_pre
    return idx.reshape(n_rep, n_blocks * BLOCK)[:, :n_days]


def effect_path(days: list[dt.date], gap: int, arm: str, effect: float) -> np.ndarray:
    """Pump log-effect per day. Activation day itself carries the full effect;
    the partial-day discard is an estimation rule, not a DGP feature."""
    ann = announcement_date(gap)
    e = np.zeros(len(days))
    for t, d in enumerate(days):
        if d >= ACTIVATION:
            if arm in ("no_anticipation", "anticipation"):
                e[t] = effect
        elif arm == "anticipation" and d >= ann:
            e[t] = ANTICIPATION_RATIO * effect
    return e


def simulate(cal: Calibration, gap: int, arm: str, effect: float,
             n_rep: int, rng: np.random.Generator) -> tuple[np.ndarray, list[dt.date]]:
    """Returns d_t draws (n_rep, T) = log1p(Pump) - log1p(Moonshot), and days."""
    days = sim_days()
    idx = bootstrap_indices(len(cal.pre_dates), len(days), n_rep, rng)
    res = cal.resid[idx]                          # (n_rep, T, 2) paired
    z = cal.mean_matrix(days)[None, :, :] + res   # untreated log-outcomes
    z[:, :, 0] += effect_path(days, gap, arm, effect)[None, :]
    return z[:, :, 0] - z[:, :, 1], days
