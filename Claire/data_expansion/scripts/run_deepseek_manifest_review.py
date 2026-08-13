#!/usr/bin/env python3
"""Ask DeepSeek V4 Flash to review compact data audit artifacts without fallback."""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "Claire" / "data_expansion" / "artifacts"
MODEL = "deepseek-v4-flash"
URL = "https://api.deepseek.com/chat/completions"
INPUTS = [
    ROOT / "Claire" / "data_expansion" / "source_manifest.csv",
    ROOT / "Claire" / "data_expansion" / "SCHEMA_CONTRACT.md",
    OUT / "coverage_audit.csv",
    OUT / "shilin_bundle_audit.json",
    OUT / "pump_metadata_git_history_summary.json",
    OUT / "base_pilot_summary.json",
    OUT / "base_pilot_treated_summary.json",
]


def main() -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is required")
    evidence = []
    for path in INPUTS:
        if path.exists():
            evidence.append(f"\n[{path.relative_to(ROOT)}]\n{path.read_text(encoding='utf-8')}")
    prompt = """Review the attached compact data inventory as a data auditor.
Return concise Chinese JSON with exactly these keys: inconsistencies, missing_provenance,
coverage_corrections, next_low_cost_checks. Do not propose causal estimation or DiD.
Treat manifest rows as claims to verify, not ground truth. Do not invent facts.
Prioritize the next steps for an extensible four chain launchpad dataset rather than an experiment specific dataset.
Keep the complete JSON response under 1200 Chinese characters.
""" + "".join(evidence)
    body = json.dumps(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "You are a careful research data auditor."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": 6000,
            "stream": False,
        }
    ).encode()
    request = urllib.request.Request(
        URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.load(response)
    choice = payload["choices"][0]["message"]["content"]
    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "requested_model": MODEL,
        "returned_model": payload.get("model", ""),
        "fallback_allowed": False,
        "usage": payload.get("usage", {}),
        "review": json.loads(choice),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "deepseek_manifest_review.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output.relative_to(ROOT)), "requested_model": MODEL, "returned_model": result["returned_model"], "usage": result["usage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
