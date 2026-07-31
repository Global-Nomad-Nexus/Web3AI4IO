"""Stakeholder metric battery for Shilin's Result 1."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .io import CaseConfig, read_hf_pump_sentiment, read_optional_csv, read_red_pump_outcomes, write_csv, write_json


STATUS_READY = "computed"
STATUS_PROXY = "computed_proxy"
STATUS_EXTENSION = "computed_extension"
STATUS_EXTERNAL = "registered_external_validation"
STATUS_EXTERNAL_SAMPLE = "computed_external_validation_sample"


def _safe_rate(numer: float, denom: float) -> float:
    return float(numer / denom) if denom else np.nan


def summarize_red_pump(config: CaseConfig) -> dict[str, object]:
    usecols = [
        "mint",
        "outcome",
        "graduated",
        "minutes_to_outcome_seen",
        "minutes_to_outcome_chain",
        "initial_market_cap_sol",
        "has_twitter",
        "has_website",
        "has_telegram",
        "has_any_social",
        "social_count",
        "description_length",
        "launch_day",
    ]
    df = read_red_pump_outcomes(config, usecols=usecols)
    total = int(len(df))
    graduated = int(df["graduated"].sum())
    timeout = int((df["outcome"] == "TIMEOUT").sum())
    grad_df = df.loc[df["graduated"].eq(1)].copy()
    no_social = df.loc[df["has_any_social"].eq(0)]
    any_social = df.loc[df["has_any_social"].eq(1)]
    by_social = {
        "no_social_graduation_rate": _safe_rate(no_social["graduated"].sum(), len(no_social)),
        "any_social_graduation_rate": _safe_rate(any_social["graduated"].sum(), len(any_social)),
    }
    by_telegram = (
        df.groupby("has_telegram")["graduated"].agg(["count", "sum", "mean"]).reset_index()
        if "has_telegram" in df
        else pd.DataFrame()
    )
    initial_mcap = pd.to_numeric(df["initial_market_cap_sol"], errors="coerce")
    return {
        "total_tokens": total,
        "graduated_tokens": graduated,
        "timeout_tokens": timeout,
        "graduation_rate": _safe_rate(graduated, total),
        "timeout_incidence_per_1000": _safe_rate(timeout, total) * 1000,
        "median_minutes_to_graduation_seen": float(pd.to_numeric(grad_df["minutes_to_outcome_seen"], errors="coerce").median()),
        "median_minutes_to_graduation_chain": float(pd.to_numeric(grad_df["minutes_to_outcome_chain"], errors="coerce").median()),
        "median_initial_market_cap_sol": float(initial_mcap.median()),
        "p90_initial_market_cap_sol": float(initial_mcap.quantile(0.90)),
        **by_social,
        "telegram_graduation_rate": float(by_telegram.loc[by_telegram["has_telegram"].eq(1), "mean"].iloc[0])
        if len(by_telegram.loc[by_telegram["has_telegram"].eq(1)])
        else np.nan,
        "no_telegram_graduation_rate": float(by_telegram.loc[by_telegram["has_telegram"].eq(0), "mean"].iloc[0])
        if len(by_telegram.loc[by_telegram["has_telegram"].eq(0)])
        else np.nan,
    }


def summarize_hf_pump_sentiment(config: CaseConfig) -> dict[str, object]:
    raw = read_hf_pump_sentiment(config, latest_per_mint=False)
    df = read_hf_pump_sentiment(config, latest_per_mint=True)
    data = df.copy()
    top10_raw = pd.to_numeric(data["top10_holder_pct"], errors="coerce")
    data["top10_holder_pct_clean"] = top10_raw.clip(0, 100)
    data["invalid_top10_gt100"] = top10_raw.gt(100)
    data["high_concentration"] = (
        data["holder_concentration"].astype(str).isin(["whale_dominated", "concentrated"])
        | data["top10_holder_pct_clean"].ge(80)
    ).astype(int)
    data["high_or_critical_risk"] = data["risk_level"].astype(str).isin(["high", "critical"]).astype(int)
    data["active_market"] = (
        pd.to_numeric(data["volume_24h"], errors="coerce").gt(0)
        & pd.to_numeric(data["liquidity"], errors="coerce").gt(0)
    ).astype(int)
    data["completed_bonding"] = pd.to_numeric(data["bonding_progress"], errors="coerce").ge(100).astype(int)
    treated = data.loc[data["high_concentration"].eq(1), "high_or_critical_risk"]
    control = data.loc[data["high_concentration"].eq(0), "high_or_critical_risk"]
    risk_diff = float(treated.mean() - control.mean()) if len(treated) and len(control) else np.nan
    return {
        "rows": int(len(data)),
        "raw_snapshot_rows": int(len(raw)),
        "unique_mints": int(data["mint"].nunique()),
        "dedupe_rule": "latest snapshot per mint, sorted by snapshot_at",
        "active_market_rate": float(data["active_market"].mean()),
        "completed_bonding_rate": float(data["completed_bonding"].mean()),
        "median_volume_24h": float(pd.to_numeric(data["volume_24h"], errors="coerce").median()),
        "median_liquidity": float(pd.to_numeric(data["liquidity"], errors="coerce").median()),
        "median_holder_count": float(pd.to_numeric(data["holder_count"], errors="coerce").median()),
        "median_top10_holder_pct_clean": float(data["top10_holder_pct_clean"].median()),
        "p90_top10_holder_pct_clean": float(data["top10_holder_pct_clean"].quantile(0.90)),
        "high_concentration_rate": float(data["high_concentration"].mean()),
        "high_or_critical_risk_rate": float(data["high_or_critical_risk"].mean()),
        "risk_rate_difference_high_concentration": risk_diff,
        "invalid_top10_gt100_rows": int(data["invalid_top10_gt100"].sum()),
        "source_note": "HuggingFace Pumpdotstudio/pump-fun-sentiment-100k local sample; raw snapshots are deduplicated to one latest record per mint for token-level summaries.",
    }


def metric_rows_from_summary(config: CaseConfig, red: dict[str, object]) -> list[dict[str, object]]:
    hf = summarize_hf_pump_sentiment(config)
    external_summary_path = config.tables_dir / "external_validation_summary.json"
    external_summary = {}
    if external_summary_path.exists():
        external_summary = json.loads(external_summary_path.read_text(encoding="utf-8"))
    dune_summary_path = config.tables_dir / "dune_indexer_export_summary.json"
    dune_summary = {}
    if dune_summary_path.exists():
        dune_summary = json.loads(dune_summary_path.read_text(encoding="utf-8"))
    moralis_summary_path = config.tables_dir / "moralis_decoded_outcomes_summary.json"
    moralis_summary = {}
    if moralis_summary_path.exists():
        moralis_summary = json.loads(moralis_summary_path.read_text(encoding="utf-8"))
    free_public_summary_path = config.tables_dir / "free_public_data_summary.json"
    free_public_summary = {}
    if free_public_summary_path.exists():
        free_public_summary = json.loads(free_public_summary_path.read_text(encoding="utf-8"))
    red_cohort_stats = free_public_summary.get("red_cohort", {}).get("descriptive_stats", {})
    red_cohort_overlap = free_public_summary.get("red_cohort_red_pump_overlap", {})
    graduated_path = config.source_path("red_pump_graduated_for_dune", required=False)
    graduated_export_rows = np.nan
    if graduated_path.exists():
        graduated_export_rows = len(pd.read_csv(graduated_path, usecols=["mint"]))
    dune_tokens = dune_summary.get("tokens_in_query", graduated_export_rows)
    if pd.isna(dune_tokens):
        dune_tokens = np.nan
        dune_tokens_label = "missing"
    else:
        dune_tokens = int(dune_tokens)
        dune_tokens_label = str(dune_tokens)
    dune_status = str(dune_summary.get("status", ""))
    dune_computed = dune_status == "computed_dune_indexer_exports"
    dune_post_rows = dune_summary.get("outputs", {}).get("post_migration", {}).get("rows", 0)
    try:
        dune_post_rows = int(dune_post_rows)
    except (TypeError, ValueError):
        dune_post_rows = 0
    dune_partial = (
        dune_status in {"computed_dune_indexer_exports_partial", "stopped_chunked_dune_indexer_exports_partial"}
        and dune_post_rows > 0
    )
    external_tokens = external_summary.get("post_migration_tokens", np.nan)
    external_median_tx = external_summary.get("median_complete_30d_pool_tx_count", np.nan)
    external_complete_share = external_summary.get("share_30d_post_windows_complete", np.nan)
    external_active_share = external_summary.get("share_complete_30d_pool_activity", np.nan)
    external_truncated_share = external_summary.get("share_30d_post_windows_potentially_truncated", np.nan)
    external_truncated_zero = external_summary.get("post_30d_truncated_zero_observed_tokens", np.nan)
    moralis_unique_swaps = int(moralis_summary.get("unique_decoded_swap_rows", 0) or 0)
    moralis_30d_tokens = int(moralis_summary.get("decoded_30d_tokens_with_swaps", 0) or 0)
    moralis_median_volume = moralis_summary.get("decoded_30d_median_volume_usd", np.nan)
    moralis_median_trades = moralis_summary.get("decoded_30d_median_trade_count", np.nan)
    moralis_status = str(moralis_summary.get("status", ""))
    moralis_computed = moralis_unique_swaps > 0 and moralis_30d_tokens > 0

    lpm = read_optional_csv(config.legacy_table("red_pump_social_lpm_results.csv", required=False))
    discord = read_optional_csv(config.legacy_table("discord_tvl_model_results.csv", required=False))
    rwa = read_optional_csv(config.legacy_table("rwa_protocol_snapshot_model_results.csv", required=False))

    telegram_lpm = np.nan
    telegram_ci = ""
    if lpm is not None and len(lpm.loc[lpm["variable"].eq("has_telegram")]):
        row = lpm.loc[lpm["variable"].eq("has_telegram")].iloc[0]
        telegram_lpm = float(row["coef_probability_points"])
        telegram_ci = f"[{row['ci95_low']:.6f}, {row['ci95_high']:.6f}]"

    discord_volume_coef = np.nan
    if discord is not None and len(discord.loc[discord["variable"].eq("log_discord_volume")]):
        discord_volume_coef = float(discord.loc[discord["variable"].eq("log_discord_volume")].iloc[0]["coef"])

    rwa_coef = np.nan
    if rwa is not None and len(rwa.loc[rwa["variable"].eq("is_rwa")]):
        rwa_coef = float(rwa.loc[rwa["variable"].eq("is_rwa")].iloc[0]["coef"])

    return [
        {
            "dimension": "Inclusion",
            "stakeholder": "Token creators",
            "metric": "Graduation rate",
            "unit": "token",
            "value": red["graduation_rate"],
            "value_label": f"{float(red['graduation_rate']) * 100:.3f}%",
            "status": STATUS_READY,
            "loss_bearer": "Creators whose tokens never reach secondary liquidity",
            "interpretation": "RED-PUMP confirms extreme entry thickness with a very thin graduation funnel.",
        },
        {
            "dimension": "Efficiency",
            "stakeholder": "Token creators",
            "metric": "Median time-to-graduation",
            "unit": "minutes",
            "value": red["median_minutes_to_graduation_seen"],
            "value_label": f"{float(red['median_minutes_to_graduation_seen']):.1f} minutes",
            "status": STATUS_READY,
            "loss_bearer": "Creators and traders facing migration friction",
            "interpretation": "Mechanism-level H1 lifecycle evidence: fast graduation is observed in RED-PUMP, while causal market claims are disciplined by the ladder.",
        },
        {
            "dimension": "Security",
            "stakeholder": "Retail traders",
            "metric": "Timeout incidence",
            "unit": "timeouts per 1000 launches",
            "value": red["timeout_incidence_per_1000"],
            "value_label": f"{float(red['timeout_incidence_per_1000']):.1f} per 1000",
            "status": STATUS_READY,
            "loss_bearer": "Retail traders holding non-graduating tokens",
            "interpretation": "Terminal-outcome security metric available without extra Dune budget.",
        },
        {
            "dimension": "Inclusion / attention",
            "stakeholder": "Community and creators",
            "metric": "Telegram metadata effect on graduation",
            "unit": "probability points",
            "value": telegram_lpm,
            "value_label": f"{telegram_lpm * 100:.3f} pp; CI {telegram_ci}" if not pd.isna(telegram_lpm) else "missing",
            "status": STATUS_READY if not pd.isna(telegram_lpm) else STATUS_EXTERNAL,
            "loss_bearer": "Creators without off-chain attention signals",
            "interpretation": "Social metadata is a strong heterogeneity channel, but not itself a PumpSwap causal effect.",
        },
        {
            "dimension": "UX / behavioral",
            "stakeholder": "Retail traders",
            "metric": "Token market-activity persistence proxy",
            "unit": "token latest snapshot",
            "value": hf["active_market_rate"],
            "value_label": f"{hf['active_market_rate'] * 100:.1f}% active; median 24h volume ${hf['median_volume_24h']:,.0f}",
            "status": STATUS_PROXY,
            "loss_bearer": "Retail traders in tokens with dry liquidity or dead volume",
            "interpretation": "Self-contained H1 token-level proxy from latest Pump.fun risk snapshots; Dune 1/7/30d windows are registered as external validation.",
        },
        {
            "dimension": "Fairness",
            "stakeholder": "Retail traders",
            "metric": "Holder concentration snapshot",
            "unit": "token latest snapshot",
            "value": hf["p90_top10_holder_pct_clean"],
            "value_label": f"p90 top-10 holder share {hf['p90_top10_holder_pct_clean']:.1f}%; high-conc rate {hf['high_concentration_rate'] * 100:.1f}%",
            "status": STATUS_PROXY,
            "loss_bearer": "Late retail entrants exposed to concentrated early supply",
            "interpretation": "Audits H4 at the holder-snapshot level. Early-buyer/sniper exports are the event-time validation layer.",
        },
        {
            "dimension": "Security / fairness",
            "stakeholder": "Retail traders",
            "metric": "Risk premium of high-concentration tokens",
            "unit": "probability points",
            "value": hf["risk_rate_difference_high_concentration"],
            "value_label": f"{hf['risk_rate_difference_high_concentration'] * 100:.1f} pp higher high/critical risk",
            "status": STATUS_PROXY,
            "loss_bearer": "Retail traders facing whale-dominated or concentrated supply",
            "interpretation": "H4 proxy association: concentrated holder structure is associated with substantially higher source-coded risk labels.",
        },
        {
            "dimension": "Mechanism validation",
            "stakeholder": "Researchers and reviewers",
            "metric": "Solana RPC external-validation sample",
            "unit": "token sample",
            "value": external_tokens,
            "value_label": (
                f"{int(external_tokens)} tokens; complete 30d {external_complete_share * 100:.0f}%; "
                f"complete-active {external_active_share * 100:.0f}%; "
                f"median complete 30d pool-tx {external_median_tx:.1f}; "
                f"truncated {external_truncated_share * 100:.0f}%; "
                f"truncated-zero observed {int(external_truncated_zero)}"
                if external_summary
                and not pd.isna(external_tokens)
                and not pd.isna(external_median_tx)
                and not pd.isna(external_complete_share)
                and not pd.isna(external_active_share)
                and not pd.isna(external_truncated_share)
                and not pd.isna(external_truncated_zero)
                else "not yet run"
            ),
            "status": STATUS_EXTERNAL_SAMPLE if external_summary else STATUS_EXTERNAL,
            "loss_bearer": "Reviewers evaluating whether proxy claims survive event-time validation",
            "interpretation": (
                "Pump.fun/Solana RPC validates post-migration pool activity on complete windows; truncated rows are retained as screening evidence and are not decoded Dune USD volume."
                if external_summary
                else "Scripted validation layer available but not yet executed."
            ),
        },
        {
            "dimension": "Mechanism validation",
            "stakeholder": "Researchers and reviewers",
            "metric": "Moralis decoded token outcomes",
            "unit": "decoded swap sample",
            "value": moralis_unique_swaps,
            "value_label": (
                f"{moralis_30d_tokens} tokens with 30d decoded swaps; "
                f"{moralis_unique_swaps:,} unique swaps; "
                f"median 30d volume ${float(moralis_median_volume):,.0f}; "
                f"median 30d trades {float(moralis_median_trades):,.0f}"
                if moralis_computed
                and not pd.isna(moralis_median_volume)
                and not pd.isna(moralis_median_trades)
                else "not yet run"
            ),
            "status": STATUS_EXTERNAL_SAMPLE if moralis_computed else STATUS_EXTERNAL,
            "loss_bearer": "Reviewers needing wallet-level, USD-denominated token outcomes rather than signature proxies",
            "interpretation": (
                "Moralis adds decoded buy/sell swaps with USD value, wallet, exchange, and pair labels for the covered graduated-token sample; it strengthens H1 outcome measurement but remains a sample, not a full welfare causal estimate."
                if moralis_computed
                else "Moralis decoded Solana Token Swaps are registered as the low-friction route for token-level USD outcomes."
            ),
        },
        {
            "dimension": "Mechanism validation",
            "stakeholder": "Researchers and reviewers",
            "metric": "Dune full-indexer export path",
            "unit": "graduated token",
            "value": dune_tokens,
            "value_label": (
                f"Dune exports computed; post rows {dune_summary.get('outputs', {}).get('post_migration', {}).get('rows', 'unknown')}"
                if dune_computed
                else f"Partial Dune exports; post rows {dune_post_rows}"
                if dune_partial
                else "Dune attempted; stopped by account datapoint limit"
                if dune_status == "stopped_chunked_dune_indexer_exports_partial"
                else f"SQL rendered for {dune_tokens_label} tokens; API key not executed"
            ),
            "status": STATUS_EXTERNAL_SAMPLE if dune_computed or dune_partial else STATUS_EXTERNAL,
            "loss_bearer": "Reviewers needing decoded USD volume and wallet-level concentration rather than public-RPC proxies",
            "interpretation": (
                "Full Dune indexer exports are present and schema-checked."
                if dune_computed
                else "Partial Dune indexer exports are present; the script stopped before submitting further queries because of a configured cap or API error."
                if dune_partial
                else "Dune execution was attempted, but the account-level datapoint limit stopped further API requests before a usable post-migration export was downloaded."
                if dune_status == "stopped_chunked_dune_indexer_exports_partial"
                else "Full 1,651-token Dune SQL has been rendered; execution requires DUNE_API_KEY and consumes Dune credits."
            ),
        },
        {
            "dimension": "Fairness / early access",
            "stakeholder": "Retail traders",
            "metric": "RED-COHORT persistent sniper cohorts",
            "unit": "cohort catalogue",
            "value": red_cohort_stats.get("n_cohorts", np.nan),
            "value_label": (
                f"{int(red_cohort_stats['n_cohorts'])} cohorts; "
                f"{int(red_cohort_stats['n_cohort_touched_mints_strict_ge2'])} strict touched mints; "
                f"median first rank {red_cohort_stats['avg_first_rank_median']:.2f}"
                if red_cohort_stats
                else "not yet downloaded"
            ),
            "status": STATUS_EXTENSION if red_cohort_stats else STATUS_EXTERNAL,
            "loss_bearer": "Retail traders competing against persistent early-wallet cohorts",
            "interpretation": (
                "No-key RED-COHORT download directly strengthens H4 mechanism evidence. "
                "Its current mint overlap with RED-PUMP outcomes is "
                f"{int(red_cohort_overlap.get('red_cohort_intra_overlap_mints', 0) or 0)}, "
                "so it is treated as external mechanism validation rather than a joined causal outcome sample."
                if red_cohort_stats
                else "RED-COHORT public download is registered as the free-data route for H4 validation."
            ),
        },
        {
            "dimension": "Community",
            "stakeholder": "Discord communities",
            "metric": "Discord volume coefficient in TVL extension",
            "unit": "log points",
            "value": discord_volume_coef,
            "value_label": f"{discord_volume_coef:.3f}" if not pd.isna(discord_volume_coef) else "missing",
            "status": STATUS_EXTENSION if not pd.isna(discord_volume_coef) else STATUS_EXTERNAL,
            "loss_bearer": "Communities whose off-chain attention is invisible in market-only evaluations",
            "interpretation": "Extension module: demonstrates off-chain community channel, not a Pump.fun causal estimate.",
        },
        {
            "dimension": "Trust / RWA",
            "stakeholder": "Asset-backed token communities",
            "metric": "RWA category coefficient in TVL snapshot",
            "unit": "log points",
            "value": rwa_coef,
            "value_label": f"{rwa_coef:.3f}" if not pd.isna(rwa_coef) else "missing",
            "status": STATUS_EXTENSION if not pd.isna(rwa_coef) else STATUS_EXTERNAL,
            "loss_bearer": "Users relying on off-chain asset credibility",
            "interpretation": "Extension module: positions memecoin launchpads against asset-backed tokenization.",
        },
    ]


def build_data_availability(config: CaseConfig) -> pd.DataFrame:
    dune_summary_path = config.tables_dir / "dune_indexer_export_summary.json"
    dune_summary = json.loads(dune_summary_path.read_text(encoding="utf-8")) if dune_summary_path.exists() else {}
    moralis_summary_path = config.tables_dir / "moralis_decoded_outcomes_summary.json"
    moralis_summary = (
        json.loads(moralis_summary_path.read_text(encoding="utf-8")) if moralis_summary_path.exists() else {}
    )
    free_public_summary_path = config.tables_dir / "free_public_data_summary.json"
    free_public_summary = (
        json.loads(free_public_summary_path.read_text(encoding="utf-8"))
        if free_public_summary_path.exists()
        else {}
    )
    checks = [
        ("market_panel", "market/protocol-day", "H1 aggregate activity"),
        ("red_pump_token_outcomes", "token lifecycle", "creator graduation, timeout, social metadata"),
        ("red_pump_graduated_for_dune", "graduated token list", "post-migration Dune query input"),
        ("hf_pump_sentiment_sample", "token risk snapshot", "H1 persistence proxy and H4 concentration/risk proxy"),
        ("discord_daily_sentiment_panel", "protocol-day off-chain", "community extension"),
        ("discord_tvl_panel", "protocol-day merged extension", "off-chain model"),
        ("rwa_registry", "protocol snapshot", "RWA trust extension"),
    ]
    rows = []
    for key, layer, purpose in checks:
        path = config.source_path(key, required=False)
        rows.append(
            {
                "source_key": key,
                "layer": layer,
                "purpose": purpose,
                "path": str(path),
                "available": path.exists(),
            }
        )
    rows.extend(
        [
            {
                "source_key": "dune_post_migration_trades",
                "layer": "token x horizon",
                "purpose": "External validation of H1 post-migration event-time persistence",
                "path": "data_sources/dune_queries/pumpswap_post_migration_trades.sql",
                "available": "registered_not_required_for_current_claim",
            },
            {
                "source_key": "dune_early_buyers",
                "layer": "token x wallet-event",
                "purpose": "External validation of H4 early allocation/sniper channel",
                "path": "data_sources/dune_queries/pumpswap_early_buyers.sql",
                "available": "registered_not_required_for_current_claim",
            },
            {
                "source_key": "dune_full_rendered_sql",
                "layer": "token x horizon and token x wallet-event",
                "purpose": "Executable full-indexer SQL rendered for all graduated RED-PUMP tokens",
                "path": str(config.output_root / "external_validation" / "dune_sql"),
                "available": dune_summary.get("status", "not_rendered"),
            },
            {
                "source_key": "dune_indexer_exports",
                "layer": "decoded token-level indexer exports",
                "purpose": "Top-conference H1/H4 decoded outcome validation",
                "path": str(config.output_root / "external_validation"),
                "available": dune_summary.get("status") == "computed_dune_indexer_exports",
            },
            {
                "source_key": "moralis_decoded_token_outcomes",
                "layer": "decoded token x horizon swaps",
                "purpose": "Moralis decoded H1 USD-volume, buy/sell, wallet, exchange, and pair outcomes",
                "path": str(config.output_root / "external_validation" / "moralis_decoded_token_outcomes.csv"),
                "available": moralis_summary.get("status", "not_run"),
            },
            {
                "source_key": "solana_rpc_post_migration_pool_windows",
                "layer": "token x horizon",
                "purpose": "Computed external-validation sample for H1 post-migration persistence",
                "path": str(config.output_root / "external_validation" / "solana_post_migration_pool_windows.csv"),
                "available": (config.output_root / "external_validation" / "solana_post_migration_pool_windows.csv").exists(),
            },
            {
                "source_key": "solana_rpc_early_wallet_concentration",
                "layer": "token x early-wallet cohort",
                "purpose": "Computed external-validation sample for H4 early allocation concentration",
                "path": str(config.output_root / "external_validation" / "solana_early_wallet_concentration.csv"),
                "available": (config.output_root / "external_validation" / "solana_early_wallet_concentration.csv").exists(),
            },
            {
                "source_key": "solarchive_public_downloads",
                "layer": "Solana-wide token/account/transaction public archive",
                "purpose": "No-key public-data extension for Solana token universe coverage and future local indexer validation",
                "path": str(config.project_root / "data_sources" / "free_public" / "solarchive"),
                "available": free_public_summary.get("solarchive", {}).get("present", False),
            },
            {
                "source_key": "red_cohort_public_download",
                "layer": "Pump.fun early-wallet cohorts",
                "purpose": "No-key public-data extension for H4 concentration/sniper mechanism validation",
                "path": str(config.project_root / "data_sources" / "free_public" / "red_cohort"),
                "available": free_public_summary.get("red_cohort", {}).get("zip_present", False),
            },
            {
                "source_key": "hf_pump_meme_public_download",
                "layer": "Pump.fun token metadata/text",
                "purpose": "No-key public-data extension for broader token metadata and textual heterogeneity checks",
                "path": str(config.project_root / "data_sources" / "free_public" / "huggingface"),
                "available": free_public_summary.get("hf_meme_token_dataset", {}).get("present", False),
            },
        ]
    )
    return pd.DataFrame(rows)


def build_metric_battery(config: CaseConfig) -> pd.DataFrame:
    red = summarize_red_pump(config)
    hf = summarize_hf_pump_sentiment(config)
    rows = metric_rows_from_summary(config, red)
    battery = pd.DataFrame(rows)
    availability = build_data_availability(config)
    claim_scope = build_claim_scope_ledger(config, red, hf)
    write_csv(config.tables_dir / "result1_stakeholder_metric_battery.csv", battery)
    write_csv(config.tables_dir / "data_availability_ledger.csv", availability)
    write_csv(config.tables_dir / "claim_scope_ledger.csv", claim_scope)
    write_json(config.tables_dir / "red_pump_result1_summary.json", red)
    write_json(config.tables_dir / "hf_pump_risk_snapshot_summary.json", hf)
    return battery


def build_claim_scope_ledger(config: CaseConfig, red: dict[str, object], hf: dict[str, object]) -> pd.DataFrame:
    """Make the paper's claim boundary explicit and self-contained."""

    h1_path = config.tables_dir / "h1_rpc_mechanism_summary.json"
    h1 = json.loads(h1_path.read_text(encoding="utf-8")) if h1_path.exists() else {}
    moralis_path = config.tables_dir / "moralis_decoded_outcomes_summary.json"
    moralis = json.loads(moralis_path.read_text(encoding="utf-8")) if moralis_path.exists() else {}
    moralis_unique_swaps = int(moralis.get("unique_decoded_swap_rows", 0) or 0)
    moralis_30d_tokens = int(moralis.get("decoded_30d_tokens_with_swaps", 0) or 0)
    return pd.DataFrame(
        [
            {
                "claim_id": "H1-market",
                "hypothesis": "H1 migration friction",
                "evidence_layer": "market-level deterministic ladder",
                "status": "computed",
                "claim_allowed": "Naive before-after evidence is positive, but trustworthy market-level inference is uncertain after controls, pretrend screening, and few-cluster inference.",
                "claim_not_allowed": "Do not claim a clean causal welfare gain from aggregate volume alone.",
            },
            {
                "claim_id": "H1-token-proxy",
                "hypothesis": "H1 post-graduation persistence",
                "evidence_layer": "HF Pump.fun token risk/market snapshot",
                "status": "computed_proxy",
                "claim_allowed": f"Token-level persistence is summarized by active-market proxy: {hf['active_market_rate'] * 100:.1f}% active in latest-per-mint snapshot sample.",
                "claim_not_allowed": "Do not label this as a 1/7/30d event-time causal estimate or infer post-migration survival timing from one snapshot.",
            },
            {
                "claim_id": "H1-rpc-mechanism",
                "hypothesis": "H1 migration friction",
                "evidence_layer": "Helius/Solana RPC post-migration pool windows",
                "status": h1.get("mechanism_claim_status", "missing_h1_rpc_mechanism_summary"),
                "claim_allowed": (
                    "PumpSwap is supported as an operational post-migration liquidity venue: "
                    f"full-sample observed 30d activity lower bound is "
                    f"{float(h1.get('full_30d_observed_active_lower_bound_share', np.nan)) * 100:.2f}% "
                    f"and complete-window active share is "
                    f"{float(h1.get('complete_30d_active_share', np.nan)) * 100:.2f}%."
                    if h1
                    else "No H1 RPC mechanism claim until the audit is generated."
                ),
                "claim_not_allowed": "Do not claim decoded USD volume, active-trader, price-quality, welfare, or H4 early-allocation causal effects from RPC signature proxies.",
            },
            {
                "claim_id": "H1-moralis-decoded-sample",
                "hypothesis": "H1 post-graduation persistence",
                "evidence_layer": "Moralis decoded Solana Token Swaps sample",
                "status": moralis.get("credible_sample_status", "not_run"),
                "claim_allowed": (
                    f"Moralis decoded sample measures {moralis_unique_swaps:,} unique swap rows and "
                    f"{moralis_30d_tokens} covered 30d token windows with positive decoded swaps."
                    if moralis_unique_swaps
                    else "No Moralis decoded-outcome claim until the collector is run."
                ),
                "claim_not_allowed": "Do not generalize the Moralis sample to all graduated tokens, H4 sniper causality, price quality, or welfare without full-cohort decoded outcomes and the merged causal design.",
            },
            {
                "claim_id": "H4-holder-risk",
                "hypothesis": "H4 allocation fairness",
                "evidence_layer": "HF holder concentration and risk snapshot",
                "status": "computed_proxy",
                "claim_allowed": f"High-concentration tokens have {hf['risk_rate_difference_high_concentration'] * 100:.1f} pp higher source-coded high/critical risk in the latest-per-mint snapshot sample.",
                "claim_not_allowed": "Do not claim independent causal risk effects or slot-level sniper causality without auditing label construction and adding the registered Dune/indexer validation export.",
            },
            {
                "claim_id": "H1-H4-event-time-validation",
                "hypothesis": "H1/H4 mechanism timing",
                "evidence_layer": "rendered Dune full-indexer SQL plus optional Pump.fun/Solana RPC sample",
                "status": "computed_external_validation_sample_if_present",
                "claim_allowed": "Rendered full-token Dune SQL defines the decoded indexer layer; when present, Solana RPC artifacts provide real pool-transaction and early-fee-payer proxy validation.",
                "claim_not_allowed": "Do not treat RPC pool-transaction proxies as decoded Dune USD swap volume or as direct proof of sniper causality.",
            },
        ]
    )


