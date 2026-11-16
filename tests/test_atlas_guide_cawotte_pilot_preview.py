"""Exact, read-only Cawotte candidate review contracts, with no Qt or user progress."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_cawotte_pilot_preview import (
    CAWOTTE_CANDIDATES, CawottePilotDataError, cawotte_review_cards,
)


class CawottePilotPreviewTests(unittest.TestCase):
    def test_64_existing_steps_and_191_candidate_actions_keep_order(self):
        cards = cawotte_review_cards()
        self.assertEqual(len(cards), 64)
        self.assertEqual(sum(len(c["manual_sections"]["now"]) for c in cards), 191)
        self.assertEqual(cards[0]["source_step_id"], "ganymede_2205_step_0001")
        self.assertEqual(cards[-1]["source_step_id"], "ganymede_2205_step_0064")
        self.assertEqual(cards[0]["manual_sections"]["now"][0]["position"], "[25, -4]")
        self.assertEqual(cards[0]["manual_sections"]["now"][0]["text"],
                         "Contrôler le parcours d'accès aux Dofus")
        self.assertEqual(cards[1]["manual_sections"]["now"][0]["text"],
                         "Cawotte pour la quête gastronomique")
        self.assertTrue(all(c["manual_source"] and c["manual_review_only"]
                            and not c["manual_quest_ids"] for c in cards))
        self.assertTrue(all("source_action" not in row
                            for c in cards for row in c["manual_sections"]["now"]))

    def test_mismatched_source_or_unverified_state_refused(self):
        original = json.loads(CAWOTTE_CANDIDATES.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "candidate.json"
            for kind in ("certified", "ready", "missing", "reorder",
                         "verified", "foreign", "empty_action"):
                with self.subTest(kind=kind):
                    data = copy.deepcopy(original)
                    if kind == "certified":
                        data["certified_actions"] = 1
                    elif kind == "ready":
                        data["ready_to_replace"] = True
                    elif kind == "missing":
                        data["steps"].pop()
                    elif kind == "reorder":
                        data["steps"][0], data["steps"][1] = data["steps"][1], data["steps"][0]
                    elif kind == "verified":
                        data["steps"][0]["quest_objectives_verified"] = True
                    elif kind == "foreign":
                        data["source_guide_id"] = 2208
                    else:
                        data["steps"][0]["actions"] = []
                    path.write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaises(CawottePilotDataError):
                        cawotte_review_cards(path)


if __name__ == "__main__":
    unittest.main()
