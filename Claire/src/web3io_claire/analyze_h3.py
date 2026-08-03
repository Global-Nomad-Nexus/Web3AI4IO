from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "pump_creator_fee_checks.json"
OUTPUT = ROOT / "artifacts" / "h3_incidence.json"


def main() -> None:
    checks = json.loads(EVIDENCE.read_text(encoding="utf-8"))["transactions"]
    support = next(item for item in checks if item["expected_balance_delta_lamports"] == 0)
    active = next(item for item in checks if item["expected_balance_delta_lamports"] > 0)

    result = {
        "event": "Pump.fun creator-fee activation",
        "activation_utc": "2025-05-13T11:27:06Z",
        "estimand": "stakeholder incidence of the creator-fee rule bundle",
        "identification_status": "mechanical_creator_incidence_only",
        "stakeholders": {
            "creator": {
                "direction": "positive",
                "identified": True,
                "evidence": "verified positive creator-vault lamport balance delta",
                "activation_transaction": active["signature"],
                "balance_delta_lamports": active["expected_balance_delta_lamports"],
            },
            "trader": {
                "direction": "mechanically_pays_fee_but_net_welfare_unknown",
                "identified": False,
                "missing": [
                    "counterfactual execution cost",
                    "behavioral response",
                    "liquidity and token-quality response",
                ],
            },
            "platform": {
                "direction": "unknown",
                "identified": False,
                "missing": ["net protocol revenue", "retention", "market-share response"],
            },
        },
        "support_upgrade_falsification": {
            "transaction": support["signature"],
            "creator_vault_delta_lamports": 0,
            "interpretation": "program support on May 12 was not economic activation",
        },
        "causal_boundary": (
            "The transfer establishes rule mechanics, not behavioral or welfare incidence. "
            "No clean comparison passed the control gate."
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
