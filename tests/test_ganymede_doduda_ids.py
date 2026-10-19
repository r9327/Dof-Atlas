from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_doduda_ids import (
    GUIDES, INDEX, audit_ganymede_doduda_ids,
)


class GanymedeDodudaIdAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.canonical = self.root / "installed_doduda" / "quests.json"
        self.index = {
            "guides": [{"ganymede_guide_id": 2205, "listed_step_count": 2}],
        }
        self.source = {
            "schema_version": 1,
            "source": {
                "name": "Ganymède",
                "guide_id": 2205,
                "source_url": "https://ganymede-app.com/guides/2205",
                "page_count": 1,
                "steps_per_page": 50,
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
                    "quest": 2, "dungeon": 0, "object": 0, "monster": 0,
                },
                "coordinate_mentions": 0,
                "quest_objective_mapping_verified": 0,
                "route_order_certified": False,
            },
            "steps": [
                {
                    "source_step_number": number,
                    "source_page": 1,
                    "linked_guide_ids": [],
                    "external_dofusdb_ids": {
                        "quest": [qid], "dungeon": [], "object": [], "monster": [],
                    },
                    "coordinate_mentions": [],
                }
                for number, qid in ((1, 101), (2, 102))
            ],
        }
        self._write_sources()

    def _write_sources(self) -> None:
        for relative, data in (
            (INDEX, self.index),
            (GUIDES / "ganymede_2205_observed_links.json", self.source),
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")

    def _write_canonical(self, ids: list[int]) -> None:
        self.canonical.parent.mkdir(parents=True, exist_ok=True)
        self.canonical.write_text(
            json.dumps({
                "RefIds": [{"data": {"id": qid}} for qid in ids]
            }), encoding="utf-8",
        )

    def _audit(self) -> dict:
        return audit_ganymede_doduda_ids(
            self.root, raw_quests_path=self.canonical
        )

    def test_numeric_presence_and_gaps_are_not_certification(self) -> None:
        self._write_canonical([101, 900])
        report = self._audit()
        self.assertEqual(report["status"], "REVIEW_RAW_ID_GAPS", report["issues"])
        self.assertEqual(report["indexed_source_guides"], 1)
        self.assertEqual(report["observed_source_guides"], 1)
        self.assertEqual(report["distinct_external_quest_ids"], 2)
        self.assertEqual(report["raw_doduda_quest_records"], 2)
        self.assertEqual(report["raw_doduda_present_external_ids"], 1)
        self.assertEqual(report["raw_doduda_missing_external_ids"], [102])
        guide = report["guide_reports"][0]
        self.assertEqual(guide["raw_doduda_present_quest_ids"], [101])
        self.assertEqual(guide["raw_doduda_missing_quest_ids"], [102])
        self.assertEqual(guide["source_step_references"], {"101": [1], "102": [2]})
        self.assertEqual(report["certified_quest_identities"], 0)
        self.assertEqual(report["certified_quest_objectives"], 0)
        self.assertEqual(report["certified_routes"], 0)

    def test_all_ids_present_does_not_certify_gameplay(self) -> None:
        self._write_canonical([101, 102])
        report = self._audit()
        self.assertEqual(report["status"], "PASS_RAW_ID_EXISTENCE_ONLY", report["issues"])
        self.assertEqual(report["raw_doduda_present_external_ids"], 2)
        self.assertEqual(report["certified_quest_identities"], 0)
        self.assertEqual(report["certified_quest_objectives"], 0)

    def test_missing_raw_data_is_blocked_not_false_absence(self) -> None:
        report = self._audit()
        self.assertEqual(report["status"], "BLOCKED_CANONICAL_SOURCE_UNAVAILABLE")
        self.assertIsNone(report["raw_doduda_missing_external_ids"])
        self.assertIsNone(report["raw_doduda_present_external_ids"])
        self.assertFalse(report["raw_source_available"])
        self.assertEqual(
            report["guide_reports"][0]["raw_doduda_id_state"],
            "BLOCKED_CANONICAL_SOURCE_UNAVAILABLE",
        )

    def test_invalid_or_truncated_source_fails_closed(self) -> None:
        self._write_canonical([101, 102])
        self.source["steps"].pop()
        self._write_sources()
        report = self._audit()
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("invalid_source_snapshot", [i["code"] for i in report["issues"]])
        self.assertIn("incomplete_source_coverage", [i["code"] for i in report["issues"]])
        self.assertEqual(report["certified_quest_identities"], 0)

    def test_duplicate_snapshot_guide_id_fails(self) -> None:
        self._write_canonical([101, 102])
        destination = self.root / GUIDES / "ganymede_duplicate_observed_links.json"
        destination.write_text(json.dumps(self.source), encoding="utf-8")
        report = self._audit()
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("duplicate_source_guide", [i["code"] for i in report["issues"]])
        self.assertEqual(report["certified_quest_objectives"], 0)

    def test_raw_json_without_refids_is_not_accepted(self) -> None:
        self.canonical.parent.mkdir(parents=True, exist_ok=True)
        self.canonical.write_text('{"quests":{"101":{}}}', encoding="utf-8")
        report = self._audit()
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("invalid_canonical_source", [i["code"] for i in report["issues"]])

    def test_repeated_quest_reference_counts_once_per_guide(self) -> None:
        self._write_canonical([101])
        self.source["steps"][1]["external_dofusdb_ids"]["quest"] = [101]
        self._write_sources()
        report = self._audit()
        self.assertEqual(report["distinct_external_quest_ids"], 1)
        self.assertEqual(report["raw_doduda_present_external_ids"], 1)
        self.assertEqual(report["guide_reports"][0]["source_step_references"]["101"], [1, 2])


if __name__ == "__main__":
    unittest.main()
