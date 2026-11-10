"""Fail-closed parsing for an optional no-Release update channel (NRU-001)."""
from __future__ import annotations

import hashlib
import io
import json
import stat
import unittest
import zipfile
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


def _valid_delta_zip_bytes(*, file_bytes: bytes = b"test", extra: bool = False,
                           symlink: bool = False, missing: bool = False) -> bytes:
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w") as archive:
        if not missing:
            if symlink:
                link = zipfile.ZipInfo("AtlasApp/AtlasApp.exe")
                link.create_system = 3
                link.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(link, file_bytes)
            else:
                archive.writestr("AtlasApp/AtlasApp.exe", file_bytes)
        if extra:
            archive.writestr("AtlasApp/unexpected.txt", b"extra")
    return memory.getvalue()


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


class RepoUpdateManifestInspectionTests(unittest.TestCase):
    def test_changed_base_reads_only_pointer_and_pinned_manifest(self) -> None:
        from app.distribution.release_client import (
            REPO_UPDATE_POINTER_URL, inspect_repo_update,
        )
        from app.distribution.manifest import MAX_MANIFEST_BYTES, REPO_UPDATE_POINTER_LIMIT

        url = parse_repo_update_pointer(_pointer()).pinned_asset_url(manifest=True)
        reads = []
        def read(address, limit, *, timeout):
            reads.append((address, limit, timeout))
            if address == REPO_UPDATE_POINTER_URL:
                return _pointer()
            if address == url:
                return _manifest()
            raise AssertionError("unexpected network request")
        with patch("app.distribution.release_client._read_limited", side_effect=read):
            result = inspect_repo_update(BASE)
        self.assertIsNotNone(result)
        pointer, manifest = result
        self.assertEqual(pointer.source_sha, SRC)
        self.assertEqual(manifest.source_sha, SRC)
        self.assertEqual(reads, [
            (REPO_UPDATE_POINTER_URL, REPO_UPDATE_POINTER_LIMIT, 5),
            (url, MAX_MANIFEST_BYTES, 10),
        ])

    def test_installed_sha_noop_skips_manifest_and_all_asset_downloads(self) -> None:
        from app.distribution.release_client import (
            REPO_UPDATE_POINTER_URL, inspect_repo_update,
        )
        with patch("app.distribution.release_client._read_limited",
                   return_value=_pointer()) as read:
            self.assertIsNone(inspect_repo_update(SRC))
        self.assertEqual(read.call_count, 1)
        self.assertEqual(read.call_args.args[0], REPO_UPDATE_POINTER_URL)

    def test_bad_manifest_and_publication_race_fail_closed(self) -> None:
        from app.distribution.release_client import UpdateError, inspect_repo_update
        corrupt = json.loads(_manifest())
        corrupt["source_sha"] = "f" * 40
        for payload in (b"missing", json.dumps(corrupt).encode(), b"{}"):
            with self.subTest(payload=payload[:30]):
                with patch("app.distribution.release_client._read_limited",
                           side_effect=[_pointer(), payload]):
                    with self.assertRaises(UpdateError):
                        inspect_repo_update(BASE)

    def test_read_only_transport_accepts_exact_commit_manifest_not_python_or_zip(self) -> None:
        from app.distribution.release_client import UpdateError, _safe_url
        ptr = parse_repo_update_pointer(_pointer())
        manifest_url = ptr.pinned_asset_url(manifest=True)
        self.assertEqual(_safe_url(manifest_url), manifest_url)
        for url in (
            ptr.pinned_asset_url() + "?raw=1",
            ptr.pinned_asset_url().replace(APP_COMMIT, "main"),
            manifest_url + "?raw=1",
            manifest_url + "#frag",
            manifest_url.replace(APP_COMMIT, "main"),
            manifest_url.replace(SRC, "latest"),
            manifest_url.replace("atlas-manifest.json", "main.py"),
            manifest_url.replace("Dof-Atlas-App", "Other-Repo"),
        ):
            with self.subTest(url=url), self.assertRaises(UpdateError):
                _safe_url(url)


