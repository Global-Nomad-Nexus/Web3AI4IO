#!/usr/bin/env python3
"""Render or execute full token-level Dune exports for application-arm H1/H4.

The script reads the 1,651 RED-PUMP graduated mints and produces two
paper-grade token-level outcome tables when a Dune API key is available:

1. 1/7/30d post-migration trading persistence from ``dex_solana.trades``.
2. Early-wallet concentration / sniper proxy in the first launch window.

By default it only renders complete SQL files under
``artifacts/external_validation/dune_sql``. Pass ``--execute`` with
``DUNE_API_KEY`` in the environment to submit the SQL through Dune's REST API.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.io import load_config, write_csv, write_json


DUNE_API_BASE = "https://api.dune.com/api/v1"

POST_REQUIRED_COLUMNS = {
    "mint",
    "graduated_at",
    "horizon_days",
    "swap_count",
    "active_traders",
    "volume_usd",
    "first_trade_at",
    "last_trade_at",
    "inactivity_gap_hours",
    "reactivated_after_7d",
}

EARLY_REQUIRED_COLUMNS = {
    "mint",
    "launch_or_graduated_at",
    "early_window_seconds",
    "early_wallets",
    "early_volume_usd",
    "top1_early_wallet_share",
    "top5_early_wallet_share",
    "top10_early_wallet_share",
    "early_wallet_hhi",
    "sniper_top1_80pct",
    "sniper_top5_95pct",
    "first_trade_at",
    "last_early_trade_at",
}


def parse_time(value: Any) -> datetime:
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text).astimezone(UTC)


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def iso_timestamp(value: Any) -> str:
    return parse_time(value).isoformat().replace("+00:00", "Z")


def dune_timestamp_expr(value: Any) -> str:
    return f"CAST(from_iso8601_timestamp({sql_string(iso_timestamp(value))}) AS timestamp)"


def dune_date_expr(value: Any) -> str:
    return f"DATE '{parse_time(value).date().isoformat()}'"


def month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def sample_graduated_tokens(graduated: pd.DataFrame, *, max_tokens: int, strategy: str) -> pd.DataFrame:
    if max_tokens <= 0 or max_tokens >= len(graduated):
        return graduated.reset_index(drop=False).rename(columns={"index": "graduated_index"})
    if strategy == "evenly_spaced":
        positions = np.linspace(0, len(graduated) - 1, max_tokens).round().astype(int)
        positions = sorted(set(int(pos) for pos in positions))
        return graduated.iloc[positions].reset_index(drop=False).rename(columns={"index": "graduated_index"})
    return graduated.head(max_tokens).reset_index(drop=False).rename(columns={"index": "graduated_index"})


def render_values(df: pd.DataFrame, *, time_column: str, include_created_at: bool = False) -> str:
    rows: list[str] = []
    for _, row in df.iterrows():
        if include_created_at:
            rows.append(
                "        ("
                f"{sql_string(str(row['mint']))}, "
                f"{dune_timestamp_expr(row['created_at'])}, "
                f"{dune_timestamp_expr(row['graduated_at'])}"
                ")"
            )
        else:
            rows.append(
                "        ("
                f"{sql_string(str(row['mint']))}, "
                f"{dune_timestamp_expr(row[time_column])}"
                ")"
            )
    return ",\n".join(rows)


def render_post_migration_sql(df: pd.DataFrame) -> str:
    values = render_values(df, time_column="graduated_at")
    min_graduated = df["graduated_at"].map(parse_time).min()
    max_graduated = df["graduated_at"].map(parse_time).max()
    upper_dt = max_graduated + pd.Timedelta(days=30)
    lower_bound = dune_timestamp_expr(min_graduated.isoformat())
    upper_bound = dune_timestamp_expr(upper_dt.isoformat())
    lower_date = dune_date_expr(min_graduated.isoformat())
    upper_date = dune_date_expr(upper_dt.isoformat())
    lower_month = dune_date_expr(month_start(min_graduated).isoformat())
    upper_month = dune_date_expr(month_start(upper_dt).isoformat())
    return f"""-- Auto-rendered by application/scripts/run_dune_token_exports.py.
-- Outcome: token-level Pump.fun/PumpSwap post-migration persistence.
-- Expected rows for full export: 1,651 tokens x 3 horizons = 4,953 rows.

