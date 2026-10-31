"""Real manual route/QuestProvider layout checks; offscreen is not desktop E2E."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListWidget, QLineEdit

from app.modules.encyclopedia.providers.quest_provider import QuestProvider
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services import AchievementProgressService
from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import GuideUltimeManualRuntimeService
from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView


class GuideManualLongLayoutTests(unittest.TestCase):
    def test_long_summary_search_normalizes_rows_only_on_population(self):
        QApplication.instance() or QApplication([])
        view = SimpleNamespace(
            service=SimpleNamespace(cards=[
                {"manual_title": "Astrub — entrée"},
                {"manual_chapter_label": "Amakna", "destination": "Village"},
                {"manual_title": "Astrub — sortie"},
            ]),
            summary_list=QListWidget(),
            summary_search=QLineEdit(),
        )
        view._filter_summary = lambda value: SharedGuideManualView._filter_summary(view, value)
        try:
            from app.modules.encyclopedia.views import shared_manual_guide_view as module
            with patch.object(module, "normalize_text", wraps=module.normalize_text) as normalize:
                SharedGuideManualView._populate_summary(view)
                initial_calls = normalize.call_count
                self.assertEqual(initial_calls, 4)  # 3 labels + initial empty search
                SharedGuideManualView._filter_summary(view, "Astrub")
                self.assertEqual(normalize.call_count, initial_calls + 1)
                self.assertEqual(
                    [view.summary_list.item(i).isHidden() for i in range(3)],
                    [False, True, False],
                )
                SharedGuideManualView._filter_summary(view, "Village")
                self.assertEqual(normalize.call_count, initial_calls + 2)
                self.assertEqual(
                    [view.summary_list.item(i).isHidden() for i in range(3)],
                    [True, False, True],
                )
        finally:
            view.summary_list.deleteLater()
            view.summary_search.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_long_canonical_card_scrolls_and_navigation_stays_reachable(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            provider = QuestProvider()
            self.assertGreater(len(provider.list_quests()), 1900)
            service = GuideUltimeManualRuntimeService(
                QuestProgressService(root / "quests.json"),
                AchievementProgressService(root / "achievements.json"),
                GuideProgressService(root / "guide.json"),
                quest_provider=provider, autoload=False, use_disk_cache=False,
            )
            self.assertEqual(len(service.cards), 267)
            index = next(i for i, card in enumerate(service.cards) if card["manual_stage_id"] == "P200-23")
            view = SharedGuideManualView(service, character_key="character:170", quest_provider=provider)
            try:
                view.view_index = index
                view._render_window(reset_scroll=True)
                for width, height in ((900, 600), (1180, 720)):
                    with self.subTest(width=width, height=height):
                        view.resize(width, height)
                        view.show()
                        view.activateWindow()
                        app.processEvents()
                        scroll = view.scroll
                        bar = scroll.verticalScrollBar()
                        self.assertGreater(bar.maximum(), 0)
                        self.assertLessEqual(scroll.widget().width(), scroll.viewport().width())
                        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                        bar.setValue(0)
                        QTest.keyClick(scroll, Qt.Key_PageDown)
                        app.processEvents()
                        self.assertGreater(bar.value(), 0)
                        bar.setValue(bar.maximum())
                        app.processEvents()
                        self.assertTrue(view.next_button.isVisible())
                        self.assertTrue(view.next_button.isEnabled())
                        self.assertTrue(view.rect().contains(view.next_button.mapTo(
                            view, view.next_button.rect().center())))
                        view.next_button.setFocus()
                        app.processEvents()
                        self.assertTrue(view.next_button.hasFocus())
                        self.assertEqual(view.rendered_card_count, 1)
            finally:
                view.close()
                view.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                app.processEvents()
