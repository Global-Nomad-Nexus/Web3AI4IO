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
        "paper_object": "main-text:pumpswap-twfe",
        "object_type": "number",
        "claim": "TWFE 0.412, CI [-0.128, 0.951], exact p = 0.6875",
        "input": "reproduction/archived/application/deterministic_ladder.csv; wild_cluster_bootstrap.json",
        "script": "Shilin/src/trustworthy_launchpads/deterministic_ladder.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:telegram-att",
        "object_type": "number",
        "claim": "Matched Telegram ATT 0.945 pp, CI [0.732, 1.163], E-value 5.02",
        "input": "reproduction/archived/application/telegram_mirror_design_summary.json",
        "script": "Shilin/scripts/run_telegram_mirror_design.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "main-text:fee-incidence",
        "object_type": "number",
        "claim": "10,732 lamports; diagnostic -0.966 [-1.252, -0.680]; 7-day contrast 0.182 [-0.174, 0.538]",
        "input": "reproduction/archived/identification/h3_incidence.json; h0_summary.json",
        "script": "Claire/src/web3io_claire/analyze_h0.py; analyze_h3.py",
        "output": "paper/neurips_2026.tex",
    },
    {
        "paper_object": "app:agent",
        "object_type": "evaluation",
        "claim": "Bounded DeepSeek deepseek-chat, 10 runs per rung, temperature 0",
        "input": "reproduction/archived/application/agent_runs.csv; agentic_arm_scores.csv; prompts/",
        "script": "Shilin/scripts/run_agentic_deepseek.py",
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
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
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
