from __future__ import annotations

import unittest

from tools.guide_tools_status import STATUS


class GuideToolsFacadeStatusTests(unittest.TestCase):
    def test_expected_canonical_components_are_declared(self) -> None:
        self.assertEqual(set(STATUS["canonical"]), {"gps", "forensic", "transversals", "structured_contracts"})


if __name__ == "__main__":
    unittest.main()
