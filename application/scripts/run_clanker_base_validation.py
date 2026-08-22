#!/usr/bin/env python3
"""Validate the Clanker/Base v4.1 MEV-module rollout as a cross-chain application case.

The script can run from public JSON-RPC for bounded replication and can ingest
archive/indexer exports for the full-cohort path. It is deliberately
conservative: full-cohort causal claims require explicit full token-horizon and
holder reconstruction coverage rather than a public-RPC convenience sample.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / "artifacts" / "external_validation"
TABLES = ROOT / "artifacts" / "tables"

CLANKER_EVENT_ID = "CLANKER_SNIPER_DECAY_V41_BASE_20250826"
BASE_RPC = "https://base-rpc.publicnode.com"
DEFILLAMA_PRICE_URL = "https://coins.llama.fi/prices/historical/{timestamp}/coingecko:ethereum"

CLANKER_V4_FACTORY = "0xe85a59c628f7d27878aceb4bf3b35733630083a9"
UNISWAP_V4_POOL_MANAGER_BASE = "0x498581ff718922c3f8e6a244956af099b2652b2b"

TOKEN_CREATED_TOPIC = "0x9299d1d1a88d8e1abdc591ae7a167a6bc63a8f17d695804e9091ee33aa89fb67"
SWAP_TOPIC = "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

V41_HOOKS = {
    "0xd60d6b218116cfd801e28f78d011a203d2b068cc": "ClankerHookDynamicFeeV2",
    "0xb429d62f8f3bffb98cdb9569533ea23bf0ba28cc": "ClankerHookStaticFeeV2",
}
V40_HOOKS = {
    "0x34a45c6b61876d739400bd71228cbcbD4F53E8cC".lower(): "ClankerHookDynamicFee",
    "0xdd5eeaff7bd481ad55db083062b13a3cdf0a68cc": "ClankerHookStaticFee",
}
V41_MEV_MODULES = {
    "0xebb25bb797d82cb78e1bc70406b13233c0854413": "ClankerSniperAuctionV2",
}
V40_MEV_MODULES = {
    "0xfdc013ce003980889cffd66b0c8329545ae1d1e8": "ClankerSniperAuctionV0",
    "0xe143f9872a33c955f23cf442bb4b1efb3a7402a2": "ClankerMevBlockDelay",
}

BASE_WETH = "0x4200000000000000000000000000000000000006"
BASE_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TOKEN_DECIMALS = {
    BASE_WETH: 18,
    BASE_USDC: 6,
}


def iso_utc(timestamp: int | float | str | None) -> str:
    if timestamp in {None, ""}:
        return ""
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def word(data: str, index: int) -> int:
    return int(data[2 + 64 * index : 2 + 64 * (index + 1)], 16)


def address_from_word(value: int) -> str:
    return "0x" + f"{value:064x}"[-40:]


def topic_address(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def signed_word(value: int) -> int:
    if value >= 1 << 255:
        return value - (1 << 256)
    return value


def rpc(method: str, params: list[Any], *, endpoint: str, timeout: int = 30, retries: int = 4) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.post(
                endpoint,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                timeout=timeout,
            )
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(payload["error"])
            return payload["result"]
        except Exception as exc:  # pragma: no cover - network backoff
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"RPC call failed after {retries} attempts: {last_error}")


def block_for_timestamp(target_ts: int, *, endpoint: str) -> int:
    latest = int(rpc("eth_blockNumber", [], endpoint=endpoint), 16)
    lo, hi = 0, latest
    while lo < hi:
        mid = (lo + hi) // 2
        block = rpc("eth_getBlockByNumber", [hex(mid), False], endpoint=endpoint)
        mid_ts = int(block["timestamp"], 16)
        if mid_ts < target_ts:
            lo = mid + 1
        else:
            hi = mid
    return lo


def fetch_logs(
    *,
    endpoint: str,
    address: str | list[str],
    from_block: int,
    to_block: int,
    topics: list[Any] | None = None,
    chunk_size: int = 10_000,
    min_chunk_size: int = 1_000,
    label: str = "logs",
    progress: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = from_block
    current_chunk_size = chunk_size
    while start <= to_block:
        end = min(start + chunk_size - 1, to_block)
        log_filter: dict[str, Any] = {
            "fromBlock": hex(start),
            "toBlock": hex(end),
            "address": address,
        }
        if topics is not None:
            log_filter["topics"] = topics
        try:
            chunk = rpc("eth_getLogs", [log_filter], endpoint=endpoint, timeout=45)
        except RuntimeError:
            if current_chunk_size <= min_chunk_size:
                raise
            current_chunk_size = max(min_chunk_size, current_chunk_size // 2)
            chunk_size = current_chunk_size
            print(f"{label}: reducing chunk size to {current_chunk_size}", flush=True)
            continue
        rows.extend(chunk)
        if progress:
            print(f"{label}: blocks {start}-{end} logs={len(chunk)} total={len(rows)}", flush=True)
        start = end + 1
    return rows


def decode_token_created(log: dict[str, Any]) -> dict[str, Any]:
    data = log["data"]
    token = topic_address(log["topics"][1])
    token_admin = topic_address(log["topics"][2])
    hook = address_from_word(word(data, 7)).lower()
    mev_module = address_from_word(word(data, 11)).lower()
    if hook in V41_HOOKS or mev_module in V41_MEV_MODULES:
        clanker_version_class = "v4.1_mev_or_hook"
    elif hook in V40_HOOKS or mev_module in V40_MEV_MODULES:
        clanker_version_class = "v4.0_mev_or_hook"
    else:
        clanker_version_class = "other_or_unknown"

    return {
        "event_id": CLANKER_EVENT_ID,
        "block_number": int(log["blockNumber"], 16),
        "block_timestamp_utc": iso_utc(int(log.get("blockTimestamp", "0x0"), 16)),
        "block_timestamp_unix": int(log.get("blockTimestamp", "0x0"), 16),
        "transaction_hash": log["transactionHash"],
        "log_index": int(log["logIndex"], 16),
        "token_id": token,
        "token_admin": token_admin,
        "msg_sender": address_from_word(word(data, 0)).lower(),
        "starting_tick": signed_word(word(data, 6)),
        "pool_hook": hook,
        "pool_hook_label": V41_HOOKS.get(hook) or V40_HOOKS.get(hook) or "other_or_unknown",
        "pool_id": "0x" + data[2 + 64 * 8 : 2 + 64 * 9],
        "paired_token": address_from_word(word(data, 9)).lower(),
        "locker": address_from_word(word(data, 10)).lower(),
        "mev_module": mev_module,
        "mev_module_label": V41_MEV_MODULES.get(mev_module)
        or V40_MEV_MODULES.get(mev_module)
        or "other_or_unknown",
        "extensions_supply_raw": word(data, 12),
        "clanker_version_class": clanker_version_class,
        "token_created_topic": TOKEN_CREATED_TOPIC,
        "source_layer": "Base public JSON-RPC; Clanker v4 IClanker.TokenCreated event",
    }


def fetch_token_created_window(
    *,
    endpoint: str,
    start_block: int,
    end_block: int,
    chunk_size: int = 10_000,
) -> pd.DataFrame:
    logs = fetch_logs(
        endpoint=endpoint,
        address=CLANKER_V4_FACTORY,
        from_block=start_block,
        to_block=end_block,
        topics=[TOKEN_CREATED_TOPIC],
        chunk_size=chunk_size,
        label="clanker_token_created",
    )
    rows = [decode_token_created(log) for log in logs]
    if not rows:
        return pd.DataFrame(
            columns=[
                "event_id",
                "block_number",
                "block_timestamp_utc",
                "block_timestamp_unix",
                "transaction_hash",
                "log_index",
                "token_id",
                "token_admin",
                "msg_sender",
                "starting_tick",
                "pool_hook",
                "pool_hook_label",
                "pool_id",
                "paired_token",
                "locker",
                "mev_module",
                "mev_module_label",
                "extensions_supply_raw",
                "clanker_version_class",
                "token_created_topic",
                "source_layer",
            ]
        )
    return pd.DataFrame(rows).sort_values(["block_number", "log_index"]).reset_index(drop=True)


def merge_token_created_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    for column in ["transaction_hash", "log_index", "block_number"]:
        if column not in merged:
            raise RuntimeError(f"TokenCreated frame is missing required column: {column}")
    merged = merged.drop_duplicates(["transaction_hash", "log_index"]).copy()
    merged["block_number"] = pd.to_numeric(merged["block_number"], errors="coerce")
    merged["log_index"] = pd.to_numeric(merged["log_index"], errors="coerce")
    return merged.sort_values(["block_number", "log_index"]).reset_index(drop=True)


def load_token_created_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def load_or_fetch_token_created(
    *,
    endpoint: str,
    start_block: int,
    end_block: int,
    created_path: Path,
    reuse_existing: bool,
    append_existing: bool,
    import_path: Path | None,
    chunk_size: int,
) -> pd.DataFrame:
    imported = load_token_created_csv(import_path) if import_path is not None else pd.DataFrame()
    existing = load_token_created_csv(created_path) if created_path.exists() else pd.DataFrame()
    if not imported.empty:
        created = merge_token_created_frames([existing if append_existing else pd.DataFrame(), imported])
        persist_created = created.copy()
        print(f"loaded token_created import rows={len(imported)} from {import_path}", flush=True)
    elif append_existing and not existing.empty:
        current_min = int(pd.to_numeric(existing["block_number"], errors="coerce").min())
        current_max = int(pd.to_numeric(existing["block_number"], errors="coerce").max())
        frames = [existing]
        if start_block < current_min:
            frames.append(
                fetch_token_created_window(
                    endpoint=endpoint,
                    start_block=start_block,
                    end_block=current_min - 1,
                    chunk_size=chunk_size,
                )
            )
        if end_block > current_max:
            frames.append(
                fetch_token_created_window(
                    endpoint=endpoint,
                    start_block=current_max + 1,
                    end_block=end_block,
                    chunk_size=chunk_size,
                )
            )
        created = merge_token_created_frames(frames)
        persist_created = created.copy()
        print(
            f"appended token_created rows={len(created)} existing_range={current_min}-{current_max} "
            f"requested_range={start_block}-{end_block}",
            flush=True,
        )
    elif reuse_existing and not existing.empty:
        created = existing.loc[
            pd.to_numeric(existing["block_number"], errors="coerce").between(start_block, end_block)
        ].copy()
        persist_created = existing.copy()
        print(f"reused token_created rows={len(created)} from {created_path}", flush=True)
    else:
        created = fetch_token_created_window(
            endpoint=endpoint,
            start_block=start_block,
            end_block=end_block,
            chunk_size=chunk_size,
        )
        persist_created = created.copy()
    created = created.loc[pd.to_numeric(created["block_number"], errors="coerce").between(start_block, end_block)].copy()
    if created.empty:
        raise RuntimeError("No Clanker TokenCreated rows found in the requested window.")
    created.attrs["persist_token_created"] = persist_created
    return created


def write_token_created_scan_summary(
    *,
    created: pd.DataFrame,
    search_start_block: int,
    search_end_block: int,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    created_path = output_dir / "clanker_base_token_created.csv"
    summary_path = TABLES / "clanker_base_token_created_scan_summary.json"
    persist_created = created.attrs.get("persist_token_created", created)
    if isinstance(persist_created, pd.DataFrame) and not persist_created.empty:
        persist_created.to_csv(created_path, index=False)
    else:
        created.to_csv(created_path, index=False)
    counts = Counter(created["clanker_version_class"])
    v41 = created.loc[created["clanker_version_class"].eq("v4.1_mev_or_hook")].copy()
    summary = {
        "event_id": CLANKER_EVENT_ID,
        "status": "token_created_scan_only",
        "search_start_block": search_start_block,
        "search_end_block": search_end_block,
        "token_created_rows": int(len(created)),
        "persisted_token_created_rows": int(len(persist_created)) if isinstance(persist_created, pd.DataFrame) else int(len(created)),
        "version_class_counts": dict(counts),
        "first_v41_block": int(v41["block_number"].min()) if not v41.empty else "",
        "last_v41_block": int(v41["block_number"].max()) if not v41.empty else "",
        "first_v41_timestamp_utc": str(v41.sort_values(["block_number", "log_index"]).iloc[0]["block_timestamp_utc"])
        if not v41.empty
        else "",
        "last_v41_timestamp_utc": str(v41.sort_values(["block_number", "log_index"]).iloc[-1]["block_timestamp_utc"])
        if not v41.empty
        else "",
        "claim_boundary": (
            "Discovery scan only. Use to decide whether the Base cohort can be expanded before computing "
            "swap and holder horizons; it is not a token-outcome validation by itself."
        ),
        "outputs": {"token_created": str(created_path.relative_to(ROOT))},
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def select_matched_controls_fast(
    *,
    treated: pd.DataFrame,
    pre_pool: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match each post-activation row to the nearest unused pre-activation control.

    Because the control pool is restricted to launches before the first v4.1
    activation, nearest-by-absolute-block is equivalent to the most recent
    unused control, with same paired-token controls preferred when available.
    """

    controls = pre_pool.copy()
    controls["paired_token_norm"] = controls["paired_token"].astype(str).str.lower()
    controls = controls.sort_values(["block_number", "log_index"]).copy()
    global_stack = list(controls.index)
    pair_stacks: dict[str, list[int]] = {
        str(pair): list(group.index) for pair, group in controls.groupby("paired_token_norm", sort=False)
    }

    matched_control_rows: list[dict[str, Any]] = []
    treated_rows: list[dict[str, Any]] = []
    used_control_idx: set[int] = set()

    def pop_unused(stack: list[int]) -> int | None:
        while stack:
            idx = int(stack.pop())
            if idx not in used_control_idx:
                return idx
        return None

    for match_index, (_, token) in enumerate(treated.iterrows()):
        token_paired = str(token.get("paired_token", "")).lower()
        control_idx = pop_unused(pair_stacks.get(token_paired, []))
        if control_idx is None:
            control_idx = pop_unused(global_stack)
        if control_idx is None:
            break

        control = controls.loc[control_idx].drop(labels=["paired_token_norm"]).to_dict()
        treated_row = token.to_dict()
        match_id = f"clanker_v41_match_{match_index:04d}"
        distance = abs(int(control["block_number"]) - int(treated_row["block_number"]))
        control["cohort_match_id"] = match_id
        control["match_distance_blocks"] = distance
        treated_row["cohort_match_id"] = match_id
        treated_row["match_distance_blocks"] = distance
        matched_control_rows.append(control)
        treated_rows.append(treated_row)
        used_control_idx.add(control_idx)

    return pd.DataFrame(matched_control_rows), pd.DataFrame(treated_rows)


