#!/usr/bin/env python
"""Monte Carlo runner for the S1 experiment.

Usage:
  python run_mc.py --reps 2000 --arms zero,homogeneous,heterogeneous --out artifacts

Writes <out>/results_long.parquet, <out>/cohort_time_truth.parquet and
<out>/run_config.json. Seeds: three-level independent streams
(scenario, arm, replication) via numpy SeedSequence spawn keys.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

EXP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP_DIR / "src"))

from calibration import build_calibration  # noqa: E402
from dgp import ARMS  # noqa: E402
from mc import N_BOOT, SCENARIO_SEED, arm_seed_sequence, run_replication  # noqa: E402
from panel import ADOPTION_DAYS, COHORT_SIZES, PANEL_DAYS  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, required=True)
    ap.add_argument("--arms", type=str, default=",".join(ARMS))
    ap.add_argument("--out", type=str, required=True)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--n-control", type=int, default=None,
                    help="simulated never-treated creators (default 3x treated)")
    ap.add_argument("--scenario-seed", type=int, default=SCENARIO_SEED)
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for a in arms:
        if a not in ARMS:
            ap.error(f"unknown arm {a!r}; choose from {ARMS}")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("building calibration from never-adopter panel ...", flush=True)
    t_cal = time.perf_counter()
    cal = build_calibration()
    print(f"  pool={cal.n_pool} creators, outcome SD={cal.outcome_sd:.4f}, "
          f"built in {time.perf_counter() - t_cal:.1f}s", flush=True)

    all_rows: list[dict] = []
    all_truth: list[dict] = []
    t0 = time.perf_counter()
    for arm in arms:
        arm_seq = arm_seed_sequence(arm, args.scenario_seed)
        rep_seqs = arm_seq.spawn(args.reps)
        t_arm = time.perf_counter()
        for rep in range(args.reps):
            rng = __import__("numpy").random.default_rng(rep_seqs[rep])
            out = run_replication(
                cal, arm, rep, rng, COHORT_SIZES, ADOPTION_DAYS,
                n_days=PANEL_DAYS, n_boot=args.n_boot, n_control=args.n_control,
            )
            all_rows.extend(out.rows)
            all_truth.extend(out.truth_cells)
            if (rep + 1) % 25 == 0 or rep == 0:
                rate = (time.perf_counter() - t_arm) / (rep + 1)
                print(f"  arm={arm} rep {rep + 1}/{args.reps} "
                      f"({rate:.3f}s/rep)", flush=True)
        print(f"arm {arm} done in {time.perf_counter() - t_arm:.1f}s", flush=True)

    results = pd.DataFrame(all_rows)
    truth = pd.DataFrame(all_truth)
    results.to_parquet(out_dir / "results_long.parquet", index=False)
    truth.to_parquet(out_dir / "cohort_time_truth.parquet", index=False)

    elapsed = time.perf_counter() - t0
    config = {
        "reps_per_arm": args.reps,
        "arms": arms,
        "n_boot": args.n_boot,
        "n_control": args.n_control,
        "scenario_seed": args.scenario_seed,
        "cohort_sizes": COHORT_SIZES,
        "adoption_days": ADOPTION_DAYS,
        "panel_days": PANEL_DAYS,
        "calibration_pool": cal.n_pool,
        "outcome_sd": cal.outcome_sd,
        "wall_time_sec": elapsed,
        "completed_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    (out_dir / "run_config.json").write_text(json.dumps(config, indent=2) + "\n")
    print(f"wrote {out_dir / 'results_long.parquet'} ({len(results)} rows), "
          f"{out_dir / 'cohort_time_truth.parquet'} ({len(truth)} rows)")
    print(f"total wall time {elapsed:.1f}s")


if __name__ == "__main__":
    main()
