from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_preparation_model import (
    aggregate_remaining, card_claims, category_for,
)


class GuidePreparationModelTests(unittest.TestCase):
    def test_structured_and_textual_complement_without_mirror_double_count(self):
        card = {
            "manual_stage_id": "stage:1",
            "a_preparer": [
                {"item_id": 101, "name": "Potion de rappel", "quantity": 3,
                 "_source_field": "quest_required_items"},
            ],
            "manual_sections": {"prepare": [
                {"text": "Prépare 3 × Potion de rappel."},
                {"text": "Prépare 2 × Clef du donjon."},
            ]},
        }
        claims = card_claims(card)
        self.assertEqual(len(claims), 2)
        self.assertEqual([(c.name, c.quantity) for c in claims], [
            ("Potion de rappel", 3), ("Clef du donjon", 2),
        ])
        self.assertEqual(claims[0].item_id, 101)

    def test_soul_stones_keys_and_professions_are_exposed(self):
        card = {
            "manual_stage_id": "stage:2",
            "a_preparer": [
                {"name": "Pierre d'âme parfaite", "quantity": 4},
                {"name": "Clef du donjon Royalmouth", "quantity": 1},
            ],
            "profession_gates": [{"name": "Alchimiste niveau 50"}],
        }
        found = card_claims(card)
        self.assertEqual([row.category for row in found], [
            "Pierres d'âme", "Clefs", "Métiers",
        ])
        self.assertIsNone(found[-1].quantity)

    def test_duplicates_are_not_false_purchases(self):
        card = {
            "manual_stage_id": "stage:3",
            "a_preparer": [
                {"name": "Potion", "quantity": 2},
                {"name": "Potion", "quantity": 2},
                {"name": "Potion", "quantity": 2, "source_step_id": "different-use"},
            ],
        }
        claims = card_claims(card)
        self.assertEqual(len(claims), 2)

    def test_sum_only_explicit_consumptions_and_max_reusables(self):
        cards = [
            {"manual_stage_id": "one", "a_preparer": [
                {"item_id": 9, "name": "Potion A", "quantity": 2, "consumable": True},
                {"item_id": 11, "name": "Objet B", "quantity": 1, "reusable": True},
            ]},
            {"manual_stage_id": "two", "a_preparer": [
                {"item_id": 9, "name": "Potion A", "quantity": 3, "consumable": True},
                {"item_id": 11, "name": "Objet B", "quantity": 4, "reusable": True},
            ]},
        ]
        rows = aggregate_remaining((card, False) for card in cards)
        by_id = {need.item_id: need for need in rows}
        self.assertEqual((by_id[9].quantity, by_id[9].confidence),
                         (5, "additive_consumption"))
        self.assertEqual((by_id[11].quantity, by_id[11].confidence),
                         (4, "reusable_maximum"))
        self.assertEqual(by_id[11].claim_count, 2)
        self.assertEqual(len(by_id[11].sources), 2)

    def test_ambiguous_consumption_and_missing_quantity_are_unknown(self):
        cards = [
            {"manual_stage_id": "one", "a_preparer": [
                {"name": "Objet rare", "quantity": 2},
                {"name": "Potion inconnue"},
            ]},
            {"manual_stage_id": "two", "a_preparer": [
                {"name": "Objet rare", "quantity": 3},
            ]},
        ]
        data = {row.name: row for row in aggregate_remaining((c, False) for c in cards)}
        self.assertIsNone(data["Objet rare"].quantity)
        self.assertEqual(data["Objet rare"].confidence, "multiple_uses_ambiguous")
        self.assertIsNone(data["Potion inconnue"].quantity)
        self.assertEqual(data["Potion inconnue"].confidence, "quantity_unverified")

    def test_completed_stages_excluded_from_remaining(self):
        first = {"manual_stage_id": "one", "a_preparer": [
            {"name": "Potion", "quantity": 2, "consumable": True},
        ]}
        second = {"manual_stage_id": "two", "a_preparer": [
            {"name": "Potion", "quantity": 4, "consumable": True},
        ]}
        rows = aggregate_remaining(((first, True), (second, False)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].quantity, 4)

    def test_unverified_candidates_do_not_claim_possession(self):
        card = {"manual_stage_id": "stage:4", "source_action_candidates": [
            {"kind": "prepare_object", "object_id": 361, "label": "Cawotte"}
        ]}
        self.assertEqual(card_claims(card), ())
        self.assertEqual(aggregate_remaining(((card, False),)), ())

    def test_unknown_quantity_is_not_faked_as_one(self):
        rows = card_claims({"a_preparer": [
            {"name": "Pierre d'âme", "quantity": 0},
            {"name": "Potion", "quantity": True},
            {"name": "Clef", "quantity": "unknown"},
        ]})
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row.quantity is None for row in rows))

    def test_authored_incarnam_resource_plan_reaches_cards(self):
        """Use real retained chapter data, not an invented synthetic item."""
        from app.modules.encyclopedia.services.guide_ultime_manual_runtime_core import (
            GuideUltimeManualRuntimeService,
        )
        root = Path(__file__).resolve().parents[1]
        chapter = json.loads((
            root / "data/routes/guide_ultime_manual/incarnam_v1.json"
        ).read_text(encoding="utf-8"))
        authored = chapter["resource_plan"]["collect_before_leaving_incarnam"]
        self.assertGreater(len(authored), 10)
        schedule = GuideUltimeManualRuntimeService._chapter_preparation_schedule(
            chapter, chapter["stages"],
        )
        self.assertIn(0, schedule)
        card = {
            "manual_stage_id": chapter["stages"][0]["id"],
            "a_preparer": schedule[0],
        }
        claims = card_claims(card)
        quantities = {claim.name: claim.quantity for claim in claims}
        self.assertEqual(quantities["Blé"], 18)
        self.assertEqual(quantities["Goujon"], 8)
        self.assertEqual(quantities["Relique d'Incarnam"], 3)
        self.assertGreaterEqual(len(quantities), len(authored))

    def test_nested_authored_resources_not_confused_with_candidate_actions(self):
        card = {"manual_stage_id": "fixture", "a_preparer": [{
            "_source_field": "resource_plan",
            "collect_before_leaving": [
                {"resource": "Ortie", "quantity": 13},
                {"item": "Fer", "quantity": 10},
            ],
            "notes": [{"policy": "Aucun achat forcé"}],
        }], "source_action_candidates": [{
            "label": "Objet Ganymède", "quantity": 999, "kind": "prepare_object",
        }]}
        claims = card_claims(card)
        self.assertEqual([(c.name, c.quantity) for c in claims],
                         [("Ortie", 13), ("Fer", 10)])
        self.assertTrue(all(c.source == "resource_plan" for c in claims))

    def test_missing_identity_never_uses_slot(self):
        rows = card_claims({"a_preparer": [
            {"name": "Potion de Rappel", "quantity": 1, "slot": 7},
        ]})
        self.assertEqual(rows[0].identity, "name:potion de rappel")
        self.assertEqual(category_for("Pierre d’âme parfaite"), "Pierres d'âme")


if __name__ == "__main__":
    unittest.main()
