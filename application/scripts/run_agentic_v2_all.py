#!/usr/bin/env python3
"""One-command, resumable execution of the complete V2 audit and verification."""

from __future__ import annotations

import argparse
import csv
import getpass
import os
import shlex
import shutil
import signal
import subprocess
import sys
from collections import Counter
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
APPLICATION = REPO / "application"
KEYCHAIN_SERVICES = {
    "OPENAI_API_KEY": "Web3AI4IO-agentic-v2-openai-key",
    "OPENAI_BASE_URL": "Web3AI4IO-agentic-v2-openai-base-url",
    "DEEPSEEK_API_KEY": "Web3AI4IO-agentic-v2-deepseek-key",
}


def select_compatible_python() -> str:
    """Find a Python runtime with the numerical dependencies required by V2."""

    candidates = [
        os.environ.get("AGENTIC_V2_PYTHON", ""),
        str(REPO / ".venv" / "bin" / "python"),
        str(APPLICATION / ".venv" / "bin" / "python"),
        sys.executable,
    ]
    candidates.extend(
        shutil.which(name) or ""
        for name in ("python3.13", "python3.12", "python3.11", "python3.10", "python3")
    )
    candidates.append("/Library/Frameworks/Python.framework/Versions/3.11/bin/python3")
    checked: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        resolved = str(Path(candidate).expanduser().resolve())
        if resolved in checked or not Path(resolved).is_file():
            continue
        checked.append(resolved)
        probe = subprocess.run(
            [resolved, "-c", "import pandas, numpy"],
            check=False,
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return resolved
    detail = "\n  - ".join(checked) if checked else "(no Python executables found)"
    raise RuntimeError(
        "No compatible Python with pandas and numpy was found. Checked:\n  - "
        f"{detail}\nCreate application/.venv and install application/requirements.txt, "
        "or set AGENTIC_V2_PYTHON to a compatible interpreter."
    )


def runtime_environment() -> dict[str, str]:
    """Load process credentials, then launchctl/Keychain, without printing values."""

    environment = os.environ.copy()
    for name, service in KEYCHAIN_SERVICES.items():
        if environment.get(name) or sys.platform != "darwin":
            continue
        result = subprocess.run(
            ["launchctl", "getenv", name],
            check=False,
            capture_output=True,
            text=True,
        )
        value = result.stdout.rstrip("\n")
        if not value:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-a",
                    getpass.getuser(),
                    "-s",
                    service,
                    "-w",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            value = result.stdout.rstrip("\n") if result.returncode == 0 else ""
        if value:
            environment[name] = value
    environment["PYTHONPATH"] = str(APPLICATION / "src")
    return environment


def print_command(command: list[str]) -> None:
    print("$ " + shlex.join(command), flush=True)


def status_snapshot(registry: Path) -> None:
    if not registry.exists():
        print("progress: registry not created yet", flush=True)
        return
    try:
        with registry.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error) as exc:
        print(f"progress: registry temporarily unreadable ({type(exc).__name__})", flush=True)
        return
    statuses = Counter(row.get("status", "unknown") for row in rows)
    terminal = sum(statuses.get(name, 0) for name in ("ok", "parse_failed", "provider_error"))
    ok_by_model = Counter(
        row.get("model_spec_id", "unknown") for row in rows if row.get("status") == "ok"
    )
    running = [
        {
            "model": row.get("model_spec_id", "unknown"),
            "condition": row.get("condition_id", "unknown"),
            "run": row.get("run_id", "unknown"),
        }
        for row in rows
        if row.get("status") == "running"
    ]
    percent = (100 * terminal / len(rows)) if rows else 0.0
    print(
        f"progress: completed={terminal}/{len(rows)} ({percent:.2f}%) "
        f"statuses={dict(sorted(statuses.items()))} "
        f"ok_by_model={dict(sorted(ok_by_model.items()))} running={running}",
        flush=True,
    )


def normalize_interrupted_registry(registry: Path) -> int:
    """Atomically return stale running rows to the resumable not-run state."""

    if not registry.exists():
        return 0
    with registry.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not fieldnames:
        raise ValueError(f"Registry has no header: {registry}")
    changed = 0
    for row in rows:
        if row.get("status") != "running":
            continue
        row["status"] = "registered_not_run"
        row["started_at_utc"] = ""
        row["completed_at_utc"] = ""
        row["error"] = ""
        changed += 1
    if not changed:
        return 0
    temporary = registry.with_suffix(registry.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, registry)
    return changed


def run_checked(command: list[str], *, environment: dict[str, str]) -> None:
    print_command(command)
    subprocess.run(command, cwd=REPO, env=environment, check=True)


def run_monitored(
    command: list[str],
    *,
    environment: dict[str, str],
    registry: Path,
    interval_seconds: float,
) -> None:
    stale = normalize_interrupted_registry(registry)
    if stale:
        print(f"resume: reset {stale} interrupted running row(s)", flush=True)
    print_command(command)
    process = subprocess.Popen(command, cwd=REPO, env=environment)
    try:
        while True:
            try:
                return_code = process.wait(timeout=interval_seconds)
                break
            except subprocess.TimeoutExpired:
                status_snapshot(registry)
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)
        changed = normalize_interrupted_registry(registry)
        print(f"interrupted: reset {changed} running row(s) for resume", flush=True)
        raise
    changed = normalize_interrupted_registry(registry)
    if changed:
        print(f"recovery: reset {changed} incomplete running row(s)", flush=True)
    status_snapshot(registry)
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(APPLICATION / "artifacts" / "agentic_v2" / "current"),
    )
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--progress-seconds", type=float, default=30.0)
    parser.add_argument("--bootstrap-draws", type=int, default=2000)
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    registry = output_dir / "run_registry.csv"
    environment = runtime_environment()
    python = select_compatible_python()
    print(f"runtime_python={python}", flush=True)

    if not args.skip_tests:
        run_checked(
            [python, "-m", "unittest", "application.tests.test_agentic_v2", "-v"],
            environment=environment,
        )

    run_monitored(
        [
            python,
            "application/scripts/run_agentic_v2.py",
            "--conditions",
            "all",
            "--resume",
            "--timeout",
            str(args.timeout),
            "--output-dir",
            str(output_dir),
        ],
        environment=environment,
        registry=registry,
        interval_seconds=args.progress_seconds,
    )
    run_checked(
        [
            python,
            "application/scripts/score_agentic_v2.py",
            "--output-dir",
            str(output_dir),
            "--bootstrap-draws",
            str(args.bootstrap_draws),
        ],
        environment=environment,
    )
    run_checked(
        [
            python,
            "application/scripts/verify_agentic_v2.py",
            "--output-dir",
            str(output_dir),
        ],
        environment=environment,
    )
    print(f"Complete V2 audit verified at {output_dir}", flush=True)


if __name__ == "__main__":
    main()
