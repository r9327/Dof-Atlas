from __future__ import annotations

import unittest
from types import SimpleNamespace
from urllib.parse import quote

from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualCard


class _QuestProvider:
    def guide_evidence(self, quest_id: int):
        if int(quest_id) != 42:
            return {}
        return {
            "items": [
                {"item_id": 123, "name": "Bière du Chabrulé", "quantity": 1},
                {"item_id": 456, "name": "Breuvage d'Erazal", "quantity": 3},
            ],
            "combats": [],
        }

    def get_quest(self, _quest_id: int):
        raise AssertionError("Guide rendering must not hydrate rich Quest details")


class GuideUltimeManualClickableEntityTests(unittest.TestCase):
    def test_canonical_and_quest_items_are_all_clickable_candidates(self) -> None:
        service = SimpleNamespace(quest_provider=_QuestProvider())
        card = {
            "manual_resource_names": ["Trèfle à 5 feuilles", "Bière du Chabrulé"],
            "manual_quest_ids": [42],
        }

        names = GuideUltimeManualCard._clickable_resource_names(service, card)

        self.assertIn("Trèfle à 5 feuilles", names)
        self.assertIn("Bière du Chabrulé", names)
        self.assertIn("Breuvage d'Erazal", names)
        self.assertEqual(names.count("Bière du Chabrulé"), 1)

    def test_each_coordinate_and_item_gets_its_own_copy_link(self) -> None:
        rendered = GuideUltimeManualCard._format_line_html(
            "• ",
            "[-12, 34] → [5,-6]",
            "Prends 3 Bières du Chabrulé puis garde le Breuvage d'Erazal.",
            [],
            ["Bière du Chabrulé", "Breuvage d'Erazal"],
        )
        beer_href = quote("Bière du Chabrulé", safe="")
        brew_href = quote("Breuvage d'Erazal", safe="")

        self.assertIn('href="travel-copy:-12,34"', rendered)
        self.assertIn('href="travel-copy:5,-6"', rendered)
        self.assertIn(f'href="item-copy:{beer_href}"', rendered)
        self.assertIn(f'href="item-copy:{brew_href}"', rendered)

    def test_item_link_copies_only_canonical_item_name(self) -> None:
        encoded = quote("Bière du Chabrulé", safe="")
        self.assertEqual(
            GuideUltimeManualCard._copy_text_for_link(f"item-copy:{encoded}"),
            "Bière du Chabrulé",
        )

    def test_coordinate_link_builds_travel_command(self) -> None:
        self.assertEqual(
            GuideUltimeManualCard._copy_text_for_link("travel-copy:-12,34"),
            "/travel -12,34",
        )
        self.assertIsNone(
            GuideUltimeManualCard._copy_text_for_link("travel-copy:-12, nope")
        )


if __name__ == "__main__":
    unittest.main()
