from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"


@dataclass(frozen=True)
class TransactionCheck:
    signature: str
    slot: int
    block_time: int
    account: str
    balance_delta: int
    expected_delta: int

    @property
    def passes(self) -> bool:
        return self.balance_delta == self.expected_delta


def rpc_call(method: str, params: list[Any], rpc_url: str = DEFAULT_RPC_URL) -> Any:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode()
    request = urllib.request.Request(
        rpc_url, payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.load(response)
    if "error" in body:
        raise RuntimeError(f"Solana RPC error: {body['error']}")
    return body["result"]


def verify_transaction(spec: dict[str, Any], rpc_url: str = DEFAULT_RPC_URL) -> TransactionCheck:
    result = rpc_call(
        "getTransaction",
        [
            spec["signature"],
            {
                "encoding": "json",
                "commitment": "finalized",
                "maxSupportedTransactionVersion": 0,
            },
        ],
        rpc_url,
    )
    if result is None:
        raise ValueError(f"Transaction unavailable: {spec['signature']}")
    if result["meta"]["err"] is not None:
        raise ValueError(f"Transaction failed: {spec['signature']}")
    keys = result["transaction"]["message"]["accountKeys"]
    loaded = result["meta"].get("loadedAddresses") or {}
    keys = keys + loaded.get("writable", []) + loaded.get("readonly", [])
    try:
        account_index = keys.index(spec["balance_account"])
    except ValueError as error:
        raise ValueError(
            f"Balance account absent from transaction: {spec['balance_account']}"
        ) from error
    delta = result["meta"]["postBalances"][account_index] - result["meta"]["preBalances"][account_index]
    check = TransactionCheck(
        signature=spec["signature"],
        slot=result["slot"],
        block_time=result["blockTime"],
        account=spec["balance_account"],
        balance_delta=delta,
        expected_delta=spec["expected_balance_delta_lamports"],
    )
    if result["slot"] != spec["expected_slot"]:
        raise ValueError(f"Unexpected slot for {spec['signature']}: {result['slot']}")
    if result["blockTime"] != spec["expected_block_time"]:
        raise ValueError(
            f"Unexpected blockTime for {spec['signature']}: {result['blockTime']}"
        )
    if not check.passes:
        raise ValueError(
            f"Unexpected balance delta for {spec['signature']}: {delta} lamports"
        )
    return check


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    specs = json.loads((root / "evidence" / "pump_creator_fee_checks.json").read_text())
    checks = [verify_transaction(spec) for spec in specs["transactions"]]
    print(
        json.dumps(
            [
                {
                    "signature": check.signature,
                    "slot": check.slot,
                    "block_time": check.block_time,
                    "balance_account": check.account,
                    "balance_delta_lamports": check.balance_delta,
                    "passes": check.passes,
                }
                for check in checks
            ],
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
