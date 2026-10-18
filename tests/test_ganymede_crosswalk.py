from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_crosswalk import (
    CATALOG,
    CROSSWALK,
    MAIN_INDEX,
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


if __name__ == "__main__":
    unittest.main()
