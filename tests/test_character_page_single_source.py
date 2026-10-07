from __future__ import annotations

from pathlib import Path
import unittest


class CharacterPageSingleSourceTests(unittest.TestCase):
    def test_modern_compatibility_shim_stays_retired(self) -> None:
        self.assertFalse(Path("app/pages/character_page_modern.py").exists())
        self.assertTrue(Path("app/pages/character_page.py").exists())


if __name__ == "__main__":
    unittest.main()
