"""Copy identity-stripped summary artifacts into reproduction/archived."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import ARCHIVED, REPO

USER_PATH = re.compile(r"/Users/[^/\s\"']+")
HOME_PATH = re.compile(r"/home/[^/\s\"']+")

COPIES: list[tuple[str, str]] = [
    ("Shilin/artifacts/tables/deterministic_ladder.csv", "application/deterministic_ladder.csv"),
    ("Shilin/artifacts/tables/wild_cluster_bootstrap.json", "application/wild_cluster_bootstrap.json"),
    ("Shilin/artifacts/tables/telegram_mirror_design_summary.json", "application/telegram_mirror_design_summary.json"),
    ("Shilin/artifacts/tables/telegram_exposure_design_summary.json", "application/telegram_exposure_design_summary.json"),
    ("Shilin/artifacts/tables/h1_rpc_mechanism_summary.json", "application/h1_rpc_mechanism_summary.json"),
    ("Shilin/artifacts/tables/agentic_arm_scores.csv", "application/agentic_arm_scores.csv"),
    ("Shilin/artifacts/tables/agentic_prompt_manifest.csv", "application/agentic_prompt_manifest.csv"),
    ("Shilin/artifacts/tables/result1_stakeholder_metric_battery.csv", "application/result1_stakeholder_metric_battery.csv"),
    ("Shilin/artifacts/tables/result1_frequency_sensitivity.csv", "application/result1_frequency_sensitivity.csv"),
    ("Shilin/artifacts/tables/event_study_coefficients_shilin.csv", "application/event_study_coefficients.csv"),
    ("Shilin/artifacts/agent_runs/agent_run_schema.json", "application/agent_run_schema.json"),
    ("Shilin/artifacts/agent_runs/agent_runs.csv", "application/agent_runs.csv"),
    ("Claire/artifacts/h0_summary.json", "identification/h0_summary.json"),
    ("Claire/artifacts/h3_incidence.json", "identification/h3_incidence.json"),
    ("Claire/artifacts/deterministic_crosscheck.json", "identification/deterministic_crosscheck.json"),
    ("Claire/evidence/pump_creator_fee_checks.json", "identification/pump_creator_fee_checks.json"),
    ("Claire/event_registry.csv", "identification/event_registry.csv"),
    ("Claire/experiments/s1_staggered/artifacts/results_summary.csv", "calibration/s1_results_summary.csv"),
    ("Claire/experiments/s2_timing/artifacts/results_summary.csv", "calibration/s2_results_summary.csv"),
    ("Claire/experiments/s3_few_clusters/artifacts/results_summary.csv", "calibration/s3_results_summary.csv"),
    ("Claire/experiments/s4_endogenous/artifacts/results_summary.csv", "calibration/s4_results_summary.csv"),
    ("Claire/experiments/s5_aggregation/artifacts/results_summary.csv", "calibration/s5_results_summary.csv"),
    ("data_pipeline/releases/v1/solana_core.json", "release/solana_core.json"),
    ("data_pipeline/releases/v1/base_core.json", "release/base_core.json"),
    ("data_pipeline/releases/v1/bnb_core.json", "release/bnb_core.json"),
    ("data_pipeline/releases/v1/tron_core.json", "release/tron_core.json"),
    ("data_pipeline/releases/v1/events_core.json", "release/events_core.json"),
    ("data_pipeline/events/v1/event_registry.json", "release/event_registry.json"),
    ("data_pipeline/events/v1/event_evidence.json", "release/event_evidence.json"),
    ("data_pipeline/source_registry.json", "release/source_registry.json"),
]


def redact_text(text: str) -> str:
    text = USER_PATH.sub("<local-home>", text)
    text = HOME_PATH.sub("<local-home>", text)
    text = text.replace("pumpswap_shilin_application", "pumpswap_application")
    return text


def copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in {".json", ".csv", ".md", ".txt"}:
        text = redact_text(src.read_text(encoding="utf-8", errors="replace"))
        dest.write_text(text, encoding="utf-8")
        return
    shutil.copy2(src, dest)


def copy_prompts() -> int:
    src_dir = REPO / "Shilin" / "prompts"
    dest_dir = ARCHIVED / "application" / "prompts"
    n = 0
    if not src_dir.exists():
        return 0
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(src_dir.glob("*.md")):
        copy_file(src, dest_dir / src.name)
        n += 1
    return n


def main() -> None:
    missing: list[str] = []
    copied = 0
    for rel_src, rel_dest in COPIES:
        src = REPO / rel_src
        dest = ARCHIVED / rel_dest
        if not src.exists():
            missing.append(rel_src)
            continue
        copy_file(src, dest)
        copied += 1
    copied += copy_prompts()
    index = {
        "copied": copied,
        "missing": missing,
        "archived_root": str(ARCHIVED.relative_to(REPO)),
    }
    ARCHIVED.mkdir(parents=True, exist_ok=True)
    (ARCHIVED / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"archived {copied} files; missing {len(missing)}")
    for path in missing:
        print(f"  missing: {path}")


if __name__ == "__main__":
    main()
