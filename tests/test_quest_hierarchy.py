from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QToolButton

from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.services import QuestGraphService, QuestHierarchyService
from app.pages.quests_page import QuestsPage
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


class QuestHierarchyServiceTests(unittest.TestCase):
    def test_source_series_order_and_truthful_fallback_are_preserved(self):
        catalog = QuestCatalog(
            [
                quest(1, "Première", "Île des Wabbits"),
                quest(2, "Deuxième", "Île des Wabbits", "Qf=1"),
                quest(3, "Troisième", "Île des Wabbits", "Qf=2"),
                quest(10, "Grade un", "Alignement Bonta"),
                quest(11, "Grade deux", "Alignement Bonta", "Qf=10"),
            ],
            achievement_series=(
                QuestAchievementSeries(99, "Suite Wabbit", "Île des Wabbits", 4, (1, 3, 2)),
            ),
        )
        provider = QuestProvider(catalog=catalog)
        hierarchy = QuestHierarchyService(catalog, QuestGraphService(provider)).build()

        wabbits = next(category for category in hierarchy.categories if category.name == "Île des Wabbits")
        self.assertEqual(wabbits.series[0].name, "Suite Wabbit")
        self.assertEqual(wabbits.series[0].quest_ids, (1, 3, 2))
        alignment = next(category for category in hierarchy.categories if category.name == "Alignement")
        self.assertEqual(alignment.series[0].name, "Alignement Bonta")
        self.assertEqual(alignment.series[0].quest_ids, (10, 11))

    def test_primary_path_prefers_the_specific_source_suite(self):
        catalog = QuestCatalog(
            [quest(index, f"Quête {index}", "Île de Pandala") for index in range(1, 6)],
            achievement_series=(
                QuestAchievementSeries(1, "Méta", "Eliocalypse", 0, (1, 2, 3, 4, 5)),
                QuestAchievementSeries(2, "Suite précise", "Île de Pandala", 0, (1, 2)),
            ),
        )
        provider = QuestProvider(catalog=catalog)
        hierarchy = QuestHierarchyService(catalog, QuestGraphService(provider)).build()

        self.assertEqual(hierarchy.path_for(1).series.name, "Suite précise")
        self.assertEqual(hierarchy.path_for(1, "achievement:1").series.name, "Méta")


class QuestsPageHierarchyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_closed_search_never_clears_the_selected_quest_sheet(self):
        from unittest.mock import patch
        from app.pages.lazy_quests_page import LazyQuestsPage
        catalog = QuestCatalog([quest(101, "Première", "Frigost")])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = LazyQuestsPage(lambda _: None, catalog=catalog, progress_path=root/"progress.json",
                profile_path=root/"profile.json", client_index_path=root/"clients.json",
                achievement_progress_path=root/"success.json", owned_items_path=root/"items.json")
            try:
                page.current_character_key = "character:1"
                page.select_quest(101, persist=False)
                page.search.blockSignals(True)
                page.search.setText("Première")
                page._search_debounce_timer.start()
                with patch.object(page, "render_empty_detail") as clear:
                    page.close_search_results()
                    self.assertFalse(page._search_debounce_timer.isActive())
                    self.assertTrue(page.search.signalsBlocked())
                    page._flush_search_refresh()
                    clear.assert_not_called()
                    self.assertEqual(page.quest_detail_view.current_quest_id, 101)
                    self.assertFalse(page.quest_list.isVisible())
            finally:
                page.deleteLater()
                self.app.processEvents()

    def test_global_and_standalone_character_changes_share_one_pipeline(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage
        quest_page = Mock()
        host = SimpleNamespace(quest_page=quest_page, current_character_key="character:8")
        EncyclopediaPage.sync_quest_page_character(host)
        quest_page.set_character_key.assert_called_once_with("character:8")
        from app.pages._quests_page_impl import QuestsPage as Base
        from app.pages.lazy_quests_page import LazyQuestsPage
        self.assertIs(QuestsPage.set_character_key, Base.set_character_key)
        self.assertIs(LazyQuestsPage.set_character_key, Base.set_character_key)

    def test_all_quest_readers_use_one_hierarchy_materializer(self):
        from app.pages._quests_page_impl import QuestsPage as Base
        from app.pages.lazy_quests_page import LazyQuestsPage
        for view in (QuestsPage, LazyQuestsPage):
            for name in ("on_hierarchy_item_expanded", "_materialize_hierarchy_category",
                         "_materialize_hierarchy_series", "sync_hierarchy_selection",
                         "ensure_series_quests_loaded", "focus_hierarchy_series", "refresh_owned_items"):
                self.assertIs(getattr(view, name), getattr(Base, name))

    def test_hierarchy_keeps_nodes_and_updates_unopened_series_after_progress_change(self):
        from app.pages.lazy_quests_page import LazyQuestsPage
        from unittest.mock import patch
        catalog = QuestCatalog(
            [quest(101, "Première", "Frigost"), quest(102, "Deuxième", "Frigost")],
            achievement_series=(QuestAchievementSeries(552, "Suite", "Frigost", 0, (101, 102)),),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for view in (QuestsPage, LazyQuestsPage):
                with self.subTest(view=view.__name__):
                    page = view(lambda _: None, catalog=catalog, progress_path=root/"progress.json",
                                profile_path=root/"profile.json", client_index_path=root/"clients.json",
                                achievement_progress_path=root/"success.json", owned_items_path=root/"items.json")
                    try:
                        category = page.category_items[page.hierarchy.path_for(101).category.name]
                        page.current_character_key = "character:1"
                        with patch.object(page, "is_quest_done", return_value=True):
                            page.refresh_hierarchy_quest_state(101)
                        series = page.ensure_series_quests_loaded("achievement:552")
                        self.assertEqual(series.child(0).text(0), "✓ Première")
                        leaf = series.child(0)
                        page.on_hierarchy_item_expanded(series)
                        self.assertIs(series.child(0), leaf)
                        self.assertEqual(len(page.quest_tree_items[101]), 1)
                        with patch.object(page.quest_progress_service, "completed_quest_ids", return_value={102}):
                            page.rebuild_hierarchy()
                        self.assertIs(page.category_items[category.text(0)], category)
                        self.assertIs(series.child(0), leaf)
                        self.assertEqual(leaf.text(0), "Première")
                        self.assertEqual(series.child(1).text(0), "✓ Deuxième")
                        page.owned_items_path.write_text('{"items":[{"item_id":8,"quantity":5}]}', encoding="utf-8")
                        page.refresh_owned_items()
                        self.assertEqual(page.owned_items, {8:5})
                        page.owned_items_path.unlink()
                        page.refresh_owned_items()
                        self.assertEqual(page.owned_items, {})
                    finally:
                        page.deleteLater()
                        self.app.processEvents()

    def test_tree_breadcrumb_and_next_navigation_stay_in_quests(self):
        catalog = QuestCatalog(
            [
                quest(101, "La terre banquise", "Île de Frigost"),
                quest(102, "La maire de glace", "Île de Frigost", "Qf=101"),
            ],
            achievement_series=(
                QuestAchievementSeries(552, "Fri carré", "Île de Frigost", 0, (101, 102)),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profiles.json"
            client_index = root / "clients.json"
            progress = root / "progress.json"
            profile.write_text(
                json.dumps({KEY_SESSION_ORDER: ["alpha", "", "", "", "", "", "", ""]}),
                encoding="utf-8",
            )
            client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")
            page = QuestsPage(
                lambda _text: None,
                catalog=catalog,
                progress_path=progress,
                profile_path=profile,
                client_index_path=client_index,
            )

            page.select_quest(101)
            self.app.processEvents()
            self.assertEqual(page.quest_detail_view.current_quest_id, 101)
            self.assertEqual(page.breadcrumb_layout.contentsMargins().top(), 5)
            breadcrumb = [label.text() for label in page.breadcrumb.findChildren(QLabel)]
            self.assertEqual(breadcrumb.count("›"), 3)
            self.assertIn("La terre banquise", breadcrumb)
            self.assertEqual(page.quest_detail_view.context.ordered_quest_ids, (101, 102))
            next_button = page.quest_detail_view.findChild(QPushButton, "QuestNextButton")
            self.assertIsNotNone(next_button)
            self.assertEqual(next_button.toolTip(), "La maire de glace")

            page.hierarchy_collapse_button.click()
            self.app.processEvents()
            self.assertTrue(page.hierarchy_collapsed)
            self.assertTrue(page.hierarchy_content.isHidden())
            self.assertFalse(page.hierarchy_collapsed_rail.isHidden())
            self.assertEqual(page.hierarchy_panel.maximumWidth(), 44)
            self.assertEqual(page.body_splitter.handleWidth(), 0)
            expand_button = page.hierarchy_collapsed_rail.findChild(QToolButton, "GuideStepsCollapseButton")
            self.assertIsNotNone(expand_button)
            expand_button.click()
            self.app.processEvents()
            self.assertFalse(page.hierarchy_collapsed)
            self.assertFalse(page.hierarchy_content.isHidden())
            self.assertEqual(page.hierarchy_panel.minimumWidth(), 300)

            next_button.click()
            self.app.processEvents()
            self.assertEqual(page.selected_quest_id, 102)
            self.assertEqual(page.active_series_id, "achievement:552")
            self.assertEqual(page.quest_detail_view.current_quest_id, 102)
            self.assertIn(
                "La maire de glace",
                [label.text() for label in page.breadcrumb.findChildren(QLabel)],
            )
            page.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
