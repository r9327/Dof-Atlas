from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QToolButton

from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualView


class _QuestProvider:
    def get_quest(self, quest_id: int):
        if int(quest_id) == 321:
            return SimpleNamespace(id=321, name="Quête de test")
        raise KeyError(quest_id)


class _ManualQuestLinkService:
    def __init__(self) -> None:
        self.quest_provider = _QuestProvider()
        self.cards = [
            {
                "manual_title": "Fiche avec quête",
                "manual_stage_id": "TEST-QUEST-LINK",
                "destination": "[5,-3] Zone test",
                "manual_quest_ids": [321, 321],
                "manual_resource_names": [],
                "manual_lines": [
                    {
                        "kind": "action",
                        "position": "[5,-3]",
                        "text": "Parler au PNJ.",
                    }
                ],
            }
        ]
        self.available = True

    def reload_progress(self) -> None:
        return

    def first_incomplete_index(self, _character_key: str) -> int:
        return 0

    def route_sheet_progress(self, _character_key: str) -> tuple[int, int]:
        return 0, 1

    def manual_lines_for_card(self, _character_key: str, card: dict) -> list[dict]:
        return list(card.get("manual_lines", []))

    def card_auto_complete(self, _character_key: str, _card: dict) -> bool:
        return False

    def page_checked(self, _character_key: str, _card: dict, _index: int) -> bool:
        return False

    def set_page_checked(
        self,
        _character_key: str,
        _card: dict,
        _index: int,
        _checked: bool,
    ) -> None:
        return


class GuideUltimeManualQuestLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_canonical_quest_ids_render_one_inline_link_and_open_quests_tab(self) -> None:
        view = GuideUltimeManualView(_ManualQuestLinkService(), character_key="character:1")
        navigations: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def navigate(*args, **kwargs) -> bool:
            navigations.append((args, kwargs))
            return True

        view.navigate_entity = navigate
        view.show()
        QApplication.processEvents()
        try:
            self.assertIsNone(view.findChild(QFrame, "GuideManualQuestSection"))
            self.assertEqual(view.findChildren(QPushButton, "GuideManualQuestLink"), [])
            buttons = view.findChildren(QToolButton, "GuideManualQuestInlineButton")
            self.assertEqual(len(buttons), 1)
            self.assertEqual(buttons[0].text(), "↗")
            self.assertEqual(buttons[0].toolTip(), "Quête de test")

            buttons[0].click()
            QApplication.processEvents()

            self.assertEqual(
                navigations,
                [
                    (
                        ("quest", 321),
                        {
                            "source": "guide_gps",
                            "guide_id": "guide_complet",
                            "guide_stage_id": "TEST-QUEST-LINK",
                            "guide_index": 0,
                        },
                    )
                ],
            )
        finally:
            view.close()


if __name__ == "__main__":
    unittest.main()
