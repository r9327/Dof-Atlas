"""Ensure the published Windows ZIP and manifest are accepted by the installer."""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.distribution.install import install_release
from app.distribution.manifest import parse_manifest
from scripts.windows.package_release import package_release


class PackagingTests(unittest.TestCase):
    def test_release_round_trip_and_private_file_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "dist" / "AtlasApp"
            (bundle / "_internal" / "data" / "local").mkdir(parents=True)
            (bundle / "_internal" / "data" / "images").mkdir(parents=True)
            (bundle / "AtlasApp.exe").write_bytes(b"MZfake-test-executable")
            (bundle / "_internal" / "data" / "local" / "quest_progress.json").write_text('{"secret":1}')
            (bundle / "_internal" / "data" / "images" / "logo.png").write_bytes(b"PNGfake")
            archive, manifest_path = package_release(bundle, root / "release", "e" * 40,
                                                       "0.1.0-eeee", "2026.10", 1)
            manifest = parse_manifest(manifest_path.read_bytes())
            self.assertEqual(manifest.source_sha, "e" * 40)
            self.assertEqual(len(manifest.files), 2)
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(set(z.namelist()), {
                    "AtlasApp/AtlasApp.exe",
                    "AtlasApp/_internal/data/images/logo.png",
                })
            location = root / "installed"
            self.assertTrue(install_release(location, archive, manifest))
            self.assertTrue((location / "versions").is_dir())

    def test_reject_git_lfs_pointer_in_distribution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "AtlasApp"
            bundle.mkdir()
            (bundle / "AtlasApp.exe").write_bytes(b"MZ")
            (bundle / "image.png").write_bytes(
                b"version https://git-lfs.github.com/spec/v1\n" + b"oid sha256:test\n")
            with self.assertRaises(ValueError):
                package_release(bundle, root / "out", "a" * 40, "1.0.0", "2026.10", 1)


if __name__ == "__main__":
    unittest.main()
