"""Estimators for the S1 experiment.

1. Static TWFE (hand-rolled): y ~ post indicator + creator FE + day FE,
   fitted by alternating-projection demeaning (bincount-based, supports
   unbalanced panels), cluster-robust SE by creator (CR1). Also reports the
   implicit per-observation regression weights w = D~ / sum(D~^2), aggregated
   per cohort (implicit weighting diagnostic).

2. Callaway-Sant'Anna style unconditional group-time ATT (no covariates):
   ATT(g,t) = [dY_treated(g,t)] - [dY_control(g,t)] with base period g-1 and
   same-day never-treated controls only. Aggregated strictly by registered
   treated creator-day cell counts over supported cells. Inference:
   creator-level multiplier bootstrap (Rademacher weights) on the per-creator
   influence function of the aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# ---------------------------------------------------------------------------
# Static TWFE
# ---------------------------------------------------------------------------


def _demean_two_way(v: np.ndarray, ci: np.ndarray, di: np.ndarray,
                    n_c: int, n_d: int, tol: float = 1e-12, max_iter: int = 200) -> np.ndarray:
    """Residuals of v on creator and day dummies via alternating projections."""
    r = v.copy()
    cnt_c = np.maximum(np.bincount(ci, minlength=n_c), 1)
    cnt_d = np.maximum(np.bincount(di, minlength=n_d), 1)
    prev_ss = np.inf
    for _ in range(max_iter):
        m_c = np.bincount(ci, weights=r, minlength=n_c) / cnt_c
        r = r - m_c[ci]
        m_d = np.bincount(di, weights=r, minlength=n_d) / cnt_d
        r = r - m_d[di]
        ss = float(r @ r)
        if abs(prev_ss - ss) <= tol * max(ss, 1e-30):
            break
        prev_ss = ss
    return r


@dataclass
class TWFEResult:
    estimate: float
    se: float
    ci_lo: float
    ci_hi: float
    n_obs: int
    cohort_weight_share: np.ndarray  # implicit weight on each cohort's post cells
    neg_weight_sum_treated: float  # sum of negative implicit weights on treated obs
    unestimable: bool


def twfe_estimate(
    y: np.ndarray,
    cohort: np.ndarray,
    adoption_day: np.ndarray,
    support: np.ndarray | None = None,
    grid=None,
    n_cohorts: int = 8,
) -> TWFEResult:
    """Static TWFE of y on a single post indicator with creator + day FE.

    Observations in unsupported treated cells (support mask False) are dropped
    so the estimator targets the same estimand as the truth.
    """
    n, n_days = y.shape
    days = np.arange(n_days)
    d_post = np.zeros((n, n_days))
    treated = cohort >= 0
    d_post[treated] = (days[None, :] >= adoption_day[treated, None]).astype(float)

    y = y.copy()
    if support is not None and grid is not None:
        for k in range(len(grid.cohort)):
            if not support[k]:
                rows = cohort == grid.cohort[k]
                y[rows, grid.day[k]] = np.nan

    valid = ~np.isnan(y)
    ci = np.repeat(np.arange(n), n_days)[valid.ravel()]
    di = np.tile(np.arange(n_days), n)[valid.ravel()]
    yv = y.ravel()[valid.ravel()]
    dv = d_post.ravel()[valid.ravel()]

    if dv.sum() <= 0 or len(yv) == 0:
        return TWFEResult(np.nan, np.nan, np.nan, np.nan, 0,
                          np.full(n_cohorts, np.nan), np.nan, True)

    d_tilde = _demean_two_way(dv, ci, di, n, n_days)
    y_tilde = _demean_two_way(yv, ci, di, n, n_days)
    denom = float(d_tilde @ d_tilde)
    if denom <= 0:
        return TWFEResult(np.nan, np.nan, np.nan, np.nan, len(yv),
                          np.full(n_cohorts, np.nan), np.nan, True)
    beta = float(d_tilde @ y_tilde / denom)
    resid = y_tilde - beta * d_tilde

    # Cluster-robust (creator) variance, CR1 small-sample factor.
    meat_per_creator = np.bincount(ci, weights=d_tilde * resid, minlength=n)
    meat = float(meat_per_creator @ meat_per_creator)
    g_clust = int((np.bincount(ci, minlength=n) > 0).sum())
    cr1 = g_clust / (g_clust - 1) if g_clust > 1 else 1.0
    var = cr1 * meat / denom**2
    se = float(np.sqrt(var))

    # Implicit weighting diagnostic: w_it = D~_it / sum(D~^2) acts on y_it.
    w = d_tilde / denom
    w_mat = np.full(n * n_days, np.nan)
    w_mat[valid.ravel()] = w
    w_mat = w_mat.reshape(n, n_days)
    post_obs = (d_post == 1) & valid
    cohort_share = np.full(n_cohorts, np.nan)
    for c in range(n_cohorts):
        rows = cohort == c
        cohort_share[c] = float(np.nansum(w_mat[rows][post_obs[rows]]))
    treated_obs = treated[:, None] & valid
    neg_sum = float(np.nansum(np.where((w_mat < 0) & treated_obs, w_mat, 0.0)))

    return TWFEResult(
        estimate=beta,
        se=se,
        ci_lo=beta - 1.959964 * se,
        ci_hi=beta + 1.959964 * se,
        n_obs=len(yv),
        cohort_weight_share=cohort_share,
        neg_weight_sum_treated=neg_sum,
        unestimable=False,
    )


# ---------------------------------------------------------------------------
# Callaway-Sant'Anna style group-time ATT
# ---------------------------------------------------------------------------


@dataclass
class CSResult:
    estimate: float
    se: float
    ci_lo: float
    ci_hi: float
    cell_att: np.ndarray  # (n_cells,), NaN for unsupported
    cell_weight: np.ndarray  # (n_cells,), normalized registered counts, 0 if unsupported
    n_supported: int
    unestimable: bool


def _cell_atts_and_if(
    y: np.ndarray, cohort: np.ndarray, grid, support: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-cell ATT(g,t) and per-creator influence contributions.

    Returns (cell_att, if_matrix (n_creators x n_cells), complete-pair counts
    per cell). Influence convention: cell_att = mean_treated dY - mean_ctrl dY
    and its influence function value for creator i is if_matrix[i, k], so
    var(cell_att_k) ~= sum_i if_matrix[i,k]^2 and bootstrap perturbations are
    sum_i if_matrix[i,k] * R_i.
    """
    n, _ = y.shape
    n_cells = len(grid.cohort)
    ctrl = cohort < 0
    cell_att = np.full(n_cells, np.nan)
    if_mat = np.zeros((n, n_cells))
    n_complete = np.zeros(n_cells)
    yc = y[ctrl]
    n_ctrl = int(ctrl.sum())

    for k in range(n_cells):
        if not support[k]:
            continue
        c, t, b = grid.cohort[k], grid.day[k], grid.base_day[k]
        tr = cohort == c
        dy_t = y[tr, t] - y[tr, b]
        ok_t = ~np.isnan(dy_t)
        dy_c = yc[:, t] - yc[:, b]
        ok_c = ~np.isnan(dy_c)
        n_t = int(ok_t.sum())
        n_c = int(ok_c.sum())
        if n_t == 0 or n_c == 0:
            continue
        m_t = float(dy_t[ok_t].mean())
        m_c = float(dy_c[ok_c].mean())
        cell_att[k] = m_t - m_c
        n_complete[k] = n_t
        idx_t = np.flatnonzero(tr)[ok_t]
        if_mat[idx_t, k] = (dy_t[ok_t] - m_t) / n_t
        idx_c = np.flatnonzero(ctrl)[ok_c]
        if_mat[idx_c, k] = -(dy_c[ok_c] - m_c) / n_c
    return cell_att, if_mat, n_complete


