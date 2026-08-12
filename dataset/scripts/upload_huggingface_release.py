#!/usr/bin/env python3
"""Upload the approved unified release manifest to a Hugging Face dataset repository."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--manifest", type=Path, default=Path("dataset/huggingface/release_manifest.json"))
    args = parser.parse_args()
    try:
        from huggingface_hub import CommitOperationAdd, HfApi
    except ImportError as exc:
        raise SystemExit("Install the dataset upload extra or huggingface_hub before upload") from exc
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN is required")
    repo = args.repo.resolve()
    manifest = json.loads((repo / args.manifest).read_text())
    operations = [
        CommitOperationAdd(
            path_in_repo=entry["dataset_path"],
            path_or_fileobj=str(repo / entry["source_path"]),
        )
        for entry in manifest["files"]
    ]
    operations.extend([
        CommitOperationAdd(path_in_repo="README.md", path_or_fileobj=str(repo / "dataset/huggingface/README.md")),
        CommitOperationAdd(path_in_repo="release_manifest.json", path_or_fileobj=str(repo / args.manifest)),
    ])
    api = HfApi(token=token)
    api.create_repo(repo_id=args.repo_id, repo_type="dataset", private=args.private, exist_ok=False)
    result = api.create_commit(
        repo_id=args.repo_id,
        repo_type="dataset",
        operations=operations,
        commit_message="Publish Web3AI4IO unified dataset v1",
    )
    print(json.dumps({"repo_id": args.repo_id, "commit_url": result.commit_url, "commit_oid": result.oid}))


if __name__ == "__main__":
    main()
