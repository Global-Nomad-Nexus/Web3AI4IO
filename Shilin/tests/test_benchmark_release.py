from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "benchmark_release" / "data"
_LOCAL_BENCHMARK = (DATA / "events.csv").exists()


@unittest.skipUnless(_LOCAL_BENCHMARK, "local Shilin benchmark tables are not part of the GitHub tree")
class BenchmarkReleaseTest(unittest.TestCase):
    def test_primary_sheets_exist_and_have_claim_boundaries(self) -> None:
        for name in ["events.csv", "metrics_panel.csv", "covariates.csv"]:
            path = DATA / name
            self.assertTrue(path.exists(), name)
            df = pd.read_csv(path)
            self.assertIn("event_id", df.columns)
            self.assertIn("claim_boundary", df.columns)
            self.assertGreater(len(df), 0)

    def test_release_scope_is_shilin_only(self) -> None:
        manifest = json.loads((DATA / "release_manifest.json").read_text(encoding="utf-8"))
        self.assertIn("Shilin", manifest["scope"])
        events = pd.read_csv(DATA / "events.csv")
        self.assertIn("PUMP_PUMPSWAP_MIGRATION_20250320", set(events["event_id"]))
        forbidden = {"PUMP_CREATOR_FEE_20250513"}
        self.assertTrue(forbidden.isdisjoint(set(events["event_id"])))

    def test_metrics_include_platform_and_token_horizon_rows(self) -> None:
        metrics = pd.read_csv(DATA / "metrics_panel.csv")
        self.assertIn("platform_day", set(metrics["unit_type"]))
        self.assertIn("token_horizon", set(metrics["unit_type"]))
        for column in ["buy_count", "sell_count", "first_trade_at", "last_trade_at"]:
            self.assertIn(column, metrics.columns)
        horizons = set(pd.to_numeric(metrics["horizon_days"], errors="coerce").dropna().astype(int))
        self.assertTrue({1, 7, 30}.issubset(horizons))
        boundary = " ".join(metrics["claim_boundary"].dropna().astype(str).head(50))
        self.assertIn("not welfare", boundary)

    def test_covariates_include_social_and_offchain_context(self) -> None:
        covariates = pd.read_csv(DATA / "covariates.csv")
        families = set(covariates["covariate_family"].dropna().astype(str))
        self.assertIn("token_social_metadata", families)
        self.assertIn("community_attention_sentiment", families)
        self.assertIn("rwa_protocol_metadata", families)

    def test_primary_sheet_schema_contract_fields_are_populated(self) -> None:
        required_by_sheet = {
            "events.csv": ["event_id", "platform", "chain", "eligibility_status", "claim_boundary", "source_artifact"],
            "metrics_panel.csv": ["event_id", "unit_id", "unit_type", "platform", "chain", "frequency", "claim_boundary", "source_layer", "status"],
            "covariates.csv": ["event_id", "unit_id", "unit_type", "platform", "chain", "frequency", "covariate_family", "claim_boundary", "source_layer", "status"],
        }
        for sheet, required in required_by_sheet.items():
            df = pd.read_csv(DATA / sheet)
            for column in required:
                self.assertIn(column, df.columns, f"{sheet}:{column}")
                populated = df[column].fillna("").astype(str).str.strip().ne("")
                self.assertTrue(populated.all(), f"{sheet}:{column}")

    def test_mirror_case_is_registered_but_not_overclaimed(self) -> None:
        mirror = pd.read_csv(DATA / "mirror_case_candidates.csv")
        row = mirror.loc[mirror["candidate_id"].eq("TELEGRAM_GRADUATION_HETEROGENEITY")].iloc[0]
        self.assertEqual(row["current_decision"], "credible_matched_design_not_causal")
        self.assertIn("exogenous", row["blocking_gap"])
        self.assertIn("decoded", row["next_action"])
        ladder = pd.read_csv(DATA / "mirror_case_ladder.csv")
        self.assertTrue({"B4", "B5", "B6"}.issubset(set(ladder["rung"])))
        matched = ladder.loc[ladder["rung"].eq("B4")].iloc[0]
        self.assertEqual(matched["decision"], "credible_matched_design_not_causal")
        self.assertIn("predictive", matched["claim_boundary"])
        timing = ladder.loc[ladder["rung"].eq("B5")].iloc[0]
        self.assertIn("timing", timing["claim_boundary"].lower())
        final = ladder.loc[ladder["rung"].eq("B6")].iloc[0]
        self.assertEqual(final["decision"], "credible_mirror_signal_not_final_causal_case")
        self.assertIn("not as a completed causal", final["claim_boundary"])

        design = pd.read_csv(DATA / "telegram_mirror_design.csv")
        self.assertIn("D1_coarsened_exact_match", set(design["stage"]))
        self.assertIn("D6a_immediate_5m_placebo_like_check", set(design["stage"]))
        self.assertIn("D7_negative_control_detection_lag", set(design["stage"]))
        shocks = pd.read_csv(DATA / "telegram_shock_candidates.csv")
        self.assertGreaterEqual(len(shocks), 1)
        self.assertIn("supported_for_exposure_design", shocks.columns)
        exposure = pd.read_csv(DATA / "telegram_exposure_design.csv")
        self.assertIn("shock_id", exposure.columns)
        d1 = design.loc[design["stage"].eq("D1_coarsened_exact_match")].iloc[0]
        self.assertEqual(d1["decision"], "credible_matched_association_not_causal")
        self.assertGreater(float(d1["n_treated"]), 1000)
        self.assertGreater(float(d1["effect"]), 0)

    def test_cross_chain_clanker_base_is_accepted_but_bounded(self) -> None:
        events = pd.read_csv(DATA / "events.csv")
        event = events.loc[events["event_id"].eq("CLANKER_SNIPER_DECAY_V41_BASE_20250826")].iloc[0]
        self.assertEqual(event["eligibility_status"], "accepted")
        self.assertIn("first_onchain", event["activation_evidence_type"])
        self.assertTrue(str(event["activation_transaction_hash"]).startswith("0x"))
        self.assertIn("not yet a platform-wide causal replication", event["claim_boundary"])

        metrics = pd.read_csv(DATA / "metrics_panel.csv")
        base = metrics.loc[metrics["event_id"].eq("CLANKER_SNIPER_DECAY_V41_BASE_20250826")]
        self.assertEqual(set(base["chain"]), {"Base"})
        self.assertGreaterEqual(base["unit_id"].nunique(), 12)
        self.assertGreaterEqual(len(base), 36)
        horizons = set(pd.to_numeric(base["horizon_days"], errors="coerce").dropna().astype(int))
        self.assertTrue({1, 7, 30}.issubset(horizons))
        self.assertIn("early_sender_concentration_top10", base.columns)
        self.assertIn("holder_concentration_top10", base.columns)
        self.assertIn("holder_count", base.columns)
        holder = pd.to_numeric(base["holder_concentration_top10"], errors="coerce").dropna()
        self.assertGreater(len(holder), 0)

        cross_chain = pd.read_csv(DATA / "cross_chain_event_candidates.csv")
        row = cross_chain.loc[cross_chain["candidate_id"].eq("CLANKER_SNIPER_DECAY_V41_BASE")].iloc[0]
        self.assertEqual(row["priority"], "high")
        self.assertIn("accepted", row["status"])
        self.assertIn("Base", row["chain"])
        self.assertIn("full holder reconstruction", row["next_action"])

    def test_base_full_cohort_manifest_is_release_ready(self) -> None:
        manifest = pd.read_csv(DATA / "clanker_base_full_cohort_manifest.csv")
        self.assertGreaterEqual(manifest["token_id"].nunique(), 10_000)
        self.assertEqual(
            manifest.loc[manifest["cohort_side"].eq("post_v4_1_treated"), "token_id"].nunique(),
            manifest.loc[manifest["cohort_side"].eq("pre_v4_0_control"), "token_id"].nunique(),
        )
        self.assertIn("max_horizon_end_block", manifest.columns)
        self.assertIn("swap_query_key", manifest.columns)
        self.assertIn("transfer_query_key", manifest.columns)

        expected = pd.read_csv(DATA / "clanker_base_full_cohort_expected_horizons.csv")
        self.assertEqual(len(expected), manifest["token_id"].nunique() * 3)
        horizons = set(pd.to_numeric(expected["horizon_days"], errors="coerce").dropna().astype(int))
        self.assertEqual(horizons, {1, 7, 30})

        swaps = pd.read_csv(DATA / "clanker_base_full_cohort_pool_query_bounds.csv")
        transfers = pd.read_csv(DATA / "clanker_base_full_cohort_transfer_query_bounds.csv")
        self.assertEqual(len(swaps), len(manifest))
        self.assertEqual(len(transfers), len(manifest))
        self.assertIn("required_import_columns", swaps.columns)
        self.assertIn("required_import_columns", transfers.columns)

        contract = pd.read_csv(DATA / "clanker_base_full_cohort_import_contract.csv")
        self.assertTrue({"poolmanager_swaps", "erc20_transfers"}.issubset(set(contract["import_name"])))
        self.assertIn("run_clanker_base_validation.py", " ".join(contract["consumer_command"].astype(str)))

        coverage = pd.read_csv(DATA / "clanker_base_full_cohort_import_coverage.csv")
        self.assertTrue({"poolmanager_swaps", "erc20_transfers"}.issubset(set(coverage["coverage_type"])))
        self.assertIn("coverage_status", coverage.columns)

    def test_base_causal_diagnostics_are_claim_bounded(self) -> None:
        diagnostics = pd.read_csv(DATA / "clanker_base_causal_diagnostics.csv")
        self.assertGreater(len(diagnostics), 0)
        self.assertTrue({1, 7, 30}.issubset(set(pd.to_numeric(diagnostics["horizon_days"], errors="coerce").astype(int))))
        self.assertIn("att_mean_pair_diff", diagnostics.columns)
        self.assertTrue(diagnostics["sample_status"].astype(str).str.contains("bounded_or_partial").all())
        boundary = " ".join(diagnostics["claim_boundary"].astype(str).unique())
        self.assertIn("platform-wide", boundary)

    def test_teacher_requirements_alignment_covers_revision_email(self) -> None:
        alignment = pd.read_csv(DATA / "teacher_requirements_alignment_shilin.csv")
        required_items = {
            "Three-sheet benchmark release",
            "Rule-event registry with rejected cases",
            "Cross-chain empirical case",
            "Base archive/indexer full-cohort path",
            "On-chain/off-chain evidence integration",
            "Mirror empirical Case B",
            "Agentic Trustworthy AI evaluation",
            "Trustworthy AI for Good societal impact",
        }
        self.assertTrue(required_items.issubset(set(alignment["ownership_item"].astype(str))))
        base = alignment.loc[alignment["ownership_item"].eq("Base archive/indexer full-cohort path")].iloc[0]
        self.assertIn("partial", base["status"])
        self.assertIn("13,880", base["evidence_or_gap"])
        mirror = alignment.loc[alignment["ownership_item"].eq("Mirror empirical Case B")].iloc[0]
        self.assertIn("not_causal", mirror["status"])


if __name__ == "__main__":
    unittest.main()
