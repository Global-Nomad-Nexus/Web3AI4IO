"""Verify archived counts, generated tables, checksums, and manuscript numbers."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import ARCHIVED, CHECKSUMS, MANIFEST, PAPER, REPRO

EXPECTED = {
    "solana_outcomes": 832941,
    "solana_graduations": 1651,
    "base_launches": 62618,
    "bnb_launches": 1593679,
    "bnb_pools": 15403,
    "tron_launches": 104548,
    "tron_pools": 1831,
    "events": 4,
    "event_evidence": 6,
}


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def load_json(rel: str) -> dict:
    return json.loads((ARCHIVED / rel).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_release_counts(errors: list[str]) -> None:
    sol = load_json("release/solana_core.json")
    base = load_json("release/base_core.json")
    bnb = load_json("release/bnb_core.json")
    tron = load_json("release/tron_core.json")
    events = load_json("release/events_core.json")
    if sol["raw_reproduction"]["deduplicated_terminal_outcomes"] != EXPECTED["solana_outcomes"]:
        fail("Solana outcome count mismatch", errors)
    if sol["raw_reproduction"]["graduated_tokens"] != EXPECTED["solana_graduations"]:
        fail("Solana graduation count mismatch", errors)
    if base["tables"]["launches"]["rows"] != EXPECTED["base_launches"]:
        fail("Base launch count mismatch", errors)
    if bnb["tables"]["launches"]["rows"] != EXPECTED["bnb_launches"]:
        fail("BNB launch count mismatch", errors)
    if bnb["tables"]["pools"]["rows"] != EXPECTED["bnb_pools"]:
        fail("BNB pool count mismatch", errors)
    if tron["tables"]["launches"]["rows"] != EXPECTED["tron_launches"]:
        fail("TRON launch count mismatch", errors)
    if tron["tables"]["pools"]["rows"] != EXPECTED["tron_pools"]:
        fail("TRON pool count mismatch", errors)
    if events["events"]["rows"] != EXPECTED["events"]:
        fail("Event count mismatch", errors)
    if events["event_evidence"]["rows"] != EXPECTED["event_evidence"]:
        fail("Event-evidence count mismatch", errors)


def check_estimates(errors: list[str]) -> None:
    with (ARCHIVED / "application/deterministic_ladder.csv").open(encoding="utf-8", newline="") as handle:
        ladder = {row["rung"]: row for row in csv.DictReader(handle)}
    twfe = float(ladder["L2"]["estimate"])
    if abs(twfe - 0.4116991342312808) > 1e-12:
        fail(f"TWFE estimate drifted: {twfe}", errors)
    wild = load_json("application/wild_cluster_bootstrap.json")
    if abs(float(wild["wild_bootstrap_p_value"]) - 0.6875) > 1e-12:
        fail("exact p-value drifted", errors)
    telegram = load_json("application/telegram_mirror_design_summary.json")
    if abs(float(telegram["matched_att"]) - 0.009448529581818533) > 1e-12:
        fail("Telegram ATT drifted", errors)
    h3 = load_json("identification/h3_incidence.json")
    if int(h3["stakeholders"]["creator"]["balance_delta_lamports"]) != 10732:
        fail("creator vault delta drifted", errors)
    s3 = list(csv.DictReader((ARCHIVED / "calibration/s3_results_summary.csv").open(encoding="utf-8")))
    zero = {row["method"]: row for row in s3 if row["arm"] == "zero"}
    if abs(float(zero["crv1_normal"]["fpr"]) - 0.0646) > 1e-8:
        fail("S3 normal FPR drifted", errors)
    if abs(float(zero["crv1_t3"]["fpr"]) - 0.0259) > 1e-8:
        fail("S3 t(3) FPR drifted", errors)


def check_manuscript(errors: list[str]) -> None:
    tex = (PAPER / "neurips_2026.tex").read_text(encoding="utf-8")
    required = [
        "832{,}941",
        "1{,}651",
        "0.412",
        "0.6875",
        "10{,}732",
        "714",
        "35.0",
        "56.3",
        "88.8",
        "64.4",
        "31.3",
        "35.8",
        "42.9",
        "2{,}000",
        "fixed-design",
        "jin2023cladder",
        "not identified",
    ]
    for token in required:
        if token not in tex:
            fail(f"manuscript missing required token: {token}", errors)
    if "The Solana creator-fee event is retained conditionally because activation is exact" in tex:
        fail("Appendix B still mislabels the canonical Solana registry event as the creator-fee event", errors)
    if "absolute calibration gap falls" in tex:
        fail("manuscript still presents the legacy self-confidence field as calibration evidence", errors)
    if "reasoning calibration" in tex or "most stable pooled safeguard" in tex:
        fail("manuscript still uses an unsupported V2 calibration or stability formulation", errors)
    claim = (PAPER / "tabs" / "tab_claim_evidence.tex").read_text(encoding="utf-8")
    if "Creator-fee rule incidence" not in claim:
        fail("claim-evidence table missing creator-fee row", errors)
    if "generated from archived artifacts" not in claim:
        fail("claim-evidence table is not marked as generated", errors)
    if "Bounded, heterogeneous evaluation" not in claim:
        fail("claim-evidence table missing the V2 heterogeneous-evaluation status", errors)


def check_checksums(errors: list[str]) -> None:
    if not CHECKSUMS.exists():
        fail("checksums.sha256 missing; run generate_manifest.py", errors)
        return
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        path = REPRO / rel
        if not path.exists():
            fail(f"checksum target missing: {rel}", errors)
            continue
        actual = sha256(path)
        if actual != digest:
            fail(f"checksum mismatch: {rel}", errors)


def check_prompt_hash_note(errors: list[str]) -> None:
    runs = ARCHIVED / "application" / "agent_runs.csv"
    manifest = ARCHIVED / "application" / "agentic_prompt_manifest.csv"
    if not runs.exists() or not manifest.exists():
        return
    run_hashes = set()
    with runs.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            run_hashes.add(row["prompt_hash"])
    file_hashes = set()
    with manifest.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            file_hashes.add(row["prompt_hash"])
    if run_hashes and file_hashes and run_hashes.isdisjoint(file_hashes):
        print(
            "NOTE: scored agent-run prompt hashes do not match current prompt-file hashes. "
            "The archived run records remain the evaluation object."
        )


def check_agent_outputs(errors: list[str]) -> None:
    runs_path = ARCHIVED / "application" / "agent_runs.csv"
    raw_dir = ARCHIVED / "application" / "raw_responses"
    if not runs_path.exists():
        fail("agent run table missing", errors)
        return
    with runs_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 80:
        fail(f"expected 80 agent runs, found {len(rows)}", errors)
    returned_models: set[str] = set()
    for row in rows:
        filename = Path(row["raw_response_path"]).name
        raw_path = raw_dir / filename
        if not raw_path.exists():
            fail(f"raw agent response missing: {filename}", errors)
            continue
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        if payload.get("status") != "ok":
            fail(f"agent response is not successful: {filename}", errors)
        if payload.get("prompt_hash") != row["prompt_hash"]:
            fail(f"agent prompt hash mismatch: {filename}", errors)
        if payload.get("model") != row["model"]:
            fail(f"requested model mismatch: {filename}", errors)
        returned = payload.get("api_response", {}).get("model")
        if returned:
            returned_models.add(str(returned))
    if returned_models != {"deepseek-v4-flash"}:
        fail(f"unexpected returned model versions: {sorted(returned_models)}", errors)
    provenance_path = ARCHIVED / "application" / "agent_provenance.json"
    if not provenance_path.exists():
        fail("agent provenance audit missing", errors)
        return
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if provenance.get("run_records") != 80 or provenance.get("raw_responses") != 80:
        fail("agent provenance counts are incomplete", errors)
    if provenance.get("hash_sets_overlap") is not False:
        fail("prompt provenance boundary changed; review exact runtime payload status", errors)


def check_agentic_v2_outputs(errors: list[str]) -> None:
    root = ARCHIVED / "application" / "agentic_v2"
    required = [
        "experiment_manifest.json",
        "condition_manifest.json",
        "evidence_blocks.json",
        "run_registry.csv",
        "score_manifest.json",
        "call_scores.csv",
        "cell_scores.csv",
        "canonical_deltas.csv",
        "factorial_effects.csv",
        "control_comparisons.csv",
        "model_block_heterogeneity.csv",
        "model_factor_interactions.csv",
        "matched_factorial_pairs.csv",
        "matched_factorial_effects.csv",
        "matched_analysis_manifest.json",
        "code_snapshot_manifest.json",
        "runtime_code_snapshot_20260826.tar.gz",
    ]
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        fail(f"V2 frozen files missing: {missing}", errors)
        return
    if (root / "provider_preflight.json").exists():
        fail("provider preflight must not be included in the anonymous V2 archive", errors)

    score_manifest = json.loads((root / "score_manifest.json").read_text(encoding="utf-8"))
    if score_manifest.get("registered_calls") != 714 or score_manifest.get("status_counts") != {"ok": 714}:
        fail("V2 score manifest is not the frozen 714/714 result", errors)
    if score_manifest.get("bootstrap_draws") != 2000 or score_manifest.get("gold_contract") != "agentic-v2-gold-1":
        fail("V2 bootstrap or deterministic gold-contract provenance drifted", errors)
    if score_manifest.get("confidence_policy") != "exploratory_only_not_calibration":
        fail("V2 self-confidence boundary changed", errors)

    with (root / "run_registry.csv").open(encoding="utf-8", newline="") as handle:
        registry = list(csv.DictReader(handle))
    if len(registry) != 714 or len({row["call_id"] for row in registry}) != 714:
        fail("V2 registry must contain 714 unique calls", errors)
    if {row["status"] for row in registry} != {"ok"}:
        fail("V2 registry contains a non-ok call", errors)
    expected_returned = {
        "gpt_5_6_terra": "gpt-5.6-terra",
        "deepseek_v4_pro": "deepseek-v4-pro",
        "qwen3_14b": "qwen3:14b",
    }
    for model, returned in expected_returned.items():
        rows = [row for row in registry if row["model_spec_id"] == model]
        if len(rows) != 238:
            fail(f"V2 model {model} has {len(rows)} calls, expected 238", errors)
        if {row["returned_model"] for row in rows} != {returned}:
            fail(f"V2 returned identifier drifted for {model}", errors)

    with (root / "call_scores.csv").open(encoding="utf-8", newline="") as handle:
        scores = list(csv.DictReader(handle))
    if len(scores) != 714:
        fail(f"V2 call_scores has {len(scores)} rows, expected 714", errors)
        return

    expected_rates = {
        "gpt_5_6_terra": (0.0, 0.8875),
        "deepseek_v4_pro": (0.35, 0.64375),
        "qwen3_14b": (0.5625, 0.3125),
    }
    for model, (expected_unsafe, expected_correct) in expected_rates.items():
        rows = [
            row for row in scores
            if row["model_spec_id"] == model and row["condition_family"] == "factorial"
        ]
        if len(rows) != 160:
            fail(f"V2 factorial cell count drifted for {model}: {len(rows)}", errors)
            continue
        unsafe = sum(float(row["unsafe_causal_affirmation"]) for row in rows) / len(rows)
        correct = sum(float(row["correct_boundary"]) for row in rows) / len(rows)
        if abs(unsafe - expected_unsafe) > 1e-12 or abs(correct - expected_correct) > 1e-12:
            fail(f"V2 factorial rates drifted for {model}: unsafe={unsafe}, correct={correct}", errors)

    with (root / "factorial_effects.csv").open(encoding="utf-8", newline="") as handle:
        effects = list(csv.DictReader(handle))
    expected_m6 = {
        "unsafe_causal_affirmation": (-0.35833333333333334, -0.43333333333333335, -0.28322916666666725),
        "correct_boundary": (0.42916666666666664, 0.35, 0.5083333333333333),
    }
    for metric, expected in expected_m6.items():
        rows = [
            row for row in effects
            if row["model_spec_id"] == "pooled"
            and row["effect_type"] == "main_effect"
            and row["factor"] == "M6"
            and row["metric"] == metric
        ]
        if len(rows) != 1:
            fail(f"V2 pooled M6 row missing for {metric}", errors)
            continue
        actual = tuple(float(rows[0][key]) for key in ("mean_difference_bit1_minus_bit0", "ci95_low", "ci95_high"))
        if any(abs(a - b) > 1e-12 for a, b in zip(actual, expected)):
            fail(f"V2 pooled M6 effect drifted for {metric}: {actual}", errors)

    with (root / "matched_factorial_effects.csv").open(encoding="utf-8", newline="") as handle:
        matched_effects = list(csv.DictReader(handle))
    matched_m6 = {
        "unsafe_causal_affirmation": (-0.35833333333333334, -0.4875, -0.2333333333333333),
        "correct_boundary": (0.42916666666666664, 0.2916666666666667, 0.5583333333333332),
    }
    for metric, expected in matched_m6.items():
        rows = [row for row in matched_effects if row["model_spec_id"] == "pooled" and row["factor"] == "M6" and row["metric"] == metric]
        if len(rows) != 1 or int(rows[0]["matched_pairs"]) != 24:
            fail(f"V2 matched pooled M6 row missing or miscounted for {metric}", errors)
            continue
        actual = tuple(float(rows[0][key]) for key in ("mean_difference_bit1_minus_bit0", "ci95_low", "ci95_high"))
        if any(abs(a - b) > 1e-12 for a, b in zip(actual, expected)):
            fail(f"V2 matched pooled M6 effect drifted for {metric}: {actual}", errors)

    with (root / "matched_factorial_pairs.csv").open(encoding="utf-8", newline="") as handle:
        matched_pairs = list(csv.DictReader(handle))
    pair_keys = {(row["model_spec_id"], row["factor"], row["metric"], row["matched_background"]) for row in matched_pairs}
    if len(matched_pairs) != 864 or len(pair_keys) != 864:
        fail(f"V2 matched pair table must contain 864 unique rows; found {len(matched_pairs)}", errors)

    l7_expected = {
        "gpt_5_6_terra": (0, 10),
        "deepseek_v4_pro": (0, 10),
        "qwen3_14b": (10, 0),
    }
    for model, (unsafe_expected, correct_expected) in l7_expected.items():
        rows = [row for row in scores if row["model_spec_id"] == model and row["condition_id"] == "F_1111"]
        unsafe = sum(int(float(row["unsafe_causal_affirmation"])) for row in rows)
        correct = sum(int(float(row["correct_boundary"])) for row in rows)
        if len(rows) != 10 or (unsafe, correct) != (unsafe_expected, correct_expected):
            fail(f"V2 L7 boundary outcomes drifted for {model}: n={len(rows)}, unsafe={unsafe}, correct={correct}", errors)


def check_telegram_replication_outputs(errors: list[str]) -> None:
    root = ARCHIVED / "application" / "telegram_replication"
    required = [
        "archive_manifest.json", "experiment_manifest.json", "condition_manifest.json",
        "evidence_blocks.json", "run_registry.csv", "parsed_outputs.jsonl", "call_scores.csv",
        "cell_scores.csv", "condition_deltas.csv", "score_manifest.json",
    ]
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        fail(f"Telegram replication files missing: {missing}", errors)
        return
    manifest = json.loads((root / "archive_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("registered_calls") != 60 or manifest.get("raw_provider_json_included") is not False:
        fail("Telegram archive scope or call count drifted", errors)
    for filename, digest in manifest.get("release_files", {}).items():
        path = root / filename
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            fail(f"Telegram archive hash mismatch: {filename}", errors)
    with (root / "run_registry.csv").open(encoding="utf-8", newline="") as handle:
        registry = list(csv.DictReader(handle))
    if len(registry) != 60 or len({row["call_id"] for row in registry}) != 60:
        fail("Telegram registry must contain exactly 60 unique calls", errors)
        return
    cells = {}
    for row in registry:
        key = (row["model_spec_id"], row["condition_id"])
        cells[key] = cells.get(key, 0) + 1
    if len(cells) != 6 or set(cells.values()) != {10}:
        fail(f"Telegram registry must contain six 10-call cells: {cells}", errors)
    terminal = {"ok", "parse_failed", "provider_error"}
    if not {row["status"] for row in registry}.issubset(terminal):
        fail("Telegram registry contains unfinished calls", errors)
    score_manifest = json.loads((root / "score_manifest.json").read_text(encoding="utf-8"))
    if score_manifest.get("registered_calls") != 60:
        fail("Telegram score manifest call count drifted", errors)


def check_artifact_manifest(errors: list[str]) -> None:
    if not MANIFEST.exists():
        fail("artifact manifest missing", errors)
        return
    with MANIFEST.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    outputs = {
        item.strip()
        for row in rows
        for item in row["output"].split(";")
        if item.strip()
    }
    tex = (PAPER / "neurips_2026.tex").read_text(encoding="utf-8")
    appendix = PAPER / "figs" / "fig_application_appendix.tex"
    if appendix.exists():
        tex += "\n" + appendix.read_text(encoding="utf-8")
    included_figures = {
        f"paper/{match}" for match in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", tex)
    }
    missing_figures = sorted(included_figures - outputs)
    if missing_figures:
        fail(f"manifest missing included figures: {missing_figures}", errors)
    numerical_rows = [row for row in rows if row["object_type"].startswith("number")]
    if len(numerical_rows) < 17:
        fail(f"numerical claim ledger is incomplete: {len(numerical_rows)} rows", errors)
    svg = PAPER / "figs" / "teaser_figure.svg"
    teaser_source = REPRO / "figures" / "teaser_figure_original.drawio.xml"
    teaser_wrapper = REPRO / "figures" / "teaser_figure_print.html"
    if not svg.exists():
        fail("teaser SVG export is missing", errors)
    if not teaser_source.exists() or "<mxfile" not in teaser_source.read_text(encoding="utf-8"):
        fail("editable original draw.io teaser source is missing", errors)
    if not teaser_wrapper.exists() or "297mm 151.8mm" not in teaser_wrapper.read_text(encoding="utf-8"):
        fail("cropped A4-width vector teaser print source is missing", errors)


def main() -> int:
    errors: list[str] = []
    check_release_counts(errors)
    check_estimates(errors)
    check_manuscript(errors)
    check_checksums(errors)
    check_agent_outputs(errors)
    check_agentic_v2_outputs(errors)
    check_telegram_replication_outputs(errors)
    check_artifact_manifest(errors)
    check_prompt_hash_note(errors)
    if errors:
        print("VERIFY FAILED")
        for item in errors:
            print(f"  - {item}")
        return 1
    print("VERIFY PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
