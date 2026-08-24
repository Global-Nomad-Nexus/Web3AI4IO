"""Metric computation for S5 (plan S7)."""

from __future__ import annotations

import numpy as np

from . import paths


def cell_metrics(est: np.ndarray, ci_lo: np.ndarray, ci_hi: np.ndarray, truth: float) -> list[dict]:
    """Per-method metrics for one arm x offset cell.

    est, ci_lo, ci_hi: (n_reps, 4) in paths.METHODS order.
    """
    n = est.shape[0]
    dec = np.where(ci_lo > 0, "positive", "null")
    rows = []
    for m, method in enumerate(paths.METHODS):
        e = est[:, m]
        err = e - truth
        covers = (ci_lo[:, m] <= truth) & (truth <= ci_hi[:, m])
        is_pos = dec[:, m] == "positive"
        if truth == 0.0:
            fpr = float(is_pos.mean())
            fnr = np.nan
            sign_correct = np.nan
            claim_accuracy = float((~is_pos).mean())  # correct claim is "null"
            attenuation = np.nan
        else:
            fpr = np.nan
            fnr = float((~is_pos).mean())
            sign_correct = float((np.sign(e) == np.sign(truth)).mean())
            claim_accuracy = float(is_pos.mean())  # correct claim is "positive"
            attenuation = float(e.mean() / truth)
        rows.append(
            {
                "method": method,
                "n_reps": int(n),
                "truth": truth,
                "mean_estimate": float(e.mean()),
                "bias": float(err.mean()),
                "mcse_bias": float(e.std(ddof=1) / np.sqrt(n)),
                "rmse": float(np.sqrt((err**2).mean())),
                "sd_estimate": float(e.std(ddof=1)),
                "coverage_95": float(covers.mean()),
                "fpr": fpr,
                "fnr": fnr,
                "sign_correctness": sign_correct,
                "claim_accuracy": claim_accuracy,
                "effect_attenuation": attenuation,
            }
        )
    return rows


def decision_disagreement(ci_lo: np.ndarray, ci_hi: np.ndarray) -> dict:
    """Decision disagreement across the four methods within each replication."""
    dec = np.where(ci_lo > 0, 1, 0)  # (n, 4)
    any_disagree = (dec.min(axis=1) != dec.max(axis=1)).mean()
    out = {"any_method_disagreement": float(any_disagree)}
    for m, method in enumerate(paths.METHODS):
        if method == "daily":
            continue
        out[f"disagree_{method}_vs_daily"] = float((dec[:, m] != dec[:, 0]).mean())
    return out


def paired_differences(est: np.ndarray) -> dict[str, np.ndarray]:
    """Per-replication method-minus-daily estimate differences."""
    return {
        f"{method}_minus_daily": est[:, m] - est[:, 0]
        for m, method in enumerate(paths.METHODS)
        if method != "daily"
    }
