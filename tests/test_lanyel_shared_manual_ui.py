from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QLabel

from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import AchievementProgressService, GuideProgressService
from app.modules.encyclopedia.views.deferred_achievement_guides_view import DeferredAchievementGuidesView
from app.modules.encyclopedia.views.shared_manual_guide_view import (
    SharedGuideManualCard,
    SharedGuideManualView,
)


class LanyelSharedManualUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.quest_provider = QuestProvider()
        cls.achievement_provider = AchievementProvider(quest_provider=cls.quest_provider)
        cls.achievement_provider.load_all()
        cls.guide_provider = GuideProvider(
            quest_provider=cls.quest_provider,
            achievement_provider=cls.achievement_provider,
        )
        cls.guide_provider.load_all()

    def _view(self, root: Path) -> DeferredAchievementGuidesView:
        quest_progress = root / "quest_progress.json"
        achievement_progress = root / "achievement_progress.json"
        guide_progress = root / "guide_progress.json"
        for path in (quest_progress, achievement_progress, guide_progress):
            path.write_text("{}", encoding="utf-8")
        view = DeferredAchievementGuidesView(
            lambda _text: None,
            provider=self.guide_provider,
            quest_provider=self.quest_provider,
            achievement_provider=self.achievement_provider,
            achievement_progress_service=AchievementProgressService(achievement_progress),
            guide_progress_service=GuideProgressService(guide_progress),
            quest_progress_path=quest_progress,
        )
        view.set_character_key("character:1")
        return view

    def test_lanyel_opens_same_manual_roadbook_renderer_as_guide_succes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))

            self.assertTrue(view.select_guide("dofus_sylvestre"))
            self.app.processEvents()
            lanyel_view = view.stack.currentWidget()
            self.assertIsInstance(lanyel_view, SharedGuideManualView)
            self.assertEqual(view.current_guide_id, "dofus_sylvestre")
            service = view._catalog_manual_services["dofus_sylvestre"]
            self.assertEqual(service.guide_id, "dofus_sylvestre")
            self.assertEqual(service.guide_title, "Lanyel Sylvestre")
            self.assertEqual(len(service.cards), 198)
            self.assertTrue(all(card.get("manual_quest_ids") for card in service.cards))
            self.assertTrue(any(service.manual_sections_for_card("character:1", card)["now"] for card in service.cards))

            self.assertTrue(view.select_guide("guide_complet"))
            self.app.processEvents()
            success_view = view.stack.currentWidget()
            self.assertIsInstance(success_view, SharedGuideManualView)
            self.assertIsNot(lanyel_view, success_view)

            view.deleteLater()
            self.app.processEvents()

    def test_prepare_rows_share_one_red_parent_instead_of_red_row_tiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))
            self.assertTrue(view.select_guide("dofus_sylvestre"))
            service = view._catalog_manual_services["dofus_sylvestre"]
            source = copy.deepcopy(service.cards[0])
            source["manual_sections"] = copy.deepcopy(source.get("manual_sections") or {})
            source["manual_sections"]["prepare"] = [
                {"kind": "warning", "position": "", "text": "Prépare le premier objet."},
                {"kind": "warning", "position": "", "text": "Prépare le second objet."},
            ]

            card = SharedGuideManualCard(service, "character:1", source, 0)
            self.app.processEvents()
            parent = card.findChild(QFrame, "GuideManualWarningSection")
            self.assertIsNotNone(parent)
            lines = parent.findChildren(QLabel, "GuideManualLine")
            self.assertEqual(len(lines), 2)
            self.assertFalse(parent.findChildren(QLabel, "GuideManualWarning"))

            card.deleteLater()
            view.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
