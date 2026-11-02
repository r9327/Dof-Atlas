"""Lossless structured-action contract for the single shared Guide card projector."""
from __future__ import annotations

import copy
import unittest

from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
    project_ganymede_authored_cards,
)


class GanymedeAuthoredProjectionTests(unittest.TestCase):
    @staticmethod
    def _source_steps() -> tuple[dict, ...]:
        return ({
            "source_step_number": 1,
            "title": "Première étape",
            "instructions": "Préparer la traversée avant le combat.",
            "actions": [
                {"kind": "travel", "text": "Aller au port", "coordinates": [2, -3]},
                {"kind": "prepare", "text": "Rassembler les objets",
                 "items": [{"name": "Potion de voyage", "quantity": 12,
                            "acquisition": "buy"}],
                 "copy_values": ["Potion de voyage", "Nom exact à copier"]},
                {"kind": "fight", "text": "Vaincre les gardiens"},
            ],
        },)

    def test_preserves_action_order_positions_items_quantities_and_copy_values(self):
        steps = self._source_steps()
        original = copy.deepcopy(steps)
        cards = project_ganymede_authored_cards(2219, "Guide exemple", steps)
        self.assertEqual(len(cards), 1)
        card = cards[0]
        rows = card["manual_lines"]
        self.assertEqual(len(rows), 4)
        self.assertIs(card["manual_sections"]["now"], rows)
        self.assertEqual([row["kind"] for row in rows[1:]],
                         ["action", "action", "combat"])
        self.assertEqual([row["position"] for row in rows[1:]],
                         ["[2,-3]", "", ""])
        self.assertEqual(rows[2]["items"], steps[0]["actions"][1]["items"])
        self.assertEqual(rows[2]["copy_values"],
                         steps[0]["actions"][1]["copy_values"])
        self.assertEqual(card["manual_resource_names"], ["Potion de voyage"])
        self.assertEqual(card["manual_stage_id"], "ganymede_2219_step_0001")
        self.assertIs(card["auto_completion_allowed"], False)
        # Projecting must not mutate the imported reference data.
        rows[2]["items"][0]["quantity"] = 999
        rows[2]["copy_values"].append("Autre valeur")
        self.assertEqual(steps, original)

    def test_rejects_malformed_explicit_copy_values(self):
        for invalid in ("une chaîne", [""], [42], ["x" * 257]):
            with self.subTest(invalid=invalid):
                steps = self._source_steps()
                steps[0]["actions"][1]["copy_values"] = invalid
                with self.assertRaisesRegex(ValueError, "Invalid authored copy values"):
                    project_ganymede_authored_cards(2219, "Guide exemple", steps)

    def test_rejects_malformed_structured_items(self):
        for invalid in (None, {"name": "Potion"}, ["Potion"]):
            with self.subTest(invalid=invalid):
                steps = self._source_steps()
                steps[0]["actions"][1]["items"] = invalid
                with self.assertRaisesRegex(ValueError, "Invalid structured items?"):
                    project_ganymede_authored_cards(2219, "Guide exemple", steps)


if __name__ == "__main__":
    unittest.main()
