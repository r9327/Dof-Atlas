"""Direct source owner: a single QSS source for the shared Guide roadbook."""
from __future__ import annotations

import ast
import inspect
import os
import textwrap
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualCard
from app.ui.theme import atlas_stylesheet


class SharedGuideManualViewThemeTests(unittest.TestCase):
    def test_roadbook_uses_only_global_theme_for_combat_and_line_widgets(self):
        """No local QSS may hide canonical Unity tokens after a palette change."""
        for method in (
            SharedGuideManualCard._add_line_section,
            SharedGuideManualCard._add_combat_target,
        ):
            source = inspect.getsource(method)
            self.assertNotIn("setStyleSheet", source)
        style = atlas_stylesheet()
        for selector in (
            "QFrame#GuideManualCombatSection",
            "QFrame#GuideManualCombatLineRow",
            "QFrame#GuideManualCombatInlineRow",
            "QFrame#GuideManualLineRow",
            "QLabel#GuideManualCombatInlineText",
            "QCheckBox#GuideManualCombatCheck",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, style)

    def test_no_private_qss_style_literals_in_shared_line_renderer(self):
        tree = ast.parse(textwrap.dedent(inspect.getsource(SharedGuideManualCard._add_line_section)))
        self.assertFalse(any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setStyleSheet"
            for node in ast.walk(tree)
        ))


if __name__ == "__main__":
    unittest.main()
