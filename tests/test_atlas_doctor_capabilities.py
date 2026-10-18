from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.capability_matrix import CAPABILITIES, BEHAVIOR_ANCHORS, capability_inventory, capability_test_ids, capability_control_ids, NEGATIVE_BEHAVIOR_ANCHORS, _call_names, _test_case_defined


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
        self.assertEqual(set(BEHAVIOR_ANCHORS), {row[0] for row in CAPABILITIES})
        self.assertEqual(result["behavior_test_anchors_defined"], 18)
        self.assertEqual(result["behavior_test_anchors_missing"], 0)
        self.assertEqual(result["negative_control_anchors_defined"], 18)
        self.assertEqual(result["negative_control_anchors_missing"], 0)
        self.assertEqual(set(NEGATIVE_BEHAVIOR_ANCHORS), set(BEHAVIOR_ANCHORS))
        for row in result["capabilities"]:
            self.assertIsInstance(row["definition_line"], int)
            self.assertGreater(row["definition_line"], 0)
            self.assertTrue(row["callsite_lines"])
            self.assertTrue(all(isinstance(line, int) and line > 0 for line in row["callsite_lines"]))
            self.assertEqual(row["callsite_resolution"], "AST_NAME_ONLY_UNVERIFIED")
            self.assertEqual(row["proof_status"], "WIRED")
            self.assertEqual(row["proof_level"], "WIRED")
            self.assertFalse(row["proven_defect"])
            self.assertFalse(row["behavior_certified"])
            self.assertEqual(row["behavior_test_anchor"], "DEFINED")
            self.assertEqual(row["negative_control_anchor"], "DEFINED")
            self.assertFalse(row["negative_control_executed"])
            self.assertTrue(row["behavior_test"].startswith("tests/test_atlas_doctor_"))
            self.assertFalse(row["behavior_test_executed"])
            self.assertEqual(row["behavior_test_result"], "UNVERIFIED")
        self.assertEqual(result["status"], "REVIEW_PENDING_TEST_EVIDENCE")
        self.assertEqual(result["certified_count"], 0)
        self.assertFalse(result["tests_executed"])
        self.assertFalse(result["graph_rebuilt"])
        self.assertEqual(result["tested_count"], 0)
        self.assertEqual(result["evidence_validation"]["status"], "NOT_PROVIDED")
        self.assertEqual({row["engine"] for row in result["capabilities"]},
                         {"Graph", "Runtime", "Change", "Test", "UI"})

    def test_each_behavior_anchor_resolves_to_one_exact_unittest(self):
        root = Path(__file__).resolve().parents[1]
        test_ids = capability_test_ids(root)
        self.assertEqual(set(test_ids), set(BEHAVIOR_ANCHORS))
        self.assertEqual(len(set(test_ids.values())), 18)
        control_ids = capability_control_ids(root)
        self.assertEqual(set(control_ids), set(test_ids))
        self.assertEqual(len(set([*test_ids.values(), *control_ids.values()])), 36)
        self.assertTrue(all(value.startswith("tests.test_atlas_doctor_")
                            for value in test_ids.values()))

    def test_behavior_witness_requires_actual_method_not_text_match(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tests = root / "tests"
            tests.mkdir()
            path = tests / "test_real.py"
            path.write_text(
                "# def test_fake(): pass\n"
                "class Check:\n"
                "    def test_real(self): pass\n",
                encoding="utf-8",
            )
            self.assertTrue(_test_case_defined(root, "test_real.py", "test_real"))
            self.assertFalse(_test_case_defined(root, "test_real.py", "test_fake"))
            self.assertFalse(_test_case_defined(root, "missing.py", "test_real"))

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
