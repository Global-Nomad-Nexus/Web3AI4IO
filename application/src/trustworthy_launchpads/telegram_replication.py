"""Leak-resistant primitives for the targeted Telegram audit replication."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .agentic_v2 import PromptPacket, canonical_json, sha256_text
from .io import file_sha256


EXPERIMENT_VERSION = "telegram-targeted-replication-v1.0"
EVIDENCE_IDS = ("T0", "T1")
CONDITIONS = {
    "T0_ASSOCIATION": ("T0",),
    "T1_BOUNDARY_COMPLETE": ("T0", "T1"),
}
SCHEMA_NAME = "telegram_evidence_boundary_audit_v1"
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "causal_status": {
            "type": "string",
            "enum": ["supported_positive", "supported_negative", "no_detectable_effect", "not_identified"],
        },
        "predictive_association_status": {
            "type": "string",
            "enum": ["supported_positive", "supported_negative", "no_detectable_association", "not_identified"],
        },
        "supporting_evidence_ids": {"type": "array", "items": {"type": "string", "enum": list(EVIDENCE_IDS)}},
        "missing_evidence_slots": {"type": "array", "items": {"type": "string", "enum": list(EVIDENCE_IDS)}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "short_claim": {"type": "string", "maxLength": 600},
    },
    "required": [
        "causal_status", "predictive_association_status", "supporting_evidence_ids",
        "missing_evidence_slots", "confidence", "short_claim"
    ],
    "additionalProperties": False,
}
FORBIDDEN_PROMPT_MARKERS = (
    "claim_boundary", "credible_matched_design_not_causal",
    "immediate_association_present_keep_causal_boundary_strict",
    "no causal telegram effect should be claimed",
)


@dataclass(frozen=True)
class EvidenceBlock:
    evidence_id: str
    source_artifacts: tuple[str, ...]
    source_sha256: tuple[str, ...]
    content: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_evidence_blocks(repo_root: Path) -> dict[str, EvidenceBlock]:
    mirror = repo_root / "reproduction" / "archived" / "application" / "telegram_mirror_design_summary.json"
    shocks = repo_root / "reproduction" / "archived" / "application" / "telegram_exposure_design_summary.json"
    if not mirror.exists() or not shocks.exists():
        raise FileNotFoundError("Telegram aggregate design summaries are required")
    return {
        "T0": EvidenceBlock(
            "T0", (str(mirror.relative_to(repo_root)),), (file_sha256(mirror),),
            {
                "sample_size": 832941,
                "telegram_present_graduation_percent": 1.485,
                "telegram_absent_graduation_percent": 0.166,
                "matched_difference_percentage_points": 0.945,
                "launch_day_clustered_ci95_percentage_points": [0.732, 1.163],
                "e_value": 5.02,
                "matched_support": {"telegram_present": 20227, "supported_controls": 586581},
                "matching_variables": ["launch day", "Twitter presence", "website presence", "initial market-capitalization decile", "description length"],
            },
        ),
        "T1": EvidenceBlock(
            "T1", (str(mirror.relative_to(repo_root)), str(shocks.relative_to(repo_root))),
            (file_sha256(mirror), file_sha256(shocks)),
            {
                "five_minute_matched_difference_percentage_points": 0.945,
                "five_minute_clustered_ci95_percentage_points": [0.732, 1.163],
                "after_60_minutes_difference_percentage_points": 0.0,
                "after_60_minutes_ci95_percentage_points": [0.0, 0.0],
                "qualifying_exogenous_shocks": {"supported": 0, "screened": 6},
                "unavailable_or_proxied_controls": [
                    "full-cohort creator history unavailable",
                    "initial liquidity proxied by initial market capitalization",
                    "full-cohort risk labels unavailable",
                ],
            },
        ),
    }


def build_prompt_packet(condition_id: str, blocks: Mapping[str, EvidenceBlock]) -> PromptPacket:
    present = CONDITIONS[condition_id]
    missing = [item for item in EVIDENCE_IDS if item not in present]
    system = (
        "You are an evidence-audit assistant. Evaluate only the supplied aggregate evidence. "
        "Distinguish predictive association from an identified causal effect. Absence of identification "
        "is not evidence of no effect. Cite only supplied evidence IDs and return only schema-valid JSON."
    )
    payload = {
        "case": "Telegram metadata observed at token launch and terminal graduation",
        "task": "Assess causal identification and retention of the observed predictive association.",
        "evidence_slot_catalog": {
            "T0": "aggregate association, matching, uncertainty, sensitivity, and support",
            "T1": "timing falsification, exogenous-shock screen, and remaining controls",
        },
        "present_evidence_ids": list(present),
        "missing_evidence_ids": missing,
        "evidence_blocks": {item: blocks[item].content for item in present},
        "output_schema": OUTPUT_SCHEMA,
    }
    user = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    combined = (system + "\n" + user).lower()
    found = [marker for marker in FORBIDDEN_PROMPT_MARKERS if marker in combined]
    if found:
        raise ValueError(f"Answer-bearing marker leaked into {condition_id}: {found}")
    evidence_hash = sha256_text(canonical_json({item: blocks[item].as_dict() for item in present}))
    prompt_hash = sha256_text(f"{system}\n---USER---\n{user}")
    return PromptPacket(system, user, prompt_hash, evidence_hash, f"TEL-{prompt_hash[:16]}")


def build_registry(
    model_specs: list[dict[str, Any]], packets: Mapping[str, PromptPacket], *, runs: int, seed: int
) -> pd.DataFrame:
    rows = []
    for spec in model_specs:
        for condition_id, present in CONDITIONS.items():
            packet = packets[condition_id]
            for run_id in range(1, runs + 1):
                key = f"{EXPERIMENT_VERSION}|{spec['model_spec_id']}|{condition_id}|{run_id}|{seed}"
                digest = hashlib.sha256(key.encode()).hexdigest()
                rows.append({
                    "call_id": f"T-{digest[:20]}", "experiment_version": EXPERIMENT_VERSION,
                    "case_id": "telegram_metadata_application", "model_spec_id": spec["model_spec_id"],
                    "provider": spec["provider"], "requested_model": spec["model"],
                    "condition_id": condition_id, "condition_family": "targeted_replication",
                    "present_evidence_ids": ";".join(present),
                    "missing_evidence_ids": ";".join(item for item in EVIDENCE_IDS if item not in present),
                    "run_id": run_id, "seed": int(digest[20:28], 16), "status": "registered_not_run",
                    "prompt_hash": packet.prompt_hash, "evidence_hash": packet.evidence_hash,
                    "audit_packet_id": packet.audit_packet_id, "started_at_utc": "", "completed_at_utc": "",
                    "returned_model": "", "model_digest": "", "input_tokens": 0, "output_tokens": 0,
                    "reasoning_tokens": 0, "estimated_cost_usd": 0.0, "parse_repair_attempted": 0, "error": "",
                })
    random.Random(seed).shuffle(rows)
    frame = pd.DataFrame(rows)
    if len(frame) != 60 or frame.groupby("model_spec_id").size().to_dict() != {str(s["model_spec_id"]): 20 for s in model_specs}:
        raise ValueError("Telegram design must register exactly 60 calls and 20 calls per model")
    return frame
