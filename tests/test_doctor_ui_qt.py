from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QToolButton, QWidget

from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView
from tools.atlas_doctor_lib.doctor_ui import verdict
from tools.atlas_doctor_lib.doctor_ui_qt import (
    UiSession, click_target, first_quest_failure, geometry_observations, settle,
    quest_outcome, sheet_observations, widget_tree,
)


class FixtureService:
    """Only validator fault tests use synthetic cards; production scenes never do."""
    def __init__(self, path):
        self.path = path
        self.available = True
        self.cards = [
            {"manual_stage_id": "TEST-A", "manual_title": "Page A", "manual_quest_ids": [321],
             "manual_lines": [{"kind": "action", "text": "First unique action", "position": ""}]},
            {"manual_stage_id": "TEST-B", "manual_title": "Page B", "manual_quest_ids": [],
             "manual_lines": [{"kind": "action", "text": "Second unique action", "position": ""}]},
        ]
        self.quest_provider = SimpleNamespace(get_quest=lambda qid: SimpleNamespace(id=qid, name="Fixture quest"))
        self.progress = {}

    def reload_progress(self):
        self.progress = json.loads(self.path.read_text()) if self.path.exists() else {}

    def manual_sections_for_card(self, key, card):
        return {"now": card["manual_lines"]}

    def manual_lines_for_card(self, key, card):
        return card["manual_lines"]

    def first_incomplete_index(self, key):
        return next((i for i, card in enumerate(self.cards) if not self.page_checked(key, card, i)), 1)

    def route_sheet_progress(self, key):
        return sum(self.page_checked(key, c, i) for i, c in enumerate(self.cards)), 2

    def card_auto_complete(self, key, card):
        return False

    def page_checked(self, key, card, index=0):
        return self.manual_checked(key, card["manual_stage_id"])

    def set_page_checked(self, key, card, index, checked):
        self.set_manual_checked(key, card["manual_stage_id"], checked)

    def manual_checked(self, key, stage):
        return self.progress.get(key, {}).get(stage, False)

    def set_manual_checked(self, key, stage, checked):
        self.progress.setdefault(key, {})[stage] = checked
        self.path.write_text(json.dumps(self.progress))


class DoctorUiQtFaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.service = FixtureService(self.folder / "progress.json")
        self.view = SharedGuideManualView(self.service, character_key="character:doctor-fixture")
        self.view.resize(1000, 700)
        self.view.show()
        settle()

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()
        settle()
        self.temp.cleanup()

    def test_healthy_real_renderer_click_changes_page_and_old_sheet_is_destroyed(self):
        from shiboken6 import isValid

        old = self.view.findChild(QFrame, "GuideManualSheet")
        self.assertEqual(sheet_observations(self.view, self.service.cards[0])["missing_lines"], [])
        self.assertTrue(click_target(self.view, self.view.next_button)["accessible"])
        self.assertEqual(self.view.view_index, 1)
        self.assertFalse(isValid(old))
        self.assertEqual(sheet_observations(self.view, self.service.cards[1])["stale_or_duplicate_lines"], [])
        click_target(self.view, self.view.prev_button)
        self.assertEqual(self.view.view_index, 0)

    def test_duplicate_sheet_and_stale_line_detected_from_real_qt_tree(self):
        sheet = self.view.findChild(QFrame, "GuideManualSheet")
        duplicate = QFrame(self.view.content)
        duplicate.setObjectName("GuideManualSheet")
        duplicate.card = self.service.cards[0]
        self.view.cards_layout.addWidget(duplicate)
        duplicate.show()
        settle()
        self.assertEqual(sheet_observations(self.view, self.service.cards[0])["sheet_count"], 2)
        duplicate.deleteLater()
        settle()
        self.view._show_index(1)
        settle()
        from PySide6.QtWidgets import QLabel, QHBoxLayout
        stale = QFrame()
        stale.setObjectName("GuideManualLineRow")
        layout = QHBoxLayout(stale)
        layout.addWidget(QLabel("Old page A ghost"))
        self.view.findChild(QFrame, "GuideManualSheet").layout().addWidget(stale)
        settle()
        observed = sheet_observations(self.view, self.service.cards[1])
        self.assertEqual(observed["stale_or_duplicate_lines"], ["Old page A ghost"])

    def test_disconnected_button_does_not_receive_a_false_navigation_pass(self):
        self.view.next_button.clicked.disconnect()
        click = click_target(self.view, self.view.next_button)
        self.assertTrue(click["accessible"])
        session = UiSession(self.folder, "verify")
        session.scenario = "broken-next"
        session.check("next", "QTest next", 1, self.view.view_index,
                      self.view.view_index == 1, self.view)
        self.assertEqual(verdict(session.assertions, session.required), "FAIL")

    def test_wrong_validation_target_and_non_persistence_are_observable(self):
        check = self.view.findChild(QPushButton, "GuideManualPageCheck")
        check.toggled.disconnect()
        check.toggled.connect(lambda checked: self.service.set_page_checked(
            "character:doctor-fixture", self.service.cards[1], 1, checked))
        click_target(self.view, check)
        self.service.reload_progress()
        self.assertFalse(self.service.page_checked("character:doctor-fixture", self.service.cards[0]))
        self.assertTrue(self.service.page_checked("character:doctor-fixture", self.service.cards[1]))
        self.view._show_index(0)
        settle()
        check = self.view.findChild(QPushButton, "GuideManualPageCheck")
        check.toggled.disconnect()
        click_target(self.view, check)
        self.service.reload_progress()
        self.assertTrue(check.isChecked())
        self.assertFalse(self.service.page_checked("character:doctor-fixture", self.service.cards[0]))

    def test_collision_overlay_hidden_scroll_and_wrong_lock_are_detectable(self):
        overlay = QPushButton("Occluding overlay", self.view)
        overlay.setGeometry(self.view.next_button.geometry())
        # Map from the nested nav parent into the top-level view.
        overlay.move(self.view.next_button.mapTo(self.view, self.view.next_button.rect().topLeft()))
        overlay.show()
        overlay.raise_()
        settle()
        self.assertFalse(click_target(self.view, self.view.next_button)["accessible"])
        self.assertIn("GuideManualNextButton", geometry_observations(self.view, self.view)["inaccessible"])
        overlay.deleteLater()
        settle()
        self.view.content.setMinimumWidth(2000)
        settle()
        self.assertTrue(geometry_observations(self.view, self.view)["horizontal_overflow"])
        self.view.route_lock_check.toggled.disconnect()
        click_target(self.view, self.view.route_lock_check)
        self.assertTrue(self.view.route_lock_check.isChecked())
        self.assertFalse(self.service.manual_checked("character:doctor-fixture", self.view.ROUTE_LOCK_PROGRESS_KEY))

    def test_real_quest_signal_without_final_effect_fails_and_localizes_each_transition(self):
        sheet = self.view.findChild(QFrame, "GuideManualSheet")
        button = sheet.findChild(QToolButton, "GuideManualQuestInlineButton")
        spy = QSignalSpy(sheet.questRequested)
        click_target(self.view, button, self.view.scroll)
        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0)[0], 321)
        healthy = {"signal_ids": [321], "expected_quest_id": 321,
                   "active_tab": "QUÊTES", "expected_tab": "QUÊTES",
                   "quests_initialized": True, "selected_quest_id": 321,
                   "detail_visible": True, "detail_quest_id": 321, "lazy_pending": False}
        self.assertIsNone(first_quest_failure(healthy))
        cases = (({"signal_ids": []}, "questRequested"),
                 ({"signal_ids": [999]}, "questRequested"),
                 ({"active_tab": "GUIDES"}, "QUESTS_TAB"),
                 ({"lazy_pending": True}, "lazy-initialization"),
                 ({"selected_quest_id": 999}, "selected_quest_id"),
                 ({"detail_visible": False}, "detail-visible"),
                 ({"detail_quest_id": 999}, "detail-quest-id"))
        for change, expected in cases:
            with self.subTest(change=change):
                self.assertEqual(first_quest_failure({**healthy, **change}), expected)
        # The real production view with no final navigator emits a signal but
        # cannot prove a tab/detail effect. This must fail at the tab transition.
        self.assertEqual(first_quest_failure({**healthy, "active_tab": "GUIDES",
                                             "detail_visible": False}), "QUESTS_TAB")

    def test_real_png_and_tree_share_action_ids_and_verify_mode_omits_images(self):
        session = UiSession(self.folder, "all")
        session.scenario = "fixture"
        session.check("identity", "inspect", "TEST-A", "TEST-A", True, self.view)
        row = session.assertions[0]
        self.assertTrue(any(path.endswith(".png") for path in row["evidence_ids"]))
        for path in row["evidence_ids"]:
            self.assertTrue((self.folder / path).is_file())
        self.assertTrue((self.folder / "001-fixture.png").read_bytes().startswith(b"\x89PNG"))
        tree = widget_tree(self.view)
        self.assertTrue(any(n["objectName"] == "GuideManualQuestInlineButton" and n["rect"][2] > 0 for n in tree))
        verify = UiSession(self.folder, "verify")
        self.assertTrue(all(not p.endswith(".png") for p in verify.snapshot(self.view)))

    def test_real_encyclopedia_final_navigation_and_injected_broken_chain(self):
        from unittest.mock import patch
        from app.modules.encyclopedia.constants import GUIDES_TAB, QUESTS_TAB
        from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
        from app.modules.encyclopedia.services import QuestGraphService
        from app.modules.encyclopedia.services.link_service import LinkService
        from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage
        from app.quest_catalog import QuestCatalog, QuestRecord

        # Public-data production scenes are covered separately by Doctor UI.
        # This small synthetic catalog permits deterministic fault injection in
        # the REAL final tab/selection/detail chain without Doduda setup.
        provider = QuestProvider(catalog=QuestCatalog([
            QuestRecord(id=321, name="Fixture quest", category="Doctor", level_min=1,
                        level_max=1, start_criterion="")]))
        achievements = AchievementProvider(quest_provider=provider)
        achievements._loaded = True
        guide_dir = self.folder / "empty-guides"
        guide_dir.mkdir()
        guides = GuideProvider(guides_dir=guide_dir, quest_provider=provider, achievement_provider=achievements)
        paths = {name: self.folder / (name + ".json") for name in ("q", "a", "g", "p", "c", "i")}
        for path in paths.values():
            path.write_text("{}")
        page = EncyclopediaPage(
            lambda _text: None, quest_provider=provider, achievement_provider=achievements,
            guide_provider=guides, quest_graph=QuestGraphService(provider, guides, achievements, eager=False),
            progress_path=paths["q"], achievement_progress_path=paths["a"], guide_progress_path=paths["g"],
            profile_path=paths["p"], client_index_path=paths["c"], owned_items_path=paths["i"],
            initial_tab=QUESTS_TAB)
        page.resize(1200, 800)
        page.show()
        settle()
        link = LinkService(page.navigate_to_entity)
        self.view.navigate_entity = link.navigate_to_entity

        def reset():
            self.view._show_index(0)
            settle()
            # Keep the unrelated Guide catalog cold in this fault fixture.
            page.tabs.blockSignals(True)
            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            page.tabs.blockSignals(False)
            sheet = self.view.findChild(QFrame, "GuideManualSheet")
            button = sheet.findChild(QToolButton, "GuideManualQuestInlineButton")
            return sheet, button, QSignalSpy(sheet.questRequested)

        try:
            sheet, button, spy = reset()
            click_target(self.view, button, self.view.scroll)
            settle(lambda: first_quest_failure(quest_outcome(page, 321, [spy.at(i) for i in range(spy.count())])) is None)
            self.assertIsNone(first_quest_failure(quest_outcome(page, 321, [spy.at(0)])))
            self.assertTrue(page.quest_page.quest_detail_view.isVisible())

            sheet, button, spy = reset()
            button.clicked.disconnect()
            click_target(self.view, button, self.view.scroll)
            self.assertEqual(first_quest_failure(quest_outcome(page, 321, [])), "questRequested")

            sheet, button, spy = reset()
            button.clicked.disconnect()
            button.clicked.connect(lambda: sheet.questRequested.emit(999, "TEST-A", 0))
            click_target(self.view, button, self.view.scroll)
            self.assertEqual(first_quest_failure(quest_outcome(page, 321, [spy.at(0)])), "questRequested")

            sheet, button, spy = reset()
            with patch.object(page.tabs, "setCurrentIndex", return_value=None):
                click_target(self.view, button, self.view.scroll)
            self.assertEqual(first_quest_failure(quest_outcome(page, 321, [spy.at(0)])), "QUESTS_TAB")

            sheet, button, spy = reset()
            with patch.object(page.quest_page, "select_quest", return_value=None):
                page.quest_page._detail_pending = True
                click_target(self.view, button, self.view.scroll)
                self.assertEqual(first_quest_failure(quest_outcome(page, 321, [spy.at(0)])), "lazy-initialization")
            page.quest_page._detail_pending = False

            sheet, button, spy = reset()
            click_target(self.view, button, self.view.scroll)
            settle()
            page.quest_page.quest_detail_view.hide()
            self.assertEqual(first_quest_failure(quest_outcome(page, 321, [spy.at(0)])), "detail-visible")
            page.quest_page.quest_detail_view.show()
            original = page.quest_page.quest_detail_view.current_quest_id
            page.quest_page.quest_detail_view.current_quest_id = 999
            self.assertEqual(first_quest_failure(quest_outcome(page, 321, [spy.at(0)])), "detail-quest-id")
            page.quest_page.quest_detail_view.current_quest_id = original
        finally:
            page.close()
            page.deleteLater()
            settle()


if __name__ == "__main__":
    unittest.main()
