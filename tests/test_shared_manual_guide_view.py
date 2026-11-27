"""Direct source owner: a single QSS source for the shared Guide roadbook."""
from __future__ import annotations

import ast
import inspect
import os
import textwrap
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualCard, SharedGuideManualView
from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualCard
from app.modules.encyclopedia.views.guides_view import linkify_travel_text
from app.modules.encyclopedia.services.guide_quest_view_model import (
    QuestStartInfo, first_position_from_quest,
)
from app.ui.theme import atlas_stylesheet


class SharedGuideManualViewThemeTests(unittest.TestCase):
    def test_guide_scrolls_use_canonical_policy_without_local_scroll_styles(self):
        source = inspect.getsource(SharedGuideManualView._build_ui)
        preparation = inspect.getsource(SharedGuideManualView._build_preparation_panel)
        self.assertIn("configure_unity_scroll_area(QScrollArea(), borderless=True)", source)
        from app.ui.components import AtlasGuidePreparationPanel
        self.assertIn("AtlasGuidePreparationPanel(", preparation)
        drawer = inspect.getsource(AtlasGuidePreparationPanel)
        self.assertIn("configure_unity_scroll_area(QScrollArea(), borderless=True)", drawer)
        for fragment in (source, preparation, drawer):
            self.assertNotIn("setHorizontalScrollBarPolicy", fragment)
            self.assertNotIn("setWidgetResizable", fragment)

    def test_validation_projection_preserves_outer_signal_block(self):
        from PySide6.QtWidgets import QApplication, QPushButton
        app = QApplication.instance() or QApplication([])
        button = QPushButton()
        button.setCheckable(True)
        probe = SimpleNamespace(
            _validation_status=lambda card, index: [],
            service=SimpleNamespace(),
        )
        try:
            for previous in (True, False):
                button.blockSignals(previous)
                SharedGuideManualView._sync_validation_control(probe, button, {}, 0)
                self.assertEqual(button.signalsBlocked(), previous)
        finally:
            button.deleteLater()

    def test_participant_progress_uses_shared_clamped_calculation(self):
        probe = SimpleNamespace(service=SimpleNamespace(route_sheet_progress=lambda key: (3, 4)))
        self.assertEqual(SharedGuideManualView._participant_progress(probe, "character:1"), 75)
        probe.service.route_sheet_progress = lambda key: (7, 4)
        self.assertEqual(SharedGuideManualView._participant_progress(probe, "character:1"), 100)
        probe.service.route_sheet_progress = lambda key: (0, 0)
        self.assertIsNone(SharedGuideManualView._participant_progress(probe, "character:1"))

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
            # This global role intentionally works on either a checkbox
            # or another checkable control; do not tie QSS to its class.
            "#GuideManualCombatCheck",
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


class GuidePositionPresentationTests(unittest.TestCase):
    def test_guide_and_quest_positions_are_bold_and_keep_copy_links(self):
        guide = GuideUltimeManualCard._format_line_html(
            "", "[12,-3]", "Parler au PNJ", [], [],
        )
        quest = linkify_travel_text("Aller en [12, -3] maintenant")
        self.assertIn("<b>", guide)
        self.assertIn("travel-copy:12,-3", guide)
        self.assertIn("<b>", quest)
        self.assertIn("atlas-travel:12,-3", quest)
        self.assertIn("Parler au PNJ", guide)
        self.assertIn("maintenant", quest)

    def test_route_finds_explicit_documentary_waypoints_without_guessing(self):
        objective = SimpleNamespace(map_label="[12, -3]")
        block = SimpleNamespace(position="[8, 9]")
        quest = SimpleNamespace(
            steps=(),
            source_solution_steps=(SimpleNamespace(objectives=(objective,)),),
            solution_blocks=(block,),
        )
        self.assertEqual(
            first_position_from_quest(quest, start_info=QuestStartInfo()),
            "[12,-3]",
        )
        quest.source_solution_steps = (
            SimpleNamespace(objectives=(SimpleNamespace(
                map_label="[-2147483648,2]",
            ),)),
        )
        self.assertEqual(
            first_position_from_quest(quest, start_info=QuestStartInfo()),
            "[8,9]",
        )
        quest.solution_blocks = (SimpleNamespace(position="Carte inconnue"),)
        self.assertEqual(
            first_position_from_quest(quest, start_info=QuestStartInfo()),
            "",
        )

    def test_route_coordinate_lookup_skips_start_map_image_reads(self):
        quest = SimpleNamespace(steps=())
        with patch(
            "app.modules.encyclopedia.services.guide_quest_view_model.quest_start_info",
            return_value=QuestStartInfo(position="[5,6]"),
        ) as start:
            self.assertEqual(first_position_from_quest(quest), "[5,6]")
        start.assert_called_once_with(quest, include_map_images=False)


if __name__ == "__main__":
    unittest.main()
