"""S4 Monte Carlo driver.

Generates replications in Python (DGP + seeds), ships binary batches to
R/estimate_batch.R for estimation, checkpoints one CSV per batch.

Usage:
  python run_mc.py --cell gamma=0.75 --arm positive --reps 2000
  python run_mc.py --all --reps 2000
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s4_endogenous.dgp import (ARMS, SEVERITIES, Calibration, EXPERIMENT_ROOT,
                               make_replication, write_batch)

R_SCRIPT = EXPERIMENT_ROOT / "R" / "estimate_batch.R"
R_LIBRARY = EXPERIMENT_ROOT / "R" / "library"
MC_DIR = EXPERIMENT_ROOT / "artifacts" / "mc"
BATCH_DIR = EXPERIMENT_ROOT / "artifacts" / "_batch_tmp"


def run_cell(gamma: float, arm: str, reps: int, batch_size: int, ncores: int,
             start_rep: int = 0) -> None:
    cell = f"gamma{gamma}_{arm}"
    out_dir = MC_DIR / cell
    out_dir.mkdir(parents=True, exist_ok=True)
    cal = Calibration.load()
    t_start = time.time()
    n_done = 0
    for b0 in range(start_rep, reps, batch_size):
        rep_ids = list(range(b0, min(b0 + batch_size, reps)))
        out_csv = out_dir / f"batch_{b0:05d}.csv"
        if out_csv.exists():
            n_done += len(rep_ids)
            continue
        panels = [make_replication(cal, gamma, arm, r) for r in rep_ids]
        if BATCH_DIR.exists():
            shutil.rmtree(BATCH_DIR)
        write_batch(panels, BATCH_DIR, rep_ids)
        env = dict(os.environ, R_LIBS=str(R_LIBRARY), OMP_NUM_THREADS="1")
        proc = subprocess.run(
            ["Rscript", str(R_SCRIPT), str(BATCH_DIR), str(out_csv), str(ncores)],
            env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            (out_dir / f"batch_{b0:05d}.err.log").write_text(proc.stdout + proc.stderr)
            raise RuntimeError(f"R batch {b0} failed; see {out_dir}/batch_{b0:05d}.err.log")
        n_done += len(rep_ids)
        rate = n_done / (time.time() - t_start)
        eta = (reps - start_rep - n_done) / rate / 60 if rate > 0 else float("nan")
        print(f"[{cell}] {n_done + start_rep}/{reps} reps, {rate:.2f} rep/s, ETA {eta:.1f} min",
              flush=True)
    if BATCH_DIR.exists():
        shutil.rmtree(BATCH_DIR)


def combine() -> None:
    """Combine per-cell batch CSVs into artifacts/results_long.parquet."""
    frames = []
    for cell_dir in sorted(MC_DIR.iterdir()):
        if not cell_dir.is_dir():
            continue
        cell = cell_dir.name
        gamma, arm = cell.rsplit("_", 1)
        csvs = sorted(cell_dir.glob("batch_*.csv"))
        if not csvs:
            continue
        df = pd.concat((pd.read_csv(c) for c in csvs), ignore_index=True)
        df["gamma"] = float(gamma.replace("gamma", ""))
        df["arm"] = arm
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["gamma", "arm", "rep_id"], keep="last")
    out.to_parquet(EXPERIMENT_ROOT / "artifacts" / "results_long.parquet", index=False)
    print(f"results_long.parquet: {len(out)} rows, "
          f"{out.groupby(['gamma', 'arm']).size().to_dict()}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", help="e.g. gamma=0.75", default=None)
    ap.add_argument("--arm", choices=list(ARMS), default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--ncores", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--start-rep", type=int, default=0)
    ap.add_argument("--combine-only", action="store_true")
    args = ap.parse_args()

    if args.combine_only:
        combine()
        return
    cells = []
    if args.all:
        cells = [(g, a) for g in SEVERITIES.values() for a in ARMS]
    else:
        gamma = float(args.cell.split("=")[1])
        assert gamma in SEVERITIES.values() and args.arm in ARMS
        cells = [(gamma, args.arm)]
    for gamma, arm in cells:
        run_cell(gamma, arm, args.reps, args.batch_size, args.ncores, args.start_rep)
    combine()


if __name__ == "__main__":
    main()
