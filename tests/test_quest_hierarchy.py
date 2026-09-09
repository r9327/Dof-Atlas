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
            self.assertEqual(breadcrumb.count(">"), 3)
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
