"""Calibration for the S1 semi-synthetic DGP -> calibration_summary.json.

Estimates the hurdle count model inputs from eligible never-adopter
creators only (>=3 launches in the shared pre-period 2025-08-18..2025-09-23):
  layer 1: creator activity probability + calendar-day activity multipliers
  layer 2: launch count given active + calendar-day count multipliers

Also computes the SD of the untreated log1p outcome over the never-adopter
creator-day panel and applies the registered scale gate: injected log
effects (0.10 / 0.20 / 0.35; homogeneous 0.20) must lie within
[0.25, 1.0] outcome SD, otherwise a scale blocker is reported.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from panel import (
    COHORT_DATES,
    PRE_PERIOD_END,
    PRE_PERIOD_START,
    WINDOW_DAYS,
    eligible_never_adopters,
    load_panel,
    treated_funnel,
)

EXP_DIR = Path(__file__).resolve().parents[1]

GATE_LOW_SD = 0.25
GATE_HIGH_SD = 1.0
REGISTERED_LOG_EFFECTS = {"homogeneous": 0.20, "hetero_0_2": 0.10, "hetero_3_6": 0.20, "hetero_7plus": 0.35}


def never_adopter_daily_counts(df: pd.DataFrame, never_ids: np.ndarray) -> pd.DataFrame:
    """Full 45-day creator-day count panel for the given never adopters."""
    sub = df[df["creator"].isin(never_ids)]
    counts = (
        sub.groupby(["creator", "date"]).size().rename("n").reset_index()
    )
    creators = pd.Index(never_ids, name="creator")
    grid = pd.MultiIndex.from_product([creators, WINDOW_DAYS], names=["creator", "date"])
    panel = counts.set_index(["creator", "date"]).reindex(grid, fill_value=0).reset_index()
    return panel


def main() -> None:
    df = load_panel()
    funnel = treated_funnel(df)
    never_ids = eligible_never_adopters(df)
    panel = never_adopter_daily_counts(df, never_ids)

    y = np.log1p(panel["n"].to_numpy(dtype=float))
    outcome_sd = float(y.std(ddof=1))

    active = panel["n"] > 0
    # Layer 1: activity probability per creator and per calendar day.
    p_act_creator = panel.groupby("creator")["n"].apply(lambda s: (s > 0).mean())
    p_act_day = panel.groupby("date")["n"].apply(lambda s: (s > 0).mean())
    act_mult_day = p_act_day / p_act_day.mean()
    # Layer 2: count given active, per creator and per calendar day.
    mu_creator = panel[active].groupby("creator")["n"].mean()
    mu_day = panel[active].groupby("date")["n"].mean()
    cnt_mult_day = mu_day / mu_day.mean()
    cnt_active = panel.loc[active, "n"].to_numpy(dtype=float)

    # Pre-period launch-rate quintiles of the never-adopter pool (strata).
    pre = df[
        df["creator"].isin(never_ids)
        & (df["date"] >= PRE_PERIOD_START)
        & (df["date"] <= PRE_PERIOD_END)
    ]
    pre_rate = pre.groupby("creator").size() / (
        (PRE_PERIOD_END - PRE_PERIOD_START).days + 1
    )
    quintile = pd.qcut(pre_rate.rank(method="first"), 5, labels=False)

    effects_in_sd = {k: v / outcome_sd for k, v in REGISTERED_LOG_EFFECTS.items()}
    gate_fail = {
        k: {"sd_units": s, "below_0.25": bool(s < GATE_LOW_SD), "above_1.0": bool(s > GATE_HIGH_SD)}
        for k, s in effects_in_sd.items()
    }
    blocked = any(v["below_0.25"] or v["above_1.0"] for v in gate_fail.values())

    summary = {
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "estimation_pool": {
            "never_adopters_eligible": int(len(never_ids)),
            "creator_days": int(len(panel)),
            "active_share": float(active.mean()),
        },
        "untreated_outcome": {
            "scale": "log1p(daily launch count)",
            "sd": outcome_sd,
            "mean": float(y.mean()),
        },
        "hurdle_layer1_activity": {
            "creator_p_active_quantiles": [
                float(q) for q in p_act_creator.quantile([0, 0.25, 0.5, 0.75, 1.0])
            ],
            "calendar_day_multiplier_range": [
                float(act_mult_day.min()),
                float(act_mult_day.max()),
            ],
        },
        "hurdle_layer2_count_given_active": {
            "mean": float(cnt_active.mean()),
            "sd": float(cnt_active.std(ddof=1)),
            "quantiles": [float(q) for q in pd.Series(cnt_active).quantile([0, 0.5, 0.9, 0.99, 1.0])],
            "calendar_day_multiplier_range": [
                float(cnt_mult_day.min()),
                float(cnt_mult_day.max()),
            ],
        },
        "strata": {
            "definition": "pre-period (2025-08-18..2025-09-23) launch-rate quintile",
            "pool_sizes": [int(x) for x in quintile.value_counts().sort_index().values],
        },
        "scale_gate": {
            "rule": "each registered injected log effect must be within [0.25, 1.0] untreated-outcome SD",
            "registered_log_effects": REGISTERED_LOG_EFFECTS,
            "effects_in_sd_units": effects_in_sd,
            "per_effect_check": gate_fail,
            "blocked": blocked,
        },
        "cohort_context": {
            "cohort_sizes": funnel["cohort_sizes"],
            "cohort_dates": [str(d.date()) for d in COHORT_DATES],
        },
    }
    out = EXP_DIR / "calibration_summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["untreated_outcome"], indent=2))
    print(json.dumps(summary["scale_gate"], indent=2))
    if blocked:
        print("SCALE BLOCKER: injected effects outside [0.25, 1.0] outcome SD")
        sys.exit(2)


if __name__ == "__main__":
    main()
