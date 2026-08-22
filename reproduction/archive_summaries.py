"""Copy identity-stripped summary artifacts into reproduction/archived."""

from __future__ import annotations

import json
import csv
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import ARCHIVED, REPO

USER_PATH = re.compile(r"/Users/[^/\s\"']+")
HOME_PATH = re.compile(r"/home/[^/\s\"']+")

COPIES: list[tuple[str, str]] = [
    ("application/artifacts/tables/deterministic_ladder.csv", "application/deterministic_ladder.csv"),
    ("application/artifacts/tables/wild_cluster_bootstrap.json", "application/wild_cluster_bootstrap.json"),
    ("application/artifacts/tables/telegram_mirror_design_summary.json", "application/telegram_mirror_design_summary.json"),
    ("application/artifacts/tables/telegram_exposure_design_summary.json", "application/telegram_exposure_design_summary.json"),
    ("application/artifacts/tables/h1_rpc_mechanism_summary.json", "application/h1_rpc_mechanism_summary.json"),
    ("application/artifacts/tables/clanker_base_event_validation_summary.json", "application/clanker_base_event_validation_summary.json"),
    ("application/artifacts/tables/agentic_arm_scores.csv", "application/agentic_arm_scores.csv"),
    ("application/artifacts/tables/agentic_prompt_manifest.csv", "application/agentic_prompt_manifest.csv"),
    ("application/artifacts/tables/result1_stakeholder_metric_battery.csv", "application/result1_stakeholder_metric_battery.csv"),
    ("application/artifacts/tables/result1_frequency_sensitivity.csv", "application/result1_frequency_sensitivity.csv"),
    ("application/artifacts/tables/event_study_coefficients_shilin.csv", "application/event_study_coefficients.csv"),
    ("application/artifacts/agent_runs/agent_run_schema.json", "application/agent_run_schema.json"),
    ("application/artifacts/agent_runs/agent_runs.csv", "application/agent_runs.csv"),
    ("identification/artifacts/h0_summary.json", "identification/h0_summary.json"),
    ("identification/artifacts/h3_incidence.json", "identification/h3_incidence.json"),
    ("identification/artifacts/deterministic_crosscheck.json", "identification/deterministic_crosscheck.json"),
    ("identification/evidence/pump_creator_fee_checks.json", "identification/pump_creator_fee_checks.json"),
    ("identification/event_registry.csv", "identification/event_registry.csv"),
    ("identification/experiments/s1_staggered/artifacts/results_summary.csv", "calibration/s1_results_summary.csv"),
    ("identification/experiments/s2_timing/artifacts/results_summary.csv", "calibration/s2_results_summary.csv"),
    ("identification/experiments/s3_few_clusters/artifacts/results_summary.csv", "calibration/s3_results_summary.csv"),
    ("identification/experiments/s4_endogenous/artifacts/results_summary.csv", "calibration/s4_results_summary.csv"),
    ("identification/experiments/s5_aggregation/artifacts/results_summary.csv", "calibration/s5_results_summary.csv"),
    ("data_pipeline/releases/v1/solana_core.json", "release/solana_core.json"),
    ("data_pipeline/releases/v1/base_core.json", "release/base_core.json"),
    ("data_pipeline/releases/v1/bnb_core.json", "release/bnb_core.json"),
    ("data_pipeline/releases/v1/tron_core.json", "release/tron_core.json"),
    ("data_pipeline/releases/v1/events_core.json", "release/events_core.json"),
    ("data_pipeline/events/v1/event_registry.json", "release/event_registry.json"),
    ("data_pipeline/events/v1/event_evidence.json", "release/event_evidence.json"),
    ("data_pipeline/source_registry.json", "release/source_registry.json"),
]

RAW_RESPONSE_CANDIDATES = [
    REPO / "application" / "artifacts" / "agent_runs" / "raw",
    REPO / "Shilin" / "artifacts" / "agent_runs" / "raw",
    REPO
    / "data"
    / "external"
    / "shilin"
    / "20260810"
    / "bundle"
    / "Web3AI4IO"
    / "Shilin"
    / "artifacts"
    / "agent_runs"
    / "raw",
]

SOURCE_ALIASES = {"application": "Shilin", "identification": "Claire"}


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


def resolve_source(rel: str) -> Path:
    direct = REPO / rel
    if direct.exists():
        return direct
    head, slash, tail = rel.partition("/")
    alias = SOURCE_ALIASES.get(head)
    if alias and slash:
        candidate = REPO / alias / tail
        if candidate.exists():
            return candidate
    return direct


def copy_prompts() -> int:
    src_dir = REPO / "application" / "prompts"
    if not src_dir.exists():
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


def copy_raw_responses() -> int:
    src_dir = next((path for path in RAW_RESPONSE_CANDIDATES if path.exists()), None)
    if src_dir is None:
        return 0
    dest_dir = ARCHIVED / "application" / "raw_responses"
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in sorted(src_dir.glob("*.json")):
        copy_file(src, dest_dir / src.name)
        copied += 1
    return copied


def write_agent_provenance() -> None:
    runs_path = ARCHIVED / "application" / "agent_runs.csv"
    manifest_path = ARCHIVED / "application" / "agentic_prompt_manifest.csv"
    raw_dir = ARCHIVED / "application" / "raw_responses"
    if not runs_path.exists():
        return
    with runs_path.open(encoding="utf-8", newline="") as handle:
        runs = list(csv.DictReader(handle))
    run_hashes = sorted({row["prompt_hash"] for row in runs})
    manifest_hashes: list[str] = []
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8", newline="") as handle:
            manifest_hashes = sorted({row["prompt_hash"] for row in csv.DictReader(handle)})
    returned_models: set[str] = set()
    fingerprints: set[str] = set()
    for raw_path in raw_dir.glob("*.json"):
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        response = payload.get("api_response", {})
        if response.get("model"):
            returned_models.add(str(response["model"]))
        if response.get("system_fingerprint"):
            fingerprints.add(str(response["system_fingerprint"]))
    provenance = {
        "run_records": len(runs),
        "raw_responses": len(list(raw_dir.glob("*.json"))),
        "requested_model_aliases": sorted({row["model"] for row in runs}),
        "returned_models": sorted(returned_models),
        "system_fingerprints": sorted(fingerprints),
        "scored_prompt_hashes": run_hashes,
        "current_template_manifest_hashes": manifest_hashes,
        "hash_sets_overlap": bool(set(run_hashes) & set(manifest_hashes)),
        "exact_runtime_prompt_payload": "not archived",
        "audit_boundary": (
            "Raw responses and scored hashes are complete. The current prompt templates do not "
            "reconstruct the scored runtime payload hashes, so the exact runtime payload is not independently repeatable."
        ),
    }
    dest = ARCHIVED / "application" / "agent_provenance.json"
    dest.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    missing: list[str] = []
    copied = 0
    for rel_src, rel_dest in COPIES:
        src = resolve_source(rel_src)
        dest = ARCHIVED / rel_dest
        if not src.exists():
            if dest.exists():
                continue
            missing.append(rel_src)
            continue
        copy_file(src, dest)
        copied += 1
    copied += copy_prompts()
    copied += copy_raw_responses()
    write_agent_provenance()
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
