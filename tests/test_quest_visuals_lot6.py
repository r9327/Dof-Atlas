from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtGui import QImage

from app.constants import ROOT_DIR
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import QuestGraphService, QuestProgressService
from app.modules.encyclopedia.services.guide_quest_view_model import (
    quest_solution_blocks,
    quest_solution_steps,
    quest_start_info,
)
from app.modules.encyclopedia.tools.enrich_quests import save_image
import app.modules.encyclopedia.views.guides_view as guides_view_module
from app.modules.encyclopedia.views.guides_view import SolutionImageLabel
from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView, QuestViewContext
from app.quest_catalog import enrichment_solution_blocks, resolve_local_asset_path


class QuestVisualsLot6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        # These tests validate documentary selection and layout, not background
        # decoding. Prevent delayed image jobs from outliving widgets between
        # tests and calling back into deleted Qt objects.
        self._image_submit_patch = patch.object(
            guides_view_module.SOLUTION_IMAGE_EXECUTOR,
            "submit",
            return_value=None,
        )
        self._image_submit_patch.start()

    def tearDown(self) -> None:
        self._image_submit_patch.stop()

    def dispose_widget(self, widget) -> None:
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.DeferredDelete)

    def test_dispose_widget_does_not_drain_unrelated_qt_events(self) -> None:
        owner = QLabel()
        timer = QTimer(owner)
        timer.setSingleShot(True)
        calls: list[str] = []
        timer.timeout.connect(lambda: calls.append("called"))
        timer.start(0)

        target = QLabel()
        self.dispose_widget(target)

        self.assertEqual(calls, [])
        self.assertTrue(timer.isActive())
        timer.stop()
        owner.deleteLater()
        QCoreApplication.sendPostedEvents(owner, QEvent.DeferredDelete)

    def test_legacy_absolute_quest_image_is_rebased_to_current_checkout(self) -> None:
        relative = Path("data/encyclopedia/images/quests/260/step_01.webp")
        stale = Path("C:/Users/TestUser/Atlas") / relative
        resolved = Path(resolve_local_asset_path(stale))
        self.assertEqual(resolved, (ROOT_DIR / relative).resolve())
        self.assertTrue(resolved.exists())

    def test_ordered_blocks_keep_image_between_its_two_paragraphs(self) -> None:
        image = "C:/Users/TestUser/Atlas/data/encyclopedia/images/quests/260/step_01.webp"
        blocks = enrichment_solution_blocks(
            {
                "solution_blocks": [
                    {"order": 1, "type": "text", "content": "Avant l'image."},
                    {"order": 2, "type": "image", "image_path": image, "caption": "Le passage."},
                    {"order": 3, "type": "text", "content": "Après l'image."},
                ]
            }
        )
        self.assertEqual([block.block_type for block in blocks], ["text", "image", "text"])
        self.assertTrue(Path(blocks[1].image_path).exists())
        self.assertEqual(blocks[1].caption, "Le passage.")

    def test_enricher_reuses_moved_local_image_without_downloading_it_again(self) -> None:
        url = "https://example.test/quest-image.webp"
        stale = "C:/Users/TestUser/Atlas/data/encyclopedia/images/quests/260/step_01.webp"
        manifest = {"by_url": {url: {"path": stale, "sha256": "known"}}, "by_sha256": {}}
        stats = {"images_reused": 0, "images_downloaded": 0}
        path = save_image(url, 260, 1, 1, manifest, stats)
        self.assertEqual(path, "data/encyclopedia/images/quests/260/step_01.webp")
        self.assertEqual(stats["images_reused"], 1)
        self.assertEqual(stats["images_downloaded"], 0)

    def test_legacy_step_does_not_promote_unproven_assets_to_documentary_blocks(self) -> None:
        base = "C:/Users/TestUser/Atlas/data/encyclopedia/images/quests/260"
        blocks = enrichment_solution_blocks(
            {
                "solution_steps": [
                    {
                        "title": "Passage",
                        "objectives": [
                            {
                                "text": "Suivre le chemin.",
                                "images": [
                                    {"path": f"{base}/step_01.webp", "caption": "Premier"},
                                    {"path": f"{base}/step_02.webp", "caption": "Second"},
                                ],
                            }
                        ],
                    }
                ]
            }
        )
        self.assertEqual(blocks, [])

    def test_primary_catalog_exposes_ordered_local_visuals_to_shared_sheet(self) -> None:
        catalog = QuestProvider().get_catalog()
        quest = catalog.by_id[26]
        blocks = quest_solution_blocks(quest)
        images = [block for block in blocks if block.block_type == "image"]
        self.assertGreater(len(images), 1)
        self.assertTrue(all(Path(block.image_path).exists() for block in images))
        self.assertTrue(any(block.block_type != "image" for block in blocks))

    def test_local_examples_cover_zero_one_multiple_path_combat_and_mechanic(self) -> None:
        catalog = QuestProvider().get_catalog()

        without_image = quest_solution_blocks(catalog.by_id[2462])
        single_image = quest_solution_blocks(catalog.by_id[1851])
        rich_path = quest_solution_blocks(catalog.by_id[26])
        combat = quest_solution_blocks(catalog.by_id[29])

        self.assertFalse(any(block.block_type == "image" for block in without_image))
        self.assertEqual(sum(block.block_type == "image" for block in single_image), 1)
        self.assertGreater(sum(block.block_type == "image" for block in rich_path), 1)
        self.assertTrue(any(block.block_type == "position" for block in rich_path))
        self.assertTrue(any("dalle" in block.content.casefold() for block in rich_path))
        self.assertTrue(any(block.block_type == "combat" for block in combat))

    def test_shared_sheet_renders_same_multiple_images_for_every_host(self) -> None:
        quest_provider = QuestProvider()
        achievement_provider = AchievementProvider(quest_provider=quest_provider)
        guide_provider = GuideProvider(
            quest_provider=quest_provider,
            achievement_provider=achievement_provider,
        )
        graph = QuestGraphService(quest_provider, guide_provider, achievement_provider)
        with tempfile.TemporaryDirectory() as tmp:
            view = QuestDetailView(
                quest_provider,
                graph,
                QuestProgressService(Path(tmp) / "progress.json"),
                achievement_provider=achievement_provider,
                guide_provider=guide_provider,
            )
            for host in ("guide", "quests", "achievement"):
                self.assertTrue(view.show_quest(691, QuestViewContext(host=host)))
                self.assertEqual(len(view.findChildren(SolutionImageLabel)), 2)
            self.dispose_widget(view)

    def test_colonie_de_vaillance_uses_only_directly_validated_documentary_images(self) -> None:
        quest_provider = QuestProvider()
        quest = quest_provider.get_quest(2464)
        assert quest is not None
        start = quest_start_info(quest)
        self.assertEqual(start.position, "[38,-77]")
        self.assertEqual(start.zone, "Nouvelle Albuera")
        self.assertTrue(start.map_image_path)
        self.assertEqual(len(start.map_image_paths), 1)
        self.assertTrue(Path(start.map_image_path).is_file())
        blocks = quest_solution_blocks(quest)
        self.assertEqual(sum(block.block_type == "image" for block in blocks), 23)
        self.assertTrue(all(Path(block.image_path).is_file() for block in blocks if block.block_type == "image"))
        self.assertEqual(len(quest_solution_steps(quest)), 18)
        self.assertTrue(all(not step.title for step in quest_solution_steps(quest)))

        achievement_provider = AchievementProvider(quest_provider=quest_provider)
        guide_provider = GuideProvider(quest_provider=quest_provider, achievement_provider=achievement_provider)
        graph = QuestGraphService(quest_provider, guide_provider, achievement_provider)
        with tempfile.TemporaryDirectory() as tmp:
            view = QuestDetailView(
                quest_provider,
                graph,
                QuestProgressService(Path(tmp) / "progress.json"),
                achievement_provider=achievement_provider,
                guide_provider=guide_provider,
            )
            self.assertTrue(view.show_quest(2464))
            labels = [label.text() for label in view.center_panel.findChildren(QLabel)]
            self.assertTrue(any("Position de lancement" in text and "[38,-77]" in text for text in labels))
            self.assertFalse(any("Documentation locale complète indisponible" in text for text in labels))
            self.assertFalse(any(text.strip().upper() == "SOLUTION" for text in labels))
            self.assertFalse(any(text.strip().casefold().startswith("étape ") for text in labels))
            self.assertEqual(len(view.center_panel.findChildren(SolutionImageLabel)), 24)
            self.dispose_widget(view)

    def test_every_authorized_start_map_is_rendered_before_the_solution(self) -> None:
        quest_provider = QuestProvider()
        quest = quest_provider.get_quest(55)
        assert quest is not None
        start = quest_start_info(quest)
        self.assertEqual(len(start.map_image_paths), 2)
        self.assertTrue(all(Path(path).is_file() for path in start.map_image_paths))
        documentary_image_count = sum(block.block_type == "image" for block in quest_solution_blocks(quest))

        achievement_provider = AchievementProvider(quest_provider=quest_provider)
        guide_provider = GuideProvider(quest_provider=quest_provider, achievement_provider=achievement_provider)
        graph = QuestGraphService(quest_provider, guide_provider, achievement_provider)
        with tempfile.TemporaryDirectory() as tmp:
            view = QuestDetailView(
                quest_provider,
                graph,
                QuestProgressService(Path(tmp) / "progress.json"),
                achievement_provider=achievement_provider,
                guide_provider=guide_provider,
            )
            self.assertTrue(view.show_quest(55))
            self.assertEqual(
                len(view.center_panel.findChildren(SolutionImageLabel)),
                documentary_image_count + len(start.map_image_paths),
            )
            self.dispose_widget(view)

    def test_documentary_images_stay_in_source_flow_when_start_map_is_not_local(self) -> None:
        quest_provider = QuestProvider()
        quest = quest_provider.get_quest(72)
        assert quest is not None
        start = quest_start_info(quest)
        self.assertFalse(start.map_image_path)
        documentary_image_count = sum(block.block_type == "image" for block in quest_solution_blocks(quest))

        achievement_provider = AchievementProvider(quest_provider=quest_provider)
        guide_provider = GuideProvider(quest_provider=quest_provider, achievement_provider=achievement_provider)
        graph = QuestGraphService(quest_provider, guide_provider, achievement_provider)
        with tempfile.TemporaryDirectory() as tmp:
            view = QuestDetailView(
                quest_provider,
                graph,
                QuestProgressService(Path(tmp) / "progress.json"),
                achievement_provider=achievement_provider,
                guide_provider=guide_provider,
            )
            self.assertTrue(view.show_quest(72))
            images = view.center_panel.findChildren(SolutionImageLabel)
            self.assertEqual(len(images), documentary_image_count)
            labels = [label.text() for label in view.center_panel.findChildren(QLabel)]
            self.assertFalse(any(text.strip().upper() == "SOLUTION" for text in labels))
            self.dispose_widget(view)

    def test_solution_images_remain_compact_and_keep_their_aspect_ratio(self) -> None:
        path = ROOT_DIR / "data/encyclopedia/images/quests/1760/step_01.webp"
        label = SolutionImageLabel(str(path), "Test")
        label.resize(800, 500)
        label.show()
        label.finish_image_load(QImage(str(path)))
        pixmap = label.pixmap()
        self.assertIsNotNone(pixmap)
        assert pixmap is not None
        self.assertLessEqual(pixmap.width(), 520)
        self.assertLessEqual(pixmap.height(), 320)
        self.assertAlmostEqual(
            pixmap.width() / pixmap.height(),
            label.source.width() / label.source.height(),
            places=2,
        )
        self.dispose_widget(label)


if __name__ == "__main__":
    unittest.main()