def select_cohort(
    created: pd.DataFrame,
    tokens_per_side: int,
    *,
    selection_mode: str,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    v41 = created.loc[created["clanker_version_class"].eq("v4.1_mev_or_hook")].copy()
    if v41.empty:
        raise RuntimeError("No v4.1 Clanker launches found in the search window.")
    activation = v41.iloc[0].to_dict()
    activation_block = int(activation["block_number"])

    pre_pool = (
        created.loc[
            created["clanker_version_class"].eq("v4.0_mev_or_hook")
            & created["block_number"].lt(activation_block)
        ]
        .copy()
        .reset_index(drop=True)
    )
    if pre_pool.empty:
        raise RuntimeError("No pre-v4.1 v4.0 controls found before activation.")

    if selection_mode == "nearest":
        pre = pre_pool.tail(tokens_per_side).copy()
        post = v41.head(tokens_per_side).copy()
        pre["cohort_match_id"] = [f"nearest_pre_{i}" for i in range(len(pre))]
        post["cohort_match_id"] = [f"nearest_post_{i}" for i in range(len(post))]
        pre["match_distance_blocks"] = ""
        post["match_distance_blocks"] = ""
    else:
        treated = v41.copy() if selection_mode == "full-window" or tokens_per_side <= 0 else v41.head(tokens_per_side).copy()
        pre, post = select_matched_controls_fast(treated=treated, pre_pool=pre_pool)

    pre["cohort_side"] = "pre_v4_0_control"
    post["cohort_side"] = "post_v4_1_treated"
    cohort = pd.concat([pre, post], ignore_index=True)
    if cohort.empty:
        raise RuntimeError("No bounded pre/post cohort could be selected.")
    selection_summary = {
        "selection_mode": selection_mode,
        "treated_available": int(len(v41)),
        "controls_available_before_activation": int(len(pre_pool)),
        "treated_selected": int(post["token_id"].nunique()) if "token_id" in post else 0,
        "controls_selected": int(pre["token_id"].nunique()) if "token_id" in pre else 0,
        "matched_pairs": int(post["cohort_match_id"].nunique()) if "cohort_match_id" in post else 0,
        "uses_all_treated_in_window": bool(selection_mode == "full-window" or tokens_per_side <= 0),
    }
    return cohort, activation, selection_summary


def eth_price_usd(timestamp: int) -> float:
    try:
        response = requests.get(DEFILLAMA_PRICE_URL.format(timestamp=timestamp), timeout=20)
        payload = response.json()
        return float(payload["coins"]["coingecko:ethereum"]["price"])
    except Exception:
        return float("nan")


def paired_amount_normalized(raw_amount: int, paired_token: str) -> float:
    decimals = TOKEN_DECIMALS.get(paired_token.lower(), 18)
    return abs(raw_amount) / (10**decimals)


def decode_swap(log: dict[str, Any]) -> dict[str, Any]:
    data = log["data"]
    return {
        "pool_id": log["topics"][1].lower(),
        "sender": topic_address(log["topics"][2]),
        "block_number": int(log["blockNumber"], 16),
        "timestamp_unix": int(log.get("blockTimestamp", "0x0"), 16),
        "timestamp_utc": iso_utc(int(log.get("blockTimestamp", "0x0"), 16)),
        "transaction_hash": log["transactionHash"],
        "amount0_raw": signed_word(word(data, 0)),
        "amount1_raw": signed_word(word(data, 1)),
        "swap_topic": log["topics"][0],
    }


def decode_transfer(log: dict[str, Any]) -> dict[str, Any]:
    return {
        "token_id": str(log["address"]).lower(),
        "from_address": topic_address(log["topics"][1]),
        "to_address": topic_address(log["topics"][2]),
        "block_number": int(log["blockNumber"], 16),
        "log_index": int(log["logIndex"], 16),
        "transaction_hash": log["transactionHash"],
        "amount_raw": int(log["data"], 16) if log.get("data") else 0,
    }


def fetch_swaps_for_pool(
    *,
    endpoint: str,
    pool_id: str,
    launch_block: int,
    end_block: int,
    chunk_size: int,
) -> pd.DataFrame:
    logs = fetch_logs(
        endpoint=endpoint,
        address=UNISWAP_V4_POOL_MANAGER_BASE,
        from_block=launch_block,
        to_block=end_block,
        topics=[SWAP_TOPIC, pool_id],
        chunk_size=chunk_size,
        label=f"pool_swaps:{pool_id[:10]}",
    )
    return pd.DataFrame([decode_swap(log) for log in logs])


def fetch_swaps_for_pools(
    *,
    endpoint: str,
    cohort: pd.DataFrame,
    max_horizon: int,
    blocks_per_day: int,
    pool_batch_size: int,
    swap_chunk_size: int,
) -> dict[str, pd.DataFrame]:
    by_pool: dict[str, pd.DataFrame] = {}
    if cohort.empty:
        return by_pool
    pool_specs = []
    for _, token in cohort.iterrows():
        pool_specs.append(
            {
                "pool_id": str(token["pool_id"]).lower(),
                "launch_block": int(token["block_number"]),
                "end_block": int(token["block_number"]) + max_horizon * blocks_per_day + 2_000,
            }
        )

    if pool_batch_size <= 1:
        for spec in pool_specs:
            by_pool[spec["pool_id"]] = fetch_swaps_for_pool(
                endpoint=endpoint,
                pool_id=spec["pool_id"],
                launch_block=spec["launch_block"],
                end_block=spec["end_block"],
                chunk_size=swap_chunk_size,
            )
        return by_pool

    try:
        for batch_start in range(0, len(pool_specs), pool_batch_size):
            batch = pool_specs[batch_start : batch_start + pool_batch_size]
            min_block = min(spec["launch_block"] for spec in batch)
            max_block = max(spec["end_block"] for spec in batch)
            pool_ids = [spec["pool_id"] for spec in batch]
            logs = fetch_logs(
                endpoint=endpoint,
                address=UNISWAP_V4_POOL_MANAGER_BASE,
                from_block=min_block,
                to_block=max_block,
                topics=[SWAP_TOPIC, pool_ids],
                chunk_size=swap_chunk_size,
                label=f"pool_swaps_batch:{batch_start // pool_batch_size}",
            )
            decoded = pd.DataFrame([decode_swap(log) for log in logs])
            for spec in batch:
                pool = spec["pool_id"]
                subset = decoded.loc[decoded["pool_id"].eq(pool)].copy() if not decoded.empty else pd.DataFrame()
                by_pool[pool] = subset.loc[
                    pd.to_numeric(subset.get("block_number", pd.Series(dtype=float)), errors="coerce").between(
                        spec["launch_block"], spec["end_block"]
                    )
                ].copy()
    except RuntimeError as exc:
        print(f"batch swap scan failed; falling back to one pool per scan: {exc}", flush=True)
        return fetch_swaps_for_pools(
            endpoint=endpoint,
            cohort=cohort,
            max_horizon=max_horizon,
            blocks_per_day=blocks_per_day,
            pool_batch_size=1,
            swap_chunk_size=swap_chunk_size,
        )
    return by_pool


def _rename_first_present(df: pd.DataFrame, canonical: str, aliases: list[str]) -> pd.DataFrame:
    if canonical in df.columns:
        return df
    for alias in aliases:
        if alias in df.columns:
            return df.rename(columns={alias: canonical})
    return df


def integer_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "0"
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "<na>"}:
        return "0"
    if text.endswith(".0") and text[:-2].lstrip("-").isdigit():
        text = text[:-2]
    if "e" in text.lower():
        return str(int(Decimal(text)))
    if text.lstrip("-").isdigit():
        return str(int(text))
    return text


