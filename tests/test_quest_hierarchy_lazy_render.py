from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.providers import QuestProvider
from app.pages.quests_page import QuestsPage
from app.quest_catalog import QuestCatalog, QuestRecord


class QuestHierarchyLazyRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def make_catalog() -> QuestCatalog:
        return QuestCatalog(
            [
                QuestRecord(1, "Une", "Catégorie", 1, 1, ""),
                QuestRecord(2, "Deux", "Catégorie", 2, 2, "Qf=1"),
                QuestRecord(3, "Trois", "Catégorie", 3, 3, "Qf=2"),
            ]
        )

    def make_page(self, root: Path) -> QuestsPage:
        profile = root / "client_profiles.json"
        clients = root / "client_index.json"
        progress = root / "quest_progress.json"
        owned = root / "craft_selection.json"
        profile.write_text("{}", encoding="utf-8")
        clients.write_text(json.dumps({"clients": []}), encoding="utf-8")
        progress.write_text(json.dumps({"version": 1, "characters": {}}), encoding="utf-8")
        owned.write_text(json.dumps({"items": []}), encoding="utf-8")
        return QuestsPage(
            lambda _message: None,
            quest_provider=QuestProvider(catalog=self.make_catalog()),
            progress_path=progress,
            profile_path=profile,
            client_index_path=clients,
            owned_items_path=owned,
        )

    def test_large_hierarchy_materializes_quests_only_for_opened_series(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.pages.quests_page._MIN_LAZY_QUESTS", 1):
                page = self.make_page(Path(tmp))

                self.assertEqual(page.quest_tree_items, {})
                series_id = next(iter(page.series_items))
                series_item = page.series_items[series_id]
                self.assertEqual(series_item.childCount(), 1)

                page.focus_hierarchy_series(series_id)

                self.assertEqual(set(page.quest_tree_items), {1, 2, 3})
                self.assertEqual(series_item.childCount(), 3)

                page.deleteLater()
                self.app.processEvents()

    def test_same_hierarchy_refresh_keeps_qt_items_and_updates_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.pages.quests_page._MIN_LAZY_QUESTS", 1):
                page = self.make_page(Path(tmp))
                series_id = next(iter(page.series_items))
                page.focus_hierarchy_series(series_id)

                category_item = next(iter(page.category_items.values()))
                series_item = page.series_items[series_id]
                quest_item = page.quest_tree_items[1][0]

                page.current_character_key = "character:1"
                page.quest_progress_service.set_quest_completed(
                    page.current_character_key,
                    1,
                    True,
                )
                page.rebuild_hierarchy()

                self.assertIs(next(iter(page.category_items.values())), category_item)
                self.assertIs(page.series_items[series_id], series_item)
                self.assertIs(page.quest_tree_items[1][0], quest_item)
                self.assertTrue(quest_item.text(0).startswith("✓ "))

                page.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
