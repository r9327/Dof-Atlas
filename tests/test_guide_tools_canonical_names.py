from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GuideToolsCanonicalNamesTests(unittest.TestCase):
    def test_canonical_entrypoints_exist(self) -> None:
        for relative in (
            "tools/guide_gps.py",
            "tools/guide_forensic.py",
            "tools/validate_guide_ultime_manual_transversals.py",
            "tools/guide_tools.py",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
