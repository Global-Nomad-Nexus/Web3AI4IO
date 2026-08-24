from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "pump_moonshot_cohort_panel.csv"
ARTIFACTS = ROOT / "artifacts"


@dataclass
class Estimate:
    specification: str
    sample: str
    outcome: str
    scale: str
    estimate: float
    std_error: float
    ci_low: float
    ci_high: float
    p_value: float
    n_days: int


def ols_hac(y: np.ndarray, x: np.ndarray, coefficient: int, maxlags: int = 7) -> tuple:
    """OLS with a Bartlett Newey-West covariance and normal-reference inference."""
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    residual = y - x @ beta
    bread = np.linalg.pinv(x.T @ x)
    meat = np.zeros((x.shape[1], x.shape[1]))
    for lag in range(maxlags + 1):
        weight = 1.0 if lag == 0 else 1.0 - lag / (maxlags + 1.0)
        gamma = np.zeros_like(meat)
        for t in range(lag, len(y)):
            gamma += residual[t] * residual[t - lag] * np.outer(x[t], x[t - lag])
        meat += gamma if lag == 0 else weight * (gamma + gamma.T)
    covariance = bread @ meat @ bread
    se = float(np.sqrt(max(covariance[coefficient, coefficient], 0.0)))
    estimate = float(beta[coefficient])
    z_value = estimate / se if se > 0 else math.inf
    p_value = math.erfc(abs(z_value) / math.sqrt(2.0))
    return estimate, se, estimate - 1.96 * se, estimate + 1.96 * se, p_value, len(y)


def fit_post_effect(series: pd.Series, dates: pd.Series, post: pd.Series) -> tuple:
    frame = pd.DataFrame(
        {
            "y": series.astype(float),
            "post": post.astype(int),
            "weekday": pd.to_datetime(dates).dt.dayofweek,
        }
    ).dropna()
    weekday = pd.get_dummies(frame["weekday"], prefix="weekday", drop_first=True, dtype=float)
    x = pd.concat([frame[["post"]].astype(float), weekday], axis=1)
    x.insert(0, "constant", 1.0)
    return ols_hac(frame["y"].to_numpy(), x.to_numpy(), coefficient=1)


def fit_pretrend(series: pd.Series, dates: pd.Series) -> tuple:
    frame = pd.DataFrame({"y": series.astype(float), "date": pd.to_datetime(dates)}).dropna()
    frame["day"] = (frame["date"] - frame["date"].min()).dt.days.astype(float)
    x = np.column_stack([np.ones(len(frame)), frame["day"].to_numpy()])
    return ols_hac(frame["y"].to_numpy(), x, coefficient=1)


def comparison_frame(data: pd.DataFrame, period_column: str, outcome: str, scale: str) -> pd.DataFrame:
    use = data[data[period_column].isin(["pre", "post"])].copy()
    wide = use.pivot(index="cohort_date", columns="platform", values=outcome).reset_index()
    periods = use[["cohort_date", period_column]].drop_duplicates()
    wide = wide.merge(periods, on="cohort_date", validate="one_to_one")
    if scale == "log1p":
        wide["pump"] = np.log1p(wide["Pump.fun"])
        wide["control"] = np.log1p(wide["Moonshot"])
    elif scale == "level":
        wide["pump"] = wide["Pump.fun"]
        wide["control"] = wide["Moonshot"]
    else:
        raise ValueError(scale)
    wide["gap"] = wide["pump"] - wide["control"]
    wide["post"] = (wide[period_column] == "post").astype(int)
    return wide.sort_values("cohort_date")


def make_estimate(specification: str, sample: str, outcome: str, scale: str, fitted: tuple) -> Estimate:
    estimate, se, low, high, p_value, n_days = fitted
    return Estimate(specification, sample, outcome, scale, estimate, se, low, high, p_value, n_days)


