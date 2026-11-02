"""Verified authored route contract: observed-link snapshots cannot become guides."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.views.guide_library_sources import (
    GanymedeListing, load_ganymede_local_instructions,
)


class AuthoredGanymedeInstructionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.entry = GanymedeListing(
            2290, "Test local", "dofus", None, 2,
            "https://ganymede-app.com/guides/2290",
        )
        self.payload = {
            "schema_version": 1,
            "source_guide_id": 2290,
            "source_url": self.entry.source_url,
            "expected_source_step_count": 2,
            "rights_basis": "atlas_original",
            "steps": [
                {
                    "source_step_number": n,
                    "title": f"Étape {n}",
                    "instructions": f"Réaliser une action vérifiée numéro {n}",
                    "actions": [
                        {
                            "kind": "travel",
                            "text": f"Aller à la destination numéro {n}",
                            "coordinates": [n, -n],
                        },
                    ],
                }
                for n in (1, 2)
            ],
        }

    def save(self):
        path = self.folder / "ganymede_2290_instructions.json"
        path.write_text(
            json.dumps(self.payload, ensure_ascii=False), encoding="utf-8",
        )

    def test_missing_is_not_a_playable_guide(self):
        self.assertIsNone(
            load_ganymede_local_instructions(self.entry, data_dir=self.folder),
        )

    def test_full_authored_route_preserves_order_and_actions(self):
        self.save()
        steps = load_ganymede_local_instructions(self.entry, data_dir=self.folder)
        self.assertEqual([s["source_step_number"] for s in steps], [1, 2])
        self.assertEqual(steps[1]["actions"][0]["coordinates"], [2, -2])

    def test_partial_route_fails_closed(self):
        self.payload["steps"].pop()
        self.save()
        with self.assertRaisesRegex(ValueError, "partial"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)

    def test_wrong_source_or_unauthorized_content_fails_closed(self):
        self.payload["source_guide_id"] = 2263
        self.save()
        with self.assertRaisesRegex(ValueError, "Unverified"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)
        self.payload["source_guide_id"] = 2290
        self.payload["rights_basis"] = "unknown"
        self.save()
        with self.assertRaisesRegex(ValueError, "Unverified"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)

    def test_ambiguous_order_or_placeholder_fails_closed(self):
        self.payload["steps"][0]["source_step_number"] = 2
        self.save()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)
        self.payload["steps"][0]["source_step_number"] = 1
        self.payload["steps"][0]["instructions"] = "À compléter"
        self.save()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)

    def test_redistribution_requires_reference_and_attribution(self):
        self.payload["rights_basis"] = "redistribution_permission"
        self.save()
        with self.assertRaisesRegex(ValueError, "permission evidence"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)
        self.payload["permission_reference"] = "Written permission ID: fixture"
        self.payload["attribution"] = "Fixture author"
        self.save()
        self.assertEqual(
            len(load_ganymede_local_instructions(self.entry, data_dir=self.folder)), 2,
        )

    def test_actions_must_be_meaningful_and_typed(self):
        self.payload["steps"][0]["actions"][0]["kind"] = "quest_link"
        self.save()
        with self.assertRaisesRegex(ValueError, "Unverified"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)
        self.payload["steps"][0]["actions"][0]["kind"] = "travel"
        self.payload["steps"][0]["actions"][0]["coordinates"] = [True, -2]
        self.save()
        with self.assertRaisesRegex(ValueError, "coordinates"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)


    def test_real_added_routes_have_full_local_instructions(self):
        # The short Dofus routes are authored, not observed-link placeholders.
        from app.modules.encyclopedia.views.guide_library_sources import (
            load_ganymede_listings,
        )

        listings = {
            entry.source_id: entry for entry in load_ganymede_listings()
        }
        for guide_id, count in ((2285, 4), (2290, 2), (2273, 15), (2247, 6), (2227, 9), (2590, 16), (2284, 21), (2224, 25), (2259, 25)):
            with self.subTest(guide_id=guide_id):
                entry = listings[guide_id]
                self.assertEqual(entry.step_count, count)
                steps = load_ganymede_local_instructions(entry)
                self.assertIsNotNone(steps)
                self.assertEqual(len(steps), count)
                self.assertEqual(
                    [step["source_step_number"] for step in steps],
                    list(range(1, count + 1)),
                )
                self.assertTrue(all(step["actions"] for step in steps))
                self.assertTrue(all(
                    action["text"].strip()
                    for step in steps for action in step["actions"]
                ))


    def test_sidimote_positioned_actions_follow_local_step_observations(self):
        # A factual coordinate must belong to its exact step in the local
        # observation file. This does not certify the original guide text.
        from app.modules.encyclopedia.views.guide_library_sources import (
            load_ganymede_listings, load_ganymede_local_observations,
        )

        entries = {row.source_id: row for row in load_ganymede_listings()}
        for source_id in (2224, 2259):
            with self.subTest(guide=source_id):
                entry = entries[source_id]
                instructions = load_ganymede_local_instructions(entry)
                observations = load_ganymede_local_observations(entry)
                self.assertEqual(len(instructions), 25)
                self.assertEqual(len(observations), 25)
                positioned = 0
                for number, (step, observed) in enumerate(
                    zip(instructions, observations), 1
                ):
                    self.assertEqual(step["source_step_number"], number)
                    self.assertEqual(observed["source_step_number"], number)
                    allowed = {
                        tuple(pair) for pair in observed["coordinate_mentions"]
                    }
                    for action in step["actions"]:
                        if "coordinates" not in action:
                            continue
                        positioned += 1
                        self.assertIn(
                            tuple(action["coordinates"]), allowed,
                            f"{source_id} step {number}",
                        )
                self.assertGreater(positioned, 20)


if __name__ == "__main__":
    unittest.main()
