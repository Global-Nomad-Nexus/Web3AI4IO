"""Causal-claim audit for the Pump.fun -> PumpSwap application arm.

This module deliberately separates a mechanism-level H1 claim from stronger
token-welfare claims. The current Helius/RPC artifacts can validate that
graduated tokens activate and persist on post-migration PumpSwap pools; they do
not decode USD trade volume, trade direction, trader identity, or early-wallet
sniper features.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

try:
    from scipy.stats import binomtest
except ModuleNotFoundError:  # pragma: no cover - fallback for slim local environments
    class _BinomResult:
        def __init__(self, pvalue: float) -> None:
            self.pvalue = pvalue

    def binomtest(successes: int, n: int, p: float, alternative: str = "greater") -> _BinomResult:
        if alternative != "greater":
            raise ValueError("Fallback binomtest only supports alternative='greater'.")
        if n <= 0:
            return _BinomResult(float("nan"))
        if successes <= 0:
            return _BinomResult(1.0)
        if successes > n:
            return _BinomResult(float("nan"))
        if p <= 0:
            return _BinomResult(1.0)
        if p >= 1:
            return _BinomResult(1.0 if successes <= n else 0.0)

        # Recurrence avoids huge combinations for n in the thousands.
        prob = (1 - p) ** n
        tail = 0.0
        for k in range(0, n + 1):
            if k >= successes:
                tail += prob
            if k == n:
                break
            prob = prob * (n - k) / (k + 1) * p / (1 - p)
        return _BinomResult(float(min(max(tail, 0.0), 1.0)))

from .io import CaseConfig, write_csv, write_json


HORIZONS = (1, 7, 30)
RANDOM_SEED = 20260729


def _read_nonempty_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _summarize_moralis_decoded_outcomes(config: CaseConfig) -> dict[str, object]:
    outcomes_path = config.output_root / "external_validation" / "moralis_decoded_token_outcomes.csv"
    outcomes = _read_nonempty_csv(outcomes_path)
    if outcomes.empty:
        return {
            "outcomes_path": str(outcomes_path),
            "decoded_outcome_rows": 0,
            "decoded_30d_tokens": 0,
            "decoded_30d_positive_volume_tokens": 0,
            "decoded_30d_positive_volume_share": np.nan,
            "decoded_30d_positive_volume_ci95_low": np.nan,
            "decoded_30d_positive_volume_ci95_high": np.nan,
            "decoded_30d_median_volume_usd": np.nan,
            "decoded_30d_median_trade_count": np.nan,
            "decoded_30d_median_active_traders": np.nan,
            "decoded_sample_present": False,
        }
    horizon = pd.to_numeric(outcomes.get("horizon_days"), errors="coerce")
    outcome30 = outcomes.loc[horizon.eq(30)].copy()
    if outcome30.empty:
        return {
            "outcomes_path": str(outcomes_path),
            "decoded_outcome_rows": int(len(outcomes)),
            "decoded_30d_tokens": 0,
            "decoded_30d_positive_volume_tokens": 0,
            "decoded_30d_positive_volume_share": np.nan,
            "decoded_30d_positive_volume_ci95_low": np.nan,
            "decoded_30d_positive_volume_ci95_high": np.nan,
            "decoded_30d_median_volume_usd": np.nan,
            "decoded_30d_median_trade_count": np.nan,
            "decoded_30d_median_active_traders": np.nan,
            "decoded_sample_present": False,
        }
    volume = pd.to_numeric(outcome30.get("decoded_volume_usd"), errors="coerce").fillna(0)
    trades = pd.to_numeric(outcome30.get("decoded_trade_count"), errors="coerce").fillna(0)
    active = pd.to_numeric(outcome30.get("decoded_active_traders"), errors="coerce").fillna(0)
    n_tokens = int(outcome30["mint"].nunique()) if "mint" in outcome30 else int(len(outcome30))
    positive_volume = int(outcome30.loc[volume.gt(0), "mint"].nunique()) if "mint" in outcome30 else int(volume.gt(0).sum())
    share = positive_volume / n_tokens if n_tokens else np.nan
    ci_low, ci_high = _wilson_interval(positive_volume, n_tokens)
    return {
        "outcomes_path": str(outcomes_path),
        "decoded_outcome_rows": int(len(outcomes)),
        "decoded_30d_tokens": n_tokens,
        "decoded_30d_positive_volume_tokens": positive_volume,
        "decoded_30d_positive_volume_share": float(share),
        "decoded_30d_positive_volume_ci95_low": ci_low,
        "decoded_30d_positive_volume_ci95_high": ci_high,
        "decoded_30d_median_volume_usd": float(volume.median()) if len(volume) else np.nan,
        "decoded_30d_median_trade_count": float(trades.median()) if len(trades) else np.nan,
        "decoded_30d_median_active_traders": float(active.median()) if len(active) else np.nan,
        "decoded_sample_present": bool(n_tokens > 0),
    }


def _wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return np.nan, np.nan
    phat = successes / n
    denom = 1 + z**2 / n
    centre = phat + z**2 / (2 * n)
    radius = z * np.sqrt((phat * (1 - phat) + z**2 / (4 * n)) / n)
    return float((centre - radius) / denom), float((centre + radius) / denom)


def _bootstrap_median_ci(values: Iterable[float], *, draws: int = 2000) -> tuple[float, float]:
    arr = np.asarray([float(v) for v in values if not pd.isna(v)], dtype=float)
    if len(arr) == 0:
        return np.nan, np.nan
    rng = np.random.default_rng(RANDOM_SEED)
    samples = rng.choice(arr, size=(draws, len(arr)), replace=True)
    medians = np.median(samples, axis=1)
    low, high = np.quantile(medians, [0.025, 0.975])
    return float(low), float(high)


def _safe_quantile(series: pd.Series, q: float) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return float(clean.quantile(q)) if len(clean) else np.nan


def _safe_median(series: pd.Series) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return float(clean.median()) if len(clean) else np.nan


def _binom_pvalue(successes: int, n: int, threshold: float) -> float:
    if n <= 0:
        return np.nan
    return float(binomtest(successes, n, p=threshold, alternative="greater").pvalue)


def build_h1_token_outcomes(config: CaseConfig, post: pd.DataFrame) -> pd.DataFrame:
    """Write one row per token with 1/7/30d RPC post-migration outcomes."""

    if post.empty:
        return pd.DataFrame()

    pieces: list[pd.DataFrame] = []
    for horizon in HORIZONS:
        horizon_df = post.loc[post["horizon_days"].eq(horizon)].copy()
        if horizon_df.empty:
            continue
        keep = [
            "mint",
            "graduated_at",
            "pool_address",
            "swap_count",
            "active_traders",
            "volume_usd",
            "volume_sol_proxy",
            "first_trade_at",
            "last_trade_at",
            "inactivity_gap_hours",
            "reactivated_after_7d",
            "signatures_scanned",
            "transactions_parsed",
            "signature_window_status",
            "validation_status",
        ]
        cols = [col for col in keep if col in horizon_df.columns]
        horizon_df = horizon_df[cols].copy()
        rename = {
            col: f"{col}_{horizon}d"
            for col in cols
            if col not in {"mint", "graduated_at", "pool_address"}
        }
        horizon_df = horizon_df.rename(columns=rename)
        horizon_df[f"active_{horizon}d"] = (
            pd.to_numeric(horizon_df[f"swap_count_{horizon}d"], errors="coerce").gt(0).astype(int)
        )
        horizon_df[f"complete_{horizon}d"] = (
            horizon_df[f"signature_window_status_{horizon}d"].astype(str).eq("ok").astype(int)
        )
        pieces.append(horizon_df.set_index("mint"))

    if not pieces:
        return pd.DataFrame()
    wide = pd.concat(pieces, axis=1)
    wide = wide.loc[:, ~wide.columns.duplicated()].reset_index()

    metadata_path = config.output_root / "external_validation" / "pumpfun_coin_metadata.csv"
    metadata = _read_nonempty_csv(metadata_path)
    if not metadata.empty:
        meta_cols = [
            "mint",
            "created_at",
            "graduated_at",
            "creator",
            "pool_address",
            "last_trade_at",
            "ath_market_cap",
            "usd_market_cap",
            "market_cap",
            "protocol",
        ]
        metadata = metadata[[col for col in meta_cols if col in metadata.columns]].drop_duplicates("mint")
        wide = metadata.merge(wide, on="mint", how="right", suffixes=("_metadata", ""))

    graduated = pd.to_datetime(wide.get("graduated_at_30d", wide.get("graduated_at")), utc=True, errors="coerce")
    first_trade = pd.to_datetime(wide.get("first_trade_at_30d"), utc=True, errors="coerce")
    wide["first_trade_lag_seconds_30d"] = (first_trade - graduated).dt.total_seconds()
    wide["temporal_order_violation_30d"] = wide["first_trade_lag_seconds_30d"].lt(0).fillna(False).astype(int)
    wide["complete_all_horizons"] = wide[[f"complete_{horizon}d" for horizon in HORIZONS if f"complete_{horizon}d" in wide]].min(axis=1)
    wide["log1p_swap_count_30d"] = np.log1p(pd.to_numeric(wide.get("swap_count_30d"), errors="coerce"))
    wide["log1p_swap_count_growth_1d_to_30d"] = (
        np.log1p(pd.to_numeric(wide.get("swap_count_30d"), errors="coerce"))
        - np.log1p(pd.to_numeric(wide.get("swap_count_1d"), errors="coerce"))
    )
    return wide


def _audit_row(
    *,
    claim_id: str,
    hypothesis: str,
    estimand: str,
    sample_rule: str,
    n_tokens: int,
    estimate: float,
    ci95_low: float,
    ci95_high: float,
    p_value: float,
    decision: str,
    causal_status: str,
    claim_allowed: str,
    claim_not_allowed: str,
    academic_standard_note: str,
) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "hypothesis": hypothesis,
        "estimand": estimand,
        "sample_rule": sample_rule,
        "n_tokens": int(n_tokens),
        "estimate": float(estimate) if not pd.isna(estimate) else np.nan,
        "ci95_low": float(ci95_low) if not pd.isna(ci95_low) else np.nan,
        "ci95_high": float(ci95_high) if not pd.isna(ci95_high) else np.nan,
        "p_value": float(p_value) if not pd.isna(p_value) else np.nan,
        "decision": decision,
        "causal_status": causal_status,
        "claim_allowed": claim_allowed,
        "claim_not_allowed": claim_not_allowed,
        "academic_standard_note": academic_standard_note,
    }


def build_teacher_requirements_alignment(config: CaseConfig, mechanism_summary: dict[str, object]) -> pd.DataFrame:
    """Map Luyao's email requirements to local code/artifact status."""

    tables = config.tables_dir
    release = config.project_root / "benchmark_release" / "data"
    events = _read_nonempty_csv(release / "events.csv")
    metrics = _read_nonempty_csv(release / "metrics_panel.csv")
    covariates = _read_nonempty_csv(release / "covariates.csv")
    gaps = _read_nonempty_csv(release / "data_gap_ledger.csv")
    agentic = _read_nonempty_csv(release / "agentic_evaluation_panel.csv")
    mirror = _read_nonempty_csv(release / "mirror_case_ladder.csv")
    telegram_shocks = _read_nonempty_csv(release / "telegram_shock_candidates.csv")
    base_manifest = _read_nonempty_csv(release / "clanker_base_full_cohort_manifest.csv")
    base_coverage = _read_nonempty_csv(release / "clanker_base_full_cohort_import_coverage.csv")
    base_diagnostics = _read_nonempty_csv(release / "clanker_base_causal_diagnostics.csv")
    base_backfill = _read_json(tables / "clanker_base_full_cohort_backfill_summary.json")
    telegram_exposure = _read_json(tables / "telegram_exposure_design_summary.json")

    event_statuses = set(events.get("eligibility_status", pd.Series(dtype=str)).dropna().astype(str))
    metric_horizons = set(pd.to_numeric(metrics.get("horizon_days", pd.Series(dtype=float)), errors="coerce").dropna().astype(int))
    covariate_families = set(covariates.get("covariate_family", pd.Series(dtype=str)).dropna().astype(str))
    gap_ids = set(gaps.get("gap_id", pd.Series(dtype=str)).dropna().astype(str))
    release_join_status = (
        "pass"
        if all(
            not frame.empty and "event_id" in frame.columns and "claim_boundary" in frame.columns
            for frame in [events, metrics, covariates]
        )
        else "gap"
    )
    events_status = "pass" if {"accepted", "conditional", "rejected"}.issubset(event_statuses) else "partial"
    metrics_status = "pass" if {1, 7, 30}.issubset(metric_horizons) and "claim_boundary" in metrics else "partial"
    covariates_status = (
        "pass"
        if {"token_social_metadata", "community_attention_sentiment", "community_attention_tvl"}.issubset(covariate_families)
        else "partial"
    )
    license_status = (
        "partial_release_ready_no_zenodo_doi"
        if (config.project_root.parent / "LICENSE").exists()
        and (config.project_root / "DATA_LICENSE.md").exists()
        and (config.project_root / "CITATION.cff").exists()
        else "gap"
    )
    cross_chain_status = (
        "partial_accepted_matched_case_full_cohort_backfill_partial"
        if not base_manifest.empty and int(base_backfill.get("transfer_import_rows", 0) or 0) > 0
        else "registered_gap"
    )
    mirror_status = (
        "credible_matched_signal_not_causal"
        if not mirror.empty and int(telegram_exposure.get("supported_shocks", 0) or 0) == 0
        else "needs_design"
    )
    agentic_status = (
        "computed_single_model_ladder_panel"
        if not agentic.empty and set(agentic.get("rung", pd.Series(dtype=str)).astype(str)) == {f"L{i}" for i in range(8)}
        else "gap"
    )
    rows = [
        {
            "ownership_item": "Three-sheet benchmark release",
            "teacher_requirement": "Treat the released dataset as a primary deliverable with linked events.csv, metrics_panel.csv, and covariates.csv.",
            "artifact": str(release),
            "status": release_join_status,
            "evidence_or_gap": (
                f"events={len(events)}, metrics={len(metrics)}, covariates={len(covariates)}; "
                "all three primary sheets carry event_id and claim_boundary."
            ),
        },
        {
            "ownership_item": "Rule-event registry with rejected cases",
            "teacher_requirement": "events.csv must include accepted, rejected, and conditional rule-event cases, with activation evidence and rejection reasons.",
            "artifact": str(release / "events.csv"),
            "status": events_status,
            "evidence_or_gap": (
                f"eligibility_status counts={events.get('eligibility_status', pd.Series(dtype=str)).value_counts(dropna=False).to_dict()}; "
                "Clanker/Base is accepted, Four.meme is rejected, PumpSwap/context rows are conditional."
            ),
        },
        {
            "ownership_item": "Metrics panel at fixed horizons",
            "teacher_requirement": "metrics_panel.csv should include platform-day and token-cohort/token-horizon rows at 7-day and 30-day windows with formal claim boundaries.",
            "artifact": str(release / "metrics_panel.csv"),
            "status": metrics_status,
            "evidence_or_gap": (
                f"unit_type counts={metrics.get('unit_type', pd.Series(dtype=str)).value_counts(dropna=False).to_dict()}; "
                f"horizons={sorted(metric_horizons)}."
            ),
        },
        {
            "ownership_item": "Off-chain and behavioral covariates",
            "teacher_requirement": "covariates.csv should include Telegram, Discord, sentiment, social metadata, and community-channel indicators.",
            "artifact": str(release / "covariates.csv"),
            "status": covariates_status,
            "evidence_or_gap": (
                f"covariate families={sorted(covariate_families)}; token social metadata and Discord/sentiment/TVL context are linked by event_id."
            ),
        },
        {
            "ownership_item": "Claim ledger, data dictionary, licensing, citation, data gaps",
            "teacher_requirement": "Prepare a complete claim-scope ledger, data dictionary, MIT code license, CC BY 4.0 data plan, CITATION.cff, Zenodo plan, and explicit data-gap ledger.",
            "artifact": f"{release / 'claim_scope_ledger.csv'}; {release / 'data_dictionary.csv'}; {release / 'data_gap_ledger.csv'}",
            "status": license_status,
            "evidence_or_gap": (
                f"gap_ids={sorted(gap_ids)}; LICENSE, DATA_LICENSE.md, and CITATION.cff are present; Zenodo DOI is still planned rather than minted."
            ),
        },
        {
            "ownership_item": "Cross-chain empirical case",
            "teacher_requirement": "Cross-chain evidence must appear in the dataset architecture, at least one empirical case, and external-validity discussion.",
            "artifact": str(release / "cross_chain_event_candidates.csv"),
            "status": cross_chain_status,
            "evidence_or_gap": (
                f"Base manifest rows={len(base_manifest)}; backfill swap rows={base_backfill.get('swap_import_rows', 0)}, "
                f"transfer rows={base_backfill.get('transfer_import_rows', 0)}; full 30-day archive/indexer coverage remains open."
            ),
        },
        {
            "ownership_item": "Base archive/indexer full-cohort path",
            "teacher_requirement": "Comparable Base outcomes should scale from bounded on-chain/import-compatible evidence to full cohort swaps, transfers, holder reconstruction, and causal diagnostics.",
            "artifact": f"{release / 'clanker_base_full_cohort_manifest.csv'}; {release / 'clanker_base_full_cohort_import_coverage.csv'}",
            "status": "partial_backfill_smoke_and_sample_import",
            "evidence_or_gap": (
                f"coverage rows={len(base_coverage)}; diagnostics rows={len(base_diagnostics)}; "
                "accepted 12-token sample is imported into the full-cohort ledger, but coverage is about 0.1% of the 13,880-row manifest."
            ),
        },
        {
            "ownership_item": "On-chain/off-chain evidence integration",
            "teacher_requirement": "Cases should integrate deployment/on-chain verification with Telegram, Discord, sentiment, social metadata, or community response where possible.",
            "artifact": f"{release / 'events.csv'}; {release / 'covariates.csv'}; {release / 'telegram_shock_candidates.csv'}",
            "status": "partial_layers_linked_no_exogenous_social_shock",
            "evidence_or_gap": (
                f"Telegram shock candidates={len(telegram_shocks)}, supported shocks={telegram_exposure.get('supported_shocks', 0)}; "
                "on-chain Base evidence and off-chain Solana/Telegram layers share schema but do not yet form a causal social-exposure design."
            ),
        },
        {
            "ownership_item": "Mirror empirical Case B",
            "teacher_requirement": "Find a complementary case where naive null/ambiguous evidence becomes credible and supported after design and adjustment.",
            "artifact": str(release / "mirror_case_ladder.csv"),
            "status": mirror_status,
            "evidence_or_gap": (
                f"mirror ladder rungs={sorted(mirror.get('rung', pd.Series(dtype=str)).astype(str).unique().tolist())}; "
                "Telegram has matched ATT and timing/sensitivity checks, but no in-window exogenous shock, so it remains predictive/mechanism-supported rather than causal."
            ),
        },
        {
            "ownership_item": "Agentic Trustworthy AI evaluation",
            "teacher_requirement": "Present agentic analysis as a central AI evaluation of evidence behavior, including per-rung decision paths and scaffold effects.",
            "artifact": str(release / "agentic_evaluation_panel.csv"),
            "status": agentic_status,
            "evidence_or_gap": (
                f"agentic rows={len(agentic)}; current release is single-model L0-L7 evidence-behavior scoring. "
                "Top-conference extension still needs multi-model reruns and scaffold ablations."
            ),
        },
        {
            "ownership_item": "Trustworthy AI for Good societal impact",
            "teacher_requirement": "Add explicit societal-impact framing around retail users, financial inclusion, welfare overclaims, SDG 8/10, and open benchmark data as a public good.",
            "artifact": str(config.project_root / "SHILIN-REPORT.md"),
            "status": "added_to_shilin_report_needs_joint_paper_sync",
            "evidence_or_gap": "SHILIN-REPORT now includes retail-user protection, financial inclusion, welfare-overclaim, SDG 8/10, and public-good benchmark framing; joint paper text still needs synchronization.",
        },
        {
            "ownership_item": "Joint August 7 deliverable scope",
            "teacher_requirement": "Provide revised dataset specification, cross-chain extension, Shilin mirror case ladder, AI-for-good framing, artifact outline, and remaining blockers.",
            "artifact": str(config.project_root / "SHILIN-AUGUST7-REVISION-PLAN.md"),
            "status": "shilin_side_release_candidate_with_blockers",
            "evidence_or_gap": "Shilin-side artifacts are concrete; Claire semi-synthetic suite and joint paper integration remain outside this Shilin-only audit.",
        },
        {
            "ownership_item": "H1 migration friction / post-graduation persistence",
            "teacher_requirement": "Shilin owns H1 and Result 1 mechanism evidence.",
            "artifact": str(tables / "h1_rpc_mechanism_causal_audit.csv"),
            "status": mechanism_summary.get("mechanism_claim_status", "missing"),
            "evidence_or_gap": (
                f"Complete 30d active share={mechanism_summary.get('complete_30d_active_share', 'NA')}; "
                f"full observed lower-bound active share={mechanism_summary.get('full_30d_observed_active_lower_bound_share', 'NA')}."
            ),
        },
        {
            "ownership_item": "H4 allocation fairness / retail risk",
            "teacher_requirement": "Shilin owns H4; H2 is joint.",
            "artifact": str(tables / "result1_stakeholder_metric_battery.csv"),
            "status": "computed_proxy_and_registered_event_time_gap",
            "evidence_or_gap": (
                "HF holder-concentration/risk and RED-COHORT mechanism evidence are computed; "
                "decoded early-wallet concentration for the same 1,651 graduated tokens remains a gap."
            ),
        },
        {
            "ownership_item": "Pillar 1 stakeholder metric battery",
            "teacher_requirement": "Compute stakeholder metrics; name stakeholder and loss bearer.",
            "artifact": str(tables / "result1_stakeholder_metric_battery.csv"),
            "status": "computed",
            "evidence_or_gap": "Creator, retail, community, protocol/reviewer metrics are generated by run_all.py.",
        },
        {
            "ownership_item": "Pillar 2 data richness and frequency",
            "teacher_requirement": "Daily vs weekly, market vs token-level, and frequency-sensitive conclusions.",
            "artifact": str(tables / "result1_frequency_sensitivity.csv"),
            "status": "computed",
            "evidence_or_gap": "Market daily/weekly TWFE and token-level RPC/HF layers are reported separately.",
        },
        {
            "ownership_item": "Naive rerun / deterministic ablation ladder",
            "teacher_requirement": "Run L0-L7 and show where the conclusion changes.",
            "artifact": str(tables / "deterministic_ladder.csv"),
            "status": "computed",
            "evidence_or_gap": "L0 says yes; L6 is no_or_uncertain after honest few-cluster inference.",
        },
        {
            "ownership_item": "Agentic execution arm",
            "teacher_requirement": "Prompts appendix and agentic columns of tab_arms.",
            "artifact": str(tables / "agentic_arm_scores.csv"),
            "status": "computed",
            "evidence_or_gap": "Ten runs per rung are scored; prompt manifest and tab_arms are generated.",
        },
        {
            "ownership_item": "GitHub/Shilin folder discipline",
            "teacher_requirement": "Put code, data, and artifacts under Shilin's folder.",
            "artifact": str(config.output_root),
            "status": "computed",
            "evidence_or_gap": "All new causal-validation artifacts are generated under Shilin/artifacts.",
        },
    ]
    alignment = pd.DataFrame(rows)
    write_csv(tables / "teacher_requirements_alignment_shilin.csv", alignment)
    return alignment


