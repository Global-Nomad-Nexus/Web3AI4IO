#!/usr/bin/env python3
"""Lightweight verification for generated Shilin artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.io import load_config


REQUIRED_TABLES = [
    "deterministic_ladder.csv",
    "event_study_coefficients_shilin.csv",
    "pretrend_diagnostics.json",
    "wild_cluster_bootstrap.json",
    "result1_frequency_sensitivity.csv",
    "result1_stakeholder_metric_battery.csv",
    "data_availability_ledger.csv",
    "claim_scope_ledger.csv",
    "hf_pump_risk_snapshot_summary.json",
    "external_validation_summary.json",
    "moralis_decoded_outcomes_summary.json",
    "h1_rpc_mechanism_causal_audit.csv",
    "h1_rpc_mechanism_summary.json",
    "teacher_requirements_alignment_shilin.csv",
    "dune_indexer_export_summary.json",
    "free_public_data_inventory.csv",
    "free_public_data_summary.json",
    "red_cohort_red_pump_overlap.csv",
    "pyfixest_did_crosscheck.csv",
    "event_date_sensitivity.csv",
    "twfe_window_sensitivity.csv",
    "control_set_sensitivity.csv",
    "placebo_event_diagnostics.csv",
    "unit_permutation_test.csv",
    "unit_permutation_summary.json",
    "synthetic_control_diagnostics.csv",
    "synthetic_control_summary.json",
    "moralis_sample_selection_audit.csv",
    "identification_strength_summary.json",
    "agentic_prompt_manifest.csv",
    "agentic_arm_scores.csv",
    "paper_readiness_audit.csv",
    "paper_readiness_summary.json",
    "radar_evidence_profiles.csv",
]

REQUIRED_FIGURES = [
    "fig_parallel_trends_shilin.png",
    "fig_event_study_shilin.png",
    "fig_ablation_ladder_shilin.png",
    "fig_frequency_sensitivity_shilin.png",
    "fig_metric_battery_status_shilin.png",
    "fig_external_validation_rpc_shilin.png",
    "fig_readiness_radar_shilin.png",
    "fig_readiness_status_bar_shilin.png",
    "fig_market_protocol_volume_lines_shilin.png",
    "fig_agentic_method_omission_bar_shilin.png",
    "fig_agentic_calibration_gap_bar_shilin.png",
    "fig_h1_mechanism_audit_shilin.png",
    "fig_token_activity_distribution_shilin.png",
    "fig_frequency_market_twfe_single_shilin.png",
    "fig_frequency_data_richness_single_shilin.png",
    "fig_rpc_active_share_single_shilin.png",
    "fig_rpc_median_persistence_single_shilin.png",
    "fig_rpc_token_distribution_single_shilin.png",
    "fig_rpc_window_coverage_single_shilin.png",
    "fig_h1_activity_placebo_single_shilin.png",
    "fig_h1_persistence_intensity_single_shilin.png",
    "fig_h1_temporal_ordering_single_shilin.png",
    "fig_h1_claim_boundary_single_shilin.png",
    "fig_token_coverage_by_date_single_shilin.png",
    "fig_token_persistence_survival_single_shilin.png",
    "fig_ladder_decision_flip_shilin.png",
    "fig_rpc_deepening_gain_shilin.png",
    "fig_horizon_ridgeline_shilin.png",
    "fig_readiness_gap_heatmap_shilin.png",
    "fig_agentic_scaffold_tradeoff_shilin.png",
    "fig_research_contribution_matrix_shilin.png",
]

EXPECTED_RUNGS = [f"L{i}" for i in range(8)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs" / "pumpswap_case.json"))
    args = parser.parse_args()
    config = load_config(args.config)

    missing: list[Path] = []
    for name in REQUIRED_TABLES:
        path = config.tables_dir / name
        if not path.exists() or path.stat().st_size == 0:
            missing.append(path)
    for name in REQUIRED_FIGURES:
        path = config.figures_dir / name
        if not path.exists() or path.stat().st_size == 0:
            missing.append(path)
    if missing:
        print("Missing or empty artifacts:")
        for path in missing:
            print(f"  - {path}")
        raise SystemExit(1)

    errors: list[str] = []
    ladder = pd.read_csv(config.tables_dir / "deterministic_ladder.csv")
    if ladder["rung"].tolist() != EXPECTED_RUNGS:
        errors.append(f"deterministic_ladder.csv must contain exactly {EXPECTED_RUNGS}")

    pyfixest = pd.read_csv(config.tables_dir / "pyfixest_did_crosscheck.csv")
    twfe = pyfixest.loc[pyfixest["spec_id"].eq("twfe_unit_date_fe")]
    l2 = ladder.loc[ladder["rung"].eq("L2")]
    if not len(twfe):
        errors.append("pyfixest_did_crosscheck.csv must include twfe_unit_date_fe.")
    elif not len(l2) or abs(float(twfe.iloc[0]["estimate"]) - float(l2.iloc[0]["estimate"])) > 1e-6:
        errors.append("PyFixest TWFE cross-check must match the deterministic L2 estimate.")

    hf = json.loads((config.tables_dir / "hf_pump_risk_snapshot_summary.json").read_text(encoding="utf-8"))
    if hf.get("rows") != hf.get("unique_mints"):
        errors.append("HF Pump.fun summary must be token-level: rows should equal unique_mints after deduplication.")
    if hf.get("raw_snapshot_rows", 0) < hf.get("rows", 0):
        errors.append("HF Pump.fun raw_snapshot_rows cannot be smaller than deduplicated rows.")
    if "latest" not in str(hf.get("dedupe_rule", "")).lower():
        errors.append("HF Pump.fun summary must record the latest-per-mint dedupe rule.")

    frequency = pd.read_csv(config.tables_dir / "result1_frequency_sensitivity.csv")
    external_summary = json.loads((config.tables_dir / "external_validation_summary.json").read_text(encoding="utf-8"))
    if external_summary.get("status") != "computed_external_validation_sample":
        errors.append("external_validation_summary.json must record computed_external_validation_sample.")
    for name in [
        "pumpfun_coin_metadata.csv",
        "solana_post_migration_pool_windows.csv",
        "solana_early_wallet_concentration.csv",
        "solana_parsed_transaction_proxies.csv",
        "dune_graduated_tokens.csv",
        "h1_rpc_token_level_outcomes.csv",
        "moralis_token_swaps.csv",
        "moralis_fetch_status.csv",
        "moralis_decoded_token_outcomes.csv",
    ]:
        path = config.output_root / "external_validation" / name
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"Missing external validation artifact: {path}")
    moralis_summary = json.loads((config.tables_dir / "moralis_decoded_outcomes_summary.json").read_text(encoding="utf-8"))
    if moralis_summary.get("status") not in {
        "computed_moralis_decoded_outcome_sample",
        "stopped_moralis_decoded_outcome_sample_partial",
        "computed_moralis_decoded_outcome_empty",
    }:
        errors.append("moralis_decoded_outcomes_summary.json must record a completed or stopped Moralis run.")
    if int(moralis_summary.get("unique_decoded_swap_rows", 0) or 0) <= 0:
        errors.append("Moralis decoded collection must contain at least one unique decoded swap row.")
    h1_audit = pd.read_csv(config.tables_dir / "h1_rpc_mechanism_causal_audit.csv")
    if "H1-rpc-complete-window-activity" not in set(h1_audit["claim_id"].astype(str)):
        errors.append("h1_rpc_mechanism_causal_audit.csv must include the complete-window H1 activity estimand.")
    if "H1-decoded-usd-trade-outcomes" not in set(h1_audit["claim_id"].astype(str)):
        errors.append("h1_rpc_mechanism_causal_audit.csv must explicitly retain the decoded USD outcome row.")
    forbidden_text = " ".join(h1_audit["claim_not_allowed"].astype(str))
    if "welfare" not in forbidden_text or "USD" not in forbidden_text:
        errors.append("H1 mechanism audit must forbid welfare/USD overclaims from RPC proxies.")
    h1_summary = json.loads((config.tables_dir / "h1_rpc_mechanism_summary.json").read_text(encoding="utf-8"))
    if h1_summary.get("mechanism_claim_status") != "pass_mechanism_level_not_welfare_causal":
        errors.append("H1 RPC mechanism audit should pass only as mechanism-level, not welfare-causal, evidence.")
    if int(h1_summary.get("temporal_order_violations_complete_30d", -1)) != 0:
        errors.append("H1 RPC mechanism audit must pass the temporal-ordering falsification check.")
    dune_summary = json.loads((config.tables_dir / "dune_indexer_export_summary.json").read_text(encoding="utf-8"))
    valid_dune_statuses = {
        "rendered_sql_only",
        "computed_dune_indexer_exports",
        "computed_dune_indexer_exports_partial",
        "stopped_chunked_dune_indexer_exports_partial",
    }
    if dune_summary.get("status") not in valid_dune_statuses:
        errors.append(f"dune_indexer_export_summary.json must have one of {sorted(valid_dune_statuses)}.")
    if int(dune_summary.get("tokens_in_query", 0)) != int(dune_summary.get("all_graduated_tokens_available", -1)):
        errors.append("Rendered Dune SQL should cover all available graduated tokens.")
    for key in ["post_sql_path", "early_sql_path"]:
        path = Path(str(dune_summary.get(key, "")))
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"Missing rendered Dune SQL artifact: {path}")
    if dune_summary.get("status") in {
        "computed_dune_indexer_exports",
        "computed_dune_indexer_exports_partial",
        "stopped_chunked_dune_indexer_exports_partial",
    }:
        outputs = dune_summary.get("outputs", {})
        if dune_summary.get("status") == "stopped_chunked_dune_indexer_exports_partial" and not any(
            int((output or {}).get("rows", 0) or 0) > 0 for output in outputs.values()
        ):
            expected_labels = []
        else:
            expected_labels = ["post_migration", "early_wallets"] if dune_summary.get("status") == "computed_dune_indexer_exports" else list(outputs)
        for label in expected_labels:
            if not outputs.get(label, {}).get("schema_ok"):
                errors.append(f"Dune output schema check failed for {label}.")
    registered_layers = {"token_post_migration_windows", "early_allocation_fairness"}
    bad_external = frequency.loc[
        frequency["layer"].isin(registered_layers)
        & ~frequency["decision"].isin(["registered_external_validation", "computed_external_validation_sample"])
    ]
    if len(bad_external):
        errors.append("Dune/indexer mechanism layers must be registered or computed external validation, not required claims.")

    free_public_summary = json.loads((config.tables_dir / "free_public_data_summary.json").read_text(encoding="utf-8"))
    if free_public_summary.get("status") != "computed_free_public_local_inventory":
        errors.append("free_public_data_summary.json must record computed_free_public_local_inventory.")
    if int(free_public_summary.get("total_files", 0)) <= 0:
        errors.append("free_public_data_inventory.csv must contain at least one downloaded public-data file.")
    overlap = free_public_summary.get("red_cohort_red_pump_overlap", {})
    if overlap.get("status") != "computed_overlap_audit":
        errors.append("free_public_data_summary.json must include a computed RED-COHORT/RED-PUMP overlap audit.")
    solarchive = free_public_summary.get("solarchive", {})
    if solarchive.get("present") and solarchive.get("transaction_partition_last_in_hf_index") not in {None, "2022-04-30"}:
        errors.append("SolArchive HF transaction-index boundary changed; update README claim boundary before reporting.")

    prompt_manifest = pd.read_csv(config.tables_dir / "agentic_prompt_manifest.csv")
    if prompt_manifest["rung"].tolist() != EXPECTED_RUNGS:
        errors.append("agentic_prompt_manifest.csv must contain exactly L0-L7.")
    l5_prompt = prompt_manifest.loc[prompt_manifest["rung"].eq("L5")]
    if not len(l5_prompt) or "HF Pump.fun risk" not in str(l5_prompt.iloc[0]["data_access"]):
        errors.append("L5 agentic prompt must disclose the HF Pump.fun risk snapshot data.")
    agent_runs_path = config.agent_runs_dir / "agent_runs.csv"
    if not agent_runs_path.exists() or agent_runs_path.stat().st_size == 0:
        errors.append("agent_runs.csv must exist; agentic arm should be real runs, not registered prompts only.")
    else:
        agent_runs = pd.read_csv(agent_runs_path)
        min_runs = int(config.raw.get("agentic", {}).get("minimum_pilot_runs_per_rung", 5))
        by_rung = agent_runs.groupby("rung").size()
        for rung in EXPECTED_RUNGS:
            if int(by_rung.get(rung, 0)) < min_runs:
                errors.append(f"agent_runs.csv must contain at least {min_runs} real runs for {rung}.")
    scores = pd.read_csv(config.tables_dir / "agentic_arm_scores.csv")
    if "registered_prompts_only" in set(scores["status"].astype(str)):
        errors.append("agentic_arm_scores.csv still contains registered_prompts_only; rerun run_all.py after agent runs.")

    readiness = pd.read_csv(config.tables_dir / "paper_readiness_audit.csv")
    required_areas = {
        "benchmark_ladder",
        "parallel_trends",
        "few_cluster_inference",
        "decoded_indexer_outcomes",
        "rpc_external_validation",
        "h1_rpc_mechanism_validation",
        "identification_stress_tests",
        "moralis_sample_selection",
        "agentic_execution",
        "claim_boundary",
    }
    missing_areas = sorted(required_areas.difference(set(readiness["area"].astype(str))))
    if missing_areas:
        errors.append(f"paper_readiness_audit.csv missing areas: {missing_areas}")
    summary = json.loads((config.tables_dir / "paper_readiness_summary.json").read_text(encoding="utf-8"))
    if summary.get("readiness_label") not in {
        "workshop_ready_with_limitations",
        "workshop_ready_as_benchmark_with_limitations",
        "strong_replication_draft_not_submission_ready",
    }:
        errors.append("paper_readiness_summary.json has an unknown readiness_label.")
    identification = json.loads((config.tables_dir / "identification_strength_summary.json").read_text(encoding="utf-8"))
    for name, minimum in [
        ("event_date_sensitivity_rows", 10),
        ("twfe_window_rows", 3),
        ("control_set_rows", 4),
        ("placebo_rows", 3),
    ]:
        if int(identification.get(name, 0) or 0) < minimum:
            errors.append(f"identification_strength_summary.json has too few rows for {name}.")
    if "diagnostic" not in str(identification.get("submission_claim_recommendation", "")).lower():
        errors.append("identification_strength_summary.json must recommend bounded diagnostic use of market DiD.")
    for name in [
        "event_date_sensitivity.csv",
        "twfe_window_sensitivity.csv",
        "control_set_sensitivity.csv",
        "placebo_event_diagnostics.csv",
        "unit_permutation_test.csv",
        "synthetic_control_diagnostics.csv",
        "moralis_sample_selection_audit.csv",
    ]:
        table = pd.read_csv(config.tables_dir / name)
        if table.empty:
            errors.append(f"{name} must not be empty.")
    permutation = json.loads((config.tables_dir / "unit_permutation_summary.json").read_text(encoding="utf-8"))
    if int(permutation.get("unit_count", 0) or 0) < 4:
        errors.append("unit_permutation_summary.json must include all four protocol units.")
    synthetic = json.loads((config.tables_dir / "synthetic_control_summary.json").read_text(encoding="utf-8"))
    if int(synthetic.get("unit_count", 0) or 0) < 4:
        errors.append("synthetic_control_summary.json must include all four protocol units.")
    if "stand-alone causal proof" not in str(synthetic.get("claim_boundary", "")):
        errors.append("synthetic_control_summary.json must include the causal-proof claim boundary.")
    radar = pd.read_csv(config.tables_dir / "radar_evidence_profiles.csv")
    expected_profiles = {"L0 naive before-after", "L2 TWFE DiD", "L6 wild-cluster DiD"}
    expected_dimensions = {
        "Effect magnitude",
        "Estimate precision",
        "Control / FE design",
        "Few-cluster correction",
        "Conservative conclusion",
        "Agent method coverage",
        "Agent calibration quality",
    }
    if set(radar["profile"].astype(str)) != expected_profiles:
        errors.append("radar_evidence_profiles.csv must contain the three actual ladder-rung comparison profiles.")
    if set(radar["dimension"].astype(str)) != expected_dimensions:
        errors.append("radar_evidence_profiles.csv must contain the expected data-derived rung dimensions.")
    if radar["profile"].astype(str).str.contains("target|submission", case=False, na=False).any():
        errors.append("radar_evidence_profiles.csv must not include aspirational target profiles.")
    if not radar["score"].between(0, 1).all():
        errors.append("radar_evidence_profiles.csv scores must lie in [0, 1].")

    if errors:
        print("Artifact logic checks failed:")
        for error in errors:
            print(f"  - {error}")
        raise SystemExit(1)
    print("All required Shilin artifacts exist and are non-empty.")
    print("Artifact logic checks passed.")


if __name__ == "__main__":
    main()
