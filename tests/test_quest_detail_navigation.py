from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import QuestGraphService, QuestProgressService
from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView


class QuestDetailNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_switching_quest_resets_shared_sheet_scroll_to_top(self) -> None:
        quest_provider = QuestProvider()
        achievement_provider = AchievementProvider(quest_provider=quest_provider)
        guide_provider = GuideProvider(
            quest_provider=quest_provider,
            achievement_provider=achievement_provider,
        )
        graph = QuestGraphService(quest_provider, guide_provider, achievement_provider)

        with tempfile.TemporaryDirectory() as tmp:
            view = QuestDetailView(
                quest_provider,
                graph,
                QuestProgressService(Path(tmp) / "progress.json"),
                achievement_provider=achievement_provider,
                guide_provider=guide_provider,
            )
            view.resize(720, 300)
            view.show()

            self.assertTrue(view.show_quest(2464))
            QTest.qWait(20)
            self.app.processEvents()
            center_bar = view.center_scroll.verticalScrollBar()
            right_bar = view.right_scroll.verticalScrollBar()
            self.assertGreater(center_bar.maximum(), 0)
            center_bar.setValue(center_bar.maximum())
            if right_bar.maximum() > 0:
                right_bar.setValue(right_bar.maximum())
            self.assertGreater(center_bar.value(), 0)

            self.assertTrue(view.show_quest(691))
            self.assertEqual(center_bar.value(), 0)
            self.assertEqual(right_bar.value(), 0)
            self.app.processEvents()
            self.assertEqual(center_bar.value(), 0)
            self.assertEqual(right_bar.value(), 0)

            view.close()
            view.deleteLater()


if __name__ == "__main__":
    unittest.main()
