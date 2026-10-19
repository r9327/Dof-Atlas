"""Qt proof of manual Ganymède source navigation, not a mock button shell."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.services.guide_progress_service import (
    GuideProgressService,
)
from app.modules.encyclopedia.views.guide_continuous_route_panel import (
    ContinuousGuideRoutePanel,
)
from tests.test_guide_continuous_navigation import _source_route


class ContinuousGuideRoutePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = GuideProgressService(Path(temp.name) / "guide_progress.json")
        self.panel = ContinuousGuideRoutePanel(
            _source_route(), self.store, ("character:1", "character:2"),
        )
        self.addCleanup(self.panel.deleteLater)

    def test_actual_summary_and_navigation_keep_popup_open(self):
        self.assertEqual(
            self.panel.navigation.position().viewed_step_id,
            "ganymede_2205_step_0001",
        )
        self.assertEqual(self.panel.title_label.text(), "Fiche 1")
        self.assertTrue(self.panel.summary.isVisibleTo(self.panel))
        self.panel.next_button.click()
        self.assertEqual(
            self.panel.navigation.position().viewed_step_id,
            "ganymede_2205_step_0002",
        )
        self.assertTrue(self.panel.summary.isVisibleTo(self.panel))
        self.panel.actual_button.click()
        self.assertEqual(
            self.panel.navigation.position().viewed_step_id,
            "ganymede_2205_step_0001",
        )
        self.assertTrue(self.panel.summary.isVisibleTo(self.panel))
        self.panel.summary_toggle.click()
        self.assertFalse(self.panel.summary.isVisible())
        self.panel.next_button.click()
        self.assertFalse(self.panel.summary.isVisible())
        self.panel.summary_toggle.click()
        self.assertTrue(self.panel.summary.isVisibleTo(self.panel))

    def test_validation_is_real_and_per_character_only(self):
        self.panel.validate_button.click()
        step = "ganymede_2205_step_0001"
        self.assertTrue(self.store.is_manual_step_completed("character:1", "dofus_cawotte", step))
        self.assertTrue(self.store.is_manual_step_completed("character:2", "dofus_cawotte", step))
        self.assertEqual(self.panel.navigation.position().actual_step_id,
                         "ganymede_2205_step_0002")
        self.panel.actual_button.click()
        self.assertEqual(self.panel.navigation.position().viewed_step_id,
                         "ganymede_2205_step_0002")
        self.panel.set_characters(["character:1"])
        self.panel.show_step(step)
        self.panel.validate_button.click()
        self.assertFalse(self.store.is_manual_step_completed("character:1", "dofus_cawotte", step))
        self.assertTrue(self.store.is_manual_step_completed("character:2", "dofus_cawotte", step))
        self.assertEqual(self.panel.navigation.position().actual_step_id, step)

    def test_no_characters_block_manual_completion(self):
        self.panel.set_characters(())
        self.assertFalse(self.panel.actual_button.isEnabled())
        self.assertFalse(self.panel.validate_button.isEnabled())
        before = self.store.manual_steps("character:1", "dofus_cawotte")
        self.panel.validate_button.click()
        self.assertEqual(before, self.store.manual_steps("character:1", "dofus_cawotte"))


if __name__ == "__main__":
    unittest.main()
