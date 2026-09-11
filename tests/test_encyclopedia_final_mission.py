from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from app.constants import KEY_SESSION_ORDER
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, ENCYCLOPEDIA_TABS
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.views import EncyclopediaPage
from app.modules.encyclopedia.views.guides_view import QuestLine
from app.quest_catalog import load_quest_progress, set_quest_done

ROOT = Path(__file__).resolve().parents[1]
GUIDES_DIR = ROOT / "data" / "encyclopedia" / "guides"
CATALOG_PATH = GUIDES_DIR / "catalog.json"


class EncyclopediaFinalMissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.quest_provider = QuestProvider()
        cls.achievement_provider = AchievementProvider(quest_provider=cls.quest_provider)
        cls.guide_provider = GuideProvider(quest_provider=cls.quest_provider, achievement_provider=cls.achievement_provider)

    def make_page(self, tmp_path: Path) -> EncyclopediaPage:
        profile = tmp_path / "client_profiles.json"
        client_index = tmp_path / "client_index.json"
        progress = tmp_path / "quest_progress.json"
        achievement_progress = tmp_path / "achievement_progress.json"
        guide_progress = tmp_path / "guide_progress.json"
        owned = tmp_path / "craft_selection.json"
        profile.write_text(json.dumps({KEY_SESSION_ORDER: ["alpha", "beta", "", "", "", "", "", ""]}), encoding="utf-8")
        client_index.write_text(json.dumps({"clients": [{"index": 1, "name": "Alpha", "handle": 1}]}), encoding="utf-8")
        progress.write_text(json.dumps({"version": 1, "characters": {}}), encoding="utf-8")
        owned.write_text(json.dumps({"items": []}), encoding="utf-8")
        return EncyclopediaPage(
            lambda _text: None,
            quest_provider=self.quest_provider,
            achievement_provider=self.achievement_provider,
            guide_provider=self.guide_provider,
            progress_path=progress,
            achievement_progress_path=achievement_progress,
            guide_progress_path=guide_progress,
            profile_path=profile,
            client_index_path=client_index,
            owned_items_path=owned,
        )

    def test_guide_catalog_is_local_and_covers_required_routes(self):
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        rows = [row for row in catalog.get("guides", []) if row.get("enabled", True)]
        by_id = {str(row.get("id") or ""): row for row in rows}
        self.assertGreaterEqual(len(rows), 20)
        self.assertIn("guide_complet", by_id)
        self.assertIn("dofus_turquoise", by_id)

        for row in rows:
            filename = str(row.get("file") or "").strip()
            self.assertTrue(filename, row)
            path = GUIDES_DIR / filename
            self.assertTrue(path.is_file(), row)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(str(payload.get("id") or ""), str(row.get("id") or ""), row)

        turquoise = json.loads((GUIDES_DIR / by_id["dofus_turquoise"]["file"]).read_text(encoding="utf-8"))
        self.assertIn("doduda", str(turquoise.get("generation_source") or ""))
        self.assertFalse(turquoise.get("source_urls") or [])

    def test_guides_and_quests_dashboards_have_fixed_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.tabs.setCurrentIndex(page.tab_labels().index("GUIDES"))
            self.assertEqual(page.guides_view.splitter.count(), 3)
            self.assertEqual(page.guides_view.splitter.handleWidth(), 0)
            self.assertFalse(hasattr(page.guides_view, "category_buttons"))
            page.tabs.setCurrentIndex(page.tab_labels().index("QUÊTES"))
            self.assertEqual(page.quest_page.splitter.count(), 2)
            self.assertEqual(page.quest_page.splitter.handleWidth(), 0)
            self.assertEqual(page.quest_page.MODES, ("PARCOURS", "DOFUS", "SUCCÈS LIÉS", "ZONES", "TOUTES"))
            self.assertEqual(page.tab_labels(), list(ENCYCLOPEDIA_TABS))
            self.assertIn(ACHIEVEMENTS_TAB, page.tab_labels())
            page.deleteLater()
            self.app.processEvents()

    def test_completed_guide_keeps_shared_quest_detail_inside_guides(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.tabs.setCurrentIndex(page.tab_labels().index("GUIDES"))
            guide = self.guide_provider.get_by_id("dofus_turquoise")
            assert guide is not None
            progress = load_quest_progress(page.guides_view.quest_progress_path)
            set_quest_done(progress, "character:1", 1653, True, page.guides_view.quest_progress_path)
            page.guides_view.refresh_external_progress()
            page.guides_view.select_guide("dofus_turquoise")
            line = next(
                row
                for row in page.guides_view.findChildren(QuestLine)
                if row.step.step_type == "quest" and row.step.entity_id == 1653
            )
            line.selected.emit(1653)
            self.app.processEvents()

            self.assertEqual(page.current_tab_label(), "GUIDES")
            self.assertEqual(page.guides_view.current_quest_id, 1653)
            self.assertEqual(page.guides_view.quest_detail_view.current_quest_id, 1653)
            labels = [label.text() for label in page.guides_view.quest_detail_view.findChildren(QLabel)]
            self.assertTrue(any(text == "Informations de quête" for text in labels))
            self.assertTrue(any("Plongeon et dragon" in text for text in labels))
            page.deleteLater()
            self.app.processEvents()

    def test_runtime_providers_do_not_open_network(self):
        original_socket = socket.socket

        def forbidden_socket(*_args, **_kwargs):
            raise AssertionError("network call forbidden")

        socket.socket = forbidden_socket
        try:
            self.assertGreater(len(GuideProvider().load_all()), 0)
            self.assertGreater(len(QuestProvider().list_quests()), 0)
            self.assertGreater(len(AchievementProvider().load_all()), 0)
        finally:
            socket.socket = original_socket


if __name__ == "__main__":
    unittest.main()