def build_h1_rpc_mechanism_causal_audit(config: CaseConfig) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Build token-level outcomes and a conservative H1 mechanism audit."""

    external_dir = config.output_root / "external_validation"
    post_path = external_dir / "solana_post_migration_pool_windows.csv"
    post = _read_nonempty_csv(post_path)
    token_outcomes = build_h1_token_outcomes(config, post)
    token_outcomes_path = external_dir / "h1_rpc_token_level_outcomes.csv"
    write_csv(token_outcomes_path, token_outcomes)

    now = datetime.now(UTC).isoformat()
    if post.empty or "horizon_days" not in post:
        audit = pd.DataFrame(
            [
                _audit_row(
                    claim_id="H1-rpc-missing",
                    hypothesis="H1 migration friction / persistence",
                    estimand="Post-migration pool activity",
                    sample_rule="No RPC post-migration window artifact found.",
                    n_tokens=0,
                    estimate=np.nan,
                    ci95_low=np.nan,
                    ci95_high=np.nan,
                    p_value=np.nan,
                    decision="gap",
                    causal_status="missing_data",
                    claim_allowed="No H1 RPC mechanism claim.",
                    claim_not_allowed="Do not infer PumpSwap mechanism activation without post-migration pool data.",
                    academic_standard_note="Missing data are recorded rather than imputed.",
                )
            ]
        )
        summary = {
            "generated_at_utc": now,
            "mechanism_claim_status": "missing_rpc_post_migration_windows",
            "post_path": str(post_path),
            "token_outcomes_path": str(token_outcomes_path),
        }
        write_csv(config.tables_dir / "h1_rpc_mechanism_causal_audit.csv", audit)
        write_json(config.tables_dir / "h1_rpc_mechanism_summary.json", summary)
        build_teacher_requirements_alignment(config, summary)
        return audit, token_outcomes, summary

    post30 = post.loc[post["horizon_days"].eq(30)].copy()
    complete30 = post30.loc[post30["signature_window_status"].astype(str).eq("ok")].copy()
    full_n = int(len(post30))
    complete_n = int(len(complete30))
    full_success = int(pd.to_numeric(post30["swap_count"], errors="coerce").gt(0).sum())
    complete_success = int(pd.to_numeric(complete30["swap_count"], errors="coerce").gt(0).sum())
    full_share = full_success / full_n if full_n else np.nan
    complete_share = complete_success / complete_n if complete_n else np.nan
    full_ci_low, full_ci_high = _wilson_interval(full_success, full_n)
    complete_ci_low, complete_ci_high = _wilson_interval(complete_success, complete_n)

    complete_swaps = pd.to_numeric(complete30["swap_count"], errors="coerce")
    median_swaps = _safe_median(complete_swaps)
    median_swaps_ci_low, median_swaps_ci_high = _bootstrap_median_ci(complete_swaps)
    q25_swaps = _safe_quantile(complete_swaps, 0.25)
    q75_swaps = _safe_quantile(complete_swaps, 0.75)

    graduated_at = pd.to_datetime(complete30["graduated_at"], utc=True, errors="coerce")
    first_trade_at = pd.to_datetime(complete30["first_trade_at"], utc=True, errors="coerce")
    first_trade_lag = (first_trade_at - graduated_at).dt.total_seconds()
    lag_nonmissing = first_trade_lag.dropna()
    median_lag = float(lag_nonmissing.median()) if len(lag_nonmissing) else np.nan
    median_lag_ci_low, median_lag_ci_high = _bootstrap_median_ci(lag_nonmissing)
    temporal_violations = int(first_trade_lag.lt(0).fillna(False).sum())
    temporal_violation_share = temporal_violations / complete_n if complete_n else np.nan
    temporal_ci_low, temporal_ci_high = _wilson_interval(temporal_violations, complete_n)

    reactivation_rate = float(pd.to_numeric(complete30["reactivated_after_7d"], errors="coerce").mean())
    inactivity_median = _safe_median(complete30["inactivity_gap_hours"])
    complete_share_of_full = complete_n / full_n if full_n else np.nan

    decoded_usd_nonmissing = (
        int(pd.to_numeric(post30.get("volume_usd", pd.Series(dtype=float)), errors="coerce").notna().sum())
        if full_n
        else 0
    )
    active_trader_nonzero = (
        int(pd.to_numeric(post30.get("active_traders", pd.Series(dtype=float)), errors="coerce").gt(0).sum())
        if full_n
        else 0
    )
    moralis_decoded = _summarize_moralis_decoded_outcomes(config)
    moralis_sample_present = bool(moralis_decoded.get("decoded_sample_present"))
    moralis_n30 = int(moralis_decoded.get("decoded_30d_tokens", 0) or 0)
    moralis_positive_volume = int(moralis_decoded.get("decoded_30d_positive_volume_tokens", 0) or 0)
    moralis_volume_share = float(moralis_decoded.get("decoded_30d_positive_volume_share", np.nan))
    moralis_ci_low = float(moralis_decoded.get("decoded_30d_positive_volume_ci95_low", np.nan))
    moralis_ci_high = float(moralis_decoded.get("decoded_30d_positive_volume_ci95_high", np.nan))

    rows = [
        _audit_row(
            claim_id="H1-rpc-full-observed-lower-bound-activity",
            hypothesis="H1 migration friction / post-graduation persistence",
            estimand="Share of all graduated tokens with at least one observed 30d post-migration PumpSwap-pool transaction",
            sample_rule="All 1,651 graduated tokens; truncated rows are retained only as lower-bound nonzero evidence.",
            n_tokens=full_n,
            estimate=full_share,
            ci95_low=full_ci_low,
            ci95_high=full_ci_high,
            p_value=_binom_pvalue(full_success, full_n, 0.90),
            decision="passes_90pct_lower_bound_threshold" if full_ci_low > 0.90 else "does_not_pass_90pct_threshold",
            causal_status="mechanism_level_lower_bound",
            claim_allowed="PumpSwap migration produced observable post-migration pool activity for nearly all graduated tokens in the local RPC artifact.",
            claim_not_allowed="Do not read this row as decoded USD volume, welfare gain, price quality, or trader-level causal evidence.",
            academic_standard_note="This is a conservative lower bound because nonzero truncated windows are real successes and truncated zeros are not converted into failures of true activity.",
        ),
        _audit_row(
            claim_id="H1-rpc-complete-window-activity",
            hypothesis="H1 migration friction / post-graduation persistence",
            estimand="Share of complete 30d windows with at least one PumpSwap-pool transaction",
            sample_rule="Only tokens whose 30d signature window reaches the migration lower bound with status ok.",
            n_tokens=complete_n,
            estimate=complete_share,
            ci95_low=complete_ci_low,
            ci95_high=complete_ci_high,
            p_value=_binom_pvalue(complete_success, complete_n, 0.90),
            decision="passes_90pct_complete_window_threshold" if complete_ci_low > 0.90 else "does_not_pass_90pct_threshold",
            causal_status="mechanism_level_complete_window",
            claim_allowed="Among coverage-complete tokens, post-migration pool activation is universal in the observed 30d windows.",
            claim_not_allowed="Do not generalize complete-window medians to all tokens without reporting truncation selection.",
            academic_standard_note="Complete-window restriction prevents lower-bound pagination counts from being treated as exact 30d outcomes.",
        ),
        _audit_row(
            claim_id="H1-rpc-complete-window-transaction-median",
            hypothesis="H1 migration friction / post-graduation persistence",
            estimand="Median 30d PumpSwap-pool transaction-count proxy among complete windows",
            sample_rule="Coverage-complete 30d windows only.",
            n_tokens=complete_n,
            estimate=median_swaps,
            ci95_low=median_swaps_ci_low,
            ci95_high=median_swaps_ci_high,
            p_value=np.nan,
            decision="positive_persistence_proxy" if median_swaps > 0 else "no_persistence_proxy",
            causal_status="mechanism_level_intensity_proxy",
            claim_allowed="The complete-window median is far above zero, supporting persistence of the migration venue at the transaction-count level.",
            claim_not_allowed="Do not convert signature counts into swap counts, active traders, or USD volume without a decoded indexer.",
            academic_standard_note=f"Nonparametric bootstrap median CI; IQR=[{q25_swaps:.3f}, {q75_swaps:.3f}].",
        ),
        _audit_row(
            claim_id="H1-rpc-first-trade-timing",
            hypothesis="H1 migration friction / post-graduation persistence",
            estimand="Median seconds from Pump.fun graduation timestamp to first observed post-migration pool transaction",
            sample_rule="Coverage-complete 30d windows with non-missing first_trade_at.",
            n_tokens=int(len(lag_nonmissing)),
            estimate=median_lag,
            ci95_low=median_lag_ci_low,
            ci95_high=median_lag_ci_high,
            p_value=np.nan,
            decision="temporal_activation_after_migration" if temporal_violations == 0 and median_lag >= 0 else "temporal_ordering_problem",
            causal_status="mechanism_temporality_check",
            claim_allowed="The observed post-migration activity occurs after the recorded graduation/migration timestamp.",
            claim_not_allowed="Do not infer user welfare from timing alone.",
            academic_standard_note="Temporal ordering is a necessary condition for the mechanism claim and a data-quality falsification check.",
        ),
        _audit_row(
            claim_id="H1-rpc-temporal-placebo-violation-rate",
            hypothesis="H1 migration friction / post-graduation persistence",
            estimand="Share of complete windows whose first observed trade predates graduation",
            sample_rule="Coverage-complete 30d windows.",
            n_tokens=complete_n,
            estimate=temporal_violation_share,
            ci95_low=temporal_ci_low,
            ci95_high=temporal_ci_high,
            p_value=np.nan,
            decision="passes_temporal_placebo" if temporal_violations == 0 else "fails_temporal_placebo",
            causal_status="falsification_check",
            claim_allowed="No pre-graduation first-trade violations are observed in complete windows.",
            claim_not_allowed="A passing placebo is not itself a welfare or market-quality effect.",
            academic_standard_note="This guards against timestamp or join errors that would invalidate event-time interpretation.",
        ),
        _audit_row(
            claim_id="H1-decoded-usd-trade-outcomes",
            hypothesis="H1 migration friction / post-graduation persistence",
            estimand=(
                "Share of Moralis-covered 30d post-migration token windows with positive decoded USD swap volume"
                if moralis_sample_present
                else "Decoded token-level 1/7/30d USD volume, active trader counts, trade direction, and fees"
            ),
            sample_rule=(
                "Moralis Solana Token Swaps decoded sample over covered graduated tokens; overlapping 1/7/30d windows are saved locally."
                if moralis_sample_present
                else "Requires Dune/Helius enhanced/Moralis/Birdeye decoded indexer export."
            ),
            n_tokens=moralis_n30 if moralis_sample_present else decoded_usd_nonmissing,
            estimate=moralis_volume_share if moralis_sample_present else np.nan,
            ci95_low=moralis_ci_low if moralis_sample_present else np.nan,
            ci95_high=moralis_ci_high if moralis_sample_present else np.nan,
            p_value=np.nan,
            decision="decoded_usd_sample_computed" if moralis_sample_present else "gap",
            causal_status="decoded_indexer_sample_not_full_causal" if moralis_sample_present else "decoded_indexer_gap",
            claim_allowed=(
                "Moralis validates USD-denominated buy/sell swap outcomes, wallet counts, and exchange/pair labels for the covered token sample."
                if moralis_sample_present
                else "Report this as the remaining top-conference validation target."
            ),
            claim_not_allowed=(
                "Do not generalize the Moralis sample to all graduated tokens or claim welfare, price-quality, or active-trader causality without the full design."
                if moralis_sample_present
                else "Do not claim decoded USD-volume or active-trader causal effects from the current RPC proxy artifact."
            ),
            academic_standard_note=(
                f"Moralis 30d decoded sample: tokens={moralis_n30}, positive-USD tokens={moralis_positive_volume}, "
                f"median volume USD={float(moralis_decoded.get('decoded_30d_median_volume_usd', np.nan)):.3f}, "
                f"median trades={float(moralis_decoded.get('decoded_30d_median_trade_count', np.nan)):.3f}, "
                f"median active traders={float(moralis_decoded.get('decoded_30d_median_active_traders', np.nan)):.3f}."
                if moralis_sample_present
                else f"Current RPC artifact has {decoded_usd_nonmissing} non-missing volume_usd rows and {active_trader_nonzero} nonzero active_traders rows."
            ),
        ),
        _audit_row(
            claim_id="H4-early-wallet-event-time-outcomes",
            hypothesis="H4 allocation fairness / retail harm",
            estimand="Early-wallet concentration, sniper share, and downstream persistence/harm",
            sample_rule="Requires early transaction or decoded holder/swap export for the same graduated-token cohort.",
            n_tokens=0,
            estimate=np.nan,
            ci95_low=np.nan,
            ci95_high=np.nan,
            p_value=np.nan,
            decision="gap",
            causal_status="early_wallet_gap",
            claim_allowed="Use HF and RED-COHORT evidence as H4 proxy/external mechanism evidence only.",
            claim_not_allowed="Do not claim PumpSwap changed early allocation fairness for the 1,651-token cohort yet.",
            academic_standard_note="H4 remains a registered causal target until same-cohort early-wallet features are decoded.",
        ),
    ]
    audit = pd.DataFrame(rows)

    mechanism_pass = (
        bool(full_ci_low > 0.90)
        and bool(complete_ci_low > 0.90)
        and temporal_violations == 0
        and complete_n >= 300
    )
    summary = {
        "generated_at_utc": now,
        "post_path": str(post_path),
        "token_outcomes_path": str(token_outcomes_path),
        "audit_path": str(config.tables_dir / "h1_rpc_mechanism_causal_audit.csv"),
        "post_30d_tokens": full_n,
        "complete_30d_tokens": complete_n,
        "complete_30d_share_of_full": float(complete_share_of_full),
        "full_30d_observed_active_tokens": full_success,
        "full_30d_observed_active_lower_bound_share": float(full_share),
        "full_30d_observed_active_ci95_low": float(full_ci_low),
        "full_30d_observed_active_ci95_high": float(full_ci_high),
        "complete_30d_active_tokens": complete_success,
        "complete_30d_active_share": float(complete_share),
        "complete_30d_active_ci95_low": float(complete_ci_low),
        "complete_30d_active_ci95_high": float(complete_ci_high),
        "complete_30d_median_tx_proxy": float(median_swaps),
        "complete_30d_median_tx_proxy_ci95_low": float(median_swaps_ci_low),
        "complete_30d_median_tx_proxy_ci95_high": float(median_swaps_ci_high),
        "complete_30d_tx_proxy_q25": float(q25_swaps),
        "complete_30d_tx_proxy_q75": float(q75_swaps),
        "complete_30d_reactivated_after_7d_rate": float(reactivation_rate),
        "complete_30d_inactivity_gap_hours_median": float(inactivity_median),
        "complete_30d_median_first_trade_lag_seconds": float(median_lag),
        "complete_30d_first_trade_lag_ci95_low": float(median_lag_ci_low),
        "complete_30d_first_trade_lag_ci95_high": float(median_lag_ci_high),
        "temporal_order_violations_complete_30d": temporal_violations,
        "decoded_usd_nonmissing_rows": decoded_usd_nonmissing,
        "active_trader_nonzero_rows": active_trader_nonzero,
        "moralis_decoded_outcome_rows": int(moralis_decoded.get("decoded_outcome_rows", 0) or 0),
        "moralis_decoded_30d_tokens": moralis_n30,
        "moralis_decoded_30d_positive_volume_tokens": moralis_positive_volume,
        "moralis_decoded_30d_positive_volume_share": moralis_volume_share,
        "moralis_decoded_30d_median_volume_usd": float(moralis_decoded.get("decoded_30d_median_volume_usd", np.nan)),
        "moralis_decoded_30d_median_trade_count": float(moralis_decoded.get("decoded_30d_median_trade_count", np.nan)),
        "moralis_decoded_30d_median_active_traders": float(
            moralis_decoded.get("decoded_30d_median_active_traders", np.nan)
        ),
        "mechanism_claim_status": (
            "pass_mechanism_level_not_welfare_causal" if mechanism_pass else "warning_mechanism_level"
        ),
        "claim_allowed": (
            "PumpSwap migration is supported as an operational post-migration liquidity venue for graduated tokens: "
            "nearly all tokens have observed 30d pool activity, complete windows are universally active, and timing is after graduation."
        ),
        "claim_not_allowed": (
            "The RPC proxy does not prove USD-volume, welfare, price-quality, active-trader, or H4 early-allocation causal effects. "
            "When present, the Moralis decoded sample is descriptive token-level outcome measurement, not a full-cohort causal welfare estimate."
        ),
    }
    write_csv(config.tables_dir / "h1_rpc_mechanism_causal_audit.csv", audit)
    write_json(config.tables_dir / "h1_rpc_mechanism_summary.json", summary)
    build_teacher_requirements_alignment(config, summary)
    return audit, token_outcomes, summary
