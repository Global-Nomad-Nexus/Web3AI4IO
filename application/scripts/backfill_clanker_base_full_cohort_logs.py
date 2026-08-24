#!/usr/bin/env python3
"""Backfill Clanker/Base full-cohort swap and transfer imports.

The preferred use is with an archive RPC endpoint. Public RPC endpoints can be
used for smoke tests or slow resumable collection, but the script keeps a
coverage ledger so partial collection cannot be mistaken for full-cohort
evidence.
"""

from __future__ import annotations

import argparse
import json
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from run_clanker_base_validation import (
    EXTERNAL,
    SWAP_TOPIC,
    TABLES,
    TRANSFER_TOPIC,
    UNISWAP_V4_POOL_MANAGER_BASE,
    decode_swap,
    decode_transfer,
    fetch_logs,
    iso_utc,
    rpc,
)


DEFAULT_BACKFILL_RPC = "https://mainnet.base.org"
DEFAULT_BLOCKSCOUT_API = "https://base.blockscout.com/api"

SWAP_IMPORT_COLUMNS = [
    "pool_id",
    "sender",
    "block_number",
    "timestamp_unix",
    "timestamp_utc",
    "transaction_hash",
    "log_index",
    "amount0_raw",
    "amount1_raw",
    "source_layer",
]

TRANSFER_IMPORT_COLUMNS = [
    "token_id",
    "from_address",
    "to_address",
    "block_number",
    "log_index",
    "transaction_hash",
    "amount_raw",
    "source_layer",
]

COVERAGE_COLUMNS = [
    "coverage_type",
    "unit_id",
    "token_id",
    "pool_id",
    "cohort_side",
    "from_block",
    "to_block",
    "observed_rows",
    "coverage_status",
    "collected_at_utc",
    "source_layer",
]


