"""Verify archived counts, generated tables, checksums, and manuscript numbers."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import ARCHIVED, CHECKSUMS, PAPER, REPRO

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
        "deepseek-chat",
        "not identified",
    ]
    for token in required:
        if token not in tex:
            fail(f"manuscript missing required token: {token}", errors)
    if "The Solana creator-fee event is retained conditionally because activation is exact" in tex:
        fail("Appendix B still mislabels the canonical Solana registry event as the creator-fee event", errors)
    claim = (PAPER / "tabs" / "tab_claim_evidence.tex").read_text(encoding="utf-8")
    if "Creator-fee rule incidence" not in claim:
        fail("claim-evidence table missing creator-fee row", errors)
    if "generated from archived artifacts" not in claim:
        fail("claim-evidence table is not marked as generated", errors)


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


def main() -> int:
    errors: list[str] = []
    check_release_counts(errors)
    check_estimates(errors)
    check_manuscript(errors)
    check_checksums(errors)
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
