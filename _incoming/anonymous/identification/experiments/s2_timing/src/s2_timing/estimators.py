"""Batched OLS with Newey-West HAC (lag 7) and the three timing estimators.

All methods target the same 21-day post estimand via
    d_t = intercept + weekday fixed effects + beta * post_t
on d_t = log1p(Pump) - log1p(Moonshot). Everything is batched over Monte
Carlo replications: D has shape (n_rep, T).
"""

from __future__ import annotations

import datetime as dt

import numpy as np
from scipy import stats

from .dgp import ACTIVATION, CLEAN_PRE_END, POST_START, SIM_END, SIM_START, announcement_date

HAC_LAG = 7
Z_CRIT = stats.norm.ppf(0.975)

METHODS = ["naive_announcement", "verified_activation", "activation_plus_anticipation_gate"]


def design_matrix(days: list[dt.date], post_mask: np.ndarray) -> np.ndarray:
    n = len(days)
    X = np.zeros((n, 8))
    X[:, 0] = 1.0
    for w in range(1, 7):
        X[:, w] = [d.weekday() == w for d in days]
    X[:, 7] = post_mask
    return X


def ols_hac(D: np.ndarray, X: np.ndarray, lag: int = HAC_LAG) -> tuple[np.ndarray, np.ndarray]:
    """OLS coefs and HAC SEs for every rep. D: (R, T), X: (T, k)."""
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = D @ X @ XtX_inv.T                     # (R, k)
    E = D - beta @ X.T                           # (R, T)
    meat = np.einsum("ti,rt,tj->rij", X, E * E, X)
    for l in range(1, lag + 1):
        w = 1.0 - l / (lag + 1.0)
        C = np.einsum("ti,rt,tj->rij", X[l:], E[:, l:] * E[:, :-l], X[:-l])
        meat += w * (C + C.transpose(0, 2, 1))
    V = np.einsum("ij,rjk,kl->ril", XtX_inv, meat, XtX_inv)
    se = np.sqrt(np.maximum(np.diagonal(V, axis1=1, axis2=2), 0.0))
    return beta, se


def _slice(days: list[dt.date], keep) -> tuple[list[dt.date], np.ndarray]:
    idx = np.array([i for i, d in enumerate(days) if keep(d)])
    return [days[i] for i in idx], idx


def method_samples(days: list[dt.date], gap: int) -> dict:
    """Sample and post mask per method. Estimator-side clean pre ends the day
    before the (synthetic) announcement; 2025-05-13 partial activation day is
    dropped except by the naive method, which treats announcement as treatment."""
    ann = announcement_date(gap)
    out = {}

    keep = lambda d: SIM_START <= d <= SIM_END
    mdays, idx = _slice(days, keep)
    out["naive_announcement"] = {
        "idx": idx, "X": design_matrix(mdays, np.array([d >= ann for d in mdays]))}

    keep = lambda d: d != ACTIVATION
    mdays, idx = _slice(days, keep)
    out["verified_activation"] = {
        "idx": idx, "X": design_matrix(mdays, np.array([d >= POST_START for d in mdays]))}

    gate_days = [d for d in days if d <= ACTIVATION - dt.timedelta(days=1)]
    ann_interval = [d for d in gate_days if d >= ann]
    gate_idx = np.array([i for i, d in enumerate(days) if d in set(gate_days)])
    gate = {"gate_idx": gate_idx}
    if ann_interval:
        Xg = design_matrix(gate_days, np.array([d >= ann for d in gate_days]))
        gate["X_gate"] = Xg
    else:  # same-day announcement: no interval, gate cannot fire
        gate["X_gate"] = None

    keep = lambda d: d < ann or d >= POST_START
    mdays, idx = _slice(days, keep)
    gate["idx"] = idx
    gate["X"] = design_matrix(mdays, np.array([d >= POST_START for d in mdays]))
    out["activation_plus_anticipation_gate"] = gate
    return out


def run_methods(D: np.ndarray, samples: dict) -> dict[str, dict[str, np.ndarray]]:
    """Per-method batched estimates. The gate method also returns gate p-values;
    reps with gate p < 0.05 are decision 'unidentified' and get no estimate."""
    res = {}
    for name in ("naive_announcement", "verified_activation"):
        s = samples[name]
        beta, se = ols_hac(D[:, s["idx"]], s["X"])
        res[name] = {"beta": beta[:, 7], "se": se[:, 7]}

    g = samples["activation_plus_anticipation_gate"]
    if g["X_gate"] is not None:
        bg, sg = ols_hac(D[:, g["gate_idx"]], g["X_gate"])
        tg = bg[:, 7] / sg[:, 7]
        gate_p = 2.0 * stats.norm.sf(np.abs(tg))
    else:
        gate_p = np.ones(D.shape[0])
    beta, se = ols_hac(D[:, g["idx"]], g["X"])
    unidentified = gate_p < 0.05
    res["activation_plus_anticipation_gate"] = {
        "beta": np.where(unidentified, np.nan, beta[:, 7]),
        "se": np.where(unidentified, np.nan, se[:, 7]),
        "gate_p": gate_p,
        "unidentified": unidentified,
    }
    return res
