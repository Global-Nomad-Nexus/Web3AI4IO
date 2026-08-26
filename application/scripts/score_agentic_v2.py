#!/usr/bin/env python3
"""Score a registered V2 evidence-ladder experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trustworthy_launchpads.agentic_v2_scoring import score_experiment


def resolve(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-config", default=str(ROOT / "configs" / "agentic_v2.json"))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--bootstrap-draws", type=int, default=None)
    args = parser.parse_args()

    experiment = json.loads(Path(args.experiment_config).expanduser().read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else resolve(experiment["output_root"])
    gold_path = resolve(experiment["gold_contract"])
    paths = score_experiment(
        output_dir,
        gold_path=gold_path,
        seed=int(experiment["random_seed"]),
        bootstrap_draws=args.bootstrap_draws or int(experiment["bootstrap_draws"]),
    )
    print(json.dumps({"output_dir": str(output_dir), "outputs": sorted(paths)}, indent=2))


if __name__ == "__main__":
    main()
