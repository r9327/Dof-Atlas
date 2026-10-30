"""No download or Windows API required for the persistent install selector."""
from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution import install_location as loc
from app.distribution.release_client import UpdateError


class RuntimeLocationTests(unittest.TestCase):
    def test_custom_runtime_root_persists_across_launcher_restarts(self):
        with tempfile.TemporaryDirectory() as temp:
            user = Path(temp) / "AppData" / "DofusAtlas"
            custom = Path(temp) / "Games" / "DofusAtlas" / "runtime"
            with (patch.object(loc, "APP_DATA", user),
                  patch.object(loc, "_SETTINGS", user / "installation.json"),
                  patch.object(loc, "DEFAULT_RUNTIME", user / "runtime")):
                self.assertEqual(loc.runtime_root(), user / "runtime")
                self.assertEqual(loc.set_runtime_root(custom), custom.resolve())
                self.assertEqual(loc.runtime_root(), custom.resolve())
                self.assertEqual(json.loads((user / "installation.json").read_text())["schema_version"], 1)
                self.assertFalse(custom.exists(), "Path selection must not extract or install files")

    def test_unicode_and_spaces_in_runtime_migration_preserve_state(self):
        # Test the path representation and migration contract without
        # installing a new release or relying on a local Windows account.
        with tempfile.TemporaryDirectory() as temp:
            user = Path(temp) / "Profil utilisateur" / "Atlas"
            source = user / "runtime"
            executable = source / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe"
            executable.parent.mkdir(parents=True)
            payload = b"MZ!valid"
            executable.write_bytes(payload)
            (source / "state.json").write_text(json.dumps({
                "active": "v1", "previous": None, "pending": False,
                "entrypoint": "AtlasApp/AtlasApp.exe",
                "entrypoint_size": len(payload),
                "entrypoint_sha256": hashlib.sha256(payload).hexdigest(),
                "source_sha": "a" * 40,
            }), encoding="utf-8")
            destination = Path(temp) / "Jeux été" / "Dofus Atlas" / "runtime"
            with (patch.object(loc, "APP_DATA", user),
                  patch.object(loc, "_SETTINGS", user / "installation.json"),
                  patch.object(loc, "DEFAULT_RUNTIME", source)):
                loc.set_runtime_root(source)
                selected = loc.relocate_runtime(destination)
                self.assertEqual(selected, destination.resolve())
                self.assertEqual(loc.runtime_root(), destination.resolve())
                self.assertEqual(
                    (destination / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe").read_bytes(),
                    payload,
                )
                self.assertEqual(
                    (destination / "state.json").read_bytes(),
                    (source / "state.json").read_bytes(),
                )
                self.assertTrue(executable.exists(), "A migration must retain rollback source")

    def test_invalid_path_cannot_replace_last_working_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            user = Path(temp) / "Data"
            with (patch.object(loc, "APP_DATA", user),
                  patch.object(loc, "_SETTINGS", user / "installation.json")):
                location = Path(temp) / "Good" / "runtime"
                loc.set_runtime_root(location)
                with self.assertRaises(UpdateError):
                    loc.set_runtime_root(Path("relative/folder"))
                self.assertEqual(loc.runtime_root(), location.resolve())
                (user / "installation.json").write_text('{"schema_version":99}')
                with self.assertRaises(UpdateError):
                    loc.runtime_root()

    def test_symlink_destination_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "target"
            target.mkdir()
            link = Path(temp) / "alias"
            try:
                link.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable on this host")
            with self.assertRaises(UpdateError):
                loc.set_runtime_root(link)


    def test_existing_installation_migrates_without_reinstalling(self):
        with tempfile.TemporaryDirectory() as temp:
            user = Path(temp) / "Data"
            source = user / "runtime"
            executable = source / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe"
            executable.parent.mkdir(parents=True)
            binary = b"MZ!"
            executable.write_bytes(binary)
            (source / "state.json").write_text(json.dumps({
                "active": "v1", "previous": None, "pending": False,
                "entrypoint": "AtlasApp/AtlasApp.exe",
                "entrypoint_size": len(binary),
                "entrypoint_sha256": hashlib.sha256(binary).hexdigest(),
                "source_sha": "a" * 40,
            }), encoding="utf-8")
            target = Path(temp) / "OtherDisk" / "DofusAtlas" / "runtime"
            with (patch.object(loc, "APP_DATA", user),
                  patch.object(loc, "_SETTINGS", user / "installation.json"),
                  patch.object(loc, "DEFAULT_RUNTIME", source)):
                self.assertEqual(loc.set_runtime_root(source), source.resolve())
                updates = []
                self.assertEqual(loc.relocate_runtime(target, lambda done, total: updates.append(done)), target.resolve())
                self.assertEqual(loc.runtime_root(), target.resolve())
                self.assertEqual((target / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe").read_bytes(), binary)
                self.assertTrue(executable.exists(), "Previous working version must remain available")
                self.assertTrue(updates)

    def test_interrupted_migration_preserves_previous_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            user = Path(temp) / "Data"
            source = user / "runtime"
            executable = source / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe"
            executable.parent.mkdir(parents=True)
            binary = b"MZ!previous"
            executable.write_bytes(binary)
            (source / "state.json").write_text(json.dumps({
                "active": "v1", "previous": None, "pending": False,
                "entrypoint": "AtlasApp/AtlasApp.exe",
                "entrypoint_size": len(binary),
                "entrypoint_sha256": hashlib.sha256(binary).hexdigest(),
                "source_sha": "a" * 40,
            }), encoding="utf-8")
            target = Path(temp) / "OtherDisk" / "DofusAtlas" / "runtime"
            with (patch.object(loc, "APP_DATA", user),
                  patch.object(loc, "_SETTINGS", user / "installation.json"),
                  patch.object(loc, "DEFAULT_RUNTIME", source)):
                loc.set_runtime_root(source)
                with patch("shutil.copytree", side_effect=OSError("Interrupted payload copy")):
                    with self.assertRaisesRegex(OSError, "Interrupted payload copy"):
                        loc.relocate_runtime(target)
                self.assertEqual(loc.runtime_root(), source.resolve())
                self.assertEqual(executable.read_bytes(), binary)
                self.assertFalse(target.exists())
                self.assertEqual(list(target.parent.glob(".atlas-move-*")), [])

    def test_corrupt_migration_staging_fails_without_switching_drives(self):
        import shutil
        with tempfile.TemporaryDirectory() as temp:
            user = Path(temp) / "Data"
            source = user / "runtime"
            executable = source / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe"
            executable.parent.mkdir(parents=True)
            binary = b"MZ!previous"
            executable.write_bytes(binary)
            (source / "state.json").write_text(json.dumps({
                "active": "v1", "previous": None, "pending": False,
                "entrypoint": "AtlasApp/AtlasApp.exe",
                "entrypoint_size": len(binary),
                "entrypoint_sha256": hashlib.sha256(binary).hexdigest(),
                "source_sha": "a" * 40,
            }), encoding="utf-8")
            target = Path(temp) / "OtherDisk" / "DofusAtlas" / "runtime"
            original_copytree = shutil.copytree

            def corrupt_staged_copy(src, dst, *args, **kwargs):
                result = original_copytree(src, dst, *args, **kwargs)
                if Path(src).samefile(source):
                    copied_executable = Path(dst) / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe"
                    copied_executable.write_bytes(b"MZ!CORRUPT!")
                    self.assertEqual(copied_executable.stat().st_size, len(binary))
                return result

            with (patch.object(loc, "APP_DATA", user),
                  patch.object(loc, "_SETTINGS", user / "installation.json"),
                  patch.object(loc, "DEFAULT_RUNTIME", source)):
                loc.set_runtime_root(source)
                with patch("shutil.copytree", side_effect=corrupt_staged_copy):
                    with self.assertRaises(UpdateError):
                        loc.relocate_runtime(target)
                self.assertEqual(loc.runtime_root(), source.resolve())
                self.assertEqual(executable.read_bytes(), binary)
                self.assertFalse(target.exists())
                self.assertEqual(list(target.parent.glob(".atlas-move-*")), [])

    def test_destination_collision_does_not_discard_current_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "current" / "runtime"
            target = Path(temp) / "other" / "runtime"
            target.mkdir(parents=True)
            user = Path(temp) / "Data"
            with (patch.object(loc, "APP_DATA", user),
                  patch.object(loc, "_SETTINGS", user / "installation.json"),
                  patch.object(loc, "DEFAULT_RUNTIME", source)):
                loc.set_runtime_root(source)
                with self.assertRaises(UpdateError):
                    loc.relocate_runtime(target)
                self.assertEqual(loc.runtime_root(), source.resolve())

    def test_saved_selection_distinguishes_existing_legacy_installs(self):
        with tempfile.TemporaryDirectory() as temp:
            user = Path(temp) / "Data"
            with (patch.object(loc, "APP_DATA", user),
                  patch.object(loc, "_SETTINGS", user / "installation.json")):
                self.assertFalse(loc.has_saved_location())
                loc.set_runtime_root(Path(temp) / "runtime")
                self.assertTrue(loc.has_saved_location())


if __name__ == "__main__":
    unittest.main()