def load_swap_indexer_import(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"Swap indexer import is missing or empty: {path}")
    swaps = pd.read_csv(path, low_memory=False, dtype=str)
    for canonical, aliases in {
        "pool_id": ["poolId", "pool", "pool_address"],
        "sender": ["trader", "caller", "tx_from", "origin"],
        "block_number": ["block", "blockNumber"],
        "timestamp_unix": ["block_timestamp_unix", "timestamp", "blockTimeUnix"],
        "timestamp_utc": ["block_timestamp_utc", "block_time", "blockTime"],
        "transaction_hash": ["tx_hash", "transactionHash", "hash"],
        "amount0_raw": ["amount0", "amount0Raw", "amount_0_raw"],
        "amount1_raw": ["amount1", "amount1Raw", "amount_1_raw"],
    }.items():
        swaps = _rename_first_present(swaps, canonical, aliases)
    if "timestamp_unix" not in swaps.columns and "timestamp_utc" in swaps.columns:
        swaps["timestamp_unix"] = (
            pd.to_datetime(swaps["timestamp_utc"], utc=True, errors="coerce").astype("int64") // 1_000_000_000
        )
    if "timestamp_utc" not in swaps.columns and "timestamp_unix" in swaps.columns:
        swaps["timestamp_utc"] = pd.to_numeric(swaps["timestamp_unix"], errors="coerce").map(iso_utc)
    required = {"pool_id", "sender", "block_number", "timestamp_unix", "timestamp_utc", "amount0_raw", "amount1_raw"}
    missing = required.difference(swaps.columns)
    if missing:
        raise RuntimeError(f"Swap indexer import {path} is missing required columns: {sorted(missing)}")
    swaps = swaps.copy()
    swaps["pool_id"] = swaps["pool_id"].astype(str).str.lower()
    swaps["sender"] = swaps["sender"].astype(str).str.lower()
    swaps["block_number"] = pd.to_numeric(swaps["block_number"], errors="coerce")
    swaps["timestamp_unix"] = pd.to_numeric(swaps["timestamp_unix"], errors="coerce")
    swaps["amount0_raw"] = swaps["amount0_raw"].map(integer_text)
    swaps["amount1_raw"] = swaps["amount1_raw"].map(integer_text)
    swaps = swaps.dropna(subset=["pool_id", "block_number", "timestamp_unix"]).reset_index(drop=True)
    swaps.attrs["import_provided"] = True
    swaps.attrs["import_path"] = str(path)
    return swaps


