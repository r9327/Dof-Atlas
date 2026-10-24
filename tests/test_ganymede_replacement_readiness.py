from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_master_refs import INDEX, ROOT
from tools.audit_ganymede_replacement_readiness import (
    CATALOG, CROSSWALK, GUIDES_DIR, audit_ganymede_replacement_readiness,
)


class ReplacementReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self._write(CATALOG, {
            "guides": [{"id": "dofus_test", "file": "dofus_test.json",
                        "category": "dofus", "enabled": True}],
        })
        self._write(INDEX, {"guides": [
            {"ganymede_guide_id": 2205, "listed_step_count": 2},
        ]})
        self._write(CROSSWALK, {"guides": [
            {"ganymede_guide_id": 2205,
             "atlas_guide_ids": ["dofus_test"],
             "status": "metadata_only",
             "quest_mapping_verified": False,
             "route_parity_verified": False},
        ]})
        self._write(GUIDES_DIR / "dofus_test.json", {
            "id": "dofus_test", "sections": [{
                "steps": [{"id": "old_q1", "type": "quest", "entity_id": 42}],
            }],
        })

    def _write(self, path: Path, content: dict) -> None:
        out = self.root / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

    def test_no_source_snapshot_does_not_erase_legacy_guide(self) -> None:
        report = audit_ganymede_replacement_readiness(self.root)
        self.assertEqual(report["status"], "BLOCKED_PENDING_PLAYABLE_ACTIONS")
        self.assertEqual(report["ready_to_replace"], 0)
        guide = report["guide_reports"][0]
        self.assertEqual(guide["legacy_step_count"], 1)
        self.assertTrue(guide["legacy_guide_preserved"])
        self.assertTrue(guide["legacy_progress_preserved"])
        self.assertIn("MISSING_SOURCE_SNAPSHOT", guide["blockers"])
        self.assertFalse(guide["replacement_active"])

    def test_direct_mapping_not_mistaken_for_playable_steps(self) -> None:
        report = audit_ganymede_replacement_readiness(self.root)
        self.assertEqual(report["dofus_guides_with_direct_source_mapping"], 1)
        self.assertEqual(report["ready_to_replace"], 0)
        self.assertIn(
            "SOURCE_STEP_ACTIONS_NOT_RECONSTRUCTED",
            report["guide_reports"][0]["blockers"],
        )

    def test_unmapped_local_dofus_is_explicitly_blocked(self) -> None:
        self._write(CROSSWALK, {"guides": []})
        report = audit_ganymede_replacement_readiness(self.root)
        self.assertEqual(
            report["dofus_guides_without_direct_source_mapping"],
            ["dofus_test"],
        )
        self.assertIn(
            "NO_DIRECT_GANYMEDE_MAPPING",
            report["guide_reports"][0]["blockers"],
        )

    def test_corrupt_original_is_fail_not_replacement(self) -> None:
        self._write(GUIDES_DIR / "dofus_test.json", {
            "id": "bad_local_id", "sections": [],
        })
        report = audit_ganymede_replacement_readiness(self.root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("INVALID_LEGACY_GUIDE", report["guide_reports"][0]["blockers"])
        self.assertEqual(report["ready_to_replace"], 0)

    def test_repository_dofus_routes_are_staged_without_breaking_legacy(self) -> None:
        report = audit_ganymede_replacement_readiness(ROOT)
        self.assertEqual(report["status"], "SOURCE_TRUSTED_MANUAL_STAGED",
                         report["issues"])
        self.assertEqual(report["dofus_guides"], 22)
        self.assertEqual(report["dofus_guides_with_direct_source_mapping"], 20)
        self.assertEqual(
            set(report["dofus_guides_without_direct_source_mapping"]),
            {"dofoozbz", "dokille"},
        )
        self.assertEqual(report["ready_to_replace"], 0)
        self.assertEqual(report["replacement_activated_count"], 0)
        self.assertFalse(report["replacement_activated"])
        self.assertEqual(report["source_trusted_manual_staged_count"], 20)
        matrix = report["activation_matrix"]
        self.assertEqual(len(matrix), 22)
        self.assertEqual({row["atlas_guide_id"] for row in matrix},
                         {row["atlas_guide_id"] for row in report["guide_reports"]})
        self.assertEqual(sum(row["route_staged"] for row in matrix), 20)
        self.assertEqual(sum(row["route_active"] for row in matrix), 0)
        self.assertTrue(all(row["legacy_progress_preserved"] for row in matrix))
        self.assertTrue(all(row["source_guide_id"] is None for row in matrix
                            if row["atlas_guide_id"] in {"dofoozbz", "dokille"}))
        self.assertEqual(report["source_trusted_manual_guides"], 20)
        self.assertEqual(report["certified_canonical_guides"], 0)
        staged = [g for g in report["guide_reports"] if g["replacement_staged"]]
        self.assertEqual(len(staged), 20)
        self.assertTrue(all(g["source_trusted_manual_only"] for g in staged))
        self.assertTrue(all(not g["canonical_objectives_verified"] for g in staged))
        self.assertTrue(all(not g["replacement_active"] for g in staged))
        self.assertTrue(all("MANUAL_UI_AND_QUEST_LINKS_NOT_INTEGRATED" in g["blockers"]
                            for g in staged))
        self.assertTrue(all(not g["replacement_staged"] for g in report["guide_reports"]
                            if g["atlas_guide_id"] in {"dofoozbz", "dokille"}))


if __name__ == "__main__":
    unittest.main()
