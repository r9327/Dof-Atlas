from __future__ import annotations

import json
import unittest
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_GUIDE = _ROOT / "data" / "encyclopedia" / "guides" / "dofus_sylvestre.json"


class SylvestreGuideTitleTests(unittest.TestCase):
    def test_display_name_changes_without_changing_canonical_id(self) -> None:
        guide = json.loads(_GUIDE.read_text(encoding="utf-8"))
        self.assertEqual(guide["id"], "dofus_sylvestre")
        self.assertEqual(guide["title"], "Sylvestre Opti")
        self.assertNotEqual(guide["title"], "Lanyel Sylvestre")


if __name__ == "__main__":
    unittest.main()
