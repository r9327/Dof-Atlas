"""Read-only review cannot dispatch a Ganymède /travel command."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.modules.encyclopedia.services.adventure_route_engine import RouteAction, RouteLocation
from app.modules.encyclopedia.services.guide_ganymede_cutover import certified_payload_sha256
from app.modules.encyclopedia.services.guide_ganymede_start_review import (
    review_ganymede_start_correspondences,
)

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "data/encyclopedia/guides"
CUTOVER = GUIDES / "replacement_drafts/cutovers"


def start_action(quest_id: int, x: int, y: int) -> RouteAction:
    return RouteAction(
        f"quest:{quest_id}:start", quest_id, "Prendre la quête", "start",
        location=RouteLocation(map_id=123, x=x, y=y),
        activates_quest=True, requires_active_quest=False,
    )


class GanymedeStartReviewTests(unittest.TestCase):
    def review(self, actions=(), maps=None, root=GUIDES):
        return review_ganymede_start_correspondences(
            root, "dofus_cawotte", ("character:1",), actions,
            maps if maps is not None else {123: (22, -10)},
        )

    def test_real_ambiguous_cawotte_source_is_never_a_travel_command(self):
        report = self.review([start_action(845, 22, -10)])
        row = next(row for row in report["candidates"]
                   if row["source_step_id"] == "ganymede_2205_step_0055")
        self.assertEqual(row["status"], "REVIEW_REQUIRED")
        self.assertIn("ambiguous", row["reason"])
        self.assertEqual(report["source_step_count"], 64)
        self.assertFalse(report["ready_for_automatic_travel"])
        self.assertEqual(report["runtime_verified_travel_plans"], {})
        self.assertTrue(all(not row["travel_authorized"] for row in report["candidates"]))
        self.assertEqual(report["candidate_count"], len(report["candidates"]))

    def test_missing_duplicate_or_untyped_actions_and_users_fail_closed(self):
        self.assertEqual(self.review()["corroborated_count"], 0)
        action = start_action(845, 22, -10)
        with self.assertRaisesRegex(ValueError, "Duplicate canonical action"):
            self.review((action, action))
        with self.assertRaisesRegex(ValueError, "typed RouteAction"):
            self.review(({"quest_id": 845},))
        for participants in ((), ("character:1", "character:1"), ("slot:3",)):
            with self.subTest(participants=participants), self.assertRaises(ValueError):
                review_ganymede_start_correspondences(
                    GUIDES, "dofus_cawotte", participants, (), {},
                )

    def test_corroborated_synthetic_signed_stage_is_still_review_only(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "replacement_drafts/cutovers"
            out.mkdir(parents=True)
            payload = deepcopy(json.loads(
                (CUTOVER / "dofus_cawotte.json").read_text(encoding="utf-8")
            ))
            step = payload["sections"][0]["steps"][2]
            step["source_action_candidates"] = [{
                "kind": "quest_start", "quest_id": 836,
                "label": "Commencer la quête",
            }]
            step["content"] = "Commencer la quête"
            step["source_coordinates_mentioned"] = [[24, -3]]
            source_file = out / "dofus_cawotte.json"
            source_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            manifest = json.loads((CUTOVER / "cutover_manifest.json").read_text(encoding="utf-8"))
            manifest["guides"]["dofus_cawotte"]["payload_sha256"] = (
                certified_payload_sha256(payload)
            )
            (out / "cutover_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8",
            )
            report = self.review([start_action(836, 24, -3)], {123: (24, -3)}, root)
            found = next(row for row in report["candidates"]
                         if row["source_step_id"] == "ganymede_2205_step_0003")
            self.assertEqual(found["status"], "CORROBORATED_REVIEW_ONLY")
            self.assertEqual(found["canonical_action_id"], "quest:836:start")
            self.assertEqual(found["canonical_map_id"], 123)
            self.assertFalse(found["travel_authorized"])
            self.assertEqual(report["runtime_verified_travel_plans"], {})
            # The manifest binds the whole payload; editing later must fail.
            payload["sections"][0]["steps"][2]["title"] = "Tampered"
            source_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integrity-checked"):
                self.review([start_action(836, 24, -3)], {123: (24, -3)}, root)


if __name__ == "__main__":
    unittest.main()
