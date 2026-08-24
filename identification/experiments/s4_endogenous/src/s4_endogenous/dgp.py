"""S4 semi-synthetic DGP: endogenous adoption driven by latent launch-growth trend.

Per replication, over the 1,379 eligible creators:
  y0[i,d] = a_i + weekday[d] + b_i*(d - 9.5) + resid60[i,d]     (d = 0..59)
  p_i     = logit^-1(alpha + gamma * z(b_i)),  alpha solved so mean p_i = 0.40
  treated ~ Bernoulli(p_i); adoption day in 24..31 by empirical cohort proportions
  y       = y0 + effect * 1[d >= adoption_day]

Oracle fields (b_i, p_i, y0, treated, adoption day) are returned separately
from the estimator input, which carries only (id, t, y, g).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_NPZ = EXPERIMENT_ROOT / "artifacts" / "calibration.npz"

SEVERITIES = {"none": 0.0, "moderate": 0.75, "strong": 1.5}
ARMS = {"zero": 0.0, "positive": 0.20}
N_DAYS = 60
TBAR = 9.5
ADOPTION_DAYS = np.arange(24, 32, dtype=np.int64)  # relative days 24..31
TARGET_SHARE = 0.40
SHARE_GATE = (0.35, 0.45)
PRE_DAYS = 21


def seed_for(gamma: float, arm: str, rep: int) -> int:
    h = hashlib.sha256(f"S4|{gamma}|{arm}|{rep}".encode()).digest()
    return int.from_bytes(h[:8], "little") % (2**32)


def _logit(p: float) -> float:
    return float(np.log(p / (1.0 - p)))


def _expit(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


@dataclass
class Calibration:
    a: np.ndarray            # creator baselines (n,)
    b: np.ndarray            # latent pretrend slopes (n,)
    weekday60: np.ndarray    # weekday effect per pseudo day (60,)
    resid_pool: np.ndarray   # never-v4.1 residual blocks (n_pool, 21)
    cohort_props: np.ndarray # empirical cohort proportions (8,)
    z: np.ndarray            # standardized latent slope (n,)

    @classmethod
    def load(cls, path: Path = CALIBRATION_NPZ) -> "Calibration":
        import json
        d = np.load(path, allow_pickle=False)
        w21 = d["weekday_by_day"]
        weekday60 = w21[np.arange(N_DAYS) % 7]  # day 0 = Monday 2025-08-18
        summary = json.loads((EXPERIMENT_ROOT / "calibration_summary.json").read_text())
        props = np.array(summary["cohort_proportions"], dtype=np.float64)
        assert props.shape == (8,) and abs(props.sum() - 1.0) < 1e-9
        b = d["b"]
        z = (b - b.mean()) / b.std(ddof=1)
        return cls(a=d["a"], b=b, weekday60=weekday60,
                   resid_pool=d["resid_pool"], cohort_props=props, z=z)

    @property
    def n_creators(self) -> int:
        return int(self.a.shape[0])


def solve_intercept(z: np.ndarray, gamma: float, target: float = TARGET_SHARE) -> float:
    """Bisection on alpha so that mean(logit^-1(alpha + gamma*z)) == target."""
    if gamma == 0.0:
        return _logit(target)
    lo, hi = _logit(target) - 10.0 * gamma, _logit(target) + 10.0 * gamma
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _expit(mid + gamma * z).mean() < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@dataclass
class Replication:
    y: np.ndarray        # (n, 60) observed outcome — estimator input
    g: np.ndarray        # (n,) int32, adoption period (1-indexed) or 0 — estimator input
    y0: np.ndarray       # oracle untreated outcomes
    p: np.ndarray        # oracle propensity
    treated: np.ndarray  # oracle assignment
    adopt: np.ndarray    # oracle adoption day (0-indexed), -1 never
    share: float
    true_att: float


def make_replication(cal: Calibration, gamma: float, arm: str, rep: int) -> Replication:
    rng = np.random.default_rng(seed_for(gamma, arm, rep))
    n = cal.n_creators

    # residual block bootstrap: draw a never-v4.1 creator block, circular-shift, tile
    j = rng.integers(0, cal.resid_pool.shape[0], size=n)
    s = rng.integers(0, PRE_DAYS, size=n)
    idx = (np.arange(N_DAYS)[None, :] + s[:, None]) % PRE_DAYS
    res = np.take_along_axis(cal.resid_pool[j], idx, axis=1)

    trend = (np.arange(N_DAYS, dtype=np.float64) - TBAR)[None, :]
    y0 = cal.a[:, None] + cal.weekday60[None, :] + cal.b[:, None] * trend + res

    alpha = solve_intercept(cal.z, gamma)
    p = _expit(alpha + gamma * cal.z)
    treated = rng.random(n) < p
    share = float(treated.mean())
    if not (SHARE_GATE[0] <= share <= SHARE_GATE[1]):
        # adjust intercept only, redraw once (locked rule)
        alpha2 = alpha + (_logit(TARGET_SHARE) - _logit(min(max(share, 1e-6), 1 - 1e-6)))
        p = _expit(alpha2 + gamma * cal.z)
        treated = rng.random(n) < p
        share = float(treated.mean())
        assert SHARE_GATE[0] <= share <= SHARE_GATE[1], f"share gate failed twice: {share}"

    adopt = np.full(n, -1, dtype=np.int64)
    n_t = int(treated.sum())
    if n_t:
        k = rng.choice(len(ADOPTION_DAYS), size=n_t, p=cal.cohort_props)
        adopt[treated] = ADOPTION_DAYS[k]

    effect = ARMS[arm]
    y = y0.copy()
    if effect != 0.0 and n_t:
        rows = np.nonzero(treated)[0]
        post = np.arange(N_DAYS)[None, :] >= adopt[rows][:, None]
        y[rows] += effect * post

    g = np.where(treated, adopt + 1, 0).astype(np.int32)  # R periods are 1..60
    return Replication(y=y, g=g, y0=y0, p=p, treated=treated, adopt=adopt,
                       share=share, true_att=effect)


def estimator_frame(rep: Replication) -> tuple[np.ndarray, np.ndarray]:
    """The only arrays the estimator may see: y (n x n_t, id-major) and g."""
    return rep.y.copy(), rep.g.copy()  # y flattened C-order == R column-major (n_t x n)


def write_batch(panels: list[Replication], out_dir: Path, rep_ids: list[int]) -> None:
    """Binary IO bridge: meta via argv, payloads as little-endian raw files.

    y.bin layout per replication: y flattened in C order of the (n_ids, n_t)
    array, i.e. creator 0 days 1..60, creator 1 days 1..60, ...; R reads it as
    matrix(x, nrow = n_t, ncol = n_ids) giving M[t, id].
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    n = panels[0].y.shape[0]
    with open(out_dir / "y.bin", "wb") as f:
        for p in panels:
            f.write(np.ascontiguousarray(p.y, dtype="<f8").tobytes())
    with open(out_dir / "g.bin", "wb") as f:
        for p in panels:
            f.write(np.ascontiguousarray(p.g, dtype="<i4").tobytes())
    (out_dir / "rep_ids.csv").write_text("rep_id\n" + "\n".join(map(str, rep_ids)) + "\n")
    (out_dir / "shape.csv").write_text(f"n_reps,n_ids,n_t\n{len(panels)},{n},{N_DAYS}\n")
