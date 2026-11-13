"""Direct Qt regression contracts for the rich GuidesView presentation."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QWidget

from app.modules.encyclopedia.views.guides_view import GuidesView


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
