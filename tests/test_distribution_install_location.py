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

    def test_runtime_cannot_overlap_profile_logs_or_personal_theme(self):
        with tempfile.TemporaryDirectory() as temp:
            app_data = Path(temp) / "Profile" / "AppData" / "Atlas"
            default = app_data / "runtime"
            external = Path(temp) / "Games" / "Atlas" / "runtime"
            with (patch.object(loc, "APP_DATA", app_data),
                  patch.object(loc, "_SETTINGS", app_data / "installation.json"),
                  patch.object(loc, "DEFAULT_RUNTIME", default)):
                # The existing installation and a separate disk remain valid.
                self.assertEqual(loc.set_runtime_root(default), default.resolve())
                self.assertEqual(loc.set_runtime_root(external), external.resolve())
                saved = (app_data / "installation.json").read_bytes()
                forbidden = (
                    app_data, app_data.parent, app_data.parent.parent,
                    app_data / "user", app_data / "user" / "characters",
                    app_data / "logs", app_data / "logs" / "archive",
                    app_data / "themes", app_data / "themes" / "dofus_unity",
                    default / "nested",
                )
                for candidate in forbidden:
                    with self.subTest(candidate=str(candidate)):
                        with self.assertRaisesRegex(UpdateError, "donnees personnelles"):
                            loc.set_runtime_root(candidate)
                        self.assertEqual((app_data / "installation.json").read_bytes(), saved)
                        self.assertEqual(loc.runtime_root(), external.resolve())
                # A migration attempt must likewise fail before touching user data.
                with self.assertRaisesRegex(UpdateError, "donnees personnelles"):
                    loc.relocate_runtime(app_data / "user" / "runtime")
                self.assertFalse((app_data / "user").exists())
                self.assertEqual(loc.runtime_root(), external.resolve())

    def test_unusable_or_readonly_target_does_not_replace_saved_location(self):
        with tempfile.TemporaryDirectory() as temp:
            app_data = Path(temp) / "Profile" / "AppData" / "Atlas"
            working = Path(temp) / "Games" / "runtime"
            blocked = Path(temp) / "ExternalDisk" / "runtime"
            file_parent = Path(temp) / "NotAFolder"
            file_parent.write_bytes(b"existing")
            with (patch.object(loc, "APP_DATA", app_data),
                  patch.object(loc, "_SETTINGS", app_data / "installation.json"),
                  patch.object(loc, "DEFAULT_RUNTIME", app_data / "runtime")):
                self.assertEqual(loc.set_runtime_root(working), working.resolve())
                saved = (app_data / "installation.json").read_bytes()
                with self.assertRaisesRegex(UpdateError, "inaccessible"):
                    loc.set_runtime_root(file_parent / "runtime")
                with patch.object(loc.tempfile, "TemporaryFile",
                                  side_effect=PermissionError("read-only disk")):
                    with self.assertRaisesRegex(UpdateError, "ecriture"):
                        loc.set_runtime_root(blocked)
                self.assertEqual((app_data / "installation.json").read_bytes(), saved)
                self.assertEqual(loc.runtime_root(), working.resolve())
                self.assertFalse(blocked.exists(),
                                 "A preflight must not create the candidate runtime")

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
            # Copy both active and rollback releases, not the disposable caches.
            rollback = source / "versions" / "v0" / "AtlasApp" / "old.dat"
            rollback.parent.mkdir(parents=True)
            rollback.write_bytes(b"previous release")
            cache = source / "downloads" / ("a" * 20 + ".zip")
            cache.parent.mkdir()
            cache.write_bytes(b"re-downloadable archive" * 1024)
            quarantined = source / "quarantine" / "damaged" / "old.bin"
            quarantined.parent.mkdir(parents=True)
            quarantined.write_bytes(b"damaged-slot" * 1024)
            health = source / ".health" / "old.ready"
            health.parent.mkdir()
            health.write_text("stale PID", encoding="ascii")
            (source / ".launcher.lock").write_bytes(b"0")
            (source / "state.json").write_text(json.dumps({
                "active": "v1", "previous": "v0", "pending": False,
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
                self.assertEqual(loc.relocate_runtime(
                    target, lambda done, total: updates.append((done, total))
                ), target.resolve())
                self.assertEqual(loc.runtime_root(), target.resolve())
                self.assertEqual((target / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe").read_bytes(), binary)
                self.assertTrue(executable.exists(), "Previous working version must remain available")
                self.assertEqual((target / "versions" / "v0" / "AtlasApp" / "old.dat").read_bytes(),
                                 b"previous release")
                self.assertEqual((target / "state.json").read_bytes(),
                                 (source / "state.json").read_bytes())
                for skipped in ("downloads", "quarantine", ".health", ".launcher.lock"):
                    self.assertFalse((target / skipped).exists(), skipped)
                    self.assertTrue((source / skipped).exists(), "Old runtime is retained")
                self.assertTrue(updates)
                # Cached ZIPs and quarantined files do not inflate the
                # disk preflight estimate or progress denominator.
                expected = (len(binary) + len(b"previous release")
                            + (source / "state.json").stat().st_size)
                self.assertEqual(updates[-1], (expected, expected))

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

    def test_same_size_corruption_in_non_executable_aborts_migration(self):
        import shutil
        with tempfile.TemporaryDirectory() as temp:
            user = Path(temp) / "Data"
            source = user / "runtime"
            executable = source / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe"
            executable.parent.mkdir(parents=True)
            binary = b"MZ!valid"
            executable.write_bytes(binary)
            (source / "versions" / "v1" / "assets.dat").write_bytes(b"safe-assets")
            (source / "state.json").write_text(json.dumps({
                "active": "v1", "previous": None, "pending": False,
                "entrypoint": "AtlasApp/AtlasApp.exe",
                "entrypoint_size": len(binary),
                "entrypoint_sha256": hashlib.sha256(binary).hexdigest(),
                "source_sha": "a" * 40,
            }), encoding="utf-8")
            target = Path(temp) / "NewDisk" / "runtime"
            original_copy2 = shutil.copy2

            def corrupt_asset(src, dst, *args, **kwargs):
                result = original_copy2(src, dst, *args, **kwargs)
                if Path(src).name == "assets.dat":
                    Path(dst).write_bytes(b"evil-assets")
                return result

            with (patch.object(loc, "APP_DATA", user),
                  patch.object(loc, "_SETTINGS", user / "installation.json"),
                  patch.object(loc, "DEFAULT_RUNTIME", source)):
                loc.set_runtime_root(source)
                with patch("shutil.copy2", side_effect=corrupt_asset):
                    with self.assertRaisesRegex(UpdateError, "corrompue"):
                        loc.relocate_runtime(target)
                self.assertEqual(loc.runtime_root(), source.resolve())
                self.assertEqual((source / "versions" / "v1" / "assets.dat").read_bytes(), b"safe-assets")
                self.assertFalse(target.exists())
                self.assertEqual(list(target.parent.glob(".atlas-move-*")), [])

    def test_link_inserted_between_scan_and_copy_is_rejected(self):
        import shutil

        for linked_directory in (False, True):
            with self.subTest(linked_directory=linked_directory):
                with tempfile.TemporaryDirectory() as temp:
                    user = Path(temp) / "Data"
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
                    late = source / ("late-folder" if linked_directory else "late-file")
                    referent = executable.parent if linked_directory else executable
                    try:
                        late.symlink_to(referent, target_is_directory=linked_directory)
                    except (OSError, NotImplementedError):
                        self.skipTest("File/directory symlinks unavailable on host")
                    late.unlink()  # First preflight sees no links.
                    original = shutil.copytree
                    called = []

                    def inject_after_scan(src, dst, *args, **kwargs):
                        if Path(src) == source:
                            late.symlink_to(referent, target_is_directory=linked_directory)
                            called.append(True)
                        return original(src, dst, *args, **kwargs)

                    target = Path(temp) / "OtherDisk" / "runtime"
                    with (patch.object(loc, "APP_DATA", user),
                          patch.object(loc, "_SETTINGS", user / "installation.json"),
                          patch.object(loc, "DEFAULT_RUNTIME", source)):
                        loc.set_runtime_root(source)
                        with patch("shutil.copytree", side_effect=inject_after_scan):
                            with self.assertRaisesRegex(UpdateError, "liens"):
                                loc.relocate_runtime(target)
                        self.assertTrue(called)
                        self.assertEqual(loc.runtime_root(), source.resolve())
                        self.assertEqual(executable.read_bytes(), payload)
                        self.assertFalse(target.exists())
                        self.assertEqual(list(target.parent.glob(".atlas-move-*")), [])

    def test_link_appearing_after_copytree_preflight_cannot_be_activated(self):
        import shutil

        with tempfile.TemporaryDirectory() as temp:
            user = Path(temp) / "Data"
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
            # The source is valid throughout both scans. Emulate a new link
            # discovered only in the private staging directory after copy.
            original = shutil.copytree

            def inject_staged_link(src, dst, *args, **kwargs):
                result = original(src, dst, *args, **kwargs)
                link = Path(dst) / "unsafe-late-link"
                try:
                    link.symlink_to(Path(dst) / "state.json")
                except (OSError, NotImplementedError):
                    self.skipTest("Symlinks unavailable on host")
                return result

            target = Path(temp) / "OtherDisk" / "runtime"
            with (patch.object(loc, "APP_DATA", user),
                  patch.object(loc, "_SETTINGS", user / "installation.json"),
                  patch.object(loc, "DEFAULT_RUNTIME", source)):
                loc.set_runtime_root(source)
                with patch("shutil.copytree", side_effect=inject_staged_link):
                    with self.assertRaisesRegex(UpdateError, "lien non autorise"):
                        loc.relocate_runtime(target)
                self.assertEqual(loc.runtime_root(), source.resolve())
                self.assertEqual(executable.read_bytes(), payload)
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
