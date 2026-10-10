from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.modules.encyclopedia.services import guide_criterion_scope as canonical
from tools import guide_ultime_scope_v5 as compatibility


ROOT = Path(__file__).resolve().parents[1]


class GuideCriterionScopeBoundaryTests(unittest.TestCase):
    def test_old_tool_exports_same_canonical_functions(self) -> None:
        for name in (
            "criterion_alternatives",
            "qf_alternative_sets",
            "mandatory_qf_ids",
            "residual_qf_alternatives",
        ):
            with self.subTest(function=name):
                self.assertIs(getattr(compatibility, name), getattr(canonical, name))

    def test_boolean_alternatives_keep_common_and_or_branches(self) -> None:
        expression = "Qf=1&(Qf=2|Qf=3)"
        self.assertEqual(canonical.mandatory_qf_ids(expression), frozenset({1}))
        self.assertEqual(
            canonical.residual_qf_alternatives(expression),
            (frozenset({2}), frozenset({3})),
        )
        self.assertEqual(canonical.residual_qf_alternatives("Qf=1|PO=123"), ())

    def test_runtime_adapter_never_imports_from_tools(self) -> None:
        path = ROOT / "app/modules/encyclopedia/services/adventure_route_adapter.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]
        self.assertFalse(
            any((node.module or "").startswith("tools") for node in imports),
            msg="Production Guide services must not depend on maintenance tools",
        )
        self.assertTrue(
            any(
                node.module == "app.modules.encyclopedia.services.guide_criterion_scope"
                for node in imports
            )
        )


if __name__ == "__main__":
    unittest.main()
