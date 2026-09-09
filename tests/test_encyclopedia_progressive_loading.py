from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.pages.progressive_quests_page import ProgressiveQuestsPage
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


def catalog() -> QuestCatalog:
    return QuestCatalog(
        [
            quest(101, "La terre banquise", "Île de Frigost"),
            quest(102, "La maire de glace", "Île de Frigost", "Qf=101"),
            quest(201, "Premier pas", "Île de Pandala"),
        ],
        achievement_series=(
            QuestAchievementSeries(552, "Fri carré", "Île de Frigost", 0, (101, 102)),
            QuestAchievementSeries(777, "Pandala", "Île de Pandala", 0, (201,)),
        ),
    )


class EncyclopediaProgressiveLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def paths(root: Path) -> dict[str, Path]:
        result = {
            "profile": root / "profiles.json",
            "clients": root / "clients.json",
            "quest_progress": root / "quest_progress.json",
            "achievement_progress": root / "achievement_progress.json",
            "guide_progress": root / "guide_progress.json",
            "owned": root / "owned.json",
        }
        result["profile"].write_text(
            json.dumps({KEY_SESSION_ORDER: ["alpha", "", "", "", "", "", "", ""]}),
            encoding="utf-8",
        )
        result["clients"].write_text(json.dumps({"clients": []}), encoding="utf-8")
        result["owned"].write_text(json.dumps({"items": []}), encoding="utf-8")
        return result

    def test_quest_tree_loads_category_then_series_then_quest_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self.paths(root)
            page = ProgressiveQuestsPage(
                lambda _text: None,
                catalog=catalog(),
                progress_path=paths["quest_progress"],
                profile_path=paths["profile"],
                client_index_path=paths["clients"],
                owned_items_path=paths["owned"],
            )
            self.app.processEvents()

            self.assertGreater(page.hierarchy_tree.topLevelItemCount(), 0)
            self.assertEqual(page.series_items, {})
            self.assertEqual(page.quest_tree_items, {})
            self.assertIsNone(page.quest_detail_view.current_quest_id)

            frigost = page.category_items["Frigost"]
            self.assertEqual(frigost.childCount(), 1)  # lightweight placeholder only
            frigost.setExpanded(True)
            self.app.processEvents()

            self.assertIn("achievement:552", page.series_items)
            self.assertNotIn("achievement:777", page.series_items)
            self.assertEqual(page.quest_tree_items, {})

            series = page.series_items["achievement:552"]
            series.setExpanded(True)
            self.app.processEvents()
            self.assertEqual(set(page.quest_tree_items), {101, 102})
            self.assertIsNone(page.quest_detail_view.current_quest_id)

            page.select_quest(101)
            self.app.processEvents()
            self.assertEqual(page.quest_detail_view.current_quest_id, 101)

            page.deleteLater()
            self.app.processEvents()

if __name__ == "__main__":
    unittest.main()
