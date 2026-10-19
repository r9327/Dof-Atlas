from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_master_refs import INDEX, ROOT
from tools.audit_ganymede_replacement_readiness import (
    CATALOG, CROSSWALK, GUIDES_DIR,
)
from tools.build_ganymede_replacement_previews import (
    build_dofus_replacement_previews,
    stable_step_id,
    write_replacement_previews,
)


class GanymedeReplacementPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.index = {"guides": [{
            "ganymede_guide_id": 2205,
            "listed_step_count": 2,
            "public_tree_prerequisite_guide_ids": [2204],
        }]}
        self.catalog = {"guides": [
            {"id": "dofus_test", "file": "dofus_test.json",
             "category": "dofus", "enabled": True},
            {"id": "dokille", "file": "dokille.json",
             "category": "dofus", "enabled": True},
        ]}
        self.crosswalk = {"guides": [{
            "ganymede_guide_id": 2205,
            "atlas_guide_ids": ["dofus_test"],
            "status": "metadata_only",
            "quest_mapping_verified": False,
            "route_parity_verified": False,
        }]}
        self.legacy = {
            "schema_version": 1, "id": "dofus_test",
            "title": "Dofus Test", "category": "dofus",
            "sections": [{"id": "ancien", "steps": [
                {"id": "old_quest_100", "type": "quest", "entity_id": 100,
                 "optional": True,
                 "prerequisites": [{"type": "quest", "entity_id": 99}],
                 "alternative_groups": ["test:or:1"]},
            ]}],
        }
        self.snapshot = {
            "schema_version": 1,
            "source": {
                "guide_id": 2205, "source_url": "https://ganymede-app.com/guides/2205",
                "page_count": 1, "steps_per_page": 50,
                "extraction_scope": "factual_link_occurrences_only",
                "editorial_text_imported": False,
            },
            "coverage": {
                "observed_steps": 2,
                "distinct_linked_guide_ids": 0,
                "linked_main_index_guide_ids": 0,
                "linked_outside_main_index_guide_ids": [],
                "step_guide_links": 0,
                "dofusdb_step_link_counts": {
                    "quest": 2, "dungeon": 1, "object": 1, "monster": 1,
                },
                "coordinate_mentions": 1,
                "quest_objective_mapping_verified": 0,
                "route_order_certified": False,
            },
            "steps": [
                {
                    "source_step_number": 1, "source_page": 1,
                    "linked_guide_ids": [],
                    "external_dofusdb_ids": {
                        "quest": [100, 101], "dungeon": [7],
                        "object": [11], "monster": [13],
                    },
                    "coordinate_mentions": [[25, -4]],
                },
                {
                    "source_step_number": 2, "source_page": 1,
                    "linked_guide_ids": [],
                    "external_dofusdb_ids": {
                        "quest": [], "dungeon": [],
                        "object": [], "monster": [],
                    },
                    "coordinate_mentions": [],
                },
            ],
        }
        self.write()

    def _write(self, relative: Path, value: dict) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def write(self) -> None:
        self._write(INDEX, self.index)
        self._write(CATALOG, self.catalog)
        self._write(CROSSWALK, self.crosswalk)
        self._write(GUIDES_DIR / "dofus_test.json", self.legacy)
        self._write(GUIDES_DIR / "ganymede_example_observed_links.json", self.snapshot)

    def test_source_order_and_stable_ids_replace_old_structure_in_preview(self) -> None:
        report = build_dofus_replacement_previews(self.root)
        self.assertEqual(report["status"], "PREVIEWS_READY_NOT_PLAYABLE", report["issues"])
        self.assertEqual(report["dofus_guides_with_continuous_drafts"], 1)
        self.assertEqual(report["total_source_steps_in_drafts"], 2)
        preview = report["previews"]["dofus_test"]
        self.assertEqual(preview["id"], "dofus_test")
        self.assertEqual(preview["source_prerequisite_guide_ids"], [2204])
        steps = preview["sections"][0]["steps"]
        self.assertEqual([s["id"] for s in steps],
                         ["ganymede_2205_step_0001", "ganymede_2205_step_0002"])
        self.assertEqual([s["source_step_number"] for s in steps], [1, 2])
        self.assertNotIn("old_quest_100", [s["id"] for s in steps])
        self.assertEqual(steps[0]["source_coordinates_mentioned"], [[25, -4]])
        self.assertEqual(steps[0]["external_dofusdb_ids"]["object"], [11])
        self.assertEqual(steps[0]["atlas_quest_candidates"][0]["quest_id"], 100)
        self.assertEqual(
            steps[0]["atlas_quest_candidates"][0]["atlas_occurrences"][0]
                ["local_declared_prerequisites"],
            [{"type": "quest", "entity_id": 99}],
        )
        self.assertEqual(
            steps[0]["atlas_quest_candidates"][1]["atlas_occurrences"], []
        )

    def test_missing_references_do_not_invent_quest_actions(self) -> None:
        preview = build_dofus_replacement_previews(self.root)["previews"]["dofus_test"]
        self.assertEqual(preview["playable_step_count"], 0)
        self.assertFalse(preview["replacement_active"])
        self.assertFalse(preview["legacy_manual_steps_migration_verified"])
        self.assertEqual(preview["completeness_status"], "draft")
        for step in preview["sections"][0]["steps"]:
            self.assertEqual(step["type"], "info")
            self.assertEqual(step["verified_actions"], [])
            self.assertFalse(step["manual_completion_allowed"])
            self.assertFalse(step["auto_completion_allowed"])
            self.assertFalse(step["original_prose_imported"])

    def test_unmapped_guides_are_explicit_not_cleared(self) -> None:
        report = build_dofus_replacement_previews(self.root)
        self.assertEqual(report["dofus_guides_without_direct_ganymede"], ["dokille"])
        self.assertFalse(report["replacement_activated"])
        self.assertFalse((self.root / GUIDES_DIR / "dokille.json").exists())

    def test_export_does_not_touch_live_legacy(self) -> None:
        previous = (self.root / GUIDES_DIR / "dofus_test.json").read_bytes()
        report = build_dofus_replacement_previews(self.root)
        files = write_replacement_previews(report, self.root / "review_output")
        self.assertEqual(len(files), 1)
        self.assertEqual((self.root / GUIDES_DIR / "dofus_test.json").read_bytes(),
                         previous)
        self.assertEqual(json.loads(files[0].read_text())["replacement_active"], False)
        with self.assertRaises(ValueError):
            write_replacement_previews(report, self.root / GUIDES_DIR)

    def test_gap_in_source_steps_rejected(self) -> None:
        self.snapshot["steps"][1]["source_step_number"] = 3
        self.write()
        report = build_dofus_replacement_previews(self.root)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["dofus_guides_with_continuous_drafts"], 0)
        self.assertEqual(report["previews"], {})

    def test_cawotte_source_actions_are_never_automatically_certified(self) -> None:
        # The independently authored action-review file can populate an
        # ordered preview, but not playable progress or auto validation.
        result = build_dofus_replacement_previews(ROOT)
        cawotte = result["previews"]["dofus_cawotte"]
        first = cawotte["sections"][0]["steps"][0]
        self.assertEqual(first["source_action_candidate_status"], "REVIEW_SOURCE_ACTION")
        self.assertTrue(first["source_action_candidates"])
        self.assertEqual(first["verified_actions"], [])
        self.assertFalse(first["manual_completion_allowed"])
        last = cawotte["sections"][0]["steps"][-1]
        self.assertEqual(last["source_action_candidate_status"], "REVIEW_SOURCE_ACTION")
        self.assertTrue(last["source_action_candidates"])
        self.assertFalse(cawotte["replacement_active"])

    def test_invalid_ids_cannot_be_used_for_progress(self) -> None:
        for gid, step in ((0, 1), (2205, 0), (True, 1), (2205, True)):
            with self.subTest(gid=gid, step=step):
                with self.assertRaises(ValueError):
                    stable_step_id(gid, step)

    def test_cawotte_factual_actions_remain_review_only(self) -> None:
        previews = build_dofus_replacement_previews(ROOT)["previews"]
        cawotte = previews["dofus_cawotte"]
        self.assertEqual(cawotte["factual_action_reviewed_step_count"], 64)
        self.assertEqual(cawotte["playable_step_count"], 0)
        self.assertFalse(cawotte["replacement_active"])
        steps = cawotte["sections"][0]["steps"]
        self.assertEqual(len(steps), 64)
        self.assertTrue(all(s["source_action_candidates"] for s in steps))
        self.assertTrue(all(s["verified_actions"] == [] for s in steps))
        self.assertTrue(all(not s["manual_completion_allowed"]
                            and not s["auto_completion_allowed"] for s in steps))
        self.assertEqual(steps[2]["source_action_candidates"][0]["quest_id"], 836)
        self.assertTrue(any(a.get("quest_id") == 836
                            for a in steps[9]["source_action_candidates"]))

    def test_committed_cawotte_emerald_dolmanax_drafts_match_source(self) -> None:
        review = build_dofus_replacement_previews(ROOT)
        self.assertEqual(review["status"], "PREVIEWS_READY_NOT_PLAYABLE",
                         review["issues"])
        for name, count, actions in (
            ("dofus_cawotte", 64, 191),
            ("dofus_emeraude", 52, 179),
            ("dolmanax", 9, 23),
        ):
            with self.subTest(guide=name):
                generated = review["previews"][name]
                path = ROOT / GUIDES_DIR / "replacement_drafts" / f"{name}.json"
                stored = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(stored["source_action_candidate_steps"], count)
                self.assertEqual(stored["source_action_candidate_actions"], actions)
                self.assertEqual(
                    generated["source_action_candidate_steps"], count
                )
                self.assertEqual(
                    generated["source_action_candidate_actions"], actions
                )
                source_steps = generated["sections"][0]["steps"]
                saved_steps = stored["sections"][0]["steps"]
                self.assertEqual(len(source_steps), count)
                self.assertEqual(len(saved_steps), count)
                self.assertEqual(
                    [row["id"] for row in saved_steps],
                    [row["id"] for row in source_steps],
                )
                self.assertEqual(
                    [row["source_action_candidates"] for row in saved_steps],
                    [row["source_action_candidates"] for row in source_steps],
                )
                self.assertTrue(all(
                    not row["manual_completion_allowed"]
                    and not row["auto_completion_allowed"]
                    and not row["verified_actions"]
                    for row in saved_steps
                ))
                self.assertFalse(stored["replacement_active"])

    def test_repository_dofus_guide_step_continuity(self) -> None:
        result = build_dofus_replacement_previews(ROOT)
        self.assertEqual(result["status"], "PREVIEWS_READY_NOT_PLAYABLE",
                         result["issues"])
        self.assertEqual(result["dofus_guides_with_continuous_drafts"], 20)
        self.assertEqual(result["total_source_steps_in_drafts"], 1694)
        cawotte = result["previews"]["dofus_cawotte"]
        self.assertEqual(cawotte["source_action_candidate_steps"], 64)
        self.assertEqual(cawotte["source_action_candidate_actions"], 191)
        self.assertEqual(
            sum(bool(s["source_action_candidates"])
                for s in cawotte["sections"][0]["steps"]), 64
        )
        self.assertTrue(all(
            s["verified_actions"] == [] and
            not s["manual_completion_allowed"]
            for s in cawotte["sections"][0]["steps"]
        ))
        self.assertEqual(
            set(result["dofus_guides_without_direct_ganymede"]),
            {"dokille", "dofoozbz"},
        )
        for preview in result["previews"].values():
            steps = preview["sections"][0]["steps"]
            self.assertEqual(len(steps), preview["expected_source_step_count"])
            self.assertEqual(len(set(step["id"] for step in steps)), len(steps))
            self.assertFalse(preview["replacement_active"])


if __name__ == "__main__":
    unittest.main()
