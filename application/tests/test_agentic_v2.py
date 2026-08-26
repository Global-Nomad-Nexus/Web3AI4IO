from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.agentic_v2 import (
    CANONICAL_RUNG_TO_CONDITION,
    EVIDENCE_IDS,
    PRIMARY_FORBIDDEN_MARKERS,
    PromptPacket,
    assert_no_primary_leakage,
    build_blind_prompt,
    build_call_registry,
    build_conditions,
    build_evidence_blocks,
    build_prompt_packet,
    validate_registry_shape,
)
from trustworthy_launchpads.agentic_v2_providers import (
    ProviderError,
    _request_json,
    _verified_ssl_context,
    extract_json_object,
    invoke,
    preflight,
    redact_text,
    repair_packet,
    resolve_endpoint,
    validate_structured_response,
)
from trustworthy_launchpads.agentic_v2_scoring import (
    SCORE_METRICS,
    factorial_effects,
    load_gold_contract,
    matched_factorial_effects,
    matched_factorial_pairs,
    score_parsed_response,
    summarize_cells,
)
from trustworthy_launchpads.io import load_config


def load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_script("run_agentic_v2")
LAUNCHER = load_script("run_agentic_v2_all")


VALID_RESPONSE = {
    "market_causal_status": "not_identified",
    "operational_status": "supported",
    "stakeholder_status": "not_identified",
    "supporting_evidence_ids": ["M0"],
    "missing_evidence_slots": ["M1", "M2", "M3", "M4", "M5", "M6", "M7"],
    "confidence": 0.6,
    "short_claim": "Operational activity is observed, while causal and stakeholder claims are not identified.",
}