def main() -> None:
    data = pd.read_csv(DATA)
    data["cohort_date"] = pd.to_datetime(data["cohort_date"]).dt.date
    estimates: list[Estimate] = []

    specs = [
        ("gross_period", "gross_21d", "launches", "log1p"),
        ("gross_period", "gross_21d", "unique_creators", "log1p"),
        ("quality_7d_period", "quality_7d_21d", "launches", "log1p"),
        ("quality_7d_period", "quality_7d_21d", "graduated_7d", "log1p"),
        ("quality_7d_period", "quality_7d_21d", "graduation_rate_7d", "level"),
        ("quality_30d_period", "quality_30d_21d", "launches", "log1p"),
        ("quality_30d_period", "quality_30d_21d", "graduated_30d", "log1p"),
        ("quality_30d_period", "quality_30d_21d", "graduation_rate_30d", "level"),
    ]

    frames: dict[tuple[str, str], pd.DataFrame] = {}
    for period, sample, outcome, scale in specs:
        frame = comparison_frame(data, period, outcome, scale)
        frames[(sample, outcome)] = frame
        fitted = fit_post_effect(frame["gap"], frame["cohort_date"], frame["post"])
        estimates.append(make_estimate("comparative_hac7", sample, outcome, scale, fitted))

        pre = frame[frame["post"] == 0]
        trend = fit_pretrend(pre["gap"], pre["cohort_date"])
        estimates.append(make_estimate("pretrend_hac7", sample, outcome, f"{scale}_per_day", trend))

        naive = fit_post_effect(frame["pump"], frame["cohort_date"], frame["post"])
        estimates.append(make_estimate("pump_before_after_hac7", sample, outcome, scale, naive))

    launch_frame = frames[("quality_7d_21d", "launches")]
    migrated_frame = frames[("quality_7d_21d", "graduated_7d")]
    joint = launch_frame[["cohort_date", "post", "gap"]].merge(
        migrated_frame[["cohort_date", "gap"]],
        on="cohort_date",
        suffixes=("_launch", "_migrated"),
        validate="one_to_one",
    )
    joint["quality_penalty"] = joint["gap_launch"] - joint["gap_migrated"]
    fitted = fit_post_effect(joint["quality_penalty"], joint["cohort_date"], joint["post"])
    estimates.append(
        make_estimate(
            "comparative_hac7",
            "quality_7d_21d",
            "launch_minus_migrated_7d",
            "log1p_difference",
            fitted,
        )
    )

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    output_csv = ARTIFACTS / "h0_estimates.csv"
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(asdict(estimates[0]).keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(asdict(item) for item in estimates)

    summary = {
        "event": "Pump.fun creator-fee activation",
        "activation_utc": "2025-05-13T11:27:06Z",
        "anticipation_start": "2025-05-08",
        "control_status": "candidate_not_accepted_due_to_concurrent_product_changes_and_interference",
        "estimand": "reduced_form_rule_bundle_effect",
        "primary_h0_rule": {
            "launch_effect_positive": False,
            "launch_effect_exceeds_7d_migration_effect": False,
            "identified": False,
        },
        "estimates": [asdict(item) for item in estimates],
    }

    primary_launch = next(
        item
        for item in estimates
        if item.specification == "comparative_hac7"
        and item.sample == "quality_7d_21d"
        and item.outcome == "launches"
    )
    penalty = next(item for item in estimates if item.outcome == "launch_minus_migrated_7d")
    summary["primary_h0_rule"]["launch_effect_positive"] = primary_launch.ci_low > 0
    summary["primary_h0_rule"]["launch_effect_exceeds_7d_migration_effect"] = penalty.ci_low > 0

    pump = data[data["platform"] == "Pump.fun"].copy()
    pump["cohort_date"] = pd.to_datetime(pump["cohort_date"])
    pump = pump.drop_duplicates("cohort_date").set_index("cohort_date").sort_index()
    pre_series = np.log1p(pump.loc["2025-04-17":"2025-05-07", "launches"].astype(float))
    placebo = []
    for split in pd.date_range("2025-04-24", "2025-05-01"):
        before = pre_series.loc[split - pd.Timedelta(days=7) : split - pd.Timedelta(days=1)]
        after = pre_series.loc[split : split + pd.Timedelta(days=6)]
        if len(before) == 7 and len(after) == 7:
            placebo.append({"pseudo_date": split.date().isoformat(), "estimate": float(after.mean() - before.mean())})
    actual_before = np.log1p(pump.loc["2025-05-01":"2025-05-07", "launches"].astype(float))
    actual_after = np.log1p(pump.loc["2025-05-14":"2025-05-20", "launches"].astype(float))
    actual_short = float(actual_after.mean() - actual_before.mean())
    extreme = sum(abs(item["estimate"]) >= abs(actual_short) for item in placebo)
    summary["in_time_placebo"] = {
        "window": "seven_launch_days_before_versus_after",
        "actual_estimate": actual_short,
        "pseudo_estimates": placebo,
        "two_sided_randomization_p": (1 + extreme) / (1 + len(placebo)),
        "interpretation": "descriptive_falsification_only",
    }

    (ARTIFACTS / "h0_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["primary_h0_rule"], indent=2))
    for item in estimates:
        if item.specification == "comparative_hac7":
            print(
                f"{item.sample:20s} {item.outcome:28s} "
                f"{item.estimate:+.4f} [{item.ci_low:+.4f}, {item.ci_high:+.4f}] "
                f"p={item.p_value:.4g}"
            )


if __name__ == "__main__":
    main()
