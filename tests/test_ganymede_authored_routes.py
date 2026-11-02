"""Three original, cross-checked Otomaï itineraries must be truly usable offline.

These tests guard against replacing the authored steps with raw IDs or a
non-operational list of observed coordinate occurrences.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.views.guide_library_sources import (
    INDEX_PATH, load_ganymede_listings, load_ganymede_local_instructions,
    load_ganymede_local_observations,
)


class OtomaiAuthoredRouteTests(unittest.TestCase):
    def test_three_offline_itineraries_have_real_actions_and_correct_source_order(self):
        listings = {entry.source_id: entry for entry in load_ganymede_listings()}
        self.assertEqual({2219, 2220, 2252}.intersection(listings), {2219, 2220, 2252})
        for guide_id in (2219, 2220, 2252):
            with self.subTest(guide_id=guide_id):
                entry = listings[guide_id]
                self.assertEqual(entry.step_count, 13 if guide_id == 2252 else 7)
                instructions = load_ganymede_local_instructions(entry)
                self.assertIsNotNone(instructions)
                self.assertEqual(len(instructions), entry.step_count)
                self.assertEqual(
                    [step["source_step_number"] for step in instructions],
                    list(range(1, entry.step_count + 1)),
                )
                self.assertTrue(all(
                    step["actions"] and len(step["instructions"]) >= 30
                    for step in instructions
                ))
                self.assertGreaterEqual(
                    sum(len(step["actions"]) for step in instructions), 15,
                )
                self.assertTrue(all(
                    action["kind"] not in {"quest_link", "id_reference"}
                    and action["text"]
                    for step in instructions for action in step["actions"]
                ))

    def test_author_written_travel_positions_are_supported_by_factual_snapshot(self):
        listings = {entry.source_id: entry for entry in load_ganymede_listings()}
        for guide_id in (2219, 2220, 2252):
            with self.subTest(guide_id=guide_id):
                entry = listings[guide_id]
                local = load_ganymede_local_observations(entry)
                observed = {
                    tuple(pair) for record in local
                    for pair in record["coordinate_mentions"]
                }
                actions = load_ganymede_local_instructions(entry)
                destinations = {
                    tuple(action["coordinates"])
                    for step in actions for action in step["actions"]
                    if action.get("coordinates") is not None
                }
                self.assertTrue(destinations)
                self.assertTrue(destinations.issubset(observed))

    def test_original_prose_has_evidence_metadata_and_no_imported_editorial_text(self):
        for guide_id in (2219, 2220, 2252):
            with self.subTest(guide_id=guide_id):
                path = INDEX_PATH.parent / f"ganymede_{guide_id}_instructions.json"
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["rights_basis"], "atlas_original")
                self.assertIs(payload["editorial_source_text_copied"], False)
                sources = payload["fact_sources"]
                self.assertGreaterEqual(len(sources), 2)
                self.assertTrue(all(
                    url.startswith("https://")
                    and "ganymede-app.com" not in url
                    for url in sources
                ))


if __name__ == "__main__":
    unittest.main()
