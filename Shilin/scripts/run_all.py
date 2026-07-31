#!/usr/bin/env python3
"""Run Shilin's full Pump.fun/PumpSwap replication pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.agentic import score_agent_runs, write_prompt_templates
from trustworthy_launchpads.causal_validation import build_h1_rpc_mechanism_causal_audit
from trustworthy_launchpads.deterministic_ladder import run_ladder
from trustworthy_launchpads.free_public import scan_free_public_assets
from trustworthy_launchpads.identification import build_identification_strength_summary, build_moralis_sample_selection_audit
from trustworthy_launchpads.io import ensure_output_dirs, file_sha256, load_config, write_json
from trustworthy_launchpads.metrics import build_metric_battery
from trustworthy_launchpads.plots import make_all_figures
from trustworthy_launchpads.readiness import build_readiness_audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs" / "pumpswap_case.json"))
    args = parser.parse_args()

    config = load_config(args.config)
    ensure_output_dirs(config)

    free_public_inventory = scan_free_public_assets(config)
    ladder_outputs = run_ladder(config)
    build_h1_rpc_mechanism_causal_audit(config)
    build_moralis_sample_selection_audit(config)
    build_identification_strength_summary(config)
    battery = build_metric_battery(config)
    prompt_manifest = write_prompt_templates(config)
    agent_scores = score_agent_runs(config, ladder_outputs.ladder)
    build_readiness_audit(config, ladder_outputs.ladder, agent_scores)

    make_all_figures(
        config,
        ladder_outputs.ladder,
        ladder_outputs.event_study,
        ladder_outputs.frequency,
        battery,
    )

    manifest = {
        "case_id": config.case_id,
        "config_path": str(config.config_path),
        "tables": sorted(p.name for p in config.tables_dir.glob("*")),
        "figures": sorted(p.name for p in config.figures_dir.glob("*")),
        "free_public_files": int(len(free_public_inventory)),
        "prompt_count": int(len(prompt_manifest)),
        "config_sha256": file_sha256(config.config_path),
    }
    write_json(config.output_root / "run_manifest.json", manifest)
    print("Shilin pipeline complete.")
    print(f"Artifacts: {config.output_root}")


if __name__ == "__main__":
    main()
