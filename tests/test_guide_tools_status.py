from __future__ import annotations

import unittest
from pathlib import Path

from tools.guide_tools_status import STATUS


class GuideToolsStatusTests(unittest.TestCase):
    def test_canonical_tools_are_unversioned(self) -> None:
        for target in STATUS["canonical"].values():
            self.assertNotIn("_v16", target)
            self.assertNotIn("_v2", target)
            self.assertNotIn("_strict", target)


    def test_retired_tool_modules_are_absent(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for module in STATUS["retired"]:
            with self.subTest(module=module):
                self.assertFalse(
                    (root / (module.replace(".", "/") + ".py")).exists(),
                    msg=f"retired Guide module reintroduced: {module}",
                )

    def test_canonical_tool_modules_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for module in STATUS["canonical"].values():
            with self.subTest(module=module):
                self.assertTrue((root / (module.replace(".", "/") + ".py")).is_file())

if __name__ == "__main__":
    unittest.main()
