"""Protect durable Atlas user data across application upgrades."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.distribution.user_data import prepare_user_data


class UserDataTests(unittest.TestCase):
    def test_seed_once_and_preserve_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "bundle" / "AtlasApp.exe"
            executable.parent.mkdir()
            executable.write_bytes(b"MZ")
            from_bundle = executable.parent / "_internal" / "data" / "local"
            from_bundle.mkdir(parents=True)
            (from_bundle / "quest_progress.json").write_text('{"quest":1}', encoding="utf-8")
            user = root / "user"
            prepare_user_data(executable, user)
            dest = user / "data" / "local" / "quest_progress.json"
            self.assertEqual(dest.read_text(encoding="utf-8"), '{"quest":1}')
            dest.write_text('{"quest":99}', encoding="utf-8")
            prepare_user_data(executable, user)
            self.assertEqual(dest.read_text(encoding="utf-8"), '{"quest":99}')

    def test_import_legacy_source_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_clone = root / "legacy"
            (old_clone / "data" / "local").mkdir(parents=True)
            (old_clone / "DOFUS.bat").write_text("@echo off")
            (old_clone / "data" / "local" / "quest_progress.json").write_text('{"quests":42}')
            bundle = root / "versions" / "v1" / "AtlasApp"
            bundle.mkdir(parents=True)
            exe = bundle / "AtlasApp.exe"
            exe.write_bytes(b"MZ")
            user = root / "user"
            prepare_user_data(exe, user, legacy_root=old_clone)
            self.assertEqual(
                (user / "data" / "local" / "quest_progress.json").read_text(),
                '{"quests":42}')
            (old_clone / "data" / "local" / "quest_progress.json").write_text('{"quests":0}')
            prepare_user_data(exe, user, legacy_root=old_clone)
            self.assertEqual(
                (user / "data" / "local" / "quest_progress.json").read_text(),
                '{"quests":42}')

    def test_no_symlink_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / "bundle" / "AtlasApp.exe"
            exe.parent.mkdir()
            exe.write_bytes(b"MZ")
            source = exe.parent / "_internal" / "data" / "local"
            source.mkdir(parents=True)
            other = root / "external.json"
            other.write_text('{"bad":true}')
            try:
                (source / "quest_progress.json").symlink_to(other)
            except (NotImplementedError, OSError):
                self.skipTest("Symlinks not available")
            user = root / "user"
            prepare_user_data(exe, user)
            self.assertFalse((user / "data" / "local" / "quest_progress.json").exists())


if __name__ == "__main__":
    unittest.main()
