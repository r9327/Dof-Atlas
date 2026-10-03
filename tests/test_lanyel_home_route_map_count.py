from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import AchievementProgressService, GuideProgressService
from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
    GuideCatalogManualRuntimeService,
)
from app.modules.encyclopedia.services.guide_catalog_route_stats import catalog_route_map_count
from app.modules.encyclopedia.views.deferred_achievement_guides_view import DeferredAchievementGuidesView
from app.modules.encyclopedia.views.guides_view import GuideHomeCard


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
            AchievementProgressService(achievement_progress),
            GuideProgressService(guide_progress),
        )

    def test_lightweight_map_count_matches_real_manual_route(self) -> None:
        guide = self.guide_provider.get_by_id("dofus_sylvestre")
        self.assertIsNotNone(guide)
        lightweight = catalog_route_map_count(guide, self.quest_provider)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _quest_path, achievement_progress, guide_progress = self._services(root)
            runtime = GuideCatalogManualRuntimeService(
                None,
                achievement_progress,
                guide_progress,
                guide=guide,
                quest_provider=self.quest_provider,
            )
            self.assertGreater(lightweight, 0)
            self.assertEqual(lightweight, len(runtime.cards))

    def test_home_card_shows_optimized_route_map_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            quest_path, achievement_progress, guide_progress = self._services(root)
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

            card = next(
                candidate
                for candidate in view.home_content.findChildren(GuideHomeCard)
                if candidate.guide.id == "dofus_sylvestre"
            )
            meta = card.findChild(QLabel, "GuideHomeCardMeta")
            self.assertIsNotNone(meta)
            count = catalog_route_map_count(
                self.guide_provider.get_by_id("dofus_sylvestre"),
                self.quest_provider,
            )
            self.assertEqual(meta.text(), f"Parcours optimisé · {count} maps")

            view.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
