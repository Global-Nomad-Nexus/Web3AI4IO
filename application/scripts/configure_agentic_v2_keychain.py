#!/usr/bin/env python3
"""Securely configure or remove V2 provider credentials in macOS Keychain."""

from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
import urllib.parse


KEYCHAIN_SERVICES = {
    "OPENAI_API_KEY": "Web3AI4IO-agentic-v2-openai-key",
    "OPENAI_BASE_URL": "Web3AI4IO-agentic-v2-openai-base-url",
    "DEEPSEEK_API_KEY": "Web3AI4IO-agentic-v2-deepseek-key",
}


def require_macos() -> None:
    if sys.platform != "darwin":
        raise SystemExit("This helper requires macOS Keychain.")


def store_hidden_secret(name: str) -> None:
    service = KEYCHAIN_SERVICES[name]
    print(f"Enter {name} in the Keychain prompt (input is hidden).", flush=True)
    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-U",
            "-a",
            getpass.getuser(),
            "-s",
            service,
            "-l",
            f"Web3AI4IO {name}",
            "-w",
        ],
        check=True,
    )


def store_public_value(name: str, value: str) -> None:
    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-U",
            "-a",
            getpass.getuser(),
            "-s",
            KEYCHAIN_SERVICES[name],
            "-l",
            f"Web3AI4IO {name}",
            "-w",
            value,
        ],
        check=True,
        capture_output=True,
    )


def delete_all() -> None:
    for name, service in KEYCHAIN_SERVICES.items():
        subprocess.run(
            [
                "security",
                "delete-generic-password",
                "-a",
                getpass.getuser(),
                "-s",
                service,
            ],
            check=False,
            capture_output=True,
        )
        subprocess.run(["launchctl", "unsetenv", name], check=False, capture_output=True)
    print("Web3AI4IO Keychain and launchctl credentials removed.")


def validate_base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("OpenAI base URL must be HTTPS and contain no embedded credentials")
    return value.strip().rstrip("/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openai-base-url", default="")
    parser.add_argument("--skip-openai", action="store_true")
    parser.add_argument("--skip-deepseek", action="store_true")
    parser.add_argument("--delete", action="store_true")
    args = parser.parse_args()
    require_macos()
    if args.delete:
        delete_all()
        return
    if not args.skip_openai:
        store_hidden_secret("OPENAI_API_KEY")
        base_url = args.openai_base_url.strip() or input(
            "OpenAI-compatible base URL [https://api.openai.com]: "
        ).strip()
        store_public_value(
            "OPENAI_BASE_URL",
            validate_base_url(base_url or "https://api.openai.com"),
        )
    if not args.skip_deepseek:
        store_hidden_secret("DEEPSEEK_API_KEY")
    print("Credentials saved in macOS Keychain; values were not printed.")


if __name__ == "__main__":
    main()
