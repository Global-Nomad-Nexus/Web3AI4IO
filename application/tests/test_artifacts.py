from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "artifacts" / "tables"
FIGURES = ROOT / "artifacts" / "figures"
_LOCAL_ARTIFACTS = (TABLES / "deterministic_ladder.csv").exists()


@unittest.skipUnless(_LOCAL_ARTIFACTS, "local application artifacts are not part of the GitHub tree")
class ArtifactIntegrityTest(unittest.TestCase):
    def test_ladder_records_the_naive_to_trustworthy_flip(self) -> None:
        ladder = pd.read_csv(TABLES / "deterministic_ladder.csv")
        self.assertEqual(ladder["rung"].tolist(), [f"L{i}" for i in range(8)])
        l0 = ladder.loc[ladder["rung"].eq("L0")].iloc[0]
        l6 = ladder.loc[ladder["rung"].eq("L6")].iloc[0]
        self.assertEqual(l0["worked_decision"], "yes")
        self.assertNotEqual(l6["worked_decision"], "yes")

    def test_paired_case_ladder_figure_exists(self) -> None:
        figure = FIGURES / "fig_paired_case_ladder_application.png"
        self.assertTrue(figure.exists())
        self.assertGreater(figure.stat().st_size, 20_000)
        mirror = pd.read_csv(ROOT / "benchmark_release" / "data" / "mirror_case_ladder.csv")
        self.assertEqual(mirror["rung"].tolist(), [f"B{i}" for i in range(7)])
        b0 = mirror.loc[mirror["rung"].eq("B0")].iloc[0]
        b4 = mirror.loc[mirror["rung"].eq("B4")].iloc[0]
        b6 = mirror.loc[mirror["rung"].eq("B6")].iloc[0]
        self.assertIn("near_null", b0["decision"])
        self.assertIn("credible", b4["decision"])
        self.assertIn("not as a completed causal", b6["claim_boundary"])

    def test_pretrend_risk_is_explicit_not_hidden(self) -> None:
        pretrend = json.loads((TABLES / "pretrend_diagnostics.json").read_text(encoding="utf-8"))
        ladder = pd.read_csv(TABLES / "deterministic_ladder.csv")
        l4 = ladder.loc[ladder["rung"].eq("L4")].iloc[0]
        self.assertIn("pretrend_flag", pretrend)
        if pretrend["pretrend_flag"]:
            self.assertEqual(l4["worked_decision"], "pretrend_flagged")

    def test_dune_gap_cannot_be_reported_as_computed_causal_evidence(self) -> None:
        dune = json.loads((TABLES / "dune_indexer_export_summary.json").read_text(encoding="utf-8"))
        claim_scope = pd.read_csv(TABLES / "claim_scope_ledger.csv")
        post_rows = int(dune.get("outputs", {}).get("post_migration", {}).get("rows", 0) or 0)
        if post_rows == 0:
            forbidden = " ".join(claim_scope["claim_not_allowed"].astype(str))
            self.assertIn("Do not", forbidden)
            self.assertNotEqual(dune.get("status"), "computed_dune_indexer_exports")

    def test_h1_rpc_mechanism_is_not_overclaimed_as_welfare_causality(self) -> None:
        summary = json.loads((TABLES / "h1_rpc_mechanism_summary.json").read_text(encoding="utf-8"))
        audit = pd.read_csv(TABLES / "h1_rpc_mechanism_causal_audit.csv")
        self.assertEqual(summary["mechanism_claim_status"], "pass_mechanism_level_not_welfare_causal")
        self.assertGreaterEqual(float(summary["full_30d_observed_active_lower_bound_share"]), 0.90)
        self.assertEqual(int(summary["temporal_order_violations_complete_30d"]), 0)
        self.assertIn("H1-decoded-usd-trade-outcomes", set(audit["claim_id"].astype(str)))
        forbidden = " ".join(audit["claim_not_allowed"].astype(str))
        self.assertIn("welfare", forbidden)
        self.assertIn("USD", forbidden)

    def test_agentic_runs_cover_every_rung(self) -> None:
        runs = pd.read_csv(ROOT / "artifacts" / "agent_runs" / "agent_runs.csv")
        counts = runs.groupby("rung").size().to_dict()
        for rung in [f"L{i}" for i in range(8)]:
            self.assertGreaterEqual(counts.get(rung, 0), 10)

    def test_red_cohort_overlap_audit_prevents_false_join_claims(self) -> None:
        overlap = pd.read_csv(TABLES / "red_cohort_red_pump_overlap.csv").iloc[0]
        self.assertEqual(overlap["status"], "computed_overlap_audit")
        if int(overlap["red_cohort_intra_overlap_mints"]) == 0:
            self.assertIn("external H4 mechanism validation", overlap["claim_boundary"])

    def test_readiness_audit_has_required_areas(self) -> None:
        audit = pd.read_csv(TABLES / "paper_readiness_audit.csv")
        required = {
            "benchmark_ladder",
            "parallel_trends",
            "few_cluster_inference",
            "identification_stress_tests",
            "decoded_indexer_outcomes",
            "rpc_external_validation",
            "h1_rpc_mechanism_validation",
            "moralis_sample_selection",
            "agentic_execution",
            "claim_boundary",
        }
        self.assertTrue(required.issubset(set(audit["area"])))

    def test_identification_stress_tests_are_machine_readable(self) -> None:
        summary = json.loads((TABLES / "identification_strength_summary.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(int(summary["event_date_sensitivity_rows"]), 10)
        self.assertGreaterEqual(int(summary["twfe_window_rows"]), 3)
        self.assertGreaterEqual(int(summary["control_set_rows"]), 4)
        self.assertGreaterEqual(int(summary["placebo_rows"]), 3)
        self.assertIn("diagnostic", summary["submission_claim_recommendation"].lower())
        synthetic = json.loads((TABLES / "synthetic_control_summary.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(int(synthetic["unit_count"]), 4)
        self.assertIn("not a stand-alone causal proof", synthetic["claim_boundary"])


if __name__ == "__main__":
    unittest.main()