def export_metric_battery_tex(battery: pd.DataFrame, path: Path) -> None:
    def latex_escape(value: object) -> str:
        text = str(value)
        replacements = {
            "\\": r"\textbackslash{}",
            "&": r"\&",
            "%": r"\%",
            "$": r"\$",
            "#": r"\#",
            "_": r"\_",
            "{": r"\{",
            "}": r"\}",
            "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}",
        }
        return "".join(replacements.get(char, char) for char in text)

    lines = [
        "% Auto-generated by Shilin/scripts/run_all.py",
        "\\begin{table}[t]",
        "\\centering",
        "\\footnotesize",
        "\\caption{Shilin Result 1 stakeholder metric battery for the Pump.fun--PumpSwap application.}",
        "\\label{tab:shilin-metric-battery}",
        "\\begin{tabularx}{\\textwidth}{@{}l l l l X@{}}",
        "\\toprule",
        "\\textbf{Dimension} & \\textbf{Stakeholder} & \\textbf{Metric} & \\textbf{Status} & \\textbf{Interpretation} \\\\",
        "\\midrule",
    ]
    for row in battery.itertuples(index=False):
        metric_cell = f"{row.metric}: {row.value_label}"
        lines.append(
            " & ".join(
                [
                    latex_escape(row.dimension),
                    latex_escape(row.stakeholder),
                    latex_escape(metric_cell),
                    latex_escape(row.status),
                    latex_escape(row.interpretation),
                ]
            )
            + " \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabularx}", "\\end{table}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