def load_transfer_indexer_import(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"Transfer indexer import is missing or empty: {path}")
    transfers = pd.read_csv(path, low_memory=False, dtype=str)
    for canonical, aliases in {
        "token_id": ["token", "contract_address", "address", "currency"],
        "from_address": ["from", "fromAddress", "sender"],
        "to_address": ["to", "toAddress", "recipient"],
        "block_number": ["block", "blockNumber"],
        "log_index": ["logIndex", "event_index"],
        "transaction_hash": ["tx_hash", "transactionHash", "hash"],
        "amount_raw": ["amount", "value", "amountRaw"],
    }.items():
        transfers = _rename_first_present(transfers, canonical, aliases)
    required = {"token_id", "from_address", "to_address", "block_number", "amount_raw"}
    missing = required.difference(transfers.columns)
    if missing:
        raise RuntimeError(f"Transfer indexer import {path} is missing required columns: {sorted(missing)}")
    transfers = transfers.copy()
    transfers["token_id"] = transfers["token_id"].astype(str).str.lower()
    transfers["from_address"] = transfers["from_address"].astype(str).str.lower()
    transfers["to_address"] = transfers["to_address"].astype(str).str.lower()
    transfers["block_number"] = pd.to_numeric(transfers["block_number"], errors="coerce")
    if "log_index" not in transfers.columns:
        transfers["log_index"] = 0
    transfers["log_index"] = pd.to_numeric(transfers["log_index"], errors="coerce").fillna(0)
    if "transaction_hash" not in transfers.columns:
        transfers["transaction_hash"] = ""
    transfers["amount_raw"] = transfers["amount_raw"].map(integer_text)
    transfers = transfers.dropna(subset=["token_id", "block_number"]).sort_values(["token_id", "block_number", "log_index"]).reset_index(drop=True)
    transfers.attrs["import_provided"] = True
    transfers.attrs["import_path"] = str(path)
    return transfers


def swaps_by_pool_from_indexer(
    *,
    cohort: pd.DataFrame,
    swaps: pd.DataFrame,
    max_horizon: int,
    blocks_per_day: int,
) -> dict[str, pd.DataFrame]:
    by_pool: dict[str, pd.DataFrame] = {}
    if cohort.empty or swaps.empty:
        return by_pool
    for _, token in cohort.iterrows():
        pool_id = str(token["pool_id"]).lower()
        launch_block = int(token["block_number"])
        end_block = launch_block + max_horizon * blocks_per_day + 2_000
        subset = swaps.loc[
            swaps["pool_id"].eq(pool_id)
            & pd.to_numeric(swaps["block_number"], errors="coerce").between(launch_block, end_block)
        ].copy()
        by_pool[pool_id] = subset
    return by_pool


def fetch_transfers_for_token(
    *,
    endpoint: str,
    token_id: str,
    launch_block: int,
    end_block: int,
    chunk_size: int,
) -> pd.DataFrame:
    logs = fetch_logs(
        endpoint=endpoint,
        address=token_id,
        from_block=launch_block,
        to_block=end_block,
        topics=[TRANSFER_TOPIC],
        chunk_size=chunk_size,
        label=f"erc20_transfers:{token_id[:10]}",
    )
    if not logs:
        return pd.DataFrame(
            columns=["token_id", "from_address", "to_address", "block_number", "log_index", "transaction_hash", "amount_raw"]
        )
    return pd.DataFrame([decode_transfer(log) for log in logs]).sort_values(["block_number", "log_index"])


