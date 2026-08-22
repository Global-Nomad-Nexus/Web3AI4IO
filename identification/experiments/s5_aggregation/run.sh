#!/bin/bash
# S5 temporal aggregation — fresh rerun command.
# Rebuilds ALL outputs from the source CSV: coverage audit, corrected panel,
# validation, calibration, SD_null lock, fidelity gate, tests, full Monte Carlo
# (5 arm cells x 7 offsets x 2000 reps, 499 bootstrap draws each; zero runs once
# per offset, substantive 0.30 and calibration 0.5 x SD_null each in transient +
# persistent profiles), artifacts, figure. Approval 2026-08-14 covers the
# 3-market PRIMARY run only; the Meteora restricted-window sensitivity is a
# separate secondary run, not part of this script.
set -euo pipefail
cd "$(dirname "$0")"
PY="../s2_timing/.venv/bin/python"

export PYTHONPATH="$PWD/src"
"$PY" -m pytest tests/ -q
"$PY" -m s5agg.runner all --reps 2000
"$PY" -c "
import sys; sys.path.insert(0, 'src')
import pandas as pd
from s5agg import paths
from s5agg.figures import make_figure
rs = pd.read_csv(paths.ARTIFACTS / 'results_summary.csv')
make_figure(rs, paths.ARTIFACTS / 'figure_s5')
print('figure written')
"
echo "S5 full rerun complete."
