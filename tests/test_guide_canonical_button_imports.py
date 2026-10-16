from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE_BUTTON_CONSUMERS = (
    "app/modules/encyclopedia/views/guides_view.py",
    "app/modules/encyclopedia/widgets/dashboard.py",
    "app/modules/encyclopedia/widgets/entity_link_button.py",
    "app/modules/encyclopedia/widgets/guide_progress_header.py",
    "app/modules/encyclopedia/widgets/guide_section_widget.py",
    "app/modules/encyclopedia/widgets/guide_step_widget.py",
)


class GuideCanonicalButtonImportsTests(unittest.TestCase):
    def test_guide_widgets_use_canonical_ui_button(self) -> None:
        for relative in GUIDE_BUTTON_CONSUMERS:
            with self.subTest(module=relative):
                tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
                imports = [
                    node
                    for node in tree.body
                    if isinstance(node, ast.ImportFrom)
                ]
                canonical = [
                    node
                    for node in imports
                    if node.module == "app.ui.components"
                    and any(alias.name == "AtlasButton" for alias in node.names)
                ]
                self.assertEqual(len(canonical), 1, msg=relative)
                self.assertFalse(
                    any(node.module == "app.storage" for node in imports),
                    msg=f"Guide must not eagerly import Zaap storage: {relative}",
                )

    def test_storage_remains_legacy_export_of_same_button(self) -> None:
        source = (ROOT / "app/storage.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertTrue(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module == "app.ui.components"
                and any(alias.name == "AtlasButton" for alias in node.names)
                for node in tree.body
            )
        )


if __name__ == "__main__":
    unittest.main()
