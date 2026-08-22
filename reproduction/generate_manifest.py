"""Map paper figures, tables, and numerical claims to generating artifacts."""

from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import ARCHIVED, GENERATED, MANIFEST, PAPER, REPRO, REPO

ROWS = [
    {
        "paper_object": "tab:data-scope",
        "object_type": "table",
        "claim": "Four-chain canonical unit counts and UTC windows",
        "input": "reproduction/scope.json; reproduction/archived/release/*_core.json",
        "script": "reproduction/generate_tables.py",
        "output": "paper/tabs/tab_data_scope.tex",
    },
    {
        "paper_object": "tab:claim-evidence",
        "object_type": "table",
        "claim": "Claim-evidence-stakeholder statuses and reported estimates",
        "input": "reproduction/archived/application/deterministic_ladder.csv; telegram_mirror_design_summary.json; h1_rpc_mechanism_summary.json; identification/h0_summary.json; identification/h3_incidence.json",
        "script": "reproduction/generate_tables.py",
        "output": "paper/tabs/tab_claim_evidence.tex",
    },
    {
        "paper_object": "tab:related-work",
        "object_type": "conceptual_table",
        "claim": "Capability matrix over representative datasets",
        "input": "notes/related_work_evidence.md; reproduction/source_ledger.md",
        "script": "none (literature table with source ledger)",
        "output": "paper/tabs/tab_related_work.tex",
    },
    {
        "paper_object": "tab:ladder",
        "object_type": "conceptual_table",
        "claim": "L0-L7 evidence contract definition",
        "input": "reproduction/source_ledger.md",
        "script": "none (definitional table with source ledger)",
        "output": "paper/tabs/tab_ladder.tex",
    },
    {
        "paper_object": "fig:evidence-contract-overview",
        "object_type": "conceptual_figure",
        "claim": "Evidence infrastructure, evaluation pillars, and bounded stakeholder interpretation",
        "input": "reproduction/scope.json; reproduction/archived/release/*_core.json; application/deterministic_ladder.csv; h1_rpc_mechanism_summary.json; telegram_mirror_design_summary.json",
        "script": "reproduction/generate_figures.py",
        "output": "paper/figs/teaser_figure.pdf; paper/figs/teaser_figure.svg",
    },
    {
        "paper_object": "fig:data-layer-coverage",
        "object_type": "figure",
        "claim": "Chain-specific coverage and event-design status",
        "input": "reproduction/scope.json; reproduction/archived/release/events_core.json",
        "script": "reproduction/generate_figures.py",
        "output": "paper/figs/fig_data_layer_coverage_map.pdf",
    },
    {
        "paper_object": "fig:pumpswap-event-study",
        "object_type": "figure",
        "claim": "PumpSwap event-study coefficients and pretrend flags",
        "input": "reproduction/archived/application/event_study_coefficients.csv",
        "script": "reproduction/generate_figures.py",
        "output": "paper/figs/fig_event_study_shilin.pdf",
    },
    {
        "paper_object": "fig:pumpswap-decision-path",
        "object_type": "figure",
        "claim": "Ladder path from L0 dashboard estimate to L6 few-cluster inference",
        "input": "reproduction/archived/application/deterministic_ladder.csv",
        "script": "reproduction/generate_figures.py",
        "output": "paper/figs/fig_ladder_decision_flip_shilin.pdf",
    },
    {
        "paper_object": "fig:stress-test-atlas",
        "object_type": "figure",
        "claim": "S1-S5 known-truth calibration map",
        "input": "reproduction/archived/calibration/s1_results_summary.csv through s5_results_summary.csv",
        "script": "reproduction/generate_figures.py",
        "output": "paper/figs/fig_stress_test_atlas.pdf",
    },
    {
        "paper_object": "fig:application-stakeholder",
        "object_type": "figure",
        "claim": "Stakeholder metric battery rates",
        "input": "reproduction/archived/application/result1_stakeholder_metric_battery.csv",
        "script": "reproduction/generate_figures.py",
        "output": "paper/figs/fig_metric_battery_status_shilin.pdf",
    },
    {
        "paper_object": "fig:application-frequency",
        "object_type": "figure",
        "claim": "Daily versus weekly TWFE aggregation shift",
        "input": "reproduction/archived/application/result1_frequency_sensitivity.csv",
        "script": "reproduction/generate_figures.py",
        "output": "paper/figs/fig_frequency_sensitivity_shilin.pdf",
    },
    {
        "paper_object": "fig:appendix-mechanism-coverage",
        "object_type": "figure",
        "claim": "Observed 30-day transaction-proxy activity and complete-window activity",
        "input": "reproduction/archived/application/h1_rpc_mechanism_summary.json",
        "script": "reproduction/generate_figures.py",
        "output": "paper/figs/fig_h1_mechanism_audit_shilin.pdf",
    },
    {
        "paper_object": "fig:appendix-agentic-tradeoff",
        "object_type": "figure",
        "claim": "Calibration gap and method-omission rate across L0 to L7",
        "input": "reproduction/archived/application/agentic_arm_scores.csv",
        "script": "reproduction/generate_figures.py",
        "output": "paper/figs/fig_agentic_scaffold_tradeoff_shilin.pdf",
    },
    {
        "paper_object": "main-text:pumpswap-twfe",
        "object_type": "number",
        "claim": "TWFE 0.412, CI [-0.128, 0.951], exact p = 0.6875",
        "input": "reproduction/archived/application/deterministic_ladder.csv; wild_cluster_bootstrap.json",
        "script": "application/src/trustworthy_launchpads/deterministic_ladder.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "intro:external-protocol-revenue",
        "object_type": "number_external",
        "claim": "Pump.fun surpassed USD 1 billion cumulative protocol revenue by early 2026",
        "input": "paper/references.bib#defillama",
        "script": "none (externally cited fact)",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "appendix:pumpswap-design",
        "object_type": "number",
        "claim": "March 20, 2025 event; plus or minus 90-day window; four protocols and four clusters",
        "input": "reproduction/archived/application/deterministic_ladder.csv; wild_cluster_bootstrap.json; event_study_coefficients.csv",
        "script": "application/src/trustworthy_launchpads/deterministic_ladder.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:telegram-att",
        "object_type": "number",
        "claim": "Matched Telegram ATT 0.945 pp, CI [0.732, 1.163], E-value 5.02",
        "input": "reproduction/archived/application/telegram_mirror_design_summary.json",
        "script": "application/scripts/run_telegram_mirror_design.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:fee-incidence",
        "object_type": "number",
        "claim": "10,732 lamports; diagnostic -0.966 [-1.252, -0.680]; 7-day contrast 0.182 [-0.174, 0.538]",
        "input": "reproduction/archived/identification/h3_incidence.json; h0_summary.json",
        "script": "identification/src/web3io_claire/analyze_h0.py; analyze_h3.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:pumpswap-mechanism",
        "object_type": "number",
        "claim": "1,636 of 1,651 observed active tokens and 762 complete active windows",
        "input": "reproduction/archived/application/h1_rpc_mechanism_summary.json",
        "script": "application/scripts/run_solana_external_validation.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:telegram-design",
        "object_type": "number",
        "claim": "1.485 versus 0.166 percent; 20,227 treated; 586,581 controls; 500 bootstrap replications; six screened shocks",
        "input": "reproduction/archived/application/telegram_mirror_design_summary.json; telegram_exposure_design_summary.json",
        "script": "application/scripts/run_telegram_mirror_design.py; run_telegram_exposure_design.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:fee-design",
        "object_type": "number",
        "claim": "May 12 zero transfer; May 13 activation at 11:27:06 UTC; six treated and six comparison Base launches",
        "input": "reproduction/archived/identification/h3_incidence.json; application/clanker_base_event_validation_summary.json",
        "script": "identification/src/web3io_claire/analyze_h3.py; application/scripts/run_clanker_base_validation.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:s1-calibration",
        "object_type": "number",
        "claim": "Eight cohorts; TWFE RMSE 0.005 versus group-time ATT RMSE 0.018",
        "input": "reproduction/archived/calibration/s1_results_summary.csv",
        "script": "identification/experiments/s1_staggered/run_mc.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:s2-calibration",
        "object_type": "number",
        "claim": "Five-day timing gap; 81 percent recovery; pre-event gate fires in 32 to 50 percent",
        "input": "reproduction/archived/calibration/s2_results_summary.csv",
        "script": "identification/experiments/s2_timing/src/s2_timing/run_mc.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:s3-calibration",
        "object_type": "number",
        "claim": "Four clusters; rejection rates 6.46 and 2.59 percent; exact minimum p values 0.125 and 0.25",
        "input": "reproduction/archived/calibration/s3_results_summary.csv",
        "script": "identification/experiments/s3_few_clusters/src/run_experiment.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:s4-calibration",
        "object_type": "number",
        "claim": "TWFE bias 0.465 and 0.707; group-time bias 0.016 and 0.026",
        "input": "reproduction/archived/calibration/s4_results_summary.csv",
        "script": "identification/experiments/s4_endogenous/src/s4_endogenous/run_mc.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:s5-calibration",
        "object_type": "number",
        "claim": "Naive weekly recovery 43 to 44 percent transient and 47 to 48 percent persistent",
        "input": "reproduction/archived/calibration/s5_results_summary.csv",
        "script": "identification/experiments/s5_aggregation/src/s5agg/runner.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:agent-score",
        "object_type": "number",
        "claim": "Eight rungs; ten runs per rung; absolute calibration gap 0.75 to 0.25",
        "input": "reproduction/archived/application/agentic_arm_scores.csv; agent_runs.csv; raw_responses/",
        "script": "application/scripts/run_agentic_deepseek.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "appendix:data-counts",
        "object_type": "number",
        "claim": "All chain counts, lifecycle counts, Solana pool-window rows, decoded swaps, and Base initial-liquidity positions",
        "input": "reproduction/archived/release/solana_core.json; base_core.json; bnb_core.json; tron_core.json",
        "script": "data_pipeline/scripts/build_solana_core.py; build_crosschain_core.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "appendix:event-layer",
        "object_type": "number",
        "claim": "Four event candidates and six evidence records with one accepted, one conditional, and two rejected",
        "input": "reproduction/archived/release/events_core.json; event_registry.json; event_evidence.json",
        "script": "data_pipeline/scripts/build_events.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "appendix:fee-panel",
        "object_type": "number",
        "claim": "156 platform-day rows, 21-day windows, seven Newey-West lags, and eight placebo dates",
        "input": "reproduction/archived/identification/h0_summary.json",
        "script": "identification/src/web3io_claire/analyze_h0.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "appendix:base-extension",
        "object_type": "number",
        "claim": "Block 34,725,785; August 26, 2025; six treated and six controls; three horizons; 36 rows",
        "input": "reproduction/archived/application/clanker_base_event_validation_summary.json",
        "script": "application/scripts/run_clanker_base_validation.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "appendix:simulation-designs",
        "object_type": "number",
        "claim": "S1 through S5 cohort counts, timing gaps, synthetic effects, replication counts, cluster counts, selection arms, and seven-day targets",
        "input": "reproduction/archived/calibration/s1_results_summary.csv through s5_results_summary.csv; identification/experiments/*/design_lock.yaml",
        "script": "identification/experiments/s1_staggered through s5_aggregation",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "app:agent",
        "object_type": "evaluation",
        "claim": "Bounded DeepSeek request alias deepseek-chat, returned model deepseek-v4-flash, 10 runs per rung, temperature 0; exact runtime payload not archived",
        "input": "reproduction/archived/application/agent_runs.csv; agentic_arm_scores.csv; raw_responses/; agent_provenance.json; prompts/",
        "script": "application/scripts/run_agentic_deepseek.py",
        "output": "reproduction/archived/application/",
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    fieldnames = ["paper_object", "object_type", "claim", "input", "script", "output"]
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(ROWS)
    checksums = []
    for path in sorted(ARCHIVED.rglob("*")):
        if path.is_file() and path.name != "index.json":
            checksums.append(f"{sha256(path)}  {path.relative_to(REPRO)}")
    for path in [GENERATED / "tab_data_scope.tex", GENERATED / "tab_claim_evidence.tex"]:
        if path.exists():
            checksums.append(f"{sha256(path)}  {path.relative_to(REPRO)}")
    (REPRO / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST.relative_to(REPO)} with {len(ROWS)} rows")
    print(f"wrote checksums for {len(checksums)} files")


if __name__ == "__main__":
    main()