WITH graduated(mint, graduated_at) AS (
    VALUES
{values}
),
token_trades AS (
    SELECT
        g.mint,
        g.graduated_at,
        t.block_time,
        t.tx_id,
        t.trader_id,
        t.amount_usd
    FROM dex_solana.trades t
    JOIN graduated g
      ON t.token_bought_mint_address = g.mint
      OR t.token_sold_mint_address = g.mint
    WHERE t.block_month >= {lower_month}
      AND t.block_month <= {upper_month}
      AND t.block_date >= {lower_date}
      AND t.block_date <= {upper_date}
      AND (
          t.token_bought_mint_address IN (SELECT mint FROM graduated)
          OR t.token_sold_mint_address IN (SELECT mint FROM graduated)
      )
      AND t.block_time >= {lower_bound}
      AND t.block_time < {upper_bound}
      AND t.block_time >= g.graduated_at
      AND t.block_time < g.graduated_at + INTERVAL '30' day
),
horizons AS (
    SELECT 1 AS horizon_days
    UNION ALL SELECT 7
    UNION ALL SELECT 30
),
by_horizon AS (
    SELECT
        g.mint,
        g.graduated_at,
        h.horizon_days,
        COUNT(DISTINCT t.tx_id) AS swap_count,
        COUNT(DISTINCT t.trader_id) AS active_traders,
        COALESCE(SUM(t.amount_usd), 0) AS volume_usd,
        MIN(t.block_time) AS first_trade_at,
        MAX(t.block_time) AS last_trade_at
    FROM graduated g
    CROSS JOIN horizons h
    LEFT JOIN token_trades t
      ON t.mint = g.mint
     AND t.block_time < g.graduated_at + h.horizon_days * INTERVAL '1' day
    GROUP BY 1, 2, 3
),
daily_activity AS (
    SELECT
        t.mint,
        DATE_TRUNC('day', t.block_time) AS trade_day,
        COUNT(*) AS swaps
    FROM token_trades t
    GROUP BY 1, 2
),
reactivation AS (
    SELECT
        d.mint,
        MAX(CASE WHEN d.trade_day >= DATE_TRUNC('day', g.graduated_at + INTERVAL '7' day) THEN 1 ELSE 0 END) AS reactivated_after_7d
    FROM daily_activity d
    JOIN graduated g ON d.mint = g.mint
    GROUP BY 1
)
SELECT
    b.mint,
    b.graduated_at,
    b.horizon_days,
    b.swap_count,
    b.active_traders,
    b.volume_usd,
    b.first_trade_at,
    b.last_trade_at,
    DATE_DIFF('hour', b.first_trade_at, b.last_trade_at) AS inactivity_gap_hours,
    COALESCE(r.reactivated_after_7d, 0) AS reactivated_after_7d
FROM by_horizon b
LEFT JOIN reactivation r ON b.mint = r.mint
ORDER BY b.mint, b.horizon_days;
"""


def render_early_wallet_sql(df: pd.DataFrame, *, early_window_seconds: int) -> str:
    values = render_values(df, time_column="created_at")
    min_created = df["created_at"].map(parse_time).min()
    max_created = df["created_at"].map(parse_time).max()
    upper_dt = max_created + pd.Timedelta(seconds=early_window_seconds)
    lower_bound = dune_timestamp_expr(min_created.isoformat())
    upper_bound = dune_timestamp_expr(upper_dt.isoformat())
    lower_date = dune_date_expr(min_created.isoformat())
    upper_date = dune_date_expr(upper_dt.isoformat())
    lower_month = dune_date_expr(month_start(min_created).isoformat())
    upper_month = dune_date_expr(month_start(upper_dt).isoformat())
    return f"""-- Auto-rendered by application/scripts/run_dune_token_exports.py.
-- Outcome: early-wallet concentration / sniper proxy around Pump.fun launch.
-- This uses Dune's decoded Solana DEX trade table; validate project labels
-- and token bought/sold semantics before making final paper claims.

