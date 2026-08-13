#!/usr/bin/env python3
"""Upload the approved unified release manifest to a Hugging Face dataset repository."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--manifest", type=Path, default=Path("dataset/huggingface/release_manifest.json"))
    parser.add_argument("--retries", type=int, default=8)
    args = parser.parse_args()
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise SystemExit("Install the dataset upload extra or huggingface_hub before upload") from exc
    repo = args.repo.resolve()
    manifest = json.loads((repo / args.manifest).read_text())
    api = HfApi()
    api.create_repo(repo_id=args.repo_id, repo_type="dataset", private=args.private, exist_ok=True)
    remote_paths = set(api.list_repo_files(repo_id=args.repo_id, repo_type="dataset"))

    def upload(path: Path, path_in_repo: str, commit_message: str) -> None:
        if path_in_repo in remote_paths:
            print(json.dumps({"status": "skipped", "path": path_in_repo}), flush=True)
            return
        for attempt in range(1, args.retries + 1):
            try:
                result = api.upload_file(
                    path_or_fileobj=str(path),
                    path_in_repo=path_in_repo,
                    repo_id=args.repo_id,
                    repo_type="dataset",
                    commit_message=commit_message,
                )
                remote_paths.add(path_in_repo)
                print(json.dumps({"status": "uploaded", "path": path_in_repo, "commit_url": str(result)}), flush=True)
                return
            except Exception as exc:
                if attempt == args.retries:
                    raise
                wait_seconds = min(60, 2 ** attempt)
                print(json.dumps({"status": "retry", "path": path_in_repo, "attempt": attempt, "wait_seconds": wait_seconds, "error": str(exc)}), flush=True)
                time.sleep(wait_seconds)

    entries = sorted(manifest["files"], key=lambda entry: entry["bytes"])
    for index, entry in enumerate(entries, start=1):
        print(json.dumps({"status": "starting", "index": index, "total": len(entries), "path": entry["dataset_path"], "bytes": entry["bytes"]}), flush=True)
        upload(repo / entry["source_path"], entry["dataset_path"], f"Upload {entry['dataset_path']}")

    upload(repo / args.manifest, "release_manifest.json", "Publish Web3AI4IO release manifest v1")
    upload(repo / "dataset/huggingface/README.md", "README.md", "Publish Web3AI4IO dataset card v1")
    info = api.dataset_info(args.repo_id, files_metadata=True)
    print(json.dumps({"repo_id": args.repo_id, "revision": info.sha, "files": len(info.siblings), "private": info.private}))


if __name__ == "__main__":
    main()
