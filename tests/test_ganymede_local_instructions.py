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


if __name__ == "__main__":
    unittest.main()
