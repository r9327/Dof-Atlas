from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.core.item_identity import item_id


ROOT = Path(__file__).resolve().parents[1]


class CraftLightweightImportBoundaryTests(unittest.TestCase):
    def test_item_id_semantics_are_unchanged(self) -> None:
        cases = (
            ({"id_dofus": "12", "ankama_id": 88, "id": 4}, 12),
            ({"id_dofus": 0, "ankama_id": "42"}, 42),
            ({"id": "7"}, 7),
            ({}, None),
            ({"id_dofus": "bad", "ankama_id": 22}, None),
        )
        for row, expected in cases:
            with self.subTest(row=row):
                self.assertEqual(item_id(row), expected)

    def test_craft_preload_does_not_import_storage_or_qt(self) -> None:
        source = (ROOT / "app/craft_preload.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        modules = {node.module for node in imports}
        self.assertNotIn("app.storage", modules)
        self.assertFalse(any((module or "").startswith("PySide6") for module in modules))
        for module in ("app.core.item_identity", "app.core.json_store", "app.core.text"):
            self.assertIn(module, modules)

    def test_craft_category_normalizer_is_deferred_until_classification(self) -> None:
        # Opening an SQLite-backed Craft page must not import the full
        # normalization stack when no item has been searched yet.
        source = (ROOT / "app/pages/craft_page.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertFalse(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module == "local_dofus_data.normalizer"
                for node in tree.body
            )
        )
        craft_page = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "CraftPage"
        )
        category = next(
            node for node in craft_page.body
            if isinstance(node, ast.FunctionDef) and node.name == "category_for_item"
        )
        self.assertTrue(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module == "local_dofus_data.normalizer"
                and any(alias.name == "craft_category_for_item" for alias in node.names)
                for node in ast.walk(category)
            )
        )

    def test_legacy_storage_still_reexports_canonical_item_id(self) -> None:
        source = (ROOT / "app/storage.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertTrue(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module == "app.core.item_identity"
                and any(alias.name == "item_id" for alias in node.names)
                for node in tree.body
            )
        )
        self.assertFalse(
            any(isinstance(node, ast.FunctionDef) and node.name == "item_id" for node in tree.body)
        )


if __name__ == "__main__":
    unittest.main()
