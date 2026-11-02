"""Uncertified draft routes must never be treated as playable Ganymède routes.

A full independently researched draft is NOT proof of identical Ganymède
stage actions or in-game certification. Only the strict full-guide loader
accepts published instructions outside replacement_drafts/authoring.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.views.guide_library_sources import (
    INDEX_PATH, load_ganymede_listings, load_ganymede_local_observations,
)

AUTHORING_DIR = INDEX_PATH.parent / "replacement_drafts" / "authoring"
KINDS = frozenset({
    "travel", "talk", "interact", "fight", "prepare", "use_item", "deliver",
    "craft", "information",
})


class GanymedePartialAuthoringTests(unittest.TestCase):
    def test_partial_sources_preserve_catalog_order_and_cannot_be_played(self):
        listings = {entry.source_id: entry for entry in load_ganymede_listings()}
        paths = sorted(AUTHORING_DIR.glob("ganymede_*_partial.json"))
        if not paths:
            self.skipTest("No incomplete authoring batches remain")
        for path in paths:
            with self.subTest(file=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                guide_id = data["source_guide_id"]
                self.assertIn(guide_id, listings)
                listing = listings[guide_id]
                self.assertEqual(path.name, f"ganymede_{guide_id}_partial.json")
                self.assertEqual(data["schema_version"], 1)
                self.assertEqual(data["source_url"], listing.source_url)
                self.assertEqual(data["expected_source_step_count"], listing.step_count)
                self.assertEqual(data["rights_basis"], "atlas_original")
                self.assertIn(data["authoring_status"], {
                    "PARTIAL_NOT_PLAYABLE", "FULL_DRAFT_NOT_PLAYABLE",
                })
                self.assertFalse(data["editorial_source_text_copied"])
                self.assertFalse(data["source_parity_certified"])
                self.assertFalse(data["gameplay_certified"])
                steps = data["steps"]
                if data["authoring_status"] == "FULL_DRAFT_NOT_PLAYABLE":
                    self.assertEqual(len(steps), listing.step_count)
                    self.assertTrue(data.get("fact_sources"))
                    self.assertTrue(data.get("further_review_needed"))
                else:
                    self.assertTrue(0 < len(steps) < listing.step_count)
                self.assertEqual(data["reviewed_stage_range"], [1, len(steps)])
                self.assertEqual(
                    [step["source_step_number"] for step in steps],
                    list(range(1, len(steps) + 1)),
                )
                self.assertTrue(all(step["title"].strip()
                                    and step["instructions"].strip()
                                    and step["actions"] for step in steps))
                self.assertTrue(all(
                    action["kind"] in KINDS and action["text"].strip()
                    for step in steps for action in step["actions"]
                ))

    def test_draft_coordinates_are_mentioned_in_same_source_step(self):
        listings = {entry.source_id: entry for entry in load_ganymede_listings()}
        for path in sorted(AUTHORING_DIR.glob("ganymede_*_partial.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            entry = listings[data["source_guide_id"]]
            observed = load_ganymede_local_observations(entry)
            with self.subTest(source_guide_id=entry.source_id):
                for step in data["steps"]:
                    source_number = step["source_step_number"]
                    mentions = observed[source_number - 1]["coordinate_mentions"]
                    for action in step["actions"]:
                        coords = action.get("coordinates")
                        if coords is not None:
                            self.assertEqual(action["kind"], "travel")
                            self.assertIn(coords, mentions)

    def test_no_partial_file_masquerades_as_full_local_instructions(self):
        from app.modules.encyclopedia.views.guide_library_sources import (
            load_ganymede_local_instructions,
        )

        listings = {entry.source_id: entry for entry in load_ganymede_listings()}
        for path in sorted(AUTHORING_DIR.glob("ganymede_*_partial.json")):
            guide_id = json.loads(path.read_text(encoding="utf-8"))["source_guide_id"]
            with self.subTest(source_guide_id=guide_id):
                full_path = INDEX_PATH.parent / f"ganymede_{guide_id}_instructions.json"
                instructions = load_ganymede_local_instructions(listings[guide_id])
                if full_path.exists():
                    # A completed route can be published independently of an
                    # old authoring draft, but only via the strict loader.
                    self.assertIsNotNone(instructions)
                    self.assertEqual(len(instructions), listings[guide_id].step_count)
                else:
                    self.assertIsNone(instructions)


    def test_gp4_full_draft_preserves_solo_and_group_fight_boundaries(self):
        path = AUTHORING_DIR / "ganymede_2204_partial.json"
        if not path.is_file():
            self.skipTest("GP4 draft archived")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["authoring_status"], "FULL_DRAFT_NOT_PLAYABLE")
        self.assertEqual(len(data["steps"]), 26)
        self.assertFalse(data["source_parity_certified"])
        self.assertFalse(data["gameplay_certified"])
        s = data["steps"]
        self.assertTrue(any("Pandawa éméché" in a["text"] and "groupe" in a["text"]
                            for a in s[10]["actions"] if a["kind"] == "fight"))
        self.assertTrue(any("Guipol" in a["text"] and "solo" in a["text"]
                            for a in s[15]["actions"] if a["kind"] == "fight"))
        self.assertTrue(any("Wabbits" in a["text"] and "groupe" in a["text"]
                            for a in s[18]["actions"] if a["kind"] == "fight"))
        self.assertTrue(any("Dopeul Maléfique" in a["text"] and "seul" in a["text"]
                            for a in s[20]["actions"] if a["kind"] == "fight"))
        self.assertEqual(
            len([a for a in s[23]["actions"] if a["kind"] == "fight"]), 2
        )
        self.assertTrue(any("classe" in a["text"].casefold()
                            for a in s[20]["actions"]))
        self.assertTrue(any("Mériana" in a["text"]
                            for a in s[25]["actions"]))

    def test_opening_source_facts_survive_rewriting(self):
        # Focused editorial guard: these are verified opening-page facts,
        # not certificates for the complete source routes.
        def draft(source_id):
            path = AUTHORING_DIR / f"ganymede_{source_id}_partial.json"
            if not path.is_file():
                self.skipTest(f"Draft {source_id} has been archived")
            return json.loads(path.read_text(encoding="utf-8"))["steps"]

        access = draft(2204)
        self.assertIn("niveau 50", access[0]["instructions"].casefold())
        self.assertTrue(any("50 Orties" in x["text"] for x in access[1]["actions"]))
        self.assertTrue(any(
            x.get("coordinates") == [12, -21]
            for x in access[5]["actions"]
        ))

        valonia = draft(2206)
        self.assertIn("aucun prérequis", valonia[0]["instructions"].casefold())
        self.assertTrue(any("100 kamas" in x["text"]
                            for x in valonia[0]["actions"]))
        self.assertTrue(any("chaque personnage" in x["text"]
                            for x in valonia[3]["actions"]))

        sufokia = draft(2228)
        self.assertIn("niveau 40", sufokia[0]["instructions"].casefold())
        self.assertTrue(any("Forgerons" in x["text"] for x in sufokia[0]["actions"]))
        self.assertTrue(any("Brâkmar" in x["text"] for x in sufokia[0]["actions"]))

        nimaltopia = draft(2229)
        self.assertTrue(any("Aventure miniature" in x["text"]
                            for x in nimaltopia[0]["actions"]))
        self.assertTrue(any("Ne tirez pas sur le messager" in x["text"]
                            for x in nimaltopia[0]["actions"]))
        self.assertIn("20 Eaux potables", nimaltopia[1]["instructions"])



if __name__ == "__main__":
    unittest.main()
