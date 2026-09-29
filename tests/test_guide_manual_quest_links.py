from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QToolButton

from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualCard


QUEST_NAME = "Les principes d'Archie m'aident"


class _QuestProvider:
    def get_quest(self, quest_id: int):
        if int(quest_id) == 1958:
            return SimpleNamespace(id=1958, name=QUEST_NAME)
        return None


class _Service:
    quest_provider = _QuestProvider()

    def manual_sections_for_card(self, _character_key, _card):
        return {
            "now": [
                {
                    "position": "[1, 2]",
                    "text": "Première action de la quête",
                    "kind": "action",
                    "quest_names": [QUEST_NAME],
                },
                {
                    "position": "[1, 2]",
                    "text": "Deuxième action de la même quête",
                    "kind": "action",
                    "quest_names": [QUEST_NAME],
                },
                {
                    "position": "[2, 2]",
                    "text": "Même quête sur une autre map",
                    "kind": "action",
                    "quest_names": [QUEST_NAME],
                },
            ]
        }


class GuideManualQuestLinksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_same_quest_same_map_only_shows_first_inline_link(self) -> None:
        card = {
            "manual_stage_id": "stage-1",
            "destination": "[1, 2]",
            "manual_title": "Étape test",
            "manual_quest_ids": [1958],
            "manual_quest_names": [QUEST_NAME],
        }
        widget = GuideUltimeManualCard(_Service(), "", card, 7)

        self.assertIsNone(widget.findChild(QFrame, "GuideManualQuestSection"))
        buttons = widget.findChildren(QToolButton, "GuideManualQuestInlineButton")
        self.assertEqual(len(buttons), 2)
        self.assertTrue(all(button.text() == "↗" for button in buttons))
        self.assertTrue(all(button.width() == 18 and button.height() == 18 for button in buttons))
        self.assertTrue(all(button.toolTip() == QUEST_NAME for button in buttons))

        emitted: list[tuple[int, str, int]] = []
        widget.questRequested.connect(
            lambda quest_id, stage_id, index: emitted.append((quest_id, stage_id, index))
        )
        buttons[0].click()
        self.assertEqual(emitted, [(1958, "stage-1", 7)])


if __name__ == "__main__":
    unittest.main()
