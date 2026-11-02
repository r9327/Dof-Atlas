"""Instruction-coverage gate: only usable authored actions count."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_instruction_coverage import audit_instruction_coverage


class InstructionCoverageAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.index = self.root / "ganymede_main_index.json"
        self.index.write_text(json.dumps({"guides": [
            {
                "ganymede_guide_id": number,
                "title": f"Route {number}",
                "source_url": f"https://ganymede-app.com/guides/{number}",
                "listed_step_count": 1,
            }
            for number in (2203, 2205)
        ]}), encoding="utf-8")

    def write(self, source_id, *, action=True):
        value = {
            "schema_version": 1,
            "source_guide_id": source_id,
            "source_url": f"https://ganymede-app.com/guides/{source_id}",
            "expected_source_step_count": 1,
            "rights_basis": "atlas_original",
            "steps": [{
                "source_step_number": 1,
                "title": "Étape",
                "instructions": "Exécuter une opération explicitement rédigée",
                "actions": [{
                    "kind": "talk" if action else "quest_link",
                    "text": "Parler au PNJ de la carte",
                }],
            }],
        }
        (self.root / f"ganymede_{source_id}_instructions.json").write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8",
        )

    def test_metadata_only_counts_as_zero_guides(self):
        report = audit_instruction_coverage(
            self.index, data_dir=self.root, expected_routes=2,
        )
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["listed_steps"], 2)
        self.assertEqual(report["complete_offline_instruction_routes"], 0)
        self.assertEqual(report["missing_instruction_routes"], [2203, 2205])

    def test_only_two_complete_authored_routes_pass(self):
        self.write(2203)
        report = audit_instruction_coverage(
            self.index, data_dir=self.root, expected_routes=2,
        )
        self.assertEqual(report["complete_offline_instruction_routes"], 1)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.write(2205)
        report = audit_instruction_coverage(
            self.index, data_dir=self.root, expected_routes=2,
        )
        self.assertEqual(report["status"], "PASS_INSTRUCTION_COVERAGE")
        self.assertEqual(report["complete_offline_instruction_steps"], 2)

    def test_invalid_actions_do_not_count(self):
        self.write(2203, action=False)
        self.write(2205)
        report = audit_instruction_coverage(
            self.index, data_dir=self.root, expected_routes=2,
        )
        self.assertEqual(report["complete_offline_instruction_routes"], 1)
        self.assertEqual([r["source_id"] for r in report["invalid_instruction_routes"]], [2203])


if __name__ == "__main__":
    unittest.main()
