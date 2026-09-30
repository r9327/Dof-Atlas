from __future__ import annotations

import unittest

from tools.guide_tools_status import STATUS


class GuideToolsStatusTests(unittest.TestCase):
    def test_canonical_tools_are_unversioned(self) -> None:
        for target in STATUS["canonical"].values():
            self.assertNotIn("_v16", target)
            self.assertNotIn("_v2", target)
            self.assertNotIn("_strict", target)


if __name__ == "__main__":
    unittest.main()
