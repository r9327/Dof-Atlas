"""Real-data contracts for the signed 20-guide Ganymède route bridge."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest

from app.modules.encyclopedia.services.guide_ganymede_continuous_plan import (
    project_ganymede_continuous_plan,
)
from app.modules.encyclopedia.services.adventure_route_engine import RouteLocation
from app.modules.encyclopedia.services.guide_route_planner import (
    GuideTravelPlan, TravelMode,
)
from tools.audit_ganymede_stage_needs import audit_stage_needs


ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "data/encyclopedia/guides"


class GanymedeContinuousPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audited = audit_stage_needs(ROOT)
        if cls.audited.get("status") == "FAIL":
            raise AssertionError(cls.audited.get("issues"))

    def build(self, guide="dofus_cawotte", characters=("character:1",), **kwargs):
        return project_ganymede_continuous_plan(
            GUIDES, self.audited, guide, characters, **kwargs,
        )

    def test_all_twenty_signed_dofus_routes_are_complete_and_ordered(self):
        total = 0
        actions_total = 0
        for guide_id in sorted(self.audited["guides"]):
            with self.subTest(guide=guide_id):
                plan = self.build(guide_id)
                stages = plan["stages"]
                self.assertEqual(plan["status"], "TRUSTED_SOURCE_STEPS_MANUAL_ONLY")
                self.assertEqual(plan["source_step_count"], len(stages))
                self.assertEqual(len(stages),
                                 self.audited["guides"][guide_id]["source_step_count"])
                self.assertEqual(plan["actual_step_id"], stages[0]["id"])
                self.assertEqual(
                    [x["source_step_number"] for x in stages],
                    list(range(1, len(stages) + 1)),
                )
                self.assertEqual(
                    sum(len(x["action_rows"]) for x in stages),
                    plan["source_action_count"],
                )
                self.assertTrue(all(
                    x["verified_travel_plan"] is None
                    and not x["automatic_completion_allowed"]
                    and len(x["pending_character_keys"]) == 1
                    and all(not a["canonical_objective_verified"]
                            and not a["auto_completion_allowed"]
                            for a in x["action_rows"])
                    for x in stages
                ))
                self.assertFalse(plan["ready_for_automatic_planning"])
                self.assertEqual(plan["preparation_item_occurrences"],
                                 sum(len(x["preparation_rows"]) for x in stages))
                self.assertFalse(plan["must_purchase"])
                total += len(stages)
                actions_total += plan["source_action_count"]
        self.assertEqual(total, 1694)
        self.assertEqual(actions_total, 6166)

    def test_runtime_travel_overlay_is_step_and_character_scoped(self):
        first_id = "ganymede_2205_step_0001"
        travel = GuideTravelPlan(
            TravelMode.DIRECT, RouteLocation(x=5, y=-18),
            ("character:1",), evidence="atlas:validated-canonical-action:quest-835",
        )
        projected = self.build(verified_stage_travel={first_id: travel})
        overlay = projected["runtime_verified_travel_plans"]
        self.assertEqual(list(overlay), [first_id])
        self.assertEqual(overlay[first_id]["atlas_guide_id"], "dofus_cawotte")
        self.assertEqual(overlay[first_id]["source_step_id"], first_id)
        self.assertEqual(overlay[first_id]["participant_keys"], ["character:1"])
        self.assertEqual(overlay[first_id]["destination"]["x"], 5)
        self.assertEqual(overlay[first_id]["destination"]["y"], -18)
        self.assertIs(projected["stages"][0]["verified_travel_plan"], overlay[first_id])
        self.assertIsNone(projected["stages"][1]["verified_travel_plan"])
        self.assertFalse(projected["auto_completion_allowed"])

    def test_runtime_travel_rejects_foreign_steps_and_unscoped_plans(self):
        direct = GuideTravelPlan(
            TravelMode.DIRECT, RouteLocation(x=1, y=2), ("character:1",),
            evidence="atlas:validated-canonical-action",
        )
        unproven = GuideTravelPlan(
            TravelMode.DIRECT, RouteLocation(x=1, y=2), ("character:1",),
        )
        wrong_member = GuideTravelPlan(
            TravelMode.DIRECT, RouteLocation(x=1, y=2), ("character:2",),
            evidence="atlas:validated-canonical-action",
        )
        first = "ganymede_2205_step_0001"
        for plan in (
            {"ganymede_999_step_0001": direct},
            {first: unproven},
            {first: wrong_member},
            {first: {"mode": "direct", "destination": {"x": 1, "y": 2}}},
        ):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                self.build(verified_stage_travel=plan)
        with self.assertRaises(ValueError):
            self.build(characters=(), verified_stage_travel={first: direct})

    def test_runtime_zaap_overlay_preserves_two_command_contract(self):
        step_id = "ganymede_2205_step_0001"
        travel = GuideTravelPlan(
            TravelMode.ZAAP_THEN_TRAVEL,
            RouteLocation(x=5, y=-18), ("character:1",),
            world="Monde des Douze",
            zaap=RouteLocation(x=-32, y=-56),
            evidence="atlas:verified-zaap-route",
        )
        overlay = self.build(verified_stage_travel={step_id: travel})[
            "runtime_verified_travel_plans"
        ][step_id]
        self.assertEqual(overlay["mode"], "zaap_then_travel")
        self.assertEqual(overlay["zaap"]["x"], -32)
        self.assertEqual(overlay["zaap"]["y"], -56)
        self.assertEqual(overlay["world"], "Monde des Douze")
        self.assertEqual(overlay["participant_keys"], ["character:1"])

    def test_actual_stage_uses_first_unfinished_for_selected_characters(self):
        baseline = self.build()
        first, second = (s["id"] for s in baseline["stages"][:2])
        self.assertEqual(first, baseline["actual_step_id"])
        self.assertTrue(baseline["stages"][0]["title"].startswith("Étape 1 — "))
        self.assertFalse(baseline["stages"][0]["short_title"].startswith("Étape 1 — "))
        self.assertTrue(baseline["stages"][0]["short_title"])
        p1 = {"character:1": {first}}
        single = self.build(completed_source_steps=p1)
        self.assertEqual(single["actual_step_id"], second)
        self.assertEqual(single["stages"][0]["manually_completed_character_keys"],
                         ["character:1"])
        mixed = self.build(
            characters=("character:1", "character:2"),
            completed_source_steps=p1,
        )
        self.assertEqual(mixed["actual_step_id"], first)
        self.assertEqual(mixed["stages"][0]["pending_character_keys"],
                         ["character:2"])
        both = self.build(
            characters=("character:1", "character:2"),
            completed_source_steps={
                "character:1": {first}, "character:2": {first},
            },
        )
        self.assertEqual(both["actual_step_id"], second)
        self.assertTrue(both["stages"][0]["all_selected_participants_completed"])
        self.assertEqual(both["stages"][0]["pending_character_keys"], [])

    def test_zero_and_five_participants_do_not_invent_progress_or_travel(self):
        empty = self.build(characters=())
        self.assertEqual(empty["actual_step_id"], None)
        self.assertTrue(all(not s["all_selected_participants_completed"]
                            for s in empty["stages"]))
        five = self.build(
            characters=tuple(f"character:{i}" for i in range(1, 6))
        )
        self.assertEqual(len(five["stages"][0]["pending_character_keys"]), 5)
        self.assertEqual(len(five["stages"]), 64)
        self.assertFalse(five["auto_completion_allowed"])

    def test_stage_preparation_per_character_no_made_up_inventory(self):
        route = self.build(
            characters=("character:1", "character:2"),
            known_owned_items={"character:1": {361: 1}},
        )
        step = route["stages"][1]
        carrots = [row for row in step["preparation_rows"]
                   if row["item_id"] == 361]
        self.assertTrue(carrots)
        first = next(row for row in carrots
                     if row["character_key"] == "character:1")
        second = next(row for row in carrots
                      if row["character_key"] == "character:2")
        self.assertEqual(first["owned_quantity_explicit"], 1)
        self.assertEqual(first["remaining_quantity_candidate"], 0)
        self.assertIsNone(second["remaining_quantity_candidate"])
        self.assertFalse(any(row["must_purchase"] for row in carrots))
        step_id = step["id"]
        after_mark = self.build(
            characters=("character:1", "character:2"),
            known_owned_items={"character:1": {361: 1}},
            completed_source_steps={"character:1": {step_id}},
        )
        self.assertFalse(any(
            row["character_key"] == "character:1"
            for row in after_mark["stages"][1]["preparation_rows"]
        ))
        self.assertTrue(any(
            row["character_key"] == "character:2"
            for row in after_mark["stages"][1]["preparation_rows"]
        ))

    def test_future_need_is_due_later_not_reclassified_as_purchase(self):
        route = self.build()
        self.assertEqual(route["preparation_summary"]["status"],
                         "REVIEW_PREPARATION_COMPACT")
        self.assertEqual(
            route["preparation_summary"]["distinct_item_count"],
            len({r["item_id"] for stage in route["stages"]
                 for r in stage["preparation_rows"]}),
        )
        # Ganymède Cawotte lists optional extra carrots on stage 2, needed
        # at stage 34. The original source occurrence stays at stage 2.
        source_stage = route["stages"][1]
        future_stage = route["stages"][33]
        source_rows = [
            r for r in source_stage["preparation_rows"]
            if r["item_id"] == 361 and r["needed_at_source_step"] == 34
        ]
        self.assertTrue(source_rows)
        matching = [
            r for r in future_stage["preparation_due_rows"]
            if r["proposal_id"] == source_rows[0]["proposal_id"]
        ]
        self.assertEqual(len(matching), len(source_rows))
        self.assertTrue(all(r["optional_or_conditional"]
                            and not r["must_purchase"] for r in matching))
        self.assertFalse(any(r["proposal_id"] == source_rows[0]["proposal_id"]
                             for r in source_stage["preparation_due_rows"]))
        # Completing the first mention must NOT hide a later requirement.
        source_done = self.build(
            completed_source_steps={"character:1": {source_stage["id"]}},
        )
        self.assertTrue(any(
            r["proposal_id"] == source_rows[0]["proposal_id"]
            for r in source_done["stages"][33]["preparation_due_rows"]
        ))
        due_done = self.build(
            completed_source_steps={"character:1": {future_stage["id"]}},
        )
        self.assertFalse(any(
            r["proposal_id"] == source_rows[0]["proposal_id"]
            for r in due_done["stages"][33]["preparation_due_rows"]
        ))

    def test_source_actions_keep_audited_types_and_ignore_navigation_links(self):
        plan = self.build(guide="dofus_argente")
        first = plan["stages"][0]
        self.assertTrue(first["action_rows"])
        self.assertTrue(all(row["source_label"] and row["display_label"]
                            for row in first["action_rows"]))
        related = [
            row for stage in plan["stages"] for row in stage["action_rows"]
            if row["classification"] == "related_guide_reference"
        ]
        self.assertTrue(related)
        self.assertTrue(all(
            row["navigation_only"] and not row["public_tree_predecessor_verified"]
            and not row["must_purchase"]
            for row in related
        ))
        self.assertTrue(all(row["canonical_objective_verified"] is False
                            for stage in plan["stages"]
                            for row in stage["action_rows"]))
        self.assertEqual(plan["audited_action_count"],
                         len(set(
                             (stage["id"], row["source_action_index"])
                             for stage in plan["stages"]
                             for row in stage["action_rows"]
                             if row["classification"] != "source_action_reference"
                         )))

    def test_canonical_quest_id_names_tooltips_and_buttons_are_deduplicated(self):
        class FakeQuestProvider:
            def __init__(self):
                self.calls = []

            def get_quest(self, quest_id):
                self.calls.append(quest_id)
                if quest_id in (840, 835):
                    return SimpleNamespace(id=quest_id, name=f"Quête {quest_id}")
                return None

        provider = FakeQuestProvider()
        plan = self.build(quest_provider=provider)
        step = plan["stages"][1]
        self.assertEqual(
            {row["quest_id"]: row["quest_name"] for row in step["linked_quests"]
             if row["catalog_id_verified"]},
            {840: "Quête 840", 835: "Quête 835"},
        )
        self.assertEqual(
            sum(row["show_quest_button"] for row in step["action_rows"]),
            2,
        )
        # Real Cawotte stage 2 references quest 835 three times. Only the
        # first line gets a button; all three retain their hover tooltip.
        repeated = [
            row for row in step["action_rows"]
            if row["quest_reference"]
            and row["quest_reference"]["quest_id"] == 835
        ]
        self.assertEqual(len(repeated), 3)
        self.assertEqual(sum(row["show_quest_button"] for row in repeated), 1)
        self.assertTrue(all(row["quest_hover_name"] == "Quête 835"
                            for row in repeated))
        self.assertEqual(len(provider.calls), len(set(provider.calls)))
        self.assertTrue(any(row["quest_hover_name"] == "Quête 840"
                            for row in step["action_rows"]))
        self.assertTrue(all(
            row["quest_completion_verified"] is False
            for stage in plan["stages"] for row in stage["linked_quests"]
        ))
        self.assertGreaterEqual(plan["catalog_quest_ids_resolved"], 2)

        unknown = self.build()
        self.assertEqual(unknown["catalog_quest_ids_resolved"], 0)
        self.assertTrue(all(
            not action["show_quest_button"] and action["quest_hover_name"] is None
            for stage in unknown["stages"] for action in stage["action_rows"]
        ))

    def test_catalogue_cannot_link_a_wrong_quest_id(self):
        class WrongQuestProvider:
            def get_quest(self, quest_id):
                return SimpleNamespace(id=quest_id + 1, name="Wrong quest")
        with self.assertRaises(ValueError):
            self.build(quest_provider=WrongQuestProvider())

    def test_invalid_or_foreign_manual_progress_is_rejected(self):
        first = self.build()["stages"][0]["id"]
        for values in (
            {"character:other": [first]},
            {"character:1": ["ganymede_999_step_0001"]},
            {"character:1": [first, first]},
            {"character:1": "ganymede_2205_step_0001"},
        ):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.build(completed_source_steps=values)

    def test_signed_file_tampering_is_rejected(self):
        manifest_source = GUIDES / "replacement_drafts/cutovers/cutover_manifest.json"
        guide_source = GUIDES / "replacement_drafts/cutovers/dofus_cawotte.json"
        with TemporaryDirectory(prefix="atlas-signed-source-") as tmp:
            root = Path(tmp)
            dest = root / "replacement_drafts/cutovers"
            dest.mkdir(parents=True)
            (dest / "cutover_manifest.json").write_bytes(manifest_source.read_bytes())
            changed = json.loads(guide_source.read_text(encoding="utf-8"))
            changed["sections"][0]["steps"][0]["title"] = "TAMPERED"
            (dest / "dofus_cawotte.json").write_text(
                json.dumps(changed, ensure_ascii=False), encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                project_ganymede_continuous_plan(
                    root, self.audited, "dofus_cawotte", ["character:1"],
                )

    def test_audited_action_ids_match_signed_source_and_keep_quest_context(self):
        plan = self.build()
        stage = plan["stages"][1]
        item = next(
            row for row in stage["action_rows"]
            if 361 in row["source_references"]["object_ids"]
        )
        self.assertEqual(item["source_references"]["quest_id"], 840)
        self.assertFalse(item["canonical_objective_verified"])

        bad = deepcopy(self.audited)
        second = next(
            stage for stage in
            bad["guides"]["dofus_cawotte"]["stages_with_requirements"]
            if stage["source_step_number"] == 2
        )
        need = next(
            item for item in second["needs"]
            if 361 in item["external_dofusdb_object_ids"]
        )
        need["external_dofusdb_object_ids"] = [99999999]
        with self.assertRaises(ValueError):
            project_ganymede_continuous_plan(
                GUIDES, bad, "dofus_cawotte", ["character:1"],
            )

    def test_audited_report_mismatch_is_rejected(self):
        bad = deepcopy(self.audited)
        bad["guides"]["dofus_cawotte"]["source_guide_id"] = 123
        with self.assertRaises(ValueError):
            project_ganymede_continuous_plan(
                GUIDES, bad, "dofus_cawotte", ["character:1"],
            )


if __name__ == "__main__":
    unittest.main()
