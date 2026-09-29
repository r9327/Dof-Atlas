from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QPushButton, QToolButton

from app.modules.encyclopedia.views.guide_ultime_manual_view import (
    GuideUltimeManualCard,
    GuideUltimeManualView,
)


class _FakeQuest:
    def __init__(self, quest_id: int, name: str) -> None:
        self.id = int(quest_id)
        self.name = name


class _FakeQuestProvider:
    def __init__(self) -> None:
        self.by_id = {
            101: _FakeQuest(101, "Quête canonique test"),
        }

    def get_quest(self, quest_id: int):
        return self.by_id.get(int(quest_id))


class _FakeManualUiService:
    def __init__(self) -> None:
        self.quest_provider = _FakeQuestProvider()
        long_lines = [
            {
                "kind": "action",
                "position": f"[{index},-{index}]",
                "text": (
                    f"Action de walkthrough numéro {index} avec suffisamment de texte "
                    "pour forcer le défilement vertical."
                ),
            }
            for index in range(60)
        ]
        self.cards = [
            {
                "manual_title": "Première fiche",
                "manual_stage_id": "TEST-01",
                "manual_chapter_id": "chapter_one",
                "manual_chapter_label": "Chapitre un",
                "destination": "[1,-1] Zone test",
                "manual_resource_names": [],
                "manual_quest_ids": [101],
                "manual_lines": list(long_lines),
            },
            {
                "manual_title": "Deuxième fiche",
                "manual_chapter_id": "chapter_two",
                "manual_chapter_label": "Chapitre deux",
                "destination": "[2,-2] Zone test",
                "manual_resource_names": [],
                "manual_lines": list(long_lines),
            },
        ]
        self.available = True
        self.active_index = 0
        self.completed = 0
        self.page_state = False
        self.page_updates: list[tuple[int, bool]] = []
        self.line_checks: set[tuple[str, str]] = set()
        self.line_updates: list[tuple[str, str, bool]] = []

    def reload_progress(self) -> None:
        return

    def first_incomplete_index(self, _character_key: str) -> int:
        return self.active_index

    def route_sheet_progress(self, _character_key: str) -> tuple[int, int]:
        return self.completed, len(self.cards)

    def manual_lines_for_card(self, _character_key: str, card: dict) -> list[dict]:
        return list(card.get("manual_lines", []))

    def card_auto_complete(self, _character_key: str, _card: dict) -> bool:
        return False

    def page_checked(self, _character_key: str, _card: dict, _index: int) -> bool:
        return self.page_state

    def set_page_checked(
        self,
        _character_key: str,
        _card: dict,
        index: int,
        checked: bool,
    ) -> None:
        self.page_state = bool(checked)
        self.page_updates.append((int(index), bool(checked)))

    def checklist_checked(
        self,
        _character_key: str,
        _card: dict,
        section: str,
        row: dict,
        _index: int,
    ) -> bool:
        return (str(section), str(row.get("text") or "")) in self.line_checks

    def set_checklist_checked(
        self,
        _character_key: str,
        _card: dict,
        section: str,
        row: dict,
        _index: int,
        checked: bool,
    ) -> None:
        key = (str(section), str(row.get("text") or ""))
        if checked:
            self.line_checks.add(key)
        else:
            self.line_checks.discard(key)
        self.line_updates.append((key[0], key[1], bool(checked)))


class GuideUltimeManualUiNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _view(self) -> tuple[_FakeManualUiService, GuideUltimeManualView]:
        service = _FakeManualUiService()
        view = GuideUltimeManualView(service, character_key="character:1")
        view.resize(560, 320)
        view.show()
        QApplication.processEvents()
        return service, view

    def test_progress_header_is_compact_and_page_is_separate_from_navigation(self) -> None:
        _service, view = self._view()
        try:
            self.assertEqual(view.route_progress_label.text(), "0 %")
            self.assertEqual(view.nav_page_label.text(), "Page 1 / 2")
            self.assertEqual(view.validation_check.text(), "Validation")
            self.assertEqual(view.route_lock_check.text(), "Verrouiller")
            self.assertIn("Validation", view.route_legend.text())
            self.assertIsNot(
                view.nav_page_label.parentWidget(),
                view.prev_button.parentWidget(),
            )
            self.assertNotIn("Quêtes", view.route_progress_label.text())
            self.assertNotIn("Donjons", view.route_progress_label.text())
        finally:
            view.close()

    def test_progress_bar_lock_blocks_only_direct_bar_jumps(self) -> None:
        _service, view = self._view()
        try:
            view.route_lock_check.setChecked(True)
            view._jump_from_progress(1.0)
            self.assertEqual(view.view_index, 0)

            view.route_lock_check.setChecked(False)
            view._jump_from_progress(1.0)
            self.assertEqual(view.view_index, 1)
        finally:
            view.close()

    def test_obsolete_breadcrumb_destination_and_success_blocks_are_not_rendered(self) -> None:
        _service, view = self._view()
        try:
            object_names = {
                frame.objectName()
                for frame in view.findChildren(QFrame)
                if frame.objectName()
            }
            self.assertNotIn("GuideBreadcrumb", object_names)
            self.assertNotIn("GuideManualDestinationSection", object_names)
            self.assertNotIn("GuideManualSuccessBlock", object_names)
            self.assertNotIn("GuideManualQuestSection", object_names)
        finally:
            view.close()

    def test_inline_quest_link_opens_quests_tab_with_stable_return_context(self) -> None:
        _service, view = self._view()
        calls: list[tuple[tuple, dict]] = []
        view.navigate_entity = lambda *args, **kwargs: calls.append((args, kwargs)) or True
        try:
            self.assertFalse(
                any(
                    candidate.objectName() == "GuideManualQuestButton"
                    for candidate in view.findChildren(QPushButton)
                )
            )
            button = next(
                candidate
                for candidate in view.findChildren(QToolButton)
                if candidate.objectName() == "GuideManualQuestInlineButton"
            )
            self.assertEqual(button.text(), "↗")
            self.assertEqual((button.width(), button.height()), (18, 18))
            self.assertTrue(button.autoRaise())
            self.assertIn("Quête canonique test", button.toolTip())
            self.assertIn("fiche canonique", button.toolTip())

            button.click()
            QApplication.processEvents()

            self.assertEqual(calls[0][0], ("quest", 101))
            self.assertEqual(calls[0][1]["source"], "guide_gps")
            self.assertEqual(calls[0][1]["guide_id"], "guide_complet")
            self.assertEqual(calls[0][1]["guide_stage_id"], "TEST-01")
            self.assertEqual(calls[0][1]["guide_index"], 0)
        finally:
            view.close()

    def test_inline_quest_link_is_shown_once_per_quest_and_map(self) -> None:
        service = _FakeManualUiService()
        card = {
            "manual_title": "Déduplication quête/map",
            "manual_stage_id": "TEST-DEDUPE",
            "destination": "[5,-7] Zone test",
            "manual_resource_names": [],
            "manual_quest_ids": [101],
            "manual_lines": [
                {
                    "kind": "action",
                    "position": "[5,-7] — Premier objectif",
                    "text": "Première action de la quête sur cette map.",
                },
                {
                    "kind": "action",
                    "position": "[5,-7] — Deuxième objectif",
                    "text": "Deuxième action de la même quête sur cette map.",
                },
                {
                    "kind": "action",
                    "position": "[6,-7] — Map suivante",
                    "text": "La quête continue sur une autre map.",
                },
            ],
        }
        widget = GuideUltimeManualCard(service, "character:1", card, 0)
        widget.show()
        QApplication.processEvents()
        try:
            buttons = [
                candidate
                for candidate in widget.findChildren(QToolButton)
                if candidate.objectName() == "GuideManualQuestInlineButton"
            ]
            self.assertEqual(len(buttons), 2)
            self.assertTrue(all(button.text() == "↗" for button in buttons))
        finally:
            widget.close()

    def test_prepare_drops_only_exact_actions_already_done_now(self) -> None:
        duplicate_prepare = {
            "kind": "warning",
            "position": "[1,-2]",
            "text": "Prendre la clé.",
        }
        duplicate_now = {
            "kind": "action",
            "position": " [1,-2] ",
            "text": "  PRENDRE LA CLÉ. ",
        }
        distinct_prepare = {
            "kind": "warning",
            "position": "",
            "text": "Prépare 4 × Potion.",
        }
        result = GuideUltimeManualCard._without_prepare_duplicates(
            {
                "prepare": [duplicate_prepare, distinct_prepare],
                "now": [duplicate_now],
                "boss": [],
            }
        )

        self.assertEqual(result["prepare"], [distinct_prepare])
        self.assertEqual(result["now"], [duplicate_now])
        self.assertEqual(result["boss"], [])

    def test_manual_lines_are_checkable_without_validating_page(self) -> None:
        service, view = self._view()
        try:
            checks = [
                check
                for check in view.findChildren(QCheckBox)
                if check.objectName() == "GuideManualLineCheck"
            ]
            self.assertGreater(len(checks), 0)
            self.assertFalse(service.page_state)

            checks[0].setChecked(True)
            QApplication.processEvents()

            self.assertTrue(service.line_updates)
            self.assertTrue(service.line_updates[-1][2])
            self.assertFalse(service.page_state)
            self.assertEqual(service.page_updates, [])
        finally:
            view.close()

    def test_position_is_bold_in_manual_action_html(self) -> None:
        rendered = GuideUltimeManualCard._format_line_html(
            "• ",
            "[1,-2]",
            "Parler au PNJ.",
            [],
            [],
        )
        self.assertIn("<b>[1,-2]</b>", rendered)

    def test_validation_control_persists_manual_page_state(self) -> None:
        service, view = self._view()
        try:
            self.assertFalse(view.validation_check.isChecked())
            self.assertTrue(view.validation_check.isEnabled())

            view.validation_check.setChecked(True)
            QApplication.processEvents()

            self.assertTrue(service.page_state)
            self.assertEqual(service.page_updates, [(0, True)])
            self.assertTrue(view.validation_check.isChecked())
        finally:
            view.close()

    def test_next_sheet_always_starts_at_top(self) -> None:
        _service, view = self._view()
        try:
            bar = view.scroll.verticalScrollBar()
            self.assertGreater(bar.maximum(), 0)
            bar.setValue(bar.maximum())
            self.assertGreater(bar.value(), 0)

            view.navigate_relative(1)
            QApplication.processEvents()

            self.assertEqual(view.view_index, 1)
            self.assertEqual(view.nav_page_label.text(), "Page 2 / 2")
            self.assertEqual(bar.value(), bar.minimum())
        finally:
            view.close()

    def test_external_progress_follows_active_sheet_and_resets_scroll(self) -> None:
        service, view = self._view()
        try:
            bar = view.scroll.verticalScrollBar()
            self.assertGreater(bar.maximum(), 0)
            bar.setValue(bar.maximum())

            service.active_index = 1
            service.completed = 1
            view.refresh_external_progress()
            QApplication.processEvents()

            self.assertEqual(view.active_index, 1)
            self.assertEqual(view.view_index, 1)
            self.assertEqual(bar.value(), bar.minimum())
            self.assertEqual(view.route_progress_label.text(), "50 %")
            self.assertEqual(view.nav_page_label.text(), "Page 2 / 2")
        finally:
            view.close()

    def test_external_progress_does_not_yank_user_back_from_history(self) -> None:
        service, view = self._view()
        try:
            view.navigate_relative(1)
            QApplication.processEvents()
            self.assertEqual(view.view_index, 1)

            service.active_index = 0
            service.completed = 0
            view.refresh_external_progress()
            QApplication.processEvents()

            self.assertEqual(view.active_index, 0)
            self.assertEqual(view.view_index, 1)
        finally:
            view.close()

    def test_same_character_reentry_resets_history_to_active_sheet(self) -> None:
        service, view = self._view()
        try:
            view.navigate_relative(1)
            QApplication.processEvents()
            self.assertEqual(view.view_index, 1)

            service.active_index = 0
            view.set_character_key("character:1")
            QApplication.processEvents()

            self.assertEqual(view.active_index, 0)
            self.assertEqual(view.view_index, 0)
            self.assertEqual(view.nav_page_label.text(), "Page 1 / 2")
        finally:
            view.close()


if __name__ == "__main__":
    unittest.main()
