from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QPushButton

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
            self.assertIsNot(
                view.nav_page_label.parentWidget(),
                view.prev_button.parentWidget(),
            )
            self.assertNotIn("Quêtes", view.route_progress_label.text())
            self.assertNotIn("Donjons", view.route_progress_label.text())
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
        finally:
            view.close()

    def test_canonical_quest_row_opens_quests_tab_with_stable_return_context(self) -> None:
        _service, view = self._view()
        calls: list[tuple[tuple, dict]] = []
        view.navigate_entity = lambda *args, **kwargs: calls.append((args, kwargs)) or True
        try:
            button = next(
                candidate
                for candidate in view.findChildren(QPushButton)
                if candidate.objectName() == "GuideManualQuestButton"
            )
            self.assertEqual(button.text(), "Quête canonique test")
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


if __name__ == "__main__":
    unittest.main()
