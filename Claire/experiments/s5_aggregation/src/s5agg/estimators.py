"""Estimators for S5 (plan S2 and S4).

All four methods estimate the same target: the average log ATT of
pump_ecosystem vs the equal-weight mean of the three controls over
rel_day = 0..6. Every method is a linear functional of the daily treated-control
difference series D_t = log_volume_pump,t - mean(log_volume_control,t) over the
42-day union window, because each weekly bin difference equals the within-bin
mean of D_t (weekly means are taken within unit first, then pump minus the
equal-weight control mean).

Weekday-alignment sensitivity (plan S5): offset k moves the event to weekday
(Thursday + k) mod 7. Equivalently the Monday-to-Sunday bin edges shift by k
days relative to event time, while the effect path stays in event time. For
offset k the event week contains w = (3 + k) mod 7 pre-event days and 7 - w
target post days.

With the plan's windows the daily DiD and the event-aligned seven-day DiD are
algebraically identical (four equal-size pre bins vs a 28-day pre mean, one
identical 7-day post window); both are reported separately as the plan requires.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import paths

WINDOW_LEN = 42  # six 7-day bins fully covering rel_day=-28..6
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def offset_params(k: int) -> dict:
    """Window structure for weekday offset k (0 = Thursday, the primary)."""
    if not 0 <= k <= 6:
        raise ValueError("offset must be in 0..6")
    w = (3 + k) % 7  # number of pre-event days in the event week
    s = -(w + 28)    # rel_day of the first day of the six-bin window
    exposures = np.array([0.0, 0.0, 0.0, 0.0, (7 - w) / 7, w / 7])
    return {
        "offset": k,
        "event_weekday_idx": w,
        "event_weekday": WEEKDAY_NAMES[w],
        "pre_days_in_event_week": w,
        "window_start_rel_day": s,
        "window_end_rel_day": s + WINDOW_LEN - 1,
        "exposures": exposures,
        "contamination_share": w / 7,  # share of event-week days that are pre-event
    }


def estimator_weights(k: int) -> np.ndarray:
    """Weight matrix W of shape (42, 4); column order = paths.METHODS.

    estimate = D_window @ W[:, m], where D_window[i] is D_t at
    rel_day = window_start + i.
    """
    p = offset_params(k)
    s = p["window_start_rel_day"]
    rel = s + np.arange(WINDOW_LEN)
    W = np.zeros((WINDOW_LEN, len(paths.METHODS)))

    # daily DiD: mean(D, rel_day 0..6) - mean(D, rel_day -28..-1)
    daily = np.zeros(WINDOW_LEN)
    daily[(rel >= 0) & (rel <= 6)] = 1.0 / 7
    daily[(rel >= -28) & (rel <= -1)] = -1.0 / 28

    # naive calendar-week DiD: mean of the two post-labelled weekly differences
    # minus mean of the four pure-pre weekly differences
    naive = np.zeros(WINDOW_LEN)
    naive[28:42] = 1.0 / 14   # bins 4 and 5 labelled post
    naive[0:28] = -1.0 / 28   # bins 0..3 pure pre

    # exposure-weighted calendar-week DiD: OLS of D_w on exposure_w (with intercept)
    x = p["exposures"]
    xbar = x.mean()
    sxx = float(((x - xbar) ** 2).sum())
    c = (x - xbar) / sxx      # regression coefficient of weekly difference m_j
    exposure = np.repeat(c / 7.0, 7)

    # event-aligned seven-day DiD: post bin rel_day 0..6 minus mean of the four
    # pre seven-day bin differences (rel_day -28..-1); identical to daily here
    aligned = daily.copy()

    W[:, 0] = daily
    W[:, 1] = naive
    W[:, 2] = exposure
    W[:, 3] = aligned
    return W


def daily_difference(panel_window: np.ndarray) -> np.ndarray:
    """D_t from a (..., 42, 4) panel window (pump must be column 0)."""
    return panel_window[..., 0] - panel_window[..., 1:].mean(axis=-1)


def window_slice(panel: np.ndarray, k: int) -> np.ndarray:
    """Slice the (n, 84, 4) simulated panel to the 42-day window of offset k."""
    s = offset_params(k)["window_start_rel_day"]
    i0 = s + 56  # rel_day -56 is index 0 of the simulated panel
    return panel[:, i0 : i0 + WINDOW_LEN, :]


def point_estimates(panel_window: np.ndarray, W: np.ndarray) -> np.ndarray:
    """(n, 42, 4) panel window -> (n, 4) estimates, column order paths.METHODS."""
    return daily_difference(panel_window) @ W


def bin_composition(k: int) -> list[dict]:
    """Per-bin target-day composition for offset k (one row per bin)."""
    p = offset_params(k)
    s = p["window_start_rel_day"]
    event = pd.Timestamp(paths.EVENT_DATE)
    rows = []
    for j in range(6):
        start = s + 7 * j
        days = np.arange(start, start + 7)
        n_target = int(((days >= 0) & (days <= 6)).sum())
        n_pre = int((days < 0).sum())
        n_post_nontarget = int((days > 6).sum())
        if j < 4:
            label = "pre"
        elif j == 4:
            label = "event_week"
        else:
            label = "post_partial"
        rows.append(
            {
                "offset": k,
                "event_weekday": p["event_weekday"],
                "bin_index": j,
                "bin_label": label,
                "start_rel_day": int(start),
                "end_rel_day": int(start + 6),
                "start_date": (event + pd.Timedelta(days=int(start))).strftime("%Y-%m-%d"),
                "end_date": (event + pd.Timedelta(days=int(start + 6))).strftime("%Y-%m-%d"),
                "n_target_days_rel0_6": n_target,
                "n_pre_event_days": n_pre,
                "n_post_nontarget_days": n_post_nontarget,
                "exposure_weight": n_target / 7.0,
                "event_week_contamination_share": p["contamination_share"] if j == 4 else 0.0,
            }
        )
    return rows
