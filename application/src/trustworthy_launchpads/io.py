"""Input/output helpers for the application-arm replication package."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CaseConfig:
    """Resolved configuration for one empirical case."""

    raw: dict[str, Any]
    config_path: Path
    project_root: Path

    @property
    def case_id(self) -> str:
        return str(self.raw["case_id"])

    @property
    def upstream_root(self) -> Path:
        return Path(self.raw["upstream_mvp_root"]).expanduser()

    @property
    def public_root(self) -> Path:
        return Path(self.raw["public_mvp_root"]).expanduser()

    @property
    def output_root(self) -> Path:
        path = Path(self.raw["output_root"])
        if not path.is_absolute():
            path = self.project_root / path
        return path

    @property
    def tables_dir(self) -> Path:
        return self.output_root / "tables"

    @property
    def figures_dir(self) -> Path:
        return self.output_root / "figures"

    @property
    def agent_runs_dir(self) -> Path:
        return self.output_root / "agent_runs"

    def source_path(self, key: str, *, required: bool = True) -> Path:
        """Resolve a configured input path, preferring the full local dataset."""

        rel = Path(self.raw[key])
        candidates = [self.upstream_root / rel, self.public_root / rel]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        if required:
            checked = ", ".join(str(c) for c in candidates)
            raise FileNotFoundError(f"Missing configured source {key}; checked {checked}")
        return candidates[0]

    def legacy_table(self, filename: str, *, required: bool = True) -> Path:
        rel = Path(self.raw["legacy_tables"]) / filename
        candidates = [self.upstream_root / rel, self.public_root / rel]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        if required:
            checked = ", ".join(str(c) for c in candidates)
            raise FileNotFoundError(f"Missing legacy table {filename}; checked {checked}")
        return candidates[0]


def load_config(path: str | Path | None = None) -> CaseConfig:
    config_path = Path(path) if path else PROJECT_ROOT / "configs" / "pumpswap_case.json"
    config_path = config_path.expanduser().resolve()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    return CaseConfig(raw=raw, config_path=config_path, project_root=PROJECT_ROOT)


def ensure_output_dirs(config: CaseConfig) -> None:
    for path in [config.tables_dir, config.figures_dir, config.agent_runs_dir]:
        path.mkdir(parents=True, exist_ok=True)


def read_market_panel(config: CaseConfig) -> pd.DataFrame:
    panel = pd.read_csv(config.source_path("market_panel"))
    panel["date"] = pd.to_datetime(panel["date"], utc=True)
    if "date_str" not in panel:
        panel["date_str"] = panel["date"].dt.strftime("%Y-%m-%d")
    return panel


def read_red_pump_outcomes(config: CaseConfig, *, usecols: list[str] | None = None) -> pd.DataFrame:
    path = config.source_path("red_pump_token_outcomes")
    df = pd.read_csv(path, usecols=usecols, low_memory=False)
    return df


def read_hf_pump_sentiment(config: CaseConfig, *, latest_per_mint: bool = True) -> pd.DataFrame:
    path = config.source_path("hf_pump_sentiment_sample")
    df = pd.read_json(path, lines=True)
    if latest_per_mint and {"mint", "snapshot_at"}.issubset(df.columns):
        df = df.sort_values(["mint", "snapshot_at"]).drop_duplicates("mint", keep="last")
    return df.reset_index(drop=True)


def read_optional_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path)


def file_sha256(path: Path, *, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(block_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]] | pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    df.to_csv(path, index=False)
