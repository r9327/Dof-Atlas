from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.pages.lazy_quests_page import LazyQuestsPage
from app.quest_catalog import QuestAchievementSeries, QuestCatalog, QuestRecord
from app.storage import KEY_SESSION_ORDER


def quest(quest_id: int, name: str, criterion: str = "") -> QuestRecord:
    return QuestRecord(
        id=quest_id,
        name=name,
        category="Île de Frigost",
        level_min=quest_id,
        level_max=quest_id,
        start_criterion=criterion,
    )


class QuestInteractionRuntimePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def build_page(self, root: Path) -> LazyQuestsPage:
        profile = root / "profiles.json"
        client_index = root / "clients.json"
        progress = root / "progress.json"
        profile.write_text(
            json.dumps({KEY_SESSION_ORDER: ["alpha", "", "", "", "", "", "", ""]}),
            encoding="utf-8",
        )
        client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")
        catalog = QuestCatalog(
            [
                quest(101, "La terre banquise"),
                quest(102, "La maire de glace", "Qf=101"),
            ],
            achievement_series=(
                QuestAchievementSeries(552, "Fri carré", "Île de Frigost", 0, (101, 102)),
            ),
        )
        page = LazyQuestsPage(
            lambda _text: None,
            catalog=catalog,
            progress_path=progress,
            profile_path=profile,
            client_index_path=client_index,
        )
        page.current_character_key = "character:1"
        page.quest_detail_view.set_character_key("character:1")
        return page

    def test_validation_keeps_current_sheet_and_avoids_body_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(Path(temporary))
            page.select_quest(101)
            self.app.processEvents()

            view = page.quest_detail_view
            solution_calls = 0
            original_render_solution = view._render_solution

            def counted_render_solution(*args, **kwargs):
                nonlocal solution_calls
                solution_calls += 1
                return original_render_solution(*args, **kwargs)

            view._render_solution = counted_render_solution
            view.toggle_completed()
            self.app.processEvents()

            self.assertTrue(page.is_quest_done(101))
            self.assertEqual(page.selected_quest_id, 101)
            self.assertEqual(view.current_quest_id, 101)
            self.assertEqual(solution_calls, 0)
            self.assertEqual(view.title_label.text(), "La terre banquise")
            self.assertIn("Quête terminée", view.done_button.text())

            page.deleteLater()
            self.app.processEvents()

    def test_next_quest_navigation_resets_shared_sheet_scrolls(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = self.build_page(Path(temporary))
            page.select_quest(101)
            self.app.processEvents()

            for scroll in (page.quest_detail_view.center_scroll, page.quest_detail_view.right_scroll):
                bar = scroll.verticalScrollBar()
                bar.setRange(0, 100)
                bar.setValue(73)

            self.assertTrue(page.open_related_quest(102))
            self.app.processEvents()

            self.assertEqual(page.selected_quest_id, 102)
            self.assertEqual(page.quest_detail_view.current_quest_id, 102)
            for scroll in (page.quest_detail_view.center_scroll, page.quest_detail_view.right_scroll):
                bar = scroll.verticalScrollBar()
                self.assertEqual(bar.value(), bar.minimum())

            page.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
