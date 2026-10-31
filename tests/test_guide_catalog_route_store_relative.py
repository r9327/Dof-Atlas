"""Windows-relative SQLite Guide route without Qt, app profiles or real LFS data."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_catalog_route_store import (
    write_indexed_route, restore_indexed_route, load_detail,
)


class RelativeGuideSQLiteTests(unittest.TestCase):
    def test_relative_build_validate_read_and_bad_signature(self):
        with tempfile.TemporaryDirectory(dir=".") as temp:
            store = Path(temp) / "guide_routes" / "sylvestre.json"
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


if __name__ == "__main__":
    unittest.main()
