"""Secondary inference for S5 (plan S4): 499-draw 7-day moving-block bootstrap.

For each generated daily panel we resample the 42-day estimation union window
with 6 moving blocks of length 7 (36 valid starts), recompute all four methods
on each resampled panel, and take percentile 95% intervals. The same resampled
blocks feed all four methods in every draw (they are all deterministic functions
of the same resampled daily panel). Block-start indices are drawn once per
offset and shared across arms, keeping replications paired.
"""

from __future__ import annotations

import numpy as np

from . import paths
from .estimators import WINDOW_LEN, daily_difference

BLOCK_LEN = 7
N_BLOCKS = WINDOW_LEN // BLOCK_LEN  # 6
N_STARTS = WINDOW_LEN - BLOCK_LEN + 1  # 36


def draw_block_positions(n_reps: int, n_boot: int, seed: int) -> np.ndarray:
    """(n_reps, n_boot, 42) day positions, shared across arms within an offset."""
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, N_STARTS, size=(n_reps, n_boot, N_BLOCKS))
    return (starts[..., None] + np.arange(BLOCK_LEN)).reshape(n_reps, n_boot, WINDOW_LEN)


def bootstrap_estimates(
    panel_window: np.ndarray,
    W: np.ndarray,
    positions: np.ndarray,
    chunk: int = 200,
) -> np.ndarray:
    """Bootstrap distribution of all four estimators.

    panel_window: (n_reps, 42, 4); positions: (n_reps, n_boot, 42).
    Returns (n_reps, n_boot, 4) estimates. Chunked over reps to bound memory.
    """
    n_reps = panel_window.shape[0]
    n_boot = positions.shape[1]
    out = np.empty((n_reps, n_boot, W.shape[1]))
    for lo in range(0, n_reps, chunk):
        hi = min(lo + chunk, n_reps)
        pos = positions[lo:hi]  # (c, n_boot, 42)
        # gather resampled panels: (c, n_boot, 42, 4)
        resampled = np.take_along_axis(
            panel_window[lo:hi][:, None, :, :], pos[..., None], axis=2
        )
        d = daily_difference(resampled)  # (c, n_boot, 42)
        out[lo:hi] = d @ W
    return out


def percentile_intervals(boot_est: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Percentile 95% intervals over the bootstrap axis. Returns (lo, hi), each (n, 4)."""
    lo, hi = np.percentile(boot_est, [2.5, 97.5], axis=1)
    return lo, hi


def decisions(ci_lo: np.ndarray, ci_hi: np.ndarray) -> np.ndarray:
    """'positive' if the interval is entirely above 0, else 'null' (plan S4)."""
    return np.where(ci_lo > 0, "positive", "null")