WITH tokens(mint, launch_or_graduated_at) AS (
    VALUES
{values}
),
candidate_trades AS (
    SELECT
        tok.mint,
        tok.launch_or_graduated_at,
        {early_window_seconds} AS early_window_seconds,
        t.block_time,
        t.tx_id,
        t.trader_id AS wallet,
        t.amount_usd,
        t.token_bought_mint_address,
        t.token_sold_mint_address
    FROM dex_solana.trades t
    JOIN tokens tok
      ON t.token_bought_mint_address = tok.mint
      OR t.token_sold_mint_address = tok.mint
    WHERE t.block_month >= {lower_month}
      AND t.block_month <= {upper_month}
      AND t.block_date >= {lower_date}
      AND t.block_date <= {upper_date}
      AND (
          t.token_bought_mint_address IN (SELECT mint FROM tokens)
          OR t.token_sold_mint_address IN (SELECT mint FROM tokens)
      )
      AND t.block_time >= {lower_bound}
      AND t.block_time < {upper_bound}
      AND t.block_time >= tok.launch_or_graduated_at
      AND t.block_time < tok.launch_or_graduated_at + INTERVAL '{early_window_seconds}' second
),
early AS (
    SELECT
        mint,
        launch_or_graduated_at,
        early_window_seconds,
        wallet,
        COUNT(DISTINCT tx_id) AS wallet_trades,
        SUM(COALESCE(amount_usd, 0)) AS wallet_volume_usd,
        CASE
            WHEN SUM(COALESCE(amount_usd, 0)) > 0 THEN SUM(COALESCE(amount_usd, 0))
            ELSE CAST(COUNT(DISTINCT tx_id) AS double)
        END AS wallet_weight,
        MIN(block_time) AS first_trade_at,
        MAX(block_time) AS last_early_trade_at
    FROM candidate_trades
    GROUP BY 1, 2, 3, 4
),
ranked AS (
    SELECT
        *,
        wallet_weight / NULLIF(SUM(wallet_weight) OVER (PARTITION BY mint), 0) AS wallet_share,
        ROW_NUMBER() OVER (PARTITION BY mint ORDER BY wallet_weight DESC, wallet_volume_usd DESC, wallet_trades DESC) AS wallet_rank
    FROM early
),
by_token AS (
    SELECT
        mint,
        MIN(launch_or_graduated_at) AS launch_or_graduated_at,
        {early_window_seconds} AS early_window_seconds,
        COUNT(DISTINCT wallet) AS early_wallets,
        SUM(wallet_volume_usd) AS early_volume_usd,
        SUM(CASE WHEN wallet_rank <= 1 THEN wallet_share ELSE 0 END) AS top1_early_wallet_share,
        SUM(CASE WHEN wallet_rank <= 5 THEN wallet_share ELSE 0 END) AS top5_early_wallet_share,
        SUM(CASE WHEN wallet_rank <= 10 THEN wallet_share ELSE 0 END) AS top10_early_wallet_share,
        SUM(POWER(wallet_share, 2)) AS early_wallet_hhi,
        CAST(SUM(CASE WHEN wallet_rank <= 1 THEN wallet_share ELSE 0 END) >= 0.80 AS integer) AS sniper_top1_80pct,
        CAST(SUM(CASE WHEN wallet_rank <= 5 THEN wallet_share ELSE 0 END) >= 0.95 AS integer) AS sniper_top5_95pct,
        MIN(first_trade_at) AS first_trade_at,
        MAX(last_early_trade_at) AS last_early_trade_at
    FROM ranked
    GROUP BY 1
)
SELECT
    tok.mint,
    tok.launch_or_graduated_at,
    {early_window_seconds} AS early_window_seconds,
    COALESCE(b.early_wallets, 0) AS early_wallets,
    COALESCE(b.early_volume_usd, 0) AS early_volume_usd,
    COALESCE(b.top1_early_wallet_share, 0) AS top1_early_wallet_share,
    COALESCE(b.top5_early_wallet_share, 0) AS top5_early_wallet_share,
    COALESCE(b.top10_early_wallet_share, 0) AS top10_early_wallet_share,
    COALESCE(b.early_wallet_hhi, 0) AS early_wallet_hhi,
    COALESCE(b.sniper_top1_80pct, 0) AS sniper_top1_80pct,
    COALESCE(b.sniper_top5_95pct, 0) AS sniper_top5_95pct,
    b.first_trade_at,
    b.last_early_trade_at
