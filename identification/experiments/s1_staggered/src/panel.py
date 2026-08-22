"""Shared data access for the S1 experiment.

Loads the canonical launches x protocol_config panel (1:1 on token_id,
version from protocol_config) and derives the registered creator groups:
treated cohorts (first v4.1 launch date in 2025-09-24..2025-10-01, >=3
pre v4.0 launches at timestamp level, singleton 2025-08-29 excluded) and
eligible never adopters (>=3 launches in the shared pre-period).

Read-only with respect to shared data.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

EXP_DIR = Path(__file__).resolve().parents[1]
REPO = EXP_DIR.parents[3]
DATA = REPO / "Web3AI4IO"

LAUNCHES_PARQUET = DATA / "data/canonical/v1/base/launches/part-00000.parquet"
CONFIG_PARQUET = DATA / "data/canonical/v1/base/protocol_config/part-00000.parquet"

COHORT_DATES = pd.date_range("2025-09-24", "2025-10-01", freq="D")
SINGLETON_DATE = pd.Timestamp("2025-08-29")
PRE_PERIOD_START = pd.Timestamp("2025-08-18")
PRE_PERIOD_END = pd.Timestamp("2025-09-23")
WINDOW_DAYS = pd.date_range("2025-08-18", "2025-10-01", freq="D")
MIN_PRE_LAUNCHES = 3
COHORT_SIZES = [100, 140, 46, 47, 26, 34, 34, 25]
N_COHORTS = len(COHORT_SIZES)
PANEL_DAYS = 60
ADOPTION_DAYS = list(range(24, 32))  # relative days, matching real daily spacing


def load_panel() -> pd.DataFrame:
    launches = pd.read_parquet(LAUNCHES_PARQUET).drop(
        columns=["protocol_version"], errors="ignore"
    )
    config = pd.read_parquet(CONFIG_PARQUET)
    assert launches["token_id"].is_unique
    assert config["token_id"].is_unique
    df = launches.merge(
        config[["token_id", "creator", "protocol_version"]],
        on="token_id",
        how="inner",
        validate="1:1",
    )
    df["launch_at"] = pd.to_datetime(df["launch_at"], utc=True)
    df["date"] = df["launch_at"].dt.floor("D").dt.tz_localize(None)
    return df[df["protocol_version"].isin(["v4.0_mev_or_hook", "v4.1_mev_or_hook"])]


def first_v41(df: pd.DataFrame) -> pd.DataFrame:
    v41 = df[df["protocol_version"] == "v4.1_mev_or_hook"]
    g = v41.groupby("creator")
    return pd.DataFrame({"first_v41_ts": g["launch_at"].min(), "first_v41_date": g["date"].min()})


def pre_v40_counts(df: pd.DataFrame) -> pd.Series:
    """v4.0 launches strictly before (timestamp level) the creator's first v4.1."""
    fv = first_v41(df)
    v40 = df[df["protocol_version"] == "v4.0_mev_or_hook"]
    pre = v40.merge(fv[["first_v41_ts"]], left_on="creator", right_index=True)
    pre = pre[pre["launch_at"] < pre["first_v41_ts"]]
    return pre.groupby("creator").size()


def treated_funnel(df: pd.DataFrame) -> dict:
    fv = first_v41(df)
    pc = pre_v40_counts(df)
    ge3 = pc[pc >= MIN_PRE_LAUNCHES]
    elig = fv.loc[ge3.index, "first_v41_date"]
    in_window = elig[elig.isin(set(COHORT_DATES))]
    sizes = in_window.value_counts().reindex(COHORT_DATES, fill_value=0).sort_index()
    return {
        "adopters_any": int(len(fv)),
        "ge1": int((pc >= 1).sum()),
        "ge3": int(len(ge3)),
        "singleton": int((elig == SINGLETON_DATE).sum()),
        "cohort_sizes": [int(x) for x in sizes.values],
        "cohort_creator_dates": in_window,  # creator -> first v4.1 date
    }


def eligible_never_adopters(df: pd.DataFrame) -> np.ndarray:
    fv = first_v41(df)
    never_mask = ~df["creator"].isin(fv.index)
    pre = df[
        never_mask
        & (df["date"] >= PRE_PERIOD_START)
        & (df["date"] <= PRE_PERIOD_END)
    ]
    counts = pre.groupby("creator").size()
    return counts[counts >= MIN_PRE_LAUNCHES].index.to_numpy()


def never_adopter_strata(df: pd.DataFrame, never_ids: np.ndarray) -> pd.Series:
    """Pre-period launch-rate quintile (0..4) per eligible never adopter."""
    pre = df[
        df["creator"].isin(never_ids)
        & (df["date"] >= PRE_PERIOD_START)
        & (df["date"] <= PRE_PERIOD_END)
    ]
    rate = pre.groupby("creator").size() / ((PRE_PERIOD_END - PRE_PERIOD_START).days + 1)
    q = pd.qcut(rate.rank(method="first"), 5, labels=False)
    return q.astype(int)
