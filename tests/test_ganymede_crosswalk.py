from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_crosswalk import (
    CATALOG,
    CROSSWALK,
    MAIN_INDEX,
    DEFAULT_ROOT,
    audit_ganymede_crosswalk,
)


class GanymedeCrosswalkAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = {
            "schema_version": 1,
            "source": {"role": "route_reference_priority"},
            "coverage": {"asserted_complete": False},
            "guides": [
                {
                    "external_key": "cawotte",
                    "ganymede_guide_id": 2205,
                    "source_url": "https://ganymede-app.com/guides/2205",
                    "atlas_guide_ids": ["dofus_cawotte"],
                    "status": "metadata_only",
                    "quest_mapping_verified": False,
                    "route_parity_verified": False,
                },
            ],
        }
        self._write()

    def _write(self) -> None:
        manifest_path = self.root / CROSSWALK
        catalog_path = self.root / CATALOG
        index_path = self.root / MAIN_INDEX
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8"
        )
        catalog_path.write_text(
            json.dumps({"guides": [{"id": "dofus_cawotte"}]}), encoding="utf-8"
        )
        index_path.write_text(
            json.dumps({
                "schema_version": 1,
                "snapshot": {"total_main_guides": 1, "guide_routes_certified": 0},
                "guides": [{
                    "ganymede_guide_id": 2205,
                    "source_url": "https://ganymede-app.com/guides/2205",
                    "title": "Cawwot Dofus",
                    "status": "metadata_only",
                }],
            }),
            encoding="utf-8",
        )

    def test_repo_source_link_coverage_is_explicit_and_not_certified(self) -> None:
        report = audit_ganymede_crosswalk(DEFAULT_ROOT)
        self.assertEqual(report["status"], "PASS_METADATA_ONLY", report["issues"])
        self.assertGreaterEqual(report["observed_source_guides"], 66)
        self.assertGreaterEqual(report["observed_source_steps"], 3147)
        self.assertEqual(report["indexed_main_guides"], 95)
        self.assertEqual(report["verified_routes"], 0)
        self.assertEqual(
            sum(row["source_link_status"] == "OBSERVED_UNCLASSIFIED"
                for row in report["guide_coverage"]),
            report["observed_source_guides"],
        )

    def test_metadata_registry_is_not_guide_certification(self) -> None:
        report = audit_ganymede_crosswalk(self.root)
        self.assertEqual(report["status"], "PASS_METADATA_ONLY")
        self.assertEqual(report["verified_routes"], 0)
        self.assertEqual(report["mapped_atlas_guides"], 1)

    def test_unknown_atlas_guide_fails(self) -> None:
        self.manifest["guides"][0]["atlas_guide_ids"] = ["invented"]
        self._write()
        self.assertIn(
            "unknown_atlas_guide",
            [issue["code"] for issue in audit_ganymede_crosswalk(self.root)["issues"]],
        )

    def test_wrong_external_id_or_domain_fails(self) -> None:
        self.manifest["guides"][0]["source_url"] = "https://example.com/guides/999"
        self._write()
        self.assertIn(
            "source_url",
            [issue["code"] for issue in audit_ganymede_crosswalk(self.root)["issues"]],
        )

    def test_claimed_parity_without_proof_fails(self) -> None:
        self.manifest["guides"][0]["route_parity_verified"] = True
        self._write()
        self.assertIn(
            "unproved_certification",
            [issue["code"] for issue in audit_ganymede_crosswalk(self.root)["issues"]],
        )

    def test_duplicate_external_guide_fails(self) -> None:
        self.manifest["guides"].append(dict(self.manifest["guides"][0]))
        self._write()
        self.assertIn(
            "external_id",
            [issue["code"] for issue in audit_ganymede_crosswalk(self.root)["issues"]],
        )

    def test_crosswalk_absent_from_source_index_fails(self) -> None:
        self.manifest["guides"][0]["ganymede_guide_id"] = 2206
        self.manifest["guides"][0]["source_url"] = "https://ganymede-app.com/guides/2206"
        self._write()
        self.assertIn(
            "crosswalk_guide_absent_from_index",
            [issue["code"] for issue in audit_ganymede_crosswalk(self.root)["issues"]],
        )

    def test_inventory_not_complete_without_proof(self) -> None:
        self.manifest["coverage"]["asserted_complete"] = True
        self._write()
        self.assertIn(
            "invalid_coverage",
            [issue["code"] for issue in audit_ganymede_crosswalk(self.root)["issues"]],
        )


    def _enable_tree_metadata(self) -> dict:
        path = self.root / MAIN_INDEX
        index = json.loads(path.read_text(encoding="utf-8"))
        index["snapshot"]["public_tree_prerequisite_graph"] = {
            "status": "SOURCE_METADATA_ONLY",
            "source_url": "https://ganymede-app.com/tree?view=list",
            "route_content_certified": False,
            "listed_step_counts": 1,
            "guides_with_dependencies": 0,
            "dependency_edges": 0,
        }
        index["guides"][0]["listed_step_count"] = 64
        index["guides"][0]["public_tree_prerequisite_guide_ids"] = []
        path.write_text(json.dumps(index), encoding="utf-8")
        return index

    def test_tree_metadata_reports_coverage_without_certifying_routes(self) -> None:
        self._enable_tree_metadata()
        report = audit_ganymede_crosswalk(self.root)
        self.assertEqual(report["status"], "PASS_METADATA_ONLY")
        self.assertEqual(report["tree_prerequisite_edges"], 0)
        self.assertEqual(report["guide_coverage"][0]["mapping_status"], "CROSSWALK_METADATA_ONLY")
        self.assertEqual(report["verified_routes"], 0)

    def test_tree_missing_step_count_fails(self) -> None:
        index = self._enable_tree_metadata()
        del index["guides"][0]["listed_step_count"]
        (self.root / MAIN_INDEX).write_text(json.dumps(index), encoding="utf-8")
        codes = [i["code"] for i in audit_ganymede_crosswalk(self.root)["issues"]]
        self.assertIn("tree_step_count", codes)

    def test_tree_unknown_prerequisite_fails(self) -> None:
        index = self._enable_tree_metadata()
        index["guides"][0]["public_tree_prerequisite_guide_ids"] = [99999]
        index["snapshot"]["public_tree_prerequisite_graph"]["dependency_edges"] = 1
        index["snapshot"]["public_tree_prerequisite_graph"]["guides_with_dependencies"] = 1
        (self.root / MAIN_INDEX).write_text(json.dumps(index), encoding="utf-8")
        codes = [i["code"] for i in audit_ganymede_crosswalk(self.root)["issues"]]
        self.assertIn("tree_unknown_or_self_prerequisite", codes)

    def test_tree_cycle_fails(self) -> None:
        index = self._enable_tree_metadata()
        index["guides"][0]["public_tree_prerequisite_guide_ids"] = [2206]
        index["guides"].append({
            "ganymede_guide_id": 2206,
            "source_url": "https://ganymede-app.com/guides/2206",
            "title": "Valonia 1",
            "status": "metadata_only",
            "listed_step_count": 30,
            "public_tree_prerequisite_guide_ids": [2205],
        })
        index["snapshot"]["total_main_guides"] = 2
        index["snapshot"]["public_tree_prerequisite_graph"].update({
            "listed_step_counts": 2, "dependency_edges": 2, "guides_with_dependencies": 2,
        })
        (self.root / MAIN_INDEX).write_text(json.dumps(index), encoding="utf-8")
        codes = [i["code"] for i in audit_ganymede_crosswalk(self.root)["issues"]]
        self.assertIn("tree_prerequisite_cycle", codes)

    def test_tree_cannot_certify_route_content(self) -> None:
        index = self._enable_tree_metadata()
        index["snapshot"]["public_tree_prerequisite_graph"]["route_content_certified"] = True
        (self.root / MAIN_INDEX).write_text(json.dumps(index), encoding="utf-8")
        codes = [i["code"] for i in audit_ganymede_crosswalk(self.root)["issues"]]
        self.assertIn("tree_false_certification", codes)

    def test_unmapped_guide_is_explicit_in_report(self) -> None:
        index = self._enable_tree_metadata()
        index["guides"].append({
            "ganymede_guide_id": 2206,
            "source_url": "https://ganymede-app.com/guides/2206",
            "title": "Valonia 1",
            "status": "metadata_only",
            "listed_step_count": 30,
            "public_tree_prerequisite_guide_ids": [],
        })
        index["snapshot"]["total_main_guides"] = 2
        index["snapshot"]["public_tree_prerequisite_graph"]["listed_step_counts"] = 2
        (self.root / MAIN_INDEX).write_text(json.dumps(index), encoding="utf-8")
        report = audit_ganymede_crosswalk(self.root)
        self.assertEqual(report["status"], "PASS_METADATA_ONLY")
        self.assertEqual(report["unmapped_guide_ids"], [2206])
        self.assertEqual(report["guide_coverage"][1]["mapping_status"], "UNMAPPED")


    def test_candidate_mapping_is_distinct_from_verified_steps(self) -> None:
        self.manifest["guides"][0]["mapping_confidence"] = "candidate"
        self._write()
        report = audit_ganymede_crosswalk(self.root)
        self.assertEqual(report["status"], "PASS_METADATA_ONLY")
        self.assertEqual(report["candidate_guide_ids"], [2205])
        self.assertEqual(report["guide_coverage"][0]["mapping_status"], "CANDIDATE_METADATA_ONLY")
        self.assertEqual(report["verified_routes"], 0)

    def test_unproved_mapping_confidence_fails(self) -> None:
        self.manifest["guides"][0]["mapping_confidence"] = "verified"
        self._write()
        codes = [i["code"] for i in audit_ganymede_crosswalk(self.root)["issues"]]
        self.assertIn("unproved_mapping_confidence", codes)


if __name__ == "__main__":
    unittest.main()
