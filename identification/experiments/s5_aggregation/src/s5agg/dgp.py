"""Semi-synthetic DGP for S5 (plan S3; revision locked 2026-08-14).

Calibration uses ONLY pre-event data (rel_day = -90..-1) of the PRIMARY
3-market corrected panel (pump_ecosystem, raydium, orca; Meteora excluded per
the locked missing-data policy):
  log_volume[u,t] = unit_fe[u] + weekday_effect[w(t)] + day_shock[t] + resid[u,t]
fitted as balanced two-way (unit + day) fixed effects; the day effect is then
decomposed into a weekday mean and a within-weekday day deviation. Simulation
draws the same-day 3-market residual vector via a moving-block bootstrap
(primary block length 7; fixed sensitivity set 14/21/28) and rebuilds an
84-day Y0 panel over rel_day=-56..27. Day shocks are not re-simulated: every
estimator differences them out cross-sectionally.

The old daily-residual-SD effect gate is DELETED (researcher lock 2026-08-14):
it was dominated by the rare Meteora zero regime and is not on the seven-day
ATT difficulty scale. SD_null — the sampling SD of the daily estimator's
seven-day ATT under this null DGP — is computed here and written into the
design lock BEFORE any positive-arm simulation.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import paths

PRE_REL_DAYS = np.arange(-90, 0)  # calibration window
SIM_REL_DAYS = np.arange(-56, 28)  # 84-day simulated window
BLOCK_LEN = 7  # primary block length


def calibrate(df: pd.DataFrame) -> dict:
    """Fit unit FE + weekday effects + common day shock on pre-event data."""
    pre = df[df["rel_day"] < 0].copy()
    # X: rows = days (rel_day -90..-1), cols = units in paths.UNITS order
    X = (
        pre.pivot(index="rel_day", columns="unit", values="log_volume")
        .loc[PRE_REL_DAYS, paths.UNITS]
        .to_numpy()
    )
    if not np.isfinite(X).all():
        raise SystemExit("STOP (plan S10): pre-event residual vector has missing values")

    n_days, n_units = X.shape
    grand = X.mean()
    unit_fe = X.mean(axis=0) - grand          # sum-to-zero unit effects
    day_fe = X.mean(axis=1) - grand           # common day shock (sum-to-zero)

    weekdays = np.array(
        [(pd.Timestamp(paths.EVENT_DATE) + pd.Timedelta(days=int(r))).weekday() for r in PRE_REL_DAYS]
    )
    weekday_effect = np.zeros(7)
    for w in range(7):
        weekday_effect[w] = day_fe[weekdays == w].mean()

    resid = X - grand - unit_fe[None, :] - day_fe[:, None]
    resid_sd = float(resid.std(ddof=1))
    d_resid = resid[:, 0] - resid[:, 1:].mean(axis=1)  # treated-control difference residual

    return {
        "grand_mean": float(grand),
        "unit_fe": unit_fe,                    # (3,) in paths.UNITS order
        "weekday_effect": weekday_effect,      # (7,), Monday=0
        "resid": resid,                        # (90, 3) pre-event residual vectors
        "resid_sd": resid_sd,
        "d_resid": d_resid,                    # (90,) residualized daily difference
        "n_calib_days": n_days,
        "weekdays_sim": np.array(
            [(pd.Timestamp(paths.EVENT_DATE) + pd.Timedelta(days=int(r))).weekday() for r in SIM_REL_DAYS]
        ),
    }


def generate_y0(
    cal: dict, n_reps: int, seed: int = paths.SEED_Y0, block_len: int = BLOCK_LEN
) -> np.ndarray:
    """Moving-block bootstrap of the 3-market residual vector.

    Returns Y0 of shape (n_reps, 84, 3): days are rel_day=-56..27, units in
    paths.UNITS order (pump first). Shared across all arms and offsets.
    """
    resid = cal["resid"]  # (90, 3)
    n_pool = resid.shape[0]
    n_starts = n_pool - block_len + 1
    n_blocks = int(np.ceil(len(SIM_REL_DAYS) / block_len))

    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n_starts, size=(n_reps, n_blocks))
    positions = starts[..., None] + np.arange(block_len)
    positions = positions.reshape(n_reps, -1)[:, : len(SIM_REL_DAYS)]
    resid_boot = resid[positions]                          # (n_reps, 84, 3)

    level = (
        cal["grand_mean"]
        + cal["unit_fe"][None, None, :]
        + cal["weekday_effect"][cal["weekdays_sim"]][None, :, None]
    )
    return level + resid_boot


def inject(y0: np.ndarray, profile: str | None, amplitude: float) -> np.ndarray:
    """Inject the known effect on pump (column 0) in event time.

    profile: None (zero arm), "transient" (rel_day 0..2) or "persistent"
    (rel_day 0..6). The effect path is defined in event time and does not
    move with calendar weekday (plan S5).
    """
    y1 = y0.copy()
    if profile is None:
        return y1
    base = 56  # rel_day 0 is index 56
    days = paths.PROFILES[profile]
    y1[:, base : base + days, 0] += amplitude
    return y1


def arm_specs(sd_null: float) -> list[dict]:
    """Locked arm definitions (2026-08-14). T = 0.5 x SD_null is on the
    seven-day ATT scale: calibration persistent amplitude = T, calibration
    transient amplitude = 7T/3 (same seven-day ATT). Zero runs once per
    offset. Substantive and calibration arms are reported separately."""
    T = paths.CALIBRATION_MULTIPLIER * sd_null
    s = paths.EFFECT_SUBSTANTIVE
    return [
        {"arm": "zero", "profile": None, "amplitude": 0.0, "truth": 0.0},
        {"arm": "substantive_transient", "profile": "transient", "amplitude": s, "truth": 3 * s / 7},
        {"arm": "substantive_persistent", "profile": "persistent", "amplitude": s, "truth": s},
        {"arm": "calibration_transient", "profile": "transient", "amplitude": 7 * T / 3, "truth": T},
        {"arm": "calibration_persistent", "profile": "persistent", "amplitude": T, "truth": T},
    ]


def sd_null(cal: dict, n_draws: int = paths.N_SDNULL_DRAWS, seed: int = paths.SEED_SDNULL,
            block_len: int = BLOCK_LEN) -> dict:
    """SD_null: sampling SD of the daily estimator's seven-day ATT under the
    revised 3-market null DGP. Locked before any positive-arm simulation.

    beta_daily = mean(D_t, rel_day=0..6) - mean(D_t, rel_day=-28..-1) on
    n_draws null Y0 panels from the moving-block bootstrap DGP.
    """
    y0 = generate_y0(cal, n_draws, seed=seed, block_len=block_len)
    win = y0[:, 28:63, :]  # rel_day -28..6 (rel_day -56 is index 0)
    d = win[..., 0] - win[..., 1:].mean(axis=-1)
    est = d[:, 28:].mean(axis=1) - d[:, :28].mean(axis=1)  # null beta_daily
    sd = float(est.std(ddof=1))
    return {
        "sd": sd,
        "mcse": sd / float(np.sqrt(2 * (n_draws - 1))),
        "n_draws": int(n_draws),
        "block_len": int(block_len),
        "seed": int(seed),
        "estimates": est,
    }


def sliding_window_estimates(d: np.ndarray) -> np.ndarray:
    """Null daily seven-day ATT estimates on all overlapping 35-day windows
    of a daily difference series d (28 pre + 7 post per window)."""
    d = np.asarray(d, dtype=float)
    n = d.shape[0]
    w = paths.FID_WINDOW_PRE + paths.FID_WINDOW_POST
    c = np.concatenate([[0.0], np.cumsum(d)])
    s = np.arange(n - w + 1)
    pre = (c[s + paths.FID_WINDOW_PRE] - c[s]) / paths.FID_WINDOW_PRE
    post = (c[s + w] - c[s + paths.FID_WINDOW_PRE]) / paths.FID_WINDOW_POST
    return post - pre


def _sliding_est_batch(series2d: np.ndarray) -> np.ndarray:
    """Sliding-window estimates for each row of a (B, n) batch."""
    B, n = series2d.shape
    w = paths.FID_WINDOW_PRE + paths.FID_WINDOW_POST
    c = np.concatenate([np.zeros((B, 1)), np.cumsum(series2d, axis=1)], axis=1)
    s = np.arange(n - w + 1)
    pre = (c[:, s + paths.FID_WINDOW_PRE] - c[:, s]) / paths.FID_WINDOW_PRE
    post = (c[:, s + w] - c[:, s + paths.FID_WINDOW_PRE]) / paths.FID_WINDOW_POST
    return post - pre


def empirical_sliding_window_sd(
    d: np.ndarray,
    block_lengths=paths.FID_BLOCK_LENGTHS,
    n_boot: int = paths.FID_N_BOOT,
    seed: int = paths.SEED_FID,
) -> dict:
    """Fidelity benchmark A: SD of the null daily seven-day ATT estimator
    computed empirically by sliding the 35-day window across the 90 pre-event
    days (56 overlapping windows). Uncertainty: moving-block bootstrap of the
    90-day D series at several block lengths (the 56 windows overlap and are
    NOT 56 independent samples, so a naive SE is not reported)."""
    d = np.asarray(d, dtype=float)
    n = d.shape[0]
    est = sliding_window_estimates(d)
    sd = float(est.std(ddof=1))
    rng = np.random.default_rng(seed)
    cis = {}
    for L in block_lengths:
        n_blocks = int(np.ceil(n / L))
        starts = rng.integers(0, n - L + 1, size=(n_boot, n_blocks))
        pos = (starts[..., None] + np.arange(L)).reshape(n_boot, -1)[:, :n]
        sds = _sliding_est_batch(d[pos]).std(axis=1, ddof=1)
        cis[f"block_len_{L}"] = [
            float(np.percentile(sds, 2.5)),
            float(np.percentile(sds, 97.5)),
        ]
    return {"sd": sd, "n_windows": int(est.shape[0]), "estimates": est, "mbb_ci95": cis}


def fidelity_check(cal: dict) -> dict:
    """DGP fidelity check (locked 2026-08-14): compare SD_null (benchmark B,
    primary block length 7) against the empirical sliding-window SD
    (benchmark A) with uncertainty on BOTH sides, plus a FIXED block-length
    sensitivity set (7/14/21/28) — no block length is chosen by fit to the
    benchmark. The check fails if B lies outside every block-length MBB 95%
    CI of A."""
    from scipy import stats

    d = cal["d_resid"]
    emp = empirical_sliding_window_sd(d)
    null = sd_null(cal)
    seed_sds = [sd_null(cal, seed=s)["sd"] for s in (1, 2, 3)]

    # fixed block-length sensitivity for the simulated null distribution
    q = [1, 5, 25, 50, 75, 95, 99]
    emp_est = emp["estimates"]
    sens = {}
    for L in paths.DGP_BLOCK_LENGTHS:
        r = sd_null(cal, block_len=L)
        sens[f"L{L}"] = {
            "sd": r["sd"],
            "skewness": float(stats.skew(r["estimates"])),
            "quantiles_pct": dict(zip(q, [round(float(v), 4) for v in np.percentile(r["estimates"], q)])),
            "ks_vs_empirical": float(stats.ks_2samp(emp_est, r["estimates"]).statistic),
        }

    ci_hi_max = max(hi for _, hi in emp["mbb_ci95"].values())
    ci_lo_min = min(lo for lo, _ in emp["mbb_ci95"].values())
    ok = bool(ci_lo_min <= null["sd"] <= ci_hi_max)
    return {
        "benchmark_A_empirical_sliding_window_sd": emp["sd"],
        "benchmark_A_n_overlapping_windows": emp["n_windows"],
        "benchmark_A_mbb_ci95": emp["mbb_ci95"],
        "benchmark_A_skewness": float(stats.skew(emp_est)),
        "benchmark_A_quantiles_pct": dict(zip(q, [round(float(v), 4) for v in np.percentile(emp_est, q)])),
        "benchmark_A_note": "56 overlapping windows are dependent; uncertainty via MBB of the 90-day D series at block lengths 14/21/28, 10,000 resamples each",
        "sd_null": null["sd"],
        "sd_null_mcse": null["mcse"],
        "sd_null_n_draws": null["n_draws"],
        "sd_null_seed_sensitivity_sds": seed_sds,
        "difference_B_minus_A": null["sd"] - emp["sd"],
        "ratio_B_over_A": null["sd"] / emp["sd"],
        "block_length_sensitivity": sens,
        "block_length_note": "fixed comparison set 7/14/21/28; L=7 primary; no block length selected by fit to the empirical benchmark",
        "fidelity_ok": ok,
        "fidelity_blocker": (
            None if ok else
            "STOP (researcher lock 2026-08-14): SD_null lies outside every "
            "empirical sliding-window SD 95% MBB CI; diagnose the block "
            "bootstrap before any positive-arm simulation"
        ),
        "_empirical_estimates": emp_est,
        "_dgp_null_estimates": null["estimates"],
    }


def calibration_diagnostics(cal: dict, fid: dict) -> dict:
    """Calibration diagnostics on the 3-market primary panel (locked
    2026-08-14): residual ACF, long-run variance, skewness, zero-volume
    frequency, extreme-date contributions, estimator variance decomposition,
    and the empirical vs simulated 35-day ATT distributions."""
    from scipy import stats

    d = cal["d_resid"]
    n = d.shape[0]
    max_lag = 35
    dm = d - d.mean()
    gamma = np.array([np.mean(dm[: n - h] * dm[h:]) for h in range(max_lag + 1)])
    acf = gamma / gamma[0]
    lrw = gamma[0] + 2 * float(
        np.sum((1 - np.arange(1, max_lag + 1) / (max_lag + 1)) * gamma[1:])
    )

    # estimator variance decomposition from the empirical autocovariance
    w = np.concatenate([
        np.full(paths.FID_WINDOW_PRE, -1.0 / paths.FID_WINDOW_PRE),
        np.full(paths.FID_WINDOW_POST, 1.0 / paths.FID_WINDOW_POST),
    ])
    idx = np.arange(w.shape[0])
    lagmat = np.abs(idx[:, None] - idx[None, :])
    W = np.outer(w, w)
    var_emp = float(np.sum(W * gamma[lagmat]))
    gamma_trunc = gamma.copy()
    gamma_trunc[BLOCK_LEN:] = 0.0
    var_trunc = float(np.sum(W * gamma_trunc[lagmat]))

    est_emp = fid["_empirical_estimates"]
    est_sim = fid["_dgp_null_estimates"]
    q = [1, 5, 25, 50, 75, 95, 99]
    ks = stats.ks_2samp(est_emp, est_sim)

    top_extreme = np.argsort(-np.abs(dm))[:5]
    return {
        "panel": "primary 3-market corrected panel (pump_ecosystem, raydium, orca)",
        "zero_volume_days_in_primary_panel": 0,
        "zero_volume_note": "primary markets pass the coverage audit with no zero-volume days in the registered window (coverage_audit_primary_markets.json); the Meteora zero regime is excluded from the primary specification",
        "d_resid_sd": float(d.std(ddof=1)),
        "d_resid_skewness": float(stats.skew(d)),
        "residual_acf_lag1_35": [round(float(a), 4) for a in acf[1:]],
        "long_run_variance_nw35": lrw,
        "long_run_variance_over_naive_variance": lrw / float(gamma[0]),
        "estimator_variance_decomposition": {
            "var_empirical_all_lags": var_emp,
            "sd_empirical_all_lags": float(np.sqrt(var_emp)),
            "var_truncated_at_lag7_like_MBB": var_trunc,
            "sd_truncated_at_lag7_like_MBB": float(np.sqrt(var_trunc)),
        },
        "top5_abs_residual_rel_days": [int(i - 90) for i in top_extreme],
        "top5_abs_residual_values": [round(float(dm[i]), 3) for i in top_extreme],
        "empirical_vs_simulated_window_att_distribution": {
            "quantile_levels_pct": q,
            "empirical_quantiles": [round(float(v), 4) for v in np.percentile(est_emp, q)],
            "dgp_null_quantiles": [round(float(v), 4) for v in np.percentile(est_sim, q)],
            "empirical_sd": float(est_emp.std(ddof=1)),
            "empirical_skewness": float(stats.skew(est_emp)),
            "dgp_null_sd": float(est_sim.std(ddof=1)),
            "dgp_null_skewness": float(stats.skew(est_sim)),
            "ks_statistic": float(ks.statistic),
            "ks_pvalue": float(ks.pvalue),
        },
    }


def calibration_summary(cal: dict) -> dict:
    resid = cal["resid"]
    return {
        "calibration_window": "rel_day=-90..-1 (pre-event only)",
        "panel": "primary 3-market corrected panel (Meteora excluded, locked 2026-08-14)",
        "n_days": int(cal["n_calib_days"]),
        "n_units": len(paths.UNITS),
        "model": "log_volume = unit_fe + weekday_effect + day_shock + residual (balanced two-way FE; day shock decomposed into weekday mean + within-weekday deviation)",
        "unit_fe": {u: float(v) for u, v in zip(paths.UNITS, cal["unit_fe"])},
        "weekday_effect_mon_to_sun": [float(v) for v in cal["weekday_effect"]],
        "residual_sd": cal["resid_sd"],
        "residual_sd_per_unit": {
            u: float(resid[:, i].std(ddof=1)) for i, u in enumerate(paths.UNITS)
        },
        "residual_cross_market_corr": np.corrcoef(resid.T).round(6).tolist(),
        "d_resid_sd": float(cal["d_resid"].std(ddof=1)),
        "effect_gate": "DELETED 2026-08-14: the daily-residual-SD gate was dominated by the rare Meteora zero regime and is not on the seven-day ATT difficulty scale; 0.30 is a substantive low-power arm and never stops the run",
        "units_order": paths.UNITS,
        "weekday_convention": "Monday=0..Sunday=6",
    }


def write_calibration_summary(cal: dict, out_path):
    summary = calibration_summary(cal)
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    return summary


def write_fidelity_report(cal: dict, out_path) -> dict:
    """Run the fidelity check + diagnostic battery and write dgp_fidelity.json."""
    fid = fidelity_check(cal)
    diag = calibration_diagnostics(cal, fid)
    report = {k: v for k, v in fid.items() if not k.startswith("_")}
    report["diagnostics"] = diag
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    return report


SD_NULL_LOCK_BEGIN = "# BEGIN SD_NULL_LOCK (machine-written by s5agg.runner)"
SD_NULL_LOCK_END = "# END SD_NULL_LOCK"


def write_sd_null_to_lock(lock_path, fid: dict) -> None:
    """Write SD_null into the design lock between the managed markers.

    Runs in data-prep, BEFORE any positive-arm simulation. The run phase
    refuses positive arms if a fresh SD_null computation disagrees with the
    locked value.
    """
    text = lock_path.read_text(encoding="utf-8")
    block = (
        f"{SD_NULL_LOCK_BEGIN}\n"
        f"sd_null_lock:\n"
        f"  value: {fid['sd_null']!r}\n"
        f"  mcse: {fid['sd_null_mcse']!r}\n"
        f"  n_draws: {fid['sd_null_n_draws']}\n"
        f"  seed: {paths.SEED_SDNULL}\n"
        f"  block_len: {BLOCK_LEN}\n"
        f'  definition: "sampling SD of the daily estimator seven-day ATT under the revised 3-market null DGP"\n'
        f"  calibration_arm_T: {paths.CALIBRATION_MULTIPLIER * fid['sd_null']!r}\n"
        f"  calibration_transient_amplitude: {7 * paths.CALIBRATION_MULTIPLIER * fid['sd_null'] / 3!r}\n"
        f"{SD_NULL_LOCK_END}"
    )
    if SD_NULL_LOCK_BEGIN in text:
        pre = text.split(SD_NULL_LOCK_BEGIN)[0]
        post = text.split(SD_NULL_LOCK_END)[1]
        text = pre + block + post
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    lock_path.write_text(text, encoding="utf-8")


def read_locked_sd_null(lock_path) -> float | None:
    text = lock_path.read_text(encoding="utf-8")
    if SD_NULL_LOCK_BEGIN not in text:
        return None
    block = text.split(SD_NULL_LOCK_BEGIN)[1].split(SD_NULL_LOCK_END)[0]
    for line in block.splitlines():
        if line.strip().startswith("value:"):
            return float(line.split(":", 1)[1].strip())
    return None
