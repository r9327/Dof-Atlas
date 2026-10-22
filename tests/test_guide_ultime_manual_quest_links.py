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
        if int(quest_id) == 654:
            return SimpleNamespace(id=654, name="Deuxième quête")
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
            self.assertEqual(buttons[0].text(), "")
            self.assertFalse(buttons[0].icon().isNull())
            self.assertEqual(buttons[0].toolTip(), "Quête de test")
            self.assertEqual(buttons[0].accessibleName(), "Quête de test")

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


    def test_one_shortcut_per_quest_per_page_even_across_different_maps(self) -> None:
        service = _ManualQuestLinkService()
        service.cards[0]["manual_lines"] = [
            {"kind": "action", "position": "[5,-3]", "text": "Parler au PNJ."},
            {"kind": "action", "position": "[6,-3]", "text": "Continuer la quête."},
        ]
        view = GuideUltimeManualView(service, character_key="character:1")
        view.show()
        QApplication.processEvents()
        try:
            buttons = view.findChildren(QToolButton, "GuideManualQuestInlineButton")
            self.assertEqual(len(buttons), 1)
            self.assertEqual(buttons[0].toolTip(), "Quête de test")
            self.assertFalse(buttons[0].icon().isNull())
        finally:
            view.close()

    def test_multiple_quests_do_not_attach_to_unrelated_actions(self) -> None:
        service = _ManualQuestLinkService()
        service.cards[0]["manual_quest_ids"] = [321, 654]
        service.cards[0]["manual_lines"] = [
            {"kind": "action", "position": "[5,-3]", "text": "Parler au PNJ."},
            {"kind": "action", "position": "[6,-3]", "text": "Accepter la Quête de test."},
            {"kind": "action", "position": "[7,-3]", "text": "Commencer Deuxième quête."},
            {"kind": "action", "position": "[8,-3]", "text": "Poursuivre Deuxième quête."},
        ]
        view = GuideUltimeManualView(service, character_key="character:1")
        view.show()
        QApplication.processEvents()
        try:
            rows = view.findChildren(QFrame, "GuideManualLineRow")
            self.assertEqual(len(rows), 4)
            links = [
                row.findChildren(QToolButton, "GuideManualQuestInlineButton")
                for row in rows
            ]
            self.assertEqual([len(group) for group in links], [0, 1, 1, 0])
            self.assertEqual(
                [button.toolTip() for group in links for button in group],
                ["Quête de test", "Deuxième quête"],
            )
        finally:
            view.close()


if __name__ == "__main__":
    unittest.main()
