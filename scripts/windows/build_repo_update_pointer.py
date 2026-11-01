"""Prepare, never publish, a verified immutable repo-update pointer.

The GitHub publishing workflow must commit immutable package files first,
obtain their exact APP commit SHA, then generate/publish the stable pointer.
This tool cannot certify an unapproved source or bypass delivery guards.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.distribution.manifest import (
    ManifestError, REPO_UPDATE_MAX_DELTA, RepoUpdatePointer, ReleaseFile,
    parse_manifest, parse_repo_update_pointer, valid_source_sha,
    verify_file, verify_repo_update_manifest,
)


def build_pointer(manifest_path: Path, delta_path: Path, app_commit_sha: str) -> bytes:
    """Return a validated pointer only for a real hash-verified frozen delta."""
    commit = valid_source_sha(app_commit_sha)
    if manifest_path.is_symlink() or delta_path.is_symlink():
        raise ManifestError("Repository update package cannot contain symlinks")
    raw = manifest_path.read_bytes()
    manifest = parse_manifest(raw)
    delta = manifest.delta
    if delta is None:
        raise ManifestError("Repository update requires a frozen delta")
    if not 0 < delta.archive_size <= REPO_UPDATE_MAX_DELTA:
        raise ManifestError("Repository update exceeds safe Git file size")
    if not verify_file(delta_path, ReleaseFile(delta_path.name, delta.archive_size, delta.archive_sha256)):
        raise ManifestError("Repository update payload does not match manifest")
    doc = {
        "protocol_version": 1,
        "channel": "stable",
        "source_sha": manifest.source_sha,
        "app_commit_sha": commit,
        "base_source_sha": delta.base_source_sha,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "delta_sha256": delta.archive_sha256,
        "delta_size": delta.archive_size,
    }
    encoded = (json.dumps(doc, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    pointer: RepoUpdatePointer = parse_repo_update_pointer(encoded)
    verify_repo_update_manifest(pointer, raw)
    return encoded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--delta", type=Path, required=True)
    parser.add_argument("--app-commit-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_pointer(args.manifest, args.delta, args.app_commit_sha)
    # Only the reviewed publishing CI may move the stable pointer. Never
    # write a token or an unverified external URL into this artifact.
    args.output.write_bytes(result)
    print("VALIDATED_REPO_UPDATE_POINTER_ONLY; NOT_PUBLISHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
