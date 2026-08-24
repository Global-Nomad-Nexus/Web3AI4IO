#!/usr/bin/env python
"""Write artifacts/sample_flow.csv from data_manifest.json + design constants.

The sample flow is the registered filtering funnel: every number is taken
from data_manifest.json (itself recomputed from the canonical parquet
inputs by src/audit.py), never re-derived here.

Usage: python src/sample_flow.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    manifest = json.loads((EXP_DIR / "data_manifest.json").read_text())
    c = manifest["counts"]
    lock_note = "design_lock.yaml"

    rows = [
        ("launches_in_window",
         "launch rows 2025-08-18..2025-10-01, versions v4.0_mev_or_hook / v4.1_mev_or_hook, joined 1:1 to protocol_config on token_id",
         c["launches_total"], "data_manifest.json"),
        ("creators_total",
         "unique creators (protocol_config.creator)",
         c["creators_total"], "data_manifest.json"),
        ("adopters_any_v41",
         "creators with >= 1 v4.1 launch",
         c["adopters_any_v41"], "data_manifest.json"),
        ("adopters_ge1_pre_v40",
         "adopters with >= 1 v4.0 launch strictly before first v4.1 (timestamp level)",
         c["adopters_ge1_pre_v40"], "data_manifest.json"),
        ("adopters_ge3_pre_v40",
         "adopters with >= 3 pre v4.0 launches (registered pre-activity rule)",
         c["adopters_ge3_pre_v40"], "data_manifest.json"),
        ("singleton_cohort_excluded",
         "eligible adopters whose first v4.1 date is 2025-08-29 (excluded: singleton cohort)",
         c["adopters_ge3_singleton_2025_08_29"], "data_manifest.json"),
        ("treated_final",
         "treated creators across the 8 daily cohorts 2025-09-24..2025-10-01 "
         f"(sizes {c['cohort_sizes_2025_09_24_to_2025_10_01']})",
         c["adopters_ge3_in_cohort_window"], "data_manifest.json"),
        ("never_adopters_total",
         "creators with only v4.0 launches in the 45-day window",
         c["never_adopters_total"], "data_manifest.json"),
        ("never_adopters_pool",
         "never adopters with >= 3 launches in pre-period 2025-08-18..2025-09-23 (calibration / resampling pool)",
         c["never_adopters_ge3_pre_period"], "data_manifest.json"),
        ("sim_treated_per_rep",
         "simulated treated creators per replication (empirical cohort sizes)",
         sum(c["cohort_sizes_2025_09_24_to_2025_10_01"]), lock_note),
        ("sim_never_treated_per_rep",
         "simulated never-treated controls per replication (3x treated, CONTROL_RATIO in src/mc.py)",
         3 * sum(c["cohort_sizes_2025_09_24_to_2025_10_01"]), lock_note),
    ]

    out = EXP_DIR / "artifacts" / "sample_flow.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["step", "description", "n", "source"])
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} steps)")


if __name__ == "__main__":
    main()
