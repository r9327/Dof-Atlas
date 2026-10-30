from __future__ import annotations

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualCard


class _Service:
    def __init__(self, contract):
        self.auto_validation_contract = contract
        self.card_key_calls = 0

    def card_key(self, card, fallback_index):
        self.card_key_calls += 1
        return str(card.get("key") or f"index:{fallback_index}")


class GuideManualContractRowCacheTests(unittest.TestCase):
    def test_contract_rows_are_indexed_once_and_reused(self) -> None:
        row_a = {"card_key": "a", "quests": [1]}
        row_b = {"card_key": "b", "quests": [2]}
        service = _Service({"cards": [row_a, row_b]})
        widget = SimpleNamespace(service=service, card={"key": "b"}, index=1)

        self.assertIs(GuideUltimeManualCard._contract_row(widget), row_b)
        first_cache = service._manual_contract_row_index_cache
        self.assertIs(GuideUltimeManualCard._contract_row(widget), row_b)
        self.assertIs(service._manual_contract_row_index_cache, first_cache)

    def test_long_guide_tooltip_index_is_not_rebuilt_for_each_line(self) -> None:
        # Static hot-path budget check. The UI-level tooltip behavior remains
        # covered by the shared manual Qt contract tests separately.
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "app" / "modules" / "encyclopedia" / "views"
            / "shared_manual_guide_view.py"
        ).read_text(encoding="utf-8")
        module = ast.parse(source)
        renderer = next(
            node for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef) and node.name == "_add_line_section"
        )
        line_loop = next(
            node for node in renderer.body
            if isinstance(node, ast.For)
            and isinstance(node.target, ast.Tuple)
            and any(
                isinstance(value, ast.Name) and value.id == "row_index"
                for value in node.target.elts
            )
        )
        before_line = [
            node for node in renderer.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "quest_names"
                for target in node.targets
            )
        ]
        self.assertEqual(len(before_line), 1)
        self.assertLess(before_line[0].lineno, line_loop.lineno)
        self.assertFalse(any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "quest_names"
                for target in node.targets
            )
            for node in ast.walk(line_loop)
        ))

    def test_replacing_contract_rebuilds_index(self) -> None:
        first = {"card_key": "a", "quests": [1]}
        service = _Service({"cards": [first]})
        widget = SimpleNamespace(service=service, card={"key": "a"}, index=0)
        self.assertIs(GuideUltimeManualCard._contract_row(widget), first)

        replacement = {"card_key": "a", "quests": [99]}
        service.auto_validation_contract = {"cards": [replacement]}
        self.assertIs(GuideUltimeManualCard._contract_row(widget), replacement)


if __name__ == "__main__":
    unittest.main()
