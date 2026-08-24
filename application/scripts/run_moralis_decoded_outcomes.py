#!/usr/bin/env python3
"""Collect Moralis decoded Solana swap outcomes for graduated Pump.fun tokens.

The script is intentionally credentials-light: it reads MORALIS_API_KEY from the
environment, writes local CSV/JSON artifacts, and stops cleanly when the API
returns a rate-limit, quota, auth, or access error. It does not persist the key.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
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


MORALIS_BASE_URL = "https://solana-gateway.moralis.io"
DEFAULT_NETWORK = "mainnet"
HORIZONS = (1, 7, 30)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
LIMIT_STOP_MARKERS = (
    "401",
    "403",
    "429",
    "access denied",
    "api key",
    "authentication",
    "browser_signature_banned",
    "cloudflare",
    "credit",
    "credits",
    "exceeded",
    "forbidden",
    "insufficient",
    "payment required",
    "quota",
    "rate limit",
    "rate-limit",
    "token is invalid",
    "too many requests",
    "unauthorized",
    "usage limit",
)


SWAP_COLUMNS = [
    "mint",
    "graduated_at",
    "horizon_days",
    "window_start",
    "window_end",
    "transaction_hash",
    "transaction_index",
    "transaction_type",
    "block_timestamp",
    "block_number",
    "wallet_address",
    "pair_address",
    "pair_label",
    "exchange_name",
    "exchange_address",
    "subcategory",
    "base_quote_price",
    "base_token_address",
    "base_token_symbol",
    "quote_token_address",
    "quote_token_symbol",
    "bought_token_address",
    "bought_token_symbol",
    "bought_amount",
    "bought_usd_amount",
    "sold_token_address",
    "sold_token_symbol",
    "sold_amount",
    "sold_usd_amount",
    "total_value_usd",
    "source",
]

PAIR_COLUMNS = [
    "mint",
    "pair_address",
    "pair_label",
    "exchange_name",
    "exchange_address",
    "base_token_address",
    "base_token_symbol",
    "quote_token_address",
    "quote_token_symbol",
    "usd_price",
    "liquidity_usd",
    "volume_24h_usd",
    "pair_created_at",
    "source",
]

STATUS_COLUMNS = [
    "mint",
    "endpoint",
    "horizon_days",
    "graduated_at",
    "status",
    "http_status",
    "rows_fetched",
    "pages_fetched",
    "cursor_remaining",
    "message",
]

OUTCOME_COLUMNS = [
    "mint",
    "horizon_days",
    "graduated_at",
    "window_start",
    "window_end",
    "decoded_trade_count",
    "decoded_buy_count",
    "decoded_sell_count",
    "decoded_volume_usd",
    "decoded_buy_volume_usd",
    "decoded_sell_volume_usd",
    "decoded_active_traders",
    "decoded_buyer_count",
    "decoded_seller_count",
    "buy_sell_imbalance",
    "median_trade_size_usd",
    "max_trade_size_usd",
    "first_decoded_trade_at",
    "last_decoded_trade_at",
    "moralis_window_status",
    "moralis_swaps_fetched",
    "moralis_pages_fetched",
    "pair_count",
    "top_pair_address",
    "top_pair_exchange_name",
    "top_pair_liquidity_usd",
    "top_pair_volume_24h_usd",
    "source",
]


def is_limit_stop_message(message: object) -> bool:
    text = str(message).lower()
    return any(marker in text for marker in LIMIT_STOP_MARKERS)


def parse_time(value: Any) -> datetime | None:
    if value is None or (not isinstance(value, (dict, list)) and pd.isna(value)):
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).astimezone(UTC)
    except ValueError:
        return None


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(value: Any) -> float:
    if value is None or value == "" or isinstance(value, (dict, list)):
        return np.nan
    try:
        if pd.isna(value):
            return np.nan
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def safe_int(value: Any) -> int | float:
    number = safe_float(value)
    return int(number) if not pd.isna(number) else np.nan


def nested_token_field(item: dict[str, Any], field: str) -> Any:
    for key in [field, field[0].upper() + field[1:]]:
        if key in item:
            return item[key]
    return ""


def token_address(item: dict[str, Any]) -> str:
    return str(
        item.get("address")
        or item.get("tokenAddress")
        or item.get("mint")
        or item.get("contractAddress")
        or ""
    )


def token_symbol(item: dict[str, Any]) -> str:
    return str(item.get("symbol") or item.get("tokenSymbol") or "")


def token_amount(item: dict[str, Any]) -> float:
    for field in ["amount", "amountFormatted", "tokenAmount", "value"]:
        value = item.get(field)
        number = safe_float(value)
        if not pd.isna(number):
            return number
    return np.nan


def token_usd_amount(item: dict[str, Any]) -> float:
    for field in ["usdAmount", "amountUsd", "amountUSD", "valueUsd", "totalValueUsd"]:
        value = item.get(field)
        number = safe_float(value)
        if not pd.isna(number):
            return number
    return np.nan


def moralis_get(
    *,
    api_key: str,
    path: str,
    params: dict[str, Any],
    timeout: float,
    retries: int,
    sleep: float,
) -> tuple[dict[str, Any], str, int | None]:
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value not in (None, "")})
    url = f"{MORALIS_BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"
    headers = {
        "Accept": "application/json",
        "X-API-Key": api_key,
        "Origin": "https://docs.moralis.com",
        "Referer": "https://docs.moralis.com/",
        "User-Agent": USER_AGENT,
    }
    last_message = "unknown"
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload if isinstance(payload, dict) else {"result": payload}, "ok", response.status
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_message = f"HTTP {exc.code}: {body[:500]}"
            if is_limit_stop_message(last_message):
                return {"error": last_message}, "quota_or_access_stop", exc.code
        except (urllib.error.URLError, TimeoutError, socket.timeout, json.JSONDecodeError) as exc:
            last_message = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(sleep * (attempt + 1))
    return {"error": last_message}, "api_error", None


def read_existing(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)


def sample_tokens(config: Any, *, max_tokens: int, strategy: str, mints: list[str]) -> pd.DataFrame:
    all_graduated = pd.read_csv(config.source_path("red_pump_graduated_for_dune")).copy()
    all_graduated["graduated_at_dt"] = pd.to_datetime(all_graduated["graduated_at"], utc=True, errors="coerce")
    all_graduated = all_graduated.dropna(subset=["graduated_at_dt"]).reset_index(drop=False)
    all_graduated = all_graduated.rename(columns={"index": "graduated_index"})
    all_graduated["mint"] = all_graduated["mint"].astype(str)
    if mints:
        requested = {str(mint) for mint in mints}
        return all_graduated.loc[all_graduated["mint"].isin(requested)].reset_index(drop=True)
    if strategy == "high_rpc_activity":
        rpc_path = config.output_root / "external_validation" / "h1_rpc_token_level_outcomes.csv"
        rpc = read_existing(rpc_path, ["mint"])
        if {"mint", "swap_count_30d"}.issubset(rpc.columns):
            rpc = rpc.copy()
            rpc["mint"] = rpc["mint"].astype(str)
            rpc["complete_30d_numeric"] = pd.to_numeric(rpc.get("complete_30d", 0), errors="coerce").fillna(0)
            rpc["swap_count_30d_numeric"] = pd.to_numeric(rpc["swap_count_30d"], errors="coerce").fillna(-1)
            ranked = rpc.sort_values(
                ["complete_30d_numeric", "swap_count_30d_numeric"],
                ascending=[False, False],
            )[["mint"]]
            selected = ranked.merge(all_graduated, on="mint", how="inner")
            if len(selected):
                return selected.head(max_tokens).reset_index(drop=True)
    if strategy == "latest":
        return all_graduated.sort_values("graduated_at_dt").tail(max_tokens).reset_index(drop=True)
    if strategy == "first":
        return all_graduated.sort_values("graduated_at_dt").head(max_tokens).reset_index(drop=True)
    positions = np.linspace(0, len(all_graduated) - 1, min(max_tokens, len(all_graduated))).round().astype(int)
    return all_graduated.sort_values("graduated_at_dt").iloc[sorted(set(positions))].reset_index(drop=True)


def flatten_swap(
    *,
    mint: str,
    graduated_at: datetime,
    horizon: int,
    window_start: datetime,
    window_end: datetime,
    item: dict[str, Any],
) -> dict[str, Any]:
    bought = item.get("bought") if isinstance(item.get("bought"), dict) else {}
    sold = item.get("sold") if isinstance(item.get("sold"), dict) else {}
    base = item.get("baseToken") if isinstance(item.get("baseToken"), dict) else {}
    quote = item.get("quoteToken") if isinstance(item.get("quoteToken"), dict) else {}
    return {
        "mint": mint,
        "graduated_at": graduated_at.isoformat(),
        "horizon_days": horizon,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "transaction_hash": item.get("transactionHash", ""),
        "transaction_index": safe_int(item.get("transactionIndex")),
        "transaction_type": item.get("transactionType", ""),
        "block_timestamp": item.get("blockTimestamp", ""),
        "block_number": safe_int(item.get("blockNumber")),
        "wallet_address": item.get("walletAddress", ""),
        "pair_address": item.get("pairAddress", ""),
        "pair_label": item.get("pairLabel", ""),
        "exchange_name": item.get("exchangeName", ""),
        "exchange_address": item.get("exchangeAddress", ""),
        "subcategory": item.get("subCategory", ""),
        "base_quote_price": safe_float(item.get("baseQuotePrice")),
        "base_token_address": token_address(base),
        "base_token_symbol": token_symbol(base),
        "quote_token_address": token_address(quote),
        "quote_token_symbol": token_symbol(quote),
        "bought_token_address": token_address(bought),
        "bought_token_symbol": token_symbol(bought),
        "bought_amount": token_amount(bought),
        "bought_usd_amount": token_usd_amount(bought),
        "sold_token_address": token_address(sold),
        "sold_token_symbol": token_symbol(sold),
        "sold_amount": token_amount(sold),
        "sold_usd_amount": token_usd_amount(sold),
        "total_value_usd": safe_float(item.get("totalValueUsd")),
        "source": "Moralis Solana Token Swaps API",
    }


def flatten_pair(*, mint: str, item: dict[str, Any]) -> dict[str, Any]:
    base = item.get("baseToken") if isinstance(item.get("baseToken"), dict) else {}
    quote = item.get("quoteToken") if isinstance(item.get("quoteToken"), dict) else {}
    return {
        "mint": mint,
        "pair_address": item.get("pairAddress", ""),
        "pair_label": item.get("pairLabel", ""),
        "exchange_name": item.get("exchangeName", ""),
        "exchange_address": item.get("exchangeAddress", ""),
        "base_token_address": token_address(base),
        "base_token_symbol": token_symbol(base),
        "quote_token_address": token_address(quote),
        "quote_token_symbol": token_symbol(quote),
        "usd_price": safe_float(item.get("usdPrice")),
        "liquidity_usd": safe_float(item.get("liquidityUsd")),
        "volume_24h_usd": safe_float(item.get("volume24hrUsd") or item.get("volume24hUsd")),
        "pair_created_at": item.get("pairCreatedAt", ""),
        "source": "Moralis Solana Token Pairs API",
    }


def fetch_pairs(
    *,
    api_key: str,
    network: str,
    mint: str,
    limit: int,
    timeout: float,
    retries: int,
    sleep: float,
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    payload, status, http_status = moralis_get(
        api_key=api_key,
        path=f"/token/{network}/{mint}/pairs",
        params={"limit": limit},
        timeout=timeout,
        retries=retries,
        sleep=sleep,
    )
    if status != "ok":
        message = str(payload.get("error", status))
        return [], {
            "mint": mint,
            "endpoint": "token_pairs",
            "horizon_days": np.nan,
            "graduated_at": "",
            "status": status,
            "http_status": http_status,
            "rows_fetched": 0,
            "pages_fetched": 0,
            "cursor_remaining": False,
            "message": message,
        }, is_limit_stop_message(message)
    result = payload.get("pairs", payload.get("result", []))
    if not isinstance(result, list):
        result = []
    rows = [flatten_pair(mint=mint, item=item) for item in result if isinstance(item, dict)]
    return rows, {
        "mint": mint,
        "endpoint": "token_pairs",
        "horizon_days": np.nan,
        "graduated_at": "",
        "status": "ok" if rows else "empty",
        "http_status": http_status,
        "rows_fetched": len(rows),
        "pages_fetched": 1,
        "cursor_remaining": False,
        "message": "",
    }, False


def fetch_swaps_window(
    *,
    api_key: str,
    network: str,
    mint: str,
    graduated_at: datetime,
    horizon: int,
    limit: int,
    max_pages: int,
    timeout: float,
    retries: int,
    sleep: float,
    raw_dir: Path | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    window_start = graduated_at
    window_end = graduated_at + timedelta(days=horizon)
    rows: list[dict[str, Any]] = []
    cursor = ""
    pages = 0
    status = "empty"
    http_status: int | None = None
    message = ""
    stop = False
    for page_idx in range(1, max_pages + 1):
        payload, request_status, http_status = moralis_get(
            api_key=api_key,
            path=f"/token/{network}/{mint}/swaps",
            params={
                "limit": limit,
                "cursor": cursor,
                "order": "ASC",
                "fromDate": iso_z(window_start),
                "toDate": iso_z(window_end),
                "transactionTypes": "buy,sell",
            },
            timeout=timeout,
            retries=retries,
            sleep=sleep,
        )
        if raw_dir is not None:
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir / f"{mint}_{horizon}d_page{page_idx:03d}.json"
            raw_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        if request_status != "ok":
            message = str(payload.get("error", request_status))
            status = request_status
            stop = is_limit_stop_message(message)
            break
        result = payload.get("result", [])
        if not isinstance(result, list):
            result = []
        rows.extend(
            flatten_swap(
                mint=mint,
                graduated_at=graduated_at,
                horizon=horizon,
                window_start=window_start,
                window_end=window_end,
                item=item,
            )
            for item in result
            if isinstance(item, dict)
        )
        pages += 1
        cursor = str(payload.get("cursor") or "")
        status = "ok" if rows else "empty"
        if not cursor or len(result) < limit:
            break
        time.sleep(sleep)
    if cursor and pages >= max_pages and status == "ok":
        status = "page_limit_reached_lower_bound"
    return rows, {
        "mint": mint,
        "endpoint": "token_swaps",
        "horizon_days": horizon,
        "graduated_at": graduated_at.isoformat(),
        "status": status,
        "http_status": http_status,
        "rows_fetched": len(rows),
        "pages_fetched": pages,
        "cursor_remaining": bool(cursor),
        "message": message,
    }, stop


def infer_horizon_status(base_status: str, cursor_remaining: bool, last_timestamp: datetime | None, horizon_end: datetime) -> str:
    if base_status in {"quota_or_access_stop", "api_error"}:
        return base_status
    if not cursor_remaining:
        return "ok" if base_status != "empty" else "empty"
    if last_timestamp is not None and last_timestamp >= horizon_end:
        return "ok"
    return "page_limit_reached_lower_bound"


def fetch_swaps_all_horizons_once(
    *,
    api_key: str,
    network: str,
    mint: str,
    graduated_at: datetime,
    limit: int,
    max_pages: int,
    timeout: float,
    retries: int,
    sleep: float,
    raw_dir: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    max_horizon = max(HORIZONS)
    window_start = graduated_at
    window_end = graduated_at + timedelta(days=max_horizon)
    fetched: list[dict[str, Any]] = []
    cursor = ""
    pages = 0
    status = "empty"
    http_status: int | None = None
    message = ""
    stop = False
    for page_idx in range(1, max_pages + 1):
        payload, request_status, http_status = moralis_get(
            api_key=api_key,
            path=f"/token/{network}/{mint}/swaps",
            params={
                "limit": limit,
                "cursor": cursor,
                "order": "ASC",
                "fromDate": iso_z(window_start),
                "toDate": iso_z(window_end),
                "transactionTypes": "buy,sell",
            },
            timeout=timeout,
            retries=retries,
            sleep=sleep,
        )
        if raw_dir is not None:
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir / f"{mint}_30d_once_page{page_idx:03d}.json"
            raw_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        if request_status != "ok":
            message = str(payload.get("error", request_status))
            status = request_status
            stop = is_limit_stop_message(message)
            break
        result = payload.get("result", [])
        if not isinstance(result, list):
            result = []
        fetched.extend(item for item in result if isinstance(item, dict))
        pages += 1
        cursor = str(payload.get("cursor") or "")
        status = "ok" if fetched else "empty"
        if not cursor or len(result) < limit:
            break
        time.sleep(sleep)
    if cursor and pages >= max_pages and status == "ok":
        status = "page_limit_reached_lower_bound"

    timestamped: list[tuple[dict[str, Any], datetime | None]] = [
        (item, parse_time(item.get("blockTimestamp"))) for item in fetched
    ]
    last_timestamp = max((ts for _, ts in timestamped if ts is not None), default=None)
    rows: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        horizon_end = graduated_at + timedelta(days=horizon)
        inside = [(item, ts) for item, ts in timestamped if ts is not None and window_start <= ts < horizon_end]
        rows.extend(
            flatten_swap(
                mint=mint,
                graduated_at=graduated_at,
                horizon=horizon,
                window_start=window_start,
                window_end=horizon_end,
                item=item,
            )
            for item, _ in inside
        )
        statuses.append(
            {
                "mint": mint,
                "endpoint": "token_swaps",
                "horizon_days": horizon,
                "graduated_at": graduated_at.isoformat(),
                "status": infer_horizon_status(status, bool(cursor), last_timestamp, horizon_end),
                "http_status": http_status,
                "rows_fetched": len(inside),
                "pages_fetched": pages,
                "cursor_remaining": bool(cursor),
                "message": message,
            }
        )
    return rows, statuses, stop


def top_pair_for_mint(pairs: pd.DataFrame, mint: str) -> dict[str, Any]:
    if pairs.empty or "mint" not in pairs:
        return {}
    token_pairs = pairs.loc[pairs["mint"].astype(str).eq(mint)].copy()
    if token_pairs.empty:
        return {}
    token_pairs["volume_24h_usd_num"] = pd.to_numeric(token_pairs.get("volume_24h_usd"), errors="coerce")
    token_pairs["liquidity_usd_num"] = pd.to_numeric(token_pairs.get("liquidity_usd"), errors="coerce")
    token_pairs = token_pairs.sort_values(["volume_24h_usd_num", "liquidity_usd_num"], ascending=[False, False])
    return token_pairs.iloc[0].to_dict()


def aggregate_outcomes(swaps: pd.DataFrame, pairs: pd.DataFrame, statuses: pd.DataFrame) -> pd.DataFrame:
    if statuses.empty:
        return pd.DataFrame(columns=OUTCOME_COLUMNS)
    swap_status = statuses.loc[statuses["endpoint"].astype(str).eq("token_swaps")].copy()
    if swap_status.empty:
        return pd.DataFrame(columns=OUTCOME_COLUMNS)
    rows: list[dict[str, Any]] = []
    working_swaps = swaps.copy() if not swaps.empty else pd.DataFrame(columns=SWAP_COLUMNS)
    if not working_swaps.empty:
        dedupe_cols = [col for col in ["mint", "horizon_days", "transaction_hash", "transaction_index"] if col in working_swaps]
        if dedupe_cols:
            working_swaps = working_swaps.drop_duplicates(dedupe_cols)
        working_swaps["total_value_usd_num"] = pd.to_numeric(working_swaps["total_value_usd"], errors="coerce")
        working_swaps["timestamp_dt"] = pd.to_datetime(working_swaps["block_timestamp"], utc=True, errors="coerce")
        working_swaps["transaction_type_norm"] = working_swaps["transaction_type"].astype(str).str.lower()
    for status in swap_status.itertuples(index=False):
        mint = str(status.mint)
        horizon = int(status.horizon_days)
        graduated_at = parse_time(status.graduated_at)
        if graduated_at is None:
            continue
        subset = working_swaps.loc[
            working_swaps.get("mint", pd.Series(dtype=str)).astype(str).eq(mint)
            & pd.to_numeric(working_swaps.get("horizon_days", pd.Series(dtype=float)), errors="coerce").eq(horizon)
        ].copy()
        volumes = pd.to_numeric(subset.get("total_value_usd_num", pd.Series(dtype=float)), errors="coerce")
        buys = subset.loc[subset.get("transaction_type_norm", pd.Series(dtype=str)).eq("buy")]
        sells = subset.loc[subset.get("transaction_type_norm", pd.Series(dtype=str)).eq("sell")]
        buyers = set(buys.get("wallet_address", pd.Series(dtype=str)).dropna().astype(str)) - {""}
        sellers = set(sells.get("wallet_address", pd.Series(dtype=str)).dropna().astype(str)) - {""}
        traders = set(subset.get("wallet_address", pd.Series(dtype=str)).dropna().astype(str)) - {""}
        first_ts = subset["timestamp_dt"].min() if "timestamp_dt" in subset and len(subset) else pd.NaT
        last_ts = subset["timestamp_dt"].max() if "timestamp_dt" in subset and len(subset) else pd.NaT
        pair_count = int(pairs.loc[pairs["mint"].astype(str).eq(mint), "pair_address"].nunique()) if not pairs.empty else 0
        top_pair = top_pair_for_mint(pairs, mint)
        buy_volume = float(pd.to_numeric(buys.get("total_value_usd", pd.Series(dtype=float)), errors="coerce").sum())
        sell_volume = float(pd.to_numeric(sells.get("total_value_usd", pd.Series(dtype=float)), errors="coerce").sum())
        denom = int(len(buys) + len(sells))
        rows.append(
            {
                "mint": mint,
                "horizon_days": horizon,
                "graduated_at": graduated_at.isoformat(),
                "window_start": graduated_at.isoformat(),
                "window_end": (graduated_at + timedelta(days=horizon)).isoformat(),
                "decoded_trade_count": int(len(subset)),
                "decoded_buy_count": int(len(buys)),
                "decoded_sell_count": int(len(sells)),
                "decoded_volume_usd": float(volumes.sum()) if len(volumes) else 0.0,
                "decoded_buy_volume_usd": buy_volume,
                "decoded_sell_volume_usd": sell_volume,
                "decoded_active_traders": int(len(traders)),
                "decoded_buyer_count": int(len(buyers)),
                "decoded_seller_count": int(len(sellers)),
                "buy_sell_imbalance": float((len(buys) - len(sells)) / denom) if denom else np.nan,
                "median_trade_size_usd": float(volumes.median()) if len(volumes.dropna()) else np.nan,
                "max_trade_size_usd": float(volumes.max()) if len(volumes.dropna()) else np.nan,
                "first_decoded_trade_at": first_ts.isoformat() if pd.notna(first_ts) else "",
                "last_decoded_trade_at": last_ts.isoformat() if pd.notna(last_ts) else "",
                "moralis_window_status": status.status,
                "moralis_swaps_fetched": int(status.rows_fetched),
                "moralis_pages_fetched": int(status.pages_fetched),
                "pair_count": pair_count,
                "top_pair_address": top_pair.get("pair_address", ""),
                "top_pair_exchange_name": top_pair.get("exchange_name", ""),
                "top_pair_liquidity_usd": safe_float(top_pair.get("liquidity_usd")),
                "top_pair_volume_24h_usd": safe_float(top_pair.get("volume_24h_usd")),
                "source": "Moralis decoded Solana token swaps, aggregated by migration-relative horizon",
            }
        )
    return pd.DataFrame(rows, columns=OUTCOME_COLUMNS)


def summarize_collection(
    *,
    outcomes: pd.DataFrame,
    swaps: pd.DataFrame,
    pairs: pd.DataFrame,
    statuses: pd.DataFrame,
    all_graduated_tokens: int,
    tokens_requested: int,
    sample_strategy: str,
    network: str,
    limit: int,
    max_pages: int,
    stop_reason: str,
    cu_budget: int,
    cu_used_before_run: int,
    estimated_cu_used_this_run: int,
    reserve_cu: int,
) -> dict[str, Any]:
    outcome30 = outcomes.loc[outcomes["horizon_days"].eq(30)].copy() if not outcomes.empty else pd.DataFrame()
    volume30 = pd.to_numeric(outcome30.get("decoded_volume_usd", pd.Series(dtype=float)), errors="coerce")
    trades30 = pd.to_numeric(outcome30.get("decoded_trade_count", pd.Series(dtype=float)), errors="coerce")
    active30 = pd.to_numeric(outcome30.get("decoded_active_traders", pd.Series(dtype=float)), errors="coerce")
    tokens_with_30d_swaps = int(outcome30.loc[trades30.gt(0), "mint"].nunique()) if len(outcome30) else 0
    tokens_with_30d_volume = int(outcome30.loc[volume30.gt(0), "mint"].nunique()) if len(outcome30) else 0
    decoded_tokens = int(outcomes.loc[pd.to_numeric(outcomes["decoded_trade_count"], errors="coerce").gt(0), "mint"].nunique()) if len(outcomes) else 0
    unique_swap_rows = (
        int(len(swaps.drop_duplicates([col for col in ["mint", "transaction_hash", "transaction_index"] if col in swaps])))
        if len(swaps)
        else 0
    )
    credible = tokens_with_30d_swaps >= 50 and unique_swap_rows >= 500
    if stop_reason and len(outcomes):
        status = "stopped_moralis_decoded_outcome_sample_partial"
    elif len(outcomes):
        status = "computed_moralis_decoded_outcome_sample"
    elif stop_reason:
        status = "blocked_or_stopped_moralis_decoded_outcomes"
    else:
        status = "computed_moralis_decoded_outcome_empty"
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "credible_sample_status": (
            "credible_moralis_decoded_sample" if credible else "pilot_moralis_decoded_sample" if decoded_tokens else "no_decoded_swaps_observed"
        ),
        "network": network,
        "all_graduated_tokens_available": int(all_graduated_tokens),
        "tokens_requested": int(tokens_requested),
        "sample_strategy": sample_strategy,
        "horizons_days": list(HORIZONS),
        "limit_per_page": int(limit),
        "max_pages_per_token_horizon": int(max_pages),
        "cu_budget": int(cu_budget),
        "cu_used_before_run": int(cu_used_before_run),
        "reserve_cu": int(reserve_cu),
        "estimated_cu_used_this_run": int(estimated_cu_used_this_run),
        "estimated_cu_used_total_after_run": int(cu_used_before_run + estimated_cu_used_this_run),
        "estimated_cu_remaining_after_run": (
            int(cu_budget - cu_used_before_run - estimated_cu_used_this_run) if cu_budget else np.nan
        ),
        "decoded_outcome_rows": int(len(outcomes)),
        "decoded_swap_rows": int(len(swaps)),
        "unique_decoded_swap_rows": unique_swap_rows,
        "decoded_pair_rows": int(len(pairs)),
        "status_rows": int(len(statuses)),
        "tokens_with_pairs": int(pairs["mint"].nunique()) if len(pairs) else 0,
        "tokens_with_decoded_outcomes": decoded_tokens,
        "decoded_30d_tokens": int(outcome30["mint"].nunique()) if len(outcome30) else 0,
        "decoded_30d_tokens_with_swaps": tokens_with_30d_swaps,
        "decoded_30d_tokens_with_positive_volume_usd": tokens_with_30d_volume,
        "decoded_30d_positive_volume_share": float(tokens_with_30d_volume / len(outcome30)) if len(outcome30) else np.nan,
        "decoded_30d_median_volume_usd": float(volume30.median()) if len(volume30.dropna()) else np.nan,
        "decoded_30d_median_trade_count": float(trades30.median()) if len(trades30.dropna()) else np.nan,
        "decoded_30d_median_active_traders": float(active30.median()) if len(active30.dropna()) else np.nan,
        "api_calls_recorded": int(len(statuses)),
        "collection_stop_reason": stop_reason,
        "sample_decoding_level": "Moralis Solana Token Swaps API decoded buy/sell swaps with USD value, wallet, pair, and exchange fields.",
        "claim_boundary": (
            "This is a decoded Moralis sample for application-arm H1/H4 measurement infrastructure. "
            "It strengthens token-level outcome measurement for covered tokens, but it is not by itself "
            "a full-cohort welfare causal estimate or the identification-arm cross-chain staggered DiD."
        ),
        "docs": {
            "token_swaps": "https://docs.moralis.com/data-api/solana/token/swaps/token-swaps",
            "token_pairs": "https://docs.moralis.com/data-api/solana/token/pairs/token-pairs",
        },
    }


def write_outputs(
    *,
    out_dir: Path,
    tables_dir: Path,
    swaps: pd.DataFrame,
    pairs: pd.DataFrame,
    statuses: pd.DataFrame,
    all_graduated_tokens: int,
    tokens_requested: int,
    sample_strategy: str,
    network: str,
    limit: int,
    max_pages: int,
    stop_reason: str,
    cu_budget: int,
    cu_used_before_run: int,
    estimated_cu_used_this_run: int,
    reserve_cu: int,
) -> dict[str, Any]:
    outcomes = aggregate_outcomes(swaps, pairs, statuses)
    write_csv(out_dir / "moralis_token_swaps.csv", swaps if len(swaps) else pd.DataFrame(columns=SWAP_COLUMNS))
    write_csv(out_dir / "moralis_token_pairs.csv", pairs if len(pairs) else pd.DataFrame(columns=PAIR_COLUMNS))
    write_csv(out_dir / "moralis_fetch_status.csv", statuses if len(statuses) else pd.DataFrame(columns=STATUS_COLUMNS))
    write_csv(out_dir / "moralis_decoded_token_outcomes.csv", outcomes)
    summary = summarize_collection(
        outcomes=outcomes,
        swaps=swaps,
        pairs=pairs,
        statuses=statuses,
        all_graduated_tokens=all_graduated_tokens,
        tokens_requested=tokens_requested,
        sample_strategy=sample_strategy,
        network=network,
        limit=limit,
        max_pages=max_pages,
        stop_reason=stop_reason,
        cu_budget=cu_budget,
        cu_used_before_run=cu_used_before_run,
        estimated_cu_used_this_run=estimated_cu_used_this_run,
        reserve_cu=reserve_cu,
    )
    write_json(tables_dir / "moralis_decoded_outcomes_summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs" / "pumpswap_case.json"))
    parser.add_argument("--network", default=DEFAULT_NETWORK)
    parser.add_argument("--max-tokens", type=int, default=80)
    parser.add_argument("--mint", action="append", default=[])
    parser.add_argument(
        "--sample-strategy",
        choices=["high_rpc_activity", "evenly_spaced", "latest", "first"],
        default="high_rpc_activity",
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--pair-limit", type=int, default=50)
    parser.add_argument("--skip-pairs", action="store_true")
    parser.add_argument(
        "--fetch-mode",
        choices=["thirty_day_once", "per_horizon"],
        default="thirty_day_once",
        help="Use one 30d swap stream per token and split locally, or call each horizon separately.",
    )
    parser.add_argument("--cu-budget", type=int, default=0, help="Optional total account CU budget for this run.")
    parser.add_argument("--cu-used", type=int, default=0, help="Optional CU already used before this run.")
    parser.add_argument("--reserve-cu", type=int, default=500, help="Do not intentionally spend into this final CU reserve.")
    parser.add_argument("--swaps-cu-cost", type=int, default=50, help="Estimated Moralis CU cost per Token Swaps page.")
    parser.add_argument("--pairs-cu-cost", type=int, default=50, help="Estimated Moralis CU cost per Token Pairs call.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--save-raw-json", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=0.12)
    parser.add_argument("--checkpoint-every", type=int, default=5)
    args = parser.parse_args()

    api_key = os.environ.get("MORALIS_API_KEY", "")
    config = load_config(args.config)
    out_dir = config.output_root / "external_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not api_key:
        summary = {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "status": "not_run_missing_moralis_api_key",
            "credible_sample_status": "missing_key",
            "collection_stop_reason": "MORALIS_API_KEY is not set",
            "claim_boundary": "No Moralis decoded outcome claim can be made without running the collector.",
        }
        write_json(config.tables_dir / "moralis_decoded_outcomes_summary.json", summary)
        write_csv(out_dir / "moralis_token_swaps.csv", pd.DataFrame(columns=SWAP_COLUMNS))
        write_csv(out_dir / "moralis_token_pairs.csv", pd.DataFrame(columns=PAIR_COLUMNS))
        write_csv(out_dir / "moralis_fetch_status.csv", pd.DataFrame(columns=STATUS_COLUMNS))
        write_csv(out_dir / "moralis_decoded_token_outcomes.csv", pd.DataFrame(columns=OUTCOME_COLUMNS))
        print(json.dumps(summary, indent=2))
        raise SystemExit(1)

    tokens = sample_tokens(config, max_tokens=args.max_tokens, strategy=args.sample_strategy, mints=args.mint)
    all_graduated_tokens = len(pd.read_csv(config.source_path("red_pump_graduated_for_dune"), usecols=["mint"]))
    raw_dir = out_dir / "moralis_raw" if args.save_raw_json else None

    swaps = read_existing(out_dir / "moralis_token_swaps.csv", SWAP_COLUMNS) if args.resume else pd.DataFrame(columns=SWAP_COLUMNS)
    pairs = read_existing(out_dir / "moralis_token_pairs.csv", PAIR_COLUMNS) if args.resume else pd.DataFrame(columns=PAIR_COLUMNS)
    statuses = read_existing(out_dir / "moralis_fetch_status.csv", STATUS_COLUMNS) if args.resume else pd.DataFrame(columns=STATUS_COLUMNS)
    stop_reason = ""
    completed_swaps = set()
    completed_pairs = set()
    if args.resume and not statuses.empty:
        for row in statuses.itertuples(index=False):
            if str(row.endpoint) == "token_swaps":
                completed_swaps.add((str(row.mint), int(row.horizon_days)))
            elif str(row.endpoint) == "token_pairs":
                completed_pairs.add(str(row.mint))
    estimated_cu_used_this_run = 0
    planned_available_cu = (
        max(args.cu_budget - args.cu_used - args.reserve_cu, 0) if args.cu_budget else None
    )

    def pages_available_for(cost_per_page: int, requested_pages: int) -> int:
        nonlocal estimated_cu_used_this_run
        if planned_available_cu is None:
            return requested_pages
        remaining = planned_available_cu - estimated_cu_used_this_run
        if remaining < cost_per_page:
            return 0
        return min(requested_pages, int(remaining // cost_per_page))

    def record_cu(cost: int) -> None:
        nonlocal estimated_cu_used_this_run
        estimated_cu_used_this_run += int(max(cost, 0))

    print(
        f"Starting Moralis decoded collection: tokens={len(tokens)}, strategy={args.sample_strategy}, "
        f"limit={args.limit}, max_pages={args.max_pages}, fetch_mode={args.fetch_mode}, "
        f"planned_available_cu={planned_available_cu if planned_available_cu is not None else 'unbounded'}",
        flush=True,
    )
    for index, token in tokens.iterrows():
        mint = str(token["mint"])
        graduated_at = parse_time(token["graduated_at"])
        if graduated_at is None:
            continue
        print(f"{index + 1}/{len(tokens)} {mint}: collecting", flush=True)
        if not args.skip_pairs and mint not in completed_pairs:
            if pages_available_for(args.pairs_cu_cost, 1) <= 0:
                stop_reason = "estimated_cu_budget_reached_before_token_pairs"
                print("Stopping collection because the configured CU budget was reached.", flush=True)
                break
            pair_rows, pair_status, stop = fetch_pairs(
                api_key=api_key,
                network=args.network,
                mint=mint,
                limit=args.pair_limit,
                timeout=args.timeout,
                retries=args.retries,
                sleep=args.sleep,
            )
            if pair_rows:
                pairs = pd.concat([pairs, pd.DataFrame(pair_rows, columns=PAIR_COLUMNS)], ignore_index=True)
            statuses = pd.concat([statuses, pd.DataFrame([pair_status], columns=STATUS_COLUMNS)], ignore_index=True)
            record_cu(args.pairs_cu_cost)
            if stop:
                stop_reason = f"token_pairs:{pair_status['status']}:{pair_status['message']}"
                print("Stopping collection because Moralis returned an access/quota error.", flush=True)
                break
            time.sleep(args.sleep)
        if args.fetch_mode == "thirty_day_once":
            if all((mint, horizon) in completed_swaps for horizon in HORIZONS):
                continue
            allowed_pages = pages_available_for(args.swaps_cu_cost, args.max_pages)
            if allowed_pages <= 0:
                stop_reason = "estimated_cu_budget_reached_before_token_swaps"
                print("Stopping collection because the configured CU budget was reached.", flush=True)
                break
            swap_rows, swap_status_rows, stop = fetch_swaps_all_horizons_once(
                api_key=api_key,
                network=args.network,
                mint=mint,
                graduated_at=graduated_at,
                limit=args.limit,
                max_pages=allowed_pages,
                timeout=args.timeout,
                retries=args.retries,
                sleep=args.sleep,
                raw_dir=raw_dir,
            )
            if swap_rows:
                swaps = pd.concat([swaps, pd.DataFrame(swap_rows, columns=SWAP_COLUMNS)], ignore_index=True)
            statuses = pd.concat([statuses, pd.DataFrame(swap_status_rows, columns=STATUS_COLUMNS)], ignore_index=True)
            pages_used = max((int(row.get("pages_fetched", 0) or 0) for row in swap_status_rows), default=0)
            record_cu(pages_used * args.swaps_cu_cost)
            for swap_status in swap_status_rows:
                print(
                    f"{index + 1}/{len(tokens)} {mint}: {swap_status['horizon_days']}d "
                    f"rows={swap_status['rows_fetched']} status={swap_status['status']}",
                    flush=True,
                )
            if stop:
                message = "; ".join(str(row.get("message", "")) for row in swap_status_rows if row.get("message"))
                stop_reason = f"token_swaps_30d_once:{message}"
                print("Stopping collection because Moralis returned an access/quota error.", flush=True)
        else:
            for horizon in HORIZONS:
                if (mint, horizon) in completed_swaps:
                    continue
                allowed_pages = pages_available_for(args.swaps_cu_cost, args.max_pages)
                if allowed_pages <= 0:
                    stop_reason = "estimated_cu_budget_reached_before_token_swaps"
                    print("Stopping collection because the configured CU budget was reached.", flush=True)
                    break
                swap_rows, swap_status, stop = fetch_swaps_window(
                    api_key=api_key,
                    network=args.network,
                    mint=mint,
                    graduated_at=graduated_at,
                    horizon=horizon,
                    limit=args.limit,
                    max_pages=allowed_pages,
                    timeout=args.timeout,
                    retries=args.retries,
                    sleep=args.sleep,
                    raw_dir=raw_dir,
                )
                if swap_rows:
                    swaps = pd.concat([swaps, pd.DataFrame(swap_rows, columns=SWAP_COLUMNS)], ignore_index=True)
                statuses = pd.concat([statuses, pd.DataFrame([swap_status], columns=STATUS_COLUMNS)], ignore_index=True)
                record_cu(int(swap_status["pages_fetched"]) * args.swaps_cu_cost)
                print(
                    f"{index + 1}/{len(tokens)} {mint}: {horizon}d rows={swap_status['rows_fetched']} "
                    f"status={swap_status['status']}",
                    flush=True,
                )
                if stop:
                    stop_reason = f"token_swaps_{horizon}d:{swap_status['status']}:{swap_status['message']}"
                    print("Stopping collection because Moralis returned an access/quota error.", flush=True)
                    break
                time.sleep(args.sleep)
        if args.checkpoint_every and (index + 1) % args.checkpoint_every == 0:
            summary = write_outputs(
                out_dir=out_dir,
                tables_dir=config.tables_dir,
                swaps=swaps,
                pairs=pairs,
                statuses=statuses,
                all_graduated_tokens=all_graduated_tokens,
                tokens_requested=len(tokens),
                sample_strategy=args.sample_strategy,
                network=args.network,
                limit=args.limit,
                max_pages=args.max_pages,
                stop_reason=stop_reason,
                cu_budget=args.cu_budget,
                cu_used_before_run=args.cu_used,
                estimated_cu_used_this_run=estimated_cu_used_this_run,
                reserve_cu=args.reserve_cu,
            )
            print(
                f"checkpoint: swaps={summary['decoded_swap_rows']}, "
                f"unique swaps={summary['unique_decoded_swap_rows']}, "
                f"30d decoded tokens={summary['decoded_30d_tokens_with_swaps']}, "
                f"estimated CU={estimated_cu_used_this_run}",
                flush=True,
            )
        if stop_reason:
            break

    summary = write_outputs(
        out_dir=out_dir,
        tables_dir=config.tables_dir,
        swaps=swaps,
        pairs=pairs,
        statuses=statuses,
        all_graduated_tokens=all_graduated_tokens,
        tokens_requested=len(tokens),
        sample_strategy=args.sample_strategy,
        network=args.network,
        limit=args.limit,
        max_pages=args.max_pages,
        stop_reason=stop_reason,
        cu_budget=args.cu_budget,
        cu_used_before_run=args.cu_used,
        estimated_cu_used_this_run=estimated_cu_used_this_run,
        reserve_cu=args.reserve_cu,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
