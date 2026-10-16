"""No-recompile JSON distribution integration tests."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.distribution.install import install_release, mark_healthy, read_state, slot_path
from app.distribution.manifest import parse_manifest
from scripts.windows.package_release import package_release
from scripts.windows.repackage_data_only import repackage_data_only


class DataOnlyPackagingTests(unittest.TestCase):
    def test_changed_json_preserves_binary_and_user_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "frozen"
            data = original / "_internal" / "data" / "raw"
            data.mkdir(parents=True)
            (original / "AtlasApp.exe").write_bytes(b"MZ-existing-binary")
            (data / "metiers.json").write_text('{"a":1}', encoding="utf-8")
            archive, manifest_path = package_release(original, root / "prior", "a" * 40,
                                                     "1.1", "data-one", 1)
            source = root / "source" / "data" / "raw"
            source.mkdir(parents=True)
            (source / "metiers.json").write_text('{"a":2}', encoding="utf-8")
            new_archive, new_manifest = repackage_data_only(
                archive, manifest_path, root / "source", ["data/raw/metiers.json"],
                root / "next", "b" * 40, "data-two",
            )
            old = parse_manifest(manifest_path.read_bytes())
            updated = parse_manifest(new_manifest.read_bytes())
            self.assertEqual(updated.app_version, old.app_version)
            self.assertEqual(updated.schema_version, old.schema_version)
            self.assertIsNotNone(updated.delta)
            target = root / "installed"
            profile = root / "user" / "client_profiles.json"
            profile.parent.mkdir()
            profile.write_text('{"keep":"yes"}')
            install_release(target, archive, old)
            mark_healthy(target)
            self.assertTrue(install_release(target, root / "next" / "atlas-delta.zip",
                                            updated, delta=True))
            slot = slot_path(target, read_state(target)["active"])
            self.assertEqual((slot / "AtlasApp/AtlasApp.exe").read_bytes(),
                             b"MZ-existing-binary")
            self.assertEqual(json.loads((slot / "AtlasApp/_internal/data/raw/metiers.json").read_text()),
                             {"a": 2})
            self.assertEqual(profile.read_text(), '{"keep":"yes"}')

    def test_non_data_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "frozen"
            original.mkdir()
            (original / "AtlasApp.exe").write_bytes(b"MZ")
            archive, manifest = package_release(original, root / "old", "a" * 40,
                                                 "1.0", "1", 1)
            for modified in ("app/core.py", "data/local/quest_progress.json",
                             "data/raw/data.py", "../secrets.json", "data/raw/../private.json"):
                with self.subTest(path=modified), self.assertRaises(ValueError):
                    repackage_data_only(archive, manifest, root, [modified],
                                        root / "out", "b" * 40, "2")


if __name__ == "__main__":
    unittest.main()
