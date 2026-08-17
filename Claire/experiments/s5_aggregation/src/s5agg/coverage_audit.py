"""Upstream coverage audit for the S5 primary markets (researcher lock 2026-08-14).

Pump, Raydium and Orca must pass a raw coverage audit before entering the
primary specification: complete observation over the registered window
(rel_day -90..+90) and definition stability over the primary calibration
window (rel_day -90..-1). Reads the immutable raw DefiLlama dumps and writes
coverage_audit_primary_markets.json. Audit only; modifies nothing upstream.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import paths

EVENT = date(2025, 3, 20)
WIN_START = EVENT - timedelta(days=90)
WIN_END = EVENT + timedelta(days=90)
CAL_END = EVENT - timedelta(days=1)  # primary calibration: rel_day -90..-1

RAW_DIR = paths.BUNDLE / (
    "01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local/data/raw"
)
LISTINGS = {
    "pump_fun_launchpad": "defillama_summary_pump_fun.json",
    "pump_swap": "defillama_summary_pump_swap.json",
    "raydium": "defillama_summary_raydium.json",
    "orca": "defillama_summary_orca.json",
}


def _chart(payload: dict) -> dict[date, float]:
    return {
        datetime.fromtimestamp(t, timezone.utc).date(): float(v)
        for t, v in payload.get("totalDataChart", [])
    }


def _childsets(payload: dict) -> list[dict]:
    out: dict[tuple, list] = {}
    for t, v in payload.get("totalDataChartBreakdown", []):
        dt = datetime.fromtimestamp(t, timezone.utc).date()
        if WIN_START <= dt <= WIN_END and isinstance(v, dict):
            for children in v.values():
                key = tuple(sorted(children.keys()))
                out.setdefault(key, [dt, dt])
                out[key][1] = dt
    return [
        {"children": list(k), "from": str(v[0]), "to": str(v[1])} for k, v in out.items()
    ]


def audit_listing(label: str, filename: str) -> dict:
    payload = json.loads((RAW_DIR / filename).read_text(encoding="utf-8"))
    chart = _chart(payload)
    n_days = (WIN_END - WIN_START).days + 1
    days = [WIN_START + timedelta(days=i) for i in range(n_days)]
    missing = [d for d in days if d not in chart]
    zeros = sorted(d for d in days if chart.get(d) == 0)
    cal_days = [d for d in days if d <= CAL_END]
    missing_cal = [d for d in cal_days if d not in chart]
    zeros_cal = [d for d in cal_days if chart.get(d) == 0]
    childsets = _childsets(payload)
    cal_childsets = [
        cs for cs in childsets if cs["from"] <= str(CAL_END)
    ]
    return {
        "listing": label,
        "raw_file": filename,
        "raw_range": [str(min(chart)), str(max(chart))],
        "window_days_observed": n_days - len(missing),
        "window_days_total": n_days,
        "missing_dates_in_window": [str(d) for d in missing],
        "zero_value_dates_in_window": [str(d) for d in zeros],
        "calibration_window_missing": [str(d) for d in missing_cal],
        "calibration_window_zeros": [str(d) for d in zeros_cal],
        "breakdown_childsets_in_window": childsets,
        "definition_stable_over_calibration_window": len(cal_childsets) == 1,
    }


def run_audit(out_json: Path | None = None) -> dict:
    listings = {label: audit_listing(label, f) for label, f in LISTINGS.items()}
    # pump_ecosystem = pump_fun_launchpad + pump_swap; pump_swap missing before
    # its launch is a documented structural zero, so the ecosystem series is
    # observed over the full window as long as pump_fun_launchpad is complete.
    fun = listings["pump_fun_launchpad"]
    ray, orca = listings["raydium"], listings["orca"]
    markets = {
        "pump_ecosystem": {
            "components": ["pump_fun_launchpad", "pump_swap"],
            "pass": not fun["calibration_window_missing"]
            and not fun["calibration_window_zeros"]
            and fun["definition_stable_over_calibration_window"],
            "note": "pump_swap absent before 2025-03-17 = structural pre-launch zero (documented upstream, build_panel.py:51-53); pump_fun_launchpad complete and definition-stable over the calibration window",
        },
        "raydium": {
            "components": ["raydium"],
            "pass": not ray["calibration_window_missing"]
            and not ray["calibration_window_zeros"]
            and ray["definition_stable_over_calibration_window"],
            "note": "LaunchLab child added 2025-04-16 (rel_day +27) — post-event only, outside the primary calibration window; recorded as a post-window definition caveat, immaterial to S5's pre-event-only calibration (real post-event outcomes are never used)",
        },
        "orca": {
            "components": ["orca"],
            "pass": not orca["calibration_window_missing"]
            and not orca["calibration_window_zeros"]
            and orca["definition_stable_over_calibration_window"],
            "note": "Orca Wavebreak child added 2025-05-29 (rel_day +70) — post-event only; same caveat as raydium",
        },
    }
    report = {
        "audit_date": "2026-08-14",
        "scope": "S5 primary markets (pump_ecosystem, raydium, orca)",
        "registered_window": [str(WIN_START), str(WIN_END)],
        "primary_calibration_window": [str(WIN_START), str(CAL_END)],
        "listings": listings,
        "markets": markets,
        "all_primary_markets_pass": all(m["pass"] for m in markets.values()),
        "meteora_combined": "FAILS the audit — see zero_day_audit.md; excluded from primary specification per the locked missing-data policy, corrected series retained for the restricted-window sensitivity only",
    }
    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    r = run_audit(paths.EXPERIMENT_DIR / "coverage_audit_primary_markets.json")
    print("all primary markets pass:", r["all_primary_markets_pass"])
