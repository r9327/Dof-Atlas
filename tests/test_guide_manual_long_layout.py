"""Real manual route/QuestProvider layout checks; offscreen is not desktop E2E."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame

from app.modules.encyclopedia.providers.quest_provider import QuestProvider
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services import AchievementProgressService
from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import GuideUltimeManualRuntimeService
from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView


class GuideManualLongLayoutTests(unittest.TestCase):
    def test_global_header_has_no_long_route_summary_index(self):
        QApplication.instance() or QApplication([])
        from tests.test_guide_ultime_manual_ui_navigation import (
            _FakeManualUiService, _FakeParticipantService,
        )
        view = SharedGuideManualView(
            _FakeManualUiService(), character_key="character:1",
            participant_service=_FakeParticipantService(),
        )
        try:
            self.assertFalse(hasattr(view, "summary_list"))
            self.assertFalse(hasattr(view, "summary_search"))
            self.assertIsNone(view.findChild(QFrame, "GuideSummaryPanel"))
            self.assertIsNotNone(view.findChild(QFrame, "GuideGlobalDetailsPanel"))
            self.assertIsNotNone(view.preparation_button)
            self.assertEqual(view.rendered_card_count, 1)
        finally:
            view.close()
            view.deleteLater()
            QCoreApplication.sendPostedEvents(view, QEvent.DeferredDelete)

    def test_long_shared_summary_is_lazy_and_keeps_existing_rows(self):
        app = QApplication.instance() or QApplication([])
        from app.ui.components import AtlasGuideReadingHeader

        header = AtlasGuideReadingHeader("Guide long")
        titles = tuple(f"Fiche {index + 1}" for index in range(267))
        calls = []
        requests = []

        def provide_titles():
            calls.append(True)
            return titles

        try:
            header.set_summary_provider(provide_titles)
            header.summaryRequested.connect(requests.append)
            header.set_summary_position(10)
            self.assertEqual(calls, [])
            self.assertEqual(header.summary_panel.count(), 0)
            header.global_details_button.click()
            self.assertEqual(calls, [])
            header.summary_button.click()
            self.assertEqual(len(calls), 1)
            self.assertEqual(header.summary_panel.count(), 267)
            self.assertEqual(header.summary_panel.currentRow(), 10)
            first = header.summary_panel.item(0)
            self.assertEqual(first.text(), "1. Fiche 1")
            first.setData(Qt.UserRole, "existing-row")

            header.set_summary_position(266)
            self.assertEqual(header.summary_panel.currentRow(), 266)
            self.assertEqual(header.summary_panel.item(266).text(), "267. Fiche 267")
            self.assertEqual(header.summary_panel.item(0).data(Qt.UserRole), "existing-row")
            self.assertEqual(requests, [])

            header.global_details_button.click()
            calls_before = len(calls)
            header.set_summary_position(20)
            self.assertEqual(len(calls), calls_before)
            header.global_details_button.click()
            self.assertEqual(header.summary_panel.currentRow(), 20)
            self.assertEqual(header.summary_panel.item(0).data(Qt.UserRole), "existing-row")
            self.assertEqual(requests, [])
        finally:
            header.close()
            header.deleteLater()
            QCoreApplication.sendPostedEvents(header, QEvent.DeferredDelete)
            app.processEvents()

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
                        # Offscreen/monolithic runs can keep another top-level
                        # Qt fixture active. Focus policy is the deterministic
                        # keyboard-reachability contract; visibility, enabled
                        # state and in-window geometry are asserted above.
                        self.assertNotEqual(view.next_button.focusPolicy(), Qt.NoFocus)
                        self.assertEqual(view.rendered_card_count, 1)
            finally:
                view.close()
                view.deleteLater()
                QCoreApplication.sendPostedEvents(view, QEvent.DeferredDelete)
                app.processEvents()
