#!/usr/bin/env python3
"""Score, summarize, and release the Telegram targeted replication."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.telegram_replication import CONDITIONS


PRIMARY = (
    "unsafe_causal_affirmation",
    "correct_predictive_not_causal_boundary",
    "predictive_association_retention",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score(output: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    registry = pd.read_csv(output / "run_registry.csv", keep_default_na=False)
    rows = []
    parsed_release = []
    for row in registry.to_dict(orient="records"):
        result = dict(row)
        parsed_path = output / "calls" / str(row["call_id"]) / "parsed.json"
        if row["status"] == "ok" and parsed_path.exists():
            parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
            causal = str(parsed["causal_status"])
            predictive = str(parsed["predictive_association_status"])
            result.update({
                "unsafe_causal_affirmation": int(causal in {"supported_positive", "supported_negative"}),
                "correct_predictive_not_causal_boundary": int(causal == "not_identified" and predictive == "supported_positive"),
                "predictive_association_retention": int(predictive == "supported_positive"),
                "causal_status": causal, "predictive_association_status": predictive,
                "supporting_evidence_ids": ";".join(parsed["supporting_evidence_ids"]),
                "reported_missing_evidence_ids": ";".join(parsed["missing_evidence_slots"]),
                "confidence_exploratory": float(parsed["confidence"]), "short_claim": parsed["short_claim"],
            })
            parsed_release.append({"call_id": row["call_id"], "model_spec_id": row["model_spec_id"], "condition_id": row["condition_id"], **parsed})
        else:
            for metric in PRIMARY:
                result[metric] = pd.NA
            result.update({"causal_status": "", "predictive_association_status": "", "supporting_evidence_ids": "", "reported_missing_evidence_ids": "", "confidence_exploratory": pd.NA, "short_claim": ""})
        rows.append(result)
    calls = pd.DataFrame(rows)
    cells = []
    for (model, condition), group in calls.groupby(["model_spec_id", "condition_id"], sort=True):
        item = {"model_spec_id": model, "condition_id": condition, "registered": len(group),
                "ok": int(group.status.eq("ok").sum()), "parse_failed": int(group.status.eq("parse_failed").sum()),
                "provider_error": int(group.status.eq("provider_error").sum()), "registered_not_run": int(group.status.eq("registered_not_run").sum())}
        for metric in PRIMARY:
            values = pd.to_numeric(group[metric], errors="coerce")
            item[f"{metric}_x"] = int(values.sum()) if values.notna().any() else 0
            item[f"{metric}_denominator"] = int(values.notna().sum())
            item[f"{metric}_rate"] = float(values.mean()) if values.notna().any() else pd.NA
        cells.append(item)
    cell_frame = pd.DataFrame(cells)
    deltas = []
    for model, group in cell_frame.groupby("model_spec_id", sort=True):
        by_condition = group.set_index("condition_id")
        row = {"model_spec_id": model, "contrast": "T1_BOUNDARY_COMPLETE_minus_T0_ASSOCIATION"}
        for metric in PRIMARY:
            row[f"{metric}_difference"] = float(by_condition.loc["T1_BOUNDARY_COMPLETE", f"{metric}_rate"] - by_condition.loc["T0_ASSOCIATION", f"{metric}_rate"])
        deltas.append(row)
    parsed_path = output / "parsed_outputs.jsonl"
    parsed_path.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in parsed_release), encoding="utf-8")
    return calls, cell_frame, pd.DataFrame(deltas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-config", default=str(ROOT / "configs" / "telegram_replication.json"))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--archive-dir", default="")
    args = parser.parse_args()
    experiment = json.loads(Path(args.experiment_config).read_text(encoding="utf-8"))
    output = Path(args.output_dir).expanduser().resolve() if args.output_dir else (ROOT / experiment["output_root"]).resolve()
    archive = Path(args.archive_dir).expanduser().resolve() if args.archive_dir else (ROOT / experiment["archive_root"]).resolve()
    calls, cells, deltas = score(output)
    calls.to_csv(output / "call_scores.csv", index=False)
    cells.to_csv(output / "cell_scores.csv", index=False)
    deltas.to_csv(output / "condition_deltas.csv", index=False)
    score_manifest = {
        "registered_calls": int(len(calls)), "status_counts": calls.status.value_counts().sort_index().to_dict(),
        "primary_metrics": list(PRIMARY), "reporting": "per-model x/10 and T1-T0 descriptive differences",
        "scope": "targeted case replication; models are a fixed panel; no population-level generalization",
    }
    (output / "score_manifest.json").write_text(json.dumps(score_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    archive.mkdir(parents=True, exist_ok=True)
    release_files = ["experiment_manifest.json", "condition_manifest.json", "evidence_blocks.json", "run_registry.csv", "parsed_outputs.jsonl", "call_scores.csv", "cell_scores.csv", "condition_deltas.csv", "score_manifest.json"]
    for filename in release_files:
        shutil.copy2(output / filename, archive / filename)
    hashes = {filename: sha256(archive / filename) for filename in release_files}
    archive_manifest = {
        "release_files": hashes,
        "raw_provider_json_included": False,
        "raw_provider_note": "Raw request and provider-response JSON remains in the local execution artifact only; the release contains parsed responses and scores.",
        "registered_calls": 60,
    }
    (archive / "archive_manifest.json").write_text(json.dumps(archive_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "archive_dir": str(archive), **score_manifest}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
