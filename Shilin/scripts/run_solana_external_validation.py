#!/usr/bin/env python3
"""Build real Solana/Pump.fun external-validation artifacts for Shilin H1/H4.

This script does not require Dune credentials. It uses:

1. Pump.fun frontend coin metadata for graduated RED-PUMP mints, including
   PumpSwap pool addresses and last-trade timestamps.
2. Public Solana JSON-RPC signatures for PumpSwap pools to estimate
   post-migration pool activity windows.
3. Public Solana JSON-RPC signatures for bonding-curve accounts to estimate
   early-wallet concentration in the first 60 seconds after token creation.

The outputs are explicitly labeled as external-validation proxies. They do not
replace a full Dune dex_solana.trades export.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.io import load_config, write_csv, write_json


SOL_MINT = "So11111111111111111111111111111111111111112"
PUMP_COIN_URL = "https://frontend-api-v3.pump.fun/coins/{mint}?sync=true"
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
LIMIT_STOP_MARKERS = (
    "429",
    "too many requests",
    "rate limit",
    "rate-limit",
    "quota",
    "credit",
    "credits",
    "monthly limit",
    "usage limit",
    "exceeded",
    "insufficient",
    "payment required",
)


def is_limit_stop_message(message: object) -> bool:
    text = str(message).lower()
    return any(marker in text for marker in LIMIT_STOP_MARKERS)


def resolve_rpc_url(explicit: str | None) -> tuple[str, str]:
    """Resolve an RPC endpoint without leaking API keys into artifacts."""

    if explicit:
        return explicit, "user_supplied_rpc"
    env_rpc = os.environ.get("SOLANA_RPC_URL")
    if env_rpc:
        return env_rpc, "env_solana_rpc_url"
    helius_key = os.environ.get("HELIUS_API_KEY")
    if helius_key:
        return f"https://mainnet.helius-rpc.com/?api-key={helius_key}", "helius_rpc"
    return DEFAULT_RPC, "public_solana_rpc"


def parse_time(value: Any) -> datetime | None:
    if pd.isna(value):
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).astimezone(UTC)
    except ValueError:
        return None


def unix_timestamp_to_datetime(value: Any) -> datetime | None:
    if value in (None, "") or pd.isna(value):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric > 10_000_000_000:
        numeric = numeric / 1000
    try:
        return datetime.fromtimestamp(numeric, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def request_json_url(url: str, *, timeout: float) -> dict[str, Any] | list[Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Origin": "https://pump.fun", "User-Agent": "ShilinResearchBot/0.1"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def rpc_call(rpc_url: str, method: str, params: list[Any], *, timeout: float) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    request = urllib.request.Request(
        rpc_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "ShilinResearchBot/0.1"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def safe_rpc_call(
    rpc_url: str,
    method: str,
    params: list[Any],
    *,
    timeout: float,
    retries: int,
    sleep: float,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            payload = rpc_call(rpc_url, method, params, timeout=timeout)
            if "error" not in payload:
                return payload
            last_error = RuntimeError(json.dumps(payload["error"]))
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            last_error = RuntimeError(f"HTTP {exc.code}: {body or exc.reason}")
            if is_limit_stop_message(last_error):
                break
        except (urllib.error.URLError, TimeoutError, socket.timeout, json.JSONDecodeError) as exc:
            last_error = exc
        if is_limit_stop_message(last_error):
            break
        time.sleep(sleep * (attempt + 1))
    return {"error": {"message": f"{type(last_error).__name__}: {last_error}" if last_error else "unknown"}}


def fetch_coin_metadata(mint: str, *, timeout: float, retries: int, sleep: float) -> tuple[dict[str, Any], str]:
    last_error = ""
    for attempt in range(retries + 1):
        try:
            payload = request_json_url(PUMP_COIN_URL.format(mint=mint), timeout=timeout)
            if isinstance(payload, dict) and payload.get("mint") == mint:
                return payload, "ok"
            last_error = json.dumps(payload)[:240]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(sleep * (attempt + 1))
    return {"mint": mint, "error": last_error}, "error"


def sample_graduated_tokens(graduated: pd.DataFrame, *, max_tokens: int, strategy: str) -> pd.DataFrame:
    if max_tokens <= 0 or max_tokens >= len(graduated):
        return graduated.reset_index(drop=False).rename(columns={"index": "graduated_index"})
    if strategy == "evenly_spaced":
        positions = np.linspace(0, len(graduated) - 1, max_tokens).round().astype(int)
        positions = sorted(set(int(pos) for pos in positions))
        return graduated.iloc[positions].reset_index(drop=False).rename(columns={"index": "graduated_index"})
    if strategy == "latest":
        return graduated.tail(max_tokens).reset_index(drop=False).rename(columns={"index": "graduated_index"})
    return graduated.head(max_tokens).reset_index(drop=False).rename(columns={"index": "graduated_index"})


def write_checkpoint(
    *,
    out_dir: Path,
    metadata_rows: list[dict[str, Any]],
    post_rows: list[dict[str, Any]],
    early_rows: list[dict[str, Any]],
    tx_rows: list[dict[str, Any]],
) -> None:
    write_csv(out_dir / "pumpfun_coin_metadata.csv", pd.DataFrame(metadata_rows))
    write_csv(out_dir / "solana_post_migration_pool_windows.csv", pd.DataFrame(post_rows))
    write_csv(out_dir / "solana_early_wallet_concentration.csv", pd.DataFrame(early_rows))
    write_csv(out_dir / "solana_parsed_transaction_proxies.csv", pd.DataFrame(tx_rows))


def read_existing_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size <= 1:
        return []
    try:
        return pd.read_csv(path).to_dict("records")
    except pd.errors.EmptyDataError:
        return []


def remove_mint_rows(
    rows: list[dict[str, Any]],
    mint: str,
    *,
    phases: set[str] | None = None,
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for item in rows:
        if str(item.get("mint")) != mint:
            kept.append(item)
            continue
        if phases is not None and str(item.get("phase", "")) not in phases:
            kept.append(item)
    return kept


def truncated_post_mints(post_rows: list[dict[str, Any]]) -> set[str]:
    post = pd.DataFrame(post_rows)
    if post.empty or "mint" not in post or "signature_window_status" not in post:
        return set()
    horizon = pd.to_numeric(post.get("horizon_days"), errors="coerce")
    status = post["signature_window_status"].astype(str)
    return set(post.loc[horizon.eq(30) & status.ne("ok"), "mint"].astype(str))


def fetch_signatures(
    address: str,
    *,
    rpc_url: str,
    start: datetime,
    end: datetime,
    page_limit: int,
    max_pages: int,
    timeout: float,
    retries: int,
    sleep: float,
) -> tuple[list[dict[str, Any]], str]:
    signatures: list[dict[str, Any]] = []
    before: str | None = None
    status = "ok"
    reached_window_start = False
    pages_read = 0
    for _ in range(max_pages):
        pages_read += 1
        options: dict[str, Any] = {"limit": page_limit}
        if before:
            options["before"] = before
        payload = safe_rpc_call(
            rpc_url,
            "getSignaturesForAddress",
            [address, options],
            timeout=timeout,
            retries=retries,
            sleep=sleep,
        )
        if "error" in payload:
            message = str(payload["error"].get("message", payload["error"]))
            status = f"quota_or_rate_limit_stop:{message}" if is_limit_stop_message(message) else message
            break
        page = payload.get("result") or []
        if not page:
            reached_window_start = True
            break
        for item in page:
            block_time = item.get("blockTime")
            if block_time is None:
                continue
            ts = datetime.fromtimestamp(int(block_time), tz=UTC)
            if start <= ts < end:
                signatures.append(item)
        oldest = min(
            (datetime.fromtimestamp(int(item["blockTime"]), tz=UTC) for item in page if item.get("blockTime")),
            default=None,
        )
        before = page[-1].get("signature")
        if len(page) < page_limit:
            reached_window_start = True
            break
        if oldest is not None and oldest < start:
            reached_window_start = True
            break
        time.sleep(sleep)
    if status == "ok" and not reached_window_start and pages_read >= max_pages:
        status = "max_pages_before_window_start_counts_are_lower_bounds"
    return signatures, status


def parsed_transfer_amounts(tx: dict[str, Any], mint: str) -> tuple[float, float]:
    sol_amounts: list[float] = []
    token_amounts: list[float] = []
    meta = tx.get("result", {}).get("meta", {}) if isinstance(tx, dict) else {}
    for group in meta.get("innerInstructions", []) or []:
        for instruction in group.get("instructions", []) or []:
            parsed = instruction.get("parsed") if isinstance(instruction, dict) else None
            if not isinstance(parsed, dict):
                continue
            info = parsed.get("info", {})
            amount = info.get("tokenAmount", {})
            try:
                ui_amount = float(amount.get("uiAmountString") or amount.get("uiAmount") or 0)
            except (TypeError, ValueError):
                ui_amount = 0.0
            transfer_mint = info.get("mint")
            if transfer_mint == SOL_MINT:
                sol_amounts.append(abs(ui_amount))
            elif transfer_mint == mint:
                token_amounts.append(abs(ui_amount))
    return (max(sol_amounts) if sol_amounts else math.nan, max(token_amounts) if token_amounts else math.nan)


def parsed_fee_payer(tx: dict[str, Any]) -> str:
    message = tx.get("result", {}).get("transaction", {}).get("message", {}) if isinstance(tx, dict) else {}
    for key in message.get("accountKeys", []) or []:
        if isinstance(key, dict) and key.get("signer"):
            return str(key.get("pubkey", ""))
    return ""


def parse_pool_transaction(
    signature: str,
    mint: str,
    *,
    rpc_url: str,
    timeout: float,
    retries: int,
    sleep: float,
) -> dict[str, Any]:
    payload = safe_rpc_call(
        rpc_url,
        "getTransaction",
        [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
        timeout=timeout,
        retries=retries,
        sleep=sleep,
    )
    if "error" in payload or not payload.get("result"):
        message = payload.get("error", {}).get("message", "missing_result")
        parse_status = f"quota_or_rate_limit_stop:{message}" if is_limit_stop_message(message) else message
        return {"signature": signature, "parse_status": parse_status}
    sol_amount, token_amount = parsed_transfer_amounts(payload, mint)
    return {
        "signature": signature,
        "parse_status": "ok",
        "fee_payer": parsed_fee_payer(payload),
        "volume_sol_proxy": sol_amount,
        "token_amount_proxy": token_amount,
    }


def aggregate_post_windows(
    *,
    mint: str,
    graduated_at: datetime,
    pool_address: str,
    signatures: list[dict[str, Any]],
    tx_details: dict[str, dict[str, Any]],
    signature_status: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    successful = [sig for sig in signatures if sig.get("err") is None]
    times = {
        sig["signature"]: datetime.fromtimestamp(int(sig["blockTime"]), tz=UTC)
        for sig in successful
        if sig.get("blockTime") is not None
    }
    for horizon in [1, 7, 30]:
        horizon_end = graduated_at + timedelta(days=horizon)
        inside = [sig for sig in successful if sig["signature"] in times and times[sig["signature"]] < horizon_end]
        fee_payers = {
            tx_details.get(sig["signature"], {}).get("fee_payer")
            for sig in inside
            if tx_details.get(sig["signature"], {}).get("fee_payer")
        }
        sol_values = [
            tx_details.get(sig["signature"], {}).get("volume_sol_proxy")
            for sig in inside
            if not pd.isna(tx_details.get(sig["signature"], {}).get("volume_sol_proxy", np.nan))
        ]
        first = min((times[sig["signature"]] for sig in inside), default=None)
        last = max((times[sig["signature"]] for sig in inside), default=None)
        rows.append(
            {
                "mint": mint,
                "graduated_at": graduated_at.isoformat(),
                "horizon_days": horizon,
                "pool_address": pool_address,
                "swap_count": len(inside),
                "active_traders": len(fee_payers),
                "volume_usd": np.nan,
                "volume_sol_proxy": float(np.nansum(sol_values)) if sol_values else np.nan,
                "first_trade_at": first.isoformat() if first else "",
                "last_trade_at": last.isoformat() if last else "",
                "inactivity_gap_hours": (last - first).total_seconds() / 3600 if first and last else np.nan,
                "reactivated_after_7d": int(
                    any(
                        graduated_at + timedelta(days=7) <= times[sig["signature"]] < graduated_at + timedelta(days=30)
                        for sig in inside
                    )
                ),
                "signatures_scanned": len(signatures),
                "transactions_parsed": sum(1 for sig in inside if tx_details.get(sig["signature"], {}).get("parse_status") == "ok"),
                "source": "Pump.fun pool address + Solana RPC getSignaturesForAddress/getTransaction",
                "signature_window_status": signature_status,
                "validation_status": "computed_pool_tx_proxy",
            }
        )
    return rows


def aggregate_early_wallets(
    *,
    mint: str,
    created_at: datetime,
    early_address: str,
    signatures: list[dict[str, Any]],
    tx_details: dict[str, dict[str, Any]],
    early_window_seconds: int,
    signature_status: str,
) -> dict[str, Any]:
    successful = [sig for sig in signatures if sig.get("err") is None]
    wallet_volume: dict[str, float] = defaultdict(float)
    for sig in successful:
        detail = tx_details.get(sig["signature"], {})
        wallet = detail.get("fee_payer")
        if not wallet:
            continue
        sol = detail.get("volume_sol_proxy")
        token = detail.get("token_amount_proxy")
        proxy = sol if not pd.isna(sol) else token
        if not pd.isna(proxy):
            wallet_volume[wallet] += float(proxy)
        else:
            wallet_volume[wallet] += 1.0
    total = sum(wallet_volume.values())
    shares = sorted((value / total for value in wallet_volume.values()), reverse=True) if total > 0 else []
    return {
        "mint": mint,
        "launch_or_graduated_at": created_at.isoformat(),
        "early_window_seconds": early_window_seconds,
        "early_address": early_address,
        "early_buyers": len(wallet_volume),
        "early_buy_volume_sol_proxy": total if total > 0 else np.nan,
        "top1_early_buyer_share": sum(shares[:1]) if shares else np.nan,
        "top5_early_buyer_share": sum(shares[:5]) if shares else np.nan,
        "top10_early_buyer_share": sum(shares[:10]) if shares else np.nan,
        "early_buyer_hhi": sum(share * share for share in shares) if shares else np.nan,
        "first_trade_at": min(
            (datetime.fromtimestamp(int(sig["blockTime"]), tz=UTC) for sig in successful if sig.get("blockTime")),
            default=None,
        ).isoformat()
        if successful
        else "",
        "last_early_trade_at": max(
            (datetime.fromtimestamp(int(sig["blockTime"]), tz=UTC) for sig in successful if sig.get("blockTime")),
            default=None,
        ).isoformat()
        if successful
        else "",
        "signatures_scanned": len(signatures),
        "transactions_parsed": sum(
            1 for sig in successful if tx_details.get(sig["signature"], {}).get("parse_status") == "ok"
        ),
        "source": "Pump.fun bonding-curve address + Solana RPC getSignaturesForAddress/getTransaction",
        "signature_window_status": signature_status,
        "validation_status": "computed_fee_payer_proxy",
    }


def summarize_outputs(
    metadata: pd.DataFrame,
    post: pd.DataFrame,
    early: pd.DataFrame,
    *,
    tokens_requested: int,
    all_graduated_tokens: int,
    sample_strategy: str,
    rpc_provider: str,
    stop_reason: str = "",
) -> dict[str, Any]:
    post_30 = post.loc[post["horizon_days"].eq(30)] if len(post) else pd.DataFrame()
    post_30_status = (
        post_30["signature_window_status"].astype(str)
        if len(post_30) and "signature_window_status" in post_30
        else pd.Series(dtype=str)
    )
    post_30_complete = post_30.loc[post_30_status.eq("ok")] if len(post_30_status) else pd.DataFrame()
    post_truncated = (
        post_30_status.ne("ok").mean()
        if len(post_30_status)
        else np.nan
    )
    post_complete = post_30_status.eq("ok") if len(post_30_status) else pd.Series(dtype=bool)
    post_truncated_zero = (
        int((post_30_status.ne("ok") & post_30["swap_count"].eq(0)).sum())
        if len(post_30_status) and "swap_count" in post_30
        else 0
    )
    early_truncated = (
        early["signature_window_status"].astype(str).ne("ok").mean()
        if len(early) and "signature_window_status" in early
        else np.nan
    )
    early_complete = (
        early["signature_window_status"].astype(str).eq("ok")
        if len(early) and "signature_window_status" in early
        else pd.Series(dtype=bool)
    )
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "all_graduated_tokens_available": int(all_graduated_tokens),
        "tokens_requested": int(tokens_requested),
        "sample_strategy": sample_strategy,
        "rpc_provider": rpc_provider,
        "metadata_rows": int(len(metadata)),
        "metadata_ok_rows": int((metadata.get("metadata_status") == "ok").sum()) if len(metadata) else 0,
        "pool_address_rows": int(metadata.get("pool_address", pd.Series(dtype=str)).astype(str).ne("").sum())
        if len(metadata)
        else 0,
        "post_migration_window_rows": int(len(post)),
        "post_migration_tokens": int(post["mint"].nunique()) if len(post) else 0,
        "median_30d_pool_tx_count": float(post_30["swap_count"].median()) if len(post_30) else np.nan,
        "share_tokens_with_30d_pool_activity": float(post_30["swap_count"].gt(0).mean()) if len(post_30) else np.nan,
        "share_30d_post_windows_potentially_truncated": float(post_truncated) if not pd.isna(post_truncated) else np.nan,
        "post_30d_complete_tokens": int(post_complete.sum()) if len(post_complete) else 0,
        "share_30d_post_windows_complete": float(post_complete.mean()) if len(post_complete) else np.nan,
        "median_complete_30d_pool_tx_count": float(post_30_complete["swap_count"].median()) if len(post_30_complete) else np.nan,
        "share_complete_30d_pool_activity": float(post_30_complete["swap_count"].gt(0).mean()) if len(post_30_complete) else np.nan,
        "post_30d_truncated_tokens": int(post_30_status.ne("ok").sum()) if len(post_30_status) else 0,
        "post_30d_truncated_zero_observed_tokens": post_truncated_zero,
        "post_transactions_parsed": int(post["transactions_parsed"].sum()) if len(post) and "transactions_parsed" in post else 0,
        "median_30d_active_fee_payers_parsed": float(post_30["active_traders"].median()) if len(post_30) else np.nan,
        "post_signatures_scanned": int(post["signatures_scanned"].sum()) if len(post) and "signatures_scanned" in post else 0,
        "early_wallet_rows": int(len(early)),
        "early_wallet_tokens": int(early["mint"].nunique()) if len(early) else 0,
        "share_tokens_with_early_signatures": float(early["signatures_scanned"].gt(0).mean())
        if len(early) and "signatures_scanned" in early
        else np.nan,
        "share_early_windows_potentially_truncated": float(early_truncated) if not pd.isna(early_truncated) else np.nan,
        "early_window_complete_tokens": int(early_complete.sum()) if len(early_complete) else 0,
        "share_early_windows_complete": float(early_complete.mean()) if len(early_complete) else np.nan,
        "median_early_buyers": float(early["early_buyers"].median()) if len(early) else np.nan,
        "median_top1_early_buyer_share": float(early["top1_early_buyer_share"].median()) if len(early) else np.nan,
        "status": "computed_external_validation_sample",
        "collection_stop_reason": stop_reason,
        "sample_decoding_level": "jsonParsed Solana RPC transaction proxy; decoded indexer USD outcomes still require Dune/Helius/Moralis/Birdeye credentials",
        "credible_sample_status": (
            "credible_complete_rpc_post_migration_sample"
            if len(post_complete) and int(post_complete.sum()) >= min(5, len(post_complete))
            else "lower_bound_rpc_proxy_sample"
        ),
        "post_activity_metric_note": (
            "Use complete-window metrics for causal interpretation. Truncated rows are screening observations; "
            "a zero swap_count with a non-ok signature_window_status is not evidence of zero 30d post-migration activity."
        ),
        "claim_boundary": (
            "These are real Pump.fun/Solana RPC external-validation proxies. "
            "They count successful pool/bonding-curve account transactions and fee-payer concentration; "
            "they do not replace a Dune dex_solana.trades export with decoded swap volume USD."
        ),
        "full_indexer_target": (
            "For top-conference claims, run all 1,651 graduated tokens through a decoded indexer "
            "such as Dune/Helius/Moralis/Birdeye and replace proxy volume/counts with token-level "
            "1/7/30d post-migration trades plus validated early-wallet/sniper features."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs" / "pumpswap_case.json"))
    parser.add_argument("--rpc-url", default=None)
    parser.add_argument("--max-tokens", type=int, default=80)
    parser.add_argument(
        "--mint",
        action="append",
        default=[],
        help="Restrict validation to one mint. Repeat for multiple mints. Overrides --max-tokens sampling.",
    )
    parser.add_argument("--sample-strategy", choices=["first", "evenly_spaced", "latest"], default="evenly_spaced")
    parser.add_argument(
        "--only",
        choices=["both", "post_migration", "early_wallets"],
        default="both",
        help="Limit validation to post-migration pool windows, early-wallet windows, or both.",
    )
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--page-limit", type=int, default=200)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--tx-limit-per-token", type=int, default=80)
    parser.add_argument("--post-tx-limit-per-token", type=int, default=None)
    parser.add_argument("--early-tx-limit-per-token", type=int, default=None)
    parser.add_argument("--early-window-seconds", type=int, default=60)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="With --resume, re-fetch selected mints and replace their existing artifact rows.",
    )
    parser.add_argument(
        "--refresh-truncated-post",
        action="store_true",
        help="With --resume, re-fetch only mints whose existing 30d post window is not complete.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    rpc_url, rpc_provider = resolve_rpc_url(args.rpc_url)
    out_dir = config.output_root / "external_validation"
    raw_dir = out_dir / "raw_coin_metadata"
    raw_dir.mkdir(parents=True, exist_ok=True)

    all_graduated = pd.read_csv(config.source_path("red_pump_graduated_for_dune"))
    if args.mint:
        requested_mints = {str(mint) for mint in args.mint}
        graduated = (
            all_graduated.loc[all_graduated["mint"].astype(str).isin(requested_mints)]
            .reset_index(drop=False)
            .rename(columns={"index": "graduated_index"})
        )
        missing_mints = sorted(requested_mints - set(graduated["mint"].astype(str)))
        if missing_mints:
            print(f"Warning: requested mints not found in graduated list: {missing_mints}", flush=True)
    else:
        graduated = sample_graduated_tokens(
            all_graduated,
            max_tokens=args.max_tokens,
            strategy=args.sample_strategy,
        )
    post_tx_limit = args.post_tx_limit_per_token
    if post_tx_limit is None:
        post_tx_limit = args.tx_limit_per_token
    early_tx_limit = args.early_tx_limit_per_token
    if early_tx_limit is None:
        early_tx_limit = args.tx_limit_per_token
    if args.resume:
        metadata_rows = read_existing_rows(out_dir / "pumpfun_coin_metadata.csv")
        post_rows = read_existing_rows(out_dir / "solana_post_migration_pool_windows.csv")
        early_rows = read_existing_rows(out_dir / "solana_early_wallet_concentration.csv")
        tx_rows = read_existing_rows(out_dir / "solana_parsed_transaction_proxies.csv")
    else:
        metadata_rows = []
        post_rows = []
        early_rows = []
        tx_rows = []
    refresh_mints: set[str] = set()
    if args.resume and args.refresh_truncated_post:
        refresh_mints = truncated_post_mints(post_rows)
        if args.mint:
            refresh_mints &= {str(mint) for mint in args.mint}
        graduated = (
            all_graduated.loc[all_graduated["mint"].astype(str).isin(refresh_mints)]
            .reset_index(drop=False)
            .rename(columns={"index": "graduated_index"})
        )
    elif args.resume and args.refresh_existing:
        refresh_mints = set(graduated["mint"].astype(str))
    completed_mints = {str(item.get("mint")) for item in metadata_rows if item.get("mint")} if args.resume else set()
    stop_reason = ""
    print(
        f"Starting Solana validation: tokens={len(graduated)}, rpc_provider={rpc_provider}, "
        f"page_limit={args.page_limit}, max_pages={args.max_pages}",
        flush=True,
    )

    for index, row in graduated.iterrows():
        mint = str(row["mint"])
        refreshing_mint = args.resume and (args.refresh_existing or mint in refresh_mints)
        if mint in completed_mints and not refreshing_mint:
            print(f"{index + 1}/{len(graduated)} {mint}: skipped_existing", flush=True)
            continue
        if refreshing_mint:
            metadata_rows = remove_mint_rows(metadata_rows, mint)
            if args.only in {"both", "post_migration"}:
                post_rows = remove_mint_rows(post_rows, mint)
                tx_rows = remove_mint_rows(tx_rows, mint, phases={"post_migration_pool"})
            if args.only in {"both", "early_wallets"}:
                early_rows = remove_mint_rows(early_rows, mint)
                tx_rows = remove_mint_rows(tx_rows, mint, phases={"early_bonding_curve"})
        graduated_at = parse_time(row["graduated_at"])
        created_at = parse_time(row["created_at"])
        if graduated_at is None or created_at is None:
            continue
        print(f"{index + 1}/{len(graduated)} {mint}: fetching metadata", flush=True)
        coin, status = fetch_coin_metadata(mint, timeout=args.timeout, retries=args.retries, sleep=args.sleep)
        (raw_dir / f"{mint}.json").write_text(json.dumps(coin, indent=2, sort_keys=True), encoding="utf-8")
        pool_address = str(coin.get("pump_swap_pool") or coin.get("pool_address") or coin.get("raydium_pool") or "")
        early_address = str(coin.get("bonding_curve") or coin.get("associated_bonding_curve") or "")
        metadata_rows.append(
            {
                "graduated_index": int(row.get("graduated_index", index)),
                "sample_strategy": args.sample_strategy,
                "mint": mint,
                "created_at": created_at.isoformat(),
                "graduated_at": graduated_at.isoformat(),
                "metadata_status": status,
                "complete": coin.get("complete"),
                "creator": coin.get("creator", ""),
                "bonding_curve": coin.get("bonding_curve", ""),
                "associated_bonding_curve": coin.get("associated_bonding_curve", ""),
                "pool_address": pool_address,
                "last_trade_timestamp": coin.get("last_trade_timestamp"),
                "last_trade_at": unix_timestamp_to_datetime(coin.get("last_trade_timestamp")).isoformat()
                if unix_timestamp_to_datetime(coin.get("last_trade_timestamp"))
                else "",
                "ath_market_cap": coin.get("ath_market_cap"),
                "ath_market_cap_timestamp": coin.get("ath_market_cap_timestamp"),
                "ath_market_cap_at": unix_timestamp_to_datetime(coin.get("ath_market_cap_timestamp")).isoformat()
                if unix_timestamp_to_datetime(coin.get("ath_market_cap_timestamp"))
                else "",
                "usd_market_cap": coin.get("usd_market_cap"),
                "market_cap": coin.get("market_cap"),
                "total_supply": coin.get("total_supply"),
                "token_program": coin.get("token_program", ""),
                "protocol": coin.get("protocol", ""),
            }
        )

        tx_details: dict[str, dict[str, Any]] = {}
        if pool_address and not args.metadata_only and args.only in {"both", "post_migration"}:
            print(f"{index + 1}/{len(graduated)} {mint}: fetching pool signatures", flush=True)
            signatures, sig_status = fetch_signatures(
                pool_address,
                rpc_url=rpc_url,
                start=graduated_at,
                end=graduated_at + timedelta(days=30),
                page_limit=args.page_limit,
                max_pages=args.max_pages,
                timeout=args.timeout,
                retries=args.retries,
                sleep=args.sleep,
            )
            print(
                f"{index + 1}/{len(graduated)} {mint}: pool signatures={len(signatures)} status={sig_status}",
                flush=True,
            )
            if str(sig_status).startswith("quota_or_rate_limit_stop:"):
                stop_reason = f"post_migration_signatures:{sig_status}"
                print(f"Stopping collection because provider limit was reached: {sig_status}", flush=True)
                write_checkpoint(
                    out_dir=out_dir,
                    metadata_rows=metadata_rows,
                    post_rows=post_rows,
                    early_rows=early_rows,
                    tx_rows=tx_rows,
                )
                break
            successful = [sig for sig in signatures if sig.get("err") is None]
            post_parse_target = successful[: max(post_tx_limit, 0)]
            for pos, sig in enumerate(post_parse_target, start=1):
                detail = parse_pool_transaction(
                    sig["signature"],
                    mint,
                    rpc_url=rpc_url,
                    timeout=args.timeout,
                    retries=args.retries,
                    sleep=args.sleep,
                )
                tx_details[sig["signature"]] = detail
                tx_rows.append({"mint": mint, "phase": "post_migration_pool", **detail})
                if str(detail.get("parse_status", "")).startswith("quota_or_rate_limit_stop:"):
                    stop_reason = f"post_migration_transaction:{detail['parse_status']}"
                    print(f"Stopping collection because provider limit was reached: {detail['parse_status']}", flush=True)
                    break
                if pos % 25 == 0 or pos == len(post_parse_target):
                    print(
                        f"{index + 1}/{len(graduated)} {mint}: parsed post tx {pos}/{len(post_parse_target)}",
                        flush=True,
                    )
                time.sleep(args.sleep)
            if stop_reason:
                write_checkpoint(
                    out_dir=out_dir,
                    metadata_rows=metadata_rows,
                    post_rows=post_rows,
                    early_rows=early_rows,
                    tx_rows=tx_rows,
                )
                break
            post_rows.extend(
                aggregate_post_windows(
                    mint=mint,
                    graduated_at=graduated_at,
                    pool_address=pool_address,
                    signatures=signatures,
                    tx_details=tx_details,
                    signature_status=sig_status,
                )
            )
        if early_address and not args.metadata_only and args.only in {"both", "early_wallets"}:
            start = created_at
            end = created_at + timedelta(seconds=args.early_window_seconds)
            print(f"{index + 1}/{len(graduated)} {mint}: fetching early signatures", flush=True)
            signatures, sig_status = fetch_signatures(
                early_address,
                rpc_url=rpc_url,
                start=start,
                end=end,
                page_limit=args.page_limit,
                max_pages=args.max_pages,
                timeout=args.timeout,
                retries=args.retries,
                sleep=args.sleep,
            )
            print(
                f"{index + 1}/{len(graduated)} {mint}: early signatures={len(signatures)} status={sig_status}",
                flush=True,
            )
            if str(sig_status).startswith("quota_or_rate_limit_stop:"):
                stop_reason = f"early_wallet_signatures:{sig_status}"
                print(f"Stopping collection because provider limit was reached: {sig_status}", flush=True)
                write_checkpoint(
                    out_dir=out_dir,
                    metadata_rows=metadata_rows,
                    post_rows=post_rows,
                    early_rows=early_rows,
                    tx_rows=tx_rows,
                )
                break
            early_details: dict[str, dict[str, Any]] = {}
            successful = [sig for sig in signatures if sig.get("err") is None]
            early_parse_target = successful[: max(early_tx_limit, 0)]
            for pos, sig in enumerate(early_parse_target, start=1):
                detail = parse_pool_transaction(
                    sig["signature"],
                    mint,
                    rpc_url=rpc_url,
                    timeout=args.timeout,
                    retries=args.retries,
                    sleep=args.sleep,
                )
                early_details[sig["signature"]] = detail
                tx_rows.append({"mint": mint, "phase": "early_bonding_curve", **detail})
                if str(detail.get("parse_status", "")).startswith("quota_or_rate_limit_stop:"):
                    stop_reason = f"early_wallet_transaction:{detail['parse_status']}"
                    print(f"Stopping collection because provider limit was reached: {detail['parse_status']}", flush=True)
                    break
                if pos % 25 == 0 or pos == len(early_parse_target):
                    print(
                        f"{index + 1}/{len(graduated)} {mint}: parsed early tx {pos}/{len(early_parse_target)}",
                        flush=True,
                    )
                time.sleep(args.sleep)
            if stop_reason:
                write_checkpoint(
                    out_dir=out_dir,
                    metadata_rows=metadata_rows,
                    post_rows=post_rows,
                    early_rows=early_rows,
                    tx_rows=tx_rows,
                )
                break
            early_rows.append(
                aggregate_early_wallets(
                    mint=mint,
                    created_at=created_at,
                    early_address=early_address,
                    signatures=signatures,
                    tx_details=early_details,
                    early_window_seconds=args.early_window_seconds,
                    signature_status=sig_status,
                )
            )
        print(
            f"{index + 1}/{len(graduated)} {mint}: metadata={status}, pool={'yes' if pool_address else 'no'}",
            flush=True,
        )
        if args.checkpoint_every and (index + 1) % args.checkpoint_every == 0:
            write_checkpoint(
                out_dir=out_dir,
                metadata_rows=metadata_rows,
                post_rows=post_rows,
                early_rows=early_rows,
                tx_rows=tx_rows,
            )
        time.sleep(args.sleep)
        if stop_reason:
            break

    metadata = pd.DataFrame(metadata_rows)
    post = pd.DataFrame(post_rows)
    early = pd.DataFrame(early_rows)
    tx = pd.DataFrame(tx_rows)

    write_checkpoint(
        out_dir=out_dir,
        metadata_rows=metadata_rows,
        post_rows=post_rows,
        early_rows=early_rows,
        tx_rows=tx_rows,
    )
    summary = summarize_outputs(
        metadata,
        post,
        early,
        tokens_requested=len(graduated),
        all_graduated_tokens=len(all_graduated),
        sample_strategy=args.sample_strategy,
        rpc_provider=rpc_provider,
        stop_reason=stop_reason,
    )
    write_json(config.tables_dir / "external_validation_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
