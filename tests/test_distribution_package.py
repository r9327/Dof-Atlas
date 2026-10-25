"""Build-time release archive integration, with a minimal simulated EXE."""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.distribution.install import install_release, active_executable
from app.distribution.manifest import parse_manifest
from scripts.windows.package_release import package_release


class PackagingTests(unittest.TestCase):
    def test_archive_verifies_and_installs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "build" / "AtlasApp"
            bundle.mkdir(parents=True)
            (bundle / "AtlasApp.exe").write_bytes(b"MZ-packaging-test")
            qt = bundle / "_internal" / "PySide6" / "QtWebEngineProcess.exe"
            qt.parent.mkdir(parents=True)
            qt.write_bytes(b"Qt helper")
            zaaps = bundle / "_internal" / "data" / "local" / "zaaps.json"
            zaaps.parent.mkdir(parents=True, exist_ok=True)
            zaaps.write_text('{"zaaps":[]}', encoding="utf-8")
            private = bundle / "_internal" / "data" / "local" / "quest_progress.json"
            private.parent.mkdir(parents=True, exist_ok=True)
            private.write_text('{"private":true}')
            extracted = bundle / "_internal" / "app" / "assets" / "themes" / "dofus_unity" / "sprites" / "btn_green_normal.png"
            extracted.parent.mkdir(parents=True, exist_ok=True)
            extracted.write_bytes(b"unlicensed-test-fixture")
            output = root / "release"
            archive, manifest_path = package_release(bundle, output, "a" * 40,
                                                      "1.0.0", "2026.10", 1)
            manifest = parse_manifest(manifest_path.read_bytes())
            entries = {f.path for f in manifest.files}
            self.assertIn("AtlasApp/AtlasApp.exe", entries)
            self.assertIn("AtlasApp/_internal/PySide6/QtWebEngineProcess.exe", entries)
            self.assertNotIn("AtlasApp/_internal/data/local/quest_progress.json", entries)
            self.assertIn("AtlasApp/_internal/data/local/zaaps.json", entries)
            self.assertNotIn(
                "AtlasApp/_internal/app/assets/themes/dofus_unity/sprites/btn_green_normal.png",
                entries,
            )
            with zipfile.ZipFile(archive) as package:
                self.assertEqual(set(package.namelist()), entries)
            target = root / "installed"
            self.assertTrue(install_release(target, archive, manifest))
            self.assertEqual(active_executable(target).read_bytes(), b"MZ-packaging-test")

    def test_reject_unresolved_lfs_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "AtlasApp"
            bundle.mkdir()
            (bundle / "AtlasApp.exe").write_bytes(b"MZ")
            (bundle / "bad.png").write_bytes(
                b"version https://git-lfs.github.com/spec/v1\n" + b"oid sha256:x")
            with self.assertRaises(ValueError):
                package_release(bundle, root / "out", "a" * 40, "1.0.0", "2026.10", 1)


if __name__ == "__main__":
    unittest.main()
