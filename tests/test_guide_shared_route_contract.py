"""Source-route adapter contracts for the existing shared Guide UI in main."""
from __future__ import annotations

import copy
import unittest

from app.modules.encyclopedia.services.guide_shared_route_contract import (
    GuideRouteContractError,
    project_authorized_guide,
)


def sample() -> dict:
    return {
        "guide_id": 2219, "title": "Guide exemple",
        "steps": [
            {"source_step_id": 42, "title": "Parler au PNJ",
             "coordinates": [-12, 7], "quest_ids": [100],
             "prerequisites": [{"item": "Ressource", "quantity": 3}],
             "actions": [
                 {"action_id": "a", "kind": "travel", "text": "Aller en [-12,7]",
                  "coordinates": [-12, 7]},
                 {"action_id": "b", "kind": "talk", "text": "Parler au PNJ Exemple",
                  "npc": "PNJ Exemple", "dialogue_choice": "Réponse B"},
                 {"action_id": "c", "kind": "item", "text": "Acheter Ressource",
                  "items": [{"name": "Ressource", "quantity": 3}]},
                 {"action_id": "d", "kind": "combat", "text": "Vaincre Monstre",
                  "monsters": [{"name": "Monstre", "quantity": 2}]},
                 {"action_id": "e", "kind": "warning", "text": "Avant de partir, conserver Ressource"},
             ]},
            {"source_step_id": "quest-2", "title": "Suite",
             "actions": [{"action_id": "talk2", "kind": "talk", "text": "Parler au PNJ B"}]},
        ],
    }