def read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def write_csv(path: Path, df: pd.DataFrame, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is not None:
        for column in columns:
            if column not in df.columns:
                df[column] = ""
        df = df[columns]
    df = df.where(pd.notna(df), "")
    df.to_csv(path, index=False)


def append_csv(path: Path, df: pd.DataFrame, columns: list[str]) -> None:
    if df.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    for column in columns:
        if column not in df.columns:
            df[column] = ""
    df = df[columns].where(pd.notna(df), "")
    if path.exists() and path.stat().st_size:
        existing_columns = list(pd.read_csv(path, nrows=0).columns)
        if existing_columns != columns:
            existing = pd.read_csv(path, low_memory=False)
            for column in columns:
                if column not in existing.columns:
                    existing[column] = ""
            combined = pd.concat([existing.reindex(columns=columns), df], ignore_index=True)
            write_csv(path, combined, columns)
            return
    df.to_csv(path, mode="a", header=not path.exists() or path.stat().st_size == 0, index=False)


def dedupe_csv(path: Path, keys: list[str], columns: list[str]) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return
    df = pd.read_csv(path, low_memory=False)
    if set(keys).issubset(df.columns):
        df = df.drop_duplicates(keys).copy()
    write_csv(path, df, columns)


def dedupe_coverage_csv(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return
    coverage = pd.read_csv(path, low_memory=False)
    keys = ["coverage_type", "unit_id"]
    if not set(keys).issubset(coverage.columns):
        write_csv(path, coverage, COVERAGE_COLUMNS)
        return
    rank = {
        "collection_error": 0,
        "processed_zero_rows": 1,
        "processed_with_rows": 2,
    }
    coverage = coverage.copy()
    coverage["_coverage_rank"] = coverage["coverage_status"].astype(str).map(rank).fillna(0)
    coverage["_observed_rows_num"] = pd.to_numeric(coverage["observed_rows"], errors="coerce").fillna(0)
    coverage = (
        coverage.sort_values(keys + ["_coverage_rank", "_observed_rows_num", "collected_at_utc"])
        .drop_duplicates(keys, keep="last")
        .drop(columns=["_coverage_rank", "_observed_rows_num"])
    )
    write_csv(path, coverage, COVERAGE_COLUMNS)


def load_manifest(
    path: Path,
    *,
    cohort_side: str,
    max_horizon_days: int,
    blocks_per_day: int,
) -> pd.DataFrame:
    manifest = pd.read_csv(path, low_memory=False)
    required = {
        "token_id",
        "cohort_side",
        "launch_block",
        "max_horizon_end_block",
        "pool_id",
        "swap_query_key",
        "transfer_query_key",
    }
    missing = required.difference(manifest.columns)
    if missing:
        raise RuntimeError(f"Manifest is missing required columns: {sorted(missing)}")
    manifest = manifest.copy()
    manifest["token_id"] = manifest["token_id"].astype(str).str.lower()
    manifest["pool_id"] = manifest["pool_id"].astype(str).str.lower()
    manifest["launch_block"] = pd.to_numeric(manifest["launch_block"], errors="coerce")
    manifest["max_horizon_end_block"] = pd.to_numeric(manifest["max_horizon_end_block"], errors="coerce")
    manifest = manifest.dropna(subset=["launch_block", "max_horizon_end_block"])
    if cohort_side != "all":
        manifest = manifest.loc[manifest["cohort_side"].astype(str).eq(cohort_side)].copy()
    if max_horizon_days > 0:
        capped_end = manifest["launch_block"] + max_horizon_days * blocks_per_day + 2_000
        manifest["max_horizon_end_block"] = manifest["max_horizon_end_block"].clip(upper=capped_end)
    return manifest.sort_values(["launch_block", "token_id"]).reset_index(drop=True)


def processed_units(coverage_path: Path, coverage_type: str) -> set[str]:
    coverage = read_csv(coverage_path, low_memory=False)
    if coverage.empty or "coverage_type" not in coverage or "unit_id" not in coverage:
        return set()
    status = (
        coverage["coverage_status"].astype(str).str.startswith("processed_")
        if "coverage_status" in coverage
        else pd.Series(True, index=coverage.index)
    )
    return set(
        coverage.loc[coverage["coverage_type"].astype(str).eq(coverage_type) & status, "unit_id"]
        .dropna()
        .astype(str)
        .unique()
    )


def select_work(
    manifest: pd.DataFrame,
    *,
    coverage_path: Path,
    coverage_type: str,
    query_key: str,
    resume: bool,
    start_index: int,
    max_units: int,
    sample_strategy: str,
) -> pd.DataFrame:
    work = manifest.copy()
    if resume:
        done = processed_units(coverage_path, coverage_type)
        work = work.loc[~work[query_key].astype(str).isin(done)].copy()
    if start_index:
        work = work.iloc[start_index:].copy()
    if max_units > 0:
        if sample_strategy == "evenly_spaced" and len(work) > max_units:
            if max_units == 1:
                positions = [0]
            else:
                positions = sorted(
                    {
                        round(i * (len(work) - 1) / (max_units - 1))
                        for i in range(max_units)
                    }
                )
            work = work.iloc[positions].copy()
        else:
            work = work.head(max_units).copy()
    return work.reset_index(drop=True)


def batch_frames(df: pd.DataFrame, size: int) -> list[pd.DataFrame]:
    if df.empty:
        return []
    return [df.iloc[start : start + size].copy() for start in range(0, len(df), size)]


def block_timestamps(endpoint: str, blocks: list[int]) -> dict[int, int]:
    out: dict[int, int] = {}
    for block_number in sorted(set(int(block) for block in blocks)):
        block = rpc("eth_getBlockByNumber", [hex(block_number), False], endpoint=endpoint)
        out[block_number] = int(block["timestamp"], 16)
    return out


def ensure_swap_timestamps(swaps: pd.DataFrame, endpoint: str) -> pd.DataFrame:
    if swaps.empty:
        return swaps
    swaps = swaps.copy()
    swaps["timestamp_unix"] = pd.to_numeric(swaps["timestamp_unix"], errors="coerce").fillna(0).astype(int)
    missing = swaps["timestamp_unix"].le(0)
    if missing.any():
        mapping = block_timestamps(endpoint, swaps.loc[missing, "block_number"].astype(int).tolist())
        swaps.loc[missing, "timestamp_unix"] = swaps.loc[missing, "block_number"].astype(int).map(mapping)
        swaps.loc[missing, "timestamp_utc"] = swaps.loc[missing, "timestamp_unix"].map(iso_utc)
    return swaps


def filter_by_bounds(
    df: pd.DataFrame,
    batch: pd.DataFrame,
    *,
    key_column: str,
    manifest_key_column: str,
) -> pd.DataFrame:
    if df.empty:
        return df
    bounds = {
        str(row[manifest_key_column]).lower(): (int(row["launch_block"]), int(row["max_horizon_end_block"]))
        for _, row in batch.iterrows()
    }
    df = df.copy()
    df[key_column] = df[key_column].astype(str).str.lower()
    df["block_number"] = pd.to_numeric(df["block_number"], errors="coerce")
    keep = []
    for _, row in df.iterrows():
        key = str(row[key_column]).lower()
        if key not in bounds or pd.isna(row["block_number"]):
            keep.append(False)
            continue
        lo, hi = bounds[key]
        keep.append(lo <= int(row["block_number"]) <= hi)
    return df.loc[keep].copy()


def collect_swap_batch(
    *,
    endpoint: str,
    batch: pd.DataFrame,
    chunk_size: int,
    min_chunk_size: int,
    progress: bool,
    source_layer: str,
) -> pd.DataFrame:
    if batch.empty:
        return pd.DataFrame(columns=SWAP_IMPORT_COLUMNS)
    logs = fetch_logs(
        endpoint=endpoint,
        address=UNISWAP_V4_POOL_MANAGER_BASE,
        from_block=int(batch["launch_block"].min()),
        to_block=int(batch["max_horizon_end_block"].max()),
        topics=[SWAP_TOPIC, batch["pool_id"].astype(str).str.lower().unique().tolist()],
        chunk_size=chunk_size,
        min_chunk_size=min_chunk_size,
        label="full_cohort_swaps",
        progress=progress,
    )
    rows = []
    for log in logs:
        row = decode_swap(log)
        row["log_index"] = int(log["logIndex"], 16)
        rows.append(row)
    swaps = pd.DataFrame(rows)
    swaps = filter_by_bounds(swaps, batch, key_column="pool_id", manifest_key_column="pool_id")
    swaps = ensure_swap_timestamps(swaps, endpoint)
    if not swaps.empty:
        swaps["source_layer"] = source_layer
    return swaps.reindex(columns=SWAP_IMPORT_COLUMNS)


def collect_transfer_batch(
    *,
    endpoint: str,
    batch: pd.DataFrame,
    chunk_size: int,
    min_chunk_size: int,
    progress: bool,
    source_layer: str,
) -> pd.DataFrame:
    if batch.empty:
        return pd.DataFrame(columns=TRANSFER_IMPORT_COLUMNS)
    logs = fetch_logs(
        endpoint=endpoint,
        address=batch["token_id"].astype(str).str.lower().unique().tolist(),
        from_block=int(batch["launch_block"].min()),
        to_block=int(batch["max_horizon_end_block"].max()),
        topics=[TRANSFER_TOPIC],
        chunk_size=chunk_size,
        min_chunk_size=min_chunk_size,
        label="full_cohort_transfers",
        progress=progress,
    )
    transfers = pd.DataFrame([decode_transfer(log) for log in logs])
    transfers = filter_by_bounds(transfers, batch, key_column="token_id", manifest_key_column="token_id")
    if not transfers.empty:
        transfers["source_layer"] = source_layer
    return transfers.reindex(columns=TRANSFER_IMPORT_COLUMNS)


def blockscout_request_json(url: str, *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "Web3AI4IOResearchBot/0.1"})
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def blockscout_legacy_logs(
    *,
    api_url: str,
    address: str,
    from_block: int,
    to_block: int,
    topic0: str,
    topic1: str | None,
    page_size: int,
    chunk_size: int,
    timeout: float,
    label: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = int(from_block)
    while start <= int(to_block):
        end = min(start + chunk_size - 1, int(to_block))
        page = 1
        while True:
            params = {
                "module": "logs",
                "action": "getLogs",
                "fromBlock": str(start),
                "toBlock": str(end),
                "address": address,
                "topic0": topic0,
                "page": str(page),
                "offset": str(page_size),
            }
            if topic1:
                params["topic1"] = topic1
                params["topic0_1_opr"] = "and"
            url = api_url + "?" + urllib.parse.urlencode(params)
            payload = blockscout_request_json(url, timeout=timeout)
            result = payload.get("result") or []
            if not isinstance(result, list):
                raise RuntimeError(f"Blockscout {label} returned non-list result: {payload}")
            rows.extend(result)
            print(f"{label}: blocks {start}-{end} page={page} logs={len(result)} total={len(rows)}", flush=True)
            if len(result) < page_size:
                break
            page += 1
        start = end + 1
    return rows


def collect_swap_batch_blockscout(
    *,
    api_url: str,
    batch: pd.DataFrame,
    chunk_size: int,
    page_size: int,
    request_timeout: float,
    source_layer: str,
) -> pd.DataFrame:
    rows = []
    for _, token in batch.iterrows():
        logs = blockscout_legacy_logs(
            api_url=api_url,
            address=UNISWAP_V4_POOL_MANAGER_BASE,
            from_block=int(token["launch_block"]),
            to_block=int(token["max_horizon_end_block"]),
            topic0=SWAP_TOPIC,
            topic1=str(token["pool_id"]).lower(),
            page_size=page_size,
            chunk_size=chunk_size,
            timeout=request_timeout,
            label=f"blockscout_swaps:{str(token['pool_id'])[:10]}",
        )
        for log in logs:
            row = decode_swap(log)
            row["log_index"] = int(log["logIndex"], 16)
            rows.append(row)
    swaps = pd.DataFrame(rows)
    swaps = filter_by_bounds(swaps, batch, key_column="pool_id", manifest_key_column="pool_id")
    if not swaps.empty:
        swaps["source_layer"] = source_layer
    return swaps.reindex(columns=SWAP_IMPORT_COLUMNS)


def collect_transfer_batch_blockscout(
    *,
    api_url: str,
    batch: pd.DataFrame,
    chunk_size: int,
    page_size: int,
    request_timeout: float,
    source_layer: str,
) -> pd.DataFrame:
    rows = []
    for _, token in batch.iterrows():
        logs = blockscout_legacy_logs(
            api_url=api_url,
            address=str(token["token_id"]).lower(),
            from_block=int(token["launch_block"]),
            to_block=int(token["max_horizon_end_block"]),
            topic0=TRANSFER_TOPIC,
            topic1=None,
            page_size=page_size,
            chunk_size=chunk_size,
            timeout=request_timeout,
            label=f"blockscout_transfers:{str(token['token_id'])[:10]}",
        )
        rows.extend(decode_transfer(log) for log in logs)
    transfers = pd.DataFrame(rows)
    transfers = filter_by_bounds(transfers, batch, key_column="token_id", manifest_key_column="token_id")
    if not transfers.empty:
        transfers["source_layer"] = source_layer
    return transfers.reindex(columns=TRANSFER_IMPORT_COLUMNS)


def coverage_rows(
    *,
    batch: pd.DataFrame,
    observed: pd.DataFrame,
    coverage_type: str,
    query_key: str,
    observed_key: str,
    source_layer: str,
) -> pd.DataFrame:
    rows = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    counts = (
        observed.assign(_key=observed[observed_key].astype(str).str.lower()).groupby("_key").size().to_dict()
        if not observed.empty and observed_key in observed
        else {}
    )
    for _, token in batch.iterrows():
        key = str(token[observed_key]).lower()
        observed_rows = int(counts.get(key, 0))
        rows.append(
            {
                "coverage_type": coverage_type,
                "unit_id": token[query_key],
                "token_id": str(token["token_id"]).lower(),
                "pool_id": str(token["pool_id"]).lower(),
                "cohort_side": token["cohort_side"],
                "from_block": int(token["launch_block"]),
                "to_block": int(token["max_horizon_end_block"]),
                "observed_rows": observed_rows,
                "coverage_status": "processed_with_rows" if observed_rows else "processed_zero_rows",
                "collected_at_utc": now,
                "source_layer": source_layer,
            }
        )
    return pd.DataFrame(rows).reindex(columns=COVERAGE_COLUMNS)


def summarize(
    *,
    manifest: pd.DataFrame,
    coverage_path: Path,
    swaps_path: Path,
    transfers_path: Path,
    summary_path: Path,
) -> None:
    coverage = read_csv(coverage_path, low_memory=False)
    swaps = read_csv(swaps_path, low_memory=False)
    transfers = read_csv(transfers_path, low_memory=False)
    summary: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "manifest_tokens": int(manifest["token_id"].nunique()) if not manifest.empty else 0,
        "manifest_rows": int(len(manifest)),
        "swap_import_rows": int(len(swaps)),
        "transfer_import_rows": int(len(transfers)),
        "claim_boundary": (
            "Backfill summary tracks processed query units and imported rows. Full-cohort causal claims require "
            "processed swap and transfer coverage for the complete manifest plus reconstructed token horizons."
        ),
        "outputs": {
            "swaps": str(swaps_path),
            "transfers": str(transfers_path),
            "coverage": str(coverage_path),
        },
    }
    if not coverage.empty:
        by_type = {}
        for coverage_type, group in coverage.groupby("coverage_type"):
            processed_group = group.loc[group["coverage_status"].astype(str).str.startswith("processed_")].copy()
            processed = int(processed_group["unit_id"].nunique())
            rows_with_data = int(
                processed_group.loc[
                    pd.to_numeric(processed_group["observed_rows"], errors="coerce").gt(0),
                    "unit_id",
                ].nunique()
            )
            by_type[str(coverage_type)] = {
                "processed_units": processed,
                "processed_share_of_manifest": processed / len(manifest) if len(manifest) else 0,
                "units_with_observed_rows": rows_with_data,
                "observed_rows": int(pd.to_numeric(processed_group["observed_rows"], errors="coerce").fillna(0).sum()),
                "collection_error_units": int(
                    group.loc[group["coverage_status"].astype(str).eq("collection_error"), "unit_id"].nunique()
                ),
            }
        summary["coverage_by_type"] = by_type
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def merge_existing_raw_sample(
    *,
    manifest: pd.DataFrame,
    sample_cohort_path: Path,
    sample_swaps_path: Path,
    sample_transfers_path: Path,
    swaps_path: Path,
    transfers_path: Path,
    coverage_path: Path,
) -> None:
    sample_cohort = read_csv(sample_cohort_path, low_memory=False)
    if sample_cohort.empty or "token_id" not in sample_cohort:
        print(f"merge_existing_raw_sample: no sample cohort at {sample_cohort_path}", flush=True)
        return
    sample_tokens = set(sample_cohort["token_id"].astype(str).str.lower())
    sample_manifest = manifest.loc[manifest["token_id"].astype(str).str.lower().isin(sample_tokens)].copy()
    if sample_manifest.empty:
        print("merge_existing_raw_sample: sample cohort tokens are not in the full manifest.", flush=True)
        return
    source_layer = "Accepted bounded Clanker/Base matched sample imported into full-cohort ledger"

    sample_swaps = read_csv(sample_swaps_path, low_memory=False, dtype=str)
    if not sample_swaps.empty:
        for column in SWAP_IMPORT_COLUMNS:
            if column not in sample_swaps.columns:
                sample_swaps[column] = ""
        sample_swaps["pool_id"] = sample_swaps["pool_id"].astype(str).str.lower()
        sample_swaps["source_layer"] = source_layer
        sample_swaps = filter_by_bounds(
            sample_swaps.reindex(columns=SWAP_IMPORT_COLUMNS),
            sample_manifest,
            key_column="pool_id",
            manifest_key_column="pool_id",
        )
        append_csv(swaps_path, sample_swaps, SWAP_IMPORT_COLUMNS)

    sample_transfers = read_csv(sample_transfers_path, low_memory=False, dtype=str)
    if not sample_transfers.empty:
        for column in TRANSFER_IMPORT_COLUMNS:
            if column not in sample_transfers.columns:
                sample_transfers[column] = ""
        sample_transfers["token_id"] = sample_transfers["token_id"].astype(str).str.lower()
        sample_transfers["source_layer"] = source_layer
        sample_transfers = filter_by_bounds(
            sample_transfers.reindex(columns=TRANSFER_IMPORT_COLUMNS),
            sample_manifest,
            key_column="token_id",
            manifest_key_column="token_id",
        )
        append_csv(transfers_path, sample_transfers, TRANSFER_IMPORT_COLUMNS)

    swap_cov = coverage_rows(
        batch=sample_manifest,
        observed=sample_swaps if not sample_swaps.empty else pd.DataFrame(columns=SWAP_IMPORT_COLUMNS),
        coverage_type="poolmanager_swaps",
        query_key="swap_query_key",
        observed_key="pool_id",
        source_layer=source_layer,
    )
    transfer_cov = coverage_rows(
        batch=sample_manifest,
        observed=sample_transfers if not sample_transfers.empty else pd.DataFrame(columns=TRANSFER_IMPORT_COLUMNS),
        coverage_type="erc20_transfers",
        query_key="transfer_query_key",
        observed_key="token_id",
        source_layer=source_layer,
    )
    append_csv(coverage_path, pd.concat([swap_cov, transfer_cov], ignore_index=True), COVERAGE_COLUMNS)
    dedupe_csv(
        swaps_path,
        ["transaction_hash", "pool_id", "block_number", "sender", "amount0_raw", "amount1_raw"],
        SWAP_IMPORT_COLUMNS,
    )
    dedupe_csv(transfers_path, ["transaction_hash", "log_index", "token_id"], TRANSFER_IMPORT_COLUMNS)
    dedupe_coverage_csv(coverage_path)
    print(
        "merge_existing_raw_sample: "
        f"sample_tokens={sample_manifest['token_id'].nunique()} swaps={len(sample_swaps)} transfers={len(sample_transfers)}",
        flush=True,
    )


def run_collection(
    *,
    kind: str,
    source: str,
    manifest: pd.DataFrame,
    endpoint: str,
    blockscout_api: str,
    batch_size: int,
    chunk_size: int,
    min_chunk_size: int,
    blockscout_page_size: int,
    request_timeout: float,
    progress: bool,
    source_layer: str,
    out_path: Path,
    coverage_path: Path,
    stop_after_seconds: int,
    skip_errors: bool,
) -> None:
    started = time.time()
    if kind == "swaps":
        collect_fn = collect_swap_batch
        blockscout_collect_fn = collect_swap_batch_blockscout
        columns = SWAP_IMPORT_COLUMNS
        coverage_type = "poolmanager_swaps"
        query_key = "swap_query_key"
        observed_key = "pool_id"
        dedupe_keys = ["transaction_hash", "pool_id", "block_number", "sender", "amount0_raw", "amount1_raw"]
    elif kind == "transfers":
        collect_fn = collect_transfer_batch
        blockscout_collect_fn = collect_transfer_batch_blockscout
        columns = TRANSFER_IMPORT_COLUMNS
        coverage_type = "erc20_transfers"
        query_key = "transfer_query_key"
        observed_key = "token_id"
        dedupe_keys = ["transaction_hash", "log_index", "token_id"]
    else:
        raise RuntimeError(f"Unknown collection kind: {kind}")

    batches = batch_frames(manifest, batch_size)
    for index, batch in enumerate(batches):
        if stop_after_seconds and time.time() - started >= stop_after_seconds:
            print(f"{kind}: stopping after {stop_after_seconds}s with {len(batches) - index} batches remaining", flush=True)
            break
        print(
            f"{kind}: batch {index + 1}/{len(batches)} units={len(batch)} "
            f"blocks={int(batch['launch_block'].min())}-{int(batch['max_horizon_end_block'].max())}",
            flush=True,
        )
        try:
            if source == "blockscout-legacy":
                observed = blockscout_collect_fn(
                    api_url=blockscout_api,
                    batch=batch,
                    chunk_size=chunk_size,
                    page_size=blockscout_page_size,
                    request_timeout=request_timeout,
                    source_layer=source_layer,
                )
            else:
                observed = collect_fn(
                    endpoint=endpoint,
                    batch=batch,
                    chunk_size=chunk_size,
                    min_chunk_size=min_chunk_size,
                    progress=progress,
                    source_layer=source_layer,
                )
        except Exception as exc:
            if not skip_errors:
                raise
            error_source = f"{source_layer}; collection_error={type(exc).__name__}: {str(exc)[:180]}"
            cov = coverage_rows(
                batch=batch,
                observed=pd.DataFrame(columns=columns),
                coverage_type=coverage_type,
                query_key=query_key,
                observed_key=observed_key,
                source_layer=error_source,
            )
            cov["coverage_status"] = "collection_error"
            append_csv(coverage_path, cov, COVERAGE_COLUMNS)
            print(f"{kind}: collection_error coverage_rows={len(cov)} error={type(exc).__name__}: {exc}", flush=True)
            continue
        append_csv(out_path, observed, columns)
        cov = coverage_rows(
            batch=batch,
            observed=observed,
            coverage_type=coverage_type,
            query_key=query_key,
            observed_key=observed_key,
            source_layer=source_layer,
        )
        append_csv(coverage_path, cov, COVERAGE_COLUMNS)
        print(f"{kind}: observed_rows={len(observed)} coverage_rows={len(cov)}", flush=True)
    if not out_path.exists():
        write_csv(out_path, pd.DataFrame(columns=columns), columns)
    dedupe_csv(out_path, dedupe_keys, columns)
    dedupe_coverage_csv(coverage_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["rpc", "blockscout-legacy"], default="rpc")
    parser.add_argument("--rpc-url", default=DEFAULT_BACKFILL_RPC)
    parser.add_argument("--blockscout-api", default=DEFAULT_BLOCKSCOUT_API)
    parser.add_argument("--manifest", default=str(EXTERNAL / "clanker_base_full_cohort_manifest.csv"))
    parser.add_argument("--collect", choices=["swaps", "transfers", "both", "none"], default="both")
    parser.add_argument("--cohort-side", choices=["all", "pre_v4_0_control", "post_v4_1_treated"], default="all")
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--min-chunk-size", type=int, default=5_000)
    parser.add_argument("--blockscout-page-size", type=int, default=1_000)
    parser.add_argument("--request-timeout", type=float, default=45.0)
    parser.add_argument("--blocks-per-day", type=int, default=43_500)
    parser.add_argument(
        "--max-horizon-days",
        type=int,
        default=30,
        help="Cap collection horizon for staged backfills or smoke tests. Use 30 for the registered full run.",
    )
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--max-units", type=int, default=0, help="0 means no explicit cap.")
    parser.add_argument(
        "--sample-strategy",
        choices=["first", "evenly_spaced"],
        default="first",
        help="How to choose rows when --max-units is set after resume/start-index filtering.",
    )
    parser.add_argument("--stop-after-seconds", type=int, default=0, help="0 means no time cap.")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--skip-errors",
        action="store_true",
        help="Record collection_error rows and continue instead of aborting a resumable backfill.",
    )
    parser.add_argument("--quiet-logs", action="store_true")
    parser.add_argument(
        "--swaps-out",
        default=str(EXTERNAL / "clanker_base_full_cohort_swaps_import.csv"),
    )
    parser.add_argument(
        "--transfers-out",
        default=str(EXTERNAL / "clanker_base_full_cohort_transfers_import.csv"),
    )
    parser.add_argument(
        "--coverage-out",
        default=str(EXTERNAL / "clanker_base_full_cohort_import_coverage.csv"),
    )
    parser.add_argument(
        "--summary-out",
        default=str(TABLES / "clanker_base_full_cohort_backfill_summary.json"),
    )
    parser.add_argument(
        "--merge-existing-raw-sample",
        action="store_true",
        help="Merge the accepted bounded Base sample raw swaps/transfers into the full-cohort import files.",
    )
    parser.add_argument(
        "--sample-cohort",
        default=str(EXTERNAL / "clanker_base_event_cohort.csv"),
    )
    parser.add_argument(
        "--sample-swaps",
        default=str(EXTERNAL / "clanker_base_pool_swaps_raw.csv"),
    )
    parser.add_argument(
        "--sample-transfers",
        default=str(EXTERNAL / "clanker_base_token_transfers_raw.csv"),
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    swaps_path = Path(args.swaps_out).expanduser().resolve()
    transfers_path = Path(args.transfers_out).expanduser().resolve()
    coverage_path = Path(args.coverage_out).expanduser().resolve()
    summary_path = Path(args.summary_out).expanduser().resolve()

    if args.source == "rpc" and "mainnet.base.org" in args.rpc_url and args.chunk_size > 10_000:
        print("Base official RPC limits eth_getLogs to 10,000 blocks; reducing --chunk-size to 10000.", flush=True)
        args.chunk_size = 10_000
    if args.source == "rpc" and "mainnet.base.org" in args.rpc_url and args.min_chunk_size > 10_000:
        args.min_chunk_size = 10_000

    full_manifest = load_manifest(
        manifest_path,
        cohort_side=args.cohort_side,
        max_horizon_days=args.max_horizon_days,
        blocks_per_day=args.blocks_per_day,
    )
    source_layer = (
        f"Base Blockscout legacy getLogs backfill: {args.blockscout_api}"
        if args.source == "blockscout-legacy"
        else f"Base JSON-RPC/archive log backfill: {args.rpc_url}"
    )
    if args.merge_existing_raw_sample:
        merge_existing_raw_sample(
            manifest=full_manifest,
            sample_cohort_path=Path(args.sample_cohort).expanduser().resolve(),
            sample_swaps_path=Path(args.sample_swaps).expanduser().resolve(),
            sample_transfers_path=Path(args.sample_transfers).expanduser().resolve(),
            swaps_path=swaps_path,
            transfers_path=transfers_path,
            coverage_path=coverage_path,
        )
    if args.collect in {"swaps", "both"}:
        swap_work = select_work(
            full_manifest,
            coverage_path=coverage_path,
            coverage_type="poolmanager_swaps",
            query_key="swap_query_key",
            resume=not args.no_resume,
            start_index=args.start_index,
            max_units=args.max_units,
            sample_strategy=args.sample_strategy,
        )
        run_collection(
            kind="swaps",
            source=args.source,
            manifest=swap_work,
            endpoint=args.rpc_url,
            blockscout_api=args.blockscout_api,
            batch_size=args.batch_size,
            chunk_size=args.chunk_size,
            min_chunk_size=args.min_chunk_size,
            blockscout_page_size=args.blockscout_page_size,
            request_timeout=args.request_timeout,
            progress=not args.quiet_logs,
            source_layer=source_layer,
            out_path=swaps_path,
            coverage_path=coverage_path,
            stop_after_seconds=args.stop_after_seconds,
            skip_errors=args.skip_errors,
        )
    if args.collect in {"transfers", "both"}:
        transfer_work = select_work(
            full_manifest,
            coverage_path=coverage_path,
            coverage_type="erc20_transfers",
            query_key="transfer_query_key",
            resume=not args.no_resume,
            start_index=args.start_index,
            max_units=args.max_units,
            sample_strategy=args.sample_strategy,
        )
        run_collection(
            kind="transfers",
            source=args.source,
            manifest=transfer_work,
            endpoint=args.rpc_url,
            blockscout_api=args.blockscout_api,
            batch_size=args.batch_size,
            chunk_size=args.chunk_size,
            min_chunk_size=args.min_chunk_size,
            blockscout_page_size=args.blockscout_page_size,
            request_timeout=args.request_timeout,
            progress=not args.quiet_logs,
            source_layer=source_layer,
            out_path=transfers_path,
            coverage_path=coverage_path,
            stop_after_seconds=args.stop_after_seconds,
            skip_errors=args.skip_errors,
        )
    summarize(
        manifest=full_manifest,
        coverage_path=coverage_path,
        swaps_path=swaps_path,
        transfers_path=transfers_path,
        summary_path=summary_path,
    )
    print(f"Backfill summary written to {summary_path}", flush=True)


if __name__ == "__main__":
    main()
