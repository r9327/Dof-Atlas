from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QWidget

from app.modules.encyclopedia.services.guide_auto_validation_contract import (
    build_route_auto_validation_contract,
)
from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualCard


class _AchievementProvider:
    def load_all(self):
        return [SimpleNamespace(id=123, name="Circulez")]


class _AchievementProgress:
    def __init__(self) -> None:
        self.completed: set[int] = set()

    def is_achievement_completed(self, _character_key: str, achievement_id: int) -> bool:
        return int(achievement_id) in self.completed

    def set_achievement_completed(
        self,
        _character_key: str,
        achievement_id: int,
        completed: bool,
    ) -> None:
        if completed:
            self.completed.add(int(achievement_id))
        else:
            self.completed.discard(int(achievement_id))


class _Service:
    def __init__(self, card: dict) -> None:
        self.cards = [card]
        self.achievement_progress = _AchievementProgress()
        self.auto_validation_contract = build_route_auto_validation_contract(
            self.cards,
            achievement_provider=_AchievementProvider(),
        )
        self.manual_checked = False

    @staticmethod
    def card_key(_card: dict, _fallback_index: int = 0) -> str:
        return "manual:test:GPS-01"

    @staticmethod
    def card_auto_complete(_character_key: str, _card: dict) -> bool:
        return False

    def page_checked(self, _character_key: str, _card: dict, _index: int) -> bool:
        return self.manual_checked

    def set_page_checked(self, _character_key: str, _card: dict, _index: int, value: bool) -> None:
        self.manual_checked = bool(value)


class GuideUltimeSuccessLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _card() -> dict:
        return {
            "index": 1,
            "manual_source": True,
            "manual_chapter_id": "test",
            "manual_stage_id": "GPS-01",
            "manual_title": "Donjon test",
            "destination": "[1,2] Zone test",
            "manual_lines": [{"kind": "action", "text": "Faire le donjon."}],
            "manual_resource_names": [],
            "manual_success_names": ["Circulez"],
            "manual_stage_data": {"id": "GPS-01"},
        }

    def test_success_checkbox_writes_shared_achievement_progress(self) -> None:
        card = self._card()
        service = _Service(card)
        widget = GuideUltimeManualCard(service, "hero", card, 0)
        checks = widget.findChildren(QCheckBox, "GuideManualSuccessCheck")
        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0].isChecked())

        checks[0].click()
        self.assertEqual(service.achievement_progress.completed, {123})

        checks[0].click()
        self.assertEqual(service.achievement_progress.completed, set())
        widget.close()

    def test_open_success_reuses_existing_entity_navigator(self) -> None:
        card = self._card()
        service = _Service(card)
        parent = QWidget()
        calls: list[tuple[str, int, dict]] = []
        parent.navigate_entity = lambda entity_type, entity_id, **context: calls.append(
            (str(entity_type), int(entity_id), dict(context))
        ) or True
        widget = GuideUltimeManualCard(service, "hero", card, 0, parent=parent)
        buttons = widget.findChildren(QPushButton, "GuideManualSuccessOpen")
        self.assertEqual(len(buttons), 1)

        buttons[0].click()
        self.assertEqual(calls, [("achievement", 123, {"source": "achievement"})])
        widget.close()
        parent.close()


if __name__ == "__main__":
    unittest.main()
