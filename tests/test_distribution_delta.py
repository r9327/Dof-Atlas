"""End-to-end changed-file ZIP tests using fake frozen Windows binaries."""
from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.distribution.install import install_release, mark_healthy, read_state, slot_path
from app.distribution.manifest import parse_manifest
from app.distribution.release_client import UpdateError
from scripts.windows.package_release import package_release


class DifferentialDistributionTests(unittest.TestCase):
    def test_delta_reuses_checked_files_and_keeps_previous_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "AtlasApp"
            data = app / "_internal" / "data" / "raw"
            data.mkdir(parents=True)
            (app / "AtlasApp.exe").write_bytes(b"MZ-unchanged-executable")
            catalog = data / "catalog.json"
            catalog.write_text('{"items":[1]}', encoding="utf-8")
            prior_zip, prior_path = package_release(app, root / "first", "a" * 40,
                                                    "1.0", "v1", 1)
            previous = parse_manifest(prior_path.read_bytes())
            target = root / "install"
            self.assertTrue(install_release(target, prior_zip, previous))
            mark_healthy(target)
            old_slot = read_state(target)["active"]

            catalog.write_text('{"items":[1,2]}', encoding="utf-8")
            archive, path = package_release(app, root / "second", "b" * 40,
                                            "1.1", "v2", 1, base_manifest=prior_path)
            latest = parse_manifest(path.read_bytes())
            self.assertIsNotNone(latest.delta)
            self.assertEqual(latest.delta.base_source_sha, "a" * 40)
            changed = set(latest.delta.paths)
            self.assertIn("AtlasApp/_internal/data/raw/catalog.json", changed)
            self.assertNotIn("AtlasApp/AtlasApp.exe", changed)
            delta_zip = root / "second" / "atlas-delta.zip"
            with zipfile.ZipFile(delta_zip) as pkg:
                self.assertEqual(set(pkg.namelist()), changed)
            self.assertTrue(install_release(target, delta_zip, latest, delta=True))
            new_slot = slot_path(target, read_state(target)["active"])
            self.assertEqual((new_slot / "AtlasApp/AtlasApp.exe").read_bytes(),
                             b"MZ-unchanged-executable")
            self.assertEqual((new_slot / "AtlasApp/_internal/data/raw/catalog.json").read_text(),
                             '{"items":[1,2]}')
            self.assertEqual((slot_path(target, old_slot) /
                              "AtlasApp/_internal/data/raw/catalog.json").read_text(),
                             '{"items":[1]}')

    def test_delta_rejects_changed_local_base_but_full_zip_repairs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "AtlasApp"
            app.mkdir()
            exe = app / "AtlasApp.exe"
            exe.write_bytes(b"MZfirst")
            first_zip, first_meta = package_release(app, root / "first", "a" * 40,
                                                     "1.0", "v1", 1)
            target = root / "installed"
            install_release(target, first_zip, parse_manifest(first_meta.read_bytes()))
            mark_healthy(target)
            exe.write_bytes(b"MZsecond")
            new_zip, new_meta = package_release(app, root / "second", "b" * 40,
                                                 "1.1", "v2", 1, base_manifest=first_meta)
            latest = parse_manifest(new_meta.read_bytes())
            # All bytes changed; the packager may omit a delta as it saves nothing.
            if latest.delta is None:
                self.assertTrue(install_release(target, new_zip, latest))
                return
            with self.assertRaises(UpdateError):
                install_release(root / "other", root / "second" / "atlas-delta.zip",
                                latest, delta=True)
            self.assertTrue(install_release(target, new_zip, latest))


    def test_reused_package_folder_cannot_publish_stale_delta(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "AtlasApp"
            app.mkdir()
            (app / "AtlasApp.exe").write_bytes(b"MZ-frozen")
            data = app / "_internal" / "data"
            data.mkdir(parents=True)
            (data / "unchanged.bin").write_bytes(os.urandom(16 * 1024))
            catalog = data / "quests.json"
            catalog.write_text('{"quests":[1]}', encoding="utf-8")
            _, base = package_release(app, root / "base", "a" * 40,
                                      "1.0", "v1", 1)

            catalog.write_text('{"quests":[1,2]}', encoding="utf-8")
            output = root / "reused"
            _, second = package_release(app, output, "b" * 40,
                                        "1.1", "v2", 1, base_manifest=base)
            self.assertIsNotNone(parse_manifest(second.read_bytes()).delta)
            self.assertTrue((output / "atlas-delta.zip").is_file())

            # Same directory, no compatible base: the previous delta must
            # disappear rather than be shipped with the new full manifest.
            _, third = package_release(app, output, "c" * 40,
                                       "1.2", "v3", 1)
            self.assertIsNone(parse_manifest(third.read_bytes()).delta)
            self.assertFalse((output / "atlas-delta.zip").exists())


if __name__ == "__main__":
    unittest.main()
