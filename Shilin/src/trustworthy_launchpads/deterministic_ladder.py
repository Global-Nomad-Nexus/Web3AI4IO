"""Deterministic L0--L7 benchmark ladder for the Pump.fun/PumpSwap case."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .identification import build_market_identification_artifacts
from .io import CaseConfig, read_hf_pump_sentiment, read_market_panel, read_optional_csv, write_csv, write_json
from .stats import (
    coefficient_row,
    estimate_ols,
    exact_rademacher_wild_cluster,
    linear_combination,
    normal_ci,
    two_sample_difference,
)


@dataclass
class LadderOutputs:
    ladder: pd.DataFrame
    event_study: pd.DataFrame
    pretrend: dict[str, object]
    frequency: pd.DataFrame


def add_weekly_panel(panel: pd.DataFrame) -> pd.DataFrame:
    data = panel.copy()
    data["date"] = pd.to_datetime(data["date"], utc=True)
    weekday = data["date"].dt.weekday
    data["week_start"] = (data["date"] - pd.to_timedelta(weekday, unit="D")).dt.floor("D")
    weekly = (
        data.groupby(["unit", "week_start"], as_index=False)
        .agg(
            daily_volume_usd=("daily_volume_usd", "sum"),
            treated=("treated", "max"),
        )
    )
    event_date = pd.Timestamp("2025-03-20", tz="UTC")
    weekly["post"] = (weekly["week_start"] >= event_date).astype(int)
    weekly["did"] = weekly["treated"] * weekly["post"]
    weekly["rel_day"] = (weekly["week_start"] - event_date).dt.days
    weekly["rel_week"] = np.floor(weekly["rel_day"] / 7).astype(int).clip(-12, 12)
    weekly["log_volume"] = np.log1p(weekly["daily_volume_usd"])
    weekly["date_str"] = weekly["week_start"].dt.strftime("%Y-%m-%d")
    weekly["calendar_week"] = weekly["date_str"]
    weekly = weekly.rename(columns={"week_start": "date"})
    return weekly


def estimate_l0(panel: pd.DataFrame, window_days: int = 90) -> dict[str, object]:
    treated = panel.loc[panel["treated"].eq(1)].copy()
    treated = treated.loc[treated["rel_day"].between(-window_days, window_days)]
    stats = two_sample_difference(
        treated.loc[treated["post"].eq(1), "log_volume"],
        treated.loc[treated["post"].eq(0), "log_volume"],
    )
    return {
        "rung": "L0",
        "component_added": "None: treated before-after means",
        "outcome": "log(1 + Pump ecosystem daily volume USD)",
        "estimate": stats["estimate"],
        "std_error": stats["std_error"],
        "ci95_low": stats["ci95_low"],
        "ci95_high": stats["ci95_high"],
        "p_value": np.nan,
        "worked_decision": "yes" if stats["ci95_low"] > 0 else "no_or_uncertain",
        "method": f"Two-sample pre/post mean difference, treated only, +/-{window_days} days",
        "notes": "This is the operational dashboard estimand: no control group, no fixed effects, no stakeholder metrics.",
    }


def estimate_l1(panel: pd.DataFrame) -> dict[str, object]:
    fit = estimate_ols(panel, "log_volume", ["treated", "post", "did"], [])
    return coefficient_row(
        "L1",
        "+ control group: naive DiD",
        "log(1 + daily volume USD)",
        fit,
        "did",
        method="OLS log_volume ~ treated + post + did, HC1",
        notes="Adds Solana DEX controls but no unit/date fixed effects.",
    )


def estimate_l2(panel: pd.DataFrame) -> dict[str, object]:
    fit = estimate_ols(panel, "log_volume", ["did"], ["unit", "date_str"])
    return coefficient_row(
        "L2",
        "+ two-way fixed effects",
        "log(1 + daily volume USD)",
        fit,
        "did",
        method="OLS log_volume ~ did + unit FE + date FE, HC1",
        notes="Market-level TWFE. Still an aggregate-volume estimand.",
    )


def build_pyfixest_crosscheck(panel: pd.DataFrame) -> pd.DataFrame:
    """Estimate the main DiD specifications with PyFixest for package-level replication."""

    try:
        import pyfixest as pf
    except ImportError as exc:  # pragma: no cover - dependency is declared in pyproject/requirements.
        raise RuntimeError("PyFixest is required for the DiD cross-check. Install requirements.txt.") from exc

    specs = [
        {
            "spec_id": "naive_did",
            "formula": "log_volume ~ treated + post + did",
            "estimand": "Protocol-day naive DiD without fixed effects",
        },
        {
            "spec_id": "twfe_unit_date_fe",
            "formula": "log_volume ~ did | unit + date_str",
            "estimand": "Protocol-day TWFE DiD with unit and date fixed effects",
        },
    ]
    rows: list[dict[str, object]] = []
    for spec in specs:
        fit = pf.feols(spec["formula"], data=panel, vcov="hetero")
        tidy = fit.tidy().reset_index().rename(columns={"index": "term"})
        did = tidy.loc[tidy["Coefficient"].eq("did")].iloc[0]
        rows.append(
            {
                "spec_id": spec["spec_id"],
                "package": "pyfixest",
                "package_version": getattr(pf, "__version__", "unknown"),
                "formula": spec["formula"],
                "vcov": "hetero",
                "estimand": spec["estimand"],
                "term": "did",
                "estimate": float(did["Estimate"]),
                "std_error": float(did["Std. Error"]),
                "ci95_low": float(did["2.5%"]),
                "ci95_high": float(did["97.5%"]),
                "p_value": float(did["Pr(>|t|)"]),
                "interpretation": (
                    "Package-level DiD cross-check. Shilin uses this for reproducibility; "
                    "Claire owns the full staggered cross-chain DiD estimator."
                ),
            }
        )
    return pd.DataFrame(rows)


def fit_event_study(panel: pd.DataFrame) -> tuple[pd.DataFrame, object]:
    data = panel.copy()
    event_weeks = sorted(int(w) for w in data["rel_week"].dropna().unique() if int(w) != -1)
    event_cols: list[tuple[int, str]] = []
    for week in event_weeks:
        label = f"event_m{abs(week)}" if week < 0 else f"event_p{week}"
        data[label] = ((data["treated"].eq(1)) & (data["rel_week"].eq(week))).astype(int)
        event_cols.append((week, label))
    fit = estimate_ols(data, "log_volume", [col for _, col in event_cols], ["unit", "date_str"])
    rows: list[dict[str, object]] = []
    for week, col in event_cols:
        coef = float(fit.params[col])
        se = float(fit.bse[col])
        ci_low, ci_high = normal_ci(coef, se)
        rows.append(
            {
                "rel_week": week,
                "term": col,
                "coef": coef,
                "std_error": se,
                "ci95_low": ci_low,
                "ci95_high": ci_high,
                "reference_week": -1,
            }
        )
    rows.append(
        {
            "rel_week": -1,
            "term": "reference",
            "coef": 0.0,
            "std_error": 0.0,
            "ci95_low": 0.0,
            "ci95_high": 0.0,
            "reference_week": -1,
        }
    )
    event = pd.DataFrame(rows).sort_values("rel_week").reset_index(drop=True)
    return event, fit


def estimate_l3(event: pd.DataFrame, fit: object) -> dict[str, object]:
    post_terms = event.loc[event["rel_week"].ge(0), "term"].tolist()
    estimate, se = linear_combination(fit, post_terms)
    ci_low, ci_high = normal_ci(estimate, se)
    return {
        "rung": "L3",
        "component_added": "+ dynamic event-study estimator",
        "outcome": "average post-event dynamic effect on log volume",
        "estimate": estimate,
        "std_error": se,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "p_value": np.nan,
        "worked_decision": "yes" if ci_low > 0 else "no_or_uncertain",
        "method": "Single-event dynamic TWFE/event-study proxy; staggered rung is partially vacuous for Shilin case.",
        "notes": "Claire owns true staggered LP-DiD. Here L3 records the compatible single-event dynamic analogue.",
    }


def estimate_l4(event: pd.DataFrame, l3_row: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    pre = event.loc[event["rel_week"].lt(-1)].copy()
    pre["significant"] = (pre["ci95_low"] > 0) | (pre["ci95_high"] < 0)
    max_abs = float(pre["coef"].abs().max()) if len(pre) else np.nan
    significant_count = int(pre["significant"].sum()) if len(pre) else 0
    diagnostics = {
        "pretrend_weeks_checked": int(len(pre)),
        "significant_pretrend_weeks": significant_count,
        "max_abs_pretrend_log_points": max_abs,
        "mean_abs_pretrend_log_points": float(pre["coef"].abs().mean()) if len(pre) else np.nan,
        "pretrend_flag": significant_count > 0,
        "interpretation": (
            "Pre-trend risk detected; market-level volume estimates should not be read as clean causal evidence."
            if significant_count > 0
            else "No statistically visible pre-trend in this event-study screen."
        ),
    }
    row = dict(l3_row)
    row.update(
        {
            "rung": "L4",
            "component_added": "+ event-study/pre-trend diagnostics",
            "worked_decision": "pretrend_flagged" if diagnostics["pretrend_flag"] else l3_row["worked_decision"],
            "method": "L3 dynamic effect plus pre-trend screen over treated x relative-week coefficients",
            "notes": diagnostics["interpretation"],
        }
    )
    return row, diagnostics


def estimate_l5(config: CaseConfig) -> dict[str, object]:
    try:
        hf = read_hf_pump_sentiment(config, latest_per_mint=True)
    except FileNotFoundError:
        hf = pd.DataFrame()
    if not hf.empty and {"risk_level", "holder_concentration", "top10_holder_pct"}.issubset(hf.columns):
        data = hf.copy()
        data["top10_holder_pct_clean"] = pd.to_numeric(data["top10_holder_pct"], errors="coerce").clip(0, 100)
        data["high_concentration"] = (
            data["holder_concentration"].astype(str).isin(["whale_dominated", "concentrated"])
            | data["top10_holder_pct_clean"].ge(80)
        ).astype(int)
        data["high_or_critical_risk"] = data["risk_level"].astype(str).isin(["high", "critical"]).astype(int)
        treated = data.loc[data["high_concentration"].eq(1), "high_or_critical_risk"]
        control = data.loc[data["high_concentration"].eq(0), "high_or_critical_risk"]
        stats = two_sample_difference(treated, control)
        z_score = stats["estimate"] / stats["std_error"] if stats["std_error"] else np.nan
        p_value = math.erfc(abs(z_score) / math.sqrt(2)) if not pd.isna(z_score) else np.nan
        return {
            "rung": "L5",
            "component_added": "+ token-level heterogeneity",
            "outcome": "source-coded high/critical risk probability: high concentration minus others",
            "estimate": stats["estimate"],
            "std_error": stats["std_error"],
            "ci95_low": stats["ci95_low"],
            "ci95_high": stats["ci95_high"],
            "p_value": p_value,
            "worked_decision": "retail_risk_higher" if stats["ci95_low"] > 0 else "mixed_or_uncertain",
            "method": "HuggingFace Pump.fun sentiment/risk sample; latest snapshot per mint; difference in high-risk rates by concentration proxy",
            "notes": (
                "This audits H4 with token-level holder concentration and source-coded risk fields; it is a proxy association, not sniper causality. "
                "Dune early-buyer data remain a registered event-time validation layer."
            ),
        }

    lpm_path = config.legacy_table("red_pump_social_lpm_results.csv", required=False)
    lpm = read_optional_csv(lpm_path)
    if lpm is None or lpm.empty:
        return {
            "rung": "L5",
            "component_added": "+ token-level heterogeneity",
            "outcome": "graduation probability",
            "estimate": np.nan,
            "std_error": np.nan,
            "ci95_low": np.nan,
            "ci95_high": np.nan,
            "p_value": np.nan,
            "worked_decision": "not_available",
            "method": "RED-PUMP social heterogeneity LPM",
            "notes": "Legacy RED-PUMP LPM table missing.",
        }
    preferred = lpm.loc[lpm["variable"].eq("has_telegram")]
    row = preferred.iloc[0] if len(preferred) else lpm.iloc[0]
    coef = float(row["coef_probability_points"])
    se = float(row["std_error"])
    ci_low = float(row["ci95_low"])
    ci_high = float(row["ci95_high"])
    return {
        "rung": "L5",
        "component_added": "+ token-level heterogeneity",
        "outcome": f"graduation probability: {row['variable']}",
        "estimate": coef,
        "std_error": se,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "p_value": float(row["p_value_normal_approx"]),
        "worked_decision": "heterogeneous_positive" if ci_low > 0 else "mixed_or_negative",
        "method": "RED-PUMP row-level LPM with launch-day fixed effects from upstream MVP",
        "notes": "Units are probability points, not log-volume points; this rung intentionally changes from aggregate mean to token distribution.",
    }


def estimate_l6(panel: pd.DataFrame) -> tuple[dict[str, object], dict[str, object]]:
    boot = exact_rademacher_wild_cluster(
        panel,
        outcome="log_volume",
        treatment="did",
        covariates=[],
        fixed_effects=["unit", "date_str"],
        cluster="unit",
    )
    row = {
        "rung": "L6",
        "component_added": "+ honest few-cluster inference",
        "outcome": "log(1 + daily volume USD)",
        "estimate": boot["estimate"],
        "std_error": boot["std_error_hc1"],
        "ci95_low": boot["wild_bootstrap_ci95_low"],
        "ci95_high": boot["wild_bootstrap_ci95_high"],
        "p_value": boot["wild_bootstrap_p_value"],
        "worked_decision": "yes" if boot["wild_bootstrap_ci95_low"] > 0 else "no_or_uncertain",
        "method": boot["method"],
        "notes": f"Exact over {boot['sign_assignments']} Rademacher assignments with {boot['cluster_count']} protocol clusters.",
    }
    return row, boot


def estimate_l7(l6_row: dict[str, object]) -> dict[str, object]:
    row = dict(l6_row)
    row.update(
        {
            "rung": "L7",
            "component_added": "+ data richness and stakeholder metric battery",
            "outcome": "stakeholder-dependent metric vector",
            "worked_decision": "depends_on_stakeholder",
            "method": "L6 estimate interpreted through Result 1 stakeholder battery and data-availability ledger",
            "notes": "Aggregate activity is only one stakeholder metric; creator, retail fairness, security, UX, and community metrics are reported separately.",
        }
    )
    return row


def build_frequency_sensitivity(panel: pd.DataFrame, config: CaseConfig) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    post_validation_path = config.output_root / "external_validation" / "solana_post_migration_pool_windows.csv"
    early_validation_path = config.output_root / "external_validation" / "solana_early_wallet_concentration.csv"
    external_summary_path = config.tables_dir / "external_validation_summary.json"
    moralis_outcomes_path = config.output_root / "external_validation" / "moralis_decoded_token_outcomes.csv"
    moralis_summary_path = config.tables_dir / "moralis_decoded_outcomes_summary.json"
    external_summary = {}
    if external_summary_path.exists():
        import json

        external_summary = json.loads(external_summary_path.read_text(encoding="utf-8"))
    moralis_summary = {}
    if moralis_summary_path.exists():
        import json

        moralis_summary = json.loads(moralis_summary_path.read_text(encoding="utf-8"))

    def read_nonempty_csv(path: Path) -> pd.DataFrame | None:
        if not path.exists() or path.stat().st_size == 0:
            return None
        try:
            return pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return None
    daily = estimate_l2(panel)
    rows.append(
        {
            "layer": "market_daily_twfe",
            "unit": "protocol-day",
            "outcome": daily["outcome"],
            "estimate": daily["estimate"],
            "ci95_low": daily["ci95_low"],
            "ci95_high": daily["ci95_high"],
            "decision": daily["worked_decision"],
            "interpretation": "Daily protocol aggregates answer platform activity, not median token welfare.",
        }
    )
    weekly_panel = add_weekly_panel(panel)
    weekly = estimate_l2(weekly_panel)
    rows.append(
        {
            "layer": "market_weekly_twfe",
            "unit": "protocol-week",
            "outcome": weekly["outcome"],
            "estimate": weekly["estimate"],
            "ci95_low": weekly["ci95_low"],
            "ci95_high": weekly["ci95_high"],
            "decision": weekly["worked_decision"],
            "interpretation": "Weekly aggregation smooths high-frequency launch/migration variation.",
        }
    )
    l5 = estimate_l5(config)
    rows.append(
        {
            "layer": "token_risk_snapshot_heterogeneity",
            "unit": "token",
            "outcome": l5["outcome"],
            "estimate": l5["estimate"],
            "ci95_low": l5["ci95_low"],
            "ci95_high": l5["ci95_high"],
            "decision": l5["worked_decision"],
            "interpretation": "Token-level concentration/risk heterogeneity is visible only below protocol aggregates; latest snapshot per mint.",
        }
    )
    post = read_nonempty_csv(post_validation_path)
    if post is not None:
        post30 = post.loc[post["horizon_days"].eq(30)] if "horizon_days" in post else pd.DataFrame()
        if len(post30) and "signature_window_status" in post30:
            complete_post30 = post30.loc[post30["signature_window_status"].astype(str).eq("ok")]
        else:
            complete_post30 = post30
        estimate = float(complete_post30["swap_count"].median()) if len(complete_post30) else np.nan
        complete_status = external_summary.get("credible_sample_status") == "credible_complete_rpc_post_migration_sample"
        rows.append(
            {
                "layer": "token_post_migration_windows",
                "unit": "token x horizon",
                "outcome": "30d successful PumpSwap-pool transaction count proxy, complete windows",
                "estimate": estimate,
                "ci95_low": np.nan,
                "ci95_high": np.nan,
                "decision": "computed_external_validation_sample",
                "interpretation": (
                    "Complete Pump.fun/Solana RPC post-migration windows validate observable pool activity; still not decoded Dune USD volume."
                    if complete_status
                    else "Real Solana RPC/Pump.fun pool-address screening sample; truncated rows are not treated as precise 30d outcomes."
                ),
            }
        )
    else:
        rows.append(
            {
                "layer": "token_post_migration_windows",
                "unit": "token x horizon",
                "outcome": "1/7/30d swap count, active traders, volume",
                "estimate": np.nan,
                "ci95_low": np.nan,
                "ci95_high": np.nan,
                "decision": "registered_external_validation",
                "interpretation": "Event-time validation layer for H1; schema and SQL are provided, but no fabricated values are reported.",
            }
        )
    moralis = read_nonempty_csv(moralis_outcomes_path)
    if moralis is not None:
        horizon = pd.to_numeric(moralis.get("horizon_days"), errors="coerce")
        moralis30 = moralis.loc[horizon.eq(30)].copy()
        volume = pd.to_numeric(moralis30.get("decoded_volume_usd"), errors="coerce")
        estimate = float(volume.median()) if len(volume.dropna()) else np.nan
        rows.append(
            {
                "layer": "token_decoded_usd_outcomes",
                "unit": "token x horizon",
                "outcome": "30d decoded Moralis USD swap volume, covered tokens",
                "estimate": estimate,
                "ci95_low": np.nan,
                "ci95_high": np.nan,
                "decision": "computed_external_validation_sample",
                "interpretation": (
                    f"Moralis decoded {int(moralis_summary.get('unique_decoded_swap_rows', 0) or 0):,} unique swap rows "
                    f"over {int(moralis_summary.get('decoded_30d_tokens_with_swaps', 0) or 0)} covered 30d token windows; "
                    "this is outcome measurement for Shilin's H1 layer, not the cross-chain staggered DiD."
                ),
            }
        )
    else:
        rows.append(
            {
                "layer": "token_decoded_usd_outcomes",
                "unit": "token x horizon",
                "outcome": "30d decoded USD swap volume, active traders, trade direction",
                "estimate": np.nan,
                "ci95_low": np.nan,
                "ci95_high": np.nan,
                "decision": "registered_external_validation",
                "interpretation": "Moralis/Birdeye/Dune decoded token-outcome layer registered; no values are fabricated when the collector has not run.",
            }
        )
    early = read_nonempty_csv(early_validation_path)
    if early is not None:
        estimate = float(early["top1_early_buyer_share"].median()) if len(early) else np.nan
        rows.append(
            {
                "layer": "early_allocation_fairness",
                "unit": "token x early-wallet cohort",
                "outcome": "median top-1 early fee-payer share proxy",
                "estimate": estimate,
                "ci95_low": np.nan,
                "ci95_high": np.nan,
                "decision": "computed_external_validation_sample",
                "interpretation": "Real Solana RPC bonding-curve sample; fee-payer concentration proxy for early allocation/sniper validation.",
            }
        )
    else:
        rows.append(
            {
                "layer": "early_allocation_fairness",
                "unit": "token x early-wallet cohort",
                "outcome": "top holder share, Gini, sniper share",
                "estimate": np.nan,
                "ci95_low": np.nan,
                "ci95_high": np.nan,
                "decision": "registered_external_validation",
                "interpretation": "Event-time validation layer for H4 early allocation/sniper mechanisms.",
            }
        )
    return pd.DataFrame(rows)


def run_ladder(config: CaseConfig) -> LadderOutputs:
    panel = read_market_panel(config)
    event, event_fit = fit_event_study(panel)
    l0_rows = [estimate_l0(panel, int(window)) for window in config.raw.get("l0_windows_days", [90])]
    l0_main = [row for row in l0_rows if row["method"].endswith("+/-90 days")]
    rows = [l0_main[0] if l0_main else l0_rows[-1]]
    rows.append(estimate_l1(panel))
    rows.append(estimate_l2(panel))
    l3 = estimate_l3(event, event_fit)
    rows.append(l3)
    l4, pretrend = estimate_l4(event, l3)
    rows.append(l4)
    rows.append(estimate_l5(config))
    l6, boot = estimate_l6(panel)
    rows.append(l6)
    rows.append(estimate_l7(l6))

    ladder = pd.DataFrame(rows)
    frequency = build_frequency_sensitivity(panel, config)
    pyfixest_crosscheck = build_pyfixest_crosscheck(panel)
    build_market_identification_artifacts(panel, config)

    write_csv(config.tables_dir / "deterministic_ladder.csv", ladder)
    write_csv(config.tables_dir / "pyfixest_did_crosscheck.csv", pyfixest_crosscheck)
    write_csv(config.tables_dir / "l0_window_sensitivity.csv", pd.DataFrame(l0_rows))
    write_csv(config.tables_dir / "event_study_coefficients_shilin.csv", event)
    write_csv(config.tables_dir / "result1_frequency_sensitivity.csv", frequency)
    write_json(config.tables_dir / "pretrend_diagnostics.json", pretrend)
    write_json(config.tables_dir / "wild_cluster_bootstrap.json", boot)
    return LadderOutputs(ladder=ladder, event_study=event, pretrend=pretrend, frequency=frequency)
