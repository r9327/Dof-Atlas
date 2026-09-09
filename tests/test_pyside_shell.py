from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import app.pages._quests_page_impl as quests_impl
from app.constants import KEY_SESSION_ORDER
from app.quest_catalog import QuestCatalog, QuestCharacter, QuestRecord
from app.session_manager_pyside import QuestsPage
from tests import _pyside_shell_base as _base


class PySideShellTests(_base.PySideShellTests):
    """Canonical shell suite with targeted overrides for superseded fixtures."""

    @staticmethod
    def _organizer_paths(organizer, root: Path) -> dict[str, Path]:
        previous = {
            "PROFILE_FILE": organizer.PROFILE_FILE,
            "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
            "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
        }
        organizer.PROFILE_FILE = root / "client_profiles.json"
        organizer.CLIENT_INDEX_JSON = root / "client_index.json"
        organizer.CLIENT_INDEX_INI = root / "client_index.ini"
        return previous

    def test_organizer_session_order_is_reapplied_after_scan(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            previous = self._organizer_paths(organizer, Path(tmp))
            try:
                page = organizer.OrganizerPage(lambda _text: None, lambda *args: None)
                page.sessions = page.build_session_slots([
                    {"nom": "Bob - Pandawa", "hwnd": 10},
                    {"nom": "Charlie - Enutrof", "hwnd": 20},
                    {"nom": "Dana - Sadida", "hwnd": 30},
                ])
                page.save_session_order()
                ordered = page.build_session_slots([
                    {"nom": "Dana - Sadida", "hwnd": 300},
                    {"nom": "Charlie - Enutrof", "hwnd": 200},
                    {"nom": "Bob - Pandawa", "hwnd": 100},
                    {"nom": "Nouveau - Cra", "hwnd": 400},
                ])

                self.assertEqual(
                    [row["nom"] for row in ordered[:4]],
                    ["Bob - Pandawa", "Charlie - Enutrof", "Dana - Sadida", "Nouveau - Cra"],
                )
                # CharacterOrderService persists a compact logical order. Class
                # suffixes and empty Organizer positions are presentation only.
                self.assertEqual(page.profiles[KEY_SESSION_ORDER], ["bob", "charlie", "dana"])
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous.items():
                    setattr(organizer, name, value)

    def test_organizer_clears_closed_windows_to_empty_slots(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            previous = self._organizer_paths(organizer, Path(tmp))
            try:
                page = organizer.OrganizerPage(lambda _text: None, lambda *args: None)
                page.sessions = page.build_session_slots([
                    {"nom": "Bob - Pandawa", "hwnd": 10},
                    {"nom": "Dana - Sadida", "hwnd": 20},
                    {"nom": "Charlie - Enutrof", "hwnd": 30},
                ])
                page.sessions = page.build_session_slots([{"nom": "Bob - Pandawa", "hwnd": 10}])
                page.render_sessions()
                page.export_client_index()

                self.assertEqual(len(page.sessions), 8)
                self.assertEqual(len(page.session_slot_widgets), 8)
                self.assertEqual(page.sessions[0]["nom"], "Bob - Pandawa")
                self.assertTrue(all(not page.sessions[index]["nom"] for index in range(1, 8)))
                self.assertEqual(page.profiles[KEY_SESSION_ORDER], ["bob"])
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertEqual(payload["count"], 1)
                self.assertEqual(payload["clients"][0]["character_name"], "Bob")
                self.assertEqual(payload["clients"][0]["slot"], 1)
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous.items():
                    setattr(organizer, name, value)

    def test_organizer_can_move_session_to_exact_empty_slot(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            previous = self._organizer_paths(organizer, Path(tmp))
            try:
                page = organizer.OrganizerPage(lambda _text: None, lambda *args: None)
                page.sessions = page.build_session_slots([
                    {"nom": "Perso 1", "hwnd": 101},
                    {"nom": "Perso 2", "hwnd": 102},
                    {"nom": "Perso 3", "hwnd": 103},
                ])
                page.reorder_session(0, 7)

                self.assertEqual(page.sessions[0]["nom"], "")
                self.assertEqual(page.sessions[1]["nom"], "Perso 2")
                self.assertEqual(page.sessions[2]["nom"], "Perso 3")
                self.assertEqual(page.sessions[7]["nom"], "Perso 1")
                self.assertEqual(page.profiles[KEY_SESSION_ORDER], ["perso_2", "perso_3", "perso_1"])
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertEqual([client["slot"] for client in payload["clients"]], [2, 3, 8])
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous.items():
                    setattr(organizer, name, value)

    def test_quests_page_tracks_progress_per_character(self):
        app = QApplication.instance() or QApplication([])
        catalog = QuestCatalog(
            [
                QuestRecord(
                    id=101,
                    name="La maire de glace",
                    category="Quetes principales",
                    level_min=50,
                    level_max=50,
                    start_criterion="PL>49",
                    zones=["Ile de Frigost"],
                    achievements=["Fri carre"],
                ),
                QuestRecord(
                    id=102,
                    name="Full contact",
                    category="Quetes principales",
                    level_min=50,
                    level_max=50,
                    start_criterion="Qf=101",
                    zones=["Ile de Frigost"],
                    achievements=["Fri carre"],
                ),
            ]
        )
        characters = [
            QuestCharacter("character:202", "Beta", 2, True),
            QuestCharacter("character:101", "Alpha", 1, True),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile = tmp_path / "client_profiles.json"
            client_index = tmp_path / "client_index.json"
            progress = tmp_path / "quest_progress.json"
            profile.write_text("{}", encoding="utf-8")
            client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")
            with patch.object(quests_impl, "load_quest_characters", return_value=characters):
                page = QuestsPage(
                    lambda _text: None,
                    catalog=catalog,
                    progress_path=progress,
                    profile_path=profile,
                    client_index_path=client_index,
                )

                self.assertEqual(page.quest_list.count(), 0)
                self.assertEqual(page.character_combo.currentText(), "Alpha")
                self.assertEqual(page.current_character_key, "character:101")
                page.search.setText("glace")
                app.processEvents()
                self.assertEqual(page.quest_list.count(), 1)
                first = page.quest_list.item(0)
                first.setCheckState(Qt.Checked)
                app.processEvents()

                saved = json.loads(progress.read_text(encoding="utf-8"))
                self.assertTrue(saved["characters"]["character:101"]["done"]["101"])
                self.assertNotIn("slot:1", saved["characters"])
                self.assertNotIn("slot:2", saved["characters"])

                page.character_combo.setCurrentIndex(0)
                app.processEvents()
                self.assertEqual(page.current_character_key, "character:202")
                self.assertEqual(page.quest_list.count(), 1)
                self.assertEqual(page.quest_list.item(0).checkState(), Qt.Unchecked)

                page.deleteLater()
                app.processEvents()
