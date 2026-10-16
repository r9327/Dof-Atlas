from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from app.pages import craft_page
from local_dofus_data.data_store import DataStore
from local_dofus_data.repositories import ItemRepository
from local_dofus_data import compatibility_adapter
from app import local_data_cache
from tests.helpers import make_config


class CraftCategorySearchTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        config = make_config(root)
        self.store = DataStore(config=config)
        self.addCleanup(self.store.close)
        self.items = ItemRepository(self.store, config)
        for index in range(182):
            kind = "Coiffe" if index < 180 else "Ressource" if index == 180 else "Trophée"
            name = f"Commun {index:03}"
            self.store.execute(
                "INSERT INTO items (ankama_id,name_fr,type,level,updated_at) VALUES (?,?,?,?,?)",
                (index + 1, name, kind, 1 if index < 180 else 200, "fixture"),
            )
            self.store.execute(
                "INSERT INTO recipes (result_ankama_id,result_name_fr,updated_at) VALUES (?,?,?)",
                (index + 1, name, "fixture"),
            )
        self.store.connect().commit()

    def test_category_is_applied_before_the_160_candidate_limit(self):
        generic = self.items.search_craft_legacy("Commun", limit=160)
        self.assertEqual(len(generic), 160)
        self.assertFalse(any(row["type"] == "Ressource" for row in generic))
        self.assertEqual([row["ankama_id"] for row in self.items.search_craft_legacy(
            "Commun", limit=160, category="resource")], [181])
        self.assertEqual([row["ankama_id"] for row in self.items.search_craft_legacy(
            "Commun", limit=160, category="trophy_prysma")], [182])
        self.assertEqual(len(self.items.search_craft_legacy("Commun", limit=3, category="equipment")), 3)
        self.assertEqual(self.items.search_craft_legacy("Commun", limit=0, category="resource"), [])

    def test_real_craft_page_forwards_its_selected_category_to_sqlite_search(self):
        page = craft_page.CraftPage(lambda _status: None, defer_runtime=True)
        try:
            page._runtime_ready = True
            page.preload = {"_lazy_items": True}
            page.category = "resource"
            page.search.blockSignals(True)
            page.search.setText("Commun")
            page.search.blockSignals(False)
            with patch.object(craft_page.local_data_cache, "search_craft_items",
                              side_effect=self.items.search_craft_legacy) as search:
                page.refresh_results()
                page.result_batch_timer.stop()
                self.assertEqual([row["ankama_id"] for row in page._pending_result_items], [181])
                search.assert_called_once_with("Commun", limit=160, category="resource")
        finally:
            page.close()
            page.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            self.app.processEvents()

    def test_filtered_search_streams_instead_of_materializing_all_candidate_rows(self):
        with patch.object(self.store, "query_all", side_effect=AssertionError("bulk rows forbidden")):
            rows = self.items.search_craft_legacy("Commun", limit=1, category="trophy_prysma")
        self.assertEqual([row["ankama_id"] for row in rows], [182])

    def test_category_crosses_the_legacy_facades_and_canonical_adapter(self):
        adapter = object.__new__(compatibility_adapter.LocalCompatibilityAdapter)
        adapter.items = self.items
        with patch.object(compatibility_adapter, "get_adapter", return_value=adapter):
            rows = local_data_cache.search_craft_items("Commun", limit=160, category="resource")
        self.assertEqual([row["ankama_id"] for row in rows], [181])
        self.assertEqual(rows[0]["_craft_category"], "resource")
