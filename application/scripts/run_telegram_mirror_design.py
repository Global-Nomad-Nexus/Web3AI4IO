#!/usr/bin/env python3
"""Run a preregistered matched-design audit for the Telegram mirror case.

This script treats launch-time Telegram metadata as the high-attention cohort
and compares it with non-Telegram tokens in the same launch-day and coarse
metadata cells.  The output is intentionally claim-bounded: the design is a
credible matched association with timing and sensitivity checks, not a causal
effect unless an exogenous attention shock is added later.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from build_benchmark_release import ROOT, relpath, source_path, load_config


TABLES = ROOT / "artifacts" / "tables"
EXTERNAL = ROOT / "artifacts" / "external_validation"
DESIGN_ID = "TELEGRAM_MIRROR_MATCHED_DESIGN_V1"
EVENT_ID = "PUMP_PUMPSWAP_MIGRATION_20250320"

SOCIAL_COLUMNS = [
    "mint",
    "created_at",
    "terminal_outcome_at",
    "launch_day",
    "initial_market_cap_sol",
    "log_initial_market_cap_sol",
    "has_twitter",
    "has_website",
    "has_telegram",
    "social_count",
    "has_any_social",
    "description_length",
    "outcome",
    "graduated",
    "minutes_to_outcome_seen",
    "minutes_to_outcome_chain",
    "final_market_cap_sol",
    "detection_lag_min",
]

CELL_COLUMNS = ["launch_day", "has_twitter", "has_website", "market_cap_decile", "description_bin"]
BALANCE_COLUMNS = [
    "log_initial_market_cap_sol",
    "initial_market_cap_sol",
    "has_twitter",
    "has_website",
    "other_social_count",
    "log_description_length",
    "description_length",
]


def read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.where(pd.notna(df), "").to_csv(path, index=False)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def clean_binary(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).clip(0, 1).astype(int)


def add_design_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in ["has_twitter", "has_website", "has_telegram", "has_any_social", "graduated"]:
        out[column] = clean_binary(out[column])
    for column in ["initial_market_cap_sol", "log_initial_market_cap_sol", "description_length", "social_count"]:
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0)
    out["other_social_count"] = (out["has_twitter"] + out["has_website"]).clip(0, 2)
    out["log_description_length"] = np.log1p(out["description_length"])
    out["market_cap_decile"] = pd.qcut(
        out["log_initial_market_cap_sol"].rank(method="first"),
        q=10,
        labels=False,
        duplicates="drop",
    ).astype(int)
    out["description_bin"] = pd.cut(
        out["description_length"],
        bins=[-1, 0, 20, 80, 200, np.inf],
        labels=["zero", "short", "medium", "long", "very_long"],
    ).astype(str)
    created = pd.to_datetime(out["created_at"], utc=True, errors="coerce")
    terminal = pd.to_datetime(out["terminal_outcome_at"], utc=True, errors="coerce")
    out["metadata_pre_outcome"] = created.le(terminal).fillna(False).astype(int)
    minutes = pd.to_numeric(out["minutes_to_outcome_seen"], errors="coerce")
    out["graduated_within_5m"] = (out["graduated"].eq(1) & minutes.le(5)).astype(int)
    out["graduated_within_15m"] = (out["graduated"].eq(1) & minutes.le(15)).astype(int)
    out["graduated_within_60m"] = (out["graduated"].eq(1) & minutes.le(60)).astype(int)
    out["graduated_after_60m"] = (out["graduated"].eq(1) & minutes.gt(60)).astype(int)
    out["timeout"] = out["outcome"].astype(str).eq("TIMEOUT").astype(int)
    out["detection_lag_min"] = pd.to_numeric(out["detection_lag_min"], errors="coerce")
    return out


def cluster_bootstrap_ci(
    supported: pd.DataFrame,
    *,
    reps: int,
    seed: int,
    outcome_column: str = "graduated",
    control_column: str = "control_graduation_mean",
) -> tuple[float, float, float]:
    if supported.empty:
        return float("nan"), float("nan"), float("nan")
    by_day = (
        supported.assign(diff=supported[outcome_column] - supported[control_column])
        .groupby("launch_day", dropna=False)
        .agg(diff_sum=("diff", "sum"), n=("diff", "size"))
    )
    if len(by_day) <= 1:
        att = float(by_day["diff_sum"].sum() / by_day["n"].sum())
        return att, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    days = by_day.index.to_numpy()
    draws = []
    for _ in range(reps):
        sampled = rng.choice(days, size=len(days), replace=True)
        sample = by_day.loc[sampled]
        draws.append(float(sample["diff_sum"].sum() / sample["n"].sum()))
    return float(np.std(draws, ddof=1)), float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def e_value_from_rr(rr: float) -> float:
    if not np.isfinite(rr) or rr <= 1:
        return float("nan")
    return float(rr + np.sqrt(rr * (rr - 1)))


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce")
    weight = pd.to_numeric(weights, errors="coerce")
    mask = numeric.notna() & weight.notna() & weight.gt(0)
    if not mask.any():
        return float("nan")
    return float(np.average(numeric.loc[mask], weights=weight.loc[mask]))


def weighted_var(values: pd.Series, weights: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce")
    weight = pd.to_numeric(weights, errors="coerce")
    mask = numeric.notna() & weight.notna() & weight.gt(0)
    if mask.sum() <= 1:
        return float("nan")
    mean = np.average(numeric.loc[mask], weights=weight.loc[mask])
    return float(np.average((numeric.loc[mask] - mean) ** 2, weights=weight.loc[mask]))


def balance_rows(
    *,
    full_treated: pd.DataFrame,
    full_control: pd.DataFrame,
    matched_treated: pd.DataFrame,
    matched_control: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for variable in BALANCE_COLUMNS:
        for sample, treated, control, control_weight in [
            ("full", full_treated, full_control, pd.Series(1, index=full_control.index)),
            ("matched", matched_treated, matched_control, matched_control["match_weight"]),
        ]:
            treated_weight = pd.Series(1, index=treated.index)
            treated_mean = weighted_mean(treated[variable], treated_weight)
            control_mean = weighted_mean(control[variable], control_weight)
            treated_var = weighted_var(treated[variable], treated_weight)
            control_var = weighted_var(control[variable], control_weight)
            pooled = np.sqrt((treated_var + control_var) / 2) if np.isfinite(treated_var + control_var) else np.nan
            smd = (treated_mean - control_mean) / pooled if pooled and np.isfinite(pooled) else np.nan
            rows.append(
                {
                    "design_id": DESIGN_ID,
                    "sample": sample,
                    "variable": variable,
                    "treated_mean": treated_mean,
                    "control_mean": control_mean,
                    "standardized_mean_difference": smd,
                    "treated_n": int(len(treated)),
                    "control_n": int(len(control)),
                    "claim_boundary": "Balance diagnostic only; residual unobserved quality confounding can remain.",
                }
            )
    return pd.DataFrame(rows)


def matched_outcome_row(
    df: pd.DataFrame,
    *,
    outcome_column: str,
    stage: str,
    estimand: str,
    decision: str,
    claim_boundary: str,
    bootstrap_reps: int,
    seed: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    treated = df.loc[df["has_telegram"].eq(1)].copy()
    controls = df.loc[df["has_telegram"].eq(0)].copy()
    treated[outcome_column] = pd.to_numeric(treated[outcome_column], errors="coerce")
    controls[outcome_column] = pd.to_numeric(controls[outcome_column], errors="coerce")
    control_mean_col = f"control_{outcome_column}_mean"
    control_cells = (
        controls.dropna(subset=[outcome_column])
        .groupby(CELL_COLUMNS, dropna=False)
        .agg(
            control_n=("mint", "count"),
            **{control_mean_col: (outcome_column, "mean")},
        )
        .reset_index()
    )
    supported = treated.dropna(subset=[outcome_column]).merge(control_cells, on=CELL_COLUMNS, how="left")
    supported = supported.loc[pd.to_numeric(supported["control_n"], errors="coerce").fillna(0).gt(0)].copy()
    treated_value = float(supported[outcome_column].mean()) if not supported.empty else float("nan")
    control_value = float(supported[control_mean_col].mean()) if not supported.empty else float("nan")
    effect = treated_value - control_value if np.isfinite(treated_value - control_value) else float("nan")
    se, ci_low, ci_high = cluster_bootstrap_ci(
        supported,
        reps=bootstrap_reps,
        seed=seed,
        outcome_column=outcome_column,
        control_column=control_mean_col,
    )
    row = {
        "design_id": DESIGN_ID,
        "stage": stage,
        "estimand": estimand,
        "outcome": outcome_column,
        "horizon_days": "",
        "n_treated": int(len(supported)),
        "n_control": int(control_cells["control_n"].sum()) if not control_cells.empty else 0,
        "treated_value": treated_value,
        "control_value": control_value,
        "effect": effect,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "sensitivity_value": se,
        "decision": decision,
        "claim_boundary": claim_boundary,
        "source_artifact": "RED-PUMP created_at, terminal_outcome_at, and launch metadata",
    }
    return row, supported


def event_time_and_negative_control_rows(
    df: pd.DataFrame,
    *,
    bootstrap_reps: int,
    seed: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    specs = [
        (
            "graduated_within_5m",
            "D6a_immediate_5m_placebo_like_check",
            "Matched ATT for graduation within 5 minutes of launch",
            "immediate_outcome_confounding_risk_check",
            "A large immediate effect is too fast for a clean Telegram attention mechanism and flags residual project-quality confounding.",
        ),
        (
            "graduated_within_15m",
            "D6b_immediate_15m_placebo_like_check",
            "Matched ATT for graduation within 15 minutes of launch",
            "immediate_outcome_confounding_risk_check",
            "A large immediate effect is too fast for a clean Telegram attention mechanism and flags residual project-quality confounding.",
        ),
        (
            "graduated_within_60m",
            "D6c_early_60m_timing_check",
            "Matched ATT for graduation within 60 minutes of launch",
            "early_outcome_timing_check",
            "Early outcomes are compatible with launch-time attention, but still cannot separate Telegram exposure from pre-existing project quality.",
        ),
        (
            "graduated_after_60m",
            "D6d_delayed_after_60m_timing_check",
            "Matched ATT for graduation after 60 minutes of launch",
            "delayed_outcome_timing_check",
            "Delayed outcomes are more mechanism-compatible than immediate outcomes, but still observational.",
        ),
        (
            "detection_lag_min",
            "D7_negative_control_detection_lag",
            "Matched difference in data-collection detection lag",
            "negative_control_diagnostic",
            "Detection lag should not be affected by Telegram metadata; imbalance here indicates remaining measurement or source-selection differences.",
        ),
    ]
    rows: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {}
    for outcome, stage, estimand, decision, boundary in specs:
        row, _ = matched_outcome_row(
            df,
            outcome_column=outcome,
            stage=stage,
            estimand=estimand,
            decision=decision,
            claim_boundary=boundary,
            bootstrap_reps=bootstrap_reps,
            seed=seed,
        )
        rows.append(row)
        diagnostics[outcome] = {
            "effect": row["effect"],
            "ci95": [row["ci95_low"], row["ci95_high"]],
            "n_treated": row["n_treated"],
        }
    immediate = float(diagnostics.get("graduated_within_5m", {}).get("effect", np.nan))
    delayed = float(diagnostics.get("graduated_after_60m", {}).get("effect", np.nan))
    diagnostics["causal_timing_interpretation"] = (
        "immediate_association_present_keep_causal_boundary_strict"
        if np.isfinite(immediate) and immediate > max(0.0005, abs(delayed) * 0.25)
        else "immediate_placebo_like_check_not_large_relative_to_delayed_signal"
    )
    return pd.DataFrame(rows), diagnostics


def build_matched_design(df: pd.DataFrame, *, bootstrap_reps: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    treated = df.loc[df["has_telegram"].eq(1)].copy()
    controls = df.loc[df["has_telegram"].eq(0)].copy()
    control_cells = (
        controls.groupby(CELL_COLUMNS, dropna=False)
        .agg(
            control_n=("mint", "count"),
            control_graduation_mean=("graduated", "mean"),
            control_metadata_pre_outcome=("metadata_pre_outcome", "mean"),
        )
        .reset_index()
    )
    supported = treated.merge(control_cells, on=CELL_COLUMNS, how="left")
    supported = supported.loc[pd.to_numeric(supported["control_n"], errors="coerce").fillna(0).gt(0)].copy()
    treated_cell_counts = supported.groupby(CELL_COLUMNS, dropna=False).agg(treated_cell_n=("mint", "count")).reset_index()
    matched_controls = controls.merge(control_cells, on=CELL_COLUMNS, how="inner").merge(treated_cell_counts, on=CELL_COLUMNS, how="inner")
    matched_controls["match_weight"] = matched_controls["treated_cell_n"] / matched_controls["control_n"]

    naive_treated_rate = float(treated["graduated"].mean())
    naive_control_rate = float(controls["graduated"].mean())
    matched_treated_rate = float(supported["graduated"].mean())
    matched_control_rate = float(supported["control_graduation_mean"].mean())
    matched_att = matched_treated_rate - matched_control_rate
    se, ci_low, ci_high = cluster_bootstrap_ci(supported, reps=bootstrap_reps, seed=seed)
    rr = matched_treated_rate / matched_control_rate if matched_control_rate > 0 else float("nan")
    e_value = e_value_from_rr(rr)

    cells = (
        supported.groupby(CELL_COLUMNS, dropna=False)
        .agg(
            treated_n=("mint", "count"),
            treated_graduation_mean=("graduated", "mean"),
            control_n=("control_n", "first"),
            control_graduation_mean=("control_graduation_mean", "first"),
        )
        .reset_index()
    )
    cells["att_cell"] = cells["treated_graduation_mean"] - cells["control_graduation_mean"]

    design_rows = [
        {
            "design_id": DESIGN_ID,
            "stage": "D0_naive",
            "estimand": "Full-sample Telegram graduation difference",
            "outcome": "graduated",
            "horizon_days": "",
            "n_treated": int(len(treated)),
            "n_control": int(len(controls)),
            "treated_value": naive_treated_rate,
            "control_value": naive_control_rate,
            "effect": naive_treated_rate - naive_control_rate,
            "ci95_low": "",
            "ci95_high": "",
            "sensitivity_value": "",
            "decision": "strong_unadjusted_association",
            "claim_boundary": "Unadjusted association; do not interpret as causal.",
            "source_artifact": "RED-PUMP token outcomes",
        },
        {
            "design_id": DESIGN_ID,
            "stage": "D1_coarsened_exact_match",
            "estimand": "ATT for Telegram-present launch metadata among supported exact-match cells",
            "outcome": "graduated",
            "horizon_days": "",
            "n_treated": int(len(supported)),
            "n_control": int(matched_controls["mint"].nunique()),
            "treated_value": matched_treated_rate,
            "control_value": matched_control_rate,
            "effect": matched_att,
            "ci95_low": ci_low,
            "ci95_high": ci_high,
            "sensitivity_value": se,
            "decision": "credible_matched_association_not_causal",
            "claim_boundary": (
                "Matched on launch day, Twitter, website, initial-market-cap decile, and description bin. "
                "Residual creator quality and off-platform promotion confounding can remain."
            ),
            "source_artifact": "artifacts/tables/telegram_mirror_matched_cells.csv",
        },
        {
            "design_id": DESIGN_ID,
            "stage": "D2_timing_gate",
            "estimand": "Share of supported Telegram cohort with metadata observed before terminal outcome",
            "outcome": "metadata_pre_outcome",
            "horizon_days": "",
            "n_treated": int(len(supported)),
            "n_control": int(len(matched_controls)),
            "treated_value": float(supported["metadata_pre_outcome"].mean()),
            "control_value": weighted_mean(matched_controls["metadata_pre_outcome"], matched_controls["match_weight"]),
            "effect": "",
            "ci95_low": "",
            "ci95_high": "",
            "sensitivity_value": "",
            "decision": "passes_metadata_before_outcome_timing_gate",
            "claim_boundary": "Timing gate verifies launch metadata precedes terminal outcomes; it does not prove exogenous Telegram attention.",
            "source_artifact": "RED-PUMP created_at and terminal_outcome_at",
        },
        {
            "design_id": DESIGN_ID,
            "stage": "D3_sensitivity",
            "estimand": "Approximate E-value for matched graduation risk ratio",
            "outcome": "graduated",
            "horizon_days": "",
            "n_treated": int(len(supported)),
            "n_control": int(matched_controls["mint"].nunique()),
            "treated_value": matched_treated_rate,
            "control_value": matched_control_rate,
            "effect": rr,
            "ci95_low": "",
            "ci95_high": "",
            "sensitivity_value": e_value,
            "decision": "large_unobserved_confounding_needed_on_rr_scale",
            "claim_boundary": "E-value is a sensitivity diagnostic for association robustness, not a causal identification proof.",
            "source_artifact": "artifacts/tables/telegram_mirror_design.csv",
        },
    ]

    event_time_rows, event_time_diagnostics = event_time_and_negative_control_rows(
        df,
        bootstrap_reps=bootstrap_reps,
        seed=seed,
    )

    summary = {
        "design_id": DESIGN_ID,
        "event_id": EVENT_ID,
        "status": "credible_matched_design_not_causal",
        "treatment_definition": "has_telegram == 1 in RED-PUMP launch-time metadata",
        "control_definition": "has_telegram == 0 in the same launch-day/coarse metadata cell",
        "cell_columns": CELL_COLUMNS,
        "bootstrap": {"cluster": "launch_day", "reps": bootstrap_reps, "seed": seed},
        "n_total": int(len(df)),
        "n_treated_full": int(len(treated)),
        "n_control_full": int(len(controls)),
        "n_treated_matched_supported": int(len(supported)),
        "n_control_matched_pool": int(matched_controls["mint"].nunique()),
        "treated_support_share": float(len(supported) / len(treated)) if len(treated) else float("nan"),
        "matched_treated_rate": matched_treated_rate,
        "matched_control_rate": matched_control_rate,
        "matched_att": matched_att,
        "cluster_bootstrap_se": se,
        "cluster_bootstrap_ci95": [ci_low, ci_high],
        "matched_risk_ratio": rr,
        "e_value": e_value,
        "event_time_diagnostics": event_time_diagnostics,
        "claim_boundary": (
            "Use as a credible matched Telegram mirror design and mechanism-supported predictive signal. "
            "Event-time diagnostics are included, but do not claim a causal Telegram effect without an exogenous "
            "attention shock or stronger event-time exposure design."
        ),
        "missing_controls": [
            "creator history is not available for the full RED-PUMP launch cohort in this table",
            "initial liquidity is proxied by initial_market_cap_sol",
            "risk labels are not joined for the full cohort",
        ],
    }
    balance = balance_rows(
        full_treated=treated,
        full_control=controls,
        matched_treated=supported,
        matched_control=matched_controls,
    )
    return pd.concat([pd.DataFrame(design_rows), event_time_rows], ignore_index=True), cells, balance, summary


def token_horizon_rows(df: pd.DataFrame) -> pd.DataFrame:
    social = df[["mint", "has_telegram"]].copy()
    rows: list[dict[str, Any]] = []
    rpc = read_csv(EXTERNAL / "h1_rpc_token_level_outcomes.csv", low_memory=False)
    if not rpc.empty:
        joined = rpc.merge(social, on="mint", how="left")
        for horizon in [1, 7, 30]:
            for metric in [f"active_{horizon}d", f"swap_count_{horizon}d", f"active_traders_{horizon}d"]:
                if metric not in joined:
                    continue
                by_tel = joined.groupby("has_telegram", dropna=False)[metric].agg(["count", "mean", "median"]).reset_index()
                if {0, 1}.issubset(set(by_tel["has_telegram"].dropna().astype(int))):
                    tel = by_tel.loc[by_tel["has_telegram"].eq(1)].iloc[0]
                    no_tel = by_tel.loc[by_tel["has_telegram"].eq(0)].iloc[0]
                    rows.append(
                        {
                            "design_id": DESIGN_ID,
                            "stage": "D4_token_horizon_validation_rpc",
                            "estimand": f"Graduated-token RPC proxy by Telegram metadata: {metric}",
                            "outcome": metric,
                            "horizon_days": horizon,
                            "n_treated": int(tel["count"]),
                            "n_control": int(no_tel["count"]),
                            "treated_value": float(tel["median"]),
                            "control_value": float(no_tel["median"]),
                            "effect": float(tel["median"] - no_tel["median"]),
                            "ci95_low": "",
                            "ci95_high": "",
                            "sensitivity_value": "",
                            "decision": "selected_graduated_token_mechanism_check",
                            "claim_boundary": "RPC row is conditional on graduation and proxy parsing; not a full launch-cohort causal outcome.",
                            "source_artifact": "artifacts/external_validation/h1_rpc_token_level_outcomes.csv",
                        }
                    )

    moralis = read_csv(EXTERNAL / "moralis_decoded_token_outcomes.csv", low_memory=False)
    if not moralis.empty:
        joined_m = moralis.merge(social, on="mint", how="left")
        for horizon in [1, 7, 30]:
            mh = joined_m.loc[pd.to_numeric(joined_m["horizon_days"], errors="coerce").eq(horizon)].copy()
            for metric in ["decoded_volume_usd", "decoded_active_traders", "decoded_trade_count"]:
                if metric not in mh:
                    continue
                by_tel = mh.groupby("has_telegram", dropna=False)[metric].agg(["count", "mean", "median"]).reset_index()
                if {0, 1}.issubset(set(by_tel["has_telegram"].dropna().astype(int))):
                    tel = by_tel.loc[by_tel["has_telegram"].eq(1)].iloc[0]
                    no_tel = by_tel.loc[by_tel["has_telegram"].eq(0)].iloc[0]
                    rows.append(
                        {
                            "design_id": DESIGN_ID,
                            "stage": "D5_token_horizon_validation_moralis",
                            "estimand": f"Moralis decoded graduated-token sample by Telegram metadata: {metric}",
                            "outcome": metric,
                            "horizon_days": horizon,
                            "n_treated": int(tel["count"]),
                            "n_control": int(no_tel["count"]),
                            "treated_value": float(tel["median"]),
                            "control_value": float(no_tel["median"]),
                            "effect": float(tel["median"] - no_tel["median"]),
                            "ci95_low": "",
                            "ci95_high": "",
                            "sensitivity_value": "",
                            "decision": "selected_decoded_sample_mechanism_check",
                            "claim_boundary": "Moralis decoded rows are selected covered tokens; not a full launch-cohort causal outcome.",
                            "source_artifact": "artifacts/external_validation/moralis_decoded_token_outcomes.csv",
                        }
                    )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap-reps", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260729)
    args = parser.parse_args()

    config = load_config()
    red_path = source_path(config, "red_pump_token_outcomes")
    red = read_csv(red_path, usecols=lambda c: c in SOCIAL_COLUMNS, low_memory=False)
    if red.empty:
        raise RuntimeError(f"Missing RED-PUMP token outcomes: {red_path}")
    design_df = add_design_features(red)
    rows, cells, balance, summary = build_matched_design(design_df, bootstrap_reps=args.bootstrap_reps, seed=args.seed)
    horizon_rows = token_horizon_rows(design_df)
    if not horizon_rows.empty:
        rows = pd.concat([rows, horizon_rows], ignore_index=True)
    summary["source_artifact"] = relpath(red_path)
    summary["token_horizon_validation_rows"] = int(len(horizon_rows))

    write_csv(TABLES / "telegram_mirror_design.csv", rows)
    write_csv(TABLES / "telegram_mirror_matched_cells.csv", cells)
    write_csv(TABLES / "telegram_mirror_balance.csv", balance)
    write_json(TABLES / "telegram_mirror_design_summary.json", summary)
    print(
        "Telegram mirror matched design written: "
        f"treated_supported={summary['n_treated_matched_supported']} "
        f"matched_att={summary['matched_att']:.6f} status={summary['status']}"
    )


if __name__ == "__main__":
    main()
