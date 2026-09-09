from __future__ import annotations

import ast
import unittest
from pathlib import Path


class GuidesLazyUltimeRuntimeTests(unittest.TestCase):
    def test_guides_constructor_does_not_build_manual_runtime(self) -> None:
        path = Path("app/modules/encyclopedia/views/guides_view.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        guides_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "GuidesView"
        )
        init = next(
            node
            for node in guides_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        init_source = ast.unparse(init)
        self.assertNotIn("GuideUltimeManualRuntimeService(", init_source)
        self.assertNotIn("GuideUltimeManualView(", init_source)

    def test_manual_runtime_is_owned_by_explicit_lazy_builder(self) -> None:
        path = Path("app/modules/encyclopedia/views/guides_view.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        guides_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "GuidesView"
        )
        lazy_builder = next(
            node
            for node in guides_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "ensure_guide_ultime_view"
        )
        source = ast.unparse(lazy_builder)
        self.assertIn("GuideUltimeManualRuntimeService(", source)
        self.assertIn("GuideUltimeManualView(", source)


if __name__ == "__main__":
    unittest.main()
