"""Source-route adapter contracts for the existing shared Guide UI in main."""
from __future__ import annotations

import copy
import ast
from pathlib import Path
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
    def test_unrecognized_source_fields_must_get_explicit_ui_mapping(self):
        for scope, field, value in (
            ("action", "make_unexpected_decision", "Choose another route"),
            ("action", "teleport_spell", {"location": [1, 2]}),
            ("action", "custom_reward", [{"item": "fictitious"}]),
            ("step", "hidden_branch_directive", {"step_id": "future"}),
            ("step", "unmapped_puzzle", "press the third button"),
        ):
            with self.subTest(scope=scope, field=field):
                source = sample()
                if scope == "action":
                    source["steps"][0]["actions"][1][field] = value
                    path = f"actions[1].{field}: unrecognized authored action field"
                else:
                    source["steps"][0][field] = value
                    path = f"steps[0].{field}: unrecognized authored step field"
                with self.assertRaises(GuideRouteContractError) as blocked:
                    project_authorized_guide(source)
                self.assertIn(path, str(blocked.exception))
        # Provenance is not a player instruction. Keep it byte-for-byte.
        source = sample()
        source["steps"][0]["source_revision"] = "fictional-rev-2"
        source["steps"][0]["actions"][1]["evidence_ref"] = "approved:action"
        source["steps"][0]["actions"][1]["source_hash"] = "sha-not-certificate"
        source["steps"][0]["actions"][1]["metadata"] = {
            "capture": "fictional provenance",
        }
        # Existing capture metadata is provenance and may legitimately
        # contain route-shaped key names. None becomes another gameplay row.
        source["steps"][0]["actions"][1]["capture"] = {
            "actions": [{"event": "fictional screenshot"}],
            "steps": [{"note": "not a route step"}],
        }
        route = project_authorized_guide(source)
        raw = route["steps"][0]["manual_runtime_metadata"]["source_step"]
        self.assertEqual(raw, source["steps"][0])

    def test_semantic_action_fields_without_shared_reader_support_fail_closed(self):
        blocked = {
            "dialogue_options": [{"label": "Accepter", "target": "next"}],
            "choices": ["Oui", "Non"],
            "branches": [{"if": "alignment", "next": "step2"}],
            "branching": {"choice": "B"},
            "alternative_routes": ["route-b"],
            "subactions": [{"action_id": "hidden"}],
            "substeps": ["missing card"],
            "interactions": [{"kind": "click"}],
            "achievement_ids": [123],
            "success_ids": [123],
            "images": ["missing.png"],
            "image": "portrait.png",
            "media": [{"url": "https://example.invalid/reference.png"}],
            "attachments": ["screenshot.png"],
            "links": [{"url": "https://example.invalid"}],
            "commands": ["/travel 1,2"],
        }
        for field, value in blocked.items():
            with self.subTest(field=field):
                source = sample()
                source["steps"][0]["actions"][1][field] = value
                with self.assertRaises(GuideRouteContractError) as error:
                    project_authorized_guide(source)
                self.assertIn(
                    f"actions[1].{field}: unsupported authored UI content",
                    str(error.exception),
                )
        # Empty optional placeholders have no lost action to display.
        source = sample()
        source["steps"][0]["actions"][1]["links"] = []
        source["steps"][0]["actions"][1]["media"] = None
        source["steps"][0]["actions"][1]["source_url"] = "https://example.invalid/proof"
        route = project_authorized_guide(source)
        stored = route["steps"][0]["manual_sections"]["now"][1]["source_action"]
        self.assertEqual(stored["links"], [])
        self.assertIsNone(stored["media"])
        self.assertEqual(stored["source_url"], "https://example.invalid/proof")

    def test_hidden_guide_specific_action_gates_require_real_validation_contract(self):
        # The generic button must not certify a source action whose own
        # completion/condition logic has not been wired into its guide.
        for field, value in (
            ("conditions", [{"alignment": "bonta"}]),
            ("validation", {"kind": "quest_completed"}),
            ("validation_rule", {"flag": "npc_answer"}),
            ("completion_rule", {"boss": "Monstre fictif"}),
            ("required_level", 200),
            ("required_class", "feca"),
            ("required_alignment", "bonta"),
            ("required_order", "ordre_2"),
            ("prerequisites", [{"quest_id": 123}]),
            ("objectives", [{"kill": "Monstre fictif"}]),
            ("dungeon_successes", ["Premier", "Nomade"]),
            ("challenges", ["Premier"]),
        ):
            with self.subTest(field=field):
                source = sample()
                source["steps"][0]["actions"][1][field] = value
                with self.assertRaises(GuideRouteContractError) as blocked:
                    project_authorized_guide(source)
                self.assertIn(
                    f"actions[1].{field}: unsupported authored UI content",
                    str(blocked.exception),
                )

    def test_nested_resources_and_monsters_with_hidden_actions_are_blocked(self):
        for collection, action_index in (("items", 2), ("monsters", 3)):
            for field, value in (
                ("choices", ["A", "B"]),
                ("condition", {"quest": "test"}),
                ("location", [-5, 2]),
                ("equip", True),
                ("consume", True),
                ("buy", True),
                ("collect", True),
                ("craft_recipe", {"item": "Ressource fictive"}),
                ("drop", {"rate": 0.5}),
                ("success_ids", [123]),
                ("challenges", ["Premier"]),
                ("media", ["image.png"]),
                ("links", ["https://example.invalid"]),
                ("actions", [{"kind": "talk"}]),
            ):
                with self.subTest(collection=collection, field=field):
                    source = sample()
                    source["steps"][0]["actions"][action_index][collection][0][field] = value
                    with self.assertRaises(GuideRouteContractError) as blocked:
                        project_authorized_guide(source)
                    self.assertIn(
                        f"actions[{action_index}].{collection}[0].{field}: unsupported authored UI content",
                        str(blocked.exception),
                    )
        source = sample()
        source["steps"][0]["actions"][2]["items"][0]["links"] = []
        source["steps"][0]["actions"][3]["monsters"][0]["media"] = None
        route = project_authorized_guide(source)
        step_actions = route["steps"][0]["manual_runtime_metadata"]["source_step"]["actions"]
        self.assertEqual(step_actions[2]["items"][0]["links"], [])
        self.assertIsNone(step_actions[3]["monsters"][0]["media"])

    def test_unrenderable_step_branch_or_media_does_not_hide_in_route_metadata(self):
        for field, value in (
            ("branches", [{"target": "hidden_step"}]),
            ("choices", ["B"]),
            ("alternative_routes", ["another route"]),
            ("media", [{"src": "missing.png"}]),
            ("links", ["https://example.invalid"]),
        ):
            with self.subTest(field=field):
                source = sample()
                source["steps"][0][field] = value
                with self.assertRaises(GuideRouteContractError) as error:
                    project_authorized_guide(source)
                self.assertIn(
                    f"steps[0].{field}: unsupported authored UI content",
                    str(error.exception),
                )
        source = sample()
        source["steps"][0]["media"] = []
        source["steps"][0]["evidence_ref"] = "independent:step-A"
        route = project_authorized_guide(source)
        metadata = route["steps"][0]["manual_runtime_metadata"]["source_step"]
        self.assertEqual(metadata["media"], [])
        self.assertEqual(metadata["evidence_ref"], "independent:step-A")

    def test_canonical_source_rows_have_one_unambiguous_section_owner(self):
        source = sample()
        source["steps"][0]["actions"].insert(0, {
            "action_id": "prepare", "kind": "prepare",
            "text": "Prepare 2 fictional resources",
            "items": [{"name": "Fictional resource", "quantity": 2}],
        })
        route = project_authorized_guide(source)
        for card in route["steps"]:
            self.assertIs(card["manual_source"], True)
            actions = card["manual_runtime_metadata"]["source_step"]["actions"]
            sections = card["manual_sections"]
            observed = [
                row["source_action_id"]
                for section in ("prepare", "now", "opportunity", "keep", "boss", "before_leave")
                for row in sections.get(section, [])
            ]
            self.assertEqual(observed, [item["action_id"] for item in actions])
            self.assertEqual(len(set(observed)), len(actions))
            self.assertEqual(
                [row["source_action_id"] for row in card["manual_lines"]],
                [item["action_id"] for item in actions if item["kind"] != "prepare"],
            )

    def test_travel_source_and_displayed_coordinates_must_agree(self):
        for travel_xy, step_xy, text in (
            ([-11, 7], [-12, 7], "Aller en [-12,7]"),
            (None, [0, 0], "Aller en [-12,7]"),
            ([-12, 7], [-12, 7], "Aller en [-12,7] puis [3,4]"),
            ([-12, 7], [-12, 7], "Aller en [99999999999,4]"),
        ):
            with self.subTest(travel_xy=travel_xy, step_xy=step_xy, text=text):
                doc = sample()
                doc["steps"][0]["coordinates"] = step_xy
                action = doc["steps"][0]["actions"][0]
                action["text"] = text
                if travel_xy is None:
                    action.pop("coordinates", None)
                else:
                    action["coordinates"] = travel_xy
                with self.assertRaisesRegex(
                    GuideRouteContractError,
                    "coordinates: conflicts with authored travel text",
                ):
                    project_authorized_guide(doc)

        doc = sample()
        doc["steps"][0]["actions"][0]["text"] = "Aller en [-012, 007]"
        self.assertEqual(
            project_authorized_guide(doc)["steps"][0]["manual_sections"]["now"][0]["position"],
            "[-12,7]",
        )
        doc["steps"][0]["actions"][0]["text"] = "Se déplacer avec le zaap indiqué"
        self.assertEqual(
            project_authorized_guide(doc)["steps"][0]["manual_sections"]["now"][0]["position"],
            "[-12,7]",
        )

    def test_dialogue_choice_must_be_visible_nonempty_source_text(self):
        for invalid in (None, "", "  ", 0, False, [], {}):
            with self.subTest(invalid=invalid):
                source = sample()
                source["steps"][0]["actions"][1]["dialogue_choice"] = invalid
                with self.assertRaisesRegex(
                    GuideRouteContractError,
                    r"actions\[1\]\.dialogue_choice",
                ):
                    project_authorized_guide(source)

        source = sample()
        choice = "  Réponse exacte : « Oui, je confirme ! »  "
        source["steps"][0]["actions"][1]["dialogue_choice"] = choice
        row = project_authorized_guide(source)["steps"][0]["manual_sections"]["now"][1]
        self.assertEqual(row["source_action"]["dialogue_choice"], choice)
        self.assertEqual(row["source_action_kind"], "talk")

    def test_source_actions_keep_precise_npc_dialogue_item_and_combat_fields(self):
        source = sample()
        source["steps"][0]["actions"][1]["dialogue_choice"] = "Réponse exacte"
        source["steps"][0]["actions"][2]["items"][0]["item_id"] = 123
        route = project_authorized_guide(source)
        card = route["steps"][0]
        actions = card["manual_sections"]["now"]
        self.assertEqual(actions[1]["source_action"]["dialogue_choice"], "Réponse exacte")
        self.assertEqual(actions[2]["source_action"]["items"], [
            {"name": "Ressource", "quantity": 3, "item_id": 123}
        ])
        self.assertEqual(actions[3]["source_action"]["monsters"], [
            {"name": "Monstre", "quantity": 2}
        ])
        self.assertEqual(actions[0]["position"], "[-12,7]")
        self.assertEqual(
            [entry["source_action_id"] for entry in actions],
            ["a", "b", "c", "d"],
        )

    def test_shared_renderer_source_section_precedence_is_local_not_a_fork(self):
        file = (
            Path(__file__).resolve().parents[1]
            / "app/modules/encyclopedia/views/shared_manual_guide_view.py"
        )
        tree = ast.parse(file.read_text(encoding="utf-8"))
        widget = next(
            node for node in tree.body if isinstance(node, ast.ClassDef)
            and node.name == "SharedGuideManualCard"
        )
        initializer = next(
            node for node in widget.body if isinstance(node, ast.FunctionDef)
            and node.name == "__init__"
        )
        # Parse the actual renderer, not an invented parallel UI. This test
        # supports the separate Qt integration tests on Windows/DOFUS.
        rendered = ast.get_source_segment(file.read_text(encoding="utf-8"), initializer)
        self.assertIn(
            'source_card = card.get("manual_source") is True and "source_step_id" in card',
            rendered,
        )
        self.assertIn('sections = card.get("manual_sections")', rendered)
        self.assertIn("if source_card:", rendered)
        self.assertIn("section_provider(character_key, card)", rendered)

    def test_source_action_quest_link_is_explicit_and_lossless(self):
        source = sample()
        source["steps"][0]["quest_ids"] = [100, 200]
        source["steps"][0]["actions"][1]["quest_ids"] = [200]
        source["steps"][0]["actions"][2]["quest_ids"] = []
        route = project_authorized_guide(source)
        rows = route["steps"][0]["manual_sections"]["now"]
        self.assertEqual(rows[1]["source_action"]["quest_ids"], [200])
        self.assertEqual(rows[2]["source_action"]["quest_ids"], [])
        self.assertEqual(route["steps"][0]["manual_quest_ids"], [100, 200])
        self.assertNotIn("quest_ids", rows[0]["source_action"])

    def test_source_action_quest_link_rejects_unproven_or_ambiguous_ids(self):
        for invalid in ([101], [True], [0], [-1], [100, 100], "100", None):
            with self.subTest(invalid=invalid):
                source = sample()
                source["steps"][0]["actions"][1]["quest_ids"] = invalid
                with self.assertRaisesRegex(
                    GuideRouteContractError,
                    "actions\\[1\\]\\.quest_ids",
                ):
                    project_authorized_guide(source)

    def test_preparation_cannot_swallow_authored_npc_dialogue_combat_or_travel(self):
        template = {
            "action_id": "prep", "kind": "prepare",
            "text": "Préparer les ressources fictives",
            "items": [{"name": "Ressource fictive", "quantity": 2}],
        }
        extras = {
            "npc": "PNJ fictif",
            "dialogue_choice": "Réponse exacte fictive",
            "monsters": [{"name": "Monstre fictif", "quantity": 3}],
            "coordinates": [7, -2],
        }
        for field, value in extras.items():
            with self.subTest(field=field):
                source = sample()
                source["steps"][0]["actions"].insert(0, {
                    **template, field: copy.deepcopy(value),
                })
                with self.assertRaisesRegex(
                    GuideRouteContractError,
                    field + ": not renderable in preparation panel",
                ):
                    project_authorized_guide(source)
        # Explicit empty optional monsters do not carry an instruction.
        source = sample()
        source["steps"][0]["actions"].insert(0, {
            **template, "monsters": [],
        })
        card = project_authorized_guide(source)["steps"][0]
        self.assertEqual(card["a_preparer"][0]["name"], "Ressource fictive")
        self.assertEqual(
            card["manual_sections"]["prepare"][0]["source_action"]["monsters"], [],
        )

    def test_preparation_action_cannot_hide_an_explicit_quest_shortcut(self):
        source = sample()
        source["steps"][0]["actions"].insert(0, {
            "action_id": "prepare", "kind": "prepare",
            "text": "Préparer 2 ressources fictives",
            "items": [{"name": "Ressource fictive", "quantity": 2}],
            "quest_ids": [100],
        })
        with self.assertRaisesRegex(
            GuideRouteContractError,
            "preparation panel cannot render Quest shortcuts",
        ):
            project_authorized_guide(source)

        # The empty list is a legitimate explicit absence, not a link.
        source["steps"][0]["actions"][0]["quest_ids"] = []
        card = project_authorized_guide(source)["steps"][0]
        self.assertEqual(
            card["manual_sections"]["prepare"][0]["source_action"]["quest_ids"], []
        )

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

    def test_original_guide_metadata_survives_projection_once_per_route(self):
        document = sample()
        document["category"] = "synthetic"
        document["authoritative_source_label"] = "fixture-only"
        document["extra_annotations"] = {"branch": "B", "unlock": ["fiction"]}
        before = copy.deepcopy(document)
        route = project_authorized_guide(document)
        self.assertEqual(document, before)
        self.assertEqual(
            route["source_guide_metadata"],
            {key: value for key, value in document.items() if key != "steps"},
        )
        self.assertNotIn("steps", route["source_guide_metadata"])
        self.assertNotIn("source_guide_metadata", route["steps"][0])

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

    def test_duplicate_quest_id_is_not_silently_hidden_by_shared_quest_rows(self):
        source = sample()
        source["steps"][0]["quest_ids"] = [100, 100]
        with self.assertRaisesRegex(GuideRouteContractError, "duplicate quest ID"):
            project_authorized_guide(source)
        source["steps"][0]["quest_ids"] = [100, 200]
        self.assertEqual(
            project_authorized_guide(source)["steps"][0]["manual_quest_ids"],
            [100, 200],
        )

    def test_invalid_item_id_never_enters_preparation_projection(self):
        for invalid in (True, False, -1, 0, "123", "invalid", 1.5):
            source = sample()
            source["steps"][0]["actions"][2]["items"][0]["item_id"] = invalid
            with self.subTest(item_id=invalid), self.assertRaisesRegex(
                GuideRouteContractError, "item_id"
            ):
                project_authorized_guide(source)
        source = sample()
        source["steps"][0]["actions"][2]["items"][0]["item_id"] = 123
        route = project_authorized_guide(source)
        self.assertEqual(
            route["steps"][0]["manual_sections"]["now"][2]["source_action"]
            ["items"][0]["item_id"], 123
        )

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
            "items": [{"name": "Ressource vérifiée", "quantity": 2}],
        })
        # With valid resource data, this must be blocked for ordering, not
        # incidentally rejected earlier as a malformed item action.
        with self.assertRaisesRegex(GuideRouteContractError, "preparation would reorder"):
            project_authorized_guide(bad)

    def test_preparation_cannot_hide_other_action_types_or_escape_inventory(self):
        for kind in ("travel", "talk", "combat", "item"):
            source = sample()
            source["steps"][0]["actions"][0]["kind"] = kind
            source["steps"][0]["actions"][0]["section"] = "prepare"
            source["steps"][0]["actions"][0]["items"] = [
                {"name": "Fictitious item", "quantity": 1},
            ]
            if kind == "combat":
                source["steps"][0]["actions"][0]["monsters"] = [
                    {"name": "Fictitious monster", "quantity": 1},
                ]
            with self.subTest(kind=kind), self.assertRaisesRegex(
                GuideRouteContractError, "prepare action/section"
            ):
                project_authorized_guide(source)
        source = sample()
        source["steps"][0]["actions"].insert(0, {
            "action_id": "hidden-prep", "kind": "prepare",
            "section": "now", "text": "Prepare fictional item",
            "items": [{"name": "Fictitious item", "quantity": 2}],
        })
        with self.assertRaisesRegex(GuideRouteContractError, "prepare action/section"):
            project_authorized_guide(source)

    def test_invalid_quest_names_and_hard_gates_cannot_enter_shared_cards(self):
        for value in (None, 7, True, "", "  ", {}):
            source = sample()
            source["steps"][0]["quest_names"] = [value]
            with self.subTest(field="quest_names", value=value), self.assertRaisesRegex(
                GuideRouteContractError, "quest_names"
            ):
                project_authorized_guide(source)
        for value in (None, False, "level 100", 5, [], {}):
            source = sample()
            source["steps"][0]["prerequisites"] = [value]
            with self.subTest(field="prerequisites", value=value), self.assertRaisesRegex(
                GuideRouteContractError, "prerequisites"
            ):
                project_authorized_guide(source)
        source = sample()
        source["steps"][0]["quest_names"] = ["Fictitious quest"]
        source["steps"][0]["prerequisites"] = [{"future": {"nested": True}}]
        route = project_authorized_guide(source)["steps"][0]
        self.assertEqual(route["manual_quest_names"], ["Fictitious quest"])
        self.assertEqual(route["hard_runtime_gates"], [{"future": {"nested": True}}])

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
