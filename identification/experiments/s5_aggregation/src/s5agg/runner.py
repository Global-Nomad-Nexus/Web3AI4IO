"""S5 experiment runner (revision locked 2026-08-14).

Phases:
  data-prep : coverage audit (primary markets) -> build corrected panel ->
              validate (source 724 rows; primary 543 rows) -> calibrate the
              3-market DGP -> SD_null -> fidelity check + diagnostics -> write
              SD_null into the design lock. Stops before any positive-arm
              simulation if the coverage audit or the fidelity check fails.
  run       : formal Monte Carlo (zero once per offset; substantive 0.30 and
              calibration 0.5 x SD_null, each in transient + persistent
              profiles; 7 weekday offsets; 499 shared-block bootstrap draws
              per panel). Refuses to run when the locked SD_null disagrees
              with a fresh computation or fidelity has not passed.
  all       : data-prep then run.

Usage (via run.sh or directly):
  python -m s5agg.runner all --reps 2000                 # full run
  python -m s5agg.runner all --reps 50 --pilot           # pilot
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import paths
from .build_corrected_panel import build_corrected_panel
from .coverage_audit import run_audit
from .dgp import (
    SIM_REL_DAYS,
    arm_specs,
    calibrate,
    fidelity_check,
    generate_y0,
    inject,
    read_locked_sd_null,
    sd_null,
    write_calibration_summary,
    write_fidelity_report,
    write_sd_null_to_lock,
)
from .estimators import (
    bin_composition,
    estimator_weights,
    offset_params,
    point_estimates,
    window_slice,
)
from .inference import bootstrap_estimates, draw_block_positions, percentile_intervals
from .metrics import cell_metrics, decision_disagreement, paired_differences
from .panel import load_validated_panel, write_data_manifest


def data_prep(exp_dir: Path) -> dict:
    audit = run_audit(exp_dir / "coverage_audit_primary_markets.json")
    if not audit["all_primary_markets_pass"]:
        raise SystemExit(
            "STOP (researcher lock 2026-08-14): a primary market failed the "
            "coverage audit; see coverage_audit_primary_markets.json"
        )
    build_corrected_panel(paths.CORRECTED_PANEL_CSV, paths.CORRECTED_PROVENANCE_JSON)
    df, report = load_validated_panel(out_json=exp_dir / "panel_validation.json")
    write_data_manifest(exp_dir / "data_manifest.json")
    cal = calibrate(df)
    summary = write_calibration_summary(cal, exp_dir / "calibration_summary.json")
    fid = write_fidelity_report(cal, exp_dir / "dgp_fidelity.json")
    write_sd_null_to_lock(paths.DESIGN_LOCK, fid)
    if not fid["fidelity_ok"]:
        raise SystemExit(
            "STOP (researcher lock 2026-08-14, DGP fidelity): SD_null = "
            f"{fid['sd_null']:.4f} outside every empirical sliding-window SD "
            f"95% MBB CI (benchmark A = {fid['benchmark_A_empirical_sliding_window_sd']:.4f}). "
            "See dgp_fidelity.json diagnostics. No positive-arm simulation may run."
        )
    return {
        "df": df,
        "cal": cal,
        "validation": report,
        "calibration_summary": summary,
        "fidelity": fid,
        "sd_null": fid["sd_null"],
    }


def run_cells(cal: dict, sd_null_value: float, n_reps: int, offsets: list[int], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    arms = arm_specs(sd_null_value)

    y0 = generate_y0(cal, n_reps, seed=paths.SEED_Y0)
    np.savez_compressed(
        out_dir / "y0_panels.npz",
        y0=y0.astype(np.float32),
        rel_days=SIM_REL_DAYS,
        units=np.array(paths.UNITS),
        seed=np.array([paths.SEED_Y0]),
        note=np.array(
            ["Y0 panels (float32) shared across arms/offsets; 3-market primary "
             "panel; injections per arm_specs in run_meta.json"]
        ),
    )

    long_rows = []
    summary_rows = []
    paired_rows = []
    bin_rows = []

    for k in offsets:
        p = offset_params(k)
        W = estimator_weights(k)
        bin_rows.extend(bin_composition(k))
        positions = draw_block_positions(n_reps, paths.N_BOOT, seed=paths.SEED_BOOT + k)

        cell_meta = {}
        for spec in arms:
            arm = spec["arm"]
            truth = spec["truth"]
            y1 = inject(y0, spec["profile"], spec["amplitude"])
            win = window_slice(y1, k)
            est = point_estimates(win, W)
            boot = bootstrap_estimates(win, W, positions)
            ci_lo, ci_hi = percentile_intervals(boot)

            for m, method in enumerate(paths.METHODS):
                dec = np.where(ci_lo[:, m] > 0, "positive", "null")
                long_rows.append(
                    pd.DataFrame(
                        {
                            "arm": arm,
                            "offset": k,
                            "event_weekday": p["event_weekday"],
                            "rep": np.arange(n_reps),
                            "method": method,
                            "estimate": est[:, m],
                            "ci_lo": ci_lo[:, m],
                            "ci_hi": ci_hi[:, m],
                            "decision": dec,
                            "truth": truth,
                        }
                    )
                )

            for row in cell_metrics(est, ci_lo, ci_hi, truth):
                row.update(
                    {
                        "arm": arm,
                        "offset": k,
                        "event_weekday": p["event_weekday"],
                        "event_week_contamination_share": p["contamination_share"],
                    }
                )
                summary_rows.append(row)
            cell_meta[arm] = decision_disagreement(ci_lo, ci_hi)

            pdiff = paired_differences(est)
            paired_rows.append(
                pd.DataFrame(
                    {
                        "arm": arm,
                        "offset": k,
                        "event_weekday": p["event_weekday"],
                        "rep": np.arange(n_reps),
                        **pdiff,
                    }
                )
            )

        # attach decision-disagreement rates to summary rows of this offset
        for row in summary_rows:
            if row["offset"] == k:
                for key, val in cell_meta[row["arm"]].items():
                    row[key] = val

        elapsed = time.time() - t0
        print(f"[offset {k} ({p['event_weekday']})] done, elapsed {elapsed:.1f}s", flush=True)

    results_long = pd.concat(long_rows, ignore_index=True)
    results_summary = pd.concat(
        [pd.DataFrame(r, index=[0]) for r in summary_rows], ignore_index=True
    )
    paired = pd.concat(paired_rows, ignore_index=True)
    bincomp = pd.DataFrame(bin_rows)

    results_long.to_parquet(out_dir / "results_long.parquet", index=False)
    results_summary.to_csv(out_dir / "results_summary.csv", index=False)
    paired.to_parquet(out_dir / "paired_differences.parquet", index=False)
    bincomp.to_csv(out_dir / "bin_composition.csv", index=False)

    meta = {
        "n_reps_per_cell": n_reps,
        "offsets": offsets,
        "arms": [
            {k: v for k, v in spec.items()} for spec in arms
        ],
        "sd_null": sd_null_value,
        "n_bootstrap_draws": paths.N_BOOT,
        "seed_y0": paths.SEED_Y0,
        "seed_bootstrap": paths.SEED_BOOT,
        "runtime_seconds": time.time() - t0,
    }
    with open(out_dir / "run_meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"cells finished in {meta['runtime_seconds']:.1f}s -> {out_dir}", flush=True)
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["data-prep", "run", "all"])
    ap.add_argument("--reps", type=int, default=paths.N_REPS_FULL)
    ap.add_argument("--offsets", type=int, nargs="+", default=list(range(paths.N_OFFSETS)))
    ap.add_argument("--pilot", action="store_true", help="write to artifacts/pilot/")
    args = ap.parse_args(argv)

    exp_dir = paths.EXPERIMENT_DIR
    out_dir = exp_dir / "artifacts" / "pilot" if args.pilot else exp_dir / "artifacts"

    prep = None
    if args.phase in ("data-prep", "all"):
        prep = data_prep(exp_dir)
        print(
            f"data-prep done: coverage audit passed, corrected panel validated, "
            f"SD_null = {prep['sd_null']:.4f} locked, fidelity passed",
            flush=True,
        )
    if args.phase in ("run", "all"):
        if prep is None:
            df, _ = load_validated_panel()
            cal = calibrate(df)
            fid = fidelity_check(cal)
            if not fid["fidelity_ok"]:
                raise SystemExit("STOP: DGP fidelity check failed, run data-prep for details")
            locked = read_locked_sd_null(paths.DESIGN_LOCK)
            if locked is None or locked != fid["sd_null"]:
                raise SystemExit(
                    "STOP: design-lock SD_null does not match a fresh computation "
                    f"(locked={locked}, fresh={fid['sd_null']}); rerun data-prep"
                )
            prep = {"df": df, "cal": cal, "sd_null": fid["sd_null"]}
        run_cells(prep["cal"], prep["sd_null"], args.reps, args.offsets, out_dir)


if __name__ == "__main__":
    sys.exit(main())
