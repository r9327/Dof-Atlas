from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.pages.craft_item_prewarm import decorate_craft_items


class CraftItemPrewarmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_decorator_precomputes_search_and_category(self) -> None:
        rows = [{"name": "Cape Test", "type": "Cape", "family": "", "category": ""}]
        result = decorate_craft_items(rows)
        self.assertIs(result, rows)
        self.assertEqual(rows[0]["_search_name"], "cape_test")
        self.assertEqual(rows[0]["_craft_category"], "equipment")

if __name__ == "__main__":
    unittest.main()
