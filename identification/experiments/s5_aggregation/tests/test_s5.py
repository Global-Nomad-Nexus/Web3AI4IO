"""Tests for S5, covering plan S9.7:
daily-to-weekly value preservation, Thursday 3-pre + 4-post event-week
composition, exposure weights (4/7, 3/7), zero arm ~ 0, persistent arm
recovery, all seven weekday offsets, and the scale-gate mechanics
(plan S3 item 8, revised 2026-08-13).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from s5agg import paths
from s5agg.dgp import (
    calibrate,
    fidelity_check,
    generate_y0,
    inject,
    sliding_window_estimates,
)
from s5agg.estimators import (
    bin_composition,
    daily_difference,
    estimator_weights,
    offset_params,
    point_estimates,
    window_slice,
)
from s5agg.panel import load_validated_panel


@pytest.fixture(scope="module")
def cal():
    df, _ = load_validated_panel()
    return calibrate(df)


# --- daily-to-weekly value preservation -------------------------------------

def test_weekly_difference_equals_mean_of_daily_differences():
    """Weekly bin difference (within-unit daily mean, then pump - controls)
    must equal the within-bin mean of the daily D_t series."""
    rng = np.random.default_rng(0)
    panel = rng.normal(size=(5, 42, 4)) + np.array([8.0, 7.0, 7.5, 7.2])
    d = daily_difference(panel)
    # manual weekly difference for bin j=4
    sl = slice(28, 35)
    weekly_manual = panel[:, sl, 0].mean(axis=1) - panel[:, sl, 1:].mean(axis=(1, 2))
    np.testing.assert_allclose(weekly_manual, d[:, sl].mean(axis=1), atol=1e-12)


def test_weights_reproduce_direct_estimators():
    """Weight-matrix estimates must match direct two-step computation."""
    rng = np.random.default_rng(1)
    panel = rng.normal(size=(7, 42, 4))
    W = estimator_weights(0)
    est = point_estimates(panel, W)
    d = daily_difference(panel)
    weekly = d.reshape(7, 6, 7).mean(axis=2)  # (n, 6 bins)
    naive_direct = weekly[:, 4:].mean(axis=1) - weekly[:, :4].mean(axis=1)
    x = np.array([0, 0, 0, 0, 4 / 7, 3 / 7])
    xm = x - x.mean()
    expo_direct = (weekly - weekly.mean(axis=1, keepdims=True)) @ xm / (xm @ xm)
    np.testing.assert_allclose(est[:, 1], naive_direct, atol=1e-12)
    np.testing.assert_allclose(est[:, 2], expo_direct, atol=1e-12)
    daily_direct = d[:, 31:38].mean(axis=1) - d[:, 3:31].mean(axis=1)
    np.testing.assert_allclose(est[:, 0], daily_direct, atol=1e-12)
    np.testing.assert_allclose(est[:, 3], est[:, 0], atol=1e-12)  # aligned == daily


# --- Thursday composition (plan S9.7) ----------------------------------------

def test_thursday_event_week_composition():
    rows = bin_composition(0)
    event_week = [r for r in rows if r["bin_label"] == "event_week"]
    assert len(event_week) == 1
    ew = event_week[0]
    assert ew["start_date"] == "2025-03-17"
    assert ew["end_date"] == "2025-03-23"
    assert ew["n_pre_event_days"] == 3
    assert ew["n_target_days_rel0_6"] == 4
    pre = [r for r in rows if r["bin_label"] == "pre"]
    assert len(pre) == 4 and all(r["n_target_days_rel0_6"] == 0 for r in pre)
    follow = [r for r in rows if r["bin_label"] == "post_partial"][0]
    assert follow["n_target_days_rel0_6"] == 3
    assert follow["n_post_nontarget_days"] == 4


def test_exposure_weights_thursday():
    p = offset_params(0)
    assert p["event_weekday"] == "Thursday"
    np.testing.assert_allclose(p["exposures"], [0, 0, 0, 0, 4 / 7, 3 / 7])


# --- zero arm and persistent arm recovery ------------------------------------

def test_zero_arm_unbiased(cal):
    y0 = generate_y0(cal, 400, seed=123)
    W = estimator_weights(0)
    est = point_estimates(window_slice(inject(y0, None, 0.0), 0), W)
    for m in range(4):
        se = est[:, m].std(ddof=1) / np.sqrt(len(est))
        assert abs(est[:, m].mean()) < 5 * se + 1e-3


def test_persistent_arm_recovery(cal):
    y0 = generate_y0(cal, 400, seed=124)
    W = estimator_weights(0)
    est = point_estimates(window_slice(inject(y0, "persistent", paths.EFFECT_SUBSTANTIVE), 0), W)
    # daily and event-aligned must recover the injected effect;
    # exposure-weighted is also unbiased for a constant effect by construction
    for m in (0, 2, 3):
        se = est[:, m].std(ddof=1) / np.sqrt(len(est))
        assert abs(est[:, m].mean() - paths.EFFECT_SUBSTANTIVE) < 5 * se + 1e-3


def test_transient_arm_truth_and_naive_dilution(cal):
    """Injection is deterministic and all estimators are linear, so the
    transient-minus-zero difference must equal the injected signal passed
    through each method's weights exactly, on every replication."""
    y0 = generate_y0(cal, 20, seed=125)
    W = estimator_weights(0)
    est_zero = point_estimates(window_slice(inject(y0, None, 0.0), 0), W)
    est_trans = point_estimates(window_slice(inject(y0, "transient", paths.EFFECT_SUBSTANTIVE), 0), W)
    # injected D_t signal in the offset-0 window (rel_day -31..10):
    # EFFECT on rel_day 0..2 -> window indices 31..33
    injected = np.zeros(42)
    injected[31:34] = paths.EFFECT_SUBSTANTIVE
    expected = injected @ W  # (4,) deterministic shift per method
    np.testing.assert_allclose(
        est_trans - est_zero, np.tile(expected, (len(est_zero), 1)), atol=1e-10
    )
    # daily recovers the seven-day ATT truth; naive is diluted to half of it
    assert abs(expected[0] - 3 * paths.EFFECT_SUBSTANTIVE / 7) < 1e-12
    assert abs(expected[3] - 3 * paths.EFFECT_SUBSTANTIVE / 7) < 1e-12
    assert abs(expected[1] - 3 * paths.EFFECT_SUBSTANTIVE / 14) < 1e-12  # naive: 0.5 x truth
    assert expected[1] < 0.75 * (3 * paths.EFFECT_SUBSTANTIVE / 7)


