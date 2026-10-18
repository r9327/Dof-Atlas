from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from tools.audit_ganymede_master_refs import (
    INDEX,
    MASTER,
    ROOT,
    audit_ganymede_master_refs,
)


class GanymedeMasterReferenceAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = {
            "guides": [
                {
                    "ganymede_guide_id": 2251,
                    "listed_step_count": 2,
                },
                {"ganymede_guide_id": 2203},
            ],
        }
        self.master = {
            "schema_version": 1,
            "source": {
                "guide_id": 2251,
                "source_url": "https://ganymede-app.com/guides/2251",
                "extraction_scope": "factual_link_occurrences_only",
                "editorial_text_imported": False,
                "page_count": 2,
                "steps_per_page": 1,
            },
            "coverage": {
                "observed_steps": 2,
                "distinct_linked_guide_ids": 2,
                "linked_main_index_guide_ids": 1,
                "linked_outside_main_index_guide_ids": [3768],
                "step_guide_links": 2,
                "dofusdb_step_link_counts": {
                    "quest": 1, "dungeon": 0, "object": 0, "monster": 0,
                },
                "coordinate_mentions": 1,
                "quest_objective_mapping_verified": 0,
                "route_order_certified": False,
            },
            "steps": [
                {
                    "source_step_number": 1,
                    "source_page": 1,
                    "linked_guide_ids": [3768],
                    "external_dofusdb_ids": {
                        "quest": [], "dungeon": [], "object": [], "monster": [],
                    },
                    "coordinate_mentions": [],
                },
                {
                    "source_step_number": 2,
                    "source_page": 2,
                    "linked_guide_ids": [2203],
                    "external_dofusdb_ids": {
                        "quest": [1631], "dungeon": [], "object": [], "monster": [],
                    },
                    "coordinate_mentions": [[4, -3]],
                },
            ],
        }
        self._write()

    def _write(self) -> None:
        for path, data in ((INDEX, self.index), (MASTER, self.master)):
            full = self.root / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def codes(self) -> list[str]:
        return [i["code"] for i in audit_ganymede_master_refs(self.root)["issues"]]

    def test_observed_links_are_not_certified_routes(self) -> None:
        report = audit_ganymede_master_refs(self.root)
        self.assertEqual(report["status"], "PASS_OBSERVED_LINKS_ONLY")
        self.assertEqual(report["verified_routes"], 0)
        self.assertEqual(report["unclassified_non_main_guide_ids"], [3768])
        self.assertEqual(report["observed_steps"], 2)

    def test_full_repository_snapshot_is_internally_coherent(self) -> None:
        report = audit_ganymede_master_refs(ROOT)
        self.assertEqual(report["status"], "PASS_OBSERVED_LINKS_ONLY", report["issues"])
        self.assertEqual(report["observed_steps"], 156)
        self.assertEqual(report["referenced_main_guides"], 89)
        self.assertEqual(report["unclassified_non_main_guide_ids"], [3238, 3768])
        self.assertEqual(report["verified_routes"], 0)

    def test_priority_source_guides_have_complete_step_sequences(self) -> None:
        for name, expected, guide_id in (
            ("argente", 237, 2203),
            ("cawotte", 64, 2205),
            ("emeraude", 52, 2211),
        ):
            with self.subTest(guide=name):
                path = Path(f"data/encyclopedia/guides/ganymede_{name}_observed_links.json")
                report = audit_ganymede_master_refs(ROOT, snapshot=path)
                self.assertEqual(report["status"], "PASS_OBSERVED_LINKS_ONLY", report["issues"])
                self.assertEqual(report["source_guide_id"], guide_id)
                self.assertEqual(report["observed_steps"], expected)
                self.assertEqual(report["verified_routes"], 0)

    def test_missing_source_step_fails(self) -> None:
        self.master["steps"].pop()
        self._write()
        self.assertIn("step_coverage", self.codes())

    def test_out_of_order_step_fails(self) -> None:
        self.master["steps"][1]["source_step_number"] = 3
        self._write()
        self.assertIn("step_sequence", self.codes())

    def test_wrong_page_fails(self) -> None:
        self.master["steps"][1]["source_page"] = 1
        self._write()
        self.assertIn("step_page", self.codes())

    def test_unreported_non_main_link_fails(self) -> None:
        self.master["coverage"]["linked_outside_main_index_guide_ids"] = []
        self._write()
        self.assertIn("link_count_mismatch", self.codes())

    def test_changed_external_id_fails(self) -> None:
        self.master["steps"][0]["linked_guide_ids"] = [0]
        self._write()
        self.assertIn("invalid_guide_links", self.codes())

    def test_wrong_count_fails(self) -> None:
        self.master["coverage"]["dofusdb_step_link_counts"]["quest"] = 2
        self._write()
        self.assertIn("link_count_mismatch", self.codes())

    def test_false_route_certification_fails(self) -> None:
        self.master["coverage"]["route_order_certified"] = True
        self._write()
        self.assertIn("false_certification", self.codes())

    def test_false_quest_verification_fails(self) -> None:
        self.master["coverage"]["quest_objective_mapping_verified"] = 1
        self._write()
        self.assertIn("false_certification", self.codes())

    def test_editorial_content_import_claim_fails(self) -> None:
        self.master["source"]["editorial_text_imported"] = True
        self._write()
        self.assertIn("unproven_source", self.codes())

    def test_duplicate_links_fail(self) -> None:
        self.master["steps"][0]["linked_guide_ids"] = [3768, 3768]
        self._write()
        self.assertIn("invalid_guide_links", self.codes())


if __name__ == "__main__":
    unittest.main()
