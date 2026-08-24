#!/usr/bin/env python3
"""Run registered agentic scaffold ablations with local Ollama models.

This is the no-API-key runner for locally available open/free models. It appends
to the same ``agentic_multimodel_ablation_runs.csv`` schema used by the API
runner, so local and remote model families can be scored together.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.agentic import (
    ABLATION_CONDITIONS,
    ABLATION_RUN_SCHEMA,
    RUNG_DESCRIPTIONS,
    score_agentic_ablation_runs,
    write_agentic_ablation_manifest,
    write_prompt_templates,
)
from trustworthy_launchpads.io import load_config

from run_agentic_deepseek import extract_json_object, normalize_row
from run_agentic_multimodel_ablation import build_ablated_prompt, parse_csv_arg, sanitize_id


DEFAULT_OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"


def ollama_chat(
    *,
    chat_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    request = urllib.request.Request(
        chat_url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def ollama_content(payload: dict[str, Any]) -> str:
    content = payload.get("message", {}).get("content", "")
    if isinstance(content, str):
        return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return ""


def write_runs(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ABLATION_RUN_SCHEMA))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in ABLATION_RUN_SCHEMA})


def existing_rows(path: Path, *, overwrite: bool) -> list[dict[str, Any]]:
    if overwrite or not path.exists() or path.stat().st_size == 0:
        return []
    return pd.read_csv(path).to_dict("records")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs" / "pumpswap_case.json"))
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_CHAT_URL)
    parser.add_argument("--models", default="llama3.1")
    parser.add_argument("--rungs", default="L0,L4,L6,L7")
    parser.add_argument("--ablation-ids", default="baseline,omit_uncertainty_inference,omit_stakeholder_battery")
    parser.add_argument("--runs-per-cell", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--max-cells", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    if not (config.tables_dir / "agentic_prompt_manifest.csv").exists():
        write_prompt_templates(config)
    write_agentic_ablation_manifest(config)

    out_path = config.agent_runs_dir / "agentic_multimodel_ablation_runs.csv"
    rows = existing_rows(out_path, overwrite=args.overwrite)
    seen = {
        (
            str(row.get("model_spec_id", "")),
            str(row.get("rung", "")),
            str(row.get("ablation_id", "")),
            int(row.get("run_id", 0)),
        )
        for row in rows
    }
    prompt_manifest = pd.read_csv(config.tables_dir / "agentic_prompt_manifest.csv")
    models = parse_csv_arg(args.models)
    rungs = parse_csv_arg(args.rungs)
    ablation_ids = parse_csv_arg(args.ablation_ids)
    unknown_rungs = sorted(set(rungs).difference(RUNG_DESCRIPTIONS))
    unknown_ablations = sorted(set(ablation_ids).difference(ABLATION_CONDITIONS))
    if unknown_rungs or unknown_ablations:
        raise SystemExit(f"Unknown rungs={unknown_rungs} ablations={unknown_ablations}")

    cells_seen = 0
    for model in models:
        model_spec_id = sanitize_id(f"Ollama_{model}")
        for rung in rungs:
            data_access = str(prompt_manifest.loc[prompt_manifest["rung"].eq(rung), "data_access"].iloc[0])
            for ablation_id in ablation_ids:
                cells_seen += 1
                if args.max_cells and cells_seen > args.max_cells:
                    write_runs(out_path, rows)
                    score_agentic_ablation_runs(config)
                    print(f"Stopped after --max-cells={args.max_cells}. Wrote {out_path}.", flush=True)
                    return
                system_prompt, user_prompt, digest = build_ablated_prompt(config_path, rung, ablation_id)
                condition = ABLATION_CONDITIONS[ablation_id]
                for run_id in range(1, args.runs_per_cell + 1):
                    key = (model_spec_id, rung, ablation_id, run_id)
                    if not args.no_resume and key in seen:
                        continue
                    raw_rel = (
                        Path("artifacts")
                        / "agent_runs"
                        / "raw_ablation"
                        / f"{model_spec_id}_{ablation_id}_{rung}_run{run_id:03d}.json"
                    )
                    raw_path = config.project_root / raw_rel
                    raw_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        payload = ollama_chat(
                            chat_url=args.ollama_url,
                            model=model,
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            temperature=args.temperature,
                            max_tokens=args.max_tokens,
                            timeout=args.timeout,
                        )
                        content = ollama_content(payload)
                        parsed = extract_json_object(content)
                        status = "ok"
                        error = ""
                    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
                        payload = {}
                        content = ""
                        parsed = {
                            "headline_estimate": None,
                            "ci95_low": None,
                            "ci95_high": None,
                            "worked_decision": "no_or_uncertain",
                            "self_reported_confidence": 0,
                            "final_claim": f"Ollama ablation run failed: {type(exc).__name__}",
                        }
                        status = "error"
                        error = f"{type(exc).__name__}: {exc}"
                    raw_path.write_text(
                        json.dumps(
                            {
                                "execution_status": status,
                                "error": error,
                                "provider": "Ollama",
                                "model": model,
                                "rung": rung,
                                "ablation_id": ablation_id,
                                "run_id": run_id,
                                "temperature": args.temperature,
                                "prompt_hash": digest,
                                "content": content,
                                "ollama_response": payload,
                            },
                            indent=2,
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    base_row = normalize_row(
                        parsed=parsed,
                        raw_text=content,
                        case_id=config.case_id,
                        rung=rung,
                        model=model,
                        provider="Ollama",
                        run_id=run_id,
                        temperature=args.temperature,
                        prompt_digest=digest,
                        data_access=f"{data_access}; ablation={ablation_id}",
                        raw_response_path=str(raw_rel),
                    )
                    base_row.update(
                        {
                            "ablation_id": ablation_id,
                            "ablation_family": condition["family"],
                            "removed_scaffold": condition["removed_scaffold"],
                            "model_spec_id": model_spec_id,
                            "execution_status": status,
                            "error": error[:240],
                        }
                    )
                    rows.append(base_row)
                    seen.add(key)
                    write_runs(out_path, rows)
                    print(f"{model_spec_id} {rung} {ablation_id} run {run_id}/{args.runs_per_cell}: {status}", flush=True)
                    time.sleep(args.sleep)
    write_runs(out_path, rows)
    score_agentic_ablation_runs(config)
    print(f"Wrote {out_path} with {len(rows)} rows.", flush=True)


if __name__ == "__main__":
    main()
