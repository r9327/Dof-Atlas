"""Prepare, never publish, a verified immutable repo-update pointer.

The GitHub publishing workflow must commit immutable package files first,
obtain their exact APP commit SHA, then generate/publish the stable pointer.
This tool cannot certify an unapproved source or bypass delivery guards.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path

from app.distribution.manifest import (
    ManifestError, MAX_MANIFEST_BYTES, REPO_UPDATE_MAX_DELTA, RepoUpdatePointer, ReleaseFile,
    parse_manifest, parse_repo_update_pointer, valid_source_sha,
    verify_file, verify_repo_update_manifest,
)


def _verify_delta_members(path: Path, manifest) -> None:
    """Check the actual ZIP members against the frozen manifest before publication.

    The archive SHA binds ZIP bytes; this also proves the ZIP can supply every
    changed file and cannot contain extra paths, links or corrupt file payloads.
    This is a publishing preflight, not an authorization to activate an update.
    """
    assert manifest.delta is not None
    changed_paths = set(manifest.delta.paths)
    expected = {entry.path: entry for entry in manifest.files
                if entry.path in changed_paths}
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) != len(expected) or {i.filename for i in members} != set(expected):
                raise ManifestError("Repository delta ZIP members differ from manifest")
            for member in members:
                entry = expected[member.filename]
                mode = member.external_attr >> 16
                if (member.is_dir() or member.flag_bits & 1
                        or stat.S_ISLNK(mode)
                        or (stat.S_IFMT(mode) and not stat.S_ISREG(mode))
                        or member.file_size != entry.size):
                    raise ManifestError("Repository delta ZIP contains unsafe file metadata")
                digest = hashlib.sha256()
                length = 0
                with archive.open(member) as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        length += len(block)
                        if length > entry.size:
                            raise ManifestError("Repository delta ZIP expands beyond manifest")
                        digest.update(block)
                if length != entry.size or digest.hexdigest() != entry.sha256:
                    raise ManifestError("Repository delta ZIP file integrity mismatch")
    except (OSError, RuntimeError, zipfile.BadZipFile, EOFError) as exc:
        raise ManifestError("Repository delta ZIP cannot be verified") from exc


def build_pointer(manifest_path: Path, delta_path: Path, app_commit_sha: str) -> bytes:
    """Return a validated pointer only for a real hash-verified frozen delta."""
    commit = valid_source_sha(app_commit_sha)
    if manifest_path.is_symlink() or delta_path.is_symlink():
        raise ManifestError("Repository update package cannot contain symlinks")
    # A stat alone is not a bound: another process can grow the manifest
    # before it is read. Never allocate an arbitrary-sized input first.
    try:
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ManifestError("Repository update manifest exceeds safe size")
        with manifest_path.open("rb") as stream:
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
    except OSError as exc:
        raise ManifestError("Repository update manifest cannot be read") from exc
    if len(raw) > MAX_MANIFEST_BYTES or manifest_path.is_symlink():
        raise ManifestError("Repository update manifest exceeds safe size")
    manifest = parse_manifest(raw)
    delta = manifest.delta
    if delta is None:
        raise ManifestError("Repository update requires a frozen delta")
    if not 0 < delta.archive_size <= REPO_UPDATE_MAX_DELTA:
        raise ManifestError("Repository update exceeds safe Git file size")
    if not verify_file(delta_path, ReleaseFile(delta_path.name, delta.archive_size, delta.archive_sha256)):
        raise ManifestError("Repository update payload does not match manifest")
    _verify_delta_members(delta_path, manifest)
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
    # The CLI must never replace either input with the generated pointer,
    # including via a relative path, symlink or pre-existing hard link.
    sources = (args.manifest, args.delta)
    if args.output.is_symlink() or any(
        args.output.resolve() == source.resolve()
        or (args.output.exists() and args.output.samefile(source))
        for source in sources
    ):
        raise ManifestError("Pointer output overlaps a source artifact")
    result = build_pointer(args.manifest, args.delta, args.app_commit_sha)
    # Only the reviewed publishing CI may move the stable pointer. Never
    # write a token or an unverified external URL into this artifact.
    args.output.write_bytes(result)
    print("VALIDATED_REPO_UPDATE_POINTER_ONLY; NOT_PUBLISHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
