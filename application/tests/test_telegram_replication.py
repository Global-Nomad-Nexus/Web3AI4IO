from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from trustworthy_launchpads.agentic_v2_providers import (
    build_request_body,
    validate_response_against_schema,
)
from trustworthy_launchpads.telegram_replication import (
    CONDITIONS,
    EVIDENCE_IDS,
    FORBIDDEN_PROMPT_MARKERS,
    OUTPUT_SCHEMA,
    SCHEMA_NAME,
    build_evidence_blocks,
    build_prompt_packet,
    build_registry,
)


REPO = Path(__file__).resolve().parents[2]


def load_script(name: str):
    path = REPO / "application" / "scripts" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


MODELS = [
    {"model_spec_id": "gpt_5_6_terra", "provider": "OpenAI", "adapter": "openai_responses", "model": "gpt-5.6-terra", "endpoint": "x"},
    {"model_spec_id": "deepseek_v4_pro", "provider": "DeepSeek", "adapter": "deepseek_chat", "model": "deepseek-v4-pro", "endpoint": "x"},
    {"model_spec_id": "qwen3_14b", "provider": "Qwen", "adapter": "ollama_chat", "model": "qwen3:14b", "endpoint": "x"},
]


class TelegramReplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blocks = build_evidence_blocks(REPO)
        cls.packets = {condition: build_prompt_packet(condition, cls.blocks) for condition in CONDITIONS}

    def test_two_conditions_have_expected_evidence(self):
        self.assertEqual(CONDITIONS["T0_ASSOCIATION"], ("T0",))
        self.assertEqual(CONDITIONS["T1_BOUNDARY_COMPLETE"], ("T0", "T1"))

    def test_prompt_has_no_archived_claim_boundary(self):
        for packet in self.packets.values():
            combined = (packet.system_prompt + packet.user_prompt).lower()
            self.assertFalse([marker for marker in FORBIDDEN_PROMPT_MARKERS if marker in combined])

    def test_t0_omits_t1_numbers(self):
        prompt = self.packets["T0_ASSOCIATION"].user_prompt
        self.assertNotIn('"supported": 0', prompt)
        self.assertNotIn('"screened": 6', prompt)

    def test_registry_is_exactly_60(self):
        registry = build_registry(MODELS, self.packets, runs=10, seed=20260826)
        self.assertEqual(len(registry), 60)
        self.assertEqual(set(registry.groupby(["model_spec_id", "condition_id"]).size()), {10})
        self.assertEqual(set(registry.groupby("model_spec_id").size()), {20})

    def test_registry_is_seed_deterministic(self):
        left = build_registry(MODELS, self.packets, runs=10, seed=20260826)
        right = build_registry(MODELS, self.packets, runs=10, seed=20260826)
        pd.testing.assert_frame_equal(left, right)

    def test_case_specific_schema_accepts_gold_boundary(self):
        payload = {
            "causal_status": "not_identified", "predictive_association_status": "supported_positive",
            "supporting_evidence_ids": ["T0"], "missing_evidence_slots": ["T1"],
            "confidence": 0.7, "short_claim": "Predictive association; causal effect is not identified.",
        }
        self.assertEqual(validate_response_against_schema(payload, output_schema=OUTPUT_SCHEMA, evidence_ids=EVIDENCE_IDS), payload)

    def test_case_specific_schema_rejects_duplicate_ids(self):
        payload = {
            "causal_status": "not_identified", "predictive_association_status": "supported_positive",
            "supporting_evidence_ids": ["T0", "T0"], "missing_evidence_slots": ["T1"],
            "confidence": 0.7, "short_claim": "Claim",
        }
        with self.assertRaises(ValueError):
            validate_response_against_schema(payload, output_schema=OUTPUT_SCHEMA, evidence_ids=EVIDENCE_IDS)

    def test_provider_body_injects_schema_without_changing_default_api(self):
        body = build_request_body(MODELS[0], self.packets["T0_ASSOCIATION"], output_schema=OUTPUT_SCHEMA, schema_name=SCHEMA_NAME)
        self.assertEqual(body["text"]["format"]["name"], SCHEMA_NAME)
        self.assertEqual(body["text"]["format"]["schema"], OUTPUT_SCHEMA)

    def test_scoring_gold_metrics(self):
        scorer = load_script("score_telegram_replication.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = build_registry(MODELS, self.packets, runs=10, seed=20260826)
            registry["status"] = "ok"
            registry.to_csv(root / "run_registry.csv", index=False)
            for row in registry.to_dict(orient="records"):
                call = root / "calls" / row["call_id"]
                call.mkdir(parents=True)
                (call / "parsed.json").write_text(json.dumps({
                    "causal_status": "not_identified", "predictive_association_status": "supported_positive",
                    "supporting_evidence_ids": row["present_evidence_ids"].split(";"),
                    "missing_evidence_slots": [x for x in row["missing_evidence_ids"].split(";") if x],
                    "confidence": 0.5, "short_claim": "Predictive, not causal.",
                }))
            calls, cells, deltas = scorer.score(root)
            self.assertEqual(int(calls["correct_predictive_not_causal_boundary"].sum()), 60)
            self.assertEqual(set(cells["correct_predictive_not_causal_boundary_x"]), {10})
            self.assertEqual(set(deltas["correct_predictive_not_causal_boundary_difference"]), {0.0})

    def test_status_denominator_conservation(self):
        registry = build_registry(MODELS, self.packets, runs=10, seed=20260826)
        self.assertEqual(int(registry.groupby(["model_spec_id", "condition_id"]).size().sum()), 60)


if __name__ == "__main__":
    unittest.main()
