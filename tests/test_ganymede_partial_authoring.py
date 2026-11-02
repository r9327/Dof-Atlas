"""Authoring batches must never be treated as playable Ganymède routes.

The first ten stages are human-written working material, not certified 1:1
source coverage. Full guide files are accepted by a different strict loader.
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
        self.assertGreaterEqual(len(paths), 3)
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
                self.assertEqual(data["authoring_status"], "PARTIAL_NOT_PLAYABLE")
                self.assertFalse(data["editorial_source_text_copied"])
                self.assertFalse(data["source_parity_certified"])
                self.assertFalse(data["gameplay_certified"])
                steps = data["steps"]
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

    def test_partial_coordinates_are_mentioned_in_same_source_step(self):
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
                self.assertFalse(
                    (INDEX_PATH.parent / f"ganymede_{guide_id}_instructions.json").exists()
                )
                self.assertIsNone(load_ganymede_local_instructions(listings[guide_id]))


if __name__ == "__main__":
    unittest.main()