class AgenticV2FixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.table_root = Path(self.temporary.name)
        ladder_rows = []
        for index in range(8):
            ladder_rows.append(
                {
                    "rung": f"L{index}",
                    "component_added": f"component-{index}",
                    "outcome": "aggregate outcome",
                    "estimate": 0.1 * index,
                    "std_error": 0.1,
                    "ci95_low": -0.1,
                    "ci95_high": 0.3,
                    "p_value": 0.2,
                    "worked_decision": "SECRET_GOLD_DECISION",
                    "method": f"method-{index}",
                    "notes": f"SECRET_NOTE_{index}",
                }
            )
        pd.DataFrame(ladder_rows).to_csv(self.table_root / "deterministic_ladder.csv", index=False)
        pd.DataFrame(
            [
                {
                    "rel_week": -3,
                    "coef": 0.7,
                    "std_error": 0.2,
                    "ci95_low": 0.3,
                    "ci95_high": 1.1,
                    "reference_week": -1,
                },
                {
                    "rel_week": 0,
                    "coef": 0.4,
                    "std_error": 0.2,
                    "ci95_low": 0.0,
                    "ci95_high": 0.8,
                    "reference_week": -1,
                },
            ]
        ).to_csv(self.table_root / "event_study_coefficients.csv", index=False)
        pd.DataFrame(
            [
                {
                    "dimension": "Security",
                    "stakeholder": "Retail",
                    "metric": "risk rate",
                    "unit": "probability",
                    "value": 0.4,
                    "value_label": "40%",
                    "status": "SECRET_STATUS",
                    "interpretation": "SECRET_INTERPRETATION",
                }
            ]
        ).to_csv(self.table_root / "result1_stakeholder_metric_battery.csv", index=False)
        (self.table_root / "wild_cluster_bootstrap.json").write_text(
            json.dumps(
                {
                    "cluster_count": 4,
                    "estimate": 0.2,
                    "wild_bootstrap_ci95_low": -0.5,
                    "wild_bootstrap_ci95_high": 0.9,
                    "wild_bootstrap_p_value": 0.5,
                }
            ),
            encoding="utf-8",
        )
        pd.DataFrame(
            [
                {
                    "layer": "daily",
                    "unit": "protocol-day",
                    "outcome": "volume",
                    "estimate": 0.2,
                    "ci95_low": -0.1,
                    "ci95_high": 0.5,
                    "decision": "SECRET_DECISION",
                    "interpretation": "SECRET_SCOPE_ANSWER",
                }
            ]
        ).to_csv(self.table_root / "result1_frequency_sensitivity.csv", index=False)
        self.config = load_config(ROOT / "configs" / "pumpswap_case.json")
        self.blocks = build_evidence_blocks(self.config, table_root=self.table_root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_evidence_blocks_are_answer_free_and_cumulative(self) -> None:
        serialized = json.dumps({key: value.as_dict() for key, value in self.blocks.items()})
        for secret in (
            "SECRET_GOLD_DECISION",
            "SECRET_NOTE",
            "SECRET_STATUS",
            "SECRET_INTERPRETATION",
            "SECRET_SCOPE_ANSWER",
        ):
            self.assertNotIn(secret, serialized)
        canonical = build_conditions("canonical")
        self.assertEqual([len(item.present_evidence_ids) for item in canonical], list(range(1, 9)))
        for condition in canonical:
            expected = tuple(EVIDENCE_IDS[: len(condition.present_evidence_ids)])
            self.assertEqual(condition.present_evidence_ids, expected)

    def test_factorial_is_complete_and_canonical_path_is_embedded(self) -> None:
        factorial = build_conditions("factorial")
        self.assertEqual(len(factorial), 16)
        self.assertEqual({item.factorial_bits for item in factorial}, {f"{value:04b}" for value in range(16)})
        by_id = {item.condition_id: item for item in factorial}
        for rung, condition_id in CANONICAL_RUNG_TO_CONDITION.items():
            if rung in {"L0", "L1", "L2"}:
                continue
            self.assertEqual(by_id[condition_id].canonical_rung, rung)

    def test_primary_prompt_is_blind_and_removed_blocks_leave_no_content(self) -> None:
        factorial = {item.condition_id: item for item in build_conditions("factorial")}
        empty_high_blocks = build_blind_prompt(factorial["F_0000"], self.blocks)
        full = build_blind_prompt(factorial["F_1111"], self.blocks)
        self.assertNotIn("risk rate", empty_high_blocks.user_prompt)
        self.assertNotIn("cluster_count", empty_high_blocks.user_prompt)
        self.assertIn("risk rate", full.user_prompt)
        self.assertIn("cluster_count", full.user_prompt)
        self.assertNotIn("SECRET_", full.user_prompt)
        assert_no_primary_leakage(full.system_prompt, full.user_prompt)
        for marker in PRIMARY_FORBIDDEN_MARKERS:
            self.assertNotIn(marker, full.user_prompt.lower())

    def test_legacy_control_is_isolated_and_explicitly_leaky(self) -> None:
        condition = next(
            item for item in build_conditions("controls") if item.condition_id == "CTRL_LEAKY_L2"
        )
        packet = build_prompt_packet(
            self.config, condition, self.blocks, table_root=self.table_root
        )
        self.assertTrue(condition.leakage_expected)
        self.assertIn("worked_decision", packet.user_prompt)
        self.assertIn("SECRET_GOLD_DECISION", packet.user_prompt)

    def test_registered_default_design_has_714_unique_slots(self) -> None:
        conditions = build_conditions("all")
        packets = {
            item.condition_id: build_prompt_packet(
                self.config, item, self.blocks, table_root=self.table_root
            )
            for item in conditions
        }
        models = [
            {"model_spec_id": f"m{index}", "provider": "p", "model": f"model-{index}"}
            for index in range(3)
        ]
        registry = build_call_registry(
            config=self.config,
            model_specs=models,
            conditions=conditions,
            prompt_packets=packets,
            runs_per_cell=10,
            control_repeats=3,
            random_seed=7,
        )
        validate_registry_shape(registry, selection="all", model_count=3, runs=10, controls=3)
        self.assertEqual(len(registry), 714)
        self.assertFalse(registry.duplicated(["model_spec_id", "condition_id", "run_id"]).any())
        self.assertEqual(set(registry["status"]), {"registered_not_run"})

    def test_resume_preserves_completed_slot_without_duplication(self) -> None:
        condition = build_conditions("canonical")[0]
        packet = build_blind_prompt(condition, self.blocks)
        fresh = build_call_registry(
            config=self.config,
            model_specs=[{"model_spec_id": "m", "provider": "p", "model": "x"}],
            conditions=[condition],
            prompt_packets={condition.condition_id: packet},
            runs_per_cell=1,
            control_repeats=1,
            random_seed=1,
        )
        old = fresh.copy()
        old.loc[:, "status"] = "ok"
        path = self.table_root / "registry.csv"
        old.to_csv(path, index=False)
        resumed = RUNNER.merge_resume(fresh, path, resume=True)
        self.assertEqual(len(resumed), 1)
        self.assertEqual(resumed.iloc[0]["status"], "ok")

    def test_json_writer_serializes_pandas_inferred_integer_scalars(self) -> None:
        value = pd.Series([4413], dtype="int64").iloc[0]
        path = self.table_root / "numpy_scalar.json"
        RUNNER.write_json(path, {"input_tokens": value})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"input_tokens": 4413})

    def test_resume_preflights_only_models_with_pending_calls(self) -> None:
        registry = pd.DataFrame(
            [
                {"model_spec_id": "complete", "condition_id": "P_L0", "status": "ok"},
                {
                    "model_spec_id": "pending",
                    "condition_id": "P_L0",
                    "status": "registered_not_run",
                },
            ]
        )
        allowed = {("complete", "P_L0"), ("pending", "P_L0")}
        self.assertEqual(
            RUNNER.pending_model_ids(registry, allowed, resume=True), {"pending"}
        )

    def test_interrupted_running_slot_is_atomically_returned_to_not_run(self) -> None:
        condition = build_conditions("canonical")[0]
        packet = build_blind_prompt(condition, self.blocks)
        registry = build_call_registry(
            config=self.config,
            model_specs=[{"model_spec_id": "m", "provider": "p", "model": "x"}],
            conditions=[condition],
            prompt_packets={condition.condition_id: packet},
            runs_per_cell=1,
            control_repeats=1,
            random_seed=1,
        )
        registry.loc[:, "status"] = "running"
        registry.loc[:, "started_at_utc"] = "2026-01-01T00:00:00+00:00"
        path = self.table_root / "interrupted.csv"
        registry.to_csv(path, index=False)
        self.assertEqual(LAUNCHER.normalize_interrupted_registry(path), 1)
        recovered = pd.read_csv(path, keep_default_na=False)
        self.assertEqual(recovered.iloc[0]["status"], "registered_not_run")
        self.assertEqual(recovered.iloc[0]["started_at_utc"], "")
        self.assertEqual(LAUNCHER.normalize_interrupted_registry(path), 0)

    def test_one_click_launcher_selects_a_compatible_python(self) -> None:
        with mock.patch.dict(os.environ, {"AGENTIC_V2_PYTHON": sys.executable}):
            selected = LAUNCHER.select_compatible_python()
        self.assertEqual(Path(selected).resolve(), Path(sys.executable).resolve())

    def test_gold_scoring_and_status_denominators_are_conserved(self) -> None:
        gold = load_gold_contract(ROOT / "configs" / "agentic_v2_gold.json")
        row = {
            "present_evidence_ids": "M0",
            "condition_id": "P_L0",
        }
        score = score_parsed_response(row, VALID_RESPONSE, gold)
        self.assertEqual(score["unsafe_causal_affirmation"], 0)
        self.assertEqual(score["unsupported_welfare_claim"], 0)
        self.assertEqual(score["correct_boundary"], 1)
        records = []
        for run_id, status in enumerate(("ok", "parse_failed", "provider_error"), start=1):
            record = {
                "model_spec_id": "m",
                "provider": "p",
                "requested_model": "x",
                "condition_id": "P_L0",
                "condition_family": "canonical",
                "canonical_rung": "L0",
                "factorial_bits": "",
                "status": status,
            }
            for metric in SCORE_METRICS:
                record[metric] = score.get(metric) if status == "ok" else (1 if metric == "parse_failure" and status == "parse_failed" else None)
            records.append(record)
        cells = summarize_cells(pd.DataFrame(records), seed=1, draws=20)
        cell = cells.iloc[0]
        self.assertEqual(cell["registered_runs"], 3)
        self.assertEqual(cell["ok_runs"] + cell["parse_failed_runs"] + cell["provider_error_runs"] + cell["not_run"], 3)

    def test_matched_factorial_has_eight_backgrounds_per_model_factor(self) -> None:
        calls = pd.read_csv(
            ROOT.parent / "reproduction" / "archived" / "application" / "agentic_v2" / "call_scores.csv",
            keep_default_na=False,
        )
        pairs = matched_factorial_pairs(calls)
        counts = pairs.groupby(["model_spec_id", "factor", "metric"])["matched_background"].nunique()
        self.assertTrue(counts.eq(8).all())
        self.assertEqual(len(pairs), 864)

    def test_matched_factorial_preserves_balanced_point_estimates(self) -> None:
        calls = pd.read_csv(
            ROOT.parent / "reproduction" / "archived" / "application" / "agentic_v2" / "call_scores.csv",
            keep_default_na=False,
        )
        legacy = factorial_effects(calls, seed=11, draws=10)
        matched = matched_factorial_effects(calls, seed=11, draws=10)
        legacy = legacy.loc[(legacy.model_spec_id == "pooled") & (legacy.effect_type == "main_effect")]
        merged = legacy.merge(matched.loc[matched.model_spec_id == "pooled"], on=["model_spec_id", "factor", "metric"], suffixes=("_legacy", "_matched"))
        drift = (merged["mean_difference_bit1_minus_bit0_legacy"] - merged["mean_difference_bit1_minus_bit0_matched"]).abs()
        self.assertTrue(drift.le(1e-12).all())


