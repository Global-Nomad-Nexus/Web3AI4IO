#!/usr/bin/env python3
"""Evaluate whether public Telegram shocks support a causal exposure design.

The current RED-PUMP mirror case has strong matched association but no causal
assignment. This script registers public Telegram outage/linking shocks, checks
whether they overlap the RED-PUMP launch window, and runs a local
difference-in-differences exposure design only for shocks with enough in-window
tokens on both sides.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from build_benchmark_release import ROOT, relpath, source_path, load_config
from run_telegram_mirror_design import SOCIAL_COLUMNS, add_design_features, write_csv, write_json


TABLES = ROOT / "artifacts" / "tables"
EXTERNAL = ROOT / "artifacts" / "external_validation"
EVENT_ID = "PUMP_PUMPSWAP_MIGRATION_20250320"
DESIGN_ID = "TELEGRAM_EXOGENOUS_EXPOSURE_DESIGN_V1"
SHOCK_COLUMNS = [
    "shock_id",
    "shock_type",
    "shock_start_utc",
    "shock_end_utc",
    "expected_direction",
    "source_name",
    "source_url",
    "source_claim",
    "source_tier",
]
DESIGN_COLUMNS = [
    "design_id",
    "shock_id",
    "stage",
    "estimand",
    "outcome",
    "analysis_window_hours",
    "n_telegram_during",
    "n_telegram_adjacent",
    "n_no_telegram_during",
    "n_no_telegram_adjacent",
    "telegram_during_rate",
    "telegram_adjacent_rate",
    "no_telegram_during_rate",
    "no_telegram_adjacent_rate",
    "effect",
    "decision",
    "claim_boundary",
    "source_artifact",
]


def public_candidate_shocks() -> pd.DataFrame:
    rows = [
        {
            "shock_id": "STATUSGATOR_TELEGRAM_APP_WEBSITE_20260616",
            "shock_type": "third_party_detected_service_outage",
            "shock_start_utc": "2026-06-16T07:30:00Z",
            "shock_end_utc": "2026-06-17T20:52:00Z",
            "expected_direction": "negative_attention_access_shock",
            "source_name": "StatusGator Telegram status history",
            "source_url": "https://statusgator.com/services/telegram",
            "source_claim": "Connection issues affecting app and website; third-party detected and not officially acknowledged.",
            "source_tier": "third_party_monitor",
        },
        {
            "shock_id": "STATUSGATOR_TELEGRAM_SERVICE_20260619",
            "shock_type": "third_party_detected_service_outage",
            "shock_start_utc": "2026-06-19T10:58:00Z",
            "shock_end_utc": "2026-06-19T15:00:00Z",
            "expected_direction": "negative_attention_access_shock",
            "source_name": "StatusGator Telegram status history",
            "source_url": "https://statusgator.com/services/telegram",
            "source_claim": "Service outage; third-party detected and not officially acknowledged.",
            "source_tier": "third_party_monitor",
        },
        {
            "shock_id": "STATUSGATOR_TELEGRAM_LOGIN_20260621",
            "shock_type": "third_party_detected_login_issue",
            "shock_start_utc": "2026-06-21T18:46:00Z",
            "shock_end_utc": "2026-06-21T20:19:00Z",
            "expected_direction": "negative_attention_access_shock",
            "source_name": "StatusGator Telegram status history",
            "source_url": "https://statusgator.com/services/telegram",
            "source_claim": "Connection issues affecting login and authentication; third-party detected.",
            "source_tier": "third_party_monitor",
        },
        {
            "shock_id": "STATUSGATOR_TELEGRAM_SERVICE_20260622",
            "shock_type": "third_party_detected_service_outage",
            "shock_start_utc": "2026-06-22T06:50:00Z",
            "shock_end_utc": "2026-06-22T15:39:00Z",
            "expected_direction": "negative_attention_access_shock",
            "source_name": "StatusGator Telegram status history",
            "source_url": "https://statusgator.com/services/telegram",
            "source_claim": "Telegram service unavailable; third-party detected.",
            "source_tier": "third_party_monitor",
        },
        {
            "shock_id": "TELEGRAM_TME_SHORTLINK_DOMAIN_20260713",
            "shock_type": "global_shortlink_domain_outage",
            "shock_start_utc": "2026-07-13T00:00:00Z",
            "shock_end_utc": "2026-07-14T14:10:00Z",
            "expected_direction": "negative_group_join_link_shock",
            "source_name": "TechCrunch",
            "source_url": "https://techcrunch.com/2026/07/14/telegrams-shortlink-domain-is-back-online-after-day-long-suspension/",
            "source_claim": "Telegram t.me shortlinks stopped working and were restored the next day.",
            "source_tier": "news_with_first_party_attribution",
        },
        {
            "shock_id": "TELEGRAM_APPSTORE_TEMP_REMOVAL_20260803",
            "shock_type": "app_store_search_or_listing_disruption",
            "shock_start_utc": "2026-08-04T02:19:00Z",
            "shock_end_utc": "2026-08-04T02:45:00Z",
            "expected_direction": "negative_new_user_install_shock",
            "source_name": "9to5Mac",
            "source_url": "https://9to5mac.com/2026/08/03/telegram-appears-to-have-been-pulled-from-the-app-store-worldwide/",
            "source_claim": "Telegram temporarily disappeared from App Store search and was later restored.",
            "source_tier": "news_with_first_party_attribution",
        },
    ]
    return pd.DataFrame(rows).reindex(columns=SHOCK_COLUMNS)


def read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def load_or_create_shocks(path: Path, *, refresh: bool) -> pd.DataFrame:
    if refresh or not path.exists() or path.stat().st_size == 0:
        shocks = public_candidate_shocks()
        write_csv(path, shocks)
        return shocks
    return read_csv(path)


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def summarize_overlap(tokens: pd.DataFrame, shocks: pd.DataFrame, *, window_hours: int, min_tokens: int) -> pd.DataFrame:
    created = _to_utc(tokens["created_at"])
    token_min = created.min()
    token_max = created.max()
    rows: list[dict[str, Any]] = []
    for _, shock in shocks.iterrows():
        start = pd.to_datetime(shock["shock_start_utc"], utc=True, errors="coerce")
        end = pd.to_datetime(shock["shock_end_utc"], utc=True, errors="coerce")
        if pd.isna(start) or pd.isna(end):
            continue
        pre_start = start - pd.Timedelta(hours=window_hours)
        post_end = end + pd.Timedelta(hours=window_hours)
        in_analysis_window = created.between(pre_start, post_end, inclusive="both")
        during = created.between(start, end, inclusive="both")
        adjacent = in_analysis_window & ~during
        telegram = tokens["has_telegram"].eq(1)
        support_cells = {
            "during_telegram": int((during & telegram).sum()),
            "during_no_telegram": int((during & ~telegram).sum()),
            "adjacent_telegram": int((adjacent & telegram).sum()),
            "adjacent_no_telegram": int((adjacent & ~telegram).sum()),
        }
        supported = all(value >= min_tokens for value in support_cells.values())
        overlaps_sample_window = bool(end >= token_min and start <= token_max)
        rows.append(
            {
                **shock.to_dict(),
                "red_pump_min_created_at": token_min.strftime("%Y-%m-%dT%H:%M:%SZ") if pd.notna(token_min) else "",
                "red_pump_max_created_at": token_max.strftime("%Y-%m-%dT%H:%M:%SZ") if pd.notna(token_max) else "",
                "overlaps_red_pump_window": overlaps_sample_window,
                "analysis_window_hours": window_hours,
                **support_cells,
                "supported_for_exposure_design": bool(supported and overlaps_sample_window),
                "support_status": "supported" if supported and overlaps_sample_window else "outside_sample_or_underpowered",
                "claim_boundary": (
                    "Use only if the shock overlaps RED-PUMP launch timestamps and has Telegram and non-Telegram tokens "
                    "inside both shock and adjacent windows."
                ),
            }
        )
    return pd.DataFrame(rows)


def did_rows(tokens: pd.DataFrame, overlap: pd.DataFrame) -> pd.DataFrame:
    created = _to_utc(tokens["created_at"])
    rows: list[dict[str, Any]] = []
    for _, shock in overlap.loc[overlap["supported_for_exposure_design"].eq(True)].iterrows():
        start = pd.to_datetime(shock["shock_start_utc"], utc=True, errors="coerce")
        end = pd.to_datetime(shock["shock_end_utc"], utc=True, errors="coerce")
        window_hours = int(shock["analysis_window_hours"])
        pre_start = start - pd.Timedelta(hours=window_hours)
        post_end = end + pd.Timedelta(hours=window_hours)
        in_window = created.between(pre_start, post_end, inclusive="both")
        during = created.between(start, end, inclusive="both")
        frame = tokens.loc[in_window].copy()
        frame["during_shock"] = during.loc[in_window].astype(int).to_numpy()
        frame["telegram"] = frame["has_telegram"].astype(int)
        frame["graduated"] = frame["graduated"].astype(int)
        grouped = frame.groupby(["telegram", "during_shock"], dropna=False)["graduated"].agg(["mean", "count"]).reset_index()
        needed = {(0, 0), (0, 1), (1, 0), (1, 1)}
        available = {(int(r.telegram), int(r.during_shock)) for r in grouped.itertuples()}
        if not needed.issubset(available):
            continue
        values = {(int(r.telegram), int(r.during_shock)): float(r.mean) for r in grouped.itertuples()}
        counts = {(int(r.telegram), int(r.during_shock)): int(r.count) for r in grouped.itertuples()}
        did = (values[(1, 1)] - values[(1, 0)]) - (values[(0, 1)] - values[(0, 0)])
        rows.append(
            {
                "design_id": DESIGN_ID,
                "shock_id": shock["shock_id"],
                "stage": "E1_exogenous_shock_did",
                "estimand": "Difference-in-differences for Telegram-present tokens during public Telegram shock windows",
                "outcome": "graduated",
                "analysis_window_hours": window_hours,
                "n_telegram_during": counts[(1, 1)],
                "n_telegram_adjacent": counts[(1, 0)],
                "n_no_telegram_during": counts[(0, 1)],
                "n_no_telegram_adjacent": counts[(0, 0)],
                "telegram_during_rate": values[(1, 1)],
                "telegram_adjacent_rate": values[(1, 0)],
                "no_telegram_during_rate": values[(0, 1)],
                "no_telegram_adjacent_rate": values[(0, 0)],
                "effect": did,
                "decision": "causal_candidate_if_shock_as_if_random",
                "claim_boundary": (
                    "This can support a causal-candidate exposure design only if the shock timing is exogenous to token launches "
                    "and no concurrent crypto-market shock drives the same window."
                ),
                "source_artifact": "artifacts/external_validation/telegram_shock_candidates.csv",
            }
        )
    return pd.DataFrame(rows).reindex(columns=DESIGN_COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shock-candidates", default=str(EXTERNAL / "telegram_shock_candidates.csv"))
    parser.add_argument("--refresh-public-candidates", action="store_true")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--min-cell-tokens", type=int, default=50)
    args = parser.parse_args()

    config = load_config()
    red_path = source_path(config, "red_pump_token_outcomes")
    tokens = read_csv(red_path, usecols=lambda c: c in SOCIAL_COLUMNS, low_memory=False)
    if tokens.empty:
        raise RuntimeError(f"Missing RED-PUMP token outcomes: {red_path}")
    tokens = add_design_features(tokens)
    shock_path = Path(args.shock_candidates).expanduser().resolve()
    shocks = load_or_create_shocks(shock_path, refresh=args.refresh_public_candidates)
    overlap = summarize_overlap(tokens, shocks, window_hours=args.window_hours, min_tokens=args.min_cell_tokens)
    design = did_rows(tokens, overlap)
    supported_shocks = int(overlap["supported_for_exposure_design"].sum()) if not overlap.empty else 0
    summary = {
        "design_id": DESIGN_ID,
        "event_id": EVENT_ID,
        "status": "causal_exposure_design_available" if supported_shocks and not design.empty else "no_in_window_exogenous_shock_yet",
        "red_pump_source_artifact": relpath(red_path),
        "shock_source_artifact": relpath(shock_path),
        "red_pump_min_created_at": str(pd.to_datetime(tokens["created_at"], utc=True, errors="coerce").min()),
        "red_pump_max_created_at": str(pd.to_datetime(tokens["created_at"], utc=True, errors="coerce").max()),
        "candidate_shocks": int(len(overlap)),
        "supported_shocks": supported_shocks,
        "design_rows": int(len(design)),
        "claim_boundary": (
            "No causal Telegram effect should be claimed unless at least one public shock overlaps the RED-PUMP launch "
            "window with enough Telegram and non-Telegram tokens for an exposure design."
        ),
    }

    write_csv(EXTERNAL / "telegram_shock_candidates.csv", overlap)
    write_csv(TABLES / "telegram_exposure_design.csv", design)
    write_json(TABLES / "telegram_exposure_design_summary.json", summary)
    print(
        "Telegram exposure design written: "
        f"candidate_shocks={summary['candidate_shocks']} supported_shocks={supported_shocks} "
        f"status={summary['status']}"
    )


if __name__ == "__main__":
    main()
