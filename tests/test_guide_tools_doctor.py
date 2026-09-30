from __future__ import annotations

import unittest

from tools.guide_tools_doctor import doctor


class GuideToolsDoctorTests(unittest.TestCase):
    def test_doctor_reports_canonical_surface(self) -> None:
        result = doctor()
        self.assertTrue(result["ok"], result)
        self.assertTrue(all(row["importable"] for row in result["canonical"].values()))
        self.assertTrue(all(result["retired_absent"].values()))


if __name__ == "__main__":
    unittest.main()
