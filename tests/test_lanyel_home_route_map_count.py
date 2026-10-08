from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import (
    AchievementProgressService,
    GuideProgressService,
    QuestProgressService,
)
from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
    GuideCatalogManualRuntimeService,
)
from app.modules.encyclopedia.services.guide_catalog_route_stats import (
    catalog_route_map_count,
    catalog_route_map_count_hint,
)
from app.modules.encyclopedia.views.deferred_achievement_guides_view import DeferredAchievementGuidesView


class LanyelHomeRouteMapCountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.quest_provider = QuestProvider()
        cls.achievement_provider = AchievementProvider(quest_provider=cls.quest_provider)
        cls.achievement_provider.load_all()
        cls.guide_provider = GuideProvider(
            quest_provider=cls.quest_provider,
            achievement_provider=cls.achievement_provider,
        )
        cls.guide_provider.load_all()

    def _services(self, root: Path):
        quest_progress = root / "quest_progress.json"
        achievement_progress = root / "achievement_progress.json"
        guide_progress = root / "guide_progress.json"
        for path in (quest_progress, achievement_progress, guide_progress):
            path.write_text("{}", encoding="utf-8")
        return (
            quest_progress,
            QuestProgressService(quest_progress),
            AchievementProgressService(achievement_progress),
            GuideProgressService(guide_progress),
        )

    def test_exact_map_count_matches_real_manual_route(self) -> None:
        guide = self.guide_provider.get_by_id("dofus_sylvestre")
        self.assertIsNotNone(guide)
        exact = catalog_route_map_count(guide, self.quest_provider)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _quest_path, quest_progress, achievement_progress, guide_progress = self._services(root)
            runtime = GuideCatalogManualRuntimeService(
                quest_progress,
                achievement_progress,
                guide_progress,
                guide=guide,
                quest_provider=self.quest_provider,
            )
            self.assertGreater(exact, 0)
            self.assertEqual(exact, len(runtime.cards))

    def test_home_card_shows_certified_lightweight_route_hint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            quest_path, _quest_progress, achievement_progress, guide_progress = self._services(root)
            view = DeferredAchievementGuidesView(
                lambda _text: None,
                provider=self.guide_provider,
                quest_provider=self.quest_provider,
                achievement_provider=self.achievement_provider,
                achievement_progress_service=achievement_progress,
                guide_progress_service=guide_progress,
                quest_progress_path=quest_path,
            )
            view.set_character_key("character:lanyel-home-maps")
            view.refresh_home()
            self.app.processEvents()

            guide = self.guide_provider.get_by_id("dofus_sylvestre")
            self.assertIsNotNone(guide)
            row = view.result_model.row_for_guide("dofus_sylvestre")
            self.assertGreaterEqual(row, 0)
            count = catalog_route_map_count_hint("dofus_sylvestre")
            self.assertEqual(count, 237)
            self.assertEqual(
                view.result_model.display_subtitle(guide),
                f"Parcours optimisé · {count} maps",
            )

            view.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
