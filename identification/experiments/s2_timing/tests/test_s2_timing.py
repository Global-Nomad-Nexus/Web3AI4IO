"""Tests for the S2 timing experiment code.

Covers the mandated scenarios: same-day announcement, partial activation day,
no anticipation, true anticipation, and the paired residual bootstrap.
"""

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s2_timing.dgp import (ACTIVATION, ANTICIPATION_RATIO, BLOCK, POST_START, Calibration,
                           announcement_date, bootstrap_indices, calibrate, effect_path,
                           sim_days, simulate)
from s2_timing.estimators import method_samples, run_methods

PANEL = Path(__file__).resolve().parents[3] / "data" / "pump_moonshot_cohort_panel.csv"
DAYS = sim_days()


def fake_calibration() -> Calibration:
    """Deterministic calibration with distinct residuals per pre day."""
    pre_dates = [dt.date(2025, 4, 17) + dt.timedelta(days=i) for i in range(21)]
    rng = np.random.default_rng(7)
    resid = rng.normal(0, 0.1, size=(21, 2))
    weekday_mean = {p: {w: 10.0 + 0.05 * w + (p == "Moonshot") for w in range(7)}
                    for p in ["Pump.fun", "Moonshot"]}
    return Calibration("launches", pre_dates, resid, weekday_mean, 0.1)


def test_same_day_announcement():
    """gap = 0: announcement interval is empty, gate cannot fire, every rep
    is identified, and the naive post indicator starts on the activation day."""
    assert announcement_date(0) == ACTIVATION
    samples = method_samples(DAYS, 0)
    assert samples["activation_plus_anticipation_gate"]["X_gate"] is None
    cal = fake_calibration()
    D, _ = simulate(cal, 0, "no_anticipation", 0.15, 50, np.random.default_rng(1))
    res = run_methods(D, samples)
    gate = res["activation_plus_anticipation_gate"]
    assert np.all(gate["gate_p"] == 1.0)
    assert not gate["unidentified"].any()
    assert not np.isnan(gate["beta"]).any()
    # naive post starts at announcement = activation day
    naive_days = [d for d in DAYS]
    post_col = samples["naive_announcement"]["X"][:, 7]
    assert post_col[naive_days.index(ACTIVATION)] == 1.0
    assert post_col[naive_days.index(ACTIVATION - dt.timedelta(days=1))] == 0.0


def test_partial_activation_day():
    """2025-05-13 is dropped by verified and gate samples, kept by naive."""
    samples = method_samples(DAYS, 5)
    idx = samples["verified_activation"]["idx"]
    kept = {DAYS[i] for i in idx}
    assert ACTIVATION not in kept
    assert ACTIVATION - dt.timedelta(days=1) in kept
    assert POST_START in kept
    naive_kept = {DAYS[i] for i in samples["naive_announcement"]["idx"]}
    assert ACTIVATION in naive_kept
    gate_kept = {DAYS[i] for i in samples["activation_plus_anticipation_gate"]["idx"]}
    assert all(d < dt.date(2025, 5, 8) or d >= POST_START for d in gate_kept)


def test_no_anticipation_arm():
    """No uplift inside the announcement interval, full effect after activation."""
    cal = calibrate(PANEL, "launches")
    D, days = simulate(cal, 5, "no_anticipation", 0.15, 2000, np.random.default_rng(2))
    D0, _ = simulate(cal, 5, "zero", 0.15, 2000, np.random.default_rng(2))
    uplift = D.mean(axis=0) - D0.mean(axis=0)
    ann = announcement_date(5)
    in_interval = [uplift[days.index(d)] for d in days if ann <= d < ACTIVATION]
    post = [uplift[days.index(d)] for d in days if d >= POST_START]
    assert np.all(np.abs(in_interval) < 0.02)
    assert abs(np.mean(post) - 0.15) < 0.02


def test_true_anticipation_arm():
    """0.4x effect inside the announcement interval, full effect afterwards."""
    cal = calibrate(PANEL, "unique_creators")
    D, days = simulate(cal, 5, "anticipation", 0.15, 2000, np.random.default_rng(3))
    D0, _ = simulate(cal, 5, "zero", 0.15, 2000, np.random.default_rng(3))
    uplift = D.mean(axis=0) - D0.mean(axis=0)
    ann = announcement_date(5)
    in_interval = [uplift[days.index(d)] for d in days if ann <= d < ACTIVATION]
    post = [uplift[days.index(d)] for d in days if d >= POST_START]
    assert abs(np.mean(in_interval) - ANTICIPATION_RATIO * 0.15) < 0.02
    assert abs(np.mean(post) - 0.15) < 0.02


def test_paired_residual_bootstrap():
    """Blocks are 7 long, circular, and each resampled day keeps an original
    same-day (Pump, Moonshot) residual pair."""
    rng = np.random.default_rng(4)
    idx = bootstrap_indices(21, 48, 200, rng)
    assert idx.shape == (200, 48)
    # block boundaries at multiples of 7: within a block, steps are +1 mod 21
    for r in range(200):
        for b in range(idx.shape[1] // BLOCK):
            block = idx[r, b * BLOCK:(b + 1) * BLOCK]
            assert np.all((block[1:] - block[:-1]) % 21 == 1)
    cal = calibrate(PANEL, "launches")
    pairs = {tuple(row) for row in cal.resid}
    res = cal.resid[idx]
    for r in range(res.shape[0]):
        for t in range(res.shape[1]):
            assert tuple(res[r, t]) in pairs


def test_methods_recover_true_effect():
    """Sanity: with no anticipation the verified and gate estimates are
    approximately unbiased for the 21-day post target, the naive estimate is
    attenuated when the announcement interval carries no effect."""
    cal = calibrate(PANEL, "launches")
    samples = method_samples(DAYS, 5)
    D, _ = simulate(cal, 5, "no_anticipation", 0.15, 2000, np.random.default_rng(5))
    res = run_methods(D, samples)
    assert abs(np.nanmean(res["verified_activation"]["beta"]) - 0.15) < 0.02
    assert abs(np.nanmean(res["activation_plus_anticipation_gate"]["beta"]) - 0.15) < 0.02
    assert np.nanmean(res["naive_announcement"]["beta"]) < 0.14
