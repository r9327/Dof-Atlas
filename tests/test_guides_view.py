"""Direct Qt regression contracts for the rich GuidesView presentation."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar

from app.modules.encyclopedia.services.guide_quest_view_model import DisplaySolutionBlock
from app.modules.encyclopedia.views.guides_view import (
    GuidesView, clear_layout, linkify_travel_text, progress_summary, solution_text_document, text_label,
)
from app.ui.entity_link_roles import ENTITY_LINK_COLOR_ROLES
from app.ui.theme import PALETTE
from app.ui.components import AtlasPanelToggle


class _Provider:
    guides = ()

    def load_all(self):
        return list(self.guides)

    def search(self, query):
        return []


class GuidesViewLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_compact_guide_progress_uses_shared_bar_with_real_route_count(self):
        for completed, total, maximum in ((2, 3, 3), (0, 0, 1), (5, 4, 4)):
            with self.subTest(completed=completed, total=total):
                row = progress_summary(completed, total)
                try:
                    bar = row.findChild(QProgressBar)
                    self.assertEqual(bar.objectName(), "GuideTinyProgress")
                    self.assertEqual((bar.minimum(), bar.maximum()), (0, maximum))
                    self.assertEqual(bar.value(), min(completed, total) if total else 0)
                    self.assertFalse(bar.isTextVisible())
                finally:
                    row.deleteLater()

    def test_guide_layout_cleanup_handles_nested_rows_and_spacers(self):
        host = QWidget()
        outer = QVBoxLayout(host)
        nested = QHBoxLayout()
        label = QLabel("old Guide")
        nested.addWidget(label)
        outer.addLayout(nested)
        outer.addStretch(1)
        try:
            clear_layout(outer)
            self.assertEqual(outer.count(), 0)
            self.assertEqual(nested.count(), 0)
            self.assertIsNone(label.parent())
        finally:
            host.deleteLater()

    def test_shared_quest_and_guide_coordinates_are_bold_unity_links(self):
        markup = linkify_travel_text("Parler à [ -1,2] puis [-12, 34] & <npc>")
        self.assertIn("<b>[-12,34]</b>", markup)
        self.assertIn('href="atlas-travel:-12,34"', markup)
        self.assertIn(
            f'color:{PALETTE[ENTITY_LINK_COLOR_ROLES["position"]]}',
            markup,
        )
        self.assertIn("&lt;npc&gt;", markup)
        self.assertIn("&amp;", markup)

        label = text_label("Aller en [-12,34] pour la quête", "QuestLaunchPosition")
        try:
            self.assertEqual(label.textFormat(), Qt.RichText)
            self.assertIn("<b>[-12,34]</b>", label.text())
            label.linkActivated.emit("atlas-travel:-12,34")
            self.assertEqual(
                QApplication.clipboard().text(), "/travel -12,34"
            )
        finally:
            label.deleteLater()

    def test_documentary_dimension_coordinates_are_bold_without_a_travel_link(self):
        instruction = "Entrer dans Osavora [1,17!] & parler au PNJ."
        for label in (
            text_label(instruction, "QuestLaunchPosition"),
            solution_text_document((DisplaySolutionBlock("text", instruction),)),
        ):
            try:
                self.assertEqual(label.textFormat(), Qt.RichText)
                self.assertIn("<b>[1,17!]</b>", label.text())
                self.assertIn("&amp;", label.text())
                self.assertNotIn("atlas-travel:", label.text())
            finally:
                label.deleteLater()

        mixed = linkify_travel_text("Départ [-22,-24] ou dimension [1,17!].")
        self.assertEqual(mixed.count("atlas-travel:"), 1)
        self.assertIn('href="atlas-travel:-22,-24"', mixed)
        self.assertIn("<b>[1,17!]</b>", mixed)

    def test_detail_breadcrumb_precedes_title_header(self):
        class QuestDetailStub(QWidget):
            questProgressChanged = Signal()

            def __init__(self, *args, **kwargs):
                super().__init__()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "app.modules.encyclopedia.widgets.quest_detail_view.QuestDetailView",
                QuestDetailStub,
            ):
                view = GuidesView(
                    lambda _message: None, provider=_Provider(),
                    quest_progress_path=root / "quests.json",
                    achievement_progress_path=root / "achievements.json",
                    guide_progress_path=root / "guides.json",
                    profile_path=root / "profile.json",
                    client_index_path=root / "clients.json",
                    defer_runtime=True,
                )
                try:
                    detail = view.build_detail_page()
                    try:
                        layout = detail.layout()
                        self.assertIs(layout.itemAt(0).widget(), view.breadcrumb)
                        self.assertIs(layout.itemAt(1).widget(), view.detail_header)
                        self.assertIs(layout.itemAt(2).widget(), view.detail_stack)
                        # Guide and Quêtes use the same Unity selector and
                        # keyboard-accessible collapse/restore states.
                        toggle = view.right_panel_toggle
                        self.assertIsInstance(toggle, AtlasPanelToggle)
                        self.assertEqual(toggle.objectName(), "GuideRightPanelToggle")
                        self.assertTrue(bool(toggle.focusPolicy() & Qt.TabFocus))
                        self.assertFalse(toggle.property("collapsed"))
                        toggle.click()
                        self.assertTrue(view.right_panel.isHidden())
                        self.assertTrue(toggle.property("collapsed"))
                        self.assertEqual(toggle.text(), "‹")
                        self.assertIn("Réafficher", toggle.accessibleName())
                        toggle.click()
                        self.assertFalse(view.right_panel.isHidden())
                        self.assertFalse(toggle.property("collapsed"))
                        self.assertEqual(toggle.text(), "›")
                    finally:
                        detail.deleteLater()
                finally:
                    view.deleteLater()
                    self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
