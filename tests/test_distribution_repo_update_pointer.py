"""Fail-closed parsing for an optional no-Release update channel (NRU-001)."""
from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace

from app.distribution.manifest import (
    ManifestError, REPO_UPDATE_MAX_DELTA, RepoUpdatePointer,
    parse_repo_update_pointer, verify_repo_update_manifest,
)

SRC = "c" * 40
BASE = "b" * 40
APP_COMMIT = "d" * 40
DELTA_HASH = "e" * 64


def _manifest() -> bytes:
    return json.dumps({
        "protocol_version": 1,
        "app_version": "1.0",
        "data_version": "1.0",
        "schema_version": 1,
        "source_sha": SRC,
        "entrypoint": "AtlasApp/AtlasApp.exe",
        "files": [{
            "path": "AtlasApp/AtlasApp.exe",
            "size": 4,
            "sha256": hashlib.sha256(b"test").hexdigest(),
        }],
        "delta": {
            "base_source_sha": BASE,
            "archive_sha256": DELTA_HASH,
            "archive_size": 42,
            "paths": ["AtlasApp/AtlasApp.exe"],
        },
    }, separators=(",", ":")).encode()


def _pointer(**changes: object) -> bytes:
    fields: dict[str, object] = {
        "protocol_version": 1,
        "channel": "stable",
        "source_sha": SRC,
        "app_commit_sha": APP_COMMIT,
        "base_source_sha": BASE,
        "manifest_sha256": hashlib.sha256(_manifest()).hexdigest(),
        "delta_sha256": DELTA_HASH,
        "delta_size": 42,
    }
    fields.update(changes)
    return json.dumps(fields, separators=(",", ":")).encode()


class RepoUpdatePointerTests(unittest.TestCase):
    def test_immutable_paths_and_existing_manifest_agree(self) -> None:
        pointer = parse_repo_update_pointer(_pointer())
        self.assertEqual(pointer.pinned_asset_url(), (
            "https://raw.githubusercontent.com/r9327/Dof-Atlas-App/"
            + APP_COMMIT + "/updates/" + SRC + "/atlas-delta.zip"
        ))
        self.assertTrue(pointer.pinned_asset_url(manifest=True).endswith(
            "/updates/" + SRC + "/atlas-manifest.json"
        ))
        self.assertEqual(verify_repo_update_manifest(pointer, _manifest()).source_sha, SRC)

    def test_rejects_raw_repo_head_or_unpinned_commit(self) -> None:
        for value in ("main", "../main", "0" * 39, "x" * 40):
            with self.subTest(value=value), self.assertRaises(ManifestError):
                parse_repo_update_pointer(_pointer(app_commit_sha=value))

    def test_rejects_unsafe_metadata(self) -> None:
        examples = [
            _pointer(channel="draft"),
            _pointer(protocol_version=True),
            _pointer(base_source_sha=SRC),
            _pointer(delta_size=0),
            _pointer(delta_size=REPO_UPDATE_MAX_DELTA + 1),
            _pointer(delta_size=True),
            _pointer(manifest_sha256="missing"),
            _pointer(archive_url="https://example.com/evil.zip"),
            b"{" + b"x" * 4096 + b"}",
            b"not-json",
        ]
        for raw in examples:
            with self.subTest(raw=raw[:80]), self.assertRaises(ManifestError):
                parse_repo_update_pointer(raw)

    def test_rejects_mismatched_manifest_and_patch(self) -> None:
        pointer = parse_repo_update_pointer(_pointer())
        for modified in (
            replace(pointer, manifest_sha256="f" * 64),
            replace(pointer, source_sha="a" * 40),
            replace(pointer, delta_sha256="f" * 64),
            replace(pointer, base_source_sha="a" * 40),
            replace(pointer, delta_size=100),
        ):
            with self.subTest(modified=modified), self.assertRaises(ManifestError):
                verify_repo_update_manifest(modified, _manifest())

    def test_unknown_fields_never_select_a_different_asset_host(self) -> None:
        doc = json.loads(_pointer())
        doc["asset_url"] = "https://example.org/malware.zip"
        with self.assertRaises(ManifestError):
            parse_repo_update_pointer(json.dumps(doc).encode())


if __name__ == "__main__":
    unittest.main()
