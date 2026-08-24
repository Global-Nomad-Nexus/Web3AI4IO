"""Tests for the S3 validation path (panel balance, pre-period fit, manifest).

The scale rule was revised on 2026-08-13 (spec sec. 3): the pre-period
residual SD check is retained as a descriptive record of the first run's
blocker, while the operative s_ATT scale check lives in
src/run_experiment.py / calibration_summary.json and is exercised by the
simulation tests (test_simulation.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import validate_panel as vp


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return pd.read_csv(vp.PANEL_CSV)


@pytest.fixture(scope="module")
def preperiod(panel: pd.DataFrame) -> pd.DataFrame:
    return vp.fit_preperiod(panel)


def test_panel_balance(panel: pd.DataFrame):
    """724 rows = 4 named Solana market clusters x 181 days, rel_day -90..90."""
    assert len(panel) == 724
    assert set(panel["unit"].unique()) == {
        "pump_ecosystem", "raydium", "orca", "meteora_combined",
    }
    counts = panel.groupby("unit")["rel_day"].count()
    assert (counts == 181).all()
    assert panel.rel_day.min() == -90 and panel.rel_day.max() == 90
    assert not panel.duplicated(["unit", "rel_day"]).any()
    assert not panel.log_volume.isna().any()
    # one calendar date per rel_day (weekday mapping is well-defined)
    assert (panel.groupby("rel_day")["date_str"].nunique() == 1).all()


def test_preperiod_fit_shape_and_rank(preperiod: pd.DataFrame):
    """Pre-period fit uses exactly rel_day -90..-1: 360 obs, rank 10."""
    assert len(preperiod) == 360
    assert preperiod.rel_day.min() == -90 and preperiod.rel_day.max() == -1
    assert preperiod.attrs["rank"] == 10  # 4 unit FE + 6 weekday dummies


def test_residuals_orthogonal_to_regressors(preperiod: pd.DataFrame):
    """OLS sanity: residuals orthogonal to unit dummies and weekday dummies."""
    u = preperiod["u"].values
    x_unit = pd.get_dummies(preperiod["unit"])[vp.EXPECTED_UNITS].values.astype(float)
    x_wd = pd.get_dummies(preperiod["weekday"]).values.astype(float)
    assert np.abs(x_unit.T @ u).max() < 1e-8
    assert np.abs(x_wd.T @ u).max() < 1e-8


def test_residual_scale_descriptive_deterministic(preperiod: pd.DataFrame):
    """The residual-SD descriptives are reproducible; the recorded 2.878
    value documents why the superseded rule stopped the first run."""
    a = vp.scale_check(preperiod)
    b = vp.scale_check(preperiod)
    assert a == b  # deterministic
    sd = a["residual_sd_variants"]["pooled_u_ddof1"]
    assert sd == pytest.approx(2.878395096604233)
    assert a["ratio_effect_over_sd_primary"] == pytest.approx(0.20 / sd)
    # old-rule verdict recorded for traceability, no longer gating
    assert not a["pass"]


def test_validation_script_output_matches_recomputed(tmp_path, panel):
    """panel_validation.json on disk agrees with an in-memory recomputation."""
    import json

    on_disk = json.loads((vp.EXPERIMENT_ROOT / "panel_validation.json").read_text())
    assert on_disk["panel_valid"] is True
    assert on_disk["status"] == "OK"  # revised rule: residual SD no longer gates
    recomputed = vp.scale_check(vp.fit_preperiod(panel))
    assert on_disk["scale_check"]["residual_sd_variants"] == pytest.approx(
        recomputed["residual_sd_variants"]
    )
