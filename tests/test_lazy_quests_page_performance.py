from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.views import EncyclopediaPage
from app.modules.encyclopedia.constants import QUESTS_TAB
from app.pages.lazy_quests_page import LazyQuestsPage
from app.pages.quests_page import HIERARCHY_ID_ROLE, HIERARCHY_KIND_ROLE
from app.quest_catalog import QuestAchievementSeries, QuestCatalog, QuestRecord
from app.storage import KEY_SESSION_ORDER


def quest(quest_id: int, name: str, category: str, criterion: str = "") -> QuestRecord:
    return QuestRecord(
        id=quest_id,
        name=name,
        category=category,
        level_min=quest_id,
        level_max=quest_id,
        start_criterion=criterion,
    )


def catalog_fixture() -> QuestCatalog:
    return QuestCatalog(
        [
            quest(1, "Première A", "Zone test"),
            quest(2, "Deuxième A", "Zone test", "Qf=1"),
            quest(3, "Première B", "Zone test"),
            quest(4, "Deuxième B", "Zone test", "Qf=3"),
        ],
        achievement_series=(
            QuestAchievementSeries(10, "Suite A", "Zone test", 0, (1, 2)),
            QuestAchievementSeries(20, "Suite B", "Zone test", 1, (3, 4)),
        ),
    )


class LazyQuestsPagePerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def build_page(self, root: Path) -> LazyQuestsPage:
        profile = root / "profiles.json"
        client_index = root / "clients.json"
        profile.write_text(
            json.dumps({KEY_SESSION_ORDER: ["alpha", "", "", "", "", "", "", ""]}),
            encoding="utf-8",
        )
        client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")
        return LazyQuestsPage(
            lambda _text: None,
            catalog=catalog_fixture(),
            progress_path=root / "progress.json",
            achievement_progress_path=root / "achievement_progress.json",
            profile_path=profile,
            client_index_path=client_index,
            owned_items_path=root / "owned_items.json",
        )

    def test_initial_tree_build_keeps_quest_rows_lazy(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(Path(temporary))

            self.assertEqual(page.quest_tree_items, {})
            self.assertEqual(page._loaded_series_ids, set())
            self.assertEqual(set(page.series_items), {"achievement:10", "achievement:20"})
            for item in page.series_items.values():
                self.assertEqual(item.childCount(), 1)
                self.assertEqual(item.child(0).data(0, HIERARCHY_KIND_ROLE), "placeholder")

            page.deleteLater()
            self.app.processEvents()

    def test_expanding_one_series_materializes_only_that_series_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(Path(temporary))
            first = page.series_items["achievement:10"]
            second = page.series_items["achievement:20"]

            first.setExpanded(True)
            self.app.processEvents()

            self.assertEqual(page._loaded_series_ids, {"achievement:10"})
            self.assertEqual(first.childCount(), 2)
            self.assertEqual(
                [first.child(index).data(0, HIERARCHY_ID_ROLE) for index in range(first.childCount())],
                [1, 2],
            )
            self.assertEqual(set(page.quest_tree_items), {1, 2})
            self.assertEqual(second.childCount(), 1)
            self.assertEqual(second.child(0).data(0, HIERARCHY_KIND_ROLE), "placeholder")

            first.setExpanded(False)
            first.setExpanded(True)
            self.app.processEvents()
            self.assertEqual(first.childCount(), 2)
            self.assertEqual(len(page.quest_tree_items[1]), 1)
            self.assertEqual(len(page.quest_tree_items[2]), 1)

            page.deleteLater()
            self.app.processEvents()

    def test_selecting_quest_loads_target_series_and_keeps_navigation_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(Path(temporary))

            page.select_quest(3, persist=False, series_id="achievement:20")
            self.app.processEvents()

            self.assertEqual(page.active_series_id, "achievement:20")
            self.assertEqual(page.selected_quest_id, 3)
            self.assertIn("achievement:20", page._loaded_series_ids)
            self.assertNotIn("achievement:10", page._loaded_series_ids)
            current = page.hierarchy_tree.currentItem()
            self.assertIsNotNone(current)
            self.assertEqual(current.data(0, HIERARCHY_KIND_ROLE), "quest")
            self.assertEqual(current.data(0, HIERARCHY_ID_ROLE), 3)
            self.assertEqual(page.quest_detail_view.context.ordered_quest_ids, (3, 4))

            page.deleteLater()
            self.app.processEvents()

    def test_search_text_is_cached_until_related_context_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(Path(temporary))
            row = page.catalog.by_id[1]

            first = page.quest_search_text(row)
            self.assertIn(1, page._quest_search_text_cache)
            second = page.quest_search_text(row)
            self.assertEqual(first, second)
            self.assertEqual(len(page._quest_search_text_cache), 1)

            page.update_related_context(graph=page.graph)
            self.assertEqual(page._quest_search_text_cache, {})

            page.deleteLater()
            self.app.processEvents()

    def test_public_encyclopedia_export_builds_lazy_quests_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profiles.json"
            client_index = root / "clients.json"
            profile.write_text(
                json.dumps({KEY_SESSION_ORDER: ["alpha", "", "", "", "", "", "", ""]}),
                encoding="utf-8",
            )
            client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")
            provider = QuestProvider(catalog=catalog_fixture())
            page = EncyclopediaPage(
                lambda _text: None,
                quest_provider=provider,
                progress_path=root / "progress.json",
                achievement_progress_path=root / "achievement_progress.json",
                guide_progress_path=root / "guide_progress.json",
                profile_path=profile,
                client_index_path=client_index,
                owned_items_path=root / "owned_items.json",
                initial_tab=QUESTS_TAB,
            )

            self.assertIsInstance(page.quest_page, LazyQuestsPage)
            self.assertEqual(page.quest_page.quest_tree_items, {})

            page.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
