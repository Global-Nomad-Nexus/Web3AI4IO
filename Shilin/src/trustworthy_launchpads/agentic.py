"""Agentic execution scaffold and scoring for Shilin's benchmark arm."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

from .io import CaseConfig, write_csv, write_json


RUN_SCHEMA = {
    "case_id": "string",
    "rung": "string in L0..L7",
    "model": "model name and version",
    "provider": "provider name",
    "run_id": "integer",
    "run_date_utc": "ISO date",
    "temperature": "float",
    "prompt_hash": "sha256 hex digest",
    "data_access": "semicolon-separated list",
    "tools_allowed": "semicolon-separated list",
    "headline_estimate": "float or blank",
    "ci95_low": "float or blank",
    "ci95_high": "float or blank",
    "worked_decision": "yes/no/no_or_uncertain/depends_on_stakeholder",
    "self_reported_confidence": "float from 0 to 1",
    "mentions_control_group": "0/1",
    "mentions_pretrend": "0/1",
    "mentions_stakeholders": "0/1",
    "mentions_uncertainty": "0/1",
    "final_claim": "short text",
    "raw_response_path": "path to verbatim response",
}


ABLATION_RUN_SCHEMA = {
    **RUN_SCHEMA,
    "ablation_id": "baseline or leave-one-scaffold-out condition",
    "ablation_family": "baseline/scaffold_removed",
    "removed_scaffold": "registered scaffold removed from prompt/data bundle",
    "model_spec_id": "stable provider/model/endpoint key from the run manifest",
    "execution_status": "ok/error/skipped",
    "error": "short error string when execution failed",
}


ABLATION_CONDITIONS = {
    "baseline": {
        "family": "baseline",
        "removed_scaffold": "",
        "description": "Registered L0-L7 prompt and artifact bundle.",
    },
    "omit_pretrend_diagnostics": {
        "family": "scaffold_removed",
        "removed_scaffold": "pretrend_event_study_guardrail",
        "description": "Remove explicit pretrend/event-study diagnostic scaffolding where present.",
    },
    "omit_uncertainty_inference": {
        "family": "scaffold_removed",
        "removed_scaffold": "few_cluster_uncertainty_guardrail",
        "description": "Remove explicit confidence-interval, p-value, and bootstrap guardrail language where present.",
    },
    "omit_stakeholder_battery": {
        "family": "scaffold_removed",
        "removed_scaffold": "stakeholder_specific_metric_battery",
        "description": "Remove stakeholder and retail-risk scaffold evidence where present.",
    },
    "omit_data_gap_ledger": {
        "family": "scaffold_removed",
        "removed_scaffold": "data_availability_claim_boundary",
        "description": "Remove data-gap and claim-scope reminders where present.",
    },
}


RUNG_DESCRIPTIONS = {
    "L0": {
        "data": "market_daily_panel only",
        "scaffold": "No control-group instruction; ask for before-after conclusion.",
    },
    "L1": {
        "data": "market_daily_panel with control units",
        "scaffold": "Control group is disclosed; ask for naive DiD.",
    },
    "L2": {
        "data": "market_daily_panel",
        "scaffold": "Unit/date fixed effects are required.",
    },
    "L3": {
        "data": "market_daily_panel plus estimator note",
        "scaffold": "Modern DiD/event-study package documentation is disclosed where compatible.",
    },
    "L4": {
        "data": "market_daily_panel",
        "scaffold": "Pre-trend/event-study diagnostic instruction is mandatory.",
    },
    "L5": {
        "data": "market panel plus RED-PUMP token outcomes and HF Pump.fun risk snapshots",
        "scaffold": "Heterogeneity by token lifecycle, social metadata, holder concentration, and source-coded risk is required.",
    },
    "L6": {
        "data": "market panel plus inference outputs",
        "scaffold": "Few-cluster uncertainty/wild bootstrap instruction is mandatory.",
    },
    "L7": {
        "data": "all computed tables plus data-availability ledger and Moralis decoded outcome sample when present",
        "scaffold": "Stakeholder metric battery is mandatory; conclusion must be stakeholder-specific.",
    },
}


def prompt_hash(system_prompt: str, user_prompt: str) -> str:
    payload = (system_prompt + "\n---USER---\n" + user_prompt).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_prompt_templates(config: CaseConfig) -> pd.DataFrame:
    prompt_dir = config.project_root / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for rung, meta in RUNG_DESCRIPTIONS.items():
        system = (
            "You are an empirical research agent being evaluated, not a coauthor. "
            "You must state the exact estimand, data used, uncertainty, and limitations. "
            "Do not infer causality from a before-after comparison unless the rung scaffold permits it. "
            "Return a JSON object matching the registered schema."
        )
        user = (
            f"Case: Pump.fun to PumpSwap migration, event date {config.raw['event_date']} UTC.\n"
            f"Rung: {rung}.\n"
            f"Data access: {meta['data']}.\n"
            f"Scaffold: {meta['scaffold']}\n"
            "Question: Did the PumpSwap regime work? Report the headline estimate, confidence interval, "
            "worked_decision, self_reported_confidence, and a short final_claim. "
            "If the data do not identify a stakeholder outcome, mark it as pending rather than fabricating it."
        )
        system_path = prompt_dir / f"{rung}_system.md"
        user_path = prompt_dir / f"{rung}_user.md"
        system_path.write_text(system + "\n", encoding="utf-8")
        user_path.write_text(user + "\n", encoding="utf-8")
        rows.append(
            {
                "rung": rung,
                "system_prompt_path": str(system_path.relative_to(config.project_root)),
                "user_prompt_path": str(user_path.relative_to(config.project_root)),
                "prompt_hash": prompt_hash(system, user),
                "data_access": meta["data"],
                "scaffold": meta["scaffold"],
            }
        )
    manifest = pd.DataFrame(rows)
    write_csv(config.tables_dir / "agentic_prompt_manifest.csv", manifest)
    write_json(config.agent_runs_dir / "agent_run_schema.json", RUN_SCHEMA)
    write_json(config.agent_runs_dir / "agentic_ablation_run_schema.json", ABLATION_RUN_SCHEMA)
    return manifest


def write_agentic_ablation_manifest(config: CaseConfig) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for rung, rung_meta in RUNG_DESCRIPTIONS.items():
        for ablation_id, ablation_meta in ABLATION_CONDITIONS.items():
            rows.append(
                {
                    "rung": rung,
                    "ablation_id": ablation_id,
                    "ablation_family": ablation_meta["family"],
                    "removed_scaffold": ablation_meta["removed_scaffold"],
                    "rung_data_access": rung_meta["data"],
                    "registered_scaffold": rung_meta["scaffold"],
                    "ablation_description": ablation_meta["description"],
                    "claim_boundary": (
                        "Registered scaffold ablation cell. It becomes empirical only after "
                        "agentic_multimodel_ablation_runs.csv contains real model outputs."
                    ),
                }
            )
    out = pd.DataFrame(rows)
    write_csv(config.tables_dir / "agentic_multimodel_ablation_manifest.csv", out)
    write_json(config.agent_runs_dir / "agentic_ablation_run_schema.json", ABLATION_RUN_SCHEMA)
    return out


def score_agent_runs(config: CaseConfig, deterministic: pd.DataFrame) -> pd.DataFrame:
    """Score actual agent runs if present; otherwise write an honest status row."""

    path = config.agent_runs_dir / "agent_runs.csv"
    if not path.exists():
        rows = [
            {
                "rung": rung,
                "runs": 0,
                "agent_mean_decision": "not_run",
                "sign_stability": np.nan,
                "calibration_gap": np.nan,
                "run_to_run_dispersion": np.nan,
                "method_omission_rate": np.nan,
                "status": "registered_prompts_only",
                "notes": "No model outputs are reported. Run agent_runs.csv with the registered schema to populate this table.",
            }
            for rung in RUNG_DESCRIPTIONS
        ]
        out = pd.DataFrame(rows)
        write_csv(config.tables_dir / "agentic_arm_scores.csv", out)
        return out

    runs = pd.read_csv(path)
    required = set(RUN_SCHEMA)
    missing = sorted(required.difference(runs.columns))
    if missing:
        raise ValueError(f"agent_runs.csv is missing registered columns: {missing}")

    score_rows: list[dict[str, object]] = []
    for rung, group in runs.groupby("rung"):
        estimates = pd.to_numeric(group["headline_estimate"], errors="coerce")
        decisions = group["worked_decision"].astype(str)
        modal = decisions.mode().iloc[0] if len(decisions.mode()) else "missing"
        sign = np.sign(estimates.dropna())
        sign_stability = float(sign.value_counts(normalize=True).max()) if len(sign) else np.nan
        dispersion = float(estimates.std(ddof=1)) if estimates.notna().sum() > 1 else np.nan
        omissions = 1 - group[["mentions_control_group", "mentions_pretrend", "mentions_stakeholders", "mentions_uncertainty"]].mean(axis=1)
        confidence = pd.to_numeric(group["self_reported_confidence"], errors="coerce")
        deterministic_row = deterministic.loc[deterministic["rung"].eq(rung)]
        coverage_proxy = np.nan
        if len(deterministic_row) and estimates.notna().any():
            ref_low = float(deterministic_row.iloc[0]["ci95_low"])
            ref_high = float(deterministic_row.iloc[0]["ci95_high"])
            coverage_proxy = float(((estimates >= ref_low) & (estimates <= ref_high)).mean())
        calibration_gap = float(confidence.mean() - coverage_proxy) if not pd.isna(coverage_proxy) else np.nan
        score_rows.append(
            {
                "rung": rung,
                "runs": int(len(group)),
                "agent_mean_decision": modal,
                "sign_stability": sign_stability,
                "calibration_gap": calibration_gap,
                "run_to_run_dispersion": dispersion,
                "method_omission_rate": float(omissions.mean()),
                "status": "scored",
                "notes": "Scored against deterministic rung output where compatible.",
            }
        )
    out = pd.DataFrame(score_rows).sort_values("rung")
    write_csv(config.tables_dir / "agentic_arm_scores.csv", out)
    return out


def score_agentic_ablation_runs(config: CaseConfig) -> pd.DataFrame:
    """Score multi-model scaffold ablation runs when present."""

    manifest_path = config.tables_dir / "agentic_multimodel_ablation_manifest.csv"
    if not manifest_path.exists():
        write_agentic_ablation_manifest(config)
    path = config.agent_runs_dir / "agentic_multimodel_ablation_runs.csv"
    if not path.exists() or path.stat().st_size == 0:
        manifest = pd.read_csv(manifest_path)
        out = manifest.loc[:, ["rung", "ablation_id", "ablation_family", "removed_scaffold"]].copy()
        out.insert(0, "provider", "")
        out.insert(1, "model", "")
        out["runs"] = 0
        out["ok_runs"] = 0
        out["error_rate"] = np.nan
        out["agent_mean_decision"] = "not_run"
        out["sign_stability"] = np.nan
        out["run_to_run_dispersion"] = np.nan
        out["method_omission_rate"] = np.nan
        out["mean_confidence"] = np.nan
        out["status"] = "registered_ablation_manifest_only"
        out["claim_boundary"] = "No multi-model ablation outputs are reported yet."
        write_csv(config.tables_dir / "agentic_multimodel_ablation_scores.csv", out)
        return out

    runs = pd.read_csv(path)
    required = set(ABLATION_RUN_SCHEMA)
    missing = sorted(required.difference(runs.columns))
    if missing:
        raise ValueError(f"agentic_multimodel_ablation_runs.csv is missing registered columns: {missing}")

    rows: list[dict[str, object]] = []
    flags = ["mentions_control_group", "mentions_pretrend", "mentions_stakeholders", "mentions_uncertainty"]
    for (provider, model, rung, ablation_id), group in runs.groupby(["provider", "model", "rung", "ablation_id"]):
        ok = group.loc[group["execution_status"].astype(str).eq("ok")].copy()
        score_group = ok if not ok.empty else group
        estimates = pd.to_numeric(score_group["headline_estimate"], errors="coerce")
        decisions = score_group["worked_decision"].astype(str)
        modal = decisions.mode().iloc[0] if len(decisions.mode()) else "missing"
        sign = np.sign(estimates.dropna())
        sign_stability = float(sign.value_counts(normalize=True).max()) if len(sign) else np.nan
        dispersion = float(estimates.std(ddof=1)) if estimates.notna().sum() > 1 else np.nan
        omissions = 1 - score_group[flags].apply(pd.to_numeric, errors="coerce").fillna(0).mean(axis=1)
        confidence = pd.to_numeric(score_group["self_reported_confidence"], errors="coerce")
        ablation_family = str(score_group["ablation_family"].iloc[0]) if "ablation_family" in score_group else ""
        removed_scaffold = str(score_group["removed_scaffold"].iloc[0]) if "removed_scaffold" in score_group else ""
        rows.append(
            {
                "provider": provider,
                "model": model,
                "rung": rung,
                "ablation_id": ablation_id,
                "ablation_family": ablation_family,
                "removed_scaffold": removed_scaffold,
                "runs": int(len(group)),
                "ok_runs": int(len(ok)),
                "error_rate": float(1 - (len(ok) / len(group))) if len(group) else np.nan,
                "agent_mean_decision": modal,
                "sign_stability": sign_stability,
                "run_to_run_dispersion": dispersion,
                "method_omission_rate": float(omissions.mean()) if len(omissions) else np.nan,
                "mean_confidence": float(confidence.mean()) if confidence.notna().any() else np.nan,
                "status": "scored" if len(ok) else "all_runs_failed",
                "claim_boundary": "Ablation output evaluates prompt-scaffold sensitivity, not causal treatment effects.",
            }
        )
    out = pd.DataFrame(rows).sort_values(["provider", "model", "rung", "ablation_id"])
    write_csv(config.tables_dir / "agentic_multimodel_ablation_scores.csv", out)
    return out
