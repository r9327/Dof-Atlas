from __future__ import annotations

import unittest
from pathlib import Path

from tools.atlas_doctor_lib.capability_matrix import CAPABILITIES, capability_inventory


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
        self.assertEqual(result["status"], "REVIEW_PENDING_FINAL_CERTIFICATION")
        self.assertEqual(result["certified_count"], 0)
        self.assertFalse(result["tests_executed"])
        self.assertFalse(result["graph_rebuilt"])
        self.assertEqual({row["engine"] for row in result["capabilities"]},
                         {"Graph", "Runtime", "Change", "Test", "UI"})


if __name__ == "__main__":
    unittest.main()
