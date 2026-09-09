from __future__ import annotations

import ast
import unittest
from pathlib import Path


class EncyclopediaCharacterSyncDedupeTests(unittest.TestCase):
    def test_achievement_sync_uses_actual_character_attribute(self) -> None:
        path = Path("app/modules/encyclopedia/views/encyclopedia_page.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        page_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "EncyclopediaPage"
        )
        method = next(
            node
            for node in page_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "sync_character_to_children"
        )
        attributes = [node.args[1].value for node in ast.walk(method)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'getattr' and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name) and node.args[0].id == 'achievements_view'
            and isinstance(node.args[1], ast.Constant)]
        self.assertIn('character_key', attributes)
        self.assertNotIn('current_character_key', attributes)


if __name__ == "__main__":
    unittest.main()
