from __future__ import annotations

import json
import re
from pathlib import Path


STUDY_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def resolve_table(name: str) -> Path:
    candidates = [
        WORKSPACE_ROOT / "web3IO" / "tabs" / name,
        STUDY_ROOT / "paper_tables" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Cannot find {name} in {[str(path) for path in candidates]}")


AB = resolve_table("tab_ablation.tex")
ARMS = resolve_table("tab_arms.tex")
OUTPUT = STUDY_ROOT / "artifacts" / "deterministic_crosscheck.json"


def rows(path: Path, decision_column: int) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for match in re.finditer(r"(?ms)^\s*(L[0-7])\s*&(.+?)\\\\", text):
        rung = match.group(1)
        cells = re.split(r"(?<!\\)&", match.group(0).removesuffix(r"\\"))
        value = " ".join(cells[decision_column].split()).strip()
        found[rung] = value
    return found


def main() -> None:
    ablation = rows(AB, decision_column=4)
    arms = rows(ARMS, decision_column=2)
    expected = [f"L{i}" for i in range(8)]
    if sorted(ablation) != expected or sorted(arms) != expected:
        raise AssertionError({"ablation_rows": sorted(ablation), "arms_rows": sorted(arms)})
    comparisons = {
        rung: {
            "tab_ablation": ablation[rung],
            "tab_arms_deterministic": arms[rung],
            "agree": ablation[rung] == arms[rung],
        }
        for rung in expected
    }
    all_agree = all(item["agree"] for item in comparisons.values())
    result = {"all_rungs_agree": all_agree, "comparisons": comparisons}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not all_agree:
        raise AssertionError("Deterministic columns disagree")


if __name__ == "__main__":
    main()
