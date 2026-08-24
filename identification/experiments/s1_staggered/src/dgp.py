"""Semi-synthetic DGP for the S1 staggered-adoption experiment.

Simulates a 60-day creator-day pseudo panel with a hurdle count model:
  layer 1: creator active on day d ~ Bernoulli(clip(p_i * act_mult_dow[d]))
  layer 2: given active, count = 1 + Poisson(max(mu_i * cnt_mult_dow[d] * m_id - 1, eps))
           so E[count | active] = mu_i * cnt_mult_dow[d] * m_id exactly.
  m_id = exp(injected log effect) on treated post-adoption days, else 1.
Layer 1 (activity) is never shifted by treatment; the injected effect scales
the expected launch rate through the count layer only.

Arms (registered constants, design_lock.yaml):
  zero:         no effect
  homogeneous:  delta = 0.20 on all post-adoption days
  heterogeneous delta(c, e) = exposure_effect(e) + cohort_modifier[c]
                exposure e = t - g: 0.10 (e 0-2), 0.20 (e 3-6), 0.35 (e 7+)
                cohort modifier early->late: 0.07 0.05 0.03 0.01 -0.01 -0.03 -0.05 -0.07
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from calibration import Calibration, stratified_draw

ARMS = ("zero", "homogeneous", "heterogeneous")
HOMOGENEOUS_EFFECT = 0.20
EXPOSURE_EFFECTS = (0.10, 0.20, 0.35)  # days 0-2, 3-6, 7+
COHORT_MODIFIERS = (0.07, 0.05, 0.03, 0.01, -0.01, -0.03, -0.05, -0.07)
EPS = 1e-9


def exposure_effect(e: np.ndarray) -> np.ndarray:
    out = np.full(e.shape, EXPOSURE_EFFECTS[2], dtype=float)
    out[e <= 2] = EXPOSURE_EFFECTS[0]
    out[(e >= 3) & (e <= 6)] = EXPOSURE_EFFECTS[1]
    return out


def log_effect(arm: str, cohort: int, day: np.ndarray, adoption_day: int) -> np.ndarray:
    """Injected log effect for a cohort on the given days (0 pre-adoption)."""
    e = day - adoption_day
    post = e >= 0
    if arm == "zero":
        return np.zeros(day.shape)
    if arm == "homogeneous":
        return np.where(post, HOMOGENEOUS_EFFECT, 0.0)
    if arm == "heterogeneous":
        base = exposure_effect(np.clip(e, 0, None))
        return np.where(post, base + COHORT_MODIFIERS[cohort], 0.0)
    raise ValueError(f"unknown arm {arm}")


@dataclass
class SimulatedPanel:
    y: np.ndarray  # (n_creators, n_days) log1p outcome
    count: np.ndarray  # (n_creators, n_days) raw counts
    cohort: np.ndarray  # (n_creators,) cohort index, -1 = never treated
    adoption_day: np.ndarray  # (n_creators,) adoption day, -1 = never treated
    p_active: np.ndarray  # (n_creators, n_days) untreated activity probability
    lam_untreated: np.ndarray  # (n_creators, n_days) untreated E[count|active]
    lam_treated: np.ndarray  # (n_creators, n_days) injected E[count|active]
    n_days: int


def simulate_panel(
    cal: Calibration,
    cohort_sizes: list[int],
    adoption_days: list[int],
    arm: str,
    rng: np.random.Generator,
    n_control: int,
    n_days: int = 60,
) -> SimulatedPanel:
    n_treated = int(sum(cohort_sizes))
    treated_idx = stratified_draw(cal, n_treated, rng)
    control_idx = stratified_draw(cal, n_control, rng)
    pool_idx = np.concatenate([treated_idx, control_idx])
    n = len(pool_idx)

    cohort = np.full(n, -1, dtype=int)
    adoption = np.full(n, -1, dtype=int)
    start = 0
    for c, size in enumerate(cohort_sizes):
        cohort[start : start + size] = c
        adoption[start : start + size] = adoption_days[c]
        start += size

    dow = cal.dow(n_days)
    p_i = cal.pool_p_active[pool_idx]
    mu_i = cal.pool_mu_count[pool_idx]

    p_mat = np.clip(p_i[:, None] * cal.act_mult_dow[dow][None, :], 0.0, 0.999)
    lam0 = mu_i[:, None] * cal.cnt_mult_dow[dow][None, :]

    # Injected intensity multiplier.
    days = np.arange(n_days)
    mult = np.ones((n, n_days))
    for c, g in enumerate(adoption_days):
        rows = cohort == c
        mult[rows] = np.exp(log_effect(arm, c, days, g))[None, :].repeat(rows.sum(), axis=0)
    lam1 = lam0 * mult

    active = rng.random((n, n_days)) < p_mat
    poisson_lam = np.clip(lam1 - 1.0, EPS, None)
    count = np.where(active, 1 + rng.poisson(poisson_lam), 0)
    y = np.log1p(count.astype(float))

    return SimulatedPanel(
        y=y,
        count=count,
        cohort=cohort,
        adoption_day=adoption,
        p_active=p_mat,
        lam_untreated=lam0,
        lam_treated=lam1,
        n_days=n_days,
    )
