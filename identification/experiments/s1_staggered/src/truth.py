"""True cohort-time ATT and shared support masks.

True ATT is computed from the same untreated/injected intensities that
generated the panel: for creator i on day t,
  E[log1p(Y)] = p_id * S(lambda_id),  S(lam) = E[log(2 + J)], J ~ Poisson(lam - 1)
(inactive days contribute log1p(0) = 0). The per-cell true ATT is the mean
over the cell's treated creators of E[log1p(Y(1))] - E[log1p(Y(0))].

Support masks are computed once from the observed outcome panel and shared
by the truth and both estimators (acceptance 8.3): a cohort-time cell is
supported iff it has >=1 treated creator with an observed (non-NaN) outcome
on both day t and base day g-1, AND >=1 never-treated creator with observed
outcomes on both days.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import gammaln


def poisson_log1p_mean(lam: np.ndarray) -> np.ndarray:
    """E[log(2 + J)] for J ~ Poisson(lam), vectorized over lam >= 0."""
    lam = np.asarray(lam, dtype=float)
    flat = lam.ravel()
    lam_max = float(flat.max()) if flat.size else 0.0
    j_max = int(min(max(np.ceil(lam_max + 12.0 * np.sqrt(lam_max + 1.0) + 10.0), 20), 500))
    j = np.arange(j_max + 1)
    lam_c = np.clip(flat, 1e-12, None)
    logpmf = -flat[:, None] + j[None, :] * np.log(lam_c[:, None]) - gammaln(j + 1)[None, :]
    pmf = np.exp(logpmf)
    out = pmf @ np.log(j + 2.0)
    return out.reshape(lam.shape)


def expected_log1p(p_active: np.ndarray, lam: np.ndarray) -> np.ndarray:
    return p_active * poisson_log1p_mean(np.clip(lam - 1.0, 0.0, None))


@dataclass
class CellGrid:
    """Cohort-time cells for post-adoption days."""

    cohort: np.ndarray  # (n_cells,)
    day: np.ndarray  # (n_cells,)
    base_day: np.ndarray  # (n_cells,) g - 1
    n_treated: np.ndarray  # (n_cells,) registered treated creator count


def build_cell_grid(cohort_sizes: list[int], adoption_days: list[int], n_days: int) -> CellGrid:
    cs, ts, bs, ns = [], [], [], []
    for c, g in enumerate(adoption_days):
        for t in range(g, n_days):
            cs.append(c)
            ts.append(t)
            bs.append(g - 1)
            ns.append(cohort_sizes[c])
    return CellGrid(
        cohort=np.array(cs), day=np.array(ts), base_day=np.array(bs), n_treated=np.array(ns)
    )


def support_mask(y: np.ndarray, cohort: np.ndarray, grid: CellGrid) -> np.ndarray:
    """Boolean (n_cells,) support mask from the observed outcome panel.

    y may contain NaN (unobserved creator-days). A cell is supported iff at
    least one of its treated creators and at least one never-treated creator
    have observed outcomes on both day t and base day g-1.
    """
    obs = ~np.isnan(y)
    ctrl = cohort < 0
    ctrl_obs = obs[ctrl]  # (n_ctrl, n_days)
    n_cells = len(grid.cohort)
    mask = np.zeros(n_cells, dtype=bool)
    for k in range(n_cells):
        c, t, b = grid.cohort[k], grid.day[k], grid.base_day[k]
        tr = cohort == c
        ok_treated = bool(np.any(obs[tr, t] & obs[tr, b]))
        ok_control = bool(np.any(ctrl_obs[:, t] & ctrl_obs[:, b]))
        mask[k] = ok_treated and ok_control
    return mask


def cell_true_att(panel, grid: CellGrid) -> np.ndarray:
    """True ATT per cell: mean over treated creators of the cell of
    E[log1p(Y(1))] - E[log1p(Y(0))] on day t."""
    e0 = expected_log1p(panel.p_active, panel.lam_untreated)
    e1 = expected_log1p(panel.p_active, panel.lam_treated)
    diff = e1 - e0  # (n_creators, n_days); zero for controls/pre days
    out = np.zeros(len(grid.cohort))
    for k in range(len(grid.cohort)):
        rows = panel.cohort == grid.cohort[k]
        out[k] = float(diff[rows, grid.day[k]].mean())
    return out


def overall_true_att(cell_att: np.ndarray, grid: CellGrid, mask: np.ndarray) -> float:
    """Aggregate strictly by registered treated creator-day cell counts."""
    w = grid.n_treated.astype(float)
    w = np.where(mask, w, 0.0)
    if w.sum() <= 0:
        return float("nan")
    return float((w * cell_att).sum() / w.sum())
