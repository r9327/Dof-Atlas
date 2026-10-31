"""Portable Quest index first-boot parity, corruption and safe fallback."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import quest_catalog_details as details
from app import quest_index_prebuilt as seed


class PortableQuestIndexTests(unittest.TestCase):
    def _create_source(self, path: Path, count: int = 1976) -> None:
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE quests (id INTEGER PRIMARY KEY, name TEXT, detail TEXT)")
            db.execute("INSERT INTO metadata VALUES ('ready', '1')")
            db.executemany(
                "INSERT INTO quests VALUES (?, ?, NULL)",
                ((i, f"Quête {i}") for i in range(1, count + 1)),
            )

    def test_roundtrip_restores_exact_summary_without_detail_source_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.sqlite3"
            self._create_source(source)
            bundle = root / "bundle"
            dest = root / "runtime" / "actual-local-signature.sqlite3"
            with patch.object(seed, "_source_sizes", return_value={"quests.json": 1234}):
                result = seed.publish_quest_index(source, bundle, source_sha="a" * 40)
                self.assertEqual(result["quest_count"], 1976)
                self.assertEqual(seed.verify_quest_index(root=bundle), 1976)
                self.assertTrue(seed.restore_quest_index(dest, root=bundle))
                self.assertFalse(seed.restore_quest_index(dest, root=bundle))
                self.assertEqual(dest.read_bytes(), (bundle / seed.FILENAME).read_bytes())
                self.assertEqual(seed._check_index(dest), 1976)
                self.assertNotIn("character:", (bundle / seed.MANIFEST).read_text())
                self.assertNotIn("quest_progress", (bundle / seed.MANIFEST).read_text())

                # Actual deferred Quest cache loader must not parse Doduda
                # because the signed summary is already present.
                another = root / "runtime" / "new-generation.sqlite3"
                with (
                    patch.object(details, "_cache_identity", return_value=((), another)),
                    patch.object(details, "_source_index",
                                 side_effect=AssertionError("Source parsing at first launch")),
                    patch.dict("os.environ", {"DOFUS_ATLAS_PREBUILT_QUEST_INDEX_DIR": str(bundle)}),
                ):
                    self.assertEqual(details.ensure_lazy_catalog_cache(
                        details.qc.RAW_QUEST_DATA_DIR, cache_root=root / "runtime",
                    ), 1976)

    def test_relative_release_paths_work_with_read_only_sqlite_on_windows(self):
        # Regression: Path.as_uri() rejects a relative temp SQLite file.
        # The release packager calls build_quest_index with a relative output.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = Path.cwd()
            try:
                os.chdir(root)
                source = Path("source.sqlite3")
                self._create_source(source)
                with patch.object(seed, "_source_sizes", return_value={"quests.json": 1234}):
                    payload = seed.publish_quest_index(
                        source, Path("data/bootstrap"), source_sha="d" * 40,
                    )
                    self.assertEqual(payload["quest_count"], 1976)
                    self.assertEqual(
                        seed.verify_quest_index(root=Path("data/bootstrap")), 1976,
                    )
                    self.assertEqual(
                        seed._check_index(Path("data/bootstrap") / seed.FILENAME), 1976,
                    )
            finally:
                os.chdir(previous)

    def test_tampering_missing_sources_and_rich_cache_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.sqlite3"
            self._create_source(source)
            with patch.object(seed, "_source_sizes", return_value={"quests.json": 12}):
                seed.publish_quest_index(source, root / "bundle", source_sha="b" * 40)
                path = root / "bundle" / seed.FILENAME
                original = path.read_bytes()
                path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
                self.assertEqual(seed.verify_quest_index(root=root / "bundle"), 0)
                self.assertFalse(seed.restore_quest_index(root / "out.sqlite3", root=root / "bundle"))
                path.write_bytes(original)
            with patch.object(seed, "_source_sizes", return_value={"quests.json": 999}):
                self.assertEqual(seed.verify_quest_index(root=root / "bundle"), 0)

            with closing(sqlite3.connect(source)) as db, db:
                db.execute("UPDATE quests SET detail='{}' WHERE id=1")
            with patch.object(seed, "_source_sizes", return_value={"quests.json": 12}):
                with self.assertRaisesRegex(ValueError, "rich details"):
                    seed.publish_quest_index(source, root / "other", source_sha="c" * 40)

    def test_invalid_sha_and_foreign_quest_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_source(root / "source.sqlite3")
            with self.assertRaises(ValueError):
                seed.publish_quest_index(root / "source.sqlite3", root / "bundle", source_sha="short")
            self.assertFalse(seed.restore_quest_index(
                root / "out.sqlite3", root=root / "bundle", data_dir=root / "custom",
            ))


if __name__ == "__main__":
    unittest.main()
