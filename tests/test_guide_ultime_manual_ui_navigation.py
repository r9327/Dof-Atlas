from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualView


class _FakeManualUiService:
    def __init__(self) -> None:
        long_lines = [
            {
                "kind": "action",
                "position": f"[{index},-{index}]",
                "text": f"Action de walkthrough numéro {index} avec suffisamment de texte pour forcer le défilement vertical.",
            }
            for index in range(60)
        ]
        self.cards = [
            {
                "manual_title": "Première fiche",
                "manual_chapter_id": "chapter_one",
                "manual_chapter_label": "Chapitre un",
                "destination": "[1,-1] Zone test",
                "manual_resource_names": [],
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
        self.auto_validation_contract = None

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
        return False

    def set_page_checked(self, _character_key: str, _card: dict, _index: int, _checked: bool) -> None:
        return


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

    def test_header_stays_compact_without_quest_or_dungeon_counters(self) -> None:
        _service, view = self._view()
        try:
            text = view.route_progress_label.text()
            self.assertIn("Fiche 1/2", text)
            self.assertIn("0 %", text)
            self.assertNotIn("Quêtes", text)
            self.assertNotIn("Donjons", text)
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
            self.assertEqual(bar.value(), bar.minimum())
        finally:
            view.close()

    def test_external_progress_follows_current_sheet_without_keeping_old_scroll(self) -> None:
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
            self.assertIn("50 %", view.route_progress_label.text())
        finally:
            view.close()


if __name__ == "__main__":
    unittest.main()
