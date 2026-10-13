"""Distribution contract tests; stdlib only; fast on Windows and Linux."""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.distribution.install import active_executable, install_release, mark_healthy, read_state, rollback_pending
from app.distribution.manifest import ManifestError, parse_manifest, verify_file
from app.distribution.release_client import UpdateError, _safe_url


def manifest_payload(files=None, **overrides):
    if files is None:
        files = [dict(path="AtlasApp/AtlasApp.exe", size=3, sha256=hashlib.sha256(b"abc").hexdigest())]
    doc = dict(protocol_version=1, app_version="1.2.3", data_version="2026.10",
               schema_version=1, source_sha="a" * 40, entrypoint="AtlasApp/AtlasApp.exe",
               files=files)
    doc.update(overrides)
    return json.dumps(doc).encode("utf-8")


def release_archive(path: Path, files=None):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for name, content in (files or {"AtlasApp/AtlasApp.exe": b"abc"}).items():
            out.writestr(name, content)


class ManifestTests(unittest.TestCase):
    def test_good_manifest_and_digest(self):
        info = parse_manifest(manifest_payload())
        with tempfile.TemporaryDirectory() as location:
            f = Path(location) / "executable"
            f.write_bytes(b"abc")
            self.assertTrue(verify_file(f, info.files[0]))
            f.write_bytes(b"abd")
            self.assertFalse(verify_file(f, info.files[0]))

    def test_path_traversal_and_reserved_names(self):
        paths = ("../oops", "/absolute", "C:/bad", "AtlasApp/../oops",
                 "AtlasApp//double", "AtlasApp\\windows", "AtlasApp/CON",
                 "AtlasApp/file.", "AtlasApp/file ", "AtlasApp/logs/a",
                 "AtlasApp/config/a", "AtlasApp/user/a",
                 "AtlasApp/a:b", "AtlasApp/a?b", "other/AtlasApp.exe")
        for value in paths:
            with self.subTest(path=value):
                with self.assertRaises(ManifestError):
                    parse_manifest(manifest_payload(files=[
                        dict(path="AtlasApp/AtlasApp.exe", size=0, sha256="a" * 64),
                        dict(path=value, size=0, sha256="a" * 64),
                    ]))

    def test_duplicate_casefold(self):
        with self.assertRaises(ManifestError):
            parse_manifest(manifest_payload(files=[
                dict(path=p, size=0, sha256="a" * 64)
                for p in ("AtlasApp/AtlasApp.exe", "atlasapp/atlasapp.exe")
            ]))

    def test_contract_failures(self):
        for update in (
            {"schema_version": True}, {"protocol_version": 2},
            {"source_sha": "x"}, {"app_version": "../../bad"},
            {"entrypoint": "AtlasApp/missing.exe"},
            {"files": [{"path": "AtlasApp/AtlasApp.exe", "size": -1, "sha256": "a" * 64}]},
        ):
            with self.subTest(update=update):
                with self.assertRaises(ManifestError):
                    parse_manifest(manifest_payload(**update))

    def test_manifest_size_cap(self):
        with self.assertRaises(ManifestError):
            parse_manifest(b" " * (2 * 1024 * 1024 + 1))

    def test_url_allowlist(self):
        self.assertEqual(
            _safe_url("https://github.com/r9327/Dof-Atlas-App/releases/download/v1/atlas-windows.zip", asset=True),
            "https://github.com/r9327/Dof-Atlas-App/releases/download/v1/atlas-windows.zip")
        for url in (
            "http://github.com/r9327/Dof-Atlas-App/releases/download/v1/atlas-windows.zip",
            "https://evil.test/x", "https://github.com.evil.test/x",
            "https://github.com/other/repo/releases/download/v1/atlas-windows.zip",
        ):
            with self.subTest(url=url), self.assertRaises(UpdateError):
                _safe_url(url, asset=True)


class InstallationTests(unittest.TestCase):
    def test_install_mark_healthy_and_rollback(self):
        with tempfile.TemporaryDirectory() as location:
            root = Path(location) / "install"
            archive = Path(location) / "release.zip"
            release_archive(archive)
            first = parse_manifest(manifest_payload())
            self.assertTrue(install_release(root, archive, first))
            self.assertTrue(read_state(root)["pending"])
            self.assertEqual(active_executable(root).read_bytes(), b"abc")
            mark_healthy(root)
            self.assertFalse(read_state(root)["pending"])
            self.assertFalse(install_release(root, archive, first))
            second = parse_manifest(manifest_payload(app_version="1.2.4", source_sha="b" * 40))
            self.assertTrue(install_release(root, archive, second))
            self.assertTrue(rollback_pending(root))
            self.assertEqual(read_state(root)["app_version"], "1.2.3")
            self.assertEqual(active_executable(root).read_bytes(), b"abc")

    def test_reject_modified_file_without_activation(self):
        with tempfile.TemporaryDirectory() as location:
            root = Path(location) / "install"
            archive = Path(location) / "release.zip"
            release_archive(archive, {"AtlasApp/AtlasApp.exe": b"BAD"})
            with self.assertRaises(UpdateError):
                install_release(root, archive, parse_manifest(manifest_payload()))
            self.assertIsNone(read_state(root)["active"])

    def test_reject_extra_zip_entry(self):
        with tempfile.TemporaryDirectory() as location:
            archive = Path(location) / "release.zip"
            release_archive(archive, {
                "AtlasApp/AtlasApp.exe": b"abc",
                "AtlasApp/../escape": b"evil",
            })
            with self.assertRaises(UpdateError):
                install_release(Path(location) / "install", archive, parse_manifest(manifest_payload()))


if __name__ == "__main__":
    unittest.main()
