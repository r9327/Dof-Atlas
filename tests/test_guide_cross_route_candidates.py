"""Cross-guide candidate report is evidence, never an optimized playable route."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_crosswalk import analyze_cross_guide_candidates


class CrossGuideCandidatesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.guides = self.root / "data" / "encyclopedia" / "guides"
        self.guides.mkdir(parents=True)
        self.index = {
            "schema_version": 1,
            "guides": [
                {
                    "ganymede_guide_id": 101,
                    "title": "Route A",
                    "source_url": "https://ganymede-app.com/guides/101",
                    "listed_step_count": 2,
                    "status": "metadata_only",
                    "public_tree_prerequisite_guide_ids": [],
                },
                {
                    "ganymede_guide_id": 102,
                    "title": "Route B",
                    "source_url": "https://ganymede-app.com/guides/102",
                    "listed_step_count": 1,
                    "status": "metadata_only",
                    "public_tree_prerequisite_guide_ids": [101],
                },
                {
                    "ganymede_guide_id": 103,
                    "title": "Route not written yet",
                    "source_url": "https://ganymede-app.com/guides/103",
                    "listed_step_count": 25,
                    "status": "metadata_only",
                    "public_tree_prerequisite_guide_ids": [],
                },
            ],
        }
        self._write("ganymede_main_index.json", self.index)
        self._optimized("guide_complet", [900, 901])
        self._optimized("dofus_sylvestre", [901, 902])
        self._authored(101, [
            [{"kind": "travel", "text": "Aller sur la carte A", "coordinates": [1, 2]}],
            [{"kind": "travel", "text": "Revenir sur la carte A", "coordinates": [1, 2]},
             {"kind": "talk", "text": "Parler à un PNJ"}],
        ])
        self._authored(102, [
            [{"kind": "travel", "text": "Aller sur la carte B", "coordinates": [1, 2]},
             {"kind": "prepare", "text": "Préparer un objet"}],
        ])

    def _write(self, name, payload):
        (self.guides / name).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8",
        )

    def _optimized(self, name, quest_ids):
        self._write(f"{name}.json", {
            "id": name,
            "sections": [{
                "steps": [{
                    "id": f"{name}_q_{qid}", "type": "quest", "entity_id": qid,
                } for qid in quest_ids],
            }],
        })

    def _authored(self, gid, actions_per_step):
        self._write(f"ganymede_{gid}_instructions.json", {
            "schema_version": 1,
            "source_guide_id": gid,
            "source_url": f"https://ganymede-app.com/guides/{gid}",
            "expected_source_step_count": len(actions_per_step),
            "rights_basis": "atlas_original",
            "steps": [{
                "source_step_number": index,
                "title": f"Etape {index}",
                "instructions": f"Parcours original Atlas pour l'etape {index}",
                "actions": actions,
            } for index, actions in enumerate(actions_per_step, 1)],
        })

    def _observed(self, gid, steps):
        self._write(f"ganymede_{gid}_observed_links.json", {
            "schema_version": 1,
            "source": {
                "guide_id": gid,
                "editorial_text_imported": False,
                "extraction_scope": "factual_link_occurrences_only",
            },
            "steps": [{
                "source_step_number": number,
                "coordinate_mentions": coords,
                "linked_guide_ids": [],
                "external_dofusdb_ids": {
                    "quest": quests,
                    "dungeon": [],
                    "object": objects,
                    "monster": [],
                },
            } for number, (coords, quests, objects) in enumerate(steps, 1)],
        })

    def test_external_cross_guide_links_are_candidates_only(self):
        self._observed(101, [
            ([[1, 2]], [888], [500, 501]),
            ([[1, 2]], [], [500]),
        ])
        self._observed(102, [
            ([[3, 4]], [888], [500]),
        ])
        report = analyze_cross_guide_candidates(self.root)
        self.assertEqual(report["status"], "REVIEW_ONLY_NOT_OPTIMIZED")
        self.assertEqual(report["observed_source_guides"], 2)
        self.assertEqual(report["observed_source_steps"], 3)
        self.assertEqual(report["source_guides_missing_observation_snapshot"], [103])
        matches = report["cross_guide_external_reference_candidates"]
        self.assertEqual(
            [(m["reference_kind"], m["external_reference_id"]) for m in matches],
            [("object", 500), ("quest", 888)],
        )
        self.assertTrue(all(not m["canonical_atlas_id_verified"] for m in matches))
        self.assertTrue(all(not m["shared_action_verified"] for m in matches))
        self.assertFalse(report["external_references_are_canonical_objectives"])
        for row in report["authored_route_evidence"]:
            self.assertFalse(row["source_route_parity_verified"])
            self.assertFalse(row["windows_game_verified"])
            self.assertFalse(row["certified"])

    def test_step_coordinate_cross_check_flags_unmatched_without_rewriting(self):
        self._observed(101, [
            ([[1, 2]], [], []),
            ([[5, 6]], [], []),
        ])
        report = analyze_cross_guide_candidates(self.root)
        row = next(row for row in report["authored_route_evidence"]
                   if row["source_guide_id"] == 101)
        self.assertEqual(
            [c["comparison_status"] for c in row["coordinate_comparisons"]],
            ["COORDINATE_IN_STEP_SNAPSHOT", "COORDINATE_NOT_IN_STEP_SNAPSHOT"],
        )
        self.assertTrue(all(not c["game_position_verified"]
                            for c in row["coordinate_comparisons"]))
        self.assertFalse(report["route_replacement_ready"])

    def test_malformed_observation_fails_closed(self):
        self._observed(101, [
            ([[1, 2]], [888], [500]),
        ])
        report = analyze_cross_guide_candidates(self.root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("invalid_observed_snapshot",
                      {issue["code"] for issue in report["issues"]})
        self.assertEqual(report["cross_guide_external_reference_candidates"], [])
        self.assertFalse(report["route_replacement_ready"])

    def test_cross_locations_preserve_source_step_and_never_validate(self):
        report = analyze_cross_guide_candidates(self.root)
        self.assertEqual(report["status"], "REVIEW_ONLY_NOT_OPTIMIZED")
        self.assertEqual(report["source_guides_indexed"], 3)
        self.assertEqual(report["source_guides_with_authored_steps"], 2)
        self.assertEqual(report["source_guides_missing_authored_steps"], [103])
        self.assertEqual(report["authored_source_steps"], 3)
        self.assertEqual(report["authored_actions"], 5)
        self.assertEqual(len(report["co_location_candidates"]), 1)
        match = report["co_location_candidates"][0]
        self.assertEqual(match["coordinates"], [1, 2])
        self.assertEqual(match["candidate_type"], "same_xy_unverified_world_and_map")
        self.assertFalse(match["same_game_map_verified"])
        self.assertEqual(
            [(r["source_guide_id"], r["source_step_number"], r["action_index"])
             for r in match["occurrences"]],
            [(101, 1, 0), (101, 2, 0), (102, 1, 0)],
        )
        self.assertTrue(all(len(r["source_file_sha256"]) == 64
                            for r in match["occurrences"]))
        self.assertFalse(match["objective_equivalence_verified"])
        self.assertFalse(match["prerequisite_order_verified"])
        self.assertFalse(report["automatic_validation_allowed"])
        self.assertFalse(report["route_replacement_ready"])
        self.assertFalse(report["character_progress_consulted"])

    def test_canonical_quest_overlap_is_atlas_only_and_source_links_are_hints(self):
        report = analyze_cross_guide_candidates(self.root)
        self.assertEqual([r["quest_id"] for r in report["same_canonical_quest_candidates"]], [901])
        self.assertFalse(report["ganymede_to_atlas_quest_mapping_verified"])
        self.assertEqual(report["public_tree_hints"], [{
            "source_guide_id": 102, "predecessor_guide_id": 101,
            "confidence": "SOURCE_METADATA_ONLY",
        }])
        self.assertFalse(report["public_tree_hints_are_hard_dependencies"])

    def test_source_step_count_change_fails_closed_without_fake_match(self):
        self.index["guides"][0]["listed_step_count"] = 3
        self._write("ganymede_main_index.json", self.index)
        report = analyze_cross_guide_candidates(self.root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("invalid_authored_route", [issue["code"] for issue in report["issues"]])
        self.assertEqual(report["source_guides_with_authored_steps"], 1)
        self.assertEqual(report["co_location_candidates"], [])
        self.assertFalse(report["route_replacement_ready"])

    def test_one_guide_repeating_a_location_is_not_a_merge(self):
        (self.guides / "ganymede_102_instructions.json").unlink()
        report = analyze_cross_guide_candidates(self.root)
        self.assertEqual(report["co_location_candidates"], [])
        self.assertEqual(report["source_guides_missing_authored_steps"], [102, 103])
        self.assertEqual(report["status"], "REVIEW_ONLY_NOT_OPTIMIZED")

    def test_invalid_index_schema_or_false_certification_fails_closed(self):
        self.index["schema_version"] = 2
        self.index["guides"][0]["status"] = "certified"
        self._write("ganymede_main_index.json", self.index)
        report = analyze_cross_guide_candidates(self.root)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue({"unsupported_source_schema", "invalid_source_entry"}
                        .issubset({issue["code"] for issue in report["issues"]}))
        self.assertFalse(report["route_replacement_ready"])

    def test_optimized_inputs_are_never_modified(self):
        paths = [self.guides / f"{name}.json"
                 for name in ("guide_complet", "dofus_sylvestre")]
        before = [p.read_bytes() for p in paths]
        analyze_cross_guide_candidates(self.root)
        self.assertEqual(before, [p.read_bytes() for p in paths])


if __name__ == "__main__":
    unittest.main()
