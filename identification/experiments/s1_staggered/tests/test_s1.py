"""Tests for the S1 semi-synthetic Monte Carlo pipeline.

Covers (acceptance 8.5): constant effect recovery, no-effect FPR sanity,
never-treated-only control path, unsupported-cell exclusion, and the
deterministic 3-cohort 6-day manual-ATT fixture (hand-computed per-cell ATT,
support and weights checked against the production functions). The fixture
lives here, not derived from any formal results. A statsmodels cross-check of
the hand-rolled TWFE is included (statsmodels is used in tests only).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from calibration import Calibration  # noqa: E402
from dgp import simulate_panel  # noqa: E402
from estimators import cs_att_estimate, twfe_estimate  # noqa: E402
from mc import rep_rng, run_replication  # noqa: E402
from truth import build_cell_grid, cell_true_att, overall_true_att, support_mask  # noqa: E402

COHORT_SIZES = [100, 140, 46, 47, 26, 34, 34, 25]
ADOPTION_DAYS = list(range(24, 32))


def synthetic_calibration(n_pool: int = 300, seed: int = 7) -> Calibration:
    rng = np.random.default_rng(seed)
    return Calibration(
        pool_p_active=rng.uniform(0.05, 0.6, n_pool),
        pool_mu_count=rng.uniform(1.2, 4.0, n_pool),
        pool_stratum=np.tile(np.arange(5), n_pool // 5),
        act_mult_dow=np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.1, 1.1]) / (1 + 0.2 / 7),
        cnt_mult_dow=np.ones(7),
        outcome_sd=0.35,
        n_pool=n_pool,
    )


# ---------------------------------------------------------------------------
# Deterministic 3-cohort 6-day fixture (spec section 4)
# ---------------------------------------------------------------------------
# Days 0..5. Cohorts g in {2, 3, 4} with sizes {2, 1, 1}; 3 never-treated
# controls with y = 0 on every day (control change = 0 everywhere).
#   cohort g=2: T00 y = 0 (t<2), 2 (t>=2);  T01 y = 1 constant
#   cohort g=3: T10 y = 0 (t<3), 3 (t>=3)
#   cohort g=4: T20 y = 0 (t<4), -1 (t>=4)
# Hand-computed ATT(g,t) (control change is 0):
#   g=2: mean over 2 creators of (y_t - y_1) = (2 + 0)/2 = 1   for t = 2..5
#   g=3: y_t - y_2 = 3                                          for t = 3..5
#   g=4: y_t - y_3 = -1                                         for t = 4..5
# Registered cell weights: n_g = {2, 1, 1}; total treated creator-days = 13.
# Overall ATT = (2*4*1 + 1*3*3 + 1*2*(-1)) / 13 = 15/13.


def manual_fixture():
    y = np.array([
        [0, 0, 2, 2, 2, 2],        # T00 (cohort 0, g=2)
        [1, 1, 1, 1, 1, 1],        # T01 (cohort 0, g=2)
        [0, 0, 0, 3, 3, 3],        # T10 (cohort 1, g=3)
        [0, 0, 0, 0, -1, -1],      # T20 (cohort 2, g=4)
        [0, 0, 0, 0, 0, 0],        # C0
        [0, 0, 0, 0, 0, 0],        # C1
        [0, 0, 0, 0, 0, 0],        # C2
    ], dtype=float)
    cohort = np.array([0, 0, 1, 2, -1, -1, -1])
    sizes, days, n_days = [2, 1, 1], [2, 3, 4], 6
    grid = build_cell_grid(sizes, days, n_days)
    # Hand-computed per-cell ATT, in grid order (cohort-major, day-minor).
    hand_att = np.array([1, 1, 1, 1, 3, 3, 3, -1, -1], dtype=float)
    hand_weights = np.array([2, 2, 2, 2, 1, 1, 1, 1, 1], dtype=float) / 13.0
    return y, cohort, grid, hand_att, hand_weights


class TestManualAttFixture(unittest.TestCase):
    def test_cell_estimates_support_weights(self):
        y, cohort, grid, hand_att, hand_weights = manual_fixture()
        mask = support_mask(y, cohort, grid)
        self.assertTrue(mask.all(), "all fixture cells should be supported")
        rng = np.random.default_rng(0)
        res = cs_att_estimate(y, cohort, grid, mask, rng, n_boot=99)
        np.testing.assert_allclose(res.cell_att, hand_att, atol=1e-12)
        np.testing.assert_allclose(res.cell_weight, hand_weights, atol=1e-12)
        self.assertAlmostEqual(res.estimate, 15.0 / 13.0, places=12)
        self.assertEqual(res.n_supported, 9)

    def test_overall_true_att_aggregation_matches_fixture(self):
        # Truth aggregation uses the same mask and registered weights: feed the
        # hand per-cell ATT through the production aggregation function.
        _, _, grid, hand_att, _ = manual_fixture()
        mask = np.ones(9, dtype=bool)
        self.assertAlmostEqual(
            overall_true_att(hand_att, grid, mask), 15.0 / 13.0, places=12
        )


class TestNeverTreatedOnlyControl(unittest.TestCase):
    """A not-yet-treated creator with extreme outcomes must not enter the
    control group. Cohorts g in {2, 4}, sizes {2, 1}, days 0..5.
    Late adopter L (g=4): y = [0, 0, 100, 100, 0, 0] -> its own cells
    ATT(4,4) = ATT(4,5) = 0 - 100 = -100. Never-treated controls: y constant
    (0 and 1) -> control change 0. Cohort g=2 cells: ATT = (2 + 0)/2 = 1,
    uncontaminated by L's 100s at t = 2, 3."""

    def test_estimate_uses_never_treated_only(self):
        y = np.array([
            [0, 0, 2, 2, 2, 2],
            [0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
            [0, 0, 100, 100, 0, 0],   # late adopter (cohort 1, g=4)
            [0, 0, 0, 0, 0, 0],
            [1, 1, 1, 1, 1, 1],
        ], dtype=float)
        cohort = np.array([0, 0, 1, -1, -1])
        grid = build_cell_grid([2, 1], [2, 4], 6)
        mask = support_mask(y, cohort, grid)
        res = cs_att_estimate(y, cohort, grid, mask, np.random.default_rng(0), n_boot=99)
        hand = np.array([1, 1, 1, 1, -100, -100], dtype=float)  # g=2: t=2..5; g=4: t=4..5
        np.testing.assert_allclose(res.cell_att, hand, atol=1e-12)
        expected = (2 * 4 * 1 + 1 * 2 * (-100)) / (2 * 4 + 1 * 2)
        self.assertAlmostEqual(res.estimate, expected, places=12)


class TestUnsupportedCellExclusion(unittest.TestCase):
    """NaN out all control outcomes on day 3 of the fixture: cells with t=3
    lose same-day never-treated support, and cells of cohort g=4 (whose base
    period g-1 = 3) lose base-period support. All must drop out of the mask,
    the estimates, the truth aggregation and the TWFE regression."""

    def test_exclusion_aligns_across_truth_and_estimators(self):
        y, cohort, grid, hand_att, _ = manual_fixture()
        y[4:, 3] = np.nan  # controls unobserved on day 3
        mask = support_mask(y, cohort, grid)
        # Cells in grid order: g=2 t=2..5, g=3 t=3..5, g=4 t=4..5.
        # Dropped: (g=2,t=3), (g=3,t=3) [day-3 control support], and both
        # g=4 cells [base day g-1 = 3 has no control support].
        expected_mask = np.array([True, False, True, True, False, True, True, False, False])
        np.testing.assert_array_equal(mask, expected_mask)

        res = cs_att_estimate(y, cohort, grid, mask, np.random.default_rng(0), n_boot=99)
        self.assertTrue(np.isnan(res.cell_att[~mask]).all())
        self.assertEqual(res.n_supported, int(expected_mask.sum()))
        # Hand aggregate over supported cells: g=2 t in {2,4,5} (w=2 each),
        # g=3 t in {4,5} (w=1 each): (2*3*1 + 1*2*3) / 8 = 1.5.
        self.assertAlmostEqual(res.estimate, 1.5, places=12)
        self.assertAlmostEqual(
            overall_true_att(hand_att, grid, mask), 1.5, places=12
        )
        np.testing.assert_allclose(
            res.cell_weight[mask], np.array([2, 2, 2, 1, 1]) / 8.0, atol=1e-12
        )

        twfe = twfe_estimate(y, cohort, np.array([2, 2, 3, 4, -1, -1, -1]),
                             support=mask, grid=grid, n_cohorts=3)
        # 42 creator-days minus the 3 NaN control obs on day 3, minus treated
        # obs in unsupported cells: (g=2,t=3) has 2 creators, (g=3,t=3) 1
        # creator, g=4 t in {4,5} 1 creator x 2 days -> 42 - 3 - 5 = 34.
        self.assertEqual(twfe.n_obs, 34)
        self.assertFalse(twfe.unestimable)


class TestConstantEffectRecovery(unittest.TestCase):
    def test_homogeneous_effect_recovered(self):
        cal = synthetic_calibration()
        sizes = [30, 40, 20, 20, 10, 15, 15, 10]
        days = list(range(24, 32))
        rng = np.random.default_rng(123)
        panel = simulate_panel(cal, sizes, days, "homogeneous", rng,
                               n_control=480, n_days=60)
        grid = build_cell_grid(sizes, days, 60)
        mask = support_mask(panel.y, panel.cohort, grid)
        cell_att = cell_true_att(panel, grid)
        truth = overall_true_att(cell_att, grid, mask)
        self.assertGreater(truth, 0.02)  # sanity: positive injected effect

        cs = cs_att_estimate(panel.y, panel.cohort, grid, mask,
                             np.random.default_rng(5), n_boot=199)
        twfe = twfe_estimate(panel.y, panel.cohort, panel.adoption_day,
                             support=mask, grid=grid)
        self.assertAlmostEqual(cs.estimate, truth, delta=0.05)
        self.assertAlmostEqual(twfe.estimate, truth, delta=0.05)


class TestZeroArmFPR(unittest.TestCase):
    def test_zero_arm_fpr_small_reps(self):
        cal = synthetic_calibration()
        sizes = [10] * 8
        days = list(range(24, 32))
        n_reps = 24
        rejects = {"twfe": 0, "cs_att": 0}
        truths = []
        for r in range(n_reps):
            rng = rep_rng("zero", r, n_reps, scenario_seed=999)
            out = run_replication(cal, "zero", r, rng, sizes, days,
                                  n_boot=199, n_control=240)
            for row in out.rows:
                rejects[row["method"]] += int(row["reject_null"])
            truths.append(out.rows[0]["true_att"])
        np.testing.assert_allclose(truths, 0.0, atol=1e-12)
        for method, k in rejects.items():
            self.assertLessEqual(k / n_reps, 0.25, f"{method} FPR {k}/{n_reps}")


class TestTwfeAgainstStatsmodels(unittest.TestCase):
    def test_beta_matches_statsmodels_dummies(self):
        import statsmodels.formula.api as smf
        import pandas as pd

        rng = np.random.default_rng(11)
        n, n_days, g = 50, 10, 5
        cohort = np.array([0] * 20 + [-1] * 30)
        adoption = np.array([g] * 20 + [-1] * 30)
        alpha = rng.normal(size=n)
        gamma = rng.normal(size=n_days)
        post = (np.arange(n_days)[None, :] >= g) & (cohort[:, None] == 0)
        y = alpha[:, None] + gamma[None, :] + 0.3 * post + rng.normal(scale=0.5, size=(n, n_days))

        ours = twfe_estimate(y, cohort, adoption, n_cohorts=1)

        df = pd.DataFrame({
            "y": y.ravel(),
            "post": post.astype(float).ravel(),
            "creator": np.repeat(np.arange(n), n_days).astype(str),
            "day": np.tile(np.arange(n_days), n).astype(str),
        })
        fit = smf.ols("y ~ post + C(creator) + C(day)", data=df).fit()
        self.assertAlmostEqual(ours.estimate, float(fit.params["post"]), places=8)


if __name__ == "__main__":
    unittest.main()
