from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GuideToolsReadmeTests(unittest.TestCase):
    def test_docs_use_unversioned_doctor_command(self) -> None:
        text = (ROOT / "tools/guide_tools_README.md").read_text(encoding="utf-8")
        self.assertIn("py -3.13 -m tools.guide_tools_cli doctor", text)


if __name__ == "__main__":
    unittest.main()
