"""Leak-resistant evidence-ladder experiment primitives.

This module deliberately does not import the scoring gold contract.  Runtime
prompts are assembled only from aggregate evidence blocks and a neutral output
schema.  The legacy answer-bearing prompt exists solely as a registered positive
control and is marked as such in every manifest row.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from .io import CaseConfig, file_sha256


EXPERIMENT_VERSION = "agentic-evidence-audit-v2.0"
EVIDENCE_IDS = tuple(f"M{i}" for i in range(8))
FACTOR_NAMES = {
    "M4": "pretrend_event_study",
    "M5": "stakeholder_evidence",
    "M6": "few_cluster_uncertainty",
    "M7": "coverage_scope",
}
CANONICAL_FACTORIAL = {
    "L3": "0000",
    "L4": "1000",
    "L5": "1100",
    "L6": "1110",
    "L7": "1111",
}
CANONICAL_RUNG_TO_CONDITION = {
    "L0": "P_L0",
    "L1": "P_L1",
    "L2": "P_L2",
    **{rung: f"F_{bits}" for rung, bits in CANONICAL_FACTORIAL.items()},
}


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "market_causal_status": {
            "type": "string",
            "enum": [
                "supported_positive",
                "supported_negative",
                "no_detectable_effect",
                "not_identified",
            ],
        },
        "operational_status": {
            "type": "string",
            "enum": ["supported", "not_supported", "not_identified"],
        },
        "stakeholder_status": {
            "type": "string",
            "enum": [
                "benefit",
                "harm",
                "mixed_or_stakeholder_specific",
                "not_identified",
            ],
        },
        "supporting_evidence_ids": {
            "type": "array",
            "items": {"type": "string", "enum": list(EVIDENCE_IDS)},
        },
        "missing_evidence_slots": {
            "type": "array",
            "items": {"type": "string", "enum": list(EVIDENCE_IDS)},
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "short_claim": {"type": "string", "maxLength": 600},
    },
    "required": [
        "market_causal_status",
        "operational_status",
        "stakeholder_status",
        "supporting_evidence_ids",
        "missing_evidence_slots",
        "confidence",
        "short_claim",
    ],
    "additionalProperties": False,
}


PRIMARY_FORBIDDEN_MARKERS = (
    "worked_decision",
    "reference_decision",
    "gold_label",
    "gold answer",
    "answer_key",
    "deterministic ladder available",
    "pretrend_flagged",
    "depends_on_stakeholder",
    "retail_risk_higher",
)


@dataclass(frozen=True)
class EvidenceBlock:
    evidence_id: str
    introduced_at_rung: str
    source_artifact: str
    source_sha256: str
    content: Any

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Condition:
    condition_id: str
    family: str
    canonical_rung: str
    factorial_bits: str
    present_evidence_ids: tuple[str, ...]
    leakage_expected: bool = False

    @property
    def missing_evidence_ids(self) -> tuple[str, ...]:
        present = set(self.present_evidence_ids)
        return tuple(item for item in EVIDENCE_IDS if item not in present)


@dataclass(frozen=True)
class PromptPacket:
    system_prompt: str
    user_prompt: str
    prompt_hash: str
    evidence_hash: str
    audit_packet_id: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relative_source(path: Path, config: CaseConfig) -> str:
    resolved = path.resolve()
    repo_root = config.project_root.parent.resolve()
    try:
        return str(resolved.relative_to(repo_root))
    except ValueError:
        return resolved.name


def resolve_evidence_source(
    config: CaseConfig,
    filename: str,
    *,
    table_root: Path | None = None,
) -> Path:
    """Resolve current aggregate tables first, then the tracked archive."""

    candidates: list[Path] = []
    if table_root is not None:
        candidates.append(Path(table_root) / filename)
    else:
        candidates.extend(
            [
                config.tables_dir / filename,
                config.project_root.parent / "reproduction" / "archived" / "application" / filename,
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    checked = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Missing aggregate evidence source {filename}; checked {checked}")


def _safe_records(path: Path, columns: Sequence[str], *, rows: int | None = None) -> list[dict[str, Any]]:
    frame = pd.read_csv(path)
    keep = [column for column in columns if column in frame.columns]
    frame = frame.loc[:, keep]
    if rows is not None:
        frame = frame.head(rows)
    frame = frame.where(pd.notna(frame), None)
    return frame.to_dict(orient="records")


def _ladder_observation(path: Path, rung: str) -> dict[str, Any]:
    frame = pd.read_csv(path)
    row = frame.loc[frame["rung"].astype(str).eq(rung)]
    if len(row) != 1:
        raise ValueError(f"Expected exactly one {rung} row in {path}; found {len(row)}")
    # Keep only measurements. Even seemingly harmless prose such as a method
    # note can encode an author's interpretation and become a latent answer key.
    safe_columns = ["outcome", "estimate", "std_error", "ci95_low", "ci95_high", "p_value"]
    payload = row.loc[:, [column for column in safe_columns if column in row.columns]].iloc[0]
    return {key: (None if pd.isna(value) else value) for key, value in payload.items()}


def _composite_hash(paths: Iterable[Path], content: Any) -> str:
    payload = {
        "sources": [{"name": path.name, "sha256": file_sha256(path)} for path in paths],
        "content": content,
    }
    return sha256_text(canonical_json(payload))


def build_evidence_blocks(
    config: CaseConfig,
    *,
    table_root: Path | None = None,
) -> dict[str, EvidenceBlock]:
    """Build M0--M7 from aggregate artifacts without answer-bearing columns."""

    ladder_path = resolve_evidence_source(config, "deterministic_ladder.csv", table_root=table_root)
    blocks: dict[str, EvidenceBlock] = {}
    for index in range(4):
        rung = f"L{index}"
        observation = _ladder_observation(ladder_path, rung)
        content: dict[str, Any] = {"aggregate_observation": observation}
        if index == 0:
            content["case"] = {
                "case_id": config.case_id,
                "event_date_utc": str(config.raw["event_date"]),
            }
        blocks[f"M{index}"] = EvidenceBlock(
            evidence_id=f"M{index}",
            introduced_at_rung=rung,
            source_artifact=_relative_source(ladder_path, config),
            source_sha256=file_sha256(ladder_path),
            content=content,
        )

    event_path = resolve_evidence_source(config, "event_study_coefficients.csv", table_root=table_root)
    event_records = _safe_records(
        event_path,
        ["rel_week", "coef", "std_error", "ci95_low", "ci95_high", "reference_week"],
        rows=40,
    )
    pre_rows = [row for row in event_records if row.get("rel_week") is not None and float(row["rel_week"]) < -1]
    excludes_zero = sum(
        1
        for row in pre_rows
        if row.get("ci95_low") is not None
        and row.get("ci95_high") is not None
        and (float(row["ci95_low"]) > 0 or float(row["ci95_high"]) < 0)
    )
    m4_content = {
        "event_study_coefficients": event_records,
        "neutral_preperiod_summary": {
            "preperiod_coefficients": len(pre_rows),
            "preperiod_intervals_excluding_zero": excludes_zero,
        },
    }
    blocks["M4"] = EvidenceBlock(
        evidence_id="M4",
        introduced_at_rung="L4",
        source_artifact=_relative_source(event_path, config),
        source_sha256=file_sha256(event_path),
        content=m4_content,
    )

    stakeholder_path = resolve_evidence_source(
        config, "result1_stakeholder_metric_battery.csv", table_root=table_root
    )
    stakeholder_records = _safe_records(
        stakeholder_path,
        ["dimension", "stakeholder", "metric", "unit", "value", "value_label"],
        rows=40,
    )
    blocks["M5"] = EvidenceBlock(
        evidence_id="M5",
        introduced_at_rung="L5",
        source_artifact=_relative_source(stakeholder_path, config),
        source_sha256=file_sha256(stakeholder_path),
        content={"stakeholder_metrics": stakeholder_records},
    )

    uncertainty_path = resolve_evidence_source(config, "wild_cluster_bootstrap.json", table_root=table_root)
    uncertainty = json.loads(uncertainty_path.read_text(encoding="utf-8"))
    blocks["M6"] = EvidenceBlock(
        evidence_id="M6",
        introduced_at_rung="L6",
        source_artifact=_relative_source(uncertainty_path, config),
        source_sha256=file_sha256(uncertainty_path),
        content={"few_cluster_inference": uncertainty},
    )

    frequency_path = resolve_evidence_source(
        config, "result1_frequency_sensitivity.csv", table_root=table_root
    )
    frequency_records = _safe_records(
        frequency_path,
        ["layer", "unit", "outcome", "estimate", "ci95_low", "ci95_high"],
        rows=40,
    )
    expected_sources = [
        "deterministic_ladder.csv",
        "event_study_coefficients.csv",
        "result1_stakeholder_metric_battery.csv",
        "wild_cluster_bootstrap.json",
        "result1_frequency_sensitivity.csv",
        "data_availability_ledger.csv",
    ]
    availability: list[dict[str, str]] = []
    for filename in expected_sources:
        try:
            path = resolve_evidence_source(config, filename, table_root=table_root)
            availability.append({"aggregate_artifact": filename, "availability": "available", "sha256": file_sha256(path)})
        except FileNotFoundError:
            availability.append({"aggregate_artifact": filename, "availability": "not_available", "sha256": ""})
    m7_content = {
        "frequency_and_data_richness": frequency_records,
        "aggregate_artifact_availability": availability,
    }
    blocks["M7"] = EvidenceBlock(
        evidence_id="M7",
        introduced_at_rung="L7",
        source_artifact=_relative_source(frequency_path, config),
        source_sha256=_composite_hash([frequency_path], m7_content),
        content=m7_content,
    )
    if tuple(blocks) != EVIDENCE_IDS:
        raise AssertionError(f"Evidence block order mismatch: {tuple(blocks)}")
    return blocks


def factorial_condition(bits: str) -> Condition:
    if len(bits) != 4 or set(bits).difference({"0", "1"}):
        raise ValueError(f"Invalid 2^4 factorial bit string: {bits}")
    ids = list(EVIDENCE_IDS[:4])
    ids.extend(f"M{index + 4}" for index, bit in enumerate(bits) if bit == "1")
    canonical = next((rung for rung, value in CANONICAL_FACTORIAL.items() if value == bits), "")
    return Condition(
        condition_id=f"F_{bits}",
        family="factorial",
        canonical_rung=canonical,
        factorial_bits=bits,
        present_evidence_ids=tuple(ids),
    )


def _primary_low_rung(rung: str) -> Condition:
    index = int(rung[1:])
    if index not in {0, 1, 2}:
        raise ValueError(rung)
    return Condition(
        condition_id=f"P_{rung}",
        family="canonical",
        canonical_rung=rung,
        factorial_bits="",
        present_evidence_ids=tuple(EVIDENCE_IDS[: index + 1]),
    )


def control_condition(kind: str, rung: str) -> Condition:
    if rung not in CANONICAL_RUNG_TO_CONDITION:
        raise ValueError(rung)
    if kind == "legacy_leaky":
        present = tuple(EVIDENCE_IDS[: int(rung[1:]) + 1])
        return Condition(
            condition_id=f"CTRL_LEAKY_{rung}",
            family="legacy_leaky_positive_control",
            canonical_rung=rung,
            factorial_bits="",
            present_evidence_ids=present,
            leakage_expected=True,
        )
    if kind == "evidence_free":
        return Condition(
            condition_id=f"CTRL_EMPTY_{rung}",
            family="evidence_free_negative_control",
            canonical_rung=rung,
            factorial_bits="",
            present_evidence_ids=(),
        )
    raise ValueError(kind)


def build_conditions(selection: str) -> list[Condition]:
    if selection not in {"canonical", "factorial", "controls", "all"}:
        raise ValueError(f"Unknown condition selection: {selection}")
    low = [_primary_low_rung(f"L{i}") for i in range(3)]
    factorial = [factorial_condition(f"{value:04b}") for value in range(16)]
    canonical_factorial = [
        factorial_condition(CANONICAL_FACTORIAL[f"L{i}"]) for i in range(3, 8)
    ]
    controls = [
        control_condition(kind, f"L{rung}")
        for kind in ("legacy_leaky", "evidence_free")
        for rung in range(8)
    ]
    if selection == "canonical":
        return low + canonical_factorial
    if selection == "factorial":
        return factorial
    if selection == "controls":
        return controls
    return low + factorial + controls


SLOT_CATALOGUE = {
    "M0": "treated-series operational summary",
    "M1": "control-group comparison",
    "M2": "fixed-effects adjustment",
    "M3": "dynamic estimator summary",
    "M4": "pre-period/event-study diagnostics",
    "M5": "stakeholder-disaggregated outcomes",
    "M6": "few-cluster uncertainty",
    "M7": "coverage, frequency, and scope information",
}


SYSTEM_PROMPT = """You are an independent empirical-evidence auditor, not a coauthor.
Use only the supplied aggregate evidence. Distinguish an operational change from a causal effect and from
stakeholder welfare. Absence of evidence is not evidence of no effect. Cite only evidence IDs that are actually
present. Report absent slots in missing_evidence_slots. Return only one JSON object conforming to the supplied
schema; do not add prose outside JSON."""


def _evidence_payload(condition: Condition, blocks: Mapping[str, EvidenceBlock]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for evidence_id in condition.present_evidence_ids:
        block = blocks[evidence_id]
        payload.append(
            {
                "evidence_id": block.evidence_id,
                "source_sha256": block.source_sha256,
                "content": block.content,
            }
        )
    return payload


def assert_no_primary_leakage(system_prompt: str, user_prompt: str) -> None:
    combined = f"{system_prompt}\n{user_prompt}".lower()
    found = [marker for marker in PRIMARY_FORBIDDEN_MARKERS if marker in combined]
    if found:
        raise ValueError(f"Primary prompt contains answer-bearing marker(s): {found}")


def build_blind_prompt(condition: Condition, blocks: Mapping[str, EvidenceBlock]) -> PromptPacket:
    if condition.leakage_expected:
        raise ValueError("Use build_legacy_leaky_prompt for the registered positive control")
    evidence = _evidence_payload(condition, blocks)
    evidence_hash = sha256_text(canonical_json(evidence))
    audit_packet_id = f"AUDIT-{sha256_text(condition.condition_id + evidence_hash)[:16]}"
    user_payload = {
        "audit_packet_id": audit_packet_id,
        "task": "Assess whether the supplied evidence supports market-causal, operational, and stakeholder claims.",
        "evidence_slot_catalogue": SLOT_CATALOGUE,
        "supplied_evidence": evidence,
        "output_schema": OUTPUT_SCHEMA,
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False, sort_keys=True, indent=2)
    assert_no_primary_leakage(SYSTEM_PROMPT, user_prompt)
    digest = sha256_text(f"{SYSTEM_PROMPT}\n---USER---\n{user_prompt}")
    return PromptPacket(SYSTEM_PROMPT, user_prompt, digest, evidence_hash, audit_packet_id)


def build_legacy_leaky_prompt(
    config: CaseConfig,
    condition: Condition,
    *,
    table_root: Path | None = None,
) -> PromptPacket:
    if not condition.leakage_expected:
        raise ValueError("Legacy leaky prompt requested for a non-leaky condition")
    rung = condition.canonical_rung
    system_path = config.project_root / "prompts" / f"{rung}_system.md"
    user_path = config.project_root / "prompts" / f"{rung}_user.md"
    system_prompt = system_path.read_text(encoding="utf-8").strip()
    old_user = user_path.read_text(encoding="utf-8").strip()
    ladder_path = resolve_evidence_source(config, "deterministic_ladder.csv", table_root=table_root)
    ladder = pd.read_csv(ladder_path)
    rung_index = int(rung[1:])
    old_slice = ladder.loc[ladder["rung"].str[1:].astype(int).le(rung_index)]
    legacy_columns = [
        "rung",
        "outcome",
        "estimate",
        "ci95_low",
        "ci95_high",
        "p_value",
        "worked_decision",
        "notes",
    ]
    legacy_csv = old_slice.loc[:, [column for column in legacy_columns if column in old_slice]].to_csv(index=False)
    user_prompt = (
        f"{old_user}\n\n[deterministic ladder available up to this rung]\n{legacy_csv}\n"
        f"Return only JSON matching this schema:\n{json.dumps(OUTPUT_SCHEMA, sort_keys=True)}"
    )
    evidence_hash = sha256_text(legacy_csv)
    audit_packet_id = f"LEAKY-{rung}-{evidence_hash[:12]}"
    digest = sha256_text(f"{system_prompt}\n---USER---\n{user_prompt}")
    return PromptPacket(system_prompt, user_prompt, digest, evidence_hash, audit_packet_id)


def build_prompt_packet(
    config: CaseConfig,
    condition: Condition,
    blocks: Mapping[str, EvidenceBlock],
    *,
    table_root: Path | None = None,
) -> PromptPacket:
    if condition.leakage_expected:
        return build_legacy_leaky_prompt(config, condition, table_root=table_root)
    return build_blind_prompt(condition, blocks)


def build_call_registry(
    *,
    config: CaseConfig,
    model_specs: Sequence[Mapping[str, Any]],
    conditions: Sequence[Condition],
    prompt_packets: Mapping[str, PromptPacket],
    runs_per_cell: int,
    control_repeats: int,
    random_seed: int,
) -> pd.DataFrame:
    if runs_per_cell < 1 or control_repeats < 1:
        raise ValueError("Run counts must be positive")
    rows: list[dict[str, Any]] = []
    for model in model_specs:
        for condition in conditions:
            repeats = control_repeats if condition.family.endswith("control") else runs_per_cell
            packet = prompt_packets[condition.condition_id]
            for run_id in range(1, repeats + 1):
                stable_key = f"{EXPERIMENT_VERSION}|{model['model_spec_id']}|{condition.condition_id}|{run_id}"
                call_id = f"C-{sha256_text(stable_key)[:20]}"
                rows.append(
                    {
                        "call_id": call_id,
                        "experiment_version": EXPERIMENT_VERSION,
                        "case_id": config.case_id,
                        "model_spec_id": model["model_spec_id"],
                        "provider": model["provider"],
                        "requested_model": model["model"],
                        "condition_id": condition.condition_id,
                        "condition_family": condition.family,
                        "canonical_rung": condition.canonical_rung,
                        "factorial_bits": condition.factorial_bits,
                        "present_evidence_ids": ";".join(condition.present_evidence_ids),
                        "missing_evidence_ids": ";".join(condition.missing_evidence_ids),
                        "leakage_expected": int(condition.leakage_expected),
                        "run_id": run_id,
                        "seed": random_seed + int(sha256_text(stable_key)[:8], 16),
                        "status": "registered_not_run",
                        "prompt_hash": packet.prompt_hash,
                        "evidence_hash": packet.evidence_hash,
                        "audit_packet_id": packet.audit_packet_id,
                        "started_at_utc": "",
                        "completed_at_utc": "",
                        "returned_model": "",
                        "model_digest": "",
                        "input_tokens": "",
                        "output_tokens": "",
                        "reasoning_tokens": "",
                        "estimated_cost_usd": "",
                        "parse_repair_attempted": 0,
                        "error": "",
                    }
                )
    random.Random(random_seed).shuffle(rows)
    return pd.DataFrame(rows)


def condition_lookup(conditions: Sequence[Condition]) -> dict[str, Condition]:
    lookup = {condition.condition_id: condition for condition in conditions}
    if len(lookup) != len(conditions):
        raise ValueError("Duplicate condition IDs")
    return lookup


def validate_registry_shape(frame: pd.DataFrame, *, selection: str, model_count: int, runs: int, controls: int) -> None:
    duplicates = frame.duplicated(["model_spec_id", "condition_id", "run_id"])
    if duplicates.any():
        raise ValueError("Duplicate registered model/condition/run slots")
    if selection == "all" and model_count == 3 and runs == 10 and controls == 3 and len(frame) != 714:
        raise ValueError(f"Registered {len(frame)} calls; the preregistered all-condition design requires 714")
