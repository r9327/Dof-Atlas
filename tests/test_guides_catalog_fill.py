from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.constants import KEY_SESSION_ORDER
from app.modules.encyclopedia.constants import ENCYCLOPEDIA_TABS
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import AchievementProgressService, GuideProgressService
from app.modules.encyclopedia.services.guide_catalog_builder import GuideCatalogBuilder
from app.modules.encyclopedia.tools import validate_guides
from app.modules.encyclopedia.views import EncyclopediaPage, GuidesView
from app.modules.encyclopedia.views.guides_view import QuestLine
from app.modules.encyclopedia.widgets import GUIDE_GROUP_ROLE
from app.quest_catalog import load_quest_progress, quest_done, set_quest_done

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "encyclopedia" / "guides" / "catalog.json"


class GuideCatalogFillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.quest_provider = QuestProvider()
        cls.achievement_provider = AchievementProvider(quest_provider=cls.quest_provider)
        cls.provider = GuideProvider(quest_provider=cls.quest_provider, achievement_provider=cls.achievement_provider)
        cls.guides = cls.provider.load_all()
        cls.by_id = {guide.id: guide for guide in cls.guides}

    def test_catalog_categories_are_strict_and_guides_are_grouped(self):
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        self.assertEqual([category["id"] for category in catalog["categories"]], ["aventure", "dofus", "alignements"])
        self.assertFalse(any(category["id"] == "divers" for category in catalog["categories"]))

        with tempfile.TemporaryDirectory() as tmp:
            view = self._make_guides_view(Path(tmp))
            self.assertFalse(hasattr(view, "category_buttons"))
            self.assertFalse(hasattr(view, "set_category"))
            groups = [
                view.result_model.data(view.result_model.index(row, 0), GUIDE_GROUP_ROLE)
                for row in range(view.result_model.rowCount())
            ]
            self.assertEqual([group for group in groups if group], ["AVENTURE", "DOFUS", "ALIGNEMENTS"])
            self.assertEqual(view.splitter.count(), 3)
            self.assertFalse(hasattr(view, "filter_panel"))
            view.deleteLater()
            self.app.processEvents()

    def test_adventure_guide_exists_and_uses_real_doduda_steps(self):
        guide = self.by_id["guide_complet"]
        self.assertEqual(guide.title, "Aventure Full Succès")
        self.assertEqual(guide.category, "aventure")
        self.assertEqual((guide.recommended_level_min, guide.recommended_level_max), (1, 200))
        self.assertEqual(guide.completeness_status, "partial")
        self.assertGreaterEqual(len(guide.sections), 6)
        first_quests = [step.entity_id for step in guide.steps if step.step_type == "quest"][:5]
        self.assertIn(2502, first_quests)
        self.assertEqual(len(first_quests), 5)
        self.assertTrue(all(self.quest_provider.get_quest(quest_id) is not None for quest_id in first_quests))

    def test_dofus_guides_have_valid_objects_images_and_turquoise_is_preserved(self):
        dofus_guides = [guide for guide in self.guides if guide.category == "dofus"]
        self.assertGreaterEqual(len(dofus_guides), 6)
        for guide in dofus_guides:
            self.assertIsNotNone(guide.reward_item_id, guide.id)
            self.assertIsNotNone(guide.illustration_item_id, guide.id)
            self.assertTrue(Path(guide.image_path).exists(), guide.id)
            self.assertFalse(str(guide.image_path).startswith("http"), guide.id)
        turquoise = self.by_id["dofus_turquoise"]
        self.assertEqual(turquoise.reward_item_id, 739)
        self.assertEqual(turquoise.illustration_item_id, 739)
        self.assertIn(1385, [ref.entity_id for ref in turquoise.context_entities if ref.entity_type == "achievement"])
        self.assertFalse([step for step in turquoise.steps if step.step_type == "achievement"])
        quest_ids = [step.entity_id for step in turquoise.steps if step.step_type == "quest"]
        self.assertTrue({1653, 1654, 1656, 1657, 1658, 1659, 1660, 1661, 1662, 1663}.issubset(quest_ids))
        self.assertEqual(len(quest_ids), len(set(quest_ids)))
        self.assertTrue(all(self.quest_provider.get_quest(quest_id) is not None for quest_id in quest_ids))

    def test_alignment_guides_exist_are_separated_and_ordered(self):
        bonta = self.by_id["alignement_bonta"]
        brakmar = self.by_id["alignement_brakmar"]
        bonta_quests = [step.entity_id for step in bonta.steps if step.step_type == "quest" and not step.optional]
        brakmar_quests = [step.entity_id for step in brakmar.steps if step.step_type == "quest" and not step.optional]
        self.assertEqual(len(bonta_quests), 100)
        self.assertEqual(len(brakmar_quests), 100)
        self.assertEqual(bonta_quests[:3], [55, 56, 57])
        self.assertEqual(brakmar_quests[:3], [375, 376, 377])
        self.assertFalse(set(bonta_quests) & set(brakmar_quests))
        self.assertTrue(all("Bonta" in self.quest_provider.get_quest(quest_id).category for quest_id in bonta_quests))
        self.assertTrue(all("Brâkmar" in self.quest_provider.get_quest(quest_id).category for quest_id in brakmar_quests))

    def test_grouped_list_and_search_cover_required_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self._make_guides_view(Path(tmp))
            self.assertGreaterEqual(len(view.visible_guides), 19)
            groups = [
                view.result_model.data(view.result_model.index(row, 0), GUIDE_GROUP_ROLE)
                for row in range(view.result_model.rowCount())
            ]
            self.assertEqual([group for group in groups if group], ["AVENTURE", "DOFUS", "ALIGNEMENTS"])
            view.set_search_text("incarnam")
            self.assertTrue(any(guide.id == "guide_complet" for guide in view.visible_guides))
            view.set_search_text("plongeon et dragon")
            self.assertTrue(any(guide.id == "dofus_turquoise" for guide in view.visible_guides))
            view.set_search_text("bonta")
            self.assertTrue(any(guide.id == "alignement_bonta" for guide in view.visible_guides))
            view.deleteLater()
            self.app.processEvents()

    def test_common_quest_and_character_progress_are_shared(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self._make_guides_view(Path(tmp))
            progress = load_quest_progress(view.quest_progress_path)
            set_quest_done(progress, "character:1", 1463, True, view.quest_progress_path)
            view.refresh_external_progress()
            emeraude = self.by_id["dofus_emeraude"]
            adventure = self.by_id["guide_complet"]
            emeraude_step = next(step for step in emeraude.steps if step.step_type == "quest" and step.entity_id == 1463)
            adventure_step = next(step for step in adventure.steps if step.step_type == "quest" and step.entity_id == 1463)
            self.assertTrue(view.step_completed(emeraude, emeraude_step))
            self.assertTrue(view.step_completed(adventure, adventure_step))
            self.assertFalse(quest_done(load_quest_progress(view.quest_progress_path), "character:2", 1463))
            view.deleteLater()
            self.app.processEvents()

    def test_partial_draft_hide_completed_and_tools(self):
        self.assertTrue(any(guide.completeness_status == "partial" for guide in self.guides))
        self.assertFalse(any(guide.completeness_status == "draft" for guide in self.guides))
        builder = GuideCatalogBuilder()
        result = builder.build()
        self.assertEqual([category["id"] for category in result.catalog["categories"]], ["aventure", "dofus", "alignements"])
        self.assertGreaterEqual(len(result.report["guides_non_ajoutes"]), 1)
        self.assertEqual(result.report["schema_version"], 2)
        self.assertIn("v4_summary", result.report)

        with tempfile.TemporaryDirectory() as tmp:
            view = self._make_guides_view(Path(tmp))
            guide = self.by_id["dofus_turquoise"]
            progress = load_quest_progress(view.quest_progress_path)
            for step in guide.required_steps:
                if step.step_type != "quest" or step.entity_id is None:
                    continue
                set_quest_done(progress, "character:1", step.entity_id, True, view.quest_progress_path)
                progress = load_quest_progress(view.quest_progress_path)
            view.refresh_external_progress()
            self.assertEqual(view.guide_state(guide), "Terminé")
            view.select_guide("dofus_turquoise")
            self.app.processEvents()
            self.assertTrue(any(item.id == "dofus_turquoise" for item in view.visible_guides))
            line = next(
                child
                for child in view.findChildren(QuestLine)
                if child.step.step_type == "quest" and child.step.entity_id == 1653
            )
            line.selected.emit(1653)
            self.app.processEvents()
            self.assertEqual(view.state, view.QUEST_DETAIL)
            self.assertEqual(view.current_quest_id, 1653)
            view.deleteLater()
            self.app.processEvents()

    def test_validator_rejects_invalid_category_fake_id_and_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._write_catalog_case(tmp_path, "bad_category", "divers", [{"id": "s", "steps": [{"id": "a", "type": "info"}]}])
            self.assertNotEqual(validate_guides.main(["--guides-dir", str(tmp_path)]), 0)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._write_catalog_case(tmp_path, "fake_quest", "aventure", [{"id": "s", "steps": [{"id": "a", "type": "quest", "entity_id": 999999999}]}])
            self.assertNotEqual(validate_guides.main(["--guides-dir", str(tmp_path)]), 0)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._write_catalog_case(
                tmp_path,
                "cycle",
                "aventure",
                [
                    {
                        "id": "s",
                        "steps": [
                            {"id": "a", "type": "quest", "entity_id": 1653, "prerequisites": [{"type": "quest", "entity_id": 1654}]},
                            {"id": "b", "type": "quest", "entity_id": 1654, "prerequisites": [{"type": "quest", "entity_id": 1653}]},
                        ],
                    }
                ],
            )
            self.assertNotEqual(validate_guides.main(["--guides-dir", str(tmp_path)]), 0)

    def test_write_missing_does_not_replace_existing_guide_and_no_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            existing = tmp_path / "dofus_turquoise.json"
            existing.write_text('{"sentinel": true}', encoding="utf-8")
            builder = GuideCatalogBuilder(guides_dir=tmp_path)
            builder.write_missing(builder.build())
            self.assertEqual(json.loads(existing.read_text(encoding="utf-8")), {"sentinel": True})

        original_socket = socket.socket

        def forbidden_socket(*_args, **_kwargs):
            raise AssertionError("network call forbidden")

        socket.socket = forbidden_socket
        try:
            provider = GuideProvider()
            self.assertGreater(len(provider.load_all()), 0)
            builder = GuideCatalogBuilder()
            self.assertGreater(len(builder.build().guides), 0)
        finally:
            socket.socket = original_socket

    def test_tabs_match_current_encyclopedia_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile, client_index, quest_progress, achievement_progress, guide_progress, owned = self._temp_paths(tmp_path)
            page = EncyclopediaPage(
                lambda _text: None,
                quest_provider=self.quest_provider,
                achievement_provider=self.achievement_provider,
                guide_provider=self.provider,
                progress_path=quest_progress,
                achievement_progress_path=achievement_progress,
                guide_progress_path=guide_progress,
                profile_path=profile,
                client_index_path=client_index,
                owned_items_path=owned,
            )
            self.assertEqual(page.tab_labels(), list(ENCYCLOPEDIA_TABS))
            self.assertIn("SUCCÈS", page.tab_labels())
            page.deleteLater()
            self.app.processEvents()

    def _make_guides_view(self, tmp_path: Path) -> GuidesView:
        _profile, _client_index, quest_progress, achievement_progress, guide_progress, _owned = self._temp_paths(tmp_path)
        view = GuidesView(
            lambda _text: None,
            provider=self.provider,
            achievement_progress_service=AchievementProgressService(achievement_progress),
            guide_progress_service=GuideProgressService(guide_progress),
            quest_progress_path=quest_progress,
        )
        view.set_character_key("character:1")
        return view

    @staticmethod
    def _temp_paths(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path, Path]:
        profile_path = tmp_path / "client_profiles.json"
        client_index_path = tmp_path / "client_index.json"
        quest_progress_path = tmp_path / "quest_progress.json"
        achievement_progress_path = tmp_path / "achievement_progress.json"
        guide_progress_path = tmp_path / "guide_progress.json"
        owned_items_path = tmp_path / "craft_selection.json"
        profile_path.write_text(json.dumps({KEY_SESSION_ORDER: ["alpha", "beta", "", "", "", "", "", ""]}), encoding="utf-8")
        client_index_path.write_text(json.dumps({"clients": [{"index": 1, "name": "Alpha", "handle": 1001}]}), encoding="utf-8")
        quest_progress_path.write_text(json.dumps({"version": 1, "characters": {}}), encoding="utf-8")
        owned_items_path.write_text(json.dumps({"items": []}), encoding="utf-8")
        return profile_path, client_index_path, quest_progress_path, achievement_progress_path, guide_progress_path, owned_items_path

    @staticmethod
    def _write_catalog_case(tmp_path: Path, guide_id: str, category: str, sections: list[dict[str, object]]) -> None:
        guide_path = tmp_path / f"{guide_id}.json"
        guide_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": guide_id,
                    "title": guide_id,
                    "category": category,
                    "completeness_status": "complete",
                    "verified_steps": sum(len(section.get("steps", [])) for section in sections),
                    "total_steps": sum(len(section.get("steps", [])) for section in sections),
                    "sections": sections,
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "catalog.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "categories": [{"id": category, "label": category, "order": 10}],
                    "guides": [{"id": guide_id, "file": guide_path.name, "category": category, "order": 10, "enabled": True}],
                }
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
