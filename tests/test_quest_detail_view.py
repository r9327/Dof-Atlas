"""Qt regression for the shared Quêtes / Guide quest information rail."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from app.quest_catalog import QuestObjective, QuestRecord, QuestStep

from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView
from app.ui.components import AtlasPanelToggle
from app.ui.theme import THEME_TOKENS, atlas_stylesheet


class QuestDetailViewColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_detail_geometry_is_shared_with_dev_ui(self) -> None:
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX

        geom = UNITY_MODULE_GEOMETRY_PX["quest_detail"]
        sheet = QuestDetailView(object(), object(), object())
        try:
            self.assertEqual(sheet._right_panel_saved_width,
                             geom["saved_right_width"])
            self.assertEqual(sheet.center_panel.minimumWidth(),
                             geom["center_min_width"])
            self.assertEqual(sheet.right_panel.minimumWidth(),
                             geom["right_min_width"])
            self.assertEqual(sheet.right_panel.maximumWidth(),
                             geom["right_max_width"])
            self.assertEqual(sheet.header.layout().getContentsMargins(),
                             geom["header_margins"])
            prerequisite = sheet._prerequisite_row("Quête précédente", False, 42)
            try:
                layout = prerequisite.layout()
                self.assertEqual(layout.spacing(), geom["prerequisite_row_spacing"])
                self.assertEqual(
                    layout.itemAt(0).widget().width(), geom["prerequisite_marker_width"]
                )
            finally:
                prerequisite.deleteLater()
        finally:
            sheet.deleteLater()

    def test_start_coordinate_is_not_falsely_certified_from_an_objective(self) -> None:
        quest = QuestRecord(
            id=42, name="Quête de test", category="Quêtes",
            level_min=1, level_max=1, start_criterion="",
            zones=["Zone locale"],
            steps=[QuestStep(
                id=1, name="Objectif", description="",
                objectives=[QuestObjective(
                    id=101, text="Rejoindre la zone", type_id=0,
                    map_label="[11,12]",
                )],
            )],
        )
        # Quest objective coordinates are valid objective hints, but not
        # independent evidence of where to launch the quest.
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, "[11,12]"),
            "Position d'objectif (départ non confirmé)",
        )
        quest.source_info = {"launch_position": {"position": "[3,4]"}}
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, "[3,4]"),
            "Position de lancement (source locale)",
        )
        self.assertEqual(
            QuestDetailView._start_position_heading(quest, ""),
            "Zone de quête",
        )

    def test_all_displayed_travel_coordinates_share_bold_link_markup(self) -> None:
        from PySide6.QtCore import Qt
        from app.modules.encyclopedia.services.guide_quest_view_model import (
            DisplaySolutionBlock,
        )
        from app.modules.encyclopedia.views.guides_view import (
            linkify_travel_text,
            solution_text_document,
            text_label,
        )

        coordinates = "Rejoindre [-2,13], puis vérifier [5,-6]."
        html = linkify_travel_text(coordinates)
        self.assertEqual(html.count("<b>"), 2)
        self.assertIn("atlas-travel:-2,13", html)
        self.assertIn("atlas-travel:5,-6", html)
        self.assertNotIn("font-size:", html)

        for label in (
            text_label(coordinates, "QuestLaunchPosition"),
            solution_text_document(
                (DisplaySolutionBlock("text", coordinates),)
            ),
        ):
            try:
                self.assertEqual(label.textFormat(), Qt.RichText)
                self.assertIn("<b>", label.text())
                self.assertEqual(label.styleSheet(), "")
            finally:
                label.deleteLater()

    def test_right_column_round_trip_preserves_quest_and_scroll(self) -> None:
        # clear() is sufficient for layout tests; no game catalogue is fetched.
        sheet = QuestDetailView(object(), object(), object())
        sheet.resize(1050, 700)
        sheet.show()
        try:
            sheet.right_layout.insertWidget(0, QLabel("Détail local"))
            self.app.processEvents()
            # An explicit range tests the scrollbar contract independently of
            # offscreen Qt platform geometry and its varying size hints.
            bar = sheet.right_scroll.verticalScrollBar()
            bar.setRange(0, 240)
            bar.setValue(120)
            expected = bar.value()
            self.assertEqual(expected, 120)
            self.assertFalse(sheet.right_panel.isHidden())
            self.assertIs(sheet.splitter.widget(1), sheet.right_panel)
            self.assertIsInstance(sheet.right_panel_toggle, AtlasPanelToggle)
            self.assertEqual(sheet.right_panel_toggle.objectName(), "GuideRightPanelToggle")
            self.assertEqual(sheet.right_panel_toggle.text(), "›")

            sheet.right_panel_toggle.click()
            self.assertTrue(sheet.right_panel.isHidden())
            self.assertTrue(sheet._right_panel_collapsed)
            self.assertEqual(sheet._right_panel_scroll_position, expected)
            self.assertEqual(sheet.right_panel_toggle.text(), "‹")
            self.assertIn("Réafficher", sheet.right_panel_toggle.accessibleName())

            sheet.right_panel_toggle.click()
            self.app.processEvents()
            self.assertFalse(sheet.right_panel.isHidden())
            self.assertFalse(sheet._right_panel_collapsed)
            self.assertGreaterEqual(sheet.splitter.sizes()[1], 240)
            self.assertEqual(bar.value(), min(expected, bar.maximum()))
            self.assertEqual(sheet.right_panel_toggle.text(), "›")
            self.assertIn("Masquer", sheet.right_panel_toggle.toolTip())

            sheet.right_panel_toggle.click()
            sheet.clear("Pas de quête sélectionnée")
            self.assertTrue(sheet.right_panel.isHidden())
            sheet.right_panel_toggle.click()
            self.assertFalse(sheet.right_panel.isHidden())
        finally:
            sheet.close()
            sheet.deleteLater()
            self.app.processEvents()

    def test_embedded_guide_context_uses_same_reversible_control(self) -> None:
        from PySide6.QtCore import Qt
        from app.modules.encyclopedia.widgets.quest_detail_view import QuestViewContext

        sheet = QuestDetailView(object(), object(), object())
        sheet.context = QuestViewContext(host="guides", guide_id="guide_local")
        context = sheet.context
        try:
            self.assertTrue(bool(sheet.right_panel_toggle.focusPolicy() & Qt.TabFocus))
            sheet.set_right_panel_collapsed(True)
            self.assertTrue(sheet.right_panel.isHidden())
            self.assertTrue(sheet.right_panel_toggle.property("collapsed"))
            sheet.set_right_panel_collapsed(True)  # Repeated signal is inert.
            sheet.set_right_panel_collapsed(False)
            self.assertFalse(sheet.right_panel.isHidden())
            self.assertFalse(sheet.right_panel_toggle.property("collapsed"))
            self.assertIs(sheet.context, context)
            self.assertEqual(context.host, "guides")
        finally:
            sheet.deleteLater()
            self.app.processEvents()

    def test_right_toggle_uses_shared_unity_theme(self) -> None:
        css = atlas_stylesheet()
        self.assertIn("QToolButton#GuideRightPanelToggle", css)
        self.assertIn("border: 1px solid " + THEME_TOKENS["BORDER"], css)
        self.assertIn('QToolButton#GuideRightPanelToggle[collapsed="true"]', css)


if __name__ == "__main__":
    unittest.main()
