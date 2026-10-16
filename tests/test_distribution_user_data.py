"""Protect durable Atlas user data across application upgrades."""
from __future__ import annotations

from contextlib import closing
import sqlite3
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

    def test_world_scan_migrates_from_previous_version_with_wal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_internal = root / "runtime" / "versions" / "old" / "AtlasApp" / "_internal"
            db_path = old_internal / "data" / "dofus_atlas_world.db"
            db_path.parent.mkdir(parents=True)
            new_exe = root / "runtime" / "versions" / "new" / "AtlasApp" / "AtlasApp.exe"
            new_exe.parent.mkdir(parents=True)
            new_exe.write_bytes(b"MZ")
            user = root / "user"
            with closing(sqlite3.connect(db_path)) as old:
                old.execute("PRAGMA journal_mode=WAL")
                old.executescript(
                    "CREATE TABLE map_views (view_key TEXT PRIMARY KEY);"
                    "CREATE TABLE maps (map_id TEXT, status TEXT);"
                )
                old.execute("INSERT INTO map_views VALUES ('incarnam')")
                old.execute("INSERT INTO maps VALUES ('123','verified')")
                old.commit()
                # Database keeps a live WAL while the new version takes a snapshot.
                prepare_user_data(new_exe, user, previous_install_root=old_internal)
            saved = user / "data" / "dofus_atlas_world.db"
            self.assertTrue(saved.is_file())
            with closing(sqlite3.connect(saved)) as migrated:
                self.assertEqual(migrated.execute(
                    "SELECT status FROM maps WHERE map_id='123'"
                ).fetchone()[0], "verified")
                migrated.execute("UPDATE maps SET status='current' WHERE map_id='123'")
                migrated.commit()
            prepare_user_data(new_exe, user, previous_install_root=old_internal)
            with closing(sqlite3.connect(saved)) as migrated:
                self.assertEqual(migrated.execute(
                    "SELECT status FROM maps WHERE map_id='123'"
                ).fetchone()[0], "current")

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
