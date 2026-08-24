"""Statistical estimators used by the deterministic benchmark arm."""

from __future__ import annotations

from itertools import product
from typing import Iterable

import numpy as np
import pandas as pd
import statsmodels.api as sm


def normal_ci(coef: float, se: float, z: float = 1.96) -> tuple[float, float]:
    return coef - z * se, coef + z * se


def estimate_ols(
    data: pd.DataFrame,
    outcome: str,
    covariates: list[str],
    fixed_effects: list[str] | None = None,
    *,
    cov_type: str = "HC1",
) -> sm.regression.linear_model.RegressionResultsWrapper:
    """Estimate an OLS model with explicit dummy fixed effects.

    The helper keeps the replication package independent of formula parsing and
    makes the design matrix reproducible across Python environments.
    """

    fixed_effects = fixed_effects or []
    columns = list(dict.fromkeys([outcome, *covariates, *fixed_effects]))
    frame = data.loc[:, columns].dropna().copy()
    x_parts = [frame[covariates].astype(float)] if covariates else []
    for fe in fixed_effects:
        dummies = pd.get_dummies(frame[fe].astype(str), prefix=fe, drop_first=True)
        x_parts.append(dummies.astype(float))
    if x_parts:
        x = pd.concat(x_parts, axis=1)
    else:
        x = pd.DataFrame(index=frame.index)
    x = sm.add_constant(x, has_constant="add")
    y = frame[outcome].astype(float)
    return sm.OLS(y, x).fit(cov_type=cov_type)


def coefficient_row(
    rung: str,
    component: str,
    outcome: str,
    fit: sm.regression.linear_model.RegressionResultsWrapper,
    variable: str,
    *,
    method: str,
    decision_threshold: float = 0.0,
    notes: str = "",
) -> dict[str, object]:
    coef = float(fit.params[variable])
    se = float(fit.bse[variable])
    ci_low, ci_high = normal_ci(coef, se)
    worked = "yes" if ci_low > decision_threshold else "no_or_uncertain"
    return {
        "rung": rung,
        "component_added": component,
        "outcome": outcome,
        "estimate": coef,
        "std_error": se,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "p_value": float(fit.pvalues[variable]),
        "worked_decision": worked,
        "method": method,
        "notes": notes,
    }


def two_sample_difference(values_post: pd.Series, values_pre: pd.Series) -> dict[str, float]:
    post = values_post.dropna().astype(float)
    pre = values_pre.dropna().astype(float)
    diff = float(post.mean() - pre.mean())
    var = float(post.var(ddof=1) / len(post) + pre.var(ddof=1) / len(pre))
    se = float(np.sqrt(var))
    ci_low, ci_high = normal_ci(diff, se)
    return {
        "estimate": diff,
        "std_error": se,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
    }


def linear_combination(
    fit: sm.regression.linear_model.RegressionResultsWrapper,
    variables: Iterable[str],
) -> tuple[float, float]:
    variables = list(variables)
    params = fit.params.reindex(variables).astype(float)
    cov = fit.cov_params().reindex(index=variables, columns=variables).astype(float)
    weights = np.ones(len(variables), dtype=float) / max(len(variables), 1)
    estimate = float(weights @ params.to_numpy())
    variance = float(weights @ cov.to_numpy() @ weights)
    return estimate, float(np.sqrt(max(variance, 0.0)))


def exact_rademacher_wild_cluster(
    data: pd.DataFrame,
    outcome: str,
    treatment: str,
    covariates: list[str],
    fixed_effects: list[str],
    cluster: str,
) -> dict[str, object]:
    """Small-cluster wild bootstrap using all Rademacher sign assignments.

    This is intentionally exact over the observed cluster count. For the
    PumpSwap market panel there are only four protocol units, so all 2^4 sign
    assignments are feasible and more transparent than simulation.
    """

    columns = list(dict.fromkeys([outcome, treatment, cluster, *covariates, *fixed_effects]))
    frame = data.loc[:, columns].dropna().copy()
    full = estimate_ols(frame, outcome, [treatment, *covariates], fixed_effects, cov_type="HC1")
    restricted = estimate_ols(frame, outcome, covariates, fixed_effects, cov_type="HC1")
    beta_hat = float(full.params[treatment])
    clusters = sorted(frame[cluster].astype(str).unique())
    fitted_restricted = restricted.fittedvalues.reindex(frame.index)
    residual_restricted = restricted.resid.reindex(frame.index)

    boot_betas: list[float] = []
    for signs in product([-1.0, 1.0], repeat=len(clusters)):
        sign_map = dict(zip(clusters, signs))
        multiplier = frame[cluster].astype(str).map(sign_map).astype(float)
        y_star = fitted_restricted + residual_restricted * multiplier
        boot_frame = frame.copy()
        boot_frame["_y_star"] = y_star
        boot_fit = estimate_ols(
            boot_frame,
            "_y_star",
            [treatment, *covariates],
            fixed_effects,
            cov_type="HC1",
        )
        boot_betas.append(float(boot_fit.params[treatment]))

    arr = np.asarray(boot_betas, dtype=float)
    p_value = float(np.mean(np.abs(arr) >= abs(beta_hat)))
    ci_low, ci_high = np.quantile(arr, [0.025, 0.975])
    return {
        "estimate": beta_hat,
        "std_error_hc1": float(full.bse[treatment]),
        "wild_bootstrap_p_value": p_value,
        "wild_bootstrap_ci95_low": float(ci_low),
        "wild_bootstrap_ci95_high": float(ci_high),
        "cluster_count": len(clusters),
        "sign_assignments": int(len(arr)),
        "method": "Exact Rademacher wild-cluster bootstrap over protocol units",
    }