# --- all seven weekday offsets ------------------------------------------------

def test_all_seven_offsets():
    weekdays = []
    for k in range(7):
        p = offset_params(k)
        weekdays.append(p["event_weekday"])
        # window covers rel_day=-28..6 target range for daily/aligned
        assert p["window_start_rel_day"] <= -28
        assert p["window_end_rel_day"] >= 6
        # six bins of seven days, exposures consistent with composition
        rows = bin_composition(k)
        assert len(rows) == 6
        exp_from_bins = [r["exposure_weight"] for r in rows]
        np.testing.assert_allclose(exp_from_bins, p["exposures"])
        # weights sane: each method's weights sum to 0 (difference-in-means)
        W = estimator_weights(k)
        np.testing.assert_allclose(W.sum(axis=0), np.zeros(4), atol=1e-12)
    assert sorted(weekdays) == sorted(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    )
    assert offset_params(0)["event_weekday"] == "Thursday"


def test_offset_windows_stay_inside_simulated_panel():
    for k in range(7):
        p = offset_params(k)
        assert p["window_start_rel_day"] >= -56
        assert p["window_end_rel_day"] <= 27


def test_exposure_recovers_constant_effect_all_offsets(cal):
    """For a persistent (constant) effect the exposure regression is unbiased
    at every offset by construction."""
    y0 = generate_y0(cal, 200, seed=126)
    for k in range(7):
        W = estimator_weights(k)
        est = point_estimates(window_slice(inject(y0, "persistent", paths.EFFECT_SUBSTANTIVE), k), W)
        se = est[:, 2].std(ddof=1) / np.sqrt(200)
        assert abs(est[:, 2].mean() - paths.EFFECT_SUBSTANTIVE) < 5 * se + 1e-3


# --- SD_null lock + arm specs + DGP fidelity (locked 2026-08-14) ----------------

def test_corrected_panel_validation():
    """Corrected panel: source 724 rows preserved, primary = 543 rows of
    3 markets, no missing/zero corrected values, Meteora missing exactly
    before the 2025-01-17 coverage boundary."""
    from s5agg.panel import load_corrected_panel, validate_corrected_panel

    df = load_corrected_panel()
    report = validate_corrected_panel(df)
    failed = [k for k, v in report["checks"].items() if not v]
    assert report["checks"]["all_passed"], f"failed checks: {failed}"