FROM tokens tok
LEFT JOIN by_token b ON tok.mint = b.mint
ORDER BY tok.mint;
"""


def request_json(
    method: str,
    url: str,
    *,
    api_key: str,
    body: dict[str, Any] | None = None,
    timeout: float,
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Dune-Api-Key": api_key,
            "User-Agent": "Web3AI4IOResearchBot/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Dune API HTTP {exc.code}: {payload[:500]}") from exc


def execute_sql(sql: str, *, api_key: str, performance: str, timeout: float) -> str:
    payload = request_json(
        "POST",
        f"{DUNE_API_BASE}/sql/execute",
        api_key=api_key,
        body={"sql": sql, "performance": performance},
        timeout=timeout,
    )
    execution_id = payload.get("execution_id")
    if not execution_id:
        raise RuntimeError(f"Dune execution did not return execution_id: {payload}")
    return str(execution_id)


def poll_execution(
    execution_id: str,
    *,
    api_key: str,
    poll_seconds: float,
    timeout_minutes: float,
    request_timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_minutes * 60
    last_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_status = request_json(
            "GET",
            f"{DUNE_API_BASE}/execution/{execution_id}/status",
            api_key=api_key,
            timeout=request_timeout,
        )
        state = str(last_status.get("state", ""))
        print(f"Dune execution {execution_id}: {state}", flush=True)
        if state in {"QUERY_STATE_COMPLETED", "QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED", "QUERY_STATE_EXPIRED"}:
            return last_status
        time.sleep(poll_seconds)
    raise TimeoutError(f"Dune execution timed out after {timeout_minutes} minutes: {last_status}")


def download_csv(
    execution_id: str,
    *,
    api_key: str,
    output_path: Path,
    allow_partial_results: bool,
    timeout: float,
) -> pd.DataFrame:
    query = urllib.parse.urlencode({"allow_partial_results": str(allow_partial_results).lower()})
    url = f"{DUNE_API_BASE}/execution/{execution_id}/results/csv?{query}"
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"X-Dune-Api-Key": api_key, "User-Agent": "Web3AI4IOResearchBot/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Dune CSV download HTTP {exc.code}: {payload[:500]}") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return pd.read_csv(io.StringIO(text))


def validate_schema(df: pd.DataFrame, required_columns: set[str], *, label: str) -> dict[str, Any]:
    columns = set(df.columns)
    missing = sorted(required_columns - columns)
    return {
        "label": label,
        "rows": int(len(df)),
        "columns": sorted(df.columns),
        "missing_required_columns": missing,
        "schema_ok": not missing,
    }


def execution_cost(status: dict[str, Any]) -> float:
    try:
        return float(status.get("execution_cost_credits", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def chunk_dataframe(df: pd.DataFrame, *, chunk_size: int) -> list[tuple[int, pd.DataFrame]]:
    if chunk_size <= 0 or chunk_size >= len(df):
        return [(0, df.reset_index(drop=True))]
    chunks = []
    for chunk_id, start in enumerate(range(0, len(df), chunk_size)):
        chunks.append((chunk_id, df.iloc[start : start + chunk_size].reset_index(drop=True)))
    return chunks


def execute_one_export(
    *,
    label: str,
    sql: str,
    output_path: Path,
    required_columns: set[str],
    api_key: str,
    performance: str,
    poll_seconds: float,
    timeout_minutes: float,
    request_timeout: float,
    allow_partial_results: bool,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    print(f"Submitting Dune SQL for {label}...", flush=True)
    execution_id = execute_sql(sql, api_key=api_key, performance=performance, timeout=request_timeout)
    status = poll_execution(
        execution_id,
        api_key=api_key,
        poll_seconds=poll_seconds,
        timeout_minutes=timeout_minutes,
        request_timeout=request_timeout,
    )
    execution = {"execution_id": execution_id, "status": status}
    if status.get("state") != "QUERY_STATE_COMPLETED":
        raise RuntimeError(f"Dune execution failed for {label}: {status}")
    df = download_csv(
        execution_id,
        api_key=api_key,
        output_path=output_path,
        allow_partial_results=allow_partial_results,
        timeout=request_timeout,
    )
    output = validate_schema(df, required_columns, label=label)
    print(f"Downloaded {label}: {len(df)} rows -> {output_path}", flush=True)
    return df, execution, output


def selected_export_specs(only: str) -> list[tuple[str, str, set[str]]]:
    specs = [
        ("post_migration", "dune_post_migration_trades.csv", POST_REQUIRED_COLUMNS),
        ("early_wallets", "dune_early_wallets.csv", EARLY_REQUIRED_COLUMNS),
    ]
    if only == "both":
        return specs
    return [spec for spec in specs if spec[0] == only]


def write_graduated_manifest(df: pd.DataFrame, output_path: Path) -> None:
    rows = df[["graduated_index", "mint", "created_at", "graduated_at"]].copy()
    write_csv(output_path, rows)


def write_sql_inputs(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["graduated_index", "mint", "created_at_iso", "graduated_at_iso"])
        for _, row in df.iterrows():
            writer.writerow(
                [
                    int(row["graduated_index"]),
                    row["mint"],
                    iso_timestamp(row["created_at"]),
                    iso_timestamp(row["graduated_at"]),
                ]
            )


def render_sql_for_label(label: str, df: pd.DataFrame, *, early_window_seconds: int) -> str:
    if label == "post_migration":
        return render_post_migration_sql(df)
    if label == "early_wallets":
        return render_early_wallet_sql(df, early_window_seconds=early_window_seconds)
    raise ValueError(f"Unknown Dune export label: {label}")


def run_chunked_exports(
    *,
    graduated: pd.DataFrame,
    config_tables_dir: Path,
    out_dir: Path,
    sql_dir: Path,
    summary: dict[str, Any],
    api_key: str,
    only: str,
    chunk_size: int,
    resume: bool,
    max_total_credits: float | None,
    performance: str,
    poll_seconds: float,
    timeout_minutes: float,
    request_timeout: float,
    allow_partial_results: bool,
    early_window_seconds: int,
) -> dict[str, Any]:
    chunk_csv_dir = out_dir / "dune_chunks"
    chunk_sql_dir = sql_dir / "chunks"
    chunk_csv_dir.mkdir(parents=True, exist_ok=True)
    chunk_sql_dir.mkdir(parents=True, exist_ok=True)

    specs = selected_export_specs(only)
    frames: dict[str, list[pd.DataFrame]] = {label: [] for label, _, _ in specs}
    executions: dict[str, list[dict[str, Any]]] = {label: [] for label, _, _ in specs}
    chunk_outputs: dict[str, list[dict[str, Any]]] = {label: [] for label, _, _ in specs}
    total_cost = 0.0
    stop_reason = ""

    chunks = chunk_dataframe(graduated, chunk_size=chunk_size)
    for chunk_id, chunk in chunks:
        if stop_reason:
            break
        chunk_min = iso_timestamp(chunk["created_at"].iloc[0])
        chunk_max = iso_timestamp(chunk["graduated_at"].iloc[-1])
        print(
            f"Dune chunk {chunk_id + 1}/{len(chunks)}: {len(chunk)} tokens "
            f"created_from={chunk_min} graduated_to={chunk_max}",
            flush=True,
        )
        for label, final_filename, required_columns in specs:
            if max_total_credits is not None and total_cost >= max_total_credits:
                stop_reason = (
                    f"Observed Dune cost {total_cost:.2f} credits reached "
                    f"--max-total-credits {max_total_credits:.2f}; no further queries submitted."
                )
                print(stop_reason, flush=True)
                break
            sql = render_sql_for_label(label, chunk, early_window_seconds=early_window_seconds)
            chunk_sql_path = chunk_sql_dir / f"{label}_chunk_{chunk_id:03d}.sql"
            chunk_sql_path.write_text(sql, encoding="utf-8")
            chunk_output_path = chunk_csv_dir / f"{label}_chunk_{chunk_id:03d}.csv"
            if resume and chunk_output_path.exists() and chunk_output_path.stat().st_size > 0:
                df = pd.read_csv(chunk_output_path)
                output = validate_schema(df, required_columns, label=label)
                output.update({"chunk_id": chunk_id, "chunk_rows": int(len(chunk)), "resumed": True})
                frames[label].append(df)
                chunk_outputs[label].append(output)
                print(f"Resumed {label} chunk {chunk_id:03d}: {len(df)} rows", flush=True)
                continue
            try:
                df, execution, output = execute_one_export(
                    label=f"{label}_chunk_{chunk_id:03d}",
                    sql=sql,
                    output_path=chunk_output_path,
                    required_columns=required_columns,
                    api_key=api_key,
                    performance=performance,
                    poll_seconds=poll_seconds,
                    timeout_minutes=timeout_minutes,
                    request_timeout=request_timeout,
                    allow_partial_results=allow_partial_results,
                )
            except Exception as exc:
                stop_reason = f"Stopped after Dune error on {label} chunk {chunk_id:03d}: {type(exc).__name__}: {exc}"
                print(stop_reason, flush=True)
                summary.update(
                    {
                        "status": "stopped_chunked_dune_indexer_exports_partial",
                        "chunked": True,
                        "chunk_size": int(chunk_size),
                        "chunks_total": int(len(chunks)),
                        "chunks_completed": int(chunk_id),
                        "performance": performance,
                        "estimated_total_execution_cost_credits": total_cost,
                        "stop_reason": stop_reason,
                        "executions": executions,
                        "chunk_outputs": chunk_outputs,
                    }
                )
                write_json(config_tables_dir / "dune_indexer_export_summary.json", summary)
                break
            cost = execution_cost(execution["status"])
            total_cost += cost
            execution.update({"chunk_id": chunk_id, "chunk_rows": int(len(chunk)), "cost_credits": cost})
            output.update({"chunk_id": chunk_id, "chunk_rows": int(len(chunk)), "resumed": False})
            frames[label].append(df)
            executions[label].append(execution)
            chunk_outputs[label].append(output)
            summary.update(
                {
                    "status": "partial_chunked_dune_indexer_exports",
                    "chunk_size": int(chunk_size),
                    "chunks_total": int(len(chunks)),
                    "chunks_completed": int(chunk_id + 1),
                    "performance": performance,
                    "estimated_total_execution_cost_credits": total_cost,
                    "executions": executions,
                    "chunk_outputs": chunk_outputs,
                }
            )
            write_json(config_tables_dir / "dune_indexer_export_summary.json", summary)
            if max_total_credits is not None and total_cost > max_total_credits:
                stop_reason = (
                    f"Stopped after {total_cost:.2f} Dune credits, above "
                    f"--max-total-credits {max_total_credits:.2f}; completed chunks are retained."
                )
                print(stop_reason, flush=True)
                break

    final_outputs: dict[str, dict[str, Any]] = {}
    for label, final_filename, required_columns in specs:
        combined = pd.concat(frames[label], ignore_index=True) if frames[label] else pd.DataFrame()
        sort_cols = [col for col in ["mint", "horizon_days", "launch_or_graduated_at", "graduated_at"] if col in combined]
        if sort_cols:
            combined = combined.sort_values(sort_cols).reset_index(drop=True)
        final_path = out_dir / final_filename
        write_csv(final_path, combined)
        final_outputs[label] = validate_schema(combined, required_columns, label=label)
        final_outputs[label]["path"] = str(final_path)

    summary.update(
        {
            "status": (
                "stopped_chunked_dune_indexer_exports_partial"
                if stop_reason
                else "computed_dune_indexer_exports"
                if only == "both"
                else "computed_dune_indexer_exports_partial"
            ),
            "chunked": True,
            "chunk_size": int(chunk_size),
            "chunks_total": int(len(chunks)),
            "chunks_completed": max((len(items) for items in chunk_outputs.values()), default=0),
            "performance": performance,
            "estimated_total_execution_cost_credits": total_cost,
            "stop_reason": stop_reason,
            "executions": executions,
            "chunk_outputs": chunk_outputs,
            "outputs": final_outputs,
        }
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs" / "pumpswap_case.json"))
    parser.add_argument("--max-tokens", type=int, default=0, help="0 means all graduated tokens.")
    parser.add_argument("--sample-strategy", choices=["first", "evenly_spaced"], default="evenly_spaced")
    parser.add_argument("--early-window-seconds", type=int, default=60)
    parser.add_argument("--execute", action="store_true", help="Submit rendered SQL to Dune. Consumes Dune API credits.")
    parser.add_argument("--api-key-env", default="DUNE_API_KEY")
    parser.add_argument("--performance", choices=["small", "medium", "large"], default="medium")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-minutes", type=float, default=120.0)
    parser.add_argument("--request-timeout", type=float, default=60.0)
    parser.add_argument("--allow-partial-results", action="store_true")
    parser.add_argument("--only", choices=["both", "post_migration", "early_wallets"], default="both")
    parser.add_argument("--chunk-size", type=int, default=0, help="Sequential token chunk size for Dune execution; 0 runs one SQL per export.")
    parser.add_argument("--resume", action="store_true", help="Reuse existing per-chunk CSVs when --chunk-size is set.")
    parser.add_argument("--max-total-credits", type=float, default=None, help="Stop chunked execution after this many observed credits.")
    args = parser.parse_args()

    config = load_config(args.config)
    out_dir = config.output_root / "external_validation"
    sql_dir = out_dir / "dune_sql"
    all_graduated = pd.read_csv(config.source_path("red_pump_graduated_for_dune"))
    graduated = sample_graduated_tokens(
        all_graduated,
        max_tokens=args.max_tokens,
        strategy=args.sample_strategy,
    )

    write_graduated_manifest(graduated, out_dir / "dune_graduated_tokens.csv")
    write_sql_inputs(graduated, sql_dir / "graduated_token_inputs.csv")

    post_sql = render_post_migration_sql(graduated)
    early_sql = render_early_wallet_sql(graduated, early_window_seconds=args.early_window_seconds)
    post_sql_path = sql_dir / "rendered_pumpswap_post_migration_trades.sql"
    early_sql_path = sql_dir / "rendered_pumpswap_early_wallets.sql"
    post_sql_path.write_text(post_sql, encoding="utf-8")
    early_sql_path.write_text(early_sql, encoding="utf-8")

    summary: dict[str, Any] = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "rendered_sql_only",
        "all_graduated_tokens_available": int(len(all_graduated)),
        "tokens_in_query": int(len(graduated)),
        "sample_strategy": args.sample_strategy,
        "early_window_seconds": int(args.early_window_seconds),
        "post_sql_path": str(post_sql_path),
        "early_sql_path": str(early_sql_path),
        "api_key_env": args.api_key_env,
        "api_key_found": bool(os.environ.get(args.api_key_env)),
        "dune_api_note": (
            "Set DUNE_API_KEY and rerun with --execute to submit SQL via Dune's "
            "/api/v1/sql/execute endpoint, poll execution status, and download CSV results."
        ),
    }

    api_key = os.environ.get(args.api_key_env)
    if args.execute:
        if not api_key:
            summary["status"] = "blocked_missing_dune_api_key"
            write_json(config.tables_dir / "dune_indexer_export_summary.json", summary)
            raise SystemExit(f"Missing {args.api_key_env}; rendered SQL but did not execute.")

        if args.chunk_size > 0:
            summary = run_chunked_exports(
                graduated=graduated,
                config_tables_dir=config.tables_dir,
                out_dir=out_dir,
                sql_dir=sql_dir,
                summary=summary,
                api_key=api_key,
                only=args.only,
                chunk_size=args.chunk_size,
                resume=args.resume,
                max_total_credits=args.max_total_credits,
                performance=args.performance,
                poll_seconds=args.poll_seconds,
                timeout_minutes=args.timeout_minutes,
                request_timeout=args.request_timeout,
                allow_partial_results=args.allow_partial_results,
                early_window_seconds=args.early_window_seconds,
            )
        else:
            executions: dict[str, dict[str, Any]] = {}
            outputs: dict[str, dict[str, Any]] = {}
            export_sql = {
                "post_migration": post_sql,
                "early_wallets": early_sql,
            }
            for label, final_filename, required in selected_export_specs(args.only):
                df, execution, output = execute_one_export(
                    label=label,
                    sql=export_sql[label],
                    output_path=out_dir / final_filename,
                    required_columns=required,
                    api_key=api_key,
                    performance=args.performance,
                    poll_seconds=args.poll_seconds,
                    timeout_minutes=args.timeout_minutes,
                    request_timeout=args.request_timeout,
                    allow_partial_results=args.allow_partial_results,
                )
                executions[label] = execution
                outputs[label] = output

            summary.update(
                {
                    "status": "computed_dune_indexer_exports" if args.only == "both" else "computed_dune_indexer_exports_partial",
                    "performance": args.performance,
                    "estimated_total_execution_cost_credits": sum(
                        execution_cost(item["status"]) for item in executions.values()
                    ),
                    "executions": executions,
                    "outputs": outputs,
                }
            )

    write_json(config.tables_dir / "dune_indexer_export_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
