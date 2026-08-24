"""Audit of S1 real-data inputs -> data_manifest.json.

Recomputes all registered counts from the canonical parquet inputs:
launch/version totals, creator counts, adopter funnel (any v4.1,
>=1 pre v4.0 launch, >=3 pre v4.0 launches), cohort sizes for
2025-09-24..2025-10-01 plus the excluded 2025-08-29 singleton, and
never-adopter eligibility under the shared pre-period rule.

Read-only with respect to the shared data; writes only inside
identification/experiments/s1_staggered/.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

EXP_DIR = Path(__file__).resolve().parents[1]
REPO = EXP_DIR.parents[3]  # NatureSD/
DATA = REPO / "Web3AI4IO"

INPUTS = {
    "launches": DATA / "data/canonical/v1/base/launches/part-00000.parquet",
    "protocol_config": DATA / "data/canonical/v1/base/protocol_config/part-00000.parquet",
    "coverage_ledger": DATA / "data/canonical/v1/base/coverage_ledger/part-00000.parquet",
    "release_manifest": DATA / "dataset/releases/v1/base_core.json",
}

COHORT_DATES = pd.date_range("2025-09-24", "2025-10-01", freq="D")
SINGLETON_DATE = pd.Timestamp("2025-08-29")
# Shared pre-period used for never-adopter eligibility and launch-rate
# quintiles: from window start to the day before the first cohort date.
PRE_PERIOD_START = pd.Timestamp("2025-08-18")
PRE_PERIOD_END = pd.Timestamp("2025-09-23")  # inclusive
MIN_PRE_LAUNCHES = 3


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_panel() -> pd.DataFrame:
    launches = pd.read_parquet(INPUTS["launches"])
    config = pd.read_parquet(INPUTS["protocol_config"])
    assert launches["token_id"].is_unique, "token_id not unique in launches"
    assert config["token_id"].is_unique, "token_id not unique in protocol_config"
    # Spec: version must come from protocol_config.protocol_version; drop the
    # duplicate column carried by launches before merging.
    df = launches.drop(columns=["protocol_version"], errors="ignore").merge(
        config[["token_id", "creator", "protocol_version"]],
        on="token_id",
        how="inner",
        validate="1:1",
    )
    df["launch_at"] = pd.to_datetime(df["launch_at"], utc=True)
    df["date"] = df["launch_at"].dt.floor("D").dt.tz_localize(None)
    df = df[df["protocol_version"].isin(["v4.0_mev_or_hook", "v4.1_mev_or_hook"])]
    return df


def main() -> None:
    df = load_panel()
    creators = df["creator"]

    is_v41 = df["protocol_version"] == "v4.1_mev_or_hook"
    first_v41 = (
        df[is_v41].groupby("creator")["date"].min().rename("first_v41_date")
    )
    v40 = df[~is_v41]

    adopters = first_v41.index
    first_v41_ts = (
        df[is_v41].groupby("creator")["launch_at"].min().rename("first_v41_ts")
    )
    v40 = df[~is_v41]
    # Pre-activity rule at timestamp level: a v4.0 launch counts as "before
    # first v4.1" iff its launch_at is strictly earlier than the first v4.1
    # launch_at (same-day earlier launches count). This reproduces the
    # registered funnel 763 -> 453 and cohort sizes [100,140,46,47,26,34,34,25].
    pre = v40.merge(first_v41_ts, left_on="creator", right_index=True)
    pre = pre[pre["launch_at"] < pre["first_v41_ts"]]
    pre_counts = pre.groupby("creator").size()

    ge1 = pre_counts[pre_counts >= 1]
    ge3 = pre_counts[pre_counts >= MIN_PRE_LAUNCHES]

    elig = first_v41.loc[ge3.index]
    in_window = elig[elig.isin(set(COHORT_DATES))]
    cohort_sizes = (
        in_window.value_counts().reindex(COHORT_DATES, fill_value=0).sort_index()
    )
    singleton_count = int((elig == SINGLETON_DATE).sum())

    # Never adopters: no v4.1 launch in the observed window.
    never_mask = ~creators.isin(adopters)
    never_ids = creators[never_mask].unique()
    never_pre = df[
        never_mask
        & (df["date"] >= PRE_PERIOD_START)
        & (df["date"] <= PRE_PERIOD_END)
    ]
    never_pre_counts = never_pre.groupby("creator").size()
    never_eligible = never_pre_counts[never_pre_counts >= MIN_PRE_LAUNCHES]

    manifest = {
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "inputs": {
            name: {
                "path": str(p.relative_to(REPO)),
                "sha256": sha256(p),
                "bytes": p.stat().st_size,
            }
            for name, p in INPUTS.items()
        },
        "join": {
            "key": "token_id",
            "unique_in_launches": True,
            "unique_in_protocol_config": True,
            "merged_rows": int(len(df)),
        },
        "launch_window_utc": [
            str(df["date"].min().date()),
            str(df["date"].max().date()),
        ],
        "counts": {
            "launches_total": int(len(df)),
            "launches_v40": int((~is_v41).sum()),
            "launches_v41": int(is_v41.sum()),
            "creators_total": int(creators.nunique()),
            "adopters_any_v41": int(len(adopters)),
            "adopters_ge1_pre_v40": int(len(ge1)),
            "adopters_ge3_pre_v40": int(len(ge3)),
            "adopters_ge3_singleton_2025_08_29": singleton_count,
            "adopters_ge3_in_cohort_window": int(len(in_window)),
            "cohort_sizes_2025_09_24_to_2025_10_01": [
                int(x) for x in cohort_sizes.values
            ],
            "never_adopters_total": int(len(never_ids)),
            "never_adopters_ge3_pre_period": int(len(never_eligible)),
        },
        "rules": {
            "min_pre_launches": MIN_PRE_LAUNCHES,
            "pre_period": [str(PRE_PERIOD_START.date()), str(PRE_PERIOD_END.date())],
            "cohort_window": [
                str(COHORT_DATES[0].date()),
                str(COHORT_DATES[-1].date()),
            ],
            "excluded_singleton_date": str(SINGLETON_DATE.date()),
        },
    }

    out = EXP_DIR / "data_manifest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["counts"], indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
