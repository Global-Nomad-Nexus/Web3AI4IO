#!/usr/bin/env python3
"""Run registered multi-model scaffold ablations with OpenAI-compatible APIs.

The script writes real model outputs to
``artifacts/agent_runs/agentic_multimodel_ablation_runs.csv``. Without API
credentials it still writes the registered ablation manifest and exits cleanly,
so the benchmark can distinguish a planned experiment from completed evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
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
    prompt_hash,
    score_agentic_ablation_runs,
    write_agentic_ablation_manifest,
    write_prompt_templates,
)
from trustworthy_launchpads.io import load_config

from run_agentic_deepseek import (
    DEFAULT_ENV_PATH,
    build_data_bundle,
    extract_json_object,
    normalize_row,
    load_env_file,
)


DEFAULT_OPENAI_COMPATIBLE_URL = "https://api.deepseek.com/chat/completions"


def parse_csv_arg(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def sanitize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "model"


def parse_model_spec(value: str | None, env_values: dict[str, str]) -> list[dict[str, str]]:
    if value:
        specs = []
        for spec_text in parse_csv_arg(value):
            parts = spec_text.split("|")
            if len(parts) != 5:
                raise SystemExit(
                    "--model-spec entries must be spec_id|provider|model|chat_url|api_key_env"
                )
            spec_id, provider, model, chat_url, api_key_env = [part.strip() for part in parts]
            specs.append(
                {
                    "model_spec_id": sanitize_id(spec_id),
                    "provider": provider,
                    "model": model,
                    "chat_url": chat_url,
                    "api_key_env": api_key_env,
                }
            )
        return specs
    model = os.environ.get("DEEPSEEK_MODEL") or env_values.get("DEEPSEEK_MODEL") or "deepseek-chat"
    return [
        {
            "model_spec_id": sanitize_id(f"DeepSeek_{model}"),
            "provider": "DeepSeek",
            "model": model,
            "chat_url": os.environ.get("DEEPSEEK_URL")
            or env_values.get("DEEPSEEK_URL")
            or DEFAULT_OPENAI_COMPATIBLE_URL,
            "api_key_env": "DEEPSEEK_API_KEY",
        }
    ]


def strip_sections(text: str, keywords: list[str]) -> str:
    lines = text.splitlines()
    out: list[str] = []
    dropping = False
    for line in lines:
        lower = line.lower()
        if lower.startswith("[") and lower.endswith("]"):
            dropping = any(keyword in lower for keyword in keywords)
        if dropping:
            continue
        out.append(line)
    return "\n".join(out).strip()


def strip_matching_lines(text: str, keywords: list[str]) -> str:
    kept = [
        line
        for line in text.splitlines()
        if not any(keyword in line.lower() for keyword in keywords)
    ]
    stripped = "\n".join(kept).strip()
    if stripped:
        return stripped
    return "You are an empirical research agent being evaluated. Return a JSON object matching the registered schema."


def ablation_keywords(ablation_id: str) -> list[str]:
    return {
        "baseline": [],
        "omit_pretrend_diagnostics": [
            "pretrend",
            "pre-trend",
            "event-study",
            "event study",
            "parallel trend",
            "parallel trends",
        ],
        "omit_uncertainty_inference": [
            "uncertainty",
            "confidence interval",
            "ci95",
            "ci ",
            "p-value",
            "p_value",
            "bootstrap",
            "few-cluster",
            "few cluster",
        ],
        "omit_stakeholder_battery": [
            "stakeholder",
            "retail",
            "creator",
            "community",
            "holder concentration",
            "hf pump",
            "risk snapshot",
        ],
        "omit_data_gap_ledger": [
            "data availability",
            "data-availability",
            "claim scope",
            "claim-scope",
            "data gap",
            "do not invent",
            "limitations",
        ],
    }.get(ablation_id, [])


def build_ablated_prompt(config_path: Path, rung: str, ablation_id: str) -> tuple[str, str, str]:
    config = load_config(config_path)
    system = (config.project_root / f"prompts/{rung}_system.md").read_text(encoding="utf-8")
    user = (config.project_root / f"prompts/{rung}_user.md").read_text(encoding="utf-8")
    bundle = build_data_bundle(config_path, rung)
    keywords = ablation_keywords(ablation_id)
    if keywords:
        system = strip_matching_lines(system, keywords)
        user = strip_matching_lines(user, keywords)
        bundle = strip_sections(strip_matching_lines(bundle, keywords), keywords)
    user_prompt = (
        f"{user}\n\n"
        "Return only a JSON object with these keys: headline_estimate, ci95_low, ci95_high, "
        "worked_decision, self_reported_confidence, final_claim. Use null for unavailable numeric fields.\n\n"
        f"{bundle}"
    )
    return system, user_prompt, prompt_hash(system, user_prompt)


def chat_completion(
    *,
    api_key: str,
    chat_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    response_format: bool,
    insecure_skip_tls_verify: bool,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if response_format:
        body["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        chat_url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    context = ssl._create_unverified_context() if insecure_skip_tls_verify else None
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if response_format and exc.code in {400, 422}:
            return chat_completion(
                api_key=api_key,
                chat_url=chat_url,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                response_format=False,
                insecure_skip_tls_verify=insecure_skip_tls_verify,
            )
        raise


def response_content(payload: dict[str, Any]) -> str:
    return (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )


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
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument(
        "--model-spec",
        default="",
        help="Comma-separated spec_id|provider|model|chat_url|api_key_env entries. Defaults to DeepSeek.",
    )
    parser.add_argument("--rungs", default=",".join(RUNG_DESCRIPTIONS))
    parser.add_argument("--ablation-ids", default=",".join(ABLATION_CONDITIONS))
    parser.add_argument("--runs-per-cell", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=900)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--max-cells", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--insecure-skip-tls-verify",
        action="store_true",
        help="Use only when local Python CA certificates fail for the configured HTTPS endpoint.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    if not (config.tables_dir / "agentic_prompt_manifest.csv").exists():
        write_prompt_templates(config)
    write_agentic_ablation_manifest(config)
    env_values = load_env_file(Path(args.env_file).expanduser())
    model_specs = parse_model_spec(args.model_spec, env_values)
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
    rungs = parse_csv_arg(args.rungs)
    ablation_ids = parse_csv_arg(args.ablation_ids)
    unknown_rungs = sorted(set(rungs).difference(RUNG_DESCRIPTIONS))
    unknown_ablations = sorted(set(ablation_ids).difference(ABLATION_CONDITIONS))
    if unknown_rungs or unknown_ablations:
        raise SystemExit(f"Unknown rungs={unknown_rungs} ablations={unknown_ablations}")
    temperature = (
        args.temperature
        if args.temperature is not None
        else float(config.raw.get("agentic", {}).get("temperature", 0))
    )
    if args.dry_run:
        score_agentic_ablation_runs(config)
        print("Registered agentic ablation manifest only; dry-run requested.")
        return

    prompt_manifest = pd.read_csv(config.tables_dir / "agentic_prompt_manifest.csv")
    cells_seen = 0
    for spec in model_specs:
        api_key = os.environ.get(spec["api_key_env"]) or env_values.get(spec["api_key_env"])
        if not api_key:
            print(f"Skipping {spec['model_spec_id']}: {spec['api_key_env']} not found.", flush=True)
            continue
        for rung in rungs:
            data_access = str(prompt_manifest.loc[prompt_manifest["rung"].eq(rung), "data_access"].iloc[0])
            for ablation_id in ablation_ids:
                cells_seen += 1
                if args.max_cells and cells_seen > args.max_cells:
                    write_runs(out_path, rows)
                    score_agentic_ablation_runs(config)
                    print(f"Stopped after --max-cells={args.max_cells}. Wrote {out_path}.")
                    return
                system_prompt, user_prompt, digest = build_ablated_prompt(config_path, rung, ablation_id)
                condition = ABLATION_CONDITIONS[ablation_id]
                for run_id in range(1, args.runs_per_cell + 1):
                    key = (spec["model_spec_id"], rung, ablation_id, run_id)
                    if not args.no_resume and key in seen:
                        continue
                    raw_rel = (
                        Path("artifacts")
                        / "agent_runs"
                        / "raw_ablation"
                        / f"{spec['model_spec_id']}_{ablation_id}_{rung}_run{run_id:03d}.json"
                    )
                    raw_path = config.project_root / raw_rel
                    raw_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        payload = chat_completion(
                            api_key=api_key,
                            chat_url=spec["chat_url"],
                            model=spec["model"],
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            temperature=temperature,
                            max_tokens=args.max_tokens,
                            timeout=args.timeout,
                            response_format=True,
                            insecure_skip_tls_verify=args.insecure_skip_tls_verify,
                        )
                        content = response_content(payload)
                        parsed = extract_json_object(content)
                        status = "ok"
                        error = ""
                    except Exception as exc:
                        payload = {}
                        content = ""
                        parsed = {
                            "headline_estimate": None,
                            "ci95_low": None,
                            "ci95_high": None,
                            "worked_decision": "no_or_uncertain",
                            "self_reported_confidence": 0,
                            "final_claim": f"Agentic ablation run failed: {type(exc).__name__}",
                        }
                        status = "error"
                        error = f"{type(exc).__name__}: {exc}"
                    raw_path.write_text(
                        json.dumps(
                            {
                                "execution_status": status,
                                "error": error,
                                "model_spec": spec,
                                "rung": rung,
                                "ablation_id": ablation_id,
                                "run_id": run_id,
                                "temperature": temperature,
                                "prompt_hash": digest,
                                "content": content,
                                "api_response": payload,
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
                        model=spec["model"],
                        provider=spec["provider"],
                        run_id=run_id,
                        temperature=temperature,
                        prompt_digest=digest,
                        data_access=f"{data_access}; ablation={ablation_id}",
                        raw_response_path=str(raw_rel),
                    )
                    base_row.update(
                        {
                            "ablation_id": ablation_id,
                            "ablation_family": condition["family"],
                            "removed_scaffold": condition["removed_scaffold"],
                            "model_spec_id": spec["model_spec_id"],
                            "execution_status": status,
                            "error": error[:240],
                        }
                    )
                    rows.append(base_row)
                    seen.add(key)
                    write_runs(out_path, rows)
                    print(
                        f"{spec['model_spec_id']} {rung} {ablation_id} run {run_id}/{args.runs_per_cell}: {status}",
                        flush=True,
                    )
                    time.sleep(args.sleep)
    write_runs(out_path, rows)
    score_agentic_ablation_runs(config)
    print(f"Wrote {out_path} with {len(rows)} rows.")


if __name__ == "__main__":
    main()