def cs_att_estimate(
    y: np.ndarray,
    cohort: np.ndarray,
    grid,
    support: np.ndarray,
    rng: np.random.Generator,
    n_boot: int = 1999,
) -> CSResult:
    """Group-time ATT aggregated by registered treated creator-day counts."""
    cell_att, if_mat, _ = _cell_atts_and_if(y, cohort, grid, support)
    w = np.where(support, grid.n_treated.astype(float), 0.0)
    w_sum = w.sum()
    if w_sum <= 0 or np.all(np.isnan(cell_att[support])):
        return CSResult(np.nan, np.nan, np.nan, np.nan, cell_att,
                        np.zeros_like(w), 0, True)
    # Cells marked supported but numerically unestimable are dropped too.
    valid = support & ~np.isnan(cell_att)
    w = np.where(valid, grid.n_treated.astype(float), 0.0)
    w_sum = w.sum()
    w_norm = w / w_sum
    att = float(w_norm @ np.where(valid, cell_att, 0.0))

    phi = if_mat @ w_norm  # per-creator influence on the aggregate
    se = float(np.sqrt(phi @ phi))

    # Creator-level multiplier bootstrap, vectorized over draws.
    rademacher = rng.integers(0, 2, size=(len(phi), n_boot), dtype=np.int8) * 2 - 1
    boot = att + (rademacher * phi[:, None]).sum(axis=0)
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])

    return CSResult(
        estimate=att,
        se=se,
        ci_lo=float(ci_lo),
        ci_hi=float(ci_hi),
        cell_att=cell_att,
        cell_weight=w_norm,
        n_supported=int(valid.sum()),
        unestimable=False,
    )
