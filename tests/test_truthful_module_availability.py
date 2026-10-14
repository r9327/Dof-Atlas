from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app import craft_preload
from app.modules.encyclopedia.constants import (
    ARCHMONSTERS_TAB, DUNGEONS_TAB, MONSTERS_TAB, WANTED_TAB,
)
from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage
from app.pages.craft_page import CraftPage
from app.pages.equipment_page import EquipmentPage
from app.ui.components import AtlasButton


class CraftPreloadAvailabilityTests(unittest.TestCase):
    def test_missing_and_corrupt_catalogue_cannot_be_prepared(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(craft_preload, "DATA_DIR", root):
                missing = craft_preload.build_compact_craft_preload()
                self.assertFalse(missing["_prepared"])
                self.assertIn("absent", missing["_skipped_reason"])
                db = root / "local" / "dofus_data.sqlite"
                db.parent.mkdir(parents=True)
                db.write_bytes(b"not a sqlite database")
                corrupt = craft_preload.build_compact_craft_preload()
                self.assertFalse(corrupt["_prepared"])
                self.assertTrue(corrupt["errors"])

    def test_worker_error_does_not_claim_prepared(self) -> None:
        import main

        with patch.object(main, "_run_preload_module_result", side_effect=RuntimeError("worker failed")):
            payload = main.build_craft_preload()
        self.assertFalse(payload["_prepared"])
        self.assertIn("worker failed", payload["errors"][0])

    def test_usable_sqlite_with_lazy_empty_item_list_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "local" / "dofus_data.sqlite"
            db.parent.mkdir(parents=True)
            with sqlite3.connect(db) as connection:
                connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
                connection.execute("INSERT INTO items (id) VALUES (1)")
            fake = Mock()
            fake.list_jobs.return_value = []
            fake.search_items.return_value = []
            with (
                patch.object(craft_preload, "DATA_DIR", root),
                patch("local_dofus_data.compatibility_adapter.LocalCompatibilityAdapter", return_value=fake),
            ):
                result = craft_preload.build_compact_craft_preload()
            self.assertTrue(result["_prepared"])
            self.assertEqual(result["items"], [])
            self.assertTrue(result["_lazy_items"])
            fake.close.assert_called_once()


class TruthfulQtAvailabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_four_bestiary_tabs_are_explicit_and_have_no_fake_search(self) -> None:
        statuses = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(EncyclopediaPage, "refresh_characters", lambda _self: None):
                page = EncyclopediaPage(
                    statuses.append,
                    quest_provider=Mock(),
                    initial_tab=DUNGEONS_TAB,
                    profile_path=root / "profile.json",
                    client_index_path=root / "client.json",
                )
            for label in (DUNGEONS_TAB, MONSTERS_TAB, ARCHMONSTERS_TAB, WANTED_TAB):
                index = page.tab_labels().index(label)
                page.tabs.setCurrentIndex(index)
                widget = page.ensure_tab_loaded(label)
                page.sync_search_visibility()
                self.assertEqual(widget.objectName(), "EncyclopediaUnavailableBestiary")
                self.assertIsNotNone(widget.findChild(
                    type(page.character_label), "EncyclopediaUnavailableMessage"
                ))
                self.assertFalse(page.search.isEnabled())
                self.assertFalse(page.search.isVisible())
            page.deleteLater()

    def test_equipment_browser_failure_reports_error_not_success(self) -> None:
        reports = []
        page = EquipmentPage(reports.append)
        with patch("app.pages.equipment_page.QDesktopServices.openUrl", return_value=False):
            self.assertFalse(page.open_huzounet())
        self.assertIn("impossible", reports[-1])
        self.assertNotIn("ouvert dans", reports[-1])
        page.deleteLater()

    def test_craft_missing_catalogue_shows_retry_then_accepts_valid_lazy_preload(self) -> None:
        reports = []
        requested = []
        page = CraftPage(
            reports.append,
            defer_runtime=True,
            retry_preload_callback=lambda: requested.append("retry"),
        )
        unavailable = {"items": [], "_lazy_items": True, "_prepared": False,
                       "_skipped_reason": "catalogue Craft local absent", "errors": []}
        self.assertFalse(page.hydrate_runtime(unavailable))
        page.show_runtime_error(unavailable["_skipped_reason"])
        self.assertFalse(page._runtime_ready)
        self.assertFalse(page.search.isEnabled())
        self.assertTrue(page.retry_preload_button.isVisible() or not page.isVisible())
        page.retry_preload_button.click()
        self.assertEqual(requested, ["retry"])
        self.assertFalse(page.retry_preload_button.isVisible())
        ready = {"items": [], "_lazy_items": True, "_prepared": True, "errors": [],
                 "jobs": [], "guides": {"guides": {}}, "selection": {}}
        self.assertTrue(page.hydrate_runtime(ready))
        self.assertTrue(page._runtime_ready)
        self.assertTrue(page.search.isEnabled())
        page.deleteLater()

    def test_craft_remove_button_has_name_tooltip_and_keyboard_focus(self) -> None:
        page = CraftPage(lambda _message: None, defer_runtime=True)
        page.selection[51] = {"item": {"name": "Potion de test"}, "quantity": 1}
        page.refresh_selection()
        row = page.selection_list.itemWidget(page.selection_list.item(0))
        self.assertIsNotNone(row)
        delete = row.findChild(AtlasButton, "CraftRemoveSelectionItem")
        self.assertIsNotNone(delete)
        self.assertIn("Potion de test", delete.toolTip())
        self.assertEqual(delete.accessibleName(), delete.toolTip())
        self.assertEqual(delete.focusPolicy(), Qt.StrongFocus)
        page.deleteLater()


if __name__ == "__main__":
    unittest.main()
