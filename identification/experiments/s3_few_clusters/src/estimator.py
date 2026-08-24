"""Closed-form TWFE DiD estimator + few-cluster inference for experiment S3.

Spec: Web3AI4IO/identification/experiment_plans/S3_few_platform_clusters.md (sec. 4).

Point estimator: OLS of log_volume on unit FE + calendar-day FE +
treated-post indicator, window rel_day -60..29 (360 obs = 4 units x 90 days).
Design rank K = 94 (4 unit dummies + 89 day dummies, day 0 dropped, + 1
treated-post). Rows are ordered day-major: row r = day * 4 + unit.

Variance: CRV1 clustered by unit, G = 4 clusters, Stata small-sample factor
(G/(G-1)) * ((N-1)/(N-K)) = (4/3) * (359/266).

Inference methods:
  1. crv1_normal      CRV1 SE, standard-normal critical value / p-value
  2. crv1_t3          CRV1 SE, t(3) critical value / p-value
  3. wild_sign_enum   restricted wild cluster sign enumeration: sharp-null
                      residuals, all 16 Rademacher sign vectors enumerated
                      (no sampling), two-sided p = share of |t*| >= |t_obs|
  4. randomization    zero arm only: two-sided p over the DiD point estimates
                      under all 4 treated-identity assignments

Everything is closed-form numpy and vectorized across replications (Y has one
column per replication). A statsmodels cross-check lives in the test suite.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from src.dgp import N_DAYS, N_UNITS, POST_START_ROW
from src.validate_panel import EXPECTED_UNITS

N_OBS = N_DAYS * N_UNITS  # 360
K = N_UNITS + (N_DAYS - 1) + 1  # 94 = unit FE + day FE (drop day 0) + did
G = N_UNITS
STATA_FACTOR = (G / (G - 1)) * ((N_OBS - 1) / (N_OBS - K))

CRIT_NORMAL = float(stats.norm.ppf(0.975))
CRIT_T3 = float(stats.t.ppf(0.975, df=G - 1))

DID_COL = K - 1  # treated-post column index

# Rademacher sign vectors over the 4 clusters, EXPECTED_UNITS order.
SIGN_VECTORS = np.array(
    [[s0, s1, s2, s3] for s0 in (1, -1) for s1 in (1, -1)
     for s2 in (1, -1) for s3 in (1, -1)],
    dtype=float,
)  # (16, 4); row 0 is the all-plus vector reproducing the observed data

ASSIGNMENTS = list(EXPECTED_UNITS)  # 4 treated-identity permutations


def _row_unit() -> np.ndarray:
    """Unit index (0..3) of each of the 360 day-major rows."""
    return np.tile(np.arange(N_UNITS), N_DAYS)


def build_design(treated_idx: int) -> np.ndarray:
    """Full-model design matrix (360, 94) for one treated assignment."""
    X = np.zeros((N_OBS, K))
    rows = np.arange(N_OBS)
    unit_of_row = _row_unit()
    day_of_row = np.repeat(np.arange(N_DAYS), N_UNITS)
    X[rows, unit_of_row] = 1.0                      # unit FE
    day_cols = day_of_row - 1                        # day FE, day 0 dropped
    mask = day_of_row > 0
    X[rows[mask], N_UNITS + day_cols[mask]] = 1.0
    post_treated = (day_of_row >= POST_START_ROW) & (unit_of_row == treated_idx)
    X[rows[post_treated], DID_COL] = 1.0
    return X


NULL_DESIGN = build_design(treated_idx=-1)[:, :DID_COL]  # unit FE + day FE


@dataclass(frozen=True)
class AssignmentFit:
    """Precomputed per-assignment linear algebra."""

    treated_idx: int
    XtX_inv: np.ndarray   # (94, 94)
    X: np.ndarray         # (360, 94)
    Xt: np.ndarray        # (94, 360)
    b: np.ndarray         # (94,) row of XtX_inv for the did coefficient


def precompute(treated_idx: int) -> AssignmentFit:
    X = build_design(treated_idx)
    XtX_inv = np.linalg.inv(X.T @ X)
    return AssignmentFit(
        treated_idx=treated_idx, XtX_inv=XtX_inv, X=X, Xt=X.T,
        b=XtX_inv[DID_COL].copy(),
    )


# Null (sharp-H0) fit quantities, shared across assignments.
_NULL_XtX_inv = np.linalg.inv(NULL_DESIGN.T @ NULL_DESIGN)
_NULL_Xt = NULL_DESIGN.T


def estimate_did(Y: np.ndarray, fit: AssignmentFit) -> dict[str, np.ndarray]:
    """Vectorized TWFE DiD + CRV1 for Y of shape (360, R).

    Returns dict with beta, se, t (each shape (R,)).
    """
    B = fit.XtX_inv @ (fit.Xt @ Y)              # (94, R)
    beta = B[DID_COL]
    E = Y - fit.X @ B                           # (360, R)
    meat = np.zeros(Y.shape[1])
    for g in range(G):
        S_g = fit.Xt[:, g::N_UNITS] @ E[g::N_UNITS, :]   # (94, R)
        w_g = fit.b @ S_g
        meat += w_g**2
    var = STATA_FACTOR * meat
    se = np.sqrt(var)
    return {"beta": beta, "se": se, "t": beta / se}


def null_residuals(Y: np.ndarray) -> np.ndarray:
    """Sharp-null residuals from the restricted (no treated-post) fit."""
    return Y - NULL_DESIGN @ (_NULL_XtX_inv @ (_NULL_Xt @ Y))


def wild_sign_enum_pvalues(Y: np.ndarray, fit: AssignmentFit,
                           obs: dict[str, np.ndarray] | None = None,
                           tol: float = 1e-10) -> tuple[np.ndarray, np.ndarray]:
    """Restricted wild cluster sign enumeration, all 16 Rademacher vectors.

    Imposes the sharp null: pseudo-data Y* = fitted_null + s_g * e_hat within
    cluster g. Because fitted_null lies in the column space of the full
    design, t* under vector s depends only on D_s e_hat, and |t*| is symmetric
    under s -> -s, so the 16 vectors yield 8 distinct |t*| values and
    attainable two-sided p-values in {2/16, 4/16, ..., 1}.

    Returns (p_values (R,), t_star (16, R)).
    """
    e_hat = null_residuals(Y)                       # (360, R)
    unit_of_row = _row_unit()
    if obs is None:
        obs = estimate_did(Y, fit)
    t_obs = np.abs(obs["t"])
    t_star = np.empty((SIGN_VECTORS.shape[0], Y.shape[1]))
    for k, signs in enumerate(SIGN_VECTORS):
        Z = e_hat * signs[unit_of_row][:, None]
        t_star[k] = estimate_did(Z, fit)["t"]
    p = (np.abs(t_star) >= t_obs[None, :] - tol).mean(axis=0)
    return p, t_star


def randomization_pvalues(betas_by_assignment: np.ndarray, observed_idx: int = 0,
                          tol: float = 1e-12) -> np.ndarray:
    """Two-sided randomization-inference p over the 4 treated identities.

    betas_by_assignment: (4, R) DiD point estimates, one per assignment.
    p = share of assignments with |beta_a| >= |beta_observed|; attainable
    values {0.25, 0.5, 0.75, 1.0}.
    """
    obs = np.abs(betas_by_assignment[observed_idx])
    return (np.abs(betas_by_assignment) >= obs[None, :] - tol).mean(axis=0)


def pvalue_crv1_normal(t: np.ndarray) -> np.ndarray:
    return 2.0 * stats.norm.sf(np.abs(t))


def pvalue_crv1_t3(t: np.ndarray) -> np.ndarray:
    return 2.0 * stats.t.sf(np.abs(t), df=G - 1)