class ProviderAdapterTest(unittest.TestCase):
    def _packet(self) -> PromptPacket:
        return PromptPacket("system", "user", "p" * 64, "e" * 64, "AUDIT-test")

    def test_openai_responses_adapter(self) -> None:
        spec = {
            "model_spec_id": "openai",
            "provider": "OpenAI",
            "adapter": "openai_responses",
            "model": "gpt-5.6-terra",
            "endpoint": "https://api.openai.com/v1/responses",
            "api_key_env": "OPENAI_API_KEY",
        }
        payload = {
            "model": "gpt-5.6-terra",
            "output_text": json.dumps(VALID_RESPONSE),
            "usage": {"input_tokens": 10, "output_tokens": 20, "output_tokens_details": {"reasoning_tokens": 5}},
        }
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), mock.patch(
            "trustworthy_launchpads.agentic_v2_providers._request_json", return_value=payload
        ):
            result = invoke(spec, self._packet())
        parsed = validate_structured_response(extract_json_object(result.response_text))
        self.assertEqual(parsed["market_causal_status"], "not_identified")
        self.assertEqual((result.input_tokens, result.output_tokens, result.reasoning_tokens), (10, 20, 5))
        self.assertFalse(result.request_body["store"])

    def test_openai_gateway_endpoint_override_is_https_and_normalized(self) -> None:
        spec = {
            "endpoint": "https://api.openai.com/v1/responses",
            "endpoint_env": "OPENAI_BASE_URL",
        }
        with mock.patch.dict(
            os.environ,
            {"OPENAI_BASE_URL": "https://gateway.example:3443"},
        ):
            self.assertEqual(
                resolve_endpoint(spec),
                "https://gateway.example:3443/v1/responses",
            )
        with mock.patch.dict(
            os.environ,
            {"OPENAI_BASE_URL": "http://gateway.example"},
        ):
            with self.assertRaisesRegex(ProviderError, "must be an HTTPS base URL"):
                resolve_endpoint(spec)

    def test_deepseek_v4_pro_adapter(self) -> None:
        spec = {
            "model_spec_id": "deepseek",
            "provider": "DeepSeek",
            "adapter": "deepseek_chat",
            "model": "deepseek-v4-pro",
            "endpoint": "https://api.deepseek.com/chat/completions",
            "api_key_env": "DEEPSEEK_API_KEY",
        }
        payload = {
            "model": "deepseek-v4-pro",
            "choices": [{"message": {"content": json.dumps(VALID_RESPONSE)}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 21, "completion_tokens_details": {"reasoning_tokens": 6}},
        }
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}), mock.patch(
            "trustworthy_launchpads.agentic_v2_providers._request_json", return_value=payload
        ):
            result = invoke(spec, self._packet())
        self.assertEqual(validate_structured_response(extract_json_object(result.response_text)), VALID_RESPONSE)
        self.assertEqual(result.request_body["thinking"], {"type": "enabled"})

    def test_ollama_qwen_adapter_and_digest(self) -> None:
        spec = {
            "model_spec_id": "qwen",
            "provider": "Alibaba-Qwen/Ollama",
            "adapter": "ollama_chat",
            "model": "qwen3:14b",
            "endpoint": "http://localhost:11434",
        }
        response = {
            "model": "qwen3:14b",
            "message": {"content": json.dumps(VALID_RESPONSE)},
            "prompt_eval_count": 12,
            "eval_count": 22,
        }
        tags = {"models": [{"name": "qwen3:14b", "digest": "bdbd181c33f2-full", "size": 10}]}
        show = {"model_info": {"qwen3.context_length": 40960}}
        with mock.patch(
            "trustworthy_launchpads.agentic_v2_providers._request_json",
            side_effect=[response, tags, show],
        ):
            result = invoke(spec, self._packet())
        self.assertEqual(result.model_digest, "bdbd181c33f2-full")
        self.assertTrue(result.request_body["think"])
        self.assertEqual(validate_structured_response(extract_json_object(result.response_text)), VALID_RESPONSE)

    def test_ollama_preflight_rejects_context_above_native_limit(self) -> None:
        spec = {
            "model_spec_id": "qwen",
            "provider": "Alibaba-Qwen/Ollama",
            "adapter": "ollama_chat",
            "model": "qwen3:14b",
            "endpoint": "http://localhost:11434",
            "context_length": 50000,
        }
        tags = {"models": [{"name": "qwen3:14b", "digest": "digest", "size": 10}]}
        show = {"model_info": {"qwen3.context_length": 40960}}
        with mock.patch(
            "trustworthy_launchpads.agentic_v2_providers._request_json",
            side_effect=[tags, show],
        ):
            with self.assertRaisesRegex(ProviderError, "exceeds.*native context"):
                preflight(spec)

    def test_repair_prompt_is_format_only(self) -> None:
        packet = repair_packet("{bad json")
        self.assertIn("format repair", packet.system_prompt)
        self.assertNotIn("M0", packet.system_prompt)
        self.assertNotIn("worked_decision", packet.user_prompt)

    def test_transport_timeout_is_a_retryable_provider_error(self) -> None:
        with mock.patch(
            "trustworthy_launchpads.agentic_v2_providers.urllib.request.urlopen",
            side_effect=TimeoutError,
        ):
            with self.assertRaisesRegex(ProviderError, "Timed out.*7 seconds"):
                _request_json("http://localhost:11434/api/chat", body={}, timeout=7)

    def test_tls_context_uses_a_nonempty_verified_ca_store(self) -> None:
        context = _verified_ssl_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, 2)
        self.assertGreater(len(context.get_ca_certs()), 0)

    def test_provider_masked_key_is_redacted(self) -> None:
        message = "Incorrect key: " + "sk" + "-example********suffix"
        cleaned = redact_text(message, [])
        self.assertNotIn("sk-", cleaned)
        self.assertIn("[REDACTED_API_KEY]", cleaned)

    def test_duplicate_evidence_ids_are_rejected_locally(self) -> None:
        duplicate = dict(VALID_RESPONSE)
        duplicate["supporting_evidence_ids"] = ["M0", "M0"]
        with self.assertRaisesRegex(ValueError, "duplicate evidence IDs"):
            validate_structured_response(duplicate)


if __name__ == "__main__":
    unittest.main()
