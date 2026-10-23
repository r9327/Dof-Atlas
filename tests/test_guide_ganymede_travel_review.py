"""Real signed routes and synthetic review fixtures must never auto-dispatch."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.modules.encyclopedia.services.adventure_route_engine import (
    RouteAction, RouteLocation,
)
from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    certified_payload_sha256,
)
from app.modules.encyclopedia.services.guide_ganymede_travel_review import (
    review_signed_ganymede_start_candidates,
)


GUIDES = Path(__file__).resolve().parents[1] / "data/encyclopedia/guides"


def start(quest_id: int, x: int, y: int, map_id: int = 123) -> RouteAction:
    return RouteAction(
        f"quest:{quest_id}:start", quest_id, "Prendre la quête", "start",
        location=RouteLocation(map_id=map_id, x=x, y=y),
        activates_quest=True, requires_active_quest=False,
    )


class GanymedeTravelReviewTests(unittest.TestCase):
    def review(self, actions=(), maps=None):
        return review_signed_ganymede_start_candidates(
            GUIDES, "dofus_cawotte", actions, maps or {}, ("character:1",),
        )

    def test_real_cawotte_quest_start_with_other_action_is_not_executable(self):
        report = self.review((start(845, 22, -10),), {123: (22, -10)})
        self.assertEqual(report["status"], "REVIEW_ONLY_NO_AUTOMATIC_TRAVEL")
        self.assertEqual(report["verified_stage_travel"], {})
        self.assertFalse(report["ready_for_automatic_planning"])
        row = next(item for item in report["entries"]
                   if item["source_step_id"] == "ganymede_2205_step_0055")
        self.assertEqual(row["quest_id"], 845)
        self.assertEqual(row["status"], "BLOCKED_LOCATION_UNVERIFIED")
        self.assertIn("ambiguous", row["reason"])

    def test_even_exact_candidate_requires_explicit_review(self):
        with TemporaryDirectory(prefix="atlas-ganymede-review-") as tmp:
            root = Path(tmp)
            folder = root / "replacement_drafts/cutovers"
            folder.mkdir(parents=True)
            signed = GUIDES / "replacement_drafts/cutovers"
            payload = json.loads((signed / "dofus_cawotte.json").read_text(encoding="utf-8"))
            # Test-only altered route. Never treat it as approved game data.
            step = payload["sections"][0]["steps"][54]
            step["source_action_candidates"] = [{
                "kind": "quest_start", "quest_id": 845,
                "label": "Démarrer Les pwinces déchus",
            }]
            step["content"] = "Démarrer Les pwinces déchus"
            manifest = json.loads((signed / "cutover_manifest.json").read_text(encoding="utf-8"))
            manifest["guides"] = {"dofus_cawotte": dict(manifest["guides"]["dofus_cawotte"])}
            manifest["guides"]["dofus_cawotte"]["payload_sha256"] = certified_payload_sha256(payload)
            (folder / "dofus_cawotte.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8",
            )
            (folder / "cutover_manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8",
            )
            report = review_signed_ganymede_start_candidates(
                root, "dofus_cawotte", (start(845, 22, -10),),
                {123: (22, -10)}, ("character:1",),
            )
            row = next(item for item in report["entries"]
                       if item["source_step_id"] == "ganymede_2205_step_0055")
            self.assertEqual(row["status"], "CANDIDATE_REQUIRES_APPROVAL")
            self.assertEqual(report["verified_stage_travel"], {})
            self.assertFalse(report["ready_for_automatic_planning"])

    def test_no_canonical_match_or_duplicate_matches_are_blocked(self):
        missing = self.review()
        row = next(x for x in missing["entries"]
                   if x["source_step_id"] == "ganymede_2205_step_0055")
        self.assertEqual(row["status"], "BLOCKED_ATLAS_MISSING")
        duplicate = self.review(
            (start(845, 22, -10), start(845, 22, -10)),
            {123: (22, -10)},
        )
        row = next(x for x in duplicate["entries"]
                   if x["source_step_id"] == "ganymede_2205_step_0055")
        self.assertEqual(row["status"], "BLOCKED_ATLAS_AMBIGUOUS")

    def test_cli_uses_exact_signed_quest_ids_without_guessing_from_labels(self):
        from tools.audit_ganymede_travel_candidates import signed_quest_start_ids

        cutover = GUIDES / "replacement_drafts/cutovers/dofus_cawotte.json"
        source = json.loads(cutover.read_text(encoding="utf-8"))
        ids = signed_quest_start_ids(source["sections"][0]["steps"])
        self.assertIn(845, ids)
        self.assertIn(836, ids)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn(True, ids)
        self.assertEqual(signed_quest_start_ids([{
            "source_action_candidates": [
                {"kind": "quest_start", "quest_id": True},
                {"kind": "quest_start", "quest_id": "845"},
                {"kind": "move", "quest_id": 845},
            ],
        }]), ())

    def test_invalid_participants_and_untyped_actions_fail_closed(self):
        with self.assertRaises(ValueError):
            review_signed_ganymede_start_candidates(
                GUIDES, "dofus_cawotte", (), {}, (),
            )
        with self.assertRaisesRegex(ValueError, "typed"):
            self.review(({"quest_id": 845},), {})
