from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.providers import (
    AchievementProvider, GuideProvider, QuestProvider,
)
from app.modules.encyclopedia.services.guide_progress_service import (
    GuideProgressService,
)
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)
from app.modules.encyclopedia.services.guide_imported_manual_runtime_service import (
    ImportedSourceManualRuntimeService,
)
from app.modules.encyclopedia.views.manual_route_guides_view import (
    ManualRouteGuidesView,
)
from app.modules.encyclopedia.views.shared_manual_guide_view import (
    SharedGuideManualView,
)
from tests.test_guide_imported_manual_runtime_service import _source_route
from tests.test_guide_ultime_manual_ui_navigation import _FakeParticipantService


class ImportedSourceRouterQtTests(unittest.TestCase):
    """Existing Guide router and shared Qt reader; never a live guide export."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.quests = QuestProvider()
        cls.achievements = AchievementProvider(quest_provider=cls.quests)
        cls.provider = GuideProvider(
            quest_provider=cls.quests, achievement_provider=cls.achievements,
        )

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.progress_path = root / "guide_progress.json"
        self.progress = GuideProgressService(self.progress_path)
        self.achievement_progress = AchievementProgressService(
            root / "achievement_progress.json"
        )
        from app.modules.encyclopedia.services.quest_progress_service import (
            QuestProgressService,
        )
        self.quest_progress = QuestProgressService(root / "quest_progress.json")
        self.service = ImportedSourceManualRuntimeService(
            self.quest_progress,
            self.achievement_progress,
            self.progress,
            route=_source_route(),
        )
        self.approved = False
        self.authorization_calls: list[str] = []
        self.messages: list[str] = []

        def approve(guide_id: str, route: dict) -> bool:
            self.authorization_calls.append(guide_id)
            self.assertEqual(route["id"], guide_id)
            return self.approved

        self.view = ManualRouteGuidesView(
            self.messages.append,
            provider=self.provider,
            quest_provider=self.quests,
            achievement_provider=self.achievements,
            achievement_progress_service=self.achievement_progress,
            guide_progress_service=self.progress,
            quest_progress_path=root / "quest_progress.json",
            profile_path=root / "profiles.json",
            client_index_path=root / "clients.json",
            character_key="character:1",
            defer_runtime=True,
            imported_source_services={self.service.guide_id: self.service},
            imported_source_authorizer=approve,
        )
        self.view.guide_participant_service = _FakeParticipantService()
        self.addCleanup(self._close_view)

    def _close_view(self) -> None:
        self.view.close()
        self.view.deleteLater()
        QApplication.processEvents()

    def test_denied_source_cannot_fall_through_to_legacy_or_load_cached_route(self):
        self.assertFalse(self.view.select_guide(self.service.guide_id))
        self.assertEqual(self.view.state, self.view.CATALOG)
        self.assertIsNone(self.view.current_guide_id)
        self.assertEqual(self.view.stack.currentWidget(), self.view.home_page)
        self.assertFalse(self.view._catalog_manual_services)
        self.assertFalse(self.view._catalog_manual_views)
        self.assertIsNone(self.view.guide_ultime_view)
        self.assertFalse(self.progress_path.exists())
        self.assertTrue(any("non certifié" in text for text in self.messages))

    def test_authorized_source_uses_same_shared_reader_and_is_lazy(self):
        self.assertFalse(self.view._catalog_manual_views)
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        reader = self.view.stack.currentWidget()
        self.assertIsInstance(reader, SharedGuideManualView)
        self.assertIs(self.view._catalog_manual_views[self.service.guide_id], reader)
        self.assertEqual(self.view.current_guide_id, self.service.guide_id)
        self.assertEqual(self.view.state, self.view.GUIDE_OVERVIEW)
        self.assertIsNone(self.view.guide_ultime_view)
        self.assertNotIn("dofus_sylvestre", self.view._catalog_manual_services)
        self.assertEqual(reader.nav_page_label.text(), "Page 1 / 2")
        self.assertEqual(self.service.route_sheet_progress("character:1"), (0, 2))
        self.assertFalse(self.progress_path.exists())
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        self.assertIs(self.view.stack.currentWidget(), reader)

    def test_shared_validation_uses_source_id_and_does_not_touch_other_guides(self):
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        reader = self.view.stack.currentWidget()
        reader._show_index(0)
        QApplication.processEvents()
        reader.validation_layout.itemAt(0).widget().click()
        QApplication.processEvents()
        self.assertTrue(self.service.page_checked("character:1", self.service.cards[0]))
        self.assertFalse(self.service.page_checked("character:2", self.service.cards[0]))
        self.assertEqual(self.service.route_sheet_progress("character:1"), (1, 2))
        self.assertFalse(self.progress.manual_steps("character:1", "guide_ultime_v5"))
        self.assertFalse(self.progress.manual_steps(
            "character:1", "catalog_manual:dofus_sylvestre"
        ))
        self.view.set_character_key("character:2")
        reader._show_index(0)
        self.assertEqual(reader.route_progress_label.text(), "0 %")
        self.assertFalse(self.service.page_checked("character:2", self.service.cards[0]))

    def test_guide_specific_prerequisite_disables_validation_without_order_prompt(self):
        self.service.cards[0]["hard_runtime_gates"] = [
            {"kind": "alignment", "expected": "Bonta"}
        ]
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        reader = self.view.stack.currentWidget()
        reader._show_index(0)
        QApplication.processEvents()
        button = reader.validation_layout.itemAt(0).widget()
        self.assertFalse(button.isEnabled())
        self.assertEqual(button.text(), "Prérequis à vérifier")
        self.assertIn("prérequis", button.toolTip())
        self.assertFalse(self.progress_path.exists())
        self.assertFalse(self.service.manual_order_choice_blocking(
            "character:1", self.service.cards[1],
        ))

    def test_revocation_between_render_and_click_blocks_atomic_team_write(self):
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        reader = self.view.stack.currentWidget()
        reader._show_index(0)
        QApplication.processEvents()
        button = reader.validation_layout.itemAt(0).widget()
        self.assertTrue(button.isEnabled())
        # A trusted release can be revoked after this button was rendered.
        self.approved = False
        button.click()
        QApplication.processEvents()
        self.assertFalse(self.progress_path.exists())
        self.assertFalse(self.service.page_checked("character:1", self.service.cards[0]))
        refreshed = reader.validation_layout.itemAt(0).widget()
        self.assertFalse(refreshed.isEnabled())
        self.assertIn("non autorisé", refreshed.toolTip())
        self.service.set_page_checked("character:1", self.service.cards[0], 0, True)
        self.assertFalse(self.progress_path.exists())

    def test_revoked_authorization_blocks_reopen_and_exits_on_refresh(self):
        self.approved = True
        self.assertTrue(self.view.select_guide(self.service.guide_id))
        reader = self.view.stack.currentWidget()
        self.approved = False
        self.assertFalse(self.view.select_guide(self.service.guide_id))
        # Reopen attempts fail closed and never create a second Qt reader.
        self.assertIs(self.view._catalog_manual_views[self.service.guide_id], reader)
        self.view.refresh_external_progress()
        self.assertEqual(self.view.state, self.view.CATALOG)
        self.assertIsNone(self.view.current_guide_id)
        self.assertEqual(self.view.stack.currentWidget(), self.view.home_page)
        self.assertFalse(self.progress_path.exists())


if __name__ == "__main__":
    unittest.main()
