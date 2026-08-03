from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API_FILE = Path("/Users/michelangelo/Works/api.txt")
ENDPOINT = "https://api.kimi.com/coding/v1/chat/completions"
MODEL = "k3-256k"


def read_key() -> str:
    environment_value = os.environ.get("KIMI_CODING_PLAN", "").strip()
    if environment_value:
        return environment_value
    if not API_FILE.exists():
        raise RuntimeError(
            "KIMI_CODING_PLAN is missing. Set the environment variable or provide the local API file."
        )
    for line in API_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("KIMI_CODING_PLAN="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    raise RuntimeError("KIMI_CODING_PLAN is missing")


def call_k3(prompt: str) -> dict:
    payload = {
        "model": MODEL,
        "temperature": 1,
        "reasoning_effort": "high",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an adversarial causal-inference reviewer. Separate verified facts, "
                    "identification assumptions, descriptive estimates, and causal claims. "
                    "Return concise JSON with keys verdict, fatal_issues, required_claim_boundary, "
                    "and useful_next_check."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {read_key()}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Exact model {MODEL!r} failed with HTTP {exc.code}: {detail}") from exc
    if body.get("model") not in {MODEL, None}:
        raise RuntimeError(f"Provider returned model {body.get('model')!r}, expected {MODEL!r}")
    content = body["choices"][0]["message"]["content"]
    return {
        "requested_model": MODEL,
        "returned_model": body.get("model", MODEL),
        "audit": json.loads(content),
        "usage": body.get("usage", {}),
    }


def main() -> None:
    h0 = (ROOT / "artifacts" / "h0_summary.json").read_text(encoding="utf-8")
    h3 = (ROOT / "artifacts" / "h3_incidence.json").read_text(encoding="utf-8")
    prompt = f"""
Audit this registered study without proposing another model or data source.

Verified design facts:
* Pump.fun creator-fee economic activation: 2025-05-13 11:27:06 UTC.
* Public documentation starts 2025-05-08, which is excluded for anticipation.
* Gross pre cohorts: 2025-04-17 to 2025-05-07. Gross post: 2025-05-14 to 2025-06-03.
* Seven-day quality pre cohorts end 2025-04-30 so their outcomes cannot cross anticipation.
* Pump and Moonshot expose exact launches and lifecycle migration, but Moonshot has concurrent
  product changes and can receive displaced Pump users. There are only two platforms.
* The treatment bundles creator subsidy, trader fee burden, and a program upgrade.

H0 machine output:
{h0}

H3 machine output:
{h3}

Question: Is it defensible to claim a causal effect on market thickness or stakeholder welfare?
What is the strongest claim supported by the evidence?
"""
    result = call_k3(prompt)
    output = ROOT / "artifacts" / "k3_subagent_audit.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"requested_model": result["requested_model"], "audit": result["audit"]}, indent=2))


if __name__ == "__main__":
    main()