def fetch_transfers_for_tokens(
    *,
    endpoint: str,
    cohort: pd.DataFrame,
    max_horizon: int,
    blocks_per_day: int,
    token_batch_size: int,
    chunk_size: int,
) -> dict[str, pd.DataFrame]:
    by_token: dict[str, pd.DataFrame] = {}
    if cohort.empty:
        return by_token
    specs = []
    for _, token in cohort.iterrows():
        specs.append(
            {
                "token_id": str(token["token_id"]).lower(),
                "launch_block": int(token["block_number"]),
                "end_block": int(token["block_number"]) + max_horizon * blocks_per_day + 2_000,
            }
        )
    if token_batch_size <= 1:
        for spec in specs:
            by_token[spec["token_id"]] = fetch_transfers_for_token(
                endpoint=endpoint,
                token_id=spec["token_id"],
                launch_block=spec["launch_block"],
                end_block=spec["end_block"],
                chunk_size=chunk_size,
            )
        return by_token

    try:
        for batch_start in range(0, len(specs), token_batch_size):
            batch = specs[batch_start : batch_start + token_batch_size]
            min_block = min(spec["launch_block"] for spec in batch)
            max_block = max(spec["end_block"] for spec in batch)
            token_ids = [spec["token_id"] for spec in batch]
            logs = fetch_logs(
                endpoint=endpoint,
                address=token_ids,
                from_block=min_block,
                to_block=max_block,
                topics=[TRANSFER_TOPIC],
                chunk_size=chunk_size,
                label=f"erc20_transfers_batch:{batch_start // token_batch_size}",
            )
            decoded = pd.DataFrame([decode_transfer(log) for log in logs])
            for spec in batch:
                token_id = spec["token_id"]
                subset = decoded.loc[decoded["token_id"].eq(token_id)].copy() if not decoded.empty else pd.DataFrame()
                by_token[token_id] = subset.loc[
                    pd.to_numeric(subset.get("block_number", pd.Series(dtype=float)), errors="coerce").between(
                        spec["launch_block"], spec["end_block"]
                    )
                ].sort_values(["block_number", "log_index"]).copy()
    except RuntimeError as exc:
        print(f"batch transfer scan failed; falling back to one token per scan: {exc}", flush=True)
        return fetch_transfers_for_tokens(
            endpoint=endpoint,
            cohort=cohort,
            max_horizon=max_horizon,
            blocks_per_day=blocks_per_day,
            token_batch_size=1,
            chunk_size=chunk_size,
        )
    return by_token


def transfers_by_token_from_indexer(
    *,
    cohort: pd.DataFrame,
    transfers: pd.DataFrame,
    max_horizon: int,
    blocks_per_day: int,
) -> dict[str, pd.DataFrame]:
    by_token: dict[str, pd.DataFrame] = {}
    if cohort.empty or transfers.empty:
        return by_token
    for _, token in cohort.iterrows():
        token_id = str(token["token_id"]).lower()
        launch_block = int(token["block_number"])
        end_block = launch_block + max_horizon * blocks_per_day + 2_000
        subset = transfers.loc[
            transfers["token_id"].eq(token_id)
            & pd.to_numeric(transfers["block_number"], errors="coerce").between(launch_block, end_block)
        ].copy()
        by_token[token_id] = subset.sort_values(["block_number", "log_index"])
    return by_token


