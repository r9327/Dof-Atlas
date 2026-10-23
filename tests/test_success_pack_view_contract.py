"""The scoped feature CI has no Qt wheels: verify UI integration syntax/contract.

The full interactive Qt test remains mandatory for final product certification.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def source(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


class SuccessUiPreparationWiringTests(unittest.TestCase):
    def test_achievement_provider_and_qt_views_are_syntax_valid(self):
        paths = (
            "app/modules/encyclopedia/providers/achievement_provider.py",
            "app/modules/encyclopedia/views/achievements_view.py",
            "app/modules/encyclopedia/widgets/achievement_detail_widget.py",
        )
        for path in paths:
            with self.subTest(path=path):
                ast.parse(source(path), filename=path)

    def test_provider_only_calls_preparation_on_user_click(self):
        widget = ast.parse(source(
            "app/modules/encyclopedia/widgets/achievement_detail_widget.py"))
        init = next(n for n in ast.walk(widget)
                    if isinstance(n, ast.FunctionDef) and n.name == "__init__")
        toggles = [n for n in ast.walk(init)
                   if isinstance(n, ast.FunctionDef) and n.name == "toggle_preparation"]
        self.assertEqual(len(toggles), 1)
        # A real Qt clicked connection, not an eager provider call at construction.
        callbacks = [
            n for n in ast.walk(init) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "connect"
            and any(isinstance(a, ast.Name) and a.id == "toggle_preparation" for a in n.args)
        ]
        self.assertEqual(len(callbacks), 1)
        prepare_calls = [
            n for n in ast.walk(init) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == "preparation_callback"
        ]
        self.assertEqual(len(prepare_calls), 1)
        self.assertTrue(all(n in list(ast.walk(toggles[0])) for n in prepare_calls))

    def test_view_routes_preparation_to_existing_success_provider(self):
        view = source("app/modules/encyclopedia/views/achievements_view.py")
        self.assertIn("preparation_callback=(", view)
        self.assertIn("self.provider.get_quest_preparation(achievement_id)", view)
        widget = source("app/modules/encyclopedia/widgets/achievement_detail_widget.py")
        self.assertIn("AchievementPreparationToggle", widget)
        self.assertIn("AchievementPreparationDetails", widget)
        self.assertIn("Qt.PlainText", widget)
        self.assertIn("Aucune préparation matérielle identifiée.", widget)


if __name__ == "__main__":
    unittest.main()
