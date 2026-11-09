"""Fail-closed parsing for an optional no-Release update channel (NRU-001)."""
from __future__ import annotations

import hashlib
import io
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

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



class RepoUpdateProbeTests(unittest.TestCase):
    def test_noop_uses_one_small_request_and_no_zip(self) -> None:
        from app.distribution.release_client import (
            REPO_UPDATE_POINTER_URL, probe_repo_update,
        )
        from app.distribution.manifest import REPO_UPDATE_POINTER_LIMIT

        with patch("app.distribution.release_client._read_limited",
                   return_value=_pointer()) as read:
            candidate = probe_repo_update(BASE)
            unchanged = probe_repo_update(SRC)
        self.assertEqual(candidate.source_sha, SRC)
        self.assertIsNone(unchanged)
        self.assertEqual(read.call_count, 2)
        read.assert_any_call(
            REPO_UPDATE_POINTER_URL, REPO_UPDATE_POINTER_LIMIT, timeout=5,
        )

    def test_missing_installed_sha_stays_on_release_bootstrap(self) -> None:
        from app.distribution.release_client import probe_repo_update

        with patch("app.distribution.release_client._read_limited") as read:
            self.assertIsNone(probe_repo_update(None))
            self.assertIsNone(probe_repo_update("main"))
        read.assert_not_called()

    def test_incompatible_or_malformed_pointer_is_not_a_valid_update(self) -> None:
        from app.distribution.release_client import UpdateError, probe_repo_update

        for installed, payload in (
            ("0" * 40, _pointer()),
            (BASE, b"not-json"),
            (BASE, _pointer(archive_url="https://example.com/malware.zip")),
        ):
            with self.subTest(installed=installed, payload=payload[:50]):
                with patch("app.distribution.release_client._read_limited",
                           return_value=payload):
                    with self.assertRaises(UpdateError):
                        probe_repo_update(installed)

    def test_raw_update_transport_rejects_unreviewed_paths(self) -> None:
        from app.distribution.release_client import (
            REPO_UPDATE_POINTER_URL, UpdateError, _safe_url,
        )
        self.assertEqual(_safe_url(REPO_UPDATE_POINTER_URL), REPO_UPDATE_POINTER_URL)
        for url in (
            "https://raw.githubusercontent.com/r9327/Dof-Atlas-App/main/main.py",
            "https://raw.githubusercontent.com/r9327/Dof-Atlas-App/main/updates/stable.json?alt=1",
            "https://raw.githubusercontent.com/attacker/repo/main/updates/stable.json",
        ):
            with self.subTest(url=url), self.assertRaises(UpdateError):
                _safe_url(url)


class RepoUpdatePublisherTests(unittest.TestCase):
    def test_builder_accepts_only_real_verified_frozen_delta(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from scripts.windows.build_repo_update_pointer import build_pointer

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = b"valid-win-delta"
            manifest_doc = json.loads(_manifest())
            manifest_doc["delta"]["archive_sha256"] = hashlib.sha256(body).hexdigest()
            manifest_doc["delta"]["archive_size"] = len(body)
            raw = json.dumps(manifest_doc).encode()
            manifest = root / "atlas-manifest.json"
            delta = root / "atlas-delta.zip"
            manifest.write_bytes(raw)
            delta.write_bytes(body)
            pointer = parse_repo_update_pointer(build_pointer(manifest, delta, APP_COMMIT))
            self.assertEqual(pointer.source_sha, SRC)
            self.assertEqual(pointer.app_commit_sha, APP_COMMIT)
            self.assertEqual(pointer.delta_size, len(body))
            self.assertEqual(verify_repo_update_manifest(pointer, raw).source_sha, SRC)

            delta.write_bytes(b"tampered")
            with self.assertRaises(ManifestError):
                build_pointer(manifest, delta, APP_COMMIT)

    def test_builder_bounded_manifest_read_refuses_concurrent_growth(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from scripts.windows.build_repo_update_pointer import build_pointer

        with TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "atlas-manifest.json"
            delta = Path(tmp) / "atlas-delta.zip"
            original = _manifest()
            manifest.write_bytes(original)
            delta.write_bytes(b"synthetic")
            limit = len(original) + 16
            original_open = Path.open

            def growing_file(path, *args, **kwargs):
                if path == manifest:
                    return io.BytesIO(b"x" * (limit + 1))
                return original_open(path, *args, **kwargs)

            # Stat sees the original small manifest. The concurrent writer
            # makes the stream exceed the cap only after that preflight.
            with (
                patch("scripts.windows.build_repo_update_pointer.MAX_MANIFEST_BYTES", limit),
                patch.object(Path, "open", autospec=True,
                             side_effect=growing_file),
            ):
                with self.assertRaises(ManifestError):
                    build_pointer(manifest, delta, APP_COMMIT)

    def test_builder_refuses_missing_or_invalid_package(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from scripts.windows.build_repo_update_pointer import build_pointer

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "atlas-manifest.json"
            delta = root / "atlas-delta.zip"
            manifest.write_bytes(_manifest())
            with self.assertRaises(ManifestError):
                build_pointer(manifest, delta, APP_COMMIT)
            delta.write_bytes(b"whatever")
            with self.assertRaises(ManifestError):
                build_pointer(manifest, delta, "main")


if __name__ == "__main__":
    unittest.main()
