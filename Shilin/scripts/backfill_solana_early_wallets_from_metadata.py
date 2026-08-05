#!/usr/bin/env python3
"""Backfill Solana early-wallet concentration from existing Pump.fun metadata.

This avoids re-fetching Pump.fun coin metadata. It reads already collected
bonding-curve addresses and only calls Solana JSON-RPC for signatures and
parsed fee-payer proxies.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.io import load_config, write_csv, write_json

from run_solana_external_validation import (
    aggregate_early_wallets,
    fetch_signatures,
    is_limit_stop_message,
    parse_pool_transaction,
    parse_time,
    read_existing_rows,
    remove_mint_rows,
    resolve_rpc_url,
    sample_graduated_tokens,
    summarize_outputs,
)


def clean_address(value: Any) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    return text if len(text) >= 32 and text.lower() != "nan" else ""


def metadata_work(metadata: pd.DataFrame, *, max_tokens: int, strategy: str) -> pd.DataFrame:
    frame = metadata.copy()
    frame["early_address"] = frame.apply(
        lambda row: clean_address(row.get("bonding_curve")) or clean_address(row.get("associated_bonding_curve")),
        axis=1,
    )
    frame = frame.loc[
        frame.get("metadata_status", pd.Series(dtype=str)).astype(str).eq("ok")
        & frame["early_address"].astype(str).ne("")
    ].copy()
    if "created_at" not in frame:
        return pd.DataFrame()
    frame = frame.loc[frame["created_at"].astype(str).ne("")].copy()
    if strategy == "latest":
        frame = frame.sort_values("created_at")
    elif strategy == "first":
        frame = frame.sort_values("created_at")
    if max_tokens <= 0 or max_tokens >= len(frame):
        return frame.reset_index(drop=True)
    if strategy == "evenly_spaced":
        positions = sample_graduated_tokens(frame.reset_index(drop=True), max_tokens=max_tokens, strategy=strategy)
        return positions.drop(columns=["graduated_index"], errors="ignore").reset_index(drop=True)
    if strategy == "latest":
        return frame.tail(max_tokens).reset_index(drop=True)
    return frame.head(max_tokens).reset_index(drop=True)


def write_outputs(
    *,
    config,
    out_dir: Path,
    metadata: pd.DataFrame,
    post: pd.DataFrame,
    early_rows: list[dict[str, Any]],
    tx_rows: list[dict[str, Any]],
    tokens_requested: int,
    all_graduated_tokens: int,
    sample_strategy: str,
    rpc_provider: str,
    stop_reason: str,
) -> None:
    early = pd.DataFrame(early_rows)
    tx = pd.DataFrame(tx_rows)
    decoded_role = tx.get("decoded_wallet_role", pd.Series(dtype=str)).astype(str).str.lower()
    classified_tx = (
        tx.loc[
            tx.get("phase", pd.Series(dtype=str)).astype(str).eq("early_bonding_curve")
            & ~decoded_role.isin(["", "nan", "none", "unclassified"])
        ]
        if len(tx)
        else pd.DataFrame()
    )
    write_csv(out_dir / "solana_early_wallet_concentration.csv", early)
    write_csv(out_dir / "solana_parsed_transaction_proxies.csv", tx)
    summary = summarize_outputs(
        metadata,
        post,
        early,
        tokens_requested=tokens_requested,
        all_graduated_tokens=all_graduated_tokens,
        sample_strategy=sample_strategy,
        rpc_provider=rpc_provider,
        stop_reason=stop_reason,
    )
    summary["early_wallet_backfill_source"] = "existing_pumpfun_coin_metadata"
    write_json(config.tables_dir / "external_validation_summary.json", summary)
    write_json(
        config.tables_dir / "solana_early_wallet_backfill_summary.json",
        {
            "tokens_requested": int(tokens_requested),
            "early_wallet_rows": int(len(early)),
            "early_wallet_tokens": int(early["mint"].nunique()) if len(early) and "mint" in early else 0,
            "parsed_early_transactions": int(
                tx.loc[tx.get("phase", pd.Series(dtype=str)).astype(str).eq("early_bonding_curve")].shape[0]
            )
            if len(tx)
            else 0,
            "classified_early_transactions": int(len(classified_tx)),
            "decoded_buyer_proxy_wallets": int(
                pd.to_numeric(early.get("decoded_buyer_proxy_wallets", pd.Series(dtype=float)), errors="coerce")
                .fillna(0)
                .sum()
            )
            if len(early)
            else 0,
            "decoded_holder_proxy_wallets": int(
                pd.to_numeric(early.get("decoded_holder_proxy_wallets", pd.Series(dtype=float)), errors="coerce")
                .fillna(0)
                .sum()
            )
            if len(early)
            else 0,
            "rpc_provider": rpc_provider,
            "sample_strategy": sample_strategy,
            "stop_reason": stop_reason,
            "claim_boundary": (
                "Early-wallet rows are fee-payer and token-balance proxy classifications from Solana JSON-RPC; "
                "same-cohort causal H4 still requires complete decoded indexer buyer/holder coverage."
            ),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs" / "pumpswap_case.json"))
    parser.add_argument("--rpc-url", default=None)
    parser.add_argument("--max-tokens", type=int, default=50)
    parser.add_argument("--sample-strategy", choices=["first", "evenly_spaced", "latest"], default="evenly_spaced")
    parser.add_argument("--early-window-seconds", type=int, default=60)
    parser.add_argument("--page-limit", type=int, default=200)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--tx-limit-per-token", type=int, default=80)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--checkpoint-every", type=int, default=5)
    parser.add_argument("--stop-after-seconds", type=int, default=0, help="0 means no wall-clock stop.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--summary-only", action="store_true", help="Refresh summaries from existing early-wallet rows.")
    args = parser.parse_args()

    config = load_config(args.config)
    rpc_url, rpc_provider = resolve_rpc_url(args.rpc_url)
    out_dir = config.output_root / "external_validation"
    metadata_path = out_dir / "pumpfun_coin_metadata.csv"
    if not metadata_path.exists():
        raise SystemExit(f"Missing existing metadata table: {metadata_path}")
    metadata = pd.read_csv(metadata_path, low_memory=False)
    post = pd.read_csv(out_dir / "solana_post_migration_pool_windows.csv", low_memory=False)
    all_graduated = pd.read_csv(config.source_path("red_pump_graduated_for_dune"))
    if args.summary_only:
        early_rows = read_existing_rows(out_dir / "solana_early_wallet_concentration.csv")
        tx_rows = read_existing_rows(out_dir / "solana_parsed_transaction_proxies.csv")
        write_outputs(
            config=config,
            out_dir=out_dir,
            metadata=metadata,
            post=post,
            early_rows=early_rows,
            tx_rows=tx_rows,
            tokens_requested=len(early_rows),
            all_graduated_tokens=len(all_graduated),
            sample_strategy=args.sample_strategy,
            rpc_provider=rpc_provider,
            stop_reason="summary_only",
        )
        print("Early-wallet summaries refreshed from existing rows.", flush=True)
        return
    work = metadata_work(metadata, max_tokens=args.max_tokens, strategy=args.sample_strategy)
    if work.empty:
        raise SystemExit("No metadata rows with bonding-curve addresses are available.")

    early_rows = read_existing_rows(out_dir / "solana_early_wallet_concentration.csv") if args.resume else []
    tx_rows = read_existing_rows(out_dir / "solana_parsed_transaction_proxies.csv") if args.resume else []
    completed = {str(row.get("mint")) for row in early_rows if row.get("mint")} if args.resume else set()
    stop_reason = ""
    started = time.time()
    print(f"Starting early-wallet backfill: tokens={len(work)}, rpc_provider={rpc_provider}", flush=True)
    for index, row in work.iterrows():
        if args.stop_after_seconds and time.time() - started >= args.stop_after_seconds:
            stop_reason = f"stopped_after_{args.stop_after_seconds}s"
            print(f"Stopping early-wallet backfill after {args.stop_after_seconds}s.", flush=True)
            break
        mint = str(row["mint"])
        if args.resume and mint in completed and not args.refresh_existing:
            print(f"{index + 1}/{len(work)} {mint}: skipped_existing", flush=True)
            continue
        if args.refresh_existing:
            early_rows = remove_mint_rows(early_rows, mint)
            tx_rows = remove_mint_rows(tx_rows, mint, phases={"early_bonding_curve"})
        created_at = parse_time(row.get("created_at"))
        early_address = clean_address(row.get("early_address"))
        if created_at is None or not early_address:
            continue
        print(f"{index + 1}/{len(work)} {mint}: fetching early signatures", flush=True)
        signatures, sig_status = fetch_signatures(
            early_address,
            rpc_url=rpc_url,
            start=created_at,
            end=created_at + timedelta(seconds=args.early_window_seconds),
            page_limit=args.page_limit,
            max_pages=args.max_pages,
            timeout=args.timeout,
            retries=args.retries,
            sleep=args.sleep,
        )
        print(f"{index + 1}/{len(work)} {mint}: early signatures={len(signatures)} status={sig_status}", flush=True)
        if is_limit_stop_message(sig_status):
            stop_reason = f"early_wallet_signatures:{sig_status}"
            break
        details: dict[str, dict[str, Any]] = {}
        successful = [sig for sig in signatures if sig.get("err") is None]
        for pos, sig in enumerate(successful[: max(args.tx_limit_per_token, 0)], start=1):
            detail = parse_pool_transaction(
                sig["signature"],
                mint,
                rpc_url=rpc_url,
                timeout=args.timeout,
                retries=args.retries,
                sleep=args.sleep,
            )
            details[sig["signature"]] = detail
            tx_rows.append({"mint": mint, "phase": "early_bonding_curve", **detail})
            if is_limit_stop_message(detail.get("parse_status", "")):
                stop_reason = f"early_wallet_transaction:{detail['parse_status']}"
                break
            if pos % 25 == 0 or pos == len(successful):
                print(f"{index + 1}/{len(work)} {mint}: parsed early tx {pos}/{len(successful)}", flush=True)
            time.sleep(args.sleep)
        early_rows.append(
            aggregate_early_wallets(
                mint=mint,
                created_at=created_at,
                early_address=early_address,
                signatures=signatures,
                tx_details=details,
                early_window_seconds=args.early_window_seconds,
                signature_status=sig_status,
            )
        )
        if args.checkpoint_every and (index + 1) % args.checkpoint_every == 0:
            write_outputs(
                config=config,
                out_dir=out_dir,
                metadata=metadata,
                post=post,
                early_rows=early_rows,
                tx_rows=tx_rows,
                tokens_requested=len(work),
                all_graduated_tokens=len(all_graduated),
                sample_strategy=args.sample_strategy,
                rpc_provider=rpc_provider,
                stop_reason=stop_reason,
            )
        if stop_reason:
            break
        time.sleep(args.sleep)
    write_outputs(
        config=config,
        out_dir=out_dir,
        metadata=metadata,
        post=post,
        early_rows=early_rows,
        tx_rows=tx_rows,
        tokens_requested=len(work),
        all_graduated_tokens=len(all_graduated),
        sample_strategy=args.sample_strategy,
        rpc_provider=rpc_provider,
        stop_reason=stop_reason,
    )
    print(f"Early-wallet backfill complete: rows={len(early_rows)} stop_reason={stop_reason}", flush=True)


if __name__ == "__main__":
    main()
