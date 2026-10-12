from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.capability_matrix import CAPABILITIES, capability_inventory, _call_names


class DoctorCapabilityContractsTests(unittest.TestCase):
    def test_exactly_eighteen_source_anchors_without_fake_certification(self):
        root = Path(__file__).resolve().parents[1]
        result = capability_inventory(root)
        self.assertEqual(len(CAPABILITIES), 18)
        self.assertEqual(len({row[0] for row in CAPABILITIES}), 18)
        self.assertEqual(result["count"], 18)
        self.assertEqual(result["source_missing"], 0, result["capabilities"])
        self.assertEqual(result["call_sites_missing"], 0, result["capabilities"])
        self.assertEqual(result["call_sites_wired"], 18)
        for row in result["capabilities"]:
            self.assertIsInstance(row["definition_line"], int)
            self.assertGreater(row["definition_line"], 0)
            self.assertTrue(row["callsite_lines"])
            self.assertTrue(all(isinstance(line, int) and line > 0 for line in row["callsite_lines"]))
            self.assertEqual(row["callsite_resolution"], "AST_NAME_ONLY_UNVERIFIED")
            self.assertEqual(row["proof_status"], "UNVERIFIED")
            self.assertFalse(row["proven_defect"])
            self.assertFalse(row["behavior_certified"])
        self.assertEqual(result["status"], "REVIEW_PENDING_FINAL_CERTIFICATION")
        self.assertEqual(result["certified_count"], 0)
        self.assertFalse(result["tests_executed"])
        self.assertFalse(result["graph_rebuilt"])
        self.assertEqual({row["engine"] for row in result["capabilities"]},
                         {"Graph", "Runtime", "Change", "Test", "UI"})

    def test_callsite_line_evidence_does_not_claim_function_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fake = root / "callsite.py"
            fake.write_text("other.file_coverage()\nfile_coverage()\n", encoding="utf-8")
            calls = _call_names(root, "callsite.py")
            self.assertEqual(calls["file_coverage"], [1, 2])
            # Both are only syntactic call names, not resolved imports.
            self.assertNotIn("binding_confirmed", calls)


if __name__ == "__main__":
    unittest.main()
