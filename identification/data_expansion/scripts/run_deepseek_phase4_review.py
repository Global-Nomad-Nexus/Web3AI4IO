#!/usr/bin/env python3
"""Ask the fixed DeepSeek V4 Flash model to audit compact Phase 4 evidence."""

from __future__ import annotations

import getpass
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODEL = "deepseek-v4-flash"
URL = "https://api.deepseek.com/chat/completions"
OUTPUT = ROOT / "identification/data_expansion/artifacts/deepseek_phase4_review.json"
INPUTS = (
    ROOT / "data_pipeline/releases/v1/bnb_core.json",
    ROOT / "data_pipeline/releases/v1/tron_core.json",
    ROOT / "data/external/fourmeme/20260811/onchain/ONCHAIN_SOURCE.json",
    ROOT / "data/external/sunpump/20260811/snapshot/ONCHAIN_SOURCE.json",
    ROOT / "identification/data_expansion/artifacts/phase4_integrity_summary.json",
)


def main() -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY") or getpass.getpass("DeepSeek API key: ")
    evidence = []
    for path in INPUTS:
        if not path.exists():
            raise SystemExit(f"Missing Phase 4 evidence: {path.relative_to(ROOT)}")
        evidence.append({"path": path.relative_to(ROOT).as_posix(), "content": json.loads(path.read_text())})
    prompt = {
        "task": "Audit Phase 4 canonical data evidence. Do not propose experiments or causal estimation.",
        "requirements": [
            "Check manifest counts against source and integrity summaries.",
            "Check that official APIs are metadata enrichment only and do not define either universe.",
            "Check observed, not_collected, and not_applicable semantics without inventing facts.",
            "Check that decoded swaps, trading, and holder data are absent by scope.",
        ],
        "response": "Return concise Chinese JSON with keys inconsistencies, provenance_gaps, semantic_risks, acceptance.",
        "evidence": evidence,
    }
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a careful research data auditor."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "temperature": 0,
        "max_tokens": 4000,
        "stream": False,
    }).encode()
    request = urllib.request.Request(URL, data=body, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.load(response)
    returned_model = payload.get("model", "")
    if returned_model != MODEL:
        raise RuntimeError(f"Model mismatch: requested={MODEL}, returned={returned_model}; fallback is forbidden")
    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_model": MODEL,
        "returned_model": returned_model,
        "fallback_allowed": False,
        "usage": payload.get("usage", {}),
        "review": json.loads(payload["choices"][0]["message"]["content"]),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": OUTPUT.relative_to(ROOT).as_posix(), "model": returned_model, "usage": result["usage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
