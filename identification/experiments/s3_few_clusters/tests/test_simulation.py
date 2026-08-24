"""Tests for the S3 Monte Carlo machinery (spec sec. 8.6).

Covers: sharp-null imposition, 16 unique sign vectors, 4 unique treatment
permutations, seed reproducibility, p-value discreteness, and agreement of
the closed-form fast path with statsmodels OLS + cov_cluster.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from src import estimator as est
from src.dgp import (
    N_DAYS,
    N_UNITS,
    POST_START_ROW,
    build_y0_panel,
    inject_effect,
    load_dgp_components,
    rep_rng,
)
from src.run_experiment import ARM_SEEDS, EXPECTED_UNITS, TREATED_IDX
from src.validate_panel import EXPERIMENT_ROOT


@pytest.fixture(scope="module")
def comp():
    return load_dgp_components()


@pytest.fixture(scope="module")
def sample_panel(comp) -> np.ndarray:
    """One deterministic synthetic panel, day-major vector (360,)."""
    y0, _ = build_y0_panel(comp, rep_rng(ARM_SEEDS["zero"], 0))
    return inject_effect(y0, TREATED_IDX, 0.20).reshape(-1)


# --- enumeration completeness (spec sec. 8.4) ---

def test_sign_vectors_16_unique():
    assert est.SIGN_VECTORS.shape == (16, N_UNITS)
    assert set(np.abs(est.SIGN_VECTORS).ravel()) == {1.0}
    assert len({tuple(row) for row in est.SIGN_VECTORS.astype(int)}) == 16


def test_treatment_permutations_4_unique():
    assert len(est.ASSIGNMENTS) == 4
    assert len(set(est.ASSIGNMENTS)) == 4
    assert set(est.ASSIGNMENTS) == {
        "pump_ecosystem", "raydium", "orca", "meteora_combined"}


def test_sign_enumeration_csv_matches_code():
    on_disk = pd.read_csv(EXPERIMENT_ROOT / "artifacts/sign_enumeration.csv")
    assert len(on_disk) == 16
    assert on_disk[EXPECTED_UNITS].values.tolist() == est.SIGN_VECTORS.astype(
        int).tolist()


def test_treatment_permutations_csv_matches_code():
    on_disk = pd.read_csv(
        EXPERIMENT_ROOT / "artifacts/treatment_permutations.csv")
    assert on_disk["treated_unit"].tolist() == EXPECTED_UNITS


# --- seed reproducibility (spec sec. 8.6) ---

def test_seed_reproducibility(comp):
    y_a, s_a = build_y0_panel(comp, rep_rng(ARM_SEEDS["low_power"], 42))
    y_b, s_b = build_y0_panel(comp, rep_rng(ARM_SEEDS["low_power"], 42))
    np.testing.assert_array_equal(y_a, y_b)
    np.testing.assert_array_equal(s_a, s_b)
    # different rep id -> different panel
    y_c, _ = build_y0_panel(comp, rep_rng(ARM_SEEDS["low_power"], 43))
    assert not np.allclose(y_a, y_c)


def test_assignment_independent_of_blocks(comp):
    """The bootstrap stream does not depend on which unit is treated."""
    rng1 = rep_rng(ARM_SEEDS["zero"], 7)
    y0_a, starts_a = build_y0_panel(comp, rng1)
    rng2 = rep_rng(ARM_SEEDS["zero"], 7)
    y0_b, starts_b = build_y0_panel(comp, rng2)
    np.testing.assert_array_equal(starts_a, starts_b)
    np.testing.assert_array_equal(y0_a, y0_b)


# --- sharp-null imposition (spec sec. 4.3) ---

def test_sharp_null_imposition(sample_panel):
    """All-plus sign vector reproduces the observed data; null residuals are
    orthogonal to the null design; wild t* under the all-plus vector equals
    the observed t statistic."""
    fit = est.precompute(TREATED_IDX)
    Y = sample_panel.reshape(-1, 1)
    e_hat = est.null_residuals(Y)
    # residuals of the restricted fit are orthogonal to the null design
    assert np.abs(est.NULL_DESIGN.T @ e_hat).max() < 1e-8
    # all-plus vector (row 0) returns the observed panel: t*[0] == t_obs
    obs = est.estimate_did(Y, fit)
    _, t_star = est.wild_sign_enum_pvalues(Y, fit, obs=obs)
    assert t_star[0, 0] == pytest.approx(obs["t"][0], rel=1e-10)
    # sign symmetry: |t*(s)| == |t*(-s)|
    assert abs(t_star[0, 0]) == pytest.approx(abs(t_star[-1, 0]), rel=1e-10)


def test_wild_pvalue_discreteness(sample_panel):
    """Attainable wild p-values are multiples of 1/16 (2/16 two-sided)."""
    fit = est.precompute(TREATED_IDX)
    rng = np.random.default_rng(0)
    Y = sample_panel.reshape(-1, 1) + rng.normal(
        scale=0.5, size=(360, 200))  # spread out observed t values
    p, _ = est.wild_sign_enum_pvalues(Y, fit)
    scaled = p * 16
    np.testing.assert_allclose(scaled, np.round(scaled), atol=1e-8)
    assert (p >= 2 / 16 - 1e-12).all()  # sign symmetry: min attainable 2/16


def test_randomization_pvalue_discreteness():
    rng = np.random.default_rng(1)
    betas = rng.normal(size=(4, 500))
    p = est.randomization_pvalues(betas, observed_idx=0)
    assert set(np.unique(p)) <= {0.25, 0.5, 0.75, 1.0}


# --- fast path vs statsmodels (spec sec. 4 performance note) ---

def test_fastpath_matches_statsmodels(sample_panel):
    """Closed-form TWFE + CRV1 (Stata factor) matches statsmodels OLS with
    cov_type='cluster' on beta, SE, and t for every assignment."""
    unit_of_row = np.tile(EXPECTED_UNITS, N_DAYS)  # day-major
    for a, treated in enumerate(EXPECTED_UNITS):
        fit = est.precompute(a)
        fast = est.estimate_did(sample_panel.reshape(-1, 1), fit)
        X = pd.DataFrame(fit.X, columns=[f"x{k}" for k in range(est.K)])
        res = sm.OLS(sample_panel, X).fit(
            cov_type="cluster",
            cov_kwds={"groups": unit_of_row, "use_correction": True},
        )
        assert fast["beta"][0] == pytest.approx(
            res.params[f"x{est.DID_COL}"], rel=1e-8)
        # statsmodels applies the Stata factor (G/(G-1))*((N-1)/(N-K))
        assert fast["se"][0] == pytest.approx(
            res.bse[f"x{est.DID_COL}"], rel=1e-8)
        assert fast["t"][0] == pytest.approx(
            res.tvalues[f"x{est.DID_COL}"], rel=1e-8)
        assert res.df_resid == est.N_OBS - est.K


# --- DGP sanity ---

def test_synthetic_panel_shape_and_injection(comp):
    y0, starts = build_y0_panel(comp, rep_rng(ARM_SEEDS["zero"], 0))
    assert y0.shape == (N_DAYS, N_UNITS)
    assert starts.shape == (13,)  # ceil(90/7) blocks
    assert ((0 <= starts) & (starts <= 90 - 7)).all()
    y1 = inject_effect(y0, TREATED_IDX, 0.20)
    diff = y1 - y0
    assert np.all(diff[:POST_START_ROW] == 0.0)
    assert diff[POST_START_ROW:, TREATED_IDX] == pytest.approx(0.20)
    others = [i for i in range(N_UNITS) if i != TREATED_IDX]
    assert np.all(diff[:, others] == 0.0)


def test_pilot_reproduces_recorded_s_att(comp):
    """The seeded pilot reproduces the s_ATT recorded in calibration_summary
    (guards against silent DGP/seed drift)."""
    import json

    from src.run_experiment import N_PILOT, PILOT_SEED, _pilot

    recorded = json.loads(
        (EXPERIMENT_ROOT / "calibration_summary.json").read_text())
    if recorded["status"] != "OK":
        pytest.skip("calibration_summary.json is a scale-blocker record")
    ests = _pilot(comp, est.precompute(TREATED_IDX))
    assert ests.shape == (N_PILOT,)
    assert float(ests.std(ddof=1)) == pytest.approx(
        recorded["scale_metric"]["s_att"], rel=1e-9)
    assert recorded["scale_metric"]["pilot_seed"] == PILOT_SEED