class TestSharedRouteContract(unittest.TestCase):
    def test_uses_existing_shared_card_schema_no_ui_fork(self):
        source = sample()
        before = copy.deepcopy(source)
        route = project_authorized_guide(source)
        self.assertEqual(source, before)
        self.assertEqual(route["schema_version"], 5)
        self.assertEqual(route["route_model"], "authored_step_actions")
        self.assertEqual(route["source_compliance"], "NOT_CERTIFIED")
        cards = route["steps"]
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]["manual_stage_id"], "source:2219:42")
        self.assertEqual(cards[1]["manual_stage_id"], "source:2219:quest-2")
        self.assertEqual(cards[0]["manual_chapter_label"], "Guide exemple")
        self.assertEqual(cards[0]["manual_route_position"], "-12,7")
        self.assertEqual(cards[0]["manual_resource_names"], ["Ressource"])
        self.assertEqual(cards[0]["hard_runtime_gates"], source["steps"][0]["prerequisites"])
        self.assertEqual(cards[0]["manual_quest_ids"], [100])

    def test_preserves_all_source_actions_and_metadata(self):
        step = sample()["steps"][0]
        card = project_authorized_guide({"guide_id": "g", "title": "T", "steps": [step]})["steps"][0]
        self.assertEqual(
            [row["source_action_id"] for row in card["manual_lines"]],
            [a["action_id"] for a in step["actions"]],
        )
        self.assertEqual(card["manual_sections"]["before_leave"][0]["text"],
                         "Avant de partir, conserver Ressource")
        # The shared reader only turns bracketed coordinates into clickable
        # travel-copy:/travel links; the route identity remains raw x,y.
        self.assertEqual(card["manual_sections"]["now"][0]["position"], "[-12,7]")
        self.assertEqual(card["manual_route_position"], "-12,7")
        self.assertEqual(card["manual_sections"]["now"][3]["kind"], "combat")
        self.assertEqual(card["manual_sections"]["now"][2]["source_action"]["items"][0]["quantity"], 3)
        self.assertEqual(card["manual_sections"]["now"][1]["source_action"]["dialogue_choice"],
                         "Réponse B")
        self.assertEqual(card["manual_runtime_metadata"]["source_step"], step)

    def test_stage_identity_does_not_shift_when_step_inserted(self):
        initial = sample()
        before = project_authorized_guide(initial)["steps"][1]["manual_stage_id"]
        initial["steps"].insert(1, {
            "source_step_id": "added", "title": "Nouveau",
            "actions": [{"action_id": "n", "kind": "talk", "text": "Nouveau contenu"}],
        })
        after = project_authorized_guide(initial)["steps"][2]["manual_stage_id"]
        self.assertEqual(before, after)

    def test_each_guide_has_disjoint_progression_identity(self):
        a = sample()
        b = copy.deepcopy(a)
        b["guide_id"] = 2220
        aa = project_authorized_guide(a)
        bb = project_authorized_guide(b)
        self.assertNotEqual(aa["id"], bb["id"])
        self.assertNotEqual(aa["steps"][0]["manual_stage_id"], bb["steps"][0]["manual_stage_id"])

    def test_fail_closed_unknown_action_and_reordering(self):
        bad = sample()
        bad["steps"][0]["actions"][0]["kind"] = "teleport_unknown"
        with self.assertRaisesRegex(GuideRouteContractError, "unsupported"):
            project_authorized_guide(bad)
        bad = sample()
        bad["steps"][0]["actions"][3]["section"] = "now"
        bad["steps"][0]["actions"][4]["section"] = "opportunity"
        bad["steps"][0]["actions"].append(
            {"action_id": "late", "kind": "talk", "text": "Après", "section": "now"}
        )
        with self.assertRaisesRegex(GuideRouteContractError, "reorder"):
            project_authorized_guide(bad)

    def test_duplicate_source_step_and_action_ids_rejected(self):
        bad = sample()
        bad["steps"][1]["source_step_id"] = 42
        with self.assertRaisesRegex(GuideRouteContractError, "duplicate source_step_id"):
            project_authorized_guide(bad)
        bad = sample()
        bad["steps"][0]["actions"][1]["action_id"] = "a"
        with self.assertRaisesRegex(GuideRouteContractError, "duplicate action_id"):
            project_authorized_guide(bad)

    def test_invalid_coordinate_does_not_fabricate_travel(self):
        for raw in ("12,13", [True, 3], [1], [1, 2, 3]):
            bad = sample()
            bad["steps"][0]["actions"][0]["coordinates"] = raw
            with self.subTest(raw=raw), self.assertRaises(GuideRouteContractError):
                project_authorized_guide(bad)

    def test_missing_travel_and_combat_evidence_is_blocked(self):
        missing_position = sample()
        missing_position["steps"][0].pop("coordinates")
        missing_position["steps"][0]["actions"][0].pop("coordinates")
        with self.assertRaisesRegex(GuideRouteContractError, "verified coordinates"):
            project_authorized_guide(missing_position)

        missing_monster = sample()
        missing_monster["steps"][0]["actions"][3].pop("monsters")
        with self.assertRaisesRegex(GuideRouteContractError, "structured monsters"):
            project_authorized_guide(missing_monster)

    def test_bad_quest_id_and_ambiguous_identity_rejected(self):
        bad = sample()
        bad["steps"][0]["quest_ids"] = [True]
        with self.assertRaisesRegex(GuideRouteContractError, "positive integer IDs"):
            project_authorized_guide(bad)
        bad = sample()
        bad["guide_id"] = "a:b"
        with self.assertRaisesRegex(GuideRouteContractError, "unsafe"):
            project_authorized_guide(bad)

    def test_invalid_quantity_and_missing_text(self):
        for quantity in (0, -2, True, 1.5, "2", None):
            bad = sample()
            bad["steps"][0]["actions"][2]["items"][0]["quantity"] = quantity
            with self.subTest(quantity=quantity), self.assertRaises(GuideRouteContractError):
                project_authorized_guide(bad)
        bad = sample()
        bad["steps"][0]["actions"][0].pop("text")
        with self.assertRaises(GuideRouteContractError):
            project_authorized_guide(bad)

    def test_empty_guide_and_absent_action_ids_fail_closed(self):
        with self.assertRaises(GuideRouteContractError):
            project_authorized_guide({"guide_id": 2219, "title": "Guide", "steps": []})
        bad = sample()
        bad["steps"][0]["actions"][0].pop("action_id")
        with self.assertRaises(GuideRouteContractError):
            project_authorized_guide(bad)

    def test_preparation_without_structured_items_is_blocked(self):
        bad = sample()
        bad["steps"][0]["actions"].insert(0, {
            "action_id": "prepare", "kind": "prepare",
            "text": "Préparer une ressource sans quantité",
        })
        with self.assertRaisesRegex(GuideRouteContractError, "structured items"):
            project_authorized_guide(bad)

    def test_late_preparation_is_not_silently_reordered(self):
        bad = sample()
        bad["steps"][0]["actions"].append({
            "action_id": "late-prepare", "kind": "prepare",
            "text": "Préparer ensuite un objet",
        })
        with self.assertRaisesRegex(GuideRouteContractError, "preparation would reorder"):
            project_authorized_guide(bad)

    def test_malformed_optional_collections_are_rejected(self):
        for field in ("quest_ids", "quest_names", "prerequisites"):
            bad = sample()
            bad["steps"][0][field] = "not-a-list"
            with self.subTest(field=field), self.assertRaises(GuideRouteContractError):
                project_authorized_guide(bad)

    def test_preparation_kept_without_duplicate_card_action(self):
        bad = sample()
        bad["steps"][0]["actions"].insert(0, {
            "action_id": "prepare", "kind": "prepare", "text": "Préparer 3 Ressource",
            "items": [{"name": "Ressource", "quantity": 3}],
        })
        first = project_authorized_guide(bad)["steps"][0]
        self.assertEqual(len(first["a_preparer"]), 1)
        self.assertEqual(first["a_preparer"][0]["name"], "Ressource")
        self.assertEqual(first["a_preparer"][0]["quantity"], 3)
        self.assertEqual(first["manual_sections"]["prepare"][0]["source_action_id"], "prepare")
        self.assertNotIn("prepare", [row["source_action_id"] for row in first["manual_lines"]])
        self.assertEqual(first["manual_resource_names"], ["Ressource"])


if __name__ == "__main__":
    unittest.main()
