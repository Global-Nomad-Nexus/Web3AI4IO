"""S4 test suite (dependency-free; run with the experiment venv python).

Covers, per plan section 9:
  gamma zero / strong selection / oracle leakage / zero effect /
  share gate / seed determinism / cohort proportions / intercept calibration.
R-side coverage (universal base period, continuous event times, sensitivity
nesting, deterministic ATT recovery) lives in test_r_bridge.R, driven by
run_tests.py --with-r once the R toolchain is present.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from s4_endogenous.dgp import (ARMS, SEVERITIES, Calibration, make_replication,
                               seed_for, solve_intercept, write_batch)

CAL = Calibration.load()
PASS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    assert cond, f"FAIL {name}: {detail}"
    PASS.append(name)
    print(f"pass: {name}")


def test_gamma_zero_independence() -> None:
    rep = make_replication(CAL, 0.0, "zero", 7)
    r = np.corrcoef(CAL.b, rep.treated.astype(float))[0, 1]
    check("gamma0_assignment_independent_of_slope", abs(r) < 0.06, f"corr={r:.4f}")


def test_strong_selection_direction() -> None:
    rep = make_replication(CAL, 1.5, "zero", 7)
    mb_t = CAL.b[rep.treated].mean()
    mb_c = CAL.b[~rep.treated].mean()
    check("strong_selection_treated_higher_slope", mb_t > mb_c + 0.005,
          f"treated {mb_t:.5f} vs control {mb_c:.5f}")
    # monotone in gamma
    rep_m = make_replication(CAL, 0.75, "zero", 7)
    gap_m = CAL.b[rep_m.treated].mean() - CAL.b[~rep_m.treated].mean()
    check("selection_gap_monotone_in_gamma", 0 < gap_m < (mb_t - mb_c) + 0.02,
          f"gap moderate {gap_m:.5f}, strong {mb_t - mb_c:.5f}")


def test_zero_effect_arm() -> None:
    rep = make_replication(CAL, 1.5, "zero", 3)
    check("zero_arm_y_equals_y0", bool(np.array_equal(rep.y, rep.y0)))
    check("zero_arm_true_att", rep.true_att == 0.0)


def test_positive_arm_effect() -> None:
    rep = make_replication(CAL, 0.0, "positive", 3)
    check("positive_arm_true_att", abs(rep.true_att - 0.20) < 1e-12)
    d = np.arange(rep.y.shape[1])[None, :]
    inj = rep.y - rep.y0
    post = d >= rep.adopt[:, None]
    tr = rep.treated
    check("positive_arm_injection_post", np.allclose(inj[tr][post[tr]], 0.20))
    check("positive_arm_no_injection_pre", np.all(inj[tr][~post[tr]] == 0.0))
    check("positive_arm_no_injection_never", np.all(inj[~tr] == 0.0))


def test_share_gate_and_intercept() -> None:
    for g in SEVERITIES.values():
        alpha = solve_intercept(CAL.z, g)
        p = 1.0 / (1.0 + np.exp(-(alpha + g * CAL.z)))
        check(f"intercept_mean_p_40_g{g}", abs(p.mean() - 0.40) < 1e-6, f"{p.mean():.6f}")
        shares = [make_replication(CAL, g, "zero", r).share for r in range(25)]
        check(f"share_gate_g{g}", all(0.35 <= s <= 0.45 for s in shares),
              f"min {min(shares):.3f} max {max(shares):.3f}")


def test_seed_determinism() -> None:
    a = make_replication(CAL, 0.75, "positive", 11)
    b = make_replication(CAL, 0.75, "positive", 11)
    c = make_replication(CAL, 0.75, "positive", 12)
    check("seed_deterministic", np.array_equal(a.y, b.y) and np.array_equal(a.g, b.g))
    check("seed_distinct_reps", not np.array_equal(a.y, c.y))
    check("seed_scheme_stable", seed_for(0.75, "positive", 11) == seed_for(0.75, "positive", 11))


def test_cohort_proportions() -> None:
    counts = np.zeros(8)
    for r in range(30):
        rep = make_replication(CAL, 0.0, "zero", 1000 + r)
        for k in range(8):
            counts[k] += np.sum(rep.adopt == 24 + k)
    props = counts / counts.sum()
    check("cohort_proportions_match_empirical",
          bool(np.max(np.abs(props - CAL.cohort_props)) < 0.03),
          f"{np.round(props, 3)} vs {np.round(CAL.cohort_props, 3)}")


def test_adoption_support() -> None:
    rep = make_replication(CAL, 0.0, "zero", 5)
    ad = rep.adopt[rep.treated]
    check("adoption_days_in_24_31", bool(((ad >= 24) & (ad <= 31)).all()))
    check("event_time_m7_support", bool((ad - 7 >= 0).all()))
    check("event_time_p7_support", bool((ad + 7 <= 59).all()))
    check("g_encoding", bool((rep.g[rep.treated] == ad + 1).all()
                             and (rep.g[~rep.treated] == 0).all()))


def test_oracle_leakage(tmp: Path) -> None:
    reps = [make_replication(CAL, 0.75, "positive", 21)]
    write_batch(reps, tmp, [21])
    files = sorted(p.name for p in tmp.iterdir())
    check("batch_files_only_payload", files == ["g.bin", "rep_ids.csv", "shape.csv", "y.bin"],
          str(files))
    n = CAL.n_creators
    check("y_bin_size", (tmp / "y.bin").stat().st_size == n * 60 * 8)
    check("g_bin_size", (tmp / "g.bin").stat().st_size == n * 4)
    # payload must not contain latent slopes or propensities
    y = np.fromfile(tmp / "y.bin", dtype="<f8").reshape(n, 60)
    g = np.fromfile(tmp / "g.bin", dtype="<i4")
    check("payload_roundtrip_y", bool(np.array_equal(y, reps[0].y)))
    check("payload_roundtrip_g", bool(np.array_equal(g, reps[0].g)))
    check("payload_no_slope_vector",
          not np.allclose(y[:, 0], CAL.b) and not np.allclose(y[:, 0], reps[0].p))
    check("payload_g_valid", set(np.unique(g)) <= {0, 25, 26, 27, 28, 29, 30, 31, 32})


def test_oracle_detrending_recovers_effect() -> None:
    """Oracle check (unit-test only): removing the true latent trend kills selection bias."""
    rep = make_replication(CAL, 1.5, "positive", 42)
    trend = (np.arange(60) - 9.5)[None, :]
    y_det = rep.y - CAL.b[:, None] * trend  # oracle operation, never seen by estimators

    def twfe(y: np.ndarray) -> float:
        post = (rep.g > 0)[:, None] & (np.arange(60)[None, :] >= rep.g[:, None])
        x = post.astype(float)
        for M in (y, x):
            pass
        yy = y - y.mean(1, keepdims=True) - y.mean(0, keepdims=True) + y.mean()
        xx = x - x.mean(1, keepdims=True) - x.mean(0, keepdims=True) + x.mean()
        return float((xx * yy).sum() / (xx**2).sum())

    biased = twfe(rep.y)
    oracle = twfe(y_det)
    check("oracle_detrend_closer_to_truth", abs(oracle - 0.20) < abs(biased - 0.20),
          f"twfe {biased:.4f}, oracle-detrended {oracle:.4f}")
    check("oracle_detrend_near_truth", abs(oracle - 0.20) < 0.05, f"{oracle:.4f}")


def main() -> None:
    tmp = Path(__file__).resolve().parents[1] / "artifacts" / "_test_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    test_gamma_zero_independence()
    test_strong_selection_direction()
    test_zero_effect_arm()
    test_positive_arm_effect()
    test_share_gate_and_intercept()
    test_seed_determinism()
    test_cohort_proportions()
    test_adoption_support()
    test_oracle_leakage(tmp)
    test_oracle_detrending_recovers_effect()
    import shutil
    shutil.rmtree(tmp)
    if "--with-r" in sys.argv:
        r_script = Path(__file__).resolve().parent / "test_r_bridge.R"
        root = Path(__file__).resolve().parents[1]
        import os
        env = dict(os.environ, R_LIBS=str(root / "R" / "library"))
        proc = subprocess.run(["Rscript", str(r_script), str(root)], env=env)
        assert proc.returncode == 0, "R bridge tests failed"
    print(f"\nAll {len(PASS)} Python checks passed.")


if __name__ == "__main__":
    main()
