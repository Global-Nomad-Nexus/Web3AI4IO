#!/usr/bin/env python3
"""Build Shilin's benchmark release tables for the PumpSwap application arm."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
SRS_ROOT = REPO_ROOT.parent
OUT = ROOT / "benchmark_release"
DATA = OUT / "data"

EVENT_ID = "PUMP_PUMPSWAP_MIGRATION_20250320"
CONTEXT_EVENT_ID = "SHILIN_OFFCHAIN_CONTEXT_PANEL"
CLANKER_BASE_EVENT_ID = "CLANKER_SNIPER_DECAY_V41_BASE_20250826"


EVENT_COLUMNS = [
    "event_id",
    "event_type",
    "platform",
    "chain",
    "rule_family",
    "rule_change",
    "announcement_timestamp_utc",
    "activation_timestamp_utc",
    "activation_evidence_type",
    "activation_evidence",
    "activation_transaction_hash",
    "next_block_verification",
    "anticipation_boundary_utc",
    "concurrent_shocks",
    "comparison_unit_status",
    "eligibility_status",
    "rejection_reason",
    "hypothesis_tags",
    "claim_boundary",
    "source_artifact",
]

METRIC_COLUMNS = [
    "event_id",
    "timestamp_utc",
    "unit_id",
    "unit_type",
    "token_id",
    "platform",
    "chain",
    "scale",
    "frequency",
    "horizon_days",
    "relative_day",
    "treated",
    "post",
    "launches",
    "unique_creators",
    "active_traders",
    "buy_count",
    "sell_count",
    "graduations",
    "migrations",
    "graduation_rate",
    "volume_usd",
    "log_volume",
    "fee_revenue_usd",
    "holder_concentration_top10",
    "holder_count",
    "early_sender_concentration_top10",
    "security_or_risk_rate",
    "swap_count",
    "first_trade_at",
    "last_trade_at",
    "market_quality_metric",
    "claim_boundary",
    "source_layer",
    "status",
]

COVARIATE_COLUMNS = [
    "event_id",
    "timestamp_utc",
    "unit_id",
    "unit_type",
    "token_id",
    "platform",
    "chain",
    "frequency",
    "covariate_family",
    "telegram_present",
    "discord_volume",
    "sentiment_score",
    "twitter_present",
    "website_present",
    "any_social",
    "social_count",
    "description_length",
    "tvl_usd",
    "rwa_category",
    "community_channel_indicator",
    "source_layer",
    "claim_boundary",
    "status",
]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def write_csv(path: Path, rows: list[dict[str, Any]] | pd.DataFrame, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if columns:
        for column in columns:
            if column not in df:
                df[column] = ""
        df = df[columns]
    df = df.where(pd.notna(df), "")
    df.to_csv(path, index=False)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def iso_utc(value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)) or str(value).strip() == "":
        return ""
    try:
        ts = pd.to_datetime(value, utc=True)
    except Exception:
        return str(value)
    if pd.isna(ts):
        return ""
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_config() -> dict[str, Any]:
    return read_json(ROOT / "configs" / "pumpswap_case.json")


def source_path(config: dict[str, Any], key: str) -> Path:
    rel = Path(config[key])
    upstream_name = Path(str(config.get("upstream_mvp_root", ""))).name
    public_name = Path(str(config.get("public_mvp_root", ""))).name
    candidates = [
        (ROOT / config.get("upstream_mvp_root", "") / rel).resolve(),
        (REPO_ROOT / config.get("upstream_mvp_root", "") / rel).resolve(),
        (SRS_ROOT / "01_Pumpfun_PumpSwap_Project" / upstream_name / rel).resolve(),
        (ROOT / config.get("public_mvp_root", "") / rel).resolve(),
        (REPO_ROOT / config.get("public_mvp_root", "") / rel).resolve(),
        (SRS_ROOT / "01_Pumpfun_PumpSwap_Project" / public_name / rel).resolve(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def relpath(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        try:
            return str(path.relative_to(SRS_ROOT))
        except ValueError:
            return str(path)


def platform_from_unit(unit: str) -> str:
    return {
        "pump_ecosystem": "Pump.fun / PumpSwap",
        "raydium": "Raydium",
        "orca": "Orca",
        "meteora_combined": "Meteora",
    }.get(unit, unit)


def build_events() -> pd.DataFrame:
    clanker_summary = read_json(ROOT / "artifacts" / "tables" / "clanker_base_event_validation_summary.json")
    if clanker_summary.get("status", "").startswith("accepted"):
        clanker_event_row = {
            "event_id": clanker_summary.get("event_id", CLANKER_BASE_EVENT_ID),
            "event_type": "rule_event",
            "platform": "Clanker",
            "chain": "Base",
            "rule_family": "trader_protection",
            "rule_change": clanker_summary.get(
                "rule_change",
                "First observed Clanker v4.1 MEV/sniper-protection module token launch on Base.",
            ),
            "announcement_timestamp_utc": "2025-08-22T00:00:00Z",
            "activation_timestamp_utc": clanker_summary.get("activation_timestamp_utc", ""),
            "activation_evidence_type": clanker_summary.get("activation_evidence_type", ""),
            "activation_evidence": (
                f"Base public JSON-RPC verifies the first v4.1 MEV-module TokenCreated log at block "
                f"{clanker_summary.get('activation_block', '')}; search window contains "
                f"{clanker_summary.get('token_created_rows', '')} Clanker v4 launches and "
                f"{clanker_summary.get('version_class_counts', {}).get('v4.1_mev_or_hook', '')} v4.1 rows."
            ),
            "activation_transaction_hash": clanker_summary.get("activation_transaction_hash", ""),
            "next_block_verification": "onchain_log_block_and_timestamp_verified",
            "anticipation_boundary_utc": "2025-08-22T00:00:00Z",
            "concurrent_shocks": "V4.1 adoption is sparse in the search window; market and creator-selection shocks remain possible.",
            "comparison_unit_status": clanker_summary.get(
                "comparison_unit_status",
                "Bounded local comparison: nearest v4.0 launch controls and first v4.1 treated launches.",
            ),
            "eligibility_status": "accepted",
            "rejection_reason": "",
            "hypothesis_tags": "H4;cross_chain",
            "claim_boundary": clanker_summary.get(
                "claim_boundary",
                "Accepted as a bounded on-chain Base validation case, not as platform-wide causal replication.",
            ),
            "source_artifact": (
                "artifacts/tables/clanker_base_event_validation_summary.json; "
                "artifacts/external_validation/clanker_base_token_horizons.csv; "
                "artifacts/external_validation/clanker_base_pool_swaps_raw.csv; "
                "artifacts/external_validation/clanker_base_token_transfers_raw.csv"
            ),
        }
    else:
        clanker_event_row = {
            "event_id": "CLANKER_SNIPER_DECAY_V41_BASE_CANDIDATE",
            "event_type": "candidate_rule_event",
            "platform": "Clanker",
            "chain": "Base",
            "rule_family": "trader_protection",
            "rule_change": "Candidate Clanker v4 MEV/sniper-protection deployment or default-configuration change for Base launchpad tokens.",
            "announcement_timestamp_utc": "",
            "activation_timestamp_utc": "",
            "activation_evidence_type": "first_party_contract_docs_plus_public_api_path_needs_onchain_validation",
            "activation_evidence": (
                "Clanker documentation records v4 MEV modules, Base v4.1 deployed sniper-auction contracts, "
                "and a token deployment config with mevModule fields. Bitquery documents Base Clanker "
                "TokenCreated queries. Use as Shilin's highest-priority cross-chain candidate, not as computed evidence."
            ),
            "activation_transaction_hash": "",
            "next_block_verification": "",
            "anticipation_boundary_utc": "",
            "concurrent_shocks": "Unknown until Base token-factory rollout and market window are validated.",
            "comparison_unit_status": "Candidate Base token cohorts and non-treated or pre/post comparison windows must be constructed before causal use.",
            "eligibility_status": "conditional",
            "rejection_reason": "activation_timestamp_adoption_share_and_token_horizon_outcomes_not_yet_verified",
            "hypothesis_tags": "H4;cross_chain",
            "claim_boundary": "Cross-chain architecture candidate only; no causal replication claim yet.",
            "source_artifact": "https://github.com/clanker-devco/DOCS; https://docs.bitquery.io/docs/blockchain/Base/base-clanker-api/",
        }

    rows = [
        {
            "event_id": EVENT_ID,
            "event_type": "rule_event",
            "platform": "Pump.fun / PumpSwap",
            "chain": "Solana",
            "rule_family": "product_option",
            "rule_change": "Graduated Pump.fun tokens migrate into PumpSwap post-graduation liquidity.",
            "announcement_timestamp_utc": "",
            "activation_timestamp_utc": "2025-03-20T00:00:00Z",
            "activation_evidence_type": "registered_event_date_plus_rpc_and_decoded_sample_validation",
            "activation_evidence": (
                "Event date registered in configs/pumpswap_case.json. Solana RPC validates post-migration "
                "pool activity, Moralis adds a covered-token decoded swap sample, and rendered Dune SQL "
                "registers the full-indexer path."
            ),
            "activation_transaction_hash": "",
            "next_block_verification": "not_registered_for_this_product_event",
            "anticipation_boundary_utc": "",
            "concurrent_shocks": "Solana DEX market cycle, control-unit pretrend risk, and few-cluster inference risk.",
            "comparison_unit_status": "Solana DEX controls exist; market-level causal status remains diagnostic.",
            "eligibility_status": "conditional",
            "rejection_reason": "",
            "hypothesis_tags": "H1;H4",
            "claim_boundary": (
                "Supports mechanism-level post-migration venue activation and an evidence-ladder conclusion flip. "
                "Does not support welfare, price-quality, full-cohort USD-volume, or same-cohort H4 causal claims."
            ),
            "source_artifact": "configs/pumpswap_case.json; artifacts/tables/*",
        },
        clanker_event_row,
        {
            "event_id": "FOUR_MEME_BNB_DISCOVERY_CANDIDATE",
            "event_type": "candidate_rule_event",
            "platform": "Four.meme",
            "chain": "BNB Chain",
            "rule_family": "entry_incentive_or_product_option",
            "rule_change": "Candidate BNB launchpad event for cross-chain external validity.",
            "announcement_timestamp_utc": "",
            "activation_timestamp_utc": "",
            "activation_evidence_type": "discovery_needed",
            "activation_evidence": "No accepted event yet.",
            "activation_transaction_hash": "",
            "next_block_verification": "",
            "anticipation_boundary_utc": "",
            "concurrent_shocks": "",
            "comparison_unit_status": "Not screened.",
            "eligibility_status": "rejected",
            "rejection_reason": "no_verified_rule_event_or_panel_yet",
            "hypothesis_tags": "H1;cross_chain",
            "claim_boundary": "Discovery candidate only.",
            "source_artifact": "Notes/MVP.md; benchmark_release/data/cross_chain_event_candidates.csv",
        },
        {
            "event_id": CONTEXT_EVENT_ID,
            "event_type": "context_panel",
            "platform": "Multiple protocols",
            "chain": "multi-chain",
            "rule_family": "offchain_context",
            "rule_change": "Discord, sentiment, TVL, RWA, and token social metadata panels for covariates.",
            "announcement_timestamp_utc": "",
            "activation_timestamp_utc": "",
            "activation_evidence_type": "not_a_rule_event",
            "activation_evidence": "Included only to give covariates.csv a stable join key for context rows.",
            "activation_transaction_hash": "",
            "next_block_verification": "not_applicable",
            "anticipation_boundary_utc": "",
            "concurrent_shocks": "",
            "comparison_unit_status": "Context only.",
            "eligibility_status": "conditional",
            "rejection_reason": "not_a_treatment_event",
            "hypothesis_tags": "offchain;interdisciplinary",
            "claim_boundary": "Use as covariates and external-validity context, not as a causal treatment.",
            "source_artifact": "legacy processed off-chain panels",
        },
    ]
    return pd.DataFrame(rows)[EVENT_COLUMNS]


def build_metrics_panel() -> pd.DataFrame:
    config = load_config()
    rows: list[dict[str, Any]] = []

    market_path = source_path(config, "market_panel")
    market = read_csv(market_path)
    for _, row in market.iterrows():
        rows.append(
            {
                "event_id": EVENT_ID,
                "timestamp_utc": iso_utc(row.get("date")),
                "unit_id": row["unit"],
                "unit_type": "platform_day",
                "token_id": "",
                "platform": platform_from_unit(str(row["unit"])),
                "chain": "Solana",
                "scale": "usd_volume_and_log1p",
                "frequency": "daily",
                "horizon_days": 0,
                "relative_day": row.get("rel_day", ""),
                "treated": row.get("treated", ""),
                "post": row.get("post", ""),
                "volume_usd": row.get("daily_volume_usd", ""),
                "log_volume": row.get("log_volume", ""),
                "claim_boundary": "Aggregate market diagnostic, not welfare or token-level causal evidence.",
                "source_layer": relpath(market_path),
                "status": "computed",
            }
        )

    rpc = read_csv(ROOT / "artifacts" / "external_validation" / "solana_post_migration_pool_windows.csv")
    for _, row in rpc.iterrows():
        rows.append(
            {
                "event_id": EVENT_ID,
                "timestamp_utc": iso_utc(row.get("graduated_at")),
                "unit_id": f"{row['mint']}:{int(row['horizon_days'])}d:rpc",
                "unit_type": "token_horizon",
                "token_id": row.get("mint", ""),
                "platform": "Pump.fun / PumpSwap",
                "chain": "Solana",
                "scale": "rpc_pool_transaction_proxy",
                "frequency": "fixed_horizon",
                "horizon_days": row.get("horizon_days", ""),
                "active_traders": row.get("active_traders", ""),
                "swap_count": row.get("swap_count", ""),
                "volume_usd": row.get("volume_usd", ""),
                "first_trade_at": iso_utc(row.get("first_trade_at")),
                "last_trade_at": iso_utc(row.get("last_trade_at")),
                "market_quality_metric": row.get("inactivity_gap_hours", ""),
                "claim_boundary": "RPC proxy validates pool activity; it is not decoded USD volume or welfare.",
                "source_layer": "Shilin/artifacts/external_validation/solana_post_migration_pool_windows.csv",
                "status": row.get("validation_status", "computed_pool_tx_proxy"),
            }
        )

    moralis = read_csv(ROOT / "artifacts" / "external_validation" / "moralis_decoded_token_outcomes.csv")
    for _, row in moralis.iterrows():
        rows.append(
            {
                "event_id": EVENT_ID,
                "timestamp_utc": iso_utc(row.get("graduated_at")),
                "unit_id": f"{row['mint']}:{int(row['horizon_days'])}d:moralis",
                "unit_type": "token_horizon",
                "token_id": row.get("mint", ""),
                "platform": "Pump.fun / PumpSwap",
                "chain": "Solana",
                "scale": "decoded_swap_sample",
                "frequency": "fixed_horizon",
                "horizon_days": row.get("horizon_days", ""),
                "active_traders": row.get("decoded_active_traders", ""),
                "buy_count": row.get("decoded_buy_count", ""),
                "sell_count": row.get("decoded_sell_count", ""),
                "swap_count": row.get("decoded_trade_count", ""),
                "volume_usd": row.get("decoded_volume_usd", ""),
                "first_trade_at": iso_utc(row.get("first_decoded_trade_at")),
                "last_trade_at": iso_utc(row.get("last_decoded_trade_at")),
                "market_quality_metric": row.get("buy_sell_imbalance", ""),
                "claim_boundary": "Moralis decoded sample measures covered tokens only; not full-cohort welfare causality.",
                "source_layer": "Shilin/artifacts/external_validation/moralis_decoded_token_outcomes.csv",
                "status": row.get("moralis_window_status", "computed_decoded_sample"),
                }
            )

    early_wallets = read_csv(ROOT / "artifacts" / "external_validation" / "dune_early_wallets.csv")
    for _, row in early_wallets.iterrows():
        rows.append(
            {
                "event_id": EVENT_ID,
                "timestamp_utc": iso_utc(row.get("launch_or_graduated_at")),
                "unit_id": f"{row['mint']}:{int(row.get('early_window_seconds', 60))}s:early_wallet",
                "unit_type": "token_wallet_horizon",
                "token_id": row.get("mint", ""),
                "platform": "Pump.fun / PumpSwap",
                "chain": "Solana",
                "scale": "early_wallet_concentration_sample",
                "frequency": "fixed_early_window",
                "horizon_days": 0,
                "volume_usd": row.get("early_volume_usd", ""),
                "holder_concentration_top10": row.get("top10_early_wallet_share", ""),
                "first_trade_at": iso_utc(row.get("first_trade_at")),
                "last_trade_at": iso_utc(row.get("last_early_trade_at")),
                "market_quality_metric": row.get("early_wallet_hhi", ""),
                "claim_boundary": (
                    "Same-cohort early-wallet sample row; useful for H4 validation plumbing, "
                    "not enough for a full retail-harm causal claim."
                ),
                "source_layer": "Shilin/artifacts/external_validation/dune_early_wallets.csv",
                "status": "computed_sample_if_present",
            }
        )

    clanker_horizons = read_csv(ROOT / "artifacts" / "external_validation" / "clanker_base_token_horizons.csv")
    for _, row in clanker_horizons.iterrows():
        rows.append(
            {
                "event_id": row.get("event_id", CLANKER_BASE_EVENT_ID),
                "timestamp_utc": iso_utc(row.get("launch_timestamp_utc")),
                "unit_id": row.get("unit_id", ""),
                "unit_type": "token_horizon",
                "token_id": row.get("token_id", ""),
                "platform": "Clanker",
                "chain": "Base",
                "scale": "base_uniswap_v4_poolmanager_swap_sample",
                "frequency": "fixed_horizon",
                "horizon_days": row.get("horizon_days", ""),
                "treated": int(str(row.get("cohort_side", "")).startswith("post_v4_1")),
                "post": int(str(row.get("cohort_side", "")).startswith("post_v4_1")),
                "active_traders": row.get("active_traders", ""),
                "buy_count": row.get("buy_count", ""),
                "sell_count": row.get("sell_count", ""),
                "volume_usd": row.get("volume_usd", ""),
                "swap_count": row.get("swap_count", ""),
                "first_trade_at": iso_utc(row.get("first_trade_at")),
                "last_trade_at": iso_utc(row.get("last_trade_at")),
                "holder_concentration_top10": row.get("holder_concentration_top10", ""),
                "holder_count": row.get("holder_count", ""),
                "early_sender_concentration_top10": row.get("early_sender_top10_share_60s", ""),
                "market_quality_metric": row.get("paired_volume", ""),
                "claim_boundary": row.get(
                    "claim_boundary",
                    "Base bounded cross-chain token-horizon sample, not platform-wide causal replication.",
                ),
                "source_layer": "Shilin/artifacts/external_validation/clanker_base_token_horizons.csv",
                "status": row.get("status", "computed_bounded_onchain_sample"),
            }
        )

    red_path = source_path(config, "red_pump_token_outcomes")
    red_cols = ["mint", "launch_day", "graduated", "outcome", "has_telegram", "has_any_social"]
    red = read_csv(red_path, usecols=lambda c: c in red_cols, low_memory=False)
    if not red.empty:
        red = red.assign(
            graduated=pd.to_numeric(red["graduated"], errors="coerce").fillna(0),
            timeout=red["outcome"].astype(str).eq("TIMEOUT").astype(int),
            has_telegram=pd.to_numeric(red["has_telegram"], errors="coerce").fillna(0),
            has_any_social=pd.to_numeric(red["has_any_social"], errors="coerce").fillna(0),
        )
        daily = (
            red.groupby("launch_day", dropna=True)
            .agg(
                launches=("mint", "count"),
                graduations=("graduated", "sum"),
                timeout_rate=("timeout", "mean"),
                telegram_share=("has_telegram", "mean"),
                any_social_share=("has_any_social", "mean"),
            )
            .reset_index()
        )
        daily["graduation_rate"] = daily["graduations"] / daily["launches"]
        for _, row in daily.iterrows():
            rows.append(
                {
                    "event_id": EVENT_ID,
                    "timestamp_utc": iso_utc(row.get("launch_day")),
                    "unit_id": f"red_pump_launch_day:{row['launch_day']}",
                    "unit_type": "token_launch_day_cohort",
                    "token_id": "",
                    "platform": "Pump.fun",
                    "chain": "Solana",
                    "scale": "token_cohort_counts",
                    "frequency": "daily_cohort",
                    "horizon_days": "",
                    "launches": row.get("launches", ""),
                    "graduations": row.get("graduations", ""),
                    "graduation_rate": row.get("graduation_rate", ""),
                    "security_or_risk_rate": row.get("timeout_rate", ""),
                    "claim_boundary": "RED-PUMP cohort summary; not a March 2025 pre/post causal estimate.",
                    "source_layer": relpath(red_path),
                    "status": "computed_external_cohort_summary",
                }
            )

    return pd.DataFrame(rows).reindex(columns=METRIC_COLUMNS)


def validation_token_ids() -> set[str]:
    token_ids: set[str] = set()
    for path in [
        ROOT / "artifacts" / "external_validation" / "h1_rpc_token_level_outcomes.csv",
        ROOT / "artifacts" / "external_validation" / "moralis_decoded_token_outcomes.csv",
    ]:
        df = read_csv(path, usecols=["mint"])
        if not df.empty:
            token_ids.update(df["mint"].dropna().astype(str).unique())
    return token_ids


def build_covariates() -> pd.DataFrame:
    config = load_config()
    rows: list[dict[str, Any]] = []

    discord_path = source_path(config, "discord_daily_sentiment_panel")
    discord = read_csv(discord_path)
    for _, row in discord.iterrows():
        rows.append(
            {
                "event_id": CONTEXT_EVENT_ID,
                "timestamp_utc": iso_utc(row.get("date")),
                "unit_id": row.get("protocol", ""),
                "unit_type": "protocol_day",
                "token_id": "",
                "platform": row.get("protocol", ""),
                "chain": "multi_chain_defi",
                "frequency": "daily",
                "covariate_family": "community_attention_sentiment",
                "discord_volume": row.get("discord_volume", ""),
                "sentiment_score": row.get("sentiment_score", ""),
                "community_channel_indicator": 1,
                "source_layer": relpath(discord_path),
                "claim_boundary": "Off-chain context, not a PumpSwap causal estimate.",
                "status": "computed_context",
            }
        )

    discord_tvl_path = source_path(config, "discord_tvl_panel")
    discord_tvl = read_csv(discord_tvl_path)
    for _, row in discord_tvl.iterrows():
        rows.append(
            {
                "event_id": CONTEXT_EVENT_ID,
                "timestamp_utc": iso_utc(row.get("date")),
                "unit_id": row.get("protocol", ""),
                "unit_type": "protocol_day_tvl",
                "token_id": "",
                "platform": row.get("protocol", ""),
                "chain": "multi_chain_defi",
                "frequency": "daily",
                "covariate_family": "community_attention_tvl",
                "discord_volume": row.get("discord_volume", ""),
                "sentiment_score": row.get("sentiment_score", ""),
                "tvl_usd": row.get("tvl_usd", ""),
                "community_channel_indicator": 1,
                "source_layer": relpath(discord_tvl_path),
                "claim_boundary": "Extension covariate panel connecting community attention and protocol TVL.",
                "status": "computed_context",
            }
        )

    rwa_path = source_path(config, "rwa_registry")
    rwa = read_csv(rwa_path)
    snapshot = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    for _, row in rwa.iterrows():
        rwa_chain = row.get("chains_joined", "multi_chain_context")
        if pd.isna(rwa_chain) or str(rwa_chain).strip() == "":
            rwa_chain = "multi_chain_context"
        rows.append(
            {
                "event_id": CONTEXT_EVENT_ID,
                "timestamp_utc": snapshot,
                "unit_id": row.get("slug", row.get("name", "")),
                "unit_type": "protocol_snapshot",
                "token_id": "",
                "platform": row.get("name", ""),
                "chain": rwa_chain,
                "frequency": "snapshot",
                "covariate_family": "rwa_protocol_metadata",
                "tvl_usd": row.get("tvl", ""),
                "rwa_category": row.get("category", ""),
                "source_layer": relpath(rwa_path),
                "claim_boundary": "Cross-chain RWA context for external-validity discussion, not a launchpad treatment effect.",
                "status": "computed_context",
            }
        )

    red_path = source_path(config, "red_pump_token_outcomes")
    token_ids = validation_token_ids()
    red_cols = [
        "mint",
        "created_at",
        "launch_day",
        "has_twitter",
        "has_website",
        "has_telegram",
        "social_count",
        "has_any_social",
        "description_length",
    ]
    red = read_csv(red_path, usecols=lambda c: c in red_cols, low_memory=False)
    if not red.empty and token_ids:
        matched = red.loc[red["mint"].astype(str).isin(token_ids)]
        for _, row in matched.iterrows():
            rows.append(
                {
                    "event_id": EVENT_ID,
                    "timestamp_utc": iso_utc(row.get("created_at") or row.get("launch_day")),
                    "unit_id": f"pump_token:{row.get('mint', '')}",
                    "unit_type": "token_day",
                    "token_id": row.get("mint", ""),
                    "platform": "Pump.fun",
                    "chain": "Solana",
                    "frequency": "token_launch",
                    "covariate_family": "token_social_metadata",
                    "telegram_present": row.get("has_telegram", ""),
                    "twitter_present": row.get("has_twitter", ""),
                    "website_present": row.get("has_website", ""),
                    "any_social": row.get("has_any_social", ""),
                    "social_count": row.get("social_count", ""),
                    "description_length": row.get("description_length", ""),
                    "community_channel_indicator": row.get("has_any_social", ""),
                    "source_layer": relpath(red_path),
                    "claim_boundary": "Token social metadata is a covariate or mirror-case mechanism signal, not assigned treatment.",
                    "status": "computed_for_validation_token_subset",
                }
            )

    return pd.DataFrame(rows).reindex(columns=COVARIATE_COLUMNS)


def build_claim_scope() -> pd.DataFrame:
    base = read_csv(ROOT / "artifacts" / "tables" / "claim_scope_ledger.csv")
    clanker_summary = read_json(ROOT / "artifacts" / "tables" / "clanker_base_event_validation_summary.json")
    telegram_design = read_json(ROOT / "artifacts" / "tables" / "telegram_mirror_design_summary.json")
    clanker_cohort_tokens = int(clanker_summary.get("cohort_tokens", 0) or 0)
    clanker_holder_tokens = int(clanker_summary.get("holder_reconstruction_tokens", 0) or 0)
    cross_chain_status = clanker_summary.get("status", "") if clanker_summary.get("status", "").startswith("accepted") else "candidate_needs_validation"
    cross_chain_allowed = (
        f"Clanker/Base is accepted as an on-chain cross-chain validation case with {clanker_cohort_tokens} bounded matched cohort tokens, 1/7/30 day token-horizon rows, and holder concentration for {clanker_holder_tokens} tokens where logs are available."
        if clanker_summary.get("status", "").startswith("accepted")
        else "Clanker/Base is the highest-priority candidate for Shilin's cross-chain extension."
    )
    cross_chain_not_allowed = (
        "Do not claim platform-wide causal replication, welfare improvement, or general trader-protection effects from the bounded early-adoption sample."
        if clanker_summary.get("status", "").startswith("accepted")
        else "Do not claim cross-chain replication until activation evidence and comparable token horizons are computed."
    )
    rows = base.to_dict(orient="records") if not base.empty else []
    rows.extend(
        [
            {
                "claim_id": "H1-benchmark-release-shilin",
                "hypothesis": "H1 migration friction",
                "evidence_layer": "Shilin three-sheet benchmark release",
                "status": "release_candidate",
                "claim_allowed": "The Shilin package exposes events, metrics, covariates, claim boundaries, and data gaps as reusable benchmark artifacts.",
                "claim_not_allowed": "Do not treat registered gaps, cross-chain candidates, or mirror candidates as completed causal findings.",
            },
            {
                "claim_id": "mirror-case-telegram",
                "hypothesis": "H1/off-chain heterogeneity",
                "evidence_layer": "RED-PUMP social metadata, matched design, timing gate, and sensitivity check",
                "status": telegram_design.get("status", "preliminary_mechanism_candidate_not_causal"),
                "claim_allowed": (
                    "Telegram/social metadata is a credible matched mirror-case signal after launch-day, social, "
                    "market-cap, and description-bin adjustment; event-time diagnostics make the causal boundary stricter."
                    if telegram_design.get("status")
                    else "Telegram/social metadata is a strong candidate for a naive-near-null to adjusted-supported mirror case."
                ),
                "claim_not_allowed": (
                    "Do not claim a causal Telegram effect without an exogenous attention shock or stronger event-time design."
                    if telegram_design.get("status")
                    else "Do not claim a causal Telegram effect until token-level 7/30 day outcomes and controls are joined."
                ),
            },
            {
                "claim_id": "cross-chain-shilin",
                "hypothesis": "H4/cross-chain external validity",
                "evidence_layer": "Base Clanker v4.1 on-chain event plus BNB/TRON candidate registry",
                "status": cross_chain_status,
                "claim_allowed": cross_chain_allowed,
                "claim_not_allowed": cross_chain_not_allowed,
            },
        ]
    )
    return pd.DataFrame(rows)


def build_data_gaps() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    clanker_summary = read_json(ROOT / "artifacts" / "tables" / "clanker_base_event_validation_summary.json")
    clanker_scan = read_json(ROOT / "artifacts" / "tables" / "clanker_base_token_created_scan_summary.json")
    clanker_manifest = read_json(ROOT / "artifacts" / "tables" / "clanker_base_full_cohort_manifest_summary.json")
    clanker_backfill = read_json(ROOT / "artifacts" / "tables" / "clanker_base_full_cohort_backfill_summary.json")
    telegram_design = read_json(ROOT / "artifacts" / "tables" / "telegram_mirror_design_summary.json")
    telegram_exposure = read_json(ROOT / "artifacts" / "tables" / "telegram_exposure_design_summary.json")
    availability = read_csv(ROOT / "artifacts" / "tables" / "data_availability_ledger.csv")
    for _, row in availability.iterrows():
        available = str(row.get("available", ""))
        if available not in {"True", "computed", "computed_extension"}:
            rows.append(
                {
                    "gap_id": f"source:{row.get('source_key', '')}",
                    "sheet": "metrics_panel",
                    "event_id": EVENT_ID,
                    "unit": row.get("layer", ""),
                    "field_or_source": row.get("source_key", ""),
                    "status": available,
                    "reason": row.get("purpose", ""),
                    "claim_consequence": "Keep associated claims at proxy, sample, or registered-validation status.",
                    "next_action": "Run or validate the registered extraction path before moving the claim boundary.",
                }
            )
    rows.extend(
        [
            {
                "gap_id": "decoded-full-cohort-usd-volume",
                "sheet": "metrics_panel",
                "event_id": EVENT_ID,
                "unit": "token_horizon",
                "field_or_source": "volume_usd; active_traders; buy/sell direction",
                "status": "partial_moralis_sample_full_dune_gap",
                "reason": "Dune execution stopped at account datapoint limit; Moralis covers a selected sample.",
                "claim_consequence": "No full-cohort token-level welfare, USD-volume, or active-trader causal claim.",
                "next_action": "Run Dune, Helius Enhanced Transactions, Moralis, or Birdeye decoded export for all graduated tokens.",
            },
            {
                "gap_id": "same-cohort-early-wallet-h4",
                "sheet": "metrics_panel",
                "event_id": EVENT_ID,
                "unit": "token_wallet_horizon",
                "field_or_source": "early wallet concentration and sniper behavior",
                "status": "external_red_cohort_only",
                "reason": "RED-COHORT strengthens mechanism evidence but current mint overlap with RED-PUMP is zero.",
                "claim_consequence": "H4 remains proxy or external mechanism validation, not same-cohort causal evidence.",
                "next_action": "Export same-cohort early buyers from Dune or another decoded indexer and join on token_id.",
            },
            {
                "gap_id": "mirror-case-causal-identification",
                "sheet": "metrics_panel; covariates",
                "event_id": EVENT_ID,
                "unit": "token_horizon",
                "field_or_source": "Telegram/social metadata x 7/30 day decoded outcomes",
                "status": (
                    "partially_closed_by_matched_design_no_in_window_shock"
                    if telegram_design.get("status")
                    else "registered_gap"
                ),
                "reason": (
                    "Telegram now has a preregistered matched launch-metadata design, timing gate, sensitivity check, selected 1/7/30 day validation rows, and a public shock registry; no registered public shock currently overlaps the RED-PUMP launch window with enough support."
                    if telegram_design.get("status")
                    else "Current Telegram result is a strong association and mirror candidate, not an event-time causal design."
                ),
                "claim_consequence": (
                    "Use as a credible predictive/mechanism-supported mirror signal, not a causal Telegram effect."
                    if telegram_design.get("status")
                    else "Mirror case should be presented as preliminary until joined decoded outcomes and controls are available."
                ),
                "next_action": (
                    f"Extend the RED-PUMP social window or collect token-level Telegram exposure timestamps; current public-shock scan status is {telegram_exposure.get('status', 'missing')}."
                    if telegram_design.get("status")
                    else "Join token social covariates to decoded token horizons and re-run the ladder for social-cohort resilience."
                ),
            },
            {
                "gap_id": "cross-chain-accepted-event",
                "sheet": "events.csv",
                "event_id": clanker_summary.get("event_id", "CLANKER_SNIPER_DECAY_V41_BASE_CANDIDATE"),
                "unit": "Base launchpad event",
                "field_or_source": "activation timestamp, on-chain rollout, token horizons",
                "status": (
                    clanker_summary.get("status", "closed_for_onchain_sample")
                    if clanker_summary.get("status", "").startswith("accepted")
                    else "candidate_needs_validation"
                ),
                "reason": (
                    f"First Clanker v4.1 MEV-module TokenCreated log, {clanker_summary.get('token_created_rows', '')} TokenCreated rows, {clanker_summary.get('version_class_counts', {}).get('v4.1_mev_or_hook', '')} v4.1 treated launches, matched 1/7/30 day PoolManager outcomes, and holder concentration rows are computed where logs are available."
                    if clanker_summary.get("status", "").startswith("accepted")
                    else "Base candidate exists but is not yet verified as platform-wide treatment."
                ),
                "claim_consequence": (
                    "Cross-chain event architecture requirement is met for an on-chain matched sample; platform-wide causal replication remains blocked."
                    if clanker_summary.get("status", "").startswith("accepted")
                    else "Cross-chain external validity remains a planned extension rather than a completed empirical case."
                ),
                "next_action": (
                    "Extend the bounded Base sample with archive/indexer coverage, complete holder-level outcomes for every selected token/horizon, and add full-cohort causal diagnostics."
                    if clanker_summary.get("status", "").startswith("accepted")
                    else "Validate Clanker factory rollout and compute 1/7/30 day Base token outcomes."
                ),
            },
            {
                "gap_id": "cross-chain-full-cohort-causal-replication",
                "sheet": "metrics_panel",
                "event_id": clanker_summary.get("event_id", CLANKER_BASE_EVENT_ID),
                "unit": "Base token_horizon full cohort",
                "field_or_source": "matched v4.0/v4.1 cohorts; holder concentration; larger active-trader outcomes",
                "status": "registered_gap",
                "reason": (
                    f"Current validated Base run is a bounded on-chain/import-compatible matched sample with {clanker_summary.get('cohort_tokens', '')} selected tokens and "
                    f"{clanker_summary.get('holder_reconstruction_tokens', '')} holder-reconstructed tokens. The latest TokenCreated discovery scan covers "
                    f"{clanker_scan.get('token_created_rows', clanker_summary.get('token_created_rows', ''))} launches and "
                    f"{clanker_scan.get('version_class_counts', {}).get('v4.1_mev_or_hook', clanker_summary.get('version_class_counts', {}).get('v4.1_mev_or_hook', ''))} v4.1 rows. "
                    f"The full-cohort archive/indexer manifest now enumerates {clanker_manifest.get('cohort_tokens', 'missing')} matched token rows and "
                    f"{clanker_manifest.get('expected_horizon_rows', 'missing')} expected 1/7/30 day horizon rows. "
                    f"Current backfill has {clanker_backfill.get('swap_import_rows', 0)} swap import rows and "
                    f"{clanker_backfill.get('transfer_import_rows', 0)} transfer import rows."
                ),
                "claim_consequence": "No platform-wide Clanker v4.1 causal replication claim yet.",
                "next_action": "Fill the full-cohort manifest with archive RPC or Bitquery/Dune swap and transfer exports, then run the import path to compute full holder reconstruction and causal diagnostics.",
            },
        ]
    )
    return pd.DataFrame(rows)


def build_cross_chain_candidates() -> pd.DataFrame:
    clanker_summary = read_json(ROOT / "artifacts" / "tables" / "clanker_base_event_validation_summary.json")
    clanker_scan = read_json(ROOT / "artifacts" / "tables" / "clanker_base_token_created_scan_summary.json")
    clanker_manifest = read_json(ROOT / "artifacts" / "tables" / "clanker_base_full_cohort_manifest_summary.json")
    if clanker_summary.get("status", "").startswith("accepted"):
        clanker_status = clanker_summary.get("status", "accepted_onchain_sample")
        clanker_evidence = (
            f"Base public JSON-RPC finds first v4.1 MEV-module TokenCreated at "
            f"{clanker_summary.get('activation_timestamp_utc')} in tx "
            f"{clanker_summary.get('activation_transaction_hash')}; "
            f"search window has {clanker_summary.get('token_created_rows')} TokenCreated rows and "
            f"{clanker_summary.get('version_class_counts', {}).get('v4.1_mev_or_hook')} v4.1 rows; "
            f"matched cohort has {clanker_summary.get('cohort_tokens')} selected tokens with holder reconstruction for "
            f"{clanker_summary.get('holder_reconstruction_tokens')} tokens. Latest discovery scan has "
            f"{clanker_scan.get('token_created_rows', 'missing')} TokenCreated rows and "
            f"{clanker_scan.get('version_class_counts', {}).get('v4.1_mev_or_hook', 'missing')} v4.1 rows. "
            f"Full-cohort indexer manifest is prepared for {clanker_manifest.get('cohort_tokens', 'missing')} matched token rows and "
            f"{clanker_manifest.get('expected_horizon_rows', 'missing')} expected horizon rows."
        )
        clanker_next_action = (
            "Scale from the validated bounded matched sample to the discovered full Base cohort with archive/indexer swap coverage, full holder reconstruction, and full-cohort causal diagnostics."
        )
    else:
        clanker_status = "candidate_needs_onchain_validation"
        clanker_evidence = (
            "First-party docs list Base v4.1 sniper-auction contracts and v4 MEV modules; "
            "Bitquery provides a Base Clanker TokenCreated event-query path."
        )
        clanker_next_action = (
            "Timestamp the first eligible v4.1/default-configuration activation, verify adoption share from factory events, "
            "and build Base token-horizon outcomes before accepting the event."
        )
    return pd.DataFrame(
        [
            {
                "candidate_id": "CLANKER_SNIPER_DECAY_V41_BASE",
                "platform": "Clanker",
                "chain": "Base",
                "rule_family": "trader_protection",
                "candidate_event": "v4 MEV/sniper-protection module rollout or default-configuration change",
                "current_evidence": clanker_evidence,
                "comparability_to_shilin_schema": "event_id, token_id, timestamp, 1/7/30d outcomes, early-wallet concentration, claim_boundary",
                "priority": "high",
                "status": clanker_status,
                "next_action": clanker_next_action,
                "source_urls": (
                    "https://github.com/clanker-devco/DOCS; "
                    "https://docs.bitquery.io/docs/blockchain/Base/base-clanker-api/"
                ),
            },
            {
                "candidate_id": "FOUR_MEME_BNB",
                "platform": "Four.meme",
                "chain": "BNB Chain",
                "rule_family": "entry_incentive_or_product_option",
                "candidate_event": "BNB launchpad rule event to be discovered",
                "current_evidence": "Project notes list it as a target platform; no event accepted.",
                "comparability_to_shilin_schema": "Same event registry and fixed token horizons if a dated rule event is found.",
                "priority": "medium",
                "status": "discovery_needed",
                "next_action": "Search first-party policy records and Dune/Bitquery schema feasibility.",
                "source_urls": "",
            },
            {
                "candidate_id": "SUNPUMP_TRON",
                "platform": "SunPump",
                "chain": "TRON",
                "rule_family": "entry_incentive_or_fee_incidence",
                "candidate_event": "TRON launchpad rule event to be discovered",
                "current_evidence": "Project notes list it as a target platform; no event accepted.",
                "comparability_to_shilin_schema": "Same event registry and fixed token horizons if transaction coverage is available.",
                "priority": "medium",
                "status": "discovery_needed",
                "next_action": "Validate lifecycle data, transaction coverage, and social-channel availability.",
                "source_urls": "",
            },
        ]
    )


def build_mirror_candidates() -> pd.DataFrame:
    red = read_json(ROOT / "artifacts" / "tables" / "red_pump_result1_summary.json")
    design = read_json(ROOT / "artifacts" / "tables" / "telegram_mirror_design_summary.json")
    exposure = read_json(ROOT / "artifacts" / "tables" / "telegram_exposure_design_summary.json")
    if design.get("status"):
        ci = design.get("cluster_bootstrap_ci95", [float("nan"), float("nan")])
        current_decision = "credible_matched_design_not_causal"
        adjusted_read = (
            f"Matched design supports {design.get('n_treated_matched_supported', 0):,} Telegram tokens "
            f"({design.get('treated_support_share', float('nan')):.2%} support), with matched ATT "
            f"{design.get('matched_att', 0) * 100:.3f} pp, CI [{float(ci[0]) * 100:.3f}, "
            f"{float(ci[1]) * 100:.3f}] pp, and E-value {design.get('e_value', float('nan')):.2f}."
        )
        blocking_gap = (
            "Matched ATT remains vulnerable to unobserved creator quality and off-platform promotion; "
            "immediate event-time signals look too fast for a clean Telegram diffusion mechanism; "
            f"{exposure.get('candidate_shocks', 0)} public shock candidates were registered, but "
            f"{exposure.get('supported_shocks', 0)} exogenous shocks overlap the RED-PUMP launch window with enough support."
        )
        next_action = "Collect token-level Telegram exposure timestamps, full-cohort decoded 7/30 day outcomes, or extend the RED-PUMP launch window to overlap a validated public Telegram shock."
    else:
        current_decision = "preliminary_mechanism_candidate_not_causal"
        adjusted_read = (
            f"Telegram-linked tokens graduate at {red.get('telegram_graduation_rate', 0):.4%} versus "
            f"{red.get('no_telegram_graduation_rate', 0):.4%} without Telegram; stakeholder battery reports "
            "a 1.227 pp association with CI [0.010642, 0.013895]."
        )
        blocking_gap = "Social metadata may proxy for unobserved project quality; this is not a causal design until joined 7/30 day decoded event-time outcomes are available."
        next_action = "Join social metadata to decoded token horizons and test whether social cohorts show relative resilience under market shocks."
    return pd.DataFrame(
        [
            {
                "candidate_id": "TELEGRAM_GRADUATION_HETEROGENEITY",
                "event_id": EVENT_ID,
                "unit": "token",
                "naive_read": (
                    f"Overall graduation is {red.get('graduation_rate', 0):.4%}, so a market-only quality read looks near-null."
                ),
                "adjusted_or_stratified_read": adjusted_read,
                "current_decision": current_decision,
                "why_it_is_mirror_like": "A naive near-null quality frame becomes a supported off-chain heterogeneity signal after token-level measurement.",
                "blocking_gap": blocking_gap,
                "next_action": next_action,
            },
            {
                "candidate_id": "SHORT_WINDOW_RELATIVE_MARKET_RESILIENCE",
                "event_id": EVENT_ID,
                "unit": "platform_day",
                "naive_read": "The 90-day trustworthy market estimate is uncertain after controls and few-cluster inference.",
                "adjusted_or_stratified_read": "30/45/60/75-day TWFE sensitivity rows are positive and statistically supported, but this is window-sensitive.",
                "current_decision": "not_selected_as_final_mirror_case",
                "why_it_is_mirror_like": "Relative adjustment strengthens support in shorter windows.",
                "blocking_gap": "The simple before-after view is already positive, so it does not cleanly satisfy naive-null to supported-effect framing.",
                "next_action": "Keep as robustness context rather than the main mirror case.",
            },
        ]
    )


def _format_pct(value: float) -> str:
    if pd.isna(value):
        return "missing"
    return f"{value:.3%}"


def _format_pp(value: float) -> str:
    if pd.isna(value):
        return "missing"
    return f"{value * 100:.3f} pp"


def build_mirror_case_ladder() -> pd.DataFrame:
    red = read_json(ROOT / "artifacts" / "tables" / "red_pump_result1_summary.json")
    design_summary = read_json(ROOT / "artifacts" / "tables" / "telegram_mirror_design_summary.json")
    exposure_summary = read_json(ROOT / "artifacts" / "tables" / "telegram_exposure_design_summary.json")
    design = read_csv(ROOT / "artifacts" / "tables" / "telegram_mirror_design.csv")
    lpm = read_csv(
        SRS_ROOT
        / "01_Pumpfun_PumpSwap_Project"
        / "pumpfun_pumpswap_did_mvp_full_local"
        / "results"
        / "tables"
        / "red_pump_social_lpm_results.csv"
    )
    lpm_meta = read_json(
        SRS_ROOT
        / "01_Pumpfun_PumpSwap_Project"
        / "pumpfun_pumpswap_did_mvp_full_local"
        / "results"
        / "tables"
        / "red_pump_social_lpm_metadata.json"
    )
    telegram_row = (
        lpm.loc[lpm["variable"].eq("has_telegram")].iloc[0].to_dict()
        if not lpm.empty and len(lpm.loc[lpm["variable"].eq("has_telegram")])
        else {}
    )

    rpc = read_csv(ROOT / "artifacts" / "external_validation" / "h1_rpc_token_level_outcomes.csv")
    moralis = read_csv(ROOT / "artifacts" / "external_validation" / "moralis_decoded_token_outcomes.csv")
    config = load_config()
    red_path = source_path(config, "red_pump_token_outcomes")
    social = read_csv(
        red_path,
        usecols=lambda c: c in {"mint", "has_telegram", "has_any_social", "social_count"},
        low_memory=False,
    )

    rpc_note = "RPC social join not available."
    if not rpc.empty and not social.empty:
        joined_rpc = rpc.merge(social, on="mint", how="left")
        by_tel = joined_rpc.groupby("has_telegram", dropna=False).agg(
            tokens=("mint", "nunique"),
            median_swaps=("swap_count_30d", "median"),
            active_share=("active_30d", "mean"),
        )
        if {0, 1}.issubset(set(by_tel.index.dropna().astype(int))):
            no_tel = by_tel.loc[0]
            tel = by_tel.loc[1]
            rpc_note = (
                f"RPC 30d join covers {int(no_tel['tokens'] + tel['tokens'])} graduated tokens; "
                f"Telegram median pool-tx proxy {tel['median_swaps']:.0f} vs "
                f"{no_tel['median_swaps']:.0f} without Telegram, with active shares "
                f"{tel['active_share']:.3f} vs {no_tel['active_share']:.3f}."
            )

    moralis_note = "Moralis social join not available."
    if not moralis.empty and not social.empty:
        m30 = moralis.loc[pd.to_numeric(moralis["horizon_days"], errors="coerce").eq(30)].copy()
        joined_moralis = m30.merge(social, on="mint", how="left")
        by_tel_m = joined_moralis.groupby("has_telegram", dropna=False).agg(
            tokens=("mint", "nunique"),
            median_volume=("decoded_volume_usd", "median"),
            median_active=("decoded_active_traders", "median"),
        )
        if {0, 1}.issubset(set(by_tel_m.index.dropna().astype(int))):
            no_tel_m = by_tel_m.loc[0]
            tel_m = by_tel_m.loc[1]
            moralis_note = (
                f"Moralis 30d decoded sample covers {int(no_tel_m['tokens'] + tel_m['tokens'])} tokens; "
                f"Telegram median USD volume ${tel_m['median_volume']:,.0f} vs "
                f"${no_tel_m['median_volume']:,.0f}, and median active traders "
                f"{tel_m['median_active']:.1f} vs {no_tel_m['median_active']:.1f}."
            )

    graduation_rate = float(red.get("graduation_rate", np.nan))
    telegram_rate = float(red.get("telegram_graduation_rate", np.nan))
    no_telegram_rate = float(red.get("no_telegram_graduation_rate", np.nan))
    raw_gap = telegram_rate - no_telegram_rate
    controlled_gap = float(telegram_row.get("coef_probability_points", np.nan))
    ci_low = float(telegram_row.get("ci95_low", np.nan))
    ci_high = float(telegram_row.get("ci95_high", np.nan))
    matched_row = (
        design.loc[design["stage"].eq("D1_coarsened_exact_match")].iloc[0].to_dict()
        if not design.empty and len(design.loc[design["stage"].eq("D1_coarsened_exact_match")])
        else {}
    )
    sensitivity_row = (
        design.loc[design["stage"].eq("D3_sensitivity")].iloc[0].to_dict()
        if not design.empty and len(design.loc[design["stage"].eq("D3_sensitivity")])
        else {}
    )
    immediate_row = (
        design.loc[design["stage"].eq("D6a_immediate_5m_placebo_like_check")].iloc[0].to_dict()
        if not design.empty and len(design.loc[design["stage"].eq("D6a_immediate_5m_placebo_like_check")])
        else {}
    )
    delayed_row = (
        design.loc[design["stage"].eq("D6d_delayed_after_60m_timing_check")].iloc[0].to_dict()
        if not design.empty and len(design.loc[design["stage"].eq("D6d_delayed_after_60m_timing_check")])
        else {}
    )
    negative_control_row = (
        design.loc[design["stage"].eq("D7_negative_control_detection_lag")].iloc[0].to_dict()
        if not design.empty and len(design.loc[design["stage"].eq("D7_negative_control_detection_lag")])
        else {}
    )

    rows = [
        {
            "case_id": "CASE_B_TELEGRAM_SOCIAL_METADATA_PRELIMINARY",
            "rung": "B0",
            "component_added": "Naive market-only quality read",
            "estimand_or_check": "Overall RED-PUMP graduation rate",
            "estimate": graduation_rate,
            "estimate_label": _format_pct(graduation_rate),
            "decision": "naive_near_null",
            "claim_boundary": "A near-zero aggregate graduation rate does not reveal which token types survive.",
            "source_artifact": "artifacts/tables/red_pump_result1_summary.json",
        },
        {
            "case_id": "CASE_B_TELEGRAM_SOCIAL_METADATA_PRELIMINARY",
            "rung": "B1",
            "component_added": "Pre-outcome social metadata stratum",
            "estimand_or_check": "Telegram-present tokens compared with non-Telegram tokens",
            "estimate": raw_gap,
            "estimate_label": (
                f"{_format_pct(telegram_rate)} vs {_format_pct(no_telegram_rate)}; "
                f"raw gap {_format_pp(raw_gap)}"
            ),
            "decision": "stratified_signal",
            "claim_boundary": "Telegram is observed metadata, not randomized assignment.",
            "source_artifact": "RED-PUMP token outcomes",
        },
        {
            "case_id": "CASE_B_TELEGRAM_SOCIAL_METADATA_PRELIMINARY",
            "rung": "B2",
            "component_added": "Controlled token-level LPM",
            "estimand_or_check": "has_telegram coefficient with launch-day fixed effects and token covariates",
            "estimate": controlled_gap,
            "estimate_label": (
                f"{_format_pp(controlled_gap)}; CI [{_format_pp(ci_low)}, {_format_pp(ci_high)}]; "
                f"n={int(lpm_meta.get('n', 0) or 0):,}"
            ),
            "decision": "supported_association_after_controls",
            "claim_boundary": "Controls reduce but do not remove project-quality confounding.",
            "source_artifact": "results/tables/red_pump_social_lpm_results.csv",
        },
        {
            "case_id": "CASE_B_TELEGRAM_SOCIAL_METADATA_PRELIMINARY",
            "rung": "B3",
            "component_added": "Joined 30d token-horizon validation",
            "estimand_or_check": "RPC and Moralis 30d outcomes stratified by Telegram metadata",
            "estimate": "",
            "estimate_label": f"{rpc_note} {moralis_note}",
            "decision": "mechanism_consistent_but_selected",
            "claim_boundary": "Decoded sample is selected toward high-activity tokens; RPC is a transaction proxy.",
            "source_artifact": "h1_rpc_token_level_outcomes.csv; moralis_decoded_token_outcomes.csv",
        },
        {
            "case_id": "CASE_B_TELEGRAM_SOCIAL_METADATA_PRELIMINARY",
            "rung": "B4",
            "component_added": "Preregistered matched design and sensitivity check",
            "estimand_or_check": "Coarsened exact matched ATT for Telegram-present launch metadata",
            "estimate": matched_row.get("effect", ""),
            "estimate_label": (
                f"Matched ATT {_format_pp(float(matched_row.get('effect', np.nan)))}; "
                f"CI [{_format_pp(float(matched_row.get('ci95_low', np.nan)))}, "
                f"{_format_pp(float(matched_row.get('ci95_high', np.nan)))}]; "
                f"support {design_summary.get('treated_support_share', float('nan')):.2%}; "
                f"E-value {float(sensitivity_row.get('sensitivity_value', np.nan)):.2f}"
            )
            if matched_row
            else "Matched design not yet run.",
            "decision": design_summary.get("status", "matched_design_not_available"),
            "claim_boundary": (
                "A naive ambiguous result becomes a robust predictive/mechanism-supported signal after matching, "
                "controls, and sensitivity checks; causal boundary remains explicit."
            ),
            "source_artifact": "artifacts/tables/telegram_mirror_design.csv",
        },
        {
            "case_id": "CASE_B_TELEGRAM_SOCIAL_METADATA_PRELIMINARY",
            "rung": "B5",
            "component_added": "Event-time and negative-control diagnostics",
            "estimand_or_check": "Immediate 5m outcome, delayed >60m outcome, and detection-lag negative control",
            "estimate": delayed_row.get("effect", ""),
            "estimate_label": (
                f"Immediate <=5m ATT {_format_pp(float(immediate_row.get('effect', np.nan)))}; "
                f"delayed >60m ATT {_format_pp(float(delayed_row.get('effect', np.nan)))}; "
                f"detection-lag difference {float(negative_control_row.get('effect', np.nan)):.3f} minutes."
            )
            if delayed_row
            else "Event-time diagnostics not yet run.",
            "decision": design_summary.get("event_time_diagnostics", {}).get(
                "causal_timing_interpretation",
                "event_time_diagnostics_not_available",
            ),
            "claim_boundary": (
                "Timing diagnostics improve the design audit; the immediate signal is a confounding warning and does not identify an exogenous Telegram exposure shock."
            ),
            "source_artifact": "artifacts/tables/telegram_mirror_design.csv",
        },
        {
            "case_id": "CASE_B_TELEGRAM_SOCIAL_METADATA_PRELIMINARY",
            "rung": "B6",
            "component_added": "Claim-boundary gate",
            "estimand_or_check": "Is this a causal mirror case?",
            "estimate": "",
            "estimate_label": (
                f"Not yet: {exposure_summary.get('candidate_shocks', 0)} public shock candidates registered, "
                f"{exposure_summary.get('supported_shocks', 0)} supported inside the RED-PUMP window."
            ),
            "decision": "credible_mirror_signal_not_final_causal_case",
            "claim_boundary": "Use as a top-conference mirror design signal, not as a completed causal Telegram effect.",
            "source_artifact": "benchmark_release/data/telegram_shock_candidates.csv; benchmark_release/data/data_gap_ledger.csv",
        },
    ]
    return pd.DataFrame(rows)


def build_telegram_mirror_design() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "tables" / "telegram_mirror_design.csv")


def build_telegram_mirror_balance() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "tables" / "telegram_mirror_balance.csv")


def build_telegram_mirror_matched_cells() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "tables" / "telegram_mirror_matched_cells.csv")


def build_telegram_exposure_design() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "tables" / "telegram_exposure_design.csv")


def build_telegram_shock_candidates() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "external_validation" / "telegram_shock_candidates.csv")


def build_paired_case_ladder() -> pd.DataFrame:
    ladder = read_csv(ROOT / "artifacts" / "tables" / "deterministic_ladder.csv")
    mirror = build_mirror_case_ladder()
    if ladder.empty or mirror.empty:
        return pd.DataFrame()

    def ladder_row(rung: str) -> dict[str, Any]:
        rows = ladder.loc[ladder["rung"].eq(rung)]
        return rows.iloc[0].to_dict() if len(rows) else {}

    def mirror_row(rung: str) -> dict[str, Any]:
        rows = mirror.loc[mirror["rung"].eq(rung)]
        return rows.iloc[0].to_dict() if len(rows) else {}

    stages = [
        ("S0", "Naive read", "L0", "B0", "Case A starts as a positive dashboard result; Case B starts as a near-null aggregate quality read."),
        ("S1", "Comparison or strata", "L1", "B1", "Adding a comparison weakens Case A but stratification reveals a Case B signal."),
        ("S2", "Controls or model", "L2", "B2", "Fixed effects leave Case A uncertain; token-level controls keep Case B positive."),
        ("S3", "Outcome depth", "L3", "B3", "Dynamic or token-horizon evidence is informative but does not by itself close claim boundaries."),
        ("S4", "Diagnostic screen", "L4", "B5", "Pretrend and timing diagnostics constrain both cases before final claims."),
        ("S5", "Inference or sensitivity", "L6", "B4", "Few-cluster inference makes Case A uncertain; matching and sensitivity support Case B as predictive."),
        ("S6", "Claim boundary", "L7", "B6", "The same ladder produces opposite revisions while preventing welfare or Telegram-causality overclaims."),
    ]
    rows = []
    for order, (stage_id, requirement, case_a_rung, case_b_rung, interpretation) in enumerate(stages):
        a = ladder_row(case_a_rung)
        b = mirror_row(case_b_rung)
        rows.append(
            {
                "paired_stage": stage_id,
                "stage_order": order,
                "evidence_requirement": requirement,
                "case_a_id": "CASE_A_PUMPSWAP_MARKET",
                "case_a_rung": case_a_rung,
                "case_a_component": a.get("component_added", ""),
                "case_a_estimate": a.get("estimate", ""),
                "case_a_ci95_low": a.get("ci95_low", ""),
                "case_a_ci95_high": a.get("ci95_high", ""),
                "case_a_decision": a.get("worked_decision", ""),
                "case_a_claim_boundary": a.get("notes", ""),
                "case_b_id": "CASE_B_TELEGRAM_SOCIAL_METADATA_PRELIMINARY",
                "case_b_rung": case_b_rung,
                "case_b_component": b.get("component_added", ""),
                "case_b_estimate": b.get("estimate", ""),
                "case_b_estimate_label": b.get("estimate_label", ""),
                "case_b_decision": b.get("decision", ""),
                "case_b_claim_boundary": b.get("claim_boundary", ""),
                "paired_interpretation": interpretation,
                "figure_artifact": "artifacts/figures/fig_paired_case_ladder_shilin.png",
            }
        )
    return pd.DataFrame(rows)


def build_clanker_full_cohort_manifest() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "external_validation" / "clanker_base_full_cohort_manifest.csv")


def build_clanker_full_cohort_pool_query_bounds() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "external_validation" / "clanker_base_full_cohort_pool_query_bounds.csv")


def build_clanker_full_cohort_transfer_query_bounds() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "external_validation" / "clanker_base_full_cohort_transfer_query_bounds.csv")


def build_clanker_full_cohort_expected_horizons() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "external_validation" / "clanker_base_full_cohort_expected_horizons.csv")


def build_clanker_full_cohort_import_contract() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "external_validation" / "clanker_base_full_cohort_import_contract.csv")


def build_clanker_full_cohort_import_coverage() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "external_validation" / "clanker_base_full_cohort_import_coverage.csv")


def build_clanker_base_causal_diagnostics() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "tables" / "clanker_base_causal_diagnostics.csv")


def build_full_cohort_coverage_audit() -> pd.DataFrame:
    manifest = read_csv(ROOT / "artifacts" / "external_validation" / "clanker_base_full_cohort_manifest.csv")
    expected = read_csv(ROOT / "artifacts" / "external_validation" / "clanker_base_full_cohort_expected_horizons.csv")
    coverage = read_csv(ROOT / "artifacts" / "external_validation" / "clanker_base_full_cohort_import_coverage.csv")
    backfill = read_json(ROOT / "artifacts" / "tables" / "clanker_base_full_cohort_backfill_summary.json")
    manifest_rows = int(len(manifest))
    expected_rows = int(len(expected))
    rows = []
    for coverage_type in ["poolmanager_swaps", "erc20_transfers"]:
        subset = coverage.loc[coverage.get("coverage_type", pd.Series(dtype=str)).astype(str).eq(coverage_type)]
        summary = backfill.get("coverage_by_type", {}).get(coverage_type, {})
        processed_units = int(summary.get("processed_units", len(subset)) or 0)
        observed_rows = int(summary.get("observed_rows", subset.get("observed_rows", pd.Series(dtype=float)).sum()) or 0)
        processed_share = float(summary.get("processed_share_of_manifest", processed_units / manifest_rows if manifest_rows else 0) or 0)
        rows.append(
            {
                "event_id": CLANKER_BASE_EVENT_ID,
                "coverage_type": coverage_type,
                "manifest_rows": manifest_rows,
                "expected_horizon_rows": expected_rows,
                "processed_units": processed_units,
                "units_with_observed_rows": int(summary.get("units_with_observed_rows", 0) or 0),
                "observed_rows": observed_rows,
                "processed_share_of_manifest": processed_share,
                "coverage_status": "partial_smoke_and_sample_import" if processed_share < 1 else "complete",
                "claim_boundary": (
                    "Full-cohort Base causal replication remains blocked until this coverage type is processed for every manifest row."
                ),
                "next_action": "Fill the import contract with archive RPC, Dune, Bitquery, or equivalent Base indexer exports.",
            }
        )
    rows.append(
        {
            "event_id": CLANKER_BASE_EVENT_ID,
            "coverage_type": "token_horizon_expected_rows",
            "manifest_rows": manifest_rows,
            "expected_horizon_rows": expected_rows,
            "processed_units": int(min(row.get("processed_units", 0) for row in rows) if rows else 0),
            "units_with_observed_rows": "",
            "observed_rows": "",
            "processed_share_of_manifest": float(min(row.get("processed_share_of_manifest", 0) for row in rows) if rows else 0),
            "coverage_status": "registered_expected_rows_not_full_cohort_outcomes",
            "claim_boundary": "Expected 1/7/30 day rows are release contracts, not observed full-cohort outcomes.",
            "next_action": "Re-run run_clanker_base_validation.py with completed swap and transfer imports, then rebuild diagnostics.",
        }
    )
    return pd.DataFrame(rows)


def build_teacher_requirements_alignment() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "tables" / "teacher_requirements_alignment_shilin.csv")


def build_agentic_panel() -> pd.DataFrame:
    scores = read_csv(ROOT / "artifacts" / "tables" / "agentic_arm_scores.csv")
    ladder = read_csv(ROOT / "artifacts" / "tables" / "deterministic_ladder.csv")
    prompts = read_csv(ROOT / "artifacts" / "tables" / "agentic_prompt_manifest.csv")
    if scores.empty:
        return pd.DataFrame()
    out = scores.merge(ladder[["rung", "worked_decision", "estimate", "ci95_low", "ci95_high"]], on="rung", how="left")
    if not prompts.empty:
        out = out.merge(prompts[["rung", "prompt_hash", "data_access", "scaffold"]], on="rung", how="left")
    out.insert(0, "event_id", EVENT_ID)
    out["claim_boundary"] = "Evaluates agent evidence behavior by rung; model outputs are not causal evidence."
    return out


def build_agentic_ablation_manifest() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "tables" / "agentic_multimodel_ablation_manifest.csv")


def build_agentic_ablation_scores() -> pd.DataFrame:
    return read_csv(ROOT / "artifacts" / "tables" / "agentic_multimodel_ablation_scores.csv")


def build_data_dictionary() -> pd.DataFrame:
    rows = [
        ("events.csv", "event_id", "string", "Stable event key used to join release sheets."),
        ("events.csv", "eligibility_status", "category", "accepted, rejected, or conditional eligibility."),
        ("metrics_panel.csv", "unit_id", "string", "Platform-day, token-horizon, or token-cohort unit key."),
        ("metrics_panel.csv", "token_id", "string", "Token mint when row is token-level."),
        ("metrics_panel.csv", "horizon_days", "integer", "Fixed outcome horizon, especially 1, 7, and 30 days."),
        ("metrics_panel.csv", "claim_boundary", "string", "Formal limit on what the row can support."),
        ("metrics_panel.csv", "buy_count", "integer", "Decoded buy count when available from an indexer sample."),
        ("metrics_panel.csv", "sell_count", "integer", "Decoded sell count when available from an indexer sample."),
        ("metrics_panel.csv", "first_trade_at", "timestamp", "First observed trade or pool transaction inside the row window."),
        ("metrics_panel.csv", "last_trade_at", "timestamp", "Last observed trade or pool transaction inside the row window."),
        ("metrics_panel.csv", "holder_concentration_top10", "float", "Top-10 holder concentration when wallet or ERC20 holder reconstruction is available."),
        ("metrics_panel.csv", "holder_count", "integer", "Number of positive-balance holders in reconstructed token holder snapshots when available."),
        ("metrics_panel.csv", "early_sender_concentration_top10", "float", "Top-10 swap-caller concentration in the first 60 seconds for bounded Base samples."),
        ("artifacts/external_validation/clanker_base_pool_swaps_raw.csv", "pool_id", "string", "Raw Base Uniswap v4 PoolManager pool identifier used to rebuild Clanker token-horizon swaps."),
        ("artifacts/external_validation/clanker_base_token_transfers_raw.csv", "token_id", "string", "Raw Base ERC20 token address used to rebuild holder concentration snapshots."),
        ("covariates.csv", "covariate_family", "category", "Social metadata, Discord, TVL, or RWA context."),
        ("covariates.csv", "telegram_present", "0/1", "Token-level Telegram metadata indicator when available."),
        ("mirror_case_ladder.csv", "decision", "category", "Per-rung status for the preliminary Telegram/social mirror case."),
        ("telegram_mirror_design.csv", "decision", "category", "Matched-design stage decision and claim boundary."),
        ("telegram_mirror_balance.csv", "standardized_mean_difference", "float", "Full and matched balance diagnostics for Telegram design covariates."),
        ("telegram_exposure_design.csv", "shock_id", "string", "Public Telegram shock used for exposure-design rows when supported."),
        ("telegram_shock_candidates.csv", "supported_for_exposure_design", "boolean", "Whether a public Telegram shock overlaps the RED-PUMP launch window with enough support."),
        ("agentic_multimodel_ablation_manifest.csv", "ablation_id", "string", "Registered baseline or leave-one-scaffold-out agentic condition."),
        ("agentic_multimodel_ablation_scores.csv", "ok_runs", "integer", "Successful real model outputs scored for a provider/model/rung/ablation cell."),
        ("agentic_multimodel_ablation_scores.csv", "method_omission_rate", "float", "Mean omission rate across control, pretrend, stakeholder, and uncertainty mentions."),
        ("clanker_base_full_cohort_manifest.csv", "token_id", "string", "Matched Base token row requiring archive/indexer outcome coverage."),
        ("clanker_base_full_cohort_pool_query_bounds.csv", "pool_id", "string", "PoolManager pool query key for full-cohort swap export."),
        ("clanker_base_full_cohort_transfer_query_bounds.csv", "contract_address", "string", "ERC20 token contract query key for full holder reconstruction."),
        ("clanker_base_full_cohort_expected_horizons.csv", "unit_id", "string", "Expected Base token-horizon row to fill after archive/indexer import."),
        ("clanker_base_full_cohort_import_contract.csv", "required_columns", "string", "CSV columns required by the full-cohort import path."),
        ("clanker_base_full_cohort_import_coverage.csv", "coverage_status", "category", "Processed-row status for full-cohort swap and transfer backfill units."),
        ("clanker_base_causal_diagnostics.csv", "att_mean_pair_diff", "float", "Matched-pair v4.1-minus-v4.0 difference for covered Base sample rows."),
        ("solana_early_wallet_concentration.csv", "decoded_buyer_proxy_wallets", "integer", "Unique fee-payer wallets conservatively classified as early buyer proxies from Solana token-balance deltas."),
        ("solana_early_wallet_concentration.csv", "decoded_holder_proxy_wallets", "integer", "Unique fee-payer wallets conservatively classified as early holder proxies from Solana post-token balances."),
        ("solana_early_wallet_concentration.csv", "classified_early_transactions", "integer", "Early pool transactions with decoded buyer/seller/holder proxy labels; unclassified rows remain claim-bounded."),
        ("solana_parsed_transaction_proxies.csv", "buyer_holder_classification", "category", "Per-transaction conservative fee-payer buyer/seller/holder proxy label from token-balance changes."),
        ("solana_parsed_transaction_proxies.csv", "classification_source", "string", "Decoder source used for the buyer/holder proxy classification, usually Solana pre/post token balances."),
        ("teacher_requirements_alignment_shilin.csv", "status", "category", "Shilin-only status against Luyao's revision requirements."),
        ("paired_case_ladder.csv", "paired_interpretation", "string", "Same-ladder interpretation linking Case A and Case B at each evidence stage."),
        ("full_cohort_coverage_audit.csv", "processed_share_of_manifest", "float", "Share of Clanker/Base full-cohort manifest units processed by coverage type."),
        ("requirement_closure_audit.csv", "top_conference_status", "category", "Whether the requirement is closed for workshop review or still a top-conference gap."),
        ("top_conference_gap_ledger.csv", "experiment_to_close", "string", "Concrete experiment or credentialed data pull needed for top-tier causal claims."),
        ("claim_scope_ledger.csv", "claim_not_allowed", "string", "Explicit claims blocked by current evidence."),
        ("data_gap_ledger.csv", "next_action", "string", "Concrete validation step needed to close the gap."),
    ]
    return pd.DataFrame(rows, columns=["sheet", "field", "type", "description"])


def build_requirement_closure_audit() -> pd.DataFrame:
    alignment = build_teacher_requirements_alignment()
    lookup = {row["ownership_item"]: row for row in alignment.to_dict("records")} if not alignment.empty else {}
    paired = build_paired_case_ladder()
    coverage = build_full_cohort_coverage_audit()
    min_base_coverage = (
        float(pd.to_numeric(coverage["processed_share_of_manifest"], errors="coerce").dropna().min())
        if not coverage.empty
        else 0.0
    )

    def from_alignment(item: str, default_status: str = "gap") -> tuple[str, str]:
        row = lookup.get(item, {})
        return str(row.get("status", default_status)), str(row.get("evidence_or_gap", ""))

    rows = []
    specs = [
        (
            "R1_three_sheet_release",
            "Three linked primary sheets with event_id and claim_boundary.",
            "Three-sheet benchmark release",
            "pass",
            "Closed for benchmark release.",
            "Keep schema contract tests in CI.",
        ),
        (
            "R2_fixed_horizon_metrics",
            "Platform-day and token-horizon metrics at 1/7/30 day windows.",
            "Metrics panel at fixed horizons",
            "pass",
            "Closed for representative release; top-tier welfare claims still require decoded full-cohort USD/trader fields.",
            "Backfill decoded token-level outcome gaps listed in data_gap_ledger.csv.",
        ),
        (
            "R3_offchain_covariates",
            "Telegram, Discord, sentiment, social metadata, and RWA/off-chain context.",
            "Off-chain and behavioral covariates",
            "pass",
            "Closed as linked covariates; causal social exposure remains separate.",
            "Collect timestamped exposure shocks or channel-level intervention data.",
        ),
        (
            "R4_license_citation_data_gaps",
            "Claim ledger, data dictionary, code/data license, citation metadata, Zenodo plan, and explicit gaps.",
            "Claim ledger, data dictionary, licensing, citation, data gaps",
            "partial",
            "Release-ready except DOI minting; DOI requires an external Zenodo deposit step.",
            "Use benchmark_release/zenodo_metadata.json when creating the Zenodo deposit.",
        ),
        (
            "R5_cross_chain_case",
            "At least one comparable cross-chain empirical case.",
            "Cross-chain empirical case",
            "partial",
            f"Bounded Base case accepted; full-cohort processed share is {min_base_coverage:.3%}.",
            "Complete Base archive/indexer swap and transfer imports for every manifest row.",
        ),
        (
            "R6_onchain_offchain_integration",
            "Integrate deployment/on-chain verification with social/community layers.",
            "On-chain/off-chain evidence integration",
            "partial",
            "Schemas are linked, but no supported in-window Telegram shock exists.",
            "Extend public-shock registry or collect token-level social exposure timestamps.",
        ),
        (
            "R7_mirror_case_b",
            "Case B: naive nothing happened to trustworthy supported effect.",
            "Mirror empirical Case B",
            "substantive_pass_claim_bounded",
            "Matched Telegram signal supports the mirror direction but not a causal Telegram treatment effect.",
            "Find an exogenous social-attention event if the paper needs causal rather than predictive language.",
        ),
        (
            "R8_paired_case_figure",
            "Present Case A and Case B in one paired evidence-ladder figure.",
            "",
            "pass" if not paired.empty else "gap",
            "Paired ladder data and figure are generated from the same release artifacts.",
            "Reference artifacts/figures/fig_paired_case_ladder_shilin.png in the joint draft.",
        ),
        (
            "R9_agentic_ai_for_good",
            "Agent evidence behavior, decision paths, scaffold effects, and societal-impact framing.",
            "Agentic Trustworthy AI evaluation",
            "partial",
            "Single-model L0-L7 panel exists; top-tier extension needs multi-model and scaffold ablations.",
            "Run additional model families and remove one scaffold at a time.",
        ),
    ]
    for requirement_id, requirement, item, override_status, top_status, next_experiment in specs:
        aligned_status, evidence = from_alignment(item, override_status) if item else (override_status, "")
        current_status = override_status if override_status in {"pass", "substantive_pass_claim_bounded"} else aligned_status
        rows.append(
            {
                "requirement_id": requirement_id,
                "professor_requirement": requirement,
                "current_status": current_status,
                "evidence_artifact": evidence,
                "top_conference_status": top_status,
                "next_experiment": next_experiment,
                "claim_boundary": "Do not upgrade partial or predictive rows into causal welfare claims.",
            }
        )
    return pd.DataFrame(rows)


def build_top_conference_gap_ledger() -> pd.DataFrame:
    exposure = read_json(ROOT / "artifacts" / "tables" / "telegram_exposure_design_summary.json")
    backfill = read_json(ROOT / "artifacts" / "tables" / "clanker_base_full_cohort_backfill_summary.json")
    h1 = read_json(ROOT / "artifacts" / "tables" / "h1_rpc_mechanism_summary.json")
    early_wallet = read_json(ROOT / "artifacts" / "tables" / "solana_early_wallet_backfill_summary.json")
    ablation_scores = read_csv(ROOT / "artifacts" / "tables" / "agentic_multimodel_ablation_scores.csv")
    scored_ablations = (
        ablation_scores.loc[ablation_scores.get("status", pd.Series(dtype=str)).astype(str).eq("scored")]
        if not ablation_scores.empty
        else pd.DataFrame()
    )
    if scored_ablations.empty:
        agentic_ablation_status = "registered_ablation_manifest_only"
    else:
        model_cells = scored_ablations[["provider", "model"]].drop_duplicates()
        ok_runs = int(pd.to_numeric(scored_ablations["ok_runs"], errors="coerce").fillna(0).sum())
        agentic_ablation_status = (
            f"partial_{len(model_cells)}_model_specs_"
            f"{scored_ablations[['provider', 'model', 'rung', 'ablation_id']].drop_duplicates().shape[0]}_scored_cells_"
            f"{ok_runs}_ok_runs"
        )
    return pd.DataFrame(
        [
            {
                "gap_id": "zenodo_doi_minting",
                "current_status": "release_metadata_ready_external_deposit_needed",
                "why_top_conference_gap": "A public DOI strengthens dataset credibility and citation tracking.",
                "data_or_credential_needed": "Zenodo account/deposit workflow.",
                "experiment_to_close": "Upload the benchmark release with benchmark_release/zenodo_metadata.json and record the DOI.",
                "claim_unlocked_if_closed": "Dataset artifact can be cited as an archived release.",
            },
            {
                "gap_id": "base_full_cohort_archive_indexer",
                "current_status": "partial_sample_import",
                "why_top_conference_gap": "The accepted Base case is bounded, not platform-wide.",
                "data_or_credential_needed": "Archive Base eth_getLogs or equivalent Dune/Bitquery exports for PoolManager Swap and ERC20 Transfer logs.",
                "experiment_to_close": (
                    f"Fill {backfill.get('manifest_rows', 0)} swap and transfer query units, then rebuild 1/7/30 day diagnostics."
                ),
                "claim_unlocked_if_closed": "Potential platform-wide Clanker/Base matched replication with holder reconstruction.",
            },
            {
                "gap_id": "telegram_exogenous_attention_shock",
                "current_status": f"{exposure.get('supported_shocks', 0)} supported shocks among {exposure.get('candidate_shocks', 0)} candidates",
                "why_top_conference_gap": "Matched Telegram metadata is predictive but not exogenous.",
                "data_or_credential_needed": "Timestamped Telegram-linking outage, channel exposure, or policy shock overlapping RED-PUMP launches.",
                "experiment_to_close": "Estimate an event-time exposure design around a supported public shock or channel-level intervention.",
                "claim_unlocked_if_closed": "Causal or quasi-causal Case B rather than claim-bounded matched association.",
            },
            {
                "gap_id": "solana_full_cohort_decoded_outcomes",
                "current_status": "partial_moralis_sample_and_rpc_proxy",
                "why_top_conference_gap": "RPC proxy proves activity, not full USD volume, active traders, or welfare.",
                "data_or_credential_needed": "Dune, Helius Enhanced Transactions, Moralis, Birdeye, or equivalent decoded export for all graduated tokens.",
                "experiment_to_close": (
                    f"Replace selected {h1.get('moralis_decoded_outcome_rows', 0)} Moralis rows with full-cohort decoded 1/7/30 day rows."
                ),
                "claim_unlocked_if_closed": "Token-level USD/trader outcome estimates with fewer sample-selection caveats.",
            },
            {
                "gap_id": "same_cohort_h4_early_wallets",
                "current_status": (
                    f"partial_same_cohort_rpc_buyer_holder_proxy_"
                    f"{early_wallet.get('early_wallet_tokens', 0)}_tokens_"
                    f"{early_wallet.get('parsed_early_transactions', 0)}_parsed_txs_"
                    f"{early_wallet.get('classified_early_transactions', 0)}_classified_txs"
                ),
                "why_top_conference_gap": "Retail-risk H4 remains external mechanism validation, not same-cohort causal evidence.",
                "data_or_credential_needed": "Complete same-cohort early buyer/holder snapshots for all 1,651 graduated PumpSwap tokens.",
                "experiment_to_close": "Join complete early-wallet concentration to 1/7/30 day token outcomes and rerun the stakeholder battery.",
                "claim_unlocked_if_closed": "Within-cohort retail concentration/risk evidence rather than external proxy validation.",
            },
            {
                "gap_id": "agentic_multimodel_scaffold_ablations",
                "current_status": agentic_ablation_status,
                "why_top_conference_gap": "A stronger AI evaluation needs model-family robustness and scaffold causal attribution.",
                "data_or_credential_needed": "Additional model API access and registered ablation prompts.",
                "experiment_to_close": "Run multi-model L0-L7 prompts plus leave-one-scaffold-out ablations.",
                "claim_unlocked_if_closed": "Generalizable agent evidence-behavior benchmark claim.",
            },
        ]
    )


def build_zenodo_metadata() -> dict[str, Any]:
    return {
        "title": "Web3AI4IO Shilin PumpSwap Benchmark Release",
        "upload_type": "dataset",
        "description": (
            "Machine-readable evidence-quality benchmark artifacts for the Shilin Pump.fun/PumpSwap application arm, "
            "including linked events, metrics, covariates, claim boundaries, paired Case A/B ladder rows, "
            "cross-chain Clanker/Base manifests, and data-gap ledgers."
        ),
        "creators": [{"name": "Global Nomad Nexus Web3AI4IO contributors"}],
        "access_right": "open",
        "license": "cc-by-4.0",
        "keywords": [
            "causal inference",
            "token launchpads",
            "PumpSwap",
            "Clanker",
            "trustworthy AI",
            "evidence ladder",
            "benchmark",
        ],
        "related_identifiers": [
            {
                "identifier": "https://github.com/Global-Nomad-Nexus/Web3AI4IO",
                "relation": "isSupplementTo",
                "scheme": "url",
            }
        ],
        "notes": (
            "Code is MIT licensed. Generated benchmark tables are prepared for CC BY 4.0 release subject to upstream "
            "license compatibility. The DOI is not minted until this metadata is used in a Zenodo deposit."
        ),
    }


def write_manifest(paths: list[Path]) -> None:
    rows = []
    for path in sorted(paths):
        if path.exists():
            row_count = ""
            if path.suffix == ".csv":
                with path.open(encoding="utf-8") as handle:
                    row_count = max(sum(1 for _ in handle) - 1, 0)
            rows.append(
                {
                    "path": str(path.relative_to(OUT)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                    "rows": row_count,
                }
            )
    write_csv(DATA / "release_file_manifest.csv", rows)
    write_json(
        DATA / "release_manifest.json",
        {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "Shilin Pump.fun/PumpSwap application arm only",
            "primary_sheets": ["events.csv", "metrics_panel.csv", "covariates.csv"],
            "supplemental_sheets": [
                "claim_scope_ledger.csv",
                "data_gap_ledger.csv",
                "cross_chain_event_candidates.csv",
                "mirror_case_candidates.csv",
                "mirror_case_ladder.csv",
                "paired_case_ladder.csv",
                "telegram_mirror_design.csv",
                "telegram_mirror_balance.csv",
                "telegram_mirror_matched_cells.csv",
                "telegram_exposure_design.csv",
                "telegram_shock_candidates.csv",
                "clanker_base_full_cohort_manifest.csv",
                "clanker_base_full_cohort_pool_query_bounds.csv",
                "clanker_base_full_cohort_transfer_query_bounds.csv",
                "clanker_base_full_cohort_expected_horizons.csv",
                "clanker_base_full_cohort_import_contract.csv",
                "clanker_base_full_cohort_import_coverage.csv",
                "full_cohort_coverage_audit.csv",
                "clanker_base_causal_diagnostics.csv",
                "teacher_requirements_alignment_shilin.csv",
                "requirement_closure_audit.csv",
                "top_conference_gap_ledger.csv",
                "agentic_evaluation_panel.csv",
                "agentic_multimodel_ablation_manifest.csv",
                "agentic_multimodel_ablation_scores.csv",
                "data_dictionary.csv",
            ],
            "zenodo_metadata": "zenodo_metadata.json",
        },
    )


def main() -> None:
    global DATA, OUT

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(DATA), help="Directory for generated release CSV files.")
    args = parser.parse_args()
    DATA = Path(args.data_dir).resolve()
    OUT = DATA.parent

    outputs = {
        "events.csv": (build_events(), EVENT_COLUMNS),
        "metrics_panel.csv": (build_metrics_panel(), METRIC_COLUMNS),
        "covariates.csv": (build_covariates(), COVARIATE_COLUMNS),
        "claim_scope_ledger.csv": (build_claim_scope(), None),
        "data_gap_ledger.csv": (build_data_gaps(), None),
        "cross_chain_event_candidates.csv": (build_cross_chain_candidates(), None),
        "mirror_case_candidates.csv": (build_mirror_candidates(), None),
        "mirror_case_ladder.csv": (build_mirror_case_ladder(), None),
        "paired_case_ladder.csv": (build_paired_case_ladder(), None),
        "telegram_mirror_design.csv": (build_telegram_mirror_design(), None),
        "telegram_mirror_balance.csv": (build_telegram_mirror_balance(), None),
        "telegram_mirror_matched_cells.csv": (build_telegram_mirror_matched_cells(), None),
        "telegram_exposure_design.csv": (build_telegram_exposure_design(), None),
        "telegram_shock_candidates.csv": (build_telegram_shock_candidates(), None),
        "clanker_base_full_cohort_manifest.csv": (build_clanker_full_cohort_manifest(), None),
        "clanker_base_full_cohort_pool_query_bounds.csv": (build_clanker_full_cohort_pool_query_bounds(), None),
        "clanker_base_full_cohort_transfer_query_bounds.csv": (build_clanker_full_cohort_transfer_query_bounds(), None),
        "clanker_base_full_cohort_expected_horizons.csv": (build_clanker_full_cohort_expected_horizons(), None),
        "clanker_base_full_cohort_import_contract.csv": (build_clanker_full_cohort_import_contract(), None),
        "clanker_base_full_cohort_import_coverage.csv": (build_clanker_full_cohort_import_coverage(), None),
        "full_cohort_coverage_audit.csv": (build_full_cohort_coverage_audit(), None),
        "clanker_base_causal_diagnostics.csv": (build_clanker_base_causal_diagnostics(), None),
        "teacher_requirements_alignment_shilin.csv": (build_teacher_requirements_alignment(), None),
        "requirement_closure_audit.csv": (build_requirement_closure_audit(), None),
        "top_conference_gap_ledger.csv": (build_top_conference_gap_ledger(), None),
        "agentic_evaluation_panel.csv": (build_agentic_panel(), None),
        "agentic_multimodel_ablation_manifest.csv": (build_agentic_ablation_manifest(), None),
        "agentic_multimodel_ablation_scores.csv": (build_agentic_ablation_scores(), None),
        "data_dictionary.csv": (build_data_dictionary(), None),
    }

    paths = []
    for filename, (df, columns) in outputs.items():
        path = DATA / filename
        write_csv(path, df, columns)
        paths.append(path)
    zenodo_path = OUT / "zenodo_metadata.json"
    write_json(zenodo_path, build_zenodo_metadata())
    write_manifest(paths + [DATA / "release_file_manifest.csv", zenodo_path])

    print(f"Shilin benchmark release written to {DATA}")
    print(
        "events={events} metrics={metrics} covariates={covariates}".format(
            events=len(outputs["events.csv"][0]),
            metrics=len(outputs["metrics_panel.csv"][0]),
            covariates=len(outputs["covariates.csv"][0]),
        )
    )


if __name__ == "__main__":
    main()