class RepoUpdateDeltaDownloadTests(unittest.TestCase):
    @staticmethod
    def _verified_package():
        import zipfile

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as bundle:
            bundle.writestr("AtlasApp/AtlasApp.exe", b"test")
        archive = output.getvalue()
        manifest_doc = json.loads(_manifest())
        manifest_doc["delta"]["archive_sha256"] = hashlib.sha256(archive).hexdigest()
        manifest_doc["delta"]["archive_size"] = len(archive)
        raw = json.dumps(manifest_doc, separators=(",", ":")).encode()
        pointer_doc = json.loads(_pointer())
        pointer_doc.update({
            "manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "delta_sha256": hashlib.sha256(archive).hexdigest(),
            "delta_size": len(archive),
        })
        pointer = parse_repo_update_pointer(json.dumps(pointer_doc).encode())
        return pointer, raw, archive

    def test_delta_is_pinned_hash_verified_and_reuses_existing_cache(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from app.distribution.release_client import download_repo_update_delta

        pointer, raw, archive = self._verified_package()
        with TemporaryDirectory() as tmp:
            dest = Path(tmp)
            with patch("app.distribution.release_client._open",
                       return_value=io.BytesIO(archive)) as open_url:
                downloaded = download_repo_update_delta(pointer, raw, dest)
            open_url.assert_called_once_with(pointer.pinned_asset_url(), {})
            self.assertEqual(downloaded.read_bytes(), archive)
            with patch("app.distribution.release_client._open",
                       side_effect=AssertionError("cached delta should not download")):
                self.assertEqual(
                    download_repo_update_delta(pointer, raw, dest), downloaded,
                )

    def test_corrupt_or_unpublished_delta_cannot_activate_any_slot(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from app.distribution.release_client import UpdateError, download_repo_update_delta

        pointer, raw, archive = self._verified_package()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("app.distribution.release_client._open",
                       return_value=io.BytesIO(archive[:-1] + b"X")):
                with self.assertRaises(UpdateError):
                    download_repo_update_delta(pointer, raw, root)
            self.assertEqual(list(root.glob("*.part")), [])
            self.assertFalse((root / "versions").exists())
            with patch("app.distribution.release_client._open",
                       side_effect=OSError("404 unavailable")):
                with self.assertRaises(UpdateError):
                    download_repo_update_delta(pointer, raw, root)
            self.assertFalse((root / "versions").exists())

    def test_tampered_manifest_is_rejected_without_network_or_disk_writes(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from app.distribution.release_client import UpdateError, download_repo_update_delta

        pointer, raw, _ = self._verified_package()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("app.distribution.release_client._open") as network:
                with self.assertRaises(UpdateError):
                    download_repo_update_delta(pointer, raw + b" ", root)
            network.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])


class RepoUpdatePublisherTests(unittest.TestCase):
    def test_builder_accepts_only_real_verified_frozen_delta(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from scripts.windows.build_repo_update_pointer import build_pointer

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = _valid_delta_zip_bytes()
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


    def test_builder_rejects_matching_zip_hash_with_unsafe_members(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from scripts.windows.build_repo_update_pointer import build_pointer

        cases = {
            "different-bytes": _valid_delta_zip_bytes(file_bytes=b"evil"),
            "extra-file": _valid_delta_zip_bytes(extra=True),
            "missing-file": _valid_delta_zip_bytes(missing=True),
            "symlink": _valid_delta_zip_bytes(symlink=True),
            "invalid-zip": b"not a ZIP",
        }
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "atlas-manifest.json"
            delta = root / "atlas-delta.zip"
            for label, body in cases.items():
                with self.subTest(label=label):
                    doc = json.loads(_manifest())
                    doc["delta"]["archive_size"] = len(body)
                    doc["delta"]["archive_sha256"] = hashlib.sha256(body).hexdigest()
                    manifest.write_text(json.dumps(doc), encoding="utf-8")
                    delta.write_bytes(body)
                    with self.assertRaisesRegex(ManifestError, "Repository delta ZIP"):
                        build_pointer(manifest, delta, APP_COMMIT)


    def test_reused_package_folder_cannot_publish_stale_delta(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from os import urandom
        from app.distribution.manifest import parse_manifest
        from scripts.windows.package_release import package_release

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "AtlasApp"
            app.mkdir()
            (app / "AtlasApp.exe").write_bytes(b"MZ-frozen")
            data = app / "_internal" / "data"
            data.mkdir(parents=True)
            (data / "unchanged.bin").write_bytes(urandom(16 * 1024))
            catalog = data / "quests.json"
            catalog.write_text('{"quests":[1]}', encoding="utf-8")
            _, base = package_release(app, root / "base", "a" * 40,
                                      "1.0", "v1", 1)

            catalog.write_text('{"quests":[1,2]}', encoding="utf-8")
            output = root / "reused"
            _, second = package_release(app, output, "b" * 40,
                                        "1.1", "v2", 1, base_manifest=base)
            self.assertIsNotNone(
                parse_manifest(second.read_bytes()).delta
            )
            self.assertTrue((output / "atlas-delta.zip").is_file())

            _, third = package_release(app, output, "c" * 40,
                                       "1.2", "v3", 1)
            self.assertIsNone(parse_manifest(third.read_bytes()).delta)
            self.assertFalse((output / "atlas-delta.zip").exists())

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


    def test_pointer_cli_never_overwrites_manifest_or_delta(self) -> None:
        import sys
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from scripts.windows.build_repo_update_pointer import main

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = _valid_delta_zip_bytes()
            document = json.loads(_manifest())
            document["delta"]["archive_size"] = len(payload)
            document["delta"]["archive_sha256"] = hashlib.sha256(payload).hexdigest()
            original_manifest = json.dumps(document).encode()
            manifest_path = root / "atlas-manifest.json"
            delta_path = root / "atlas-delta.zip"
            manifest_path.write_bytes(original_manifest)
            delta_path.write_bytes(payload)
            source_args = [
                "--manifest", str(manifest_path), "--delta", str(delta_path),
                "--app-commit-sha", APP_COMMIT,
            ]
            for output in (manifest_path, delta_path):
                with self.subTest(output=output.name):
                    with patch.object(sys, "argv", [
                        "build_repo_update_pointer", *source_args,
                        "--output", str(output),
                    ]):
                        with self.assertRaisesRegex(ManifestError, "overlaps"):
                            main()
                    self.assertEqual(manifest_path.read_bytes(), original_manifest)
                    self.assertEqual(delta_path.read_bytes(), payload)

            # A different filename may still target the same inode.
            alias = root / "pointer-alias.json"
            try:
                alias.hardlink_to(manifest_path)
            except OSError:
                pass  # Host does not support creation of hard links.
            else:
                with patch.object(sys, "argv", [
                    "build_repo_update_pointer", *source_args,
                    "--output", str(alias),
                ]):
                    with self.assertRaisesRegex(ManifestError, "overlaps"):
                        main()
                self.assertEqual(manifest_path.read_bytes(), original_manifest)

            output = root / "stable.json"
            # Simulate an interrupted/offline publishing preparation: the
            # earlier pointer must survive unchanged, without orphan temp files.
            previous_pointer = b"previous-candidate"
            output.write_bytes(previous_pointer)
            with (
                patch.object(sys, "argv", [
                    "build_repo_update_pointer", *source_args, "--output", str(output),
                ]),
                patch("scripts.windows.build_repo_update_pointer.os.replace",
                      side_effect=OSError("simulated Windows file lock")),
            ):
                with self.assertRaises(OSError):
                    main()
            self.assertEqual(output.read_bytes(), previous_pointer)
            self.assertEqual(list(root.glob(".atlas-pointer-*.tmp")), [])
            self.assertEqual(manifest_path.read_bytes(), original_manifest)
            self.assertEqual(delta_path.read_bytes(), payload)
            with patch.object(sys, "argv", [
                "build_repo_update_pointer", *source_args, "--output", str(output),
            ]):
                self.assertEqual(main(), 0)
            self.assertEqual(parse_repo_update_pointer(output.read_bytes()).source_sha, SRC)
            self.assertEqual(list(root.glob(".atlas-pointer-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
