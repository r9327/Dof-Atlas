from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.core.text import clean_auto_group_name, normalize_key, strip_accents
from app.services.character_order_logic import normalize_character_order


ROOT_DIR = Path(__file__).resolve().parents[1]


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


class CoreTextTests(unittest.TestCase):
    def test_normalize_key_preserves_existing_contract(self):
        self.assertEqual(normalize_key("Routes Rocailleuses"), "routes_rocailleuses")
        self.assertEqual(normalize_key("Cité d'Astrub"), "cite_d_astrub")
        self.assertEqual(normalize_key(None), "")

    def test_strip_accents_preserves_text_shape(self):
        self.assertEqual(strip_accents("Été à Brâkmar"), "Ete a Brakmar")

    def test_clean_auto_group_name_removes_window_suffix(self):
        self.assertEqual(clean_auto_group_name("  Alice  - Dofus  "), "Alice")
        self.assertEqual(clean_auto_group_name("Alice\n- Dofus"), "Alice")

    def test_core_text_is_qt_and_ui_free(self):
        modules = imported_modules(ROOT_DIR / "app" / "core" / "text.py")
        self.assertFalse(any(module.startswith("PySide6") for module in modules))
        self.assertFalse(any(module.startswith("app.ui") for module in modules))
        self.assertNotIn("app.storage", modules)

    def test_storage_reexports_core_text_helpers(self):
        path = ROOT_DIR / "app" / "storage.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "app.core.text"
            for alias in node.names
        }
        self.assertTrue({"normalize_key", "strip_accents", "clean_auto_group_name"}.issubset(imported))

    def test_auto_group_no_longer_imports_storage(self):
        modules = imported_modules(ROOT_DIR / "app" / "macros" / "auto_group.py")
        self.assertIn("app.core.text", modules)
        self.assertNotIn("app.storage", modules)

    def test_character_order_logic_no_longer_imports_storage(self):
        modules = imported_modules(ROOT_DIR / "app" / "services" / "character_order_logic.py")
        self.assertIn("app.core.text", modules)
        self.assertNotIn("app.storage", modules)
        self.assertEqual(normalize_character_order(["Élio", "elio", "Hupper"]), ("elio", "hupper"))

    def test_character_order_service_no_longer_imports_storage(self):
        modules = imported_modules(ROOT_DIR / "app" / "services" / "character_order_service.py")
        self.assertIn("app.core.text", modules)
        self.assertNotIn("app.storage", modules)


if __name__ == "__main__":
    unittest.main()