def write_raw_log_table(path: Path | None, frames: dict[str, pd.DataFrame], *, source_layer: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    nonempty = [frame.copy() for frame in frames.values() if frame is not None and not frame.empty]
    if not nonempty:
        pd.DataFrame().to_csv(path, index=False)
        return
    raw = pd.concat(nonempty, ignore_index=True)
    if "transaction_hash" in raw.columns and "log_index" in raw.columns:
        raw = raw.drop_duplicates(["transaction_hash", "log_index"])
    raw["source_layer"] = source_layer
    raw.to_csv(path, index=False)


def artifact_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def compute_holder_concentration(
    *,
    endpoint: str,
    cohort: pd.DataFrame,
    horizons: list[int],
    blocks_per_day: int,
    transfer_chunk_size: int,
    transfer_token_batch_size: int,
    transfer_indexer: pd.DataFrame,
    raw_transfers_out: Path | None,
) -> dict[tuple[str, int], dict[str, Any]]:
    holder_rows: dict[tuple[str, int], dict[str, Any]] = {}
    max_horizon = max(horizons)
    if transfer_indexer.attrs.get("import_provided"):
        transfers_by_token = transfers_by_token_from_indexer(
            cohort=cohort,
            transfers=transfer_indexer,
            max_horizon=max_horizon,
            blocks_per_day=blocks_per_day,
        )
        transfer_source = "Base archive/indexer ERC20 Transfer import"
    else:
        transfers_by_token = fetch_transfers_for_tokens(
            endpoint=endpoint,
            cohort=cohort,
            max_horizon=max_horizon,
            blocks_per_day=blocks_per_day,
            token_batch_size=transfer_token_batch_size,
            chunk_size=transfer_chunk_size,
        )
        transfer_source = "Base public JSON-RPC; ERC20 Transfer event"
    write_raw_log_table(raw_transfers_out, transfers_by_token, source_layer=transfer_source)

    for _, token in cohort.iterrows():
        token_id = str(token["token_id"]).lower()
        launch_block = int(token["block_number"])
        transfers = transfers_by_token.get(token_id, pd.DataFrame())
        print(f"decoded transfers token={token_id} rows={len(transfers)}", flush=True)
        balances: defaultdict[str, int] = defaultdict(int)
        pointer = 0
        transfers_records = transfers.to_dict(orient="records") if not transfers.empty else []
        for horizon in sorted(horizons):
            cutoff_block = launch_block + horizon * blocks_per_day + 2_000
            while pointer < len(transfers_records) and int(transfers_records[pointer]["block_number"]) <= cutoff_block:
                transfer = transfers_records[pointer]
                from_address = str(transfer["from_address"]).lower()
                to_address = str(transfer["to_address"]).lower()
                amount = int(transfer["amount_raw"])
                if from_address != ZERO_ADDRESS:
                    balances[from_address] -= amount
                if to_address != ZERO_ADDRESS:
                    balances[to_address] += amount
                pointer += 1
            positive = [amount for address, amount in balances.items() if address != ZERO_ADDRESS and amount > 0]
            total_supply_observed = sum(positive)
            top10 = sum(sorted(positive, reverse=True)[:10])
            holder_rows[(token_id, horizon)] = {
                "holder_count": len(positive),
                "holder_concentration_top10": top10 / total_supply_observed if total_supply_observed else float("nan"),
                "transfer_log_count": len(transfers_records),
                "holder_concentration_status": (
                    "computed_from_erc20_transfer_logs" if transfers_records else "no_transfer_logs_in_rpc_window"
                ),
            }
    return holder_rows


def compute_token_horizons(
    *,
    endpoint: str,
    cohort: pd.DataFrame,
    horizons: list[int],
    blocks_per_day: int,
    swap_pool_batch_size: int,
    swap_chunk_size: int,
    swap_indexer: pd.DataFrame,
    raw_swaps_out: Path | None,
    include_holder_concentration: bool,
    transfer_chunk_size: int,
    transfer_token_batch_size: int,
    transfer_indexer: pd.DataFrame,
    raw_transfers_out: Path | None,
) -> pd.DataFrame:
    max_horizon = max(horizons)
    rows: list[dict[str, Any]] = []
    price_cache: dict[int, float] = {}
    if swap_indexer.attrs.get("import_provided"):
        swaps_by_pool = swaps_by_pool_from_indexer(
            cohort=cohort,
            swaps=swap_indexer,
            max_horizon=max_horizon,
            blocks_per_day=blocks_per_day,
        )
        swap_source = "Base archive/indexer Uniswap v4 PoolManager Swap import"
    else:
        swaps_by_pool = fetch_swaps_for_pools(
            endpoint=endpoint,
            cohort=cohort,
            max_horizon=max_horizon,
            blocks_per_day=blocks_per_day,
            pool_batch_size=swap_pool_batch_size,
            swap_chunk_size=swap_chunk_size,
        )
        swap_source = "Base public JSON-RPC; Uniswap v4 PoolManager Swap event"
    write_raw_log_table(raw_swaps_out, swaps_by_pool, source_layer=swap_source)
    holder_by_token_horizon: dict[tuple[str, int], dict[str, Any]] = {}
    if include_holder_concentration:
        holder_by_token_horizon = compute_holder_concentration(
            endpoint=endpoint,
            cohort=cohort,
            horizons=horizons,
            blocks_per_day=blocks_per_day,
            transfer_chunk_size=transfer_chunk_size,
            transfer_token_batch_size=transfer_token_batch_size,
            transfer_indexer=transfer_indexer,
            raw_transfers_out=raw_transfers_out,
        )

    for _, token in cohort.iterrows():
        launch_ts = int(token["block_timestamp_unix"])
        swaps = swaps_by_pool.get(str(token["pool_id"]).lower(), pd.DataFrame())
        print(
            f"decoded swaps token={token['token_id']} side={token['cohort_side']} rows={len(swaps)}",
            flush=True,
        )
        paired_token = str(token["paired_token"]).lower()
        token_is_currency0 = int(str(token["token_id"]), 16) < int(paired_token, 16)
        launch_date_key = int(datetime.fromtimestamp(launch_ts, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        if launch_date_key not in price_cache:
            price_cache[launch_date_key] = eth_price_usd(launch_date_key)
        eth_price = price_cache[launch_date_key]

        for horizon in horizons:
            cutoff = launch_ts + horizon * 86_400
            horizon_swaps = swaps.loc[pd.to_numeric(swaps.get("timestamp_unix", pd.Series(dtype=float)), errors="coerce").le(cutoff)].copy()
            buy_count = 0
            sell_count = 0
            paired_volume = 0.0
            early_sender_volume: defaultdict[str, float] = defaultdict(float)

            for _, swap in horizon_swaps.iterrows():
                amount0 = int(swap["amount0_raw"])
                amount1 = int(swap["amount1_raw"])
                token_delta = amount0 if token_is_currency0 else amount1
                paired_delta = amount1 if token_is_currency0 else amount0
                if token_delta < 0:
                    buy_count += 1
                elif token_delta > 0:
                    sell_count += 1
                normalized = paired_amount_normalized(paired_delta, paired_token)
                paired_volume += normalized
                if int(swap["timestamp_unix"]) <= launch_ts + 60:
                    early_sender_volume[str(swap["sender"]).lower()] += normalized

            if paired_token == BASE_USDC:
                volume_usd = paired_volume
            elif paired_token == BASE_WETH and pd.notna(eth_price):
                volume_usd = paired_volume * eth_price
            else:
                volume_usd = float("nan")

            total_early = sum(early_sender_volume.values())
            top10_early = sum(sorted(early_sender_volume.values(), reverse=True)[:10])
            early_top10_share = top10_early / total_early if total_early else float("nan")
            holder = holder_by_token_horizon.get((str(token["token_id"]).lower(), horizon), {})
            holder_status = holder.get(
                "holder_concentration_status",
                "not_requested" if not include_holder_concentration else "missing_holder_reconstruction",
            )
            row_status = (
                "computed_onchain_token_horizon_with_holder_reconstruction"
                if holder_status == "computed_from_erc20_transfer_logs"
                else "computed_onchain_token_horizon_holder_missing_or_not_requested"
            )

            rows.append(
                {
                    "event_id": CLANKER_EVENT_ID,
                    "token_id": token["token_id"],
                    "unit_id": f"{token['token_id']}:{horizon}d:base_v4_poolmanager",
                    "cohort_side": token["cohort_side"],
                    "clanker_version_class": token["clanker_version_class"],
                    "pool_id": token["pool_id"],
                    "cohort_match_id": token.get("cohort_match_id", ""),
                    "match_distance_blocks": token.get("match_distance_blocks", ""),
                    "paired_token": paired_token,
                    "launch_block": token["block_number"],
                    "launch_timestamp_utc": token["block_timestamp_utc"],
                    "horizon_days": horizon,
                    "swap_count": len(horizon_swaps),
                    "active_traders": horizon_swaps["sender"].nunique() if not horizon_swaps.empty else 0,
                    "buy_count": buy_count,
                    "sell_count": sell_count,
                    "paired_volume": paired_volume,
                    "volume_usd": volume_usd,
                    "first_trade_at": horizon_swaps["timestamp_utc"].min() if not horizon_swaps.empty else "",
                    "last_trade_at": horizon_swaps["timestamp_utc"].max() if not horizon_swaps.empty else "",
                    "early_sender_top10_share_60s": early_top10_share,
                    "holder_concentration_top10": holder.get("holder_concentration_top10", float("nan")),
                    "holder_count": holder.get("holder_count", ""),
                    "transfer_log_count": holder.get("transfer_log_count", ""),
                    "holder_concentration_status": holder_status,
                    "claim_boundary": (
                        "Base bounded Uniswap v4 PoolManager swap sample; sender is a router/swap-caller proxy, "
                        "volume_usd uses launch-day ETH price for WETH pairs, early concentration is sender-based, "
                        "and holder concentration is reconstructed from ERC20 Transfer logs when requested."
                    ),
                    "source_layer": swap_source,
                    "status": row_status,
                }
            )
    return pd.DataFrame(rows)


def merge_existing_holder_concentration(horizons: pd.DataFrame, existing_path: Path) -> pd.DataFrame:
    if horizons.empty or not existing_path.exists() or existing_path.stat().st_size == 0:
        return horizons
    existing = pd.read_csv(existing_path)
    holder_columns = [
        "token_id",
        "horizon_days",
        "holder_concentration_top10",
        "holder_count",
        "transfer_log_count",
        "holder_concentration_status",
    ]
    if not set(holder_columns).issubset(existing.columns):
        return horizons
    existing_holder = existing[holder_columns].copy()
    merged = horizons.merge(
        existing_holder,
        on=["token_id", "horizon_days"],
        how="left",
        suffixes=("", "_existing"),
    )
    for column in ["holder_concentration_top10", "holder_count", "transfer_log_count", "holder_concentration_status"]:
        existing_column = f"{column}_existing"
        if existing_column not in merged:
            continue
        missing = merged[column].isna() | merged[column].astype(str).isin(["", "not_requested"])
        merged.loc[missing, column] = merged.loc[missing, existing_column]
        merged = merged.drop(columns=[existing_column])
    has_holder = merged["holder_concentration_status"].astype(str).eq("computed_from_erc20_transfer_logs")
    merged.loc[has_holder, "status"] = "computed_onchain_token_horizon_with_holder_reconstruction"
    return merged


def write_outputs(
    *,
    created: pd.DataFrame,
    cohort: pd.DataFrame,
    horizons: pd.DataFrame,
    activation: dict[str, Any],
    selection_summary: dict[str, Any],
    search_start_block: int,
    search_end_block: int,
    output_dir: Path,
    raw_swaps_path: Path | None,
    raw_transfers_path: Path | None,
    summary_path: Path | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)

    created_path = output_dir / "clanker_base_token_created.csv"
    cohort_path = output_dir / "clanker_base_event_cohort.csv"
    horizons_path = output_dir / "clanker_base_token_horizons.csv"
    summary_path = summary_path or TABLES / "clanker_base_event_validation_summary.json"

    created.to_csv(created_path, index=False)
    cohort.to_csv(cohort_path, index=False)
    horizons.to_csv(horizons_path, index=False)

    counts = Counter(created["clanker_version_class"])
    horizon_summary = (
        horizons.groupby(["cohort_side", "horizon_days"], dropna=False)
        .agg(
            tokens=("token_id", "nunique"),
            median_swaps=("swap_count", "median"),
            median_active_traders=("active_traders", "median"),
            median_volume_usd=("volume_usd", "median"),
            median_early_sender_top10_share_60s=("early_sender_top10_share_60s", "median"),
            median_holder_concentration_top10=("holder_concentration_top10", "median")
            if "holder_concentration_top10" in horizons
            else ("swap_count", "median"),
            median_holder_count=("holder_count", "median") if "holder_count" in horizons else ("swap_count", "median"),
        )
        .reset_index()
        .to_dict(orient="records")
        if not horizons.empty
        else []
    )
    holder_rows = (
        horizons.loc[horizons.get("holder_concentration_status", pd.Series(dtype=str)).astype(str).eq("computed_from_erc20_transfer_logs")]
        if not horizons.empty and "holder_concentration_status" in horizons
        else pd.DataFrame()
    )
    holder_reconstruction_tokens = int(holder_rows["token_id"].nunique()) if not holder_rows.empty else 0
    holder_reconstruction_rows = int(len(holder_rows))
    cohort_tokens = int(cohort["token_id"].nunique())
    horizon_rows = int(len(horizons))
    selection_mode = selection_summary.get("selection_mode", "nearest")
    if selection_mode == "nearest":
        status = "accepted_bounded_onchain_sample"
        comparison_unit_status = "nearest bounded pre/post token sample"
        boundary_tail = "comparison tokens are local nearest v4.0 launches."
    elif selection_summary.get("uses_all_treated_in_window"):
        status = "accepted_full_window_matched_onchain_sample"
        comparison_unit_status = "all observed v4.1 launches in the search window matched to nearest v4.0 controls"
        boundary_tail = "full-window coverage is limited to the searched block range and available raw/imported logs."
    else:
        status = "accepted_matched_onchain_sample"
        comparison_unit_status = "matched v4.1 launches and nearest v4.0 controls"
        boundary_tail = "matched sample still depends on v4.1 adoption in the search window."
    summary = {
        "event_id": CLANKER_EVENT_ID,
        "status": status,
        "platform": "Clanker",
        "chain": "Base",
        "rule_family": "trader_protection",
        "rule_change": "First observed Clanker v4.1 MEV/sniper-protection module token launch on Base.",
        "activation_timestamp_utc": activation["block_timestamp_utc"],
        "activation_block": int(activation["block_number"]),
        "activation_transaction_hash": activation["transaction_hash"],
        "activation_token_id": activation["token_id"],
        "activation_pool_id": activation["pool_id"],
        "activation_pool_hook": activation["pool_hook"],
        "activation_mev_module": activation["mev_module"],
        "activation_evidence_type": "first_onchain_token_created_with_v41_mev_module",
        "search_start_block": search_start_block,
        "search_end_block": search_end_block,
        "token_created_rows": int(len(created)),
        "version_class_counts": dict(counts),
        "selection": selection_summary,
        "comparison_unit_status": comparison_unit_status,
        "cohort_tokens": cohort_tokens,
        "horizon_rows": horizon_rows,
        "holder_reconstruction_tokens": holder_reconstruction_tokens,
        "holder_reconstruction_rows": holder_reconstruction_rows,
        "holder_reconstruction_token_share": holder_reconstruction_tokens / cohort_tokens if cohort_tokens else float("nan"),
        "holder_reconstruction_row_share": holder_reconstruction_rows / horizon_rows if horizon_rows else float("nan"),
        "horizon_summary": horizon_summary,
        "claim_boundary": (
            "Accepted as an on-chain verified Base rule/adoption event with token-horizon outcomes and "
            "holder-level concentration reconstruction where logs are available. It is not yet a platform-wide "
            f"causal replication because {boundary_tail}"
        ),
        "source_urls": [
            "https://github.com/clanker-devco/DOCS",
            "https://github.com/clanker-devco/v4-contracts",
            "https://developers.uniswap.org/docs/protocols/v4/deployments",
        ],
        "outputs": {
            "token_created": str(created_path.relative_to(ROOT)),
            "cohort": str(cohort_path.relative_to(ROOT)),
            "token_horizons": str(horizons_path.relative_to(ROOT)),
        },
    }
    if raw_swaps_path is not None and raw_swaps_path.exists():
        summary["outputs"]["raw_swaps"] = artifact_path(raw_swaps_path)
        summary["raw_swap_rows"] = max(sum(1 for _ in raw_swaps_path.open(encoding="utf-8")) - 1, 0)
    if raw_transfers_path is not None and raw_transfers_path.exists():
        summary["outputs"]["raw_transfers"] = artifact_path(raw_transfers_path)
        summary["raw_transfer_rows"] = max(sum(1 for _ in raw_transfers_path.open(encoding="utf-8")) - 1, 0)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc-url", default=BASE_RPC)
    parser.add_argument("--start-date", default="2025-08-18", help="UTC date for launch-log search start.")
    parser.add_argument("--end-date", default="2025-08-27", help="UTC date for launch-log search end.")
    parser.add_argument("--start-block", type=int, default=None, help="Override search start block.")
    parser.add_argument("--end-block", type=int, default=None, help="Override search end block.")
    parser.add_argument("--tokens-per-side", type=int, default=2)
    parser.add_argument(
        "--selection-mode",
        choices=["nearest", "matched", "full-window"],
        default="matched",
        help="nearest reproduces the old bounded sample; matched pairs v4.1 launches to nearest v4.0 controls; full-window uses all v4.1 rows in the search window.",
    )
    parser.add_argument("--horizons", default="1,7,30")
    parser.add_argument(
        "--blocks-per-day",
        type=int,
        default=43_500,
        help="Conservative Base block upper bound per UTC day; logs are still timestamp-filtered.",
    )
    parser.add_argument("--swap-pool-batch-size", type=int, default=1)
    parser.add_argument("--swap-chunk-size", type=int, default=25_000)
    parser.add_argument("--token-created-chunk-size", type=int, default=25_000)
    parser.add_argument("--transfer-chunk-size", type=int, default=25_000)
    parser.add_argument("--transfer-token-batch-size", type=int, default=12)
    parser.add_argument(
        "--skip-holder-concentration",
        action="store_true",
        help="Skip ERC20 Transfer-log holder reconstruction.",
    )
    parser.add_argument(
        "--no-preserve-existing-holder-concentration",
        action="store_true",
        help="When skipping holder reconstruction, do not carry forward holder fields from an existing horizon file.",
    )
    parser.add_argument("--skip-swaps", action="store_true", help="Only build activation/cohort rows.")
    parser.add_argument(
        "--reuse-token-created",
        action="store_true",
        help="Read artifacts/external_validation/clanker_base_token_created.csv and filter it to the requested block window.",
    )
    parser.add_argument(
        "--append-token-created",
        action="store_true",
        help="Append missing requested block ranges to artifacts/external_validation/clanker_base_token_created.csv.",
    )
    parser.add_argument(
        "--token-created-only",
        action="store_true",
        help="Only update the TokenCreated scan and write a scan summary; do not overwrite cohort or horizon outputs.",
    )
    parser.add_argument(
        "--token-created-import",
        default="",
        help="Optional CSV export from an archive/indexer with the same TokenCreated schema to merge before cohort selection.",
    )
    parser.add_argument(
        "--swap-import",
        default="",
        help="Optional CSV export from an archive/indexer containing Base Uniswap v4 Swap rows.",
    )
    parser.add_argument(
        "--transfer-import",
        default="",
        help="Optional CSV export from an archive/indexer containing ERC20 Transfer rows for selected Base tokens.",
    )
    parser.add_argument(
        "--raw-swaps-out",
        default=str(EXTERNAL / "clanker_base_pool_swaps_raw.csv"),
        help="Where to write collected or imported raw Base swap rows.",
    )
    parser.add_argument(
        "--raw-transfers-out",
        default=str(EXTERNAL / "clanker_base_token_transfers_raw.csv"),
        help="Where to write collected or imported raw Base ERC20 Transfer rows.",
    )
    parser.add_argument(
        "--no-write-raw-logs",
        action="store_true",
        help="Do not persist raw swap/transfer collection CSVs.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(EXTERNAL),
        help="Directory for token_created, cohort, horizon, and summary outputs.",
    )
    parser.add_argument(
        "--summary-out",
        default="",
        help="Optional summary JSON path. Defaults to artifacts/tables/clanker_base_event_validation_summary.json.",
    )
    args = parser.parse_args()

    if args.start_block is not None and args.end_block is not None:
        start_block = args.start_block
        end_block = args.end_block
    else:
        start_ts = int(datetime.fromisoformat(args.start_date).replace(tzinfo=timezone.utc).timestamp())
        end_ts = int(datetime.fromisoformat(args.end_date).replace(tzinfo=timezone.utc).timestamp())
        start_block = block_for_timestamp(start_ts, endpoint=args.rpc_url)
        end_block = block_for_timestamp(end_ts, endpoint=args.rpc_url)
    created_path = EXTERNAL / "clanker_base_token_created.csv"
    import_path = Path(args.token_created_import).expanduser().resolve() if args.token_created_import else None
    swap_import_path = Path(args.swap_import).expanduser().resolve() if args.swap_import else None
    transfer_import_path = Path(args.transfer_import).expanduser().resolve() if args.transfer_import else None
    raw_swaps_path = None if args.no_write_raw_logs else Path(args.raw_swaps_out).expanduser().resolve()
    raw_transfers_path = None if args.no_write_raw_logs else Path(args.raw_transfers_out).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    summary_out = Path(args.summary_out).expanduser().resolve() if args.summary_out else None
    created = load_or_fetch_token_created(
        endpoint=args.rpc_url,
        start_block=start_block,
        end_block=end_block,
        created_path=created_path,
        reuse_existing=args.reuse_token_created,
        append_existing=args.append_token_created,
        import_path=import_path,
        chunk_size=args.token_created_chunk_size,
    )
    if args.token_created_only:
        write_token_created_scan_summary(
            created=created,
            search_start_block=start_block,
            search_end_block=end_block,
            output_dir=EXTERNAL,
        )
        counts = Counter(created["clanker_version_class"])
        print(
            "Clanker/Base TokenCreated scan written: "
            f"created={len(created)} v41={counts.get('v4.1_mev_or_hook', 0)} range={start_block}-{end_block}"
        )
        return
    cohort, activation, selection_summary = select_cohort(
        created,
        args.tokens_per_side,
        selection_mode=args.selection_mode,
    )
    horizons = [int(part.strip()) for part in args.horizons.split(",") if part.strip()]
    token_horizons = pd.DataFrame()
    if not args.skip_swaps:
        swap_indexer = load_swap_indexer_import(swap_import_path)
        transfer_indexer = load_transfer_indexer_import(transfer_import_path)
        token_horizons = compute_token_horizons(
            endpoint=args.rpc_url,
            cohort=cohort,
            horizons=horizons,
            blocks_per_day=args.blocks_per_day,
            swap_pool_batch_size=args.swap_pool_batch_size,
            swap_chunk_size=args.swap_chunk_size,
            swap_indexer=swap_indexer,
            raw_swaps_out=raw_swaps_path,
            include_holder_concentration=not args.skip_holder_concentration,
            transfer_chunk_size=args.transfer_chunk_size,
            transfer_token_batch_size=args.transfer_token_batch_size,
            transfer_indexer=transfer_indexer,
            raw_transfers_out=raw_transfers_path,
        )
        if args.skip_holder_concentration and not args.no_preserve_existing_holder_concentration:
            token_horizons = merge_existing_holder_concentration(token_horizons, EXTERNAL / "clanker_base_token_horizons.csv")
    write_outputs(
        created=created,
        cohort=cohort,
        horizons=token_horizons,
        activation=activation,
        selection_summary=selection_summary,
        search_start_block=start_block,
        search_end_block=end_block,
        output_dir=output_dir,
        raw_swaps_path=raw_swaps_path,
        raw_transfers_path=raw_transfers_path,
        summary_path=summary_out,
    )
    print(
        "Clanker/Base validation written: "
        f"created={len(created)} cohort_tokens={cohort['token_id'].nunique()} horizon_rows={len(token_horizons)}"
    )
    print(
        f"accepted activation {activation['block_timestamp_utc']} block={activation['block_number']} "
        f"tx={activation['transaction_hash']}"
    )


if __name__ == "__main__":
    main()
