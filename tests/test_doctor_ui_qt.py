from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QToolButton, QWidget

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView
from tests.test_guide_ultime_manual_ui_navigation import _FakeParticipantService
from tools.atlas_doctor_lib.doctor_ui import verdict
from tools.atlas_doctor_lib.doctor_ui_qt import (
    UiSession, click_target, click_achievement_row, first_quest_failure,
    first_achievement_failure, achievement_layout_observations,
    first_achievement_layout_failure, achievement_title_contrast,
    achievement_readable_text_observations, detailed_achievement_oracle,
    completion_transition_failure, bottom_guide_observations,
    first_quest_link_page, geometry_observations, settle,
    quest_outcome, sheet_observations, widget_tree, glyph_legibility_probe,
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
        self.progress_id = "catalog_manual:doctor_ui_fixture"
        self.guide_progress = GuideProgressService(path.with_name("guide_progress.json"))

    def page_key(self, card, index=0):
        return f"page:doctor:{card['manual_stage_id']}"

    def reload_progress(self):
        self.progress = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.guide_progress.reload()

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
        return self.guide_progress.is_manual_step_completed(
            key, self.progress_id, self.page_key(card, index)
        )

    def set_page_checked(self, key, card, index, checked):
        self.guide_progress.set_manual_step_completed(
            key, self.progress_id, self.page_key(card, index), checked
        )

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
        self.view = SharedGuideManualView(
            self.service, character_key="character:1",
            participant_service=_FakeParticipantService(),
        )
        self.view.resize(1000, 700)
        self.view.show()
        settle()

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()
        settle()
        self.temp.cleanup()

    def test_settle_yields_to_python_background_workers(self):
        completed = threading.Event()

        def work():
            deadline = time.monotonic() + 0.05
            while time.monotonic() < deadline:
                sum(range(100))
            completed.set()

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        self.assertTrue(settle(completed.is_set, timeout=0.5))
        worker.join(0.5)
        self.assertFalse(worker.is_alive())

    def test_real_scene_prepares_disk_only_quest_indexes_before_interaction(self):
        source = Path(
            "tools/atlas_doctor_lib/doctor_ui_qt.py"
        ).read_text(encoding="utf-8")
        scene = source[source.index("def build_scene("):source.index("def open_guide(")]
        self.assertIn("ensure_lazy_catalog_cache()", scene)
        self.assertIn("ensure_detail_source_offsets()", scene)
        self.assertLess(
            scene.index("ensure_detail_source_offsets()"),
            scene.index("quests = QuestProvider()"),
        )
        self.assertNotIn("get_detail(", scene)

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

    def test_quest_scenario_finds_first_page_with_a_real_link(self):
        self.service.cards[0]["manual_quest_ids"] = []
        self.service.cards[1]["manual_quest_ids"] = [321]
        index, sheet, buttons = first_quest_link_page(self.view)
        self.assertEqual(index, 1)
        self.assertEqual(sheet.card["manual_stage_id"], "TEST-B")
        self.assertEqual(len(buttons), 1)

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

    def test_real_guide_validation_persists_source_and_advances_to_unchecked_next_card(self):
        from shiboken6 import isValid

        character = "character:1"
        self.assertEqual(self.view.view_index, 0)
        self.assertEqual(self.view.active_index, 0)
        old = self.view.findChild(QPushButton, "GuideManualPageCheck")
        self.assertFalse(old.isChecked())
        click = click_target(self.view, old, self.view.scroll)
        self.service.reload_progress()
        self.assertTrue(click["accessible"])
        self.assertFalse(isValid(old))
        self.assertTrue(self.service.page_checked(character, self.service.cards[0], 0))
        self.assertEqual(self.view.view_index, 1)
        self.assertEqual(self.view.active_index, 1)
        next_button = self.view.findChild(QPushButton, "GuideManualPageCheck")
        self.assertFalse(next_button.isChecked())
        self.assertFalse(self.service.page_checked(character, self.service.cards[1], 1))
        self.assertEqual(sheet_observations(self.view, self.service.cards[1])["stage_ids"],
                         ["TEST-B"])
        # Reopening the SOURCE must show the saved check, not the destination's.
        self.view._show_index(0)
        settle()
        source_button = self.view.findChild(QPushButton, "GuideManualPageCheck")
        self.assertTrue(source_button.isChecked())

    def test_guide_manual_click_rebuilds_and_destroys_clicked_qt_button(self):
        from shiboken6 import isValid

        character = "character:1"
        card = self.service.cards[0]
        old = self.view.findChild(QPushButton, "GuideManualPageCheck")
        self.assertFalse(self.service.page_checked(character, card, 0))
        # Simulate production's synchronous widget replacement after saving
        # without mocking the real QPushButton, its mouse click or persistence.
        old.toggled.connect(lambda _checked: self.view._show_index(0))
        click = click_target(self.view, old, self.view.scroll)
        self.service.reload_progress()
        new = self.view.findChild(QPushButton, "GuideManualPageCheck")
        self.assertTrue(click["accessible"])
        self.assertFalse(isValid(old))
        self.assertIsNotNone(new)
        self.assertIsNot(new, old)
        self.assertTrue(self.service.page_checked(character, card, 0))
        self.assertTrue(new.isChecked())
        # The next click uses the *new* widget; never read the deleted handle.
        click_back = click_target(self.view, new, self.view.scroll)
        self.service.reload_progress()
        self.assertTrue(click_back["accessible"])
        self.assertFalse(self.service.page_checked(character, card, 0))
        current = self.view.findChild(QPushButton, "GuideManualPageCheck")
        self.assertFalse(current.isChecked())

    def test_wrong_validation_target_and_non_persistence_are_observable(self):
        check = self.view.findChild(QPushButton, "GuideManualPageCheck")
        check.toggled.disconnect()
        check.toggled.connect(lambda checked: self.service.set_page_checked(
            "character:1", self.service.cards[1], 1, checked))
        click_target(self.view, check)
        self.service.reload_progress()
        self.assertFalse(self.service.page_checked("character:1", self.service.cards[0]))
        self.assertTrue(self.service.page_checked("character:1", self.service.cards[1]))
        self.view._show_index(0)
        settle()
        check = self.view.findChild(QPushButton, "GuideManualPageCheck")
        check.toggled.disconnect()
        click_target(self.view, check)
        self.service.reload_progress()
        self.assertTrue(check.isChecked())
        self.assertFalse(self.service.page_checked("character:1", self.service.cards[0]))

    def test_real_guide_bottom_scroll_checks_rows_and_button_occlusion(self):
        from PySide6.QtWidgets import QHBoxLayout, QLabel
        from PySide6.QtCore import QRect

        sheet = self.view.findChild(QFrame, "GuideManualSheet")
        for index in range(45):
            line = QFrame()
            line.setObjectName("GuideManualLineRow")
            row = QHBoxLayout(line)
            row.addWidget(QLabel(f"Contenu du guide, ligne {index}"))
            sheet.layout().addWidget(line)
        target = QPushButton("Bouton en bas de page")
        target.setObjectName("GuideBottomAction")
        sheet.layout().addWidget(target)
        self.view.resize(640, 460)
        settle()
        healthy = bottom_guide_observations(self.view, self.view, self.service.cards[0])
        self.assertEqual(healthy["status"], "PASS", healthy)
        self.assertGreater(healthy["scroll_max"], 0)
        self.assertEqual(healthy["scroll_position"], healthy["scroll_max"])
        self.assertGreater(healthy["visible_line_rows"], 0)
        self.assertGreater(healthy["visible_line_text_labels"], 0)
        self.assertIn("GuideBottomAction",
                      [item["name"] for item in healthy["visible_buttons"]])

        point = target.mapTo(self.view, target.rect().topLeft())
        overlay = QPushButton("Intercept", self.view)
        overlay.setGeometry(QRect(point, target.size()))
        overlay.show()
        overlay.raise_()
        settle()
        broken = bottom_guide_observations(self.view, self.view, self.service.cards[0])
        self.assertEqual(broken["status"], "FAIL", broken)
        self.assertIn("GuideBottomAction", broken["occluded_buttons"])
        overlay.close()
        overlay.deleteLater()
        settle()

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
        click_target(self.view, self.view.settings_button)
        settle()
        self.view.route_lock_check.toggled.disconnect()
        click_target(self.view, self.view.route_lock_check)
        self.assertTrue(self.view.route_lock_check.isChecked())
        self.assertFalse(self.service.manual_checked("character:1", self.view.ROUTE_LOCK_PROGRESS_KEY))

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

    def test_real_qt_success_list_mouse_event_does_not_fake_detail_effect(self):
        from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout

        host = QWidget()
        layout = QVBoxLayout(host)
        listing = QListWidget()
        listing.setObjectName("QuestResultList")
        host.list_widget = listing
        layout.addWidget(listing)
        item = QListWidgetItem("Achievement from test public-style row")
        item.setData(Qt.UserRole, 321)
        listing.addItem(item)
        triggered = []
        listing.itemClicked.connect(
            lambda selected: triggered.append(int(selected.data(Qt.UserRole)))
        )
        host.resize(700, 450)
        host.show()
        settle()
        try:
            click = click_achievement_row(host, host, item)
            self.assertTrue(click["accessible"])
            self.assertEqual(click["item_id"], 321)
            self.assertEqual(triggered, [321])
            listing.itemClicked.disconnect()
            click = click_achievement_row(host, host, item)
            self.assertTrue(click["accessible"])
            # QTest injected another real click but no final signal consumer.
            self.assertEqual(triggered, [321])
        finally:
            host.close()
            host.deleteLater()
            settle()

    def test_success_detail_oracle_localizes_hidden_and_wrong_details(self):
        healthy = {
            "active_tab": "SUCCÈS", "expected_tab": "SUCCÈS",
            "expected_id": 321, "current_achievement_id": 321,
            "detail_open": True, "detail_stack_active": True,
            "stack_visible": True, "scroll_visible": True,
            "viewport_visible": True, "stack_width": 350, "stack_height": 550,
            "viewport_width": 330, "viewport_height": 530,
            "detail_body_count": 1, "body_visible": True,
            "body_achievement_id": 321, "title": "Test success",
            "expected_title": "Test success", "title_visible": True, "title_hit": True,
        }
        self.assertIsNone(first_achievement_failure(healthy))
        failures = [
            ({"active_tab": "GUIDES"}, "SUCCES_TAB"),
            ({"current_achievement_id": 999}, "selected_achievement_id"),
            ({"detail_open": False}, "detail_open"),
            ({"detail_stack_active": False}, "detail_stack_active"),
            ({"scroll_visible": False}, "detail_visible"),
            ({"viewport_visible": False}, "detail_visible"),
            ({"stack_width": 0}, "detail_geometry"),
            ({"viewport_width": 0}, "detail_geometry"),
            ({"detail_body_count": 0}, "detail_body"),
            ({"body_visible": False}, "detail_body"),
            ({"body_achievement_id": 999}, "detail_body"),
            ({"title": "Wrong detail"}, "detail_title"),
            ({"title_hit": False}, "detail_title"),
        ]
        for alteration, expected in failures:
            with self.subTest(alteration=alteration):
                self.assertEqual(
                    first_achievement_failure({**healthy, **alteration}), expected,
                )
        self.assertEqual(
            verdict([], ["achievement-detail/click-opens-detail"]), "BLOCKED",
        )

    def test_to_fu_squares_cannot_pass_as_legible_qt_capture(self):
        from unittest.mock import patch

        # Rendered fonts can be available or missing on a given CI host. A
        # known tofu renderer (all glyphs identical) must ALWAYS fail.
        with patch("tools.atlas_doctor_lib.doctor_ui_qt._glyph_signature",
                   return_value="identical-missing-glyph"):
            probe = glyph_legibility_probe(self.view)
        self.assertEqual(probe["status"], "FAIL")
        self.assertEqual(probe["reason"], "MISSING_OR_SQUARE_FONT_GLYPHS")
        self.assertTrue(probe["labels"])
        self.assertTrue(all(row["unique_raster_glyphs"] == 1 for row in probe["labels"]))
        witness = UiSession(self.folder, "all")
        witness.scenario = "session"
        witness.check("glyph-rendering", "Font renderer", "Unique glyph pixels", probe,
                      probe["status"] == "PASS", self.view)
        self.assertEqual(verdict(witness.assertions, ["session/glyph-rendering"]), "FAIL")

    def test_real_checkbox_click_cannot_hide_broken_progress_persistence(self):
        from PySide6.QtWidgets import QCheckBox, QVBoxLayout

        page = QWidget()
        layout = QVBoxLayout(page)
        checkbox = QCheckBox("Succès terminé")
        checkbox.setObjectName("AchievementDoneCheck")
        layout.addWidget(checkbox)
        page.resize(400, 200)
        page.show()
        settle()
        try:
            click = click_target(page, checkbox)
            self.assertTrue(click["accessible"], click)
            self.assertTrue(checkbox.isChecked())
            valid = {
                "click": click, "before": False, "expected_before": False,
                "expected_after": True, "after_checkbox": True,
                "after_service": True, "progress_bar": 100,
                "expected_progress_bar": 100,
            }
            self.assertIsNone(completion_transition_failure(valid))
            for change, expected in (
                ({"click": {"accessible": False}}, "BUTTON_NOT_ACCESSIBLE"),
                ({"before": True}, "BASELINE_MISMATCH"),
                ({"after_checkbox": False}, "CHECKBOX_DID_NOT_TOGGLE"),
                ({"after_service": False}, "SERVICE_DID_NOT_PERSIST"),
                ({"progress_bar": 0}, "PROGRESS_BAR_NOT_UPDATED"),
            ):
                with self.subTest(change=change):
                    broken = dict(valid, **change)
                    self.assertEqual(completion_transition_failure(broken), expected)
        finally:
            page.close()
            page.deleteLater()
            settle()

    def test_detailed_success_description_oracle_never_uses_catalog_summary(self):
        class Provider:
            def __init__(self, detail):
                self.detail = detail
                self.calls = []

            def get_detail_by_id(self, achievement_id):
                self.calls.append(achievement_id)
                return self.detail

        full = Provider(SimpleNamespace(id=8518, name="Premier temps",
                                        description="Véritable description détaillée"))
        actual = detailed_achievement_oracle(full, 8518, "Premier temps")
        self.assertEqual(full.calls, [8518])
        self.assertEqual(actual["description"], "Véritable description détaillée")
        self.assertEqual(actual["id"], 8518)
        for bad in (None, SimpleNamespace(id=999, name="Premier temps", description="x"),
                    SimpleNamespace(id=8518, name="Autre nom", description="x")):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(RuntimeError, "Detailed Success"):
                    detailed_achievement_oracle(Provider(bad), 8518, "Premier temps")

    def test_real_qt_success_description_progress_and_checkbox_contrast(self):
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QCheckBox, QLabel, QScrollArea, QVBoxLayout

        page = QWidget()
        page.setStyleSheet(
            "QWidget { background-color: #081113; color: #f5f7f2; }"
        )
        layout = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        content = QFrame()
        content_layout = QVBoxLayout(content)
        values = (
            ("AchievementDetailTitle", "Premier temps"),
            ("AchievementDescription", "Terminer la première partie du tutoriel."),
            ("AchievementProgressText", "Progression • 0 / 2 objectif(s) • 0 %"),
        )
        labels = {}
        for name, text in values:
            label = QLabel(text)
            label.setObjectName(name)
            label.setFont(QFont("Arial", 12))
            label.setWordWrap(False)
            content_layout.addWidget(label)
            labels[name] = label
        check = QCheckBox("Succès terminé")
        check.setObjectName("AchievementDoneCheck")
        check.setFont(QFont("Arial", 12))
        content_layout.addWidget(check)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        view = SimpleNamespace(detail_content=content, detail_scroll=scroll)
        page.resize(720, 400)
        page.show()
        settle()
        try:
            description = values[1][1]
            healthy = achievement_readable_text_observations(
                page, view, expected_description=description,
            )
            self.assertEqual(healthy["status"], "PASS", healthy)
            self.assertEqual(
                set(healthy["statuses"]),
                {"title", "description", "progress", "completion_label"},
            )
            self.assertTrue(all(value == "PASS" for value in healthy["statuses"].values()))

            progress = labels["AchievementProgressText"]
            progress.setStyleSheet("color: #182123")
            progress.repaint()
            settle()
            too_faint = achievement_readable_text_observations(
                page, view, expected_description=description,
            )
            self.assertEqual(too_faint["status"], "FAIL", too_faint)
            self.assertEqual(too_faint["statuses"]["progress"], "FAIL")
            self.assertEqual(too_faint["statuses"]["title"], "PASS")
            progress.setStyleSheet("color: #f5f7f2")
            settle()

            labels["AchievementDescription"].hide()
            settle()
            missing = achievement_readable_text_observations(
                page, view, expected_description=description,
            )
            self.assertEqual(missing["status"], "BLOCKED")
            self.assertEqual(missing["statuses"]["description"], "BLOCKED")
            labels["AchievementDescription"].show()
            settle()

            check.setText("Texte incorrect")
            wrong = achievement_readable_text_observations(
                page, view, expected_description=description,
            )
            self.assertEqual(wrong["status"], "FAIL")
            self.assertEqual(wrong["statuses"]["completion_label"], "FAIL")
        finally:
            page.close()
            page.deleteLater()
            settle()

    def test_real_qt_screenshot_contrast_uses_actual_title_pixels(self):
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QLabel, QVBoxLayout

        page = QWidget()
        page.setStyleSheet("background-color: #081113;")
        layout = QVBoxLayout(page)
        content = QFrame()
        inner = QVBoxLayout(content)
        title = QLabel("Premier temps")
        title.setObjectName("AchievementDetailTitle")
        title.setFont(QFont("Arial", 15))
        # Point-size metrics vary with the Windows runner DPI and installed
        # font fallback. Keep enough real pixels for the contrast oracle to
        # exercise its ink threshold instead of blocking on fixture geometry.
        title.setMinimumHeight(32)
        title.setStyleSheet("color: #f5f7f2; background-color: transparent;")
        inner.addWidget(title)
        inner.addStretch(1)
        layout.addWidget(content)
        view = SimpleNamespace(detail_content=content)
        page.resize(580, 250)
        page.show()
        settle()
        try:
            good = achievement_title_contrast(page, view)
            self.assertEqual(good["status"], "PASS", good)
            self.assertGreaterEqual(good["above_minimum_ratio_pixels"],
                                    good["required_ink_pixels"])
            self.assertEqual(good["widget"], "AchievementDetailTitle")
            self.assertLess(good["crop"][2], title.width())

            title.setStyleSheet("color: #182123; background-color: transparent;")
            title.repaint()
            page.repaint()
            settle()
            bad = achievement_title_contrast(page, view)
            self.assertEqual(bad["status"], "FAIL", bad)
            self.assertIn(bad["reason"],
                          ("TEXT_INVISIBLE_OR_TOO_FAINT", "INSUFFICIENT_PIXEL_CONTRAST"))
        finally:
            page.close()
            page.deleteLater()
            settle()

    def test_real_qt_success_layout_oracle_rejects_clipped_title_and_scroll(self):
        from PySide6.QtWidgets import QCheckBox, QLabel, QScrollArea, QVBoxLayout

        page = QWidget()
        outer = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        content = QFrame()
        inner = QVBoxLayout(content)
        title = QLabel("Succès terminé")
        title.setObjectName("AchievementDetailTitle")
        title.setWordWrap(True)
        inner.addWidget(title)
        checkbox = QCheckBox("Succès terminé")
        checkbox.setObjectName("AchievementDoneCheck")
        inner.addWidget(checkbox)
        inner.addStretch(1)
        scroll.setWidget(content)
        probe_view = SimpleNamespace(detail_scroll=scroll, detail_content=content)
        page.resize(650, 440)
        page.show()
        settle()
        try:
            healthy = achievement_layout_observations(page, probe_view)
            self.assertIsNone(first_achievement_layout_failure(healthy), healthy)
            self.assertEqual(healthy["control_count_in_viewport"], 1)

            title.setFixedHeight(3)
            settle()
            truncated = achievement_layout_observations(page, probe_view)
            self.assertTrue(truncated["title_clipped"])
            self.assertEqual(first_achievement_layout_failure(truncated), "TITLE_CLIPPED")
            title.setMinimumHeight(0)
            title.setMaximumHeight(16777215)
            settle()

            scroll.setWidgetResizable(False)
            content.setMinimumWidth(1500)
            content.resize(1500, 430)
            settle()
            overflow = achievement_layout_observations(page, probe_view)
            self.assertGreater(overflow["horizontal_scroll_max"], 2)
            self.assertEqual(first_achievement_layout_failure(overflow),
                             "HORIZONTAL_OVERFLOW")
        finally:
            page.close()
            page.deleteLater()
            settle()

    def test_success_layout_oracle_refuses_missing_control_or_detected_overlap(self):
        base = {
            "status": "OBSERVED",
            "title_clipped": False,
            "horizontal_overflow": False,
            "control_count_in_viewport": 2,
            "overlaps": [],
            "inaccessible_controls": [],
        }
        self.assertIsNone(first_achievement_layout_failure(base))
        cases = [
            ({"control_count_in_viewport": 0}, "NO_EXPOSED_DETAIL_CONTROLS"),
            ({"overlaps": [{"left": "a", "right": "b"}]}, "BUTTON_OVERLAP"),
            ({"inaccessible_controls": ["AchievementDoneCheck"]}, "BUTTON_OCCLUDED"),
            ({"status": "BLOCKED", "reason": "MISSING_ACHIEVEMENT_TITLE"},
             "MISSING_ACHIEVEMENT_TITLE"),
        ]
        for fault, expected in cases:
            with self.subTest(fault=fault):
                self.assertEqual(first_achievement_layout_failure({**base, **fault}), expected)

    def test_screen_pixels_override_successful_font_metric_checks(self):
        from unittest.mock import patch

        screenshot = {
            "status": "FAIL", "reason": "REPEATED_HOLLOW_SQUARE_GLYPHS",
            "box_count": 730, "failure_threshold": 16,
        }
        with (
            patch("tools.atlas_doctor_lib.doctor_ui_qt._glyph_signature",
                  side_effect=lambda _font, letter: "unique-" + letter),
            patch("tools.atlas_doctor_lib.ui_raster_oracle.detect_replacement_squares",
                  return_value=screenshot),
        ):
            probe = glyph_legibility_probe(self.view)
        self.assertEqual(probe["status"], "FAIL")
        self.assertEqual(probe["reason"], "REPEATED_SCREENSHOT_TOFU")
        self.assertEqual(probe["screenshot_raster"]["total_hollow_boxes"], 730)
        self.assertEqual(probe["screenshot_raster"]["bad_captures"][0]["box_count"], 730)
        judge = UiSession(self.folder, "all")
        judge.scenario = "session"
        judge.check("glyph-rendering", "Actual screen raster", "No repeated tofu",
                    probe, probe["status"] == "PASS", self.view)
        self.assertEqual(verdict(judge.assertions, ["session/glyph-rendering"]), "FAIL")

    def test_stored_bad_png_does_not_get_laundered_by_later_good_screen(self):
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QColor, QImage, QPainter, QPen

        image = QImage(350, 120, QImage.Format_RGB32)
        image.fill(QColor(12, 12, 12))
        painter = QPainter(image)
        painter.setPen(QPen(QColor(220, 220, 220), 1))
        for index in range(25):
            x, y = 7 + (index % 20) * 15, 8 + (index // 20) * 17
            painter.drawRect(QRect(x, y, 7, 7))
        painter.end()
        bad = self.folder / "historic-tofu.png"
        self.assertTrue(image.save(str(bad)))

        good = QImage(350, 120, QImage.Format_RGB32)
        good.fill(QColor(12, 12, 12))
        normal = self.folder / "later-good.png"
        self.assertTrue(good.save(str(normal)))

        observed = glyph_legibility_probe(self.view, screenshots=[bad, normal])
        self.assertEqual(observed["status"], "FAIL")
        self.assertEqual(observed["reason"], "REPEATED_SCREENSHOT_TOFU")
        self.assertEqual(observed["screenshot_raster"]["captures_checked"], 2)
        self.assertEqual(
            [x["capture"] for x in observed["screenshot_raster"]["bad_captures"]],
            ["historic-tofu.png"],
        )
        self.assertGreaterEqual(
            observed["screenshot_raster"]["bad_captures"][0]["box_count"], 20,
        )

    def test_doctor_ui_extra_catalog_evidence_keeps_a_bounded_action_budget(self):
        # The five real scenario union now includes catalog/return screenshots.
        # The cap is raised only enough to finish the validated final checks;
        # runaway sessions must still fail closed.
        session = UiSession(self.folder, "verify")
        session.scenario = "budget-boundary"
        session.step = 127
        evidence = session.snapshot(self.view)
        self.assertEqual(session.step, 128)
        self.assertTrue(all(name.endswith("-tree.json") for name in evidence))
        with self.assertRaisesRegex(RuntimeError, "action budget exceeded"):
            session.snapshot(self.view)

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