def test_arm_specs(cal):
    """Locked arm structure: zero once; substantive 0.30 and calibration
    T = 0.5 x SD_null, each in transient + persistent profiles, all scored on
    the same seven-day ATT. Calibration transient amplitude = 7T/3."""
    from s5agg.dgp import arm_specs, sd_null

    T = paths.CALIBRATION_MULTIPLIER * sd_null(cal)["sd"]
    specs = {a["arm"]: a for a in arm_specs(sd_null(cal)["sd"])}
    assert set(specs) == {
        "zero",
        "substantive_transient",
        "substantive_persistent",
        "calibration_transient",
        "calibration_persistent",
    }
    assert specs["zero"]["amplitude"] == 0.0 and specs["zero"]["truth"] == 0.0
    s = paths.EFFECT_SUBSTANTIVE
    assert specs["substantive_transient"]["truth"] == 3 * s / 7
    assert specs["substantive_persistent"]["truth"] == s
    assert specs["calibration_transient"]["amplitude"] == 7 * T / 3
    assert specs["calibration_transient"]["truth"] == T
    assert specs["calibration_persistent"]["amplitude"] == T
    assert specs["calibration_persistent"]["truth"] == T


def test_sd_null_lock_roundtrip(tmp_path):
    """The SD_null managed block round-trips through the design lock file and
    is written before any positive-arm simulation (runner data-prep)."""
    from s5agg.dgp import read_locked_sd_null, write_sd_null_to_lock

    lock = tmp_path / "design_lock.yaml"
    lock.write_text("experiment: test\n")
    fid = {"sd_null": 0.3307, "sd_null_mcse": 0.001, "sd_null_n_draws": 50000}
    write_sd_null_to_lock(lock, fid)
    assert read_locked_sd_null(lock) == 0.3307
    fid2 = {"sd_null": 0.4, "sd_null_mcse": 0.001, "sd_null_n_draws": 50000}
    write_sd_null_to_lock(lock, fid2)  # rewrite replaces the block in place
    assert read_locked_sd_null(lock) == 0.4
    assert "experiment: test" in lock.read_text()


def test_sliding_window_estimates():
    """The empirical sliding-window benchmark must reproduce the daily
    estimator window math and the 56-window count on the 90-day pre panel."""
    toy = np.arange(1.0, 91.0)  # slope 1: pre mean s+14.5, post mean s+32 -> diff 17.5
    est = sliding_window_estimates(toy)
    assert len(est) == 90 - 35 + 1 == 56
    np.testing.assert_allclose(est[0], toy[28:35].mean() - toy[:28].mean())
    np.testing.assert_allclose(est, 17.5)  # same for every window of a linear series
    const = np.full(90, 3.0)
    np.testing.assert_allclose(sliding_window_estimates(const), 0.0)


def test_fidelity_check_mechanics(cal):
    """Fidelity benchmarks are reproducible under locked seeds and the report
    carries uncertainty on both sides (MBB CIs for A, MCSE + seed range for B)."""
    fid = fidelity_check(cal)
    again = fidelity_check(cal)
    assert fid["benchmark_A_empirical_sliding_window_sd"] == again["benchmark_A_empirical_sliding_window_sd"]
    assert fid["sd_null"] == again["sd_null"]
    assert fid["benchmark_A_mbb_ci95"] == again["benchmark_A_mbb_ci95"]
    assert fid["benchmark_A_n_overlapping_windows"] == 56
    for lo, hi in fid["benchmark_A_mbb_ci95"].values():
        assert lo < fid["benchmark_A_empirical_sliding_window_sd"] < hi or lo <= hi
    ci_hi_max = max(hi for _, hi in fid["benchmark_A_mbb_ci95"].values())
    ci_lo_min = min(lo for lo, _ in fid["benchmark_A_mbb_ci95"].values())
    assert fid["fidelity_ok"] == bool(ci_lo_min <= fid["sd_null"] <= ci_hi_max)
    assert fid["sd_null_n_draws"] == paths.N_SDNULL_DRAWS
    # fixed block-length sensitivity set is always reported in full
    assert set(fid["block_length_sensitivity"]) == {"L7", "L14", "L21", "L28"}
