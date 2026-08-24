"""Identification stress tests for the Pump.fun -> PumpSwap application arm."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .io import CaseConfig, write_csv, write_json
from .stats import coefficient_row, estimate_ols


ACTUAL_EVENT_DATE = pd.Timestamp("2025-03-20", tz="UTC")
TREATED_UNIT = "pump_ecosystem"


def _read_nonempty_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _prepare_panel_for_event(
    panel: pd.DataFrame,
    *,
    event_date: pd.Timestamp,
    window_days: int | None = None,
    treated_unit: str = TREATED_UNIT,
    included_units: list[str] | None = None,
) -> pd.DataFrame:
    data = panel.copy()
    data["date"] = pd.to_datetime(data["date"], utc=True)
    if included_units is not None:
        data = data.loc[data["unit"].astype(str).isin(included_units)].copy()
    data["treated"] = data["unit"].astype(str).eq(treated_unit).astype(int)
    data["rel_day"] = (data["date"] - event_date).dt.days
    if window_days is not None:
        data = data.loc[data["rel_day"].between(-window_days, window_days)].copy()
    data["post"] = data["rel_day"].ge(0).astype(int)
    data["did"] = data["treated"] * data["post"]
    data["date_str"] = data["date"].dt.strftime("%Y-%m-%d")
    data["log_volume"] = np.log1p(pd.to_numeric(data["daily_volume_usd"], errors="coerce"))
    return data


def _twfe_row(
    panel: pd.DataFrame,
    *,
    event_date: pd.Timestamp,
    window_days: int | None,
    treated_unit: str = TREATED_UNIT,
    included_units: list[str] | None = None,
) -> dict[str, object]:
    data = _prepare_panel_for_event(
        panel,
        event_date=event_date,
        window_days=window_days,
        treated_unit=treated_unit,
        included_units=included_units,
    )
    required_cells = data.groupby(["treated", "post"]).size()
    if data.empty or required_cells.reindex(pd.MultiIndex.from_product([[0, 1], [0, 1]])).isna().any():
        return {
            "estimate": np.nan,
            "std_error": np.nan,
            "ci95_low": np.nan,
            "ci95_high": np.nan,
            "p_value": np.nan,
            "worked_decision": "not_estimable",
            "n_rows": int(len(data)),
            "n_units": int(data["unit"].nunique()) if "unit" in data else 0,
            "n_dates": int(data["date_str"].nunique()) if "date_str" in data else 0,
        }
    fit = estimate_ols(data, "log_volume", ["did"], ["unit", "date_str"])
    row = coefficient_row(
        "robustness",
        "TWFE robustness specification",
        "log(1 + daily volume USD)",
        fit,
        "did",
        method="OLS log_volume ~ did | unit + date FE, HC1",
    )
    return {
        "estimate": row["estimate"],
        "std_error": row["std_error"],
        "ci95_low": row["ci95_low"],
        "ci95_high": row["ci95_high"],
        "p_value": row["p_value"],
        "worked_decision": row["worked_decision"],
        "n_rows": int(len(data)),
        "n_units": int(data["unit"].nunique()),
        "n_dates": int(data["date_str"].nunique()),
    }


def build_event_date_sensitivity(panel: pd.DataFrame, config: CaseConfig) -> pd.DataFrame:
    offsets = list(range(-7, 8))
    window_days = int(config.raw.get("robustness", {}).get("event_date_window_days", 60))
    rows: list[dict[str, object]] = []
    for offset in offsets:
        event_date = ACTUAL_EVENT_DATE + pd.Timedelta(days=offset)
        stats = _twfe_row(panel, event_date=event_date, window_days=window_days)
        rows.append(
            {
                "event_date": event_date.strftime("%Y-%m-%d"),
                "offset_days_from_baseline": offset,
                "window_days": window_days,
                **stats,
                "stress_test": "event_date_sensitivity",
                "interpretation": (
                    "Positive under this event-date choice, but still evaluated only as market-level diagnostic evidence."
                    if pd.notna(stats["estimate"]) and float(stats["estimate"]) > 0
                    else "Non-positive or not estimable under this event-date choice; do not overclaim timing precision."
                ),
            }
        )
    out = pd.DataFrame(rows)
    write_csv(config.tables_dir / "event_date_sensitivity.csv", out)
    return out


def build_twfe_window_sensitivity(panel: pd.DataFrame, config: CaseConfig) -> pd.DataFrame:
    windows = config.raw.get("robustness", {}).get("twfe_windows_days", [30, 45, 60, 75, 90])
    rows: list[dict[str, object]] = []
    for window in windows:
        stats = _twfe_row(panel, event_date=ACTUAL_EVENT_DATE, window_days=int(window))
        rows.append(
            {
                "event_date": ACTUAL_EVENT_DATE.strftime("%Y-%m-%d"),
                "window_days": int(window),
                **stats,
                "stress_test": "twfe_window_sensitivity",
                "interpretation": (
                    "Window choice preserves a positive estimate."
                    if pd.notna(stats["estimate"]) and float(stats["estimate"]) > 0
                    else "Window choice weakens or reverses the aggregate-volume estimate."
                ),
            }
        )
    out = pd.DataFrame(rows)
    write_csv(config.tables_dir / "twfe_window_sensitivity.csv", out)
    return out


def build_control_set_sensitivity(panel: pd.DataFrame, config: CaseConfig) -> pd.DataFrame:
    units = sorted(panel["unit"].astype(str).unique())
    controls = [unit for unit in units if unit != TREATED_UNIT]
    rows: list[dict[str, object]] = []
    for dropped in [None, *controls]:
        included_controls = [unit for unit in controls if unit != dropped]
        if not included_controls:
            continue
        included_units = [TREATED_UNIT, *included_controls]
        stats = _twfe_row(
            panel,
            event_date=ACTUAL_EVENT_DATE,
            window_days=90,
            included_units=included_units,
        )
        rows.append(
            {
                "control_rule": "all_controls" if dropped is None else f"drop_{dropped}",
                "included_controls": ";".join(included_controls),
                "dropped_control": "" if dropped is None else dropped,
                "window_days": 90,
                **stats,
                "stress_test": "leave_one_control_out",
                "interpretation": (
                    "Estimate remains positive after this control-set perturbation."
                    if pd.notna(stats["estimate"]) and float(stats["estimate"]) > 0
                    else "Estimate is sensitive to this control-set perturbation."
                ),
            }
        )
    for control in controls:
        included_units = [TREATED_UNIT, control]
        stats = _twfe_row(
            panel,
            event_date=ACTUAL_EVENT_DATE,
            window_days=90,
            included_units=included_units,
        )
        rows.append(
            {
                "control_rule": f"single_control_{control}",
                "included_controls": control,
                "dropped_control": ";".join([unit for unit in controls if unit != control]),
                "window_days": 90,
                **stats,
                "stress_test": "single_control_only",
                "interpretation": (
                    "Single-control specification remains positive."
                    if pd.notna(stats["estimate"]) and float(stats["estimate"]) > 0
                    else "Single-control specification weakens or reverses the estimate."
                ),
            }
        )
    out = pd.DataFrame(rows)
    write_csv(config.tables_dir / "control_set_sensitivity.csv", out)
    return out


def build_placebo_event_diagnostics(panel: pd.DataFrame, config: CaseConfig) -> pd.DataFrame:
    robustness = config.raw.get("robustness", {})
    offsets = robustness.get("placebo_offsets_days", [-70, -56, -42, -28])
    window_days = int(robustness.get("placebo_window_days", 14))
    rows: list[dict[str, object]] = []
    for offset in offsets:
        event_date = ACTUAL_EVENT_DATE + pd.Timedelta(days=int(offset))
        stats = _twfe_row(panel, event_date=event_date, window_days=window_days)
        placebo_positive = bool(pd.notna(stats["ci95_low"]) and float(stats["ci95_low"]) > 0)
        rows.append(
            {
                "placebo_event_date": event_date.strftime("%Y-%m-%d"),
                "offset_days_from_true_event": int(offset),
                "window_days": window_days,
                **stats,
                "placebo_positive_significant": int(placebo_positive),
                "stress_test": "pre_event_placebo",
                "interpretation": (
                    "Placebo produces a positive significant estimate; this is a warning about latent pre-event dynamics."
                    if placebo_positive
                    else "No positive significant placebo effect under this pre-event pseudo-date."
                ),
            }
        )
    out = pd.DataFrame(rows)
    write_csv(config.tables_dir / "placebo_event_diagnostics.csv", out)
    return out


def build_unit_permutation_test(panel: pd.DataFrame, config: CaseConfig) -> tuple[pd.DataFrame, dict[str, object]]:
    units = sorted(panel["unit"].astype(str).unique())
    rows: list[dict[str, object]] = []
    for unit in units:
        stats = _twfe_row(
            panel,
            event_date=ACTUAL_EVENT_DATE,
            window_days=90,
            treated_unit=unit,
            included_units=units,
        )
        rows.append(
            {
                "pseudo_treated_unit": unit,
                "is_actual_treated": int(unit == TREATED_UNIT),
                "event_date": ACTUAL_EVENT_DATE.strftime("%Y-%m-%d"),
                "window_days": 90,
                **stats,
            }
        )
    out = pd.DataFrame(rows)
    actual = out.loc[out["is_actual_treated"].eq(1)]
    actual_estimate = float(actual.iloc[0]["estimate"]) if len(actual) else np.nan
    estimates = pd.to_numeric(out["estimate"], errors="coerce").dropna()
    if pd.isna(actual_estimate) or estimates.empty:
        p_two_sided = np.nan
        rank_abs = np.nan
    else:
        p_two_sided = float((estimates.abs() >= abs(actual_estimate)).mean())
        rank_abs = int((estimates.abs().rank(ascending=False, method="min").loc[actual.index[0]]))
    summary = {
        "event_date": ACTUAL_EVENT_DATE.strftime("%Y-%m-%d"),
        "treated_unit": TREATED_UNIT,
        "unit_count": int(len(units)),
        "actual_estimate": actual_estimate,
        "two_sided_unit_permutation_p_value": p_two_sided,
        "actual_abs_rank_among_units": rank_abs,
        "interpretation": (
            "Small-unit permutation is a stress test, not a formal large-sample test. A high p-value supports the paper's "
            "decision to treat market-level DiD as diagnostic rather than definitive causal evidence."
        ),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    write_csv(config.tables_dir / "unit_permutation_test.csv", out)
    write_json(config.tables_dir / "unit_permutation_summary.json", summary)
    return out, summary


def _synthetic_weights(pre: pd.DataFrame, treated_unit: str, control_units: list[str]) -> np.ndarray:
    x = pre[control_units].to_numpy(dtype=float)
    y = pre[treated_unit].to_numpy(dtype=float)
    n_controls = len(control_units)
    if n_controls == 0:
        return np.asarray([], dtype=float)

    def objective(weights: np.ndarray) -> float:
        gap = y - x @ weights
        gap = gap - gap.mean()
        return float(np.mean(gap**2))

    result = minimize(
        objective,
        np.ones(n_controls, dtype=float) / n_controls,
        bounds=[(0.0, 1.0)] * n_controls,
        constraints={"type": "eq", "fun": lambda weights: float(weights.sum() - 1.0)},
        method="SLSQP",
    )
    if not result.success:
        return np.ones(n_controls, dtype=float) / n_controls
    return np.asarray(result.x, dtype=float)


def build_synthetic_control_diagnostics(panel: pd.DataFrame, config: CaseConfig) -> tuple[pd.DataFrame, dict[str, object]]:
    data = panel.copy()
    data["date"] = pd.to_datetime(data["date"], utc=True)
    data["log_volume"] = np.log1p(pd.to_numeric(data["daily_volume_usd"], errors="coerce"))
    pivot = data.pivot_table(index="date", columns="unit", values="log_volume", aggfunc="mean").dropna()
    pre = pivot.loc[pivot.index < ACTUAL_EVENT_DATE]
    post = pivot.loc[pivot.index >= ACTUAL_EVENT_DATE]
    units = sorted(str(unit) for unit in pivot.columns)
    rows: list[dict[str, object]] = []
    for treated_unit in units:
        control_units = [unit for unit in units if unit != treated_unit]
        weights = _synthetic_weights(pre, treated_unit, control_units)
        pre_gap = pre[treated_unit].to_numpy(dtype=float) - pre[control_units].to_numpy(dtype=float) @ weights
        post_gap = post[treated_unit].to_numpy(dtype=float) - post[control_units].to_numpy(dtype=float) @ weights
        pre_gap_mean = float(np.mean(pre_gap)) if len(pre_gap) else np.nan
        post_gap_mean = float(np.mean(post_gap)) if len(post_gap) else np.nan
        gap_change = post_gap_mean - pre_gap_mean if pd.notna(pre_gap_mean) and pd.notna(post_gap_mean) else np.nan
        centered_rmse = float(np.sqrt(np.mean((pre_gap - pre_gap_mean) ** 2))) if len(pre_gap) else np.nan
        row = {
            "treated_unit": treated_unit,
            "is_actual_treated": int(treated_unit == TREATED_UNIT),
            "event_date": ACTUAL_EVENT_DATE.strftime("%Y-%m-%d"),
            "pre_days": int(len(pre)),
            "post_days": int(len(post)),
            "pre_centered_rmse": centered_rmse,
            "pre_gap_mean": pre_gap_mean,
            "post_gap_mean": post_gap_mean,
            "gap_change": gap_change,
            "synthetic_control_units": ";".join(control_units),
            "interpretation": (
                "Synthetic-control-style gap change is positive for Pump, but placebo units determine whether this is distinctive."
                if treated_unit == TREATED_UNIT
                else "Placebo synthetic-control unit for small-N diagnostic comparison."
            ),
        }
        for control_unit, weight in zip(control_units, weights):
            row[f"weight_{control_unit}"] = float(weight)
        rows.append(row)
    out = pd.DataFrame(rows)
    actual = out.loc[out["is_actual_treated"].eq(1)]
    actual_gap_change = float(actual.iloc[0]["gap_change"]) if len(actual) else np.nan
    gaps = pd.to_numeric(out["gap_change"], errors="coerce").dropna()
    if pd.isna(actual_gap_change) or gaps.empty:
        p_two_sided = np.nan
        rank_abs = np.nan
    else:
        p_two_sided = float((gaps.abs() >= abs(actual_gap_change)).mean())
        rank_abs = int(gaps.abs().rank(ascending=False, method="min").loc[actual.index[0]])
    summary = {
        "event_date": ACTUAL_EVENT_DATE.strftime("%Y-%m-%d"),
        "treated_unit": TREATED_UNIT,
        "unit_count": int(len(units)),
        "actual_gap_change": actual_gap_change,
        "actual_pre_centered_rmse": float(actual.iloc[0]["pre_centered_rmse"]) if len(actual) else np.nan,
        "two_sided_placebo_p_value": p_two_sided,
        "actual_abs_rank_among_units": rank_abs,
        "claim_boundary": (
            "This is a synthetic-control-style diagnostic with only three donor units. It strengthens the robustness ledger, "
            "but it is not a stand-alone causal proof."
        ),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    write_csv(config.tables_dir / "synthetic_control_diagnostics.csv", out)
    write_json(config.tables_dir / "synthetic_control_summary.json", summary)
    return out, summary


def build_moralis_sample_selection_audit(config: CaseConfig) -> pd.DataFrame:
    token_outcomes_path = config.output_root / "external_validation" / "h1_rpc_token_level_outcomes.csv"
    moralis_path = config.output_root / "external_validation" / "moralis_decoded_token_outcomes.csv"
    token_outcomes = _read_nonempty_csv(token_outcomes_path)
    moralis = _read_nonempty_csv(moralis_path)
    if token_outcomes.empty or moralis.empty or "mint" not in token_outcomes or "mint" not in moralis:
        audit = pd.DataFrame(
            [
                {
                    "metric": "sample_available",
                    "covered_n": 0,
                    "uncovered_n": 0,
                    "covered_value": np.nan,
                    "uncovered_value": np.nan,
                    "difference": np.nan,
                    "standardized_mean_difference": np.nan,
                    "interpretation": "Moralis sample-selection audit could not run because token outcomes or decoded sample are missing.",
                }
            ]
        )
        write_csv(config.tables_dir / "moralis_sample_selection_audit.csv", audit)
        return audit

    covered_mints = set(moralis["mint"].astype(str).unique())
    data = token_outcomes.copy()
    data["moralis_covered"] = data["mint"].astype(str).isin(covered_mints).astype(int)
    metrics = [
        ("complete_30d", "mean", "Share with complete 30d RPC window"),
        ("active_30d", "mean", "Share with observed 30d RPC pool activity"),
        ("swap_count_30d", "median", "Median 30d RPC transaction-count proxy"),
        ("log1p_swap_count_30d", "mean", "Mean log1p 30d RPC transaction-count proxy"),
        ("first_trade_lag_seconds_30d", "median", "Median seconds from graduation to first observed pool transaction"),
        ("ath_market_cap", "median", "Median Pump.fun ATH market cap in metadata"),
    ]
    rows: list[dict[str, object]] = []
    covered = data.loc[data["moralis_covered"].eq(1)]
    uncovered = data.loc[data["moralis_covered"].eq(0)]
    for col, reducer, label in metrics:
        if col not in data:
            continue
        covered_values = pd.to_numeric(covered[col], errors="coerce").dropna()
        uncovered_values = pd.to_numeric(uncovered[col], errors="coerce").dropna()
        if reducer == "median":
            covered_value = float(covered_values.median()) if len(covered_values) else np.nan
            uncovered_value = float(uncovered_values.median()) if len(uncovered_values) else np.nan
        else:
            covered_value = float(covered_values.mean()) if len(covered_values) else np.nan
            uncovered_value = float(uncovered_values.mean()) if len(uncovered_values) else np.nan
        pooled_std = float(pd.concat([covered_values, uncovered_values]).std(ddof=1)) if len(data) else np.nan
        diff = covered_value - uncovered_value if pd.notna(covered_value) and pd.notna(uncovered_value) else np.nan
        smd = diff / pooled_std if pooled_std and not pd.isna(diff) else np.nan
        rows.append(
            {
                "metric": col,
                "metric_label": label,
                "reducer": reducer,
                "covered_n": int(len(covered_values)),
                "uncovered_n": int(len(uncovered_values)),
                "covered_value": covered_value,
                "uncovered_value": uncovered_value,
                "difference": diff,
                "standardized_mean_difference": smd,
                "interpretation": (
                    "Moralis decoded sample differs materially from the rest of the RPC cohort; report it as a covered-token sample."
                    if pd.notna(smd) and abs(float(smd)) >= 0.25
                    else "Moralis decoded sample is not materially different on this RPC/metadata diagnostic."
                ),
            }
        )
    audit = pd.DataFrame(rows)
    write_csv(config.tables_dir / "moralis_sample_selection_audit.csv", audit)
    return audit


def build_identification_strength_summary(config: CaseConfig) -> dict[str, object]:
    event = _read_nonempty_csv(config.tables_dir / "event_date_sensitivity.csv")
    windows = _read_nonempty_csv(config.tables_dir / "twfe_window_sensitivity.csv")
    controls = _read_nonempty_csv(config.tables_dir / "control_set_sensitivity.csv")
    placebo = _read_nonempty_csv(config.tables_dir / "placebo_event_diagnostics.csv")
    selection = _read_nonempty_csv(config.tables_dir / "moralis_sample_selection_audit.csv")
    permutation_path = config.tables_dir / "unit_permutation_summary.json"
    permutation = json.loads(permutation_path.read_text(encoding="utf-8")) if permutation_path.exists() else {}
    synthetic_path = config.tables_dir / "synthetic_control_summary.json"
    synthetic = json.loads(synthetic_path.read_text(encoding="utf-8")) if synthetic_path.exists() else {}

    def positive_share(df: pd.DataFrame) -> float:
        if df.empty or "estimate" not in df:
            return np.nan
        vals = pd.to_numeric(df["estimate"], errors="coerce").dropna()
        return float(vals.gt(0).mean()) if len(vals) else np.nan

    def yes_share(df: pd.DataFrame) -> float:
        if df.empty or "worked_decision" not in df:
            return np.nan
        decisions = df["worked_decision"].astype(str)
        return float(decisions.eq("yes").mean()) if len(decisions) else np.nan

    max_selection_smd = (
        float(pd.to_numeric(selection["standardized_mean_difference"], errors="coerce").abs().max())
        if not selection.empty and "standardized_mean_difference" in selection
        else np.nan
    )
    placebo_positive_count = (
        int(pd.to_numeric(placebo.get("placebo_positive_significant"), errors="coerce").fillna(0).sum())
        if not placebo.empty
        else 0
    )
    control_leave_one_out = controls.loc[controls.get("stress_test", pd.Series(dtype=str)).astype(str).eq("leave_one_control_out")]
    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "event_date_sensitivity_rows": int(len(event)),
        "event_date_positive_share": positive_share(event),
        "event_date_yes_share": yes_share(event),
        "twfe_window_rows": int(len(windows)),
        "twfe_window_positive_share": positive_share(windows),
        "twfe_window_yes_share": yes_share(windows),
        "control_set_rows": int(len(controls)),
        "leave_one_control_positive_share": positive_share(control_leave_one_out),
        "placebo_rows": int(len(placebo)),
        "placebo_positive_significant_count": placebo_positive_count,
        "unit_permutation_p_value": permutation.get("two_sided_unit_permutation_p_value", np.nan),
        "unit_permutation_abs_rank": permutation.get("actual_abs_rank_among_units", np.nan),
        "synthetic_control_gap_change": synthetic.get("actual_gap_change", np.nan),
        "synthetic_control_pre_centered_rmse": synthetic.get("actual_pre_centered_rmse", np.nan),
        "synthetic_control_placebo_p_value": synthetic.get("two_sided_placebo_p_value", np.nan),
        "synthetic_control_abs_rank": synthetic.get("actual_abs_rank_among_units", np.nan),
        "moralis_sample_max_abs_smd": max_selection_smd,
        "market_identification_grade": (
            "diagnostic_only"
            if placebo_positive_count > 0 or float(permutation.get("two_sided_unit_permutation_p_value", 1.0) or 1.0) > 0.25
            else "moderate_support"
        ),
        "submission_claim_recommendation": (
            "Use the market DiD only as the benchmark's conclusion-flip diagnostic. Anchor H1 on mechanism-level RPC "
            "coverage and covered-token Moralis decoded outcomes; state that welfare and H4 same-cohort causal effects remain gaps."
        ),
    }
    write_json(config.tables_dir / "identification_strength_summary.json", summary)
    return summary


def build_market_identification_artifacts(panel: pd.DataFrame, config: CaseConfig) -> dict[str, object]:
    build_event_date_sensitivity(panel, config)
    build_twfe_window_sensitivity(panel, config)
    build_control_set_sensitivity(panel, config)
    build_placebo_event_diagnostics(panel, config)
    build_unit_permutation_test(panel, config)
    build_synthetic_control_diagnostics(panel, config)
    return build_identification_strength_summary(config)
