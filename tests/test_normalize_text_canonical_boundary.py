from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.core.text import normalize_key
from app.quest_catalog import normalize_text


ROOT = Path(__file__).resolve().parents[1]


class NormalizeTextCanonicalBoundaryTests(unittest.TestCase):
    def test_quest_compatibility_export_reuses_core_implementation(self) -> None:
        self.assertIs(normalize_text, normalize_key)

    def test_normalization_contract(self) -> None:
        samples = (
            (None, ""),
            ("Épée du Iop !", "epee_du_iop"),
            ("  Panda / Élio ", "panda_elio"),
            ("A__B", "a_b"),
            ("œŒ", ""),
            ("12-34", "12_34"),
        )
        for value, expected in samples:
            with self.subTest(value=value):
                self.assertEqual(normalize_text(value), expected)

    def test_guide_import_avoids_quest_catalog_dependency(self) -> None:
        path = ROOT / "app/modules/encyclopedia/views/guides_view.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]
        self.assertFalse(
            any(
                node.module == "app.quest_catalog"
                and any(alias.name == "normalize_text" for alias in node.names)
                for node in imports
            )
        )
        self.assertTrue(
            any(
                node.module == "app.core.text"
                and any(alias.name == "normalize_key" and alias.asname == "normalize_text" for alias in node.names)
                for node in imports
            )
        )


if __name__ == "__main__":
    unittest.main()
