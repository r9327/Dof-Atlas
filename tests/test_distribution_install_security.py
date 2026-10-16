"""Updater security regressions: hostile local state and incompatible releases."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.distribution.install import install_release, read_state, slot_path
from app.distribution.manifest import ManifestError, parse_manifest
from app.distribution.release_client import UpdateError


def manifest(*, schema=1, extra=None):
    files = [
        {"path": "AtlasApp/AtlasApp.exe", "size": 3,
         "sha256": hashlib.sha256(b"MZ!").hexdigest()},
    ]
    if extra:
        files.extend(extra)
    return parse_manifest(json.dumps({
        "protocol_version": 1, "app_version": "1.0.0",
        "data_version": "2026.10", "schema_version": schema,
        "source_sha": "a" * 40, "entrypoint": "AtlasApp/AtlasApp.exe",
        "files": files,
    }).encode("utf-8"))


class DistributionSecurityTests(unittest.TestCase):
    def test_reject_path_escape_from_installation_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for bad in ("..", ".", ".bad", "abc.", "../outside", "a/b", "a\\b"):
                with self.subTest(slot=bad):
                    with self.assertRaises(UpdateError):
                        slot_path(root, bad)
                    (root / "state.json").write_text(
                        json.dumps({"active": bad, "previous": None, "pending": False}),
                        encoding="utf-8",
                    )
                    with self.assertRaises(UpdateError):
                        read_state(root)

    def test_reject_future_schema_without_activating(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with zipfile.ZipFile(root / "release.zip", "w") as archive:
                archive.writestr("AtlasApp/AtlasApp.exe", b"MZ!")
            with self.assertRaises(UpdateError):
                install_release(root / "installed", root / "release.zip", manifest(schema=2))
            self.assertFalse((root / "installed" / "state.json").exists())

    def test_reject_file_directory_collision(self):
        with self.assertRaises(ManifestError):
            manifest(extra=[{
                "path": "AtlasApp/AtlasApp.exe/assets",
                "size": 0, "sha256": hashlib.sha256(b"").hexdigest(),
            }])


if __name__ == "__main__":
    unittest.main()
