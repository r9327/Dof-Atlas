from __future__ import annotations

import unittest
from pathlib import Path

from tools.guide_tools_status import STATUS

ROOT = Path(__file__).resolve().parents[1]


class GuideToolsStatusRetiredTests(unittest.TestCase):
    def test_retired_modules_are_absent(self) -> None:
        for module in STATUS["retired"]:
            path = ROOT / (module.replace(".", "/") + ".py")
            self.assertFalse(path.exists(), str(path))


if __name__ == "__main__":
    unittest.main()
