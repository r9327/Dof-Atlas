"""Windows-relative SQLite Guide route without Qt, app profiles or real LFS data."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import sqlite3

from app.modules.encyclopedia.services.guide_catalog_route_store import (
    write_indexed_route, restore_indexed_route, load_detail,
)


class RelativeGuideSQLiteTests(unittest.TestCase):
    def test_relative_build_validate_read_and_bad_signature(self):
        with tempfile.TemporaryDirectory(dir=".") as temp:
            store = Path(temp).relative_to(Path.cwd()) / "guide_routes" / "sylvestre.json"
            self.assertFalse(store.is_absolute())
            lines = [{"kind": "action", "text": "La quête continue"}]
            full = SimpleNamespace(
                guide_id="dofus_sylvestre",
                route={"id": "catalog_manual_dofus_sylvestre",
                       "steps": [{"manual_stage_id": "sylvestre:1"}]},
                cards=[{"manual_stage_id": "sylvestre:1",
                        "manual_lines": lines,
                        "manual_sections": {"now": lines}}],
                manual_audit_data={"card_count": 1},
                _common_quest_ids=(42,),
            )
            sig = "d" * 40
            created = write_indexed_route(full, store, sig)
            self.assertTrue(created.is_file())
            restored = SimpleNamespace(guide_id="dofus_sylvestre")
            self.assertFalse(restore_indexed_route(restored, store, "f" * 40))
            self.assertFalse(hasattr(restored, "cards"))
            self.assertTrue(restore_indexed_route(restored, store, sig))
            self.assertEqual(restored.cards[0]["manual_stage_id"], "sylvestre:1")
            self.assertEqual(load_detail(restored._catalog_detail_store_path, 0)["manual_lines"], lines)

    def test_stat_race_returns_false_without_crashing(self):
        fake = MagicMock()
        fake.is_file.return_value = True
        fake.stat.side_effect = OSError("file removed between existence and size check")
        with patch("app.modules.encyclopedia.services.guide_catalog_route_store.indexed_path",
                   return_value=fake):
            restored = SimpleNamespace(guide_id="dofus_sylvestre")
            self.assertFalse(restore_indexed_route(restored, Path("cache/route.json"), "d" * 40))
            self.assertFalse(hasattr(restored, "cards"))

    def test_trailing_compressed_bytes_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Path(temp) / "sylvestre.json"
            lines = [{"kind": "action", "text": "Maintenir intégrité"}]
            original = SimpleNamespace(
                guide_id="dofus_sylvestre",
                route={"id": "catalog_manual_dofus_sylvestre",
                       "steps": [{"manual_stage_id": "sylvestre:1"}]},
                cards=[{"manual_stage_id": "sylvestre:1",
                        "manual_lines": lines, "manual_sections": {"now": lines}}],
                manual_audit_data={"card_count": 1}, _common_quest_ids=(42,),
            )
            sqlite_path = write_indexed_route(original, store, "d" * 40)
            with sqlite3.connect(sqlite_path) as connection:
                payload = connection.execute("SELECT data FROM details WHERE idx=0").fetchone()[0]
                connection.execute("UPDATE details SET data=? WHERE idx=0",
                                   (payload + b"trailing-corruption",))
            with self.assertRaises(ValueError):
                load_detail(sqlite_path, 0)



if __name__ == "__main__":
    unittest.main()
