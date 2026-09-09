from __future__ import annotations

import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt, QUrl
from PySide6.QtGui import QColor, QKeyEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QComboBox, QPushButton, QSpinBox, QToolButton

from app.constants import KEY_CLICK_HOTKEY, KEY_DEBUG_MODE, KEY_DOUBLE_CLICK_HOTKEY, KEY_SESSION_ORDER, KEY_SWITCH_CLICK, KEY_SWITCH_DOUBLE_CLICK, RAW_QUEST_DATA_DIR
from app.core.settings import ZaapTimings, load_settings, timings_for_speed
from app.input.hotkeys import HotkeyAction, HotkeyRegistry, build_hotkey_actions, parse_hotkey
from app.modules.encyclopedia.providers import AchievementProvider
from app.quest_catalog import (
    QuestCatalog,
    QuestCharacter,
    QuestObjective,
    QuestRecord,
    QuestReward,
    QuestStep,
    quest_kamas_amount,
    quest_xp_amount,
    select_reward_rows,
)
from app.pages.quests_page import linkify_travel_coordinates, quest_detail_html, quest_required_items
import app.storage as storage
from app.session_manager_pyside import (
    AtlasWindow,
    CraftPage,
    QuestsPage,
    ZaapWidget,
    canonical_job_name,
    display_path,
    hwnd_value,
    key_sequence_to_hotkey,
    normalize_key,
    parse_size_pair,
    read_zaap_button_ratios,
    read_zaap_favorites,
    route_path_for,
    score_match,
    save_zaap_button_ratios,
    save_zaap_favorites,
    zaap_search_min_score,
    zaap_search_score,
)
from main import build_quest_preload


class PySideShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls._runtime_patch = patch.object(AtlasWindow, "start_runtime", return_value=None)
        cls._tray_patch = patch.object(AtlasWindow, "setup_tray", return_value=None)
        cls._runtime_patch.start()
        cls._tray_patch.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tray_patch.stop()
        cls._runtime_patch.stop()

    def test_normalize_key_removes_accents(self):
        self.assertEqual(normalize_key("Routes Rocailleuses"), "routes_rocailleuses")
        self.assertEqual(normalize_key("Cite d'Astrub"), "cite_d_astrub")

    def test_score_match_supports_contains_and_fuzzy(self):
        self.assertGreater(score_match(["Routes Rocailleuses"], "oute"), 0)
        self.assertGreater(score_match(["Bonta"], "bonta"), 90)

    def test_zaap_search_score_handles_smart_queries(self):
        astrub = {"label": "Cit\u00e9 d\u2019Astrub [5,-18]", "name": "Cit\u00e9 d\u2019Astrub", "posX": 5, "posY": -18}
        otomai = {"label": "Village c\u00f4tier [-46,18]", "subareas": ["Arche d'Otoma\u00ef"]}
        wabbit = {"label": "\u00cele de la Cawotte [25,-4]", "subareas": ["Terrier du Wa Wabbit"]}
        guerre = {"label": "Blessures de Guerre [1,-1]", "subareas": ["D\u00e9sert de Mis\u00e8re"]}
        frigost = {"label": "La Bourgade [-78,-41]", "region": "\u00cele de Frigost"}
        sidimote = {"label": "Route des Roulottes [-25,12]", "region": "Landes de Sidimote"}
        astrub_region_only = {"label": "Tain\u00e9la [1,-32]", "region": "Astrub"}
        grobe = {"label": "Mont des Tombeaux [40,-44]", "region": "\u00cele de Grobe"}
        nested = {"label": "Zaap test [1,2]", "region": {"fr": "Plaines de Cania"}, "aliases": [{"fr": "Routes Rocailleuses"}]}

        self.assertGreaterEqual(zaap_search_score(astrub, "astru"), 80)
        self.assertGreater(zaap_search_score(astrub, "astru"), zaap_search_score(astrub_region_only, "astru"))
        self.assertGreaterEqual(zaap_search_score(astrub, "cite astrub"), 90)
        self.assertGreaterEqual(zaap_search_score(astrub, "5 -18"), 100)
        self.assertGreaterEqual(zaap_search_score(otomai, "otomai"), 80)
        self.assertGreaterEqual(zaap_search_score(wabbit, "ile wabbit"), 80)
        self.assertGreaterEqual(zaap_search_score(guerre, "blessure guerre"), 80)
        self.assertGreaterEqual(zaap_search_score(guerre, "desert misere"), 80)
        self.assertGreaterEqual(zaap_search_score(frigost, "frigost"), 80)
        self.assertGreaterEqual(zaap_search_score(sidimote, "sidimote"), 80)
        self.assertGreaterEqual(zaap_search_score(grobe, "tombeau grobe"), 80)
        self.assertGreaterEqual(zaap_search_score(otomai, "otm"), 80)
        self.assertGreaterEqual(zaap_search_score(nested, "rocailleuse cania"), 80)
        self.assertGreater(zaap_search_min_score("desert misere"), zaap_search_score(astrub, "desert misere"))
        self.assertEqual(zaap_search_min_score("5 -18"), 90)

    def test_icon_cache_reuses_cached_icon_without_rechecking_path(self):
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "icon.png"
            pixmap = QPixmap(12, 12)
            pixmap.fill(QColor("#ff0000"))
            self.assertTrue(pixmap.save(str(image_path), "PNG"))

            cache = storage.IconCache(size=12)
            icon = cache.icon_for_item({"image_path": str(image_path)})
            self.assertFalse(icon.isNull())

            original_exists = storage.Path.exists

            def fail_for_cached_path(path):
                if str(path) == str(image_path):
                    raise AssertionError("cached icon path was checked again")
                return original_exists(path)

            storage.Path.exists = fail_for_cached_path
            try:
                cached_icon = cache.icon_for_item({"image_path": str(image_path)})
            finally:
                storage.Path.exists = original_exists
            self.assertFalse(cached_icon.isNull())

    def test_zaap_ratios_are_saved_for_runtime_clicks(self):
        with tempfile.TemporaryDirectory() as tmp:
            shortcuts = Path(tmp) / "zaap_shortcuts.json"
            shortcuts.write_text(json.dumps({"zaap_favorites": ["Bonta"]}), encoding="utf-8")

            saved = save_zaap_button_ratios(0.5234, 0.7812, shortcuts)
            self.assertEqual(saved, (0.5234, 0.7812))
            self.assertEqual(read_zaap_button_ratios({"zaap_button": {"x_ratio": 0.5234, "y_ratio": 0.7812}}), saved)
            payload = json.loads(shortcuts.read_text(encoding="utf-8"))
            self.assertEqual(payload["zaap_favorites"], ["Bonta"])

    def test_zaap_favorites_are_saved_in_shortcuts_json(self):
        zaaps = [
            {"label": "Cite d'Astrub [5,-18]", "name": "Cite d'Astrub", "posX": 5, "posY": -18},
            {"label": "Bonta [-32,-56]", "name": "Bonta", "posX": -32, "posY": -56},
            {"label": "Tainéla [1,-32]", "name": "Tainéla", "posX": 1, "posY": -32},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            shortcuts = Path(tmp) / "zaap_shortcuts.json"
            shortcuts.write_text(
                json.dumps({"zaap_button": {"x_ratio": 0.25, "y_ratio": 0.5}}),
                encoding="utf-8",
            )

            saved = save_zaap_favorites(["Bonta", "Inexistant", "Tainéla", "Bonta"], zaaps, shortcuts)

            self.assertEqual(saved, ["Bonta", "Tainéla"])
            payload = json.loads(shortcuts.read_text(encoding="utf-8"))
            self.assertEqual(payload["zaap_favorites"], ["Bonta", "Tainéla"])
            self.assertEqual(read_zaap_button_ratios(payload), (0.25, 0.5))
            self.assertEqual(read_zaap_favorites(zaaps, payload), ["Bonta", "Tainéla"])

    def test_zaap_widget_refresh_keeps_typed_text(self):
        app = QApplication.instance() or QApplication([])
        widget = ZaapWidget(lambda _text: None)
        widget.zaaps = [
            {"label": "Cite d'Astrub [5,-18]", "name": "Cite d'Astrub", "posX": 5, "posY": -18},
            {"label": "Village cotier [-46,18]", "subareas": ["Arche d'Otomai"]},
        ]

        widget.search_input.setText("astr")
        widget.refresh_results("astr")
        widget.search_input.setText("astru")
        widget.refresh_results("astru")

        self.assertEqual(widget.search_input.text(), "astru")
        self.assertIsNone(widget.search_input.completer())
        self.assertEqual(widget.findChildren(QComboBox), [])
        self.assertEqual(widget.suggestion_popup.windowType(), Qt.Tool)
        self.assertTrue(bool(widget.suggestion_popup.windowFlags() & Qt.WindowDoesNotAcceptFocus))
        self.assertEqual(widget.suggestion_popup.focusPolicy(), Qt.NoFocus)
        self.assertGreater(widget.suggestion_popup.count(), 0)
        self.assertEqual(widget.filtered_zaaps[0]["name"], "Cite d'Astrub")
        widget.deleteLater()
        app.processEvents()

    def test_zaap_widget_keyboard_selection_keeps_typed_text(self):
        app = QApplication.instance() or QApplication([])
        calls = []
        widget = ZaapWidget(lambda _text: None, lambda *args: calls.append(args))
        widget.zaaps = [
            {"label": "Cite d'Astrub [5,-18]", "name": "Cite d'Astrub", "posX": 5, "posY": -18},
            {"label": "Village cotier [-46,18]", "name": "Village cotier", "posX": -46, "posY": 18},
            {"label": "Bonta [-32,-56]", "name": "Bonta", "posX": -32, "posY": -56},
        ]

        widget.search_input.setText("a")
        widget.refresh_results("a")
        widget.show_suggestions()
        typed_text = widget.search_input.text()
        widget.move_suggestion_selection(1)

        self.assertEqual(widget.search_input.text(), typed_text)
        self.assertTrue(widget.launch_current_suggestion())
        self.assertIn(widget.search_input.text(), {"Cite d'Astrub [5,-18]", "Village cotier [-46,18]", "Bonta [-32,-56]"})
        self.assertTrue(calls)
        self.assertIn(calls[-1][0], {"Cite d'Astrub", "Village cotier", "Bonta"})
        widget.deleteLater()
        app.processEvents()

    def test_zaap_widget_launch_keeps_selected_text(self):
        app = QApplication.instance() or QApplication([])
        calls = []
        widget = ZaapWidget(lambda _text: None, lambda *args: calls.append(args))
        widget.search_input.setText("astru")
        widget.launch_zaap({"label": "Cite d'Astrub [5,-18]", "search": "Cite d'Astrub"})

        self.assertEqual(widget.search_input.text(), "Cite d'Astrub [5,-18]")
        self.assertEqual(calls[-1][0], "Cite d'Astrub")
        widget.deleteLater()
        app.processEvents()

    def test_zaap_widget_can_hide_position_controls(self):
        app = QApplication.instance() or QApplication([])
        widget = ZaapWidget(lambda _text: None, show_position_controls=False)

        self.assertTrue(widget.position_divider.isHidden())
        self.assertTrue(widget.position_label.isHidden())
        self.assertTrue(widget.position_wrapper.isHidden())
        self.assertTrue(widget.calibrate_button.isHidden())
        widget.deleteLater()
        app.processEvents()

    def test_zaap_widget_toggles_favorites_and_renders_chips(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            previous_shortcuts = storage.ZAAP_SHORTCUTS_FILE
            storage.ZAAP_SHORTCUTS_FILE = Path(tmp) / "zaap_shortcuts.json"
            calls = []
            try:
                widget = ZaapWidget(lambda _text: None, lambda *args: calls.append(args))
                widget.zaaps = [
                    {"label": "Bonta [-32,-56]", "name": "Bonta", "posX": -32, "posY": -56},
                    {"label": "Tainéla [1,-32]", "name": "Tainéla", "posX": 1, "posY": -32},
                ]
                widget.favorite_names = []
                widget.refresh_results("")
                widget.refresh_favorite_chips()

                row = widget.zaaps[0]
                self.assertEqual(widget.favorite_marker(row), "☆")
                widget.toggle_favorite(row)

                payload = json.loads(storage.ZAAP_SHORTCUTS_FILE.read_text(encoding="utf-8"))
                self.assertEqual(payload["zaap_favorites"], ["Bonta"])
                self.assertEqual(widget.favorite_marker(row), "★")
                self.assertEqual(len(widget.favorite_buttons), 1)
                self.assertEqual(len(widget.favorite_star_buttons), 1)

                widget.favorite_buttons[0].click()
                self.assertEqual(calls[-1][0], "Bonta")
                widget.favorite_star_buttons[0].click()
                payload = json.loads(storage.ZAAP_SHORTCUTS_FILE.read_text(encoding="utf-8"))
                self.assertEqual(payload["zaap_favorites"], [])
                widget.deleteLater()
                app.processEvents()
            finally:
                storage.ZAAP_SHORTCUTS_FILE = previous_shortcuts

    def test_parse_size_pair_clamps_popup_size(self):
        self.assertEqual(parse_size_pair("467,624", (520, 360)), (467, 624))
        self.assertEqual(parse_size_pair("120x80", (520, 360)), (320, 240))
        self.assertEqual(parse_size_pair("bad", (520, 360)), (520, 360))

    def test_route_path_uses_normalized_job_and_resource(self):
        path = route_path_for("Mineur", "Cristal liquide", 2)
        self.assertTrue(path.as_posix().endswith("data/routes/mineur/cristal_liquide_2.png"))

    def test_canonical_job_name_keeps_route_folder_compatible(self):
        self.assertEqual(canonical_job_name("B\u00fbcheron"), "Bucheron")

    def test_key_sequence_to_hotkey_uses_runtime_names(self):
        self.assertEqual(key_sequence_to_hotkey(Qt.Key_F6), "F6")
        self.assertEqual(key_sequence_to_hotkey(Qt.Key_Return), "RETURN")
        self.assertEqual(key_sequence_to_hotkey(Qt.Key_F12, Qt.ControlModifier | Qt.AltModifier), "CTRL+ALT+F12")

    def test_display_path_handles_none(self):
        self.assertEqual(display_path(None), "")

    def test_quest_catalog_loads_local_doduda_quests(self):
        catalog = QuestCatalog.load(RAW_QUEST_DATA_DIR)

        self.assertGreaterEqual(len(catalog.quests), 1900)
        self.assertTrue(any(quest.name and quest.steps for quest in catalog.quests))
        self.assertTrue(any(quest.achievements for quest in catalog.quests))

    def test_quest_preload_builds_catalog(self):
        preload = build_quest_preload(include_related=False)
        catalog = preload.get("catalog")

        self.assertEqual(preload.get("errors"), [])
        self.assertIsInstance(catalog, QuestCatalog)
        self.assertGreaterEqual(len(catalog.quests), 1900)
        achievement_provider = preload.get("achievement_provider")
        self.assertIsInstance(achievement_provider, AchievementProvider)
        self.assertFalse(achievement_provider._loaded)

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
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile = tmp_path / "client_profiles.json"
            client_index = tmp_path / "client_index.json"
            progress = tmp_path / "quest_progress.json"
            profile.write_text(json.dumps({KEY_SESSION_ORDER: ["alpha", "beta", "", "", "", "", "", ""]}), encoding="utf-8")
            client_index.write_text(
                json.dumps({"clients": [{"index": 1, "name": "Alpha", "handle": 1234}]}),
                encoding="utf-8",
            )
            page = QuestsPage(
                lambda _text: None,
                catalog=catalog,
                progress_path=progress,
                profile_path=profile,
                client_index_path=client_index,
            )

            self.assertEqual(page.quest_list.count(), 0)
            self.assertEqual(page.character_combo.currentText(), "Alpha")
            self.assertNotIn("Personnage", page.character_combo.currentText())
            page.search.setText("glace")
            app.processEvents()
            self.assertEqual(page.quest_list.count(), 1)
            first = page.quest_list.item(0)
            first.setCheckState(Qt.Checked)
            app.processEvents()

            saved = json.loads(progress.read_text(encoding="utf-8"))
            self.assertTrue(saved["characters"]["slot:1"]["done"]["101"])

            page.character_combo.setCurrentIndex(1)
            app.processEvents()
            self.assertEqual(page.current_character_key, "slot:2")
            self.assertEqual(page.quest_list.count(), 1)

            page.deleteLater()
            app.processEvents()

    def test_quest_coordinates_copy_travel_command(self):
        app = QApplication.instance() or QApplication([])
        catalog = QuestCatalog(
            [
                QuestRecord(
                    id=201,
                    name="Position de test",
                    category="Quetes principales",
                    level_min=1,
                    level_max=1,
                    start_criterion="",
                    steps=[
                        QuestStep(
                            id=1,
                            name="Depart",
                            description="Rejoindre la carte [5,-18].",
                            objectives=[QuestObjective(id=1, text="Parler au pnj en [5,-18]", type_id=0)],
                        )
                    ],
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile = tmp_path / "client_profiles.json"
            client_index = tmp_path / "client_index.json"
            progress = tmp_path / "quest_progress.json"
            profile.write_text(json.dumps({KEY_SESSION_ORDER: ["alpha", "", "", "", "", "", "", ""]}), encoding="utf-8")
            client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")
            statuses = []
            page = QuestsPage(
                statuses.append,
                catalog=catalog,
                progress_path=progress,
                profile_path=profile,
                client_index_path=client_index,
            )

            page.select_quest(201)
            self.assertIn('href="atlas-travel:5,-18"', linkify_travel_coordinates("Carte [5,-18]"))
            self.assertIn("atlas-travel:5,-18", page.detail.toHtml())
            self.assertFalse(page.detail.openLinks())
            page.on_detail_link_clicked(QUrl("atlas-travel:5,-18"))

            self.assertEqual(QApplication.clipboard().text(), "/travel 5,-18")
            self.assertEqual(statuses[-1], "Copie: /travel 5,-18")
            self.assertIn("/travel 5,-18", page.copy_feedback.text())
            page.deleteLater()
            app.processEvents()

    def test_quest_detail_uses_local_images_without_external_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "reward.png"
            image_path.write_bytes(b"")
            quest = QuestRecord(
                id=202,
                name="Image locale",
                category="Quetes principales",
                level_min=1,
                level_max=1,
                start_criterion="",
                rewards=[QuestReward("Objet local", 1, str(image_path))],
                steps=[
                    QuestStep(
                        id=1,
                        name="Voir",
                        description="Regarder [1,2].",
                        objectives=[
                            QuestObjective(
                                id=1,
                                text="Inspecter [1,2]",
                                type_id=0,
                                image_path=str(image_path),
                                image_label="Illustration locale",
                            )
                        ],
                    )
                ],
            )
            html = quest_detail_html(quest, False)

            self.assertIn("file:///", html)
            self.assertIn("atlas-travel:1,2", html)
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)
            self.assertNotIn("Sources", html)

    def test_quest_page_has_interactive_required_items(self):
        app = QApplication.instance() or QApplication([])
        quest = QuestRecord(
            id=203,
            name="Stock local",
            category="Quetes principales",
            level_min=20,
            level_max=20,
            start_criterion="",
            rewards=[QuestReward("Idole locale", 1, item_id=28446)],
            steps=[
                QuestStep(
                    id=1,
                    name="Rapporter",
                    description="",
                    objectives=[
                        QuestObjective(
                            id=1,
                            text="Ramener x3 Idole locale",
                            type_id=3,
                            image_label="Idole locale",
                            item_id=28446,
                            item_quantity=3,
                        ),
                        QuestObjective(
                            id=2,
                            text="Utiliser une alteration locale",
                            type_id=8,
                            image_label="Alteration locale",
                            item_id=99999,
                            item_quantity=1,
                        )
                    ],
                )
            ],
        )
        catalog = QuestCatalog([quest])
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile = tmp_path / "client_profiles.json"
            client_index = tmp_path / "client_index.json"
            progress = tmp_path / "quest_progress.json"
            selection = tmp_path / "craft_selection.json"
            profile.write_text(json.dumps({KEY_SESSION_ORDER: ["alpha", "", "", "", "", "", "", ""]}), encoding="utf-8")
            client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")
            selection.write_text(
                json.dumps({"items": [{"item_id": 28446, "ankama_id": 28446, "name": "Idole locale", "quantity": 2}]}),
                encoding="utf-8",
            )
            page = QuestsPage(
                lambda _text: None,
                catalog=catalog,
                progress_path=progress,
                profile_path=profile,
                client_index_path=client_index,
                owned_items_path=selection,
            )
            page.current_character_key = "character:1"
            page.quest_detail_view.set_character_key("character:1")

            page.select_quest(203)
            required_items = quest_required_items(quest)
            self.assertEqual([item["name"] for item in required_items], ["Idole locale"])
            self.assertIsNone(page.right_panel.findChild(QSpinBox))

            image = page.right_panel.findChild(QToolButton, "GuideItemIcon")
            name_button = page.right_panel.findChild(QPushButton, "GuideItemNameButton")
            self.assertIsNotNone(image)
            self.assertIsNotNone(name_button)
            name_button.click()
            app.processEvents()
            self.assertEqual(QApplication.clipboard().text(), "Idole locale")
            self.assertFalse(progress.exists())

            image.click()
            app.processEvents()
            saved_progress = json.loads(progress.read_text(encoding="utf-8"))
            self.assertTrue(saved_progress["characters"]["character:1"]["quest_items"]["203"]["28446"])
            self.assertEqual(image.property("state"), "done")

            labels = [label.text() for label in page.right_panel.findChildren(QLabel)]
            button_texts = [button.text() for button in page.right_panel.findChildren(QPushButton)]
            self.assertIn("Idole locale", button_texts)
            self.assertIn("x3", labels)
            self.assertNotIn("En inventaire", labels)
            self.assertNotIn("manque", quest_detail_html(quest, False, {28446: 2}))
            steps_html = quest_detail_html(quest, False, {28446: 2}).split("<h2>Étapes</h2>", 1)[1]
            self.assertNotIn("Possede", steps_html)
            page.deleteLater()
            app.processEvents()

    def test_quest_reward_level_filter_and_xp_number(self):
        rows = [
            {"experienceRatio": 2, "levelMin": 9, "levelMax": 29},
            {"experienceRatio": 2, "levelMin": 30, "levelMax": 49},
        ]

        self.assertEqual(select_reward_rows(rows, 20), [rows[0]])
        self.assertEqual(quest_xp_amount(rows[0], {20: 86700}, 20), 1734)
        self.assertEqual(quest_kamas_amount({"kamasRatio": 0.42, "levelMin": 20, "levelMax": 20}, 20), 840)
        self.assertEqual(quest_kamas_amount({"kamasRatio": 0, "levelMin": 20, "levelMax": 20}, 20), 0)
        quest = QuestRecord(
            id=204,
            name="Recompenses locales",
            category="Quetes principales",
            level_min=20,
            level_max=20,
            start_criterion="",
            rewards=[
                QuestReward("XP", 1734, kind="xp"),
                QuestReward("Kamas", 840, kind="kamas"),
                QuestReward("Kamas", 0, kind="kamas"),
                QuestReward("Objet local", 2, item_id=28446),
                QuestReward("Champion local", 1, kind="title"),
            ],
        )
        html = quest_detail_html(quest, False, {28446: 2})

        self.assertNotIn("XP approx", html)
        self.assertIn("840 Kamas", html)
        self.assertNotIn('<li class="reward">0 Kamas</li>', html)
        self.assertIn("x2 Objet local", html)
        self.assertIn("Titre : Champion local", html)
        self.assertNotIn("Possede", html)

    def test_atlas_window_can_be_created(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            try:
                window = AtlasWindow()
                self.assertEqual(window.windowTitle(), "Dofus Atlas")
                window.quit_requested = True
                window.close()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_atlas_window_defers_heavy_pages(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            try:
                window = AtlasWindow()
                self.assertIn("Scan Monde", window.page_factories)
                self.assertIn("Craft", window.page_factories)
                self.assertIn("Quetes", window.page_factories)
                self.assertIn("Equipement", window.page_factories)
                self.assertEqual(
                    set(window.page_widgets),
                    {
                        "Home",
                        "Organizer",
                        "Scan Monde",
                        "Craft",
                        "Quetes",
                        "Equipement",
                        "Almanax",
                        "Settings",
                    },
                )
                self.assertEqual(set(window.page_factories), {"Scan Monde", "Craft", "Quetes", "Equipement"})
                self.assertEqual(type(window.page_widgets["Organizer"]).__name__, "OrganizerPage")
                self.assertNotEqual(type(window.page_widgets["Scan Monde"]).__name__, "WorldScanPanel")
                self.assertNotEqual(type(window.page_widgets["Equipement"]).__name__, "EquipmentPage")
                self.assertEqual(window.page_nav_group["Quetes"], "Encyclopédie")
                self.assertNotEqual(type(window.page_widgets["Quetes"]).__name__, "QuestsPage")
                window.quit_requested = True
                window.close()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_atlas_window_preloads_craft_and_quests_from_startup_payload(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        quest_catalog = QuestCatalog(
            [
                QuestRecord(
                    id=301,
                    name="Quete prechargee",
                    category="Quetes principales",
                    level_min=1,
                    level_max=1,
                    start_criterion="",
                )
            ]
        )
        startup_preload = {
            "craft": {
                "items": [{"name": "Anneau precharge", "ankama_id": 101, "level": 12, "type": "Anneau"}],
                "jobs": [{"name": "Mineur", "ankama_id": 1, "image_path": "", "type": "job"}],
                "guides": {"guides": {}},
                "selection": {},
                "lookup_items": [],
                "errors": [],
            },
            "quests": {"catalog": quest_catalog, "owned_items": {}, "errors": []},
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            try:
                window = AtlasWindow(initial_preload=startup_preload)
                self.assertIn("Craft", window.page_factories)
                self.assertIn("Quetes", window.page_factories)
                self.assertNotEqual(type(window.page_widgets["Craft"]).__name__, "CraftPage")
                self.assertNotEqual(type(window.page_widgets["Quetes"]).__name__, "EncyclopediaPage")

                window.show_page("Craft")
                app.processEvents()
                window.show_page("Quetes")
                app.processEvents()

                self.assertNotIn("Craft", window.page_factories)
                self.assertNotIn("Quetes", window.page_factories)
                self.assertEqual(type(window.page_widgets["Craft"]).__name__, "CraftPage")
                self.assertEqual(type(window.page_widgets["Quetes"]).__name__, "EncyclopediaPage")
                self.assertEqual(window.page_widgets["Craft"].items[0]["name"], "Anneau precharge")
                self.assertEqual(window.page_widgets["Quetes"].current_tab_label(), "QUÊTES")
                self.assertEqual(len(window.page_widgets["Quetes"].quest_page.catalog.quests), 1)
                window.quit_requested = True
                window.close()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_atlas_window_background_preload_keeps_heavy_pages_lazy(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        quest_catalog = QuestCatalog(
            [
                QuestRecord(
                    id=301,
                    name="Quete prechargee",
                    category="Quetes principales",
                    level_min=1,
                    level_max=1,
                    start_criterion="",
                )
            ]
        )
        startup_preload = {
            "craft": {
                "items": [{"name": "Anneau precharge", "ankama_id": 101, "level": 12, "type": "Anneau"}],
                "jobs": [{"name": "Mineur", "ankama_id": 1, "image_path": "", "type": "job"}],
                "guides": {"guides": {}},
                "selection": {},
                "lookup_items": [],
                "errors": [],
            },
            "quests": {"catalog": quest_catalog, "owned_items": {}, "errors": []},
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            try:
                window = AtlasWindow()
                window.preload_started = True
                window.preload_queue.put(startup_preload)
                window.collect_preload_result()

                self.assertIn("Craft", window.page_factories)
                self.assertIn("Quetes", window.page_factories)
                self.assertNotEqual(type(window.page_widgets["Craft"]).__name__, "CraftPage")
                self.assertNotEqual(type(window.page_widgets["Quetes"]).__name__, "EncyclopediaPage")

                self.assertIn("Quetes", window.page_factories)
                self.assertNotEqual(type(window.page_widgets["Quetes"]).__name__, "EncyclopediaPage")

                window.show_page("Quetes")
                app.processEvents()

                encyclopedia = window.page_widgets["Quetes"]
                self.assertNotIn("Quetes", window.page_factories)
                self.assertEqual(type(encyclopedia).__name__, "EncyclopediaPage")
                self.assertEqual(len(encyclopedia.quest_page.catalog.quests), 1)
                self.assertIsNone(encyclopedia.guides_view)
                self.assertIsNone(encyclopedia.get_achievements_view())

                window.show_page("Craft")
                app.processEvents()

                self.assertNotIn("Craft", window.page_factories)
                self.assertEqual(type(window.page_widgets["Craft"]).__name__, "CraftPage")
                self.assertEqual(window.page_widgets["Craft"].items[0]["name"], "Anneau precharge")
                window.quit_requested = True
                window.close()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_atlas_window_page_navigation_defers_factory_to_next_qt_cycle(self):
        app = QApplication.instance() or QApplication([])
        window = AtlasWindow()
        window.preload_started = True
        calls: list[str] = []

        def factory():
            calls.append("loaded")
            return QLabel("Loaded")

        try:
            window.page_factories["Quetes"] = factory
            window.show_page("Quetes")

            self.assertEqual(calls, [])
            self.assertIn("Quetes", window.page_factories)
            self.assertEqual(window.active_page_name(), "Home")
            self.assertNotEqual(type(window.page_widgets["Quetes"]).__name__, "QLabel")

            app.processEvents()

            self.assertEqual(calls, ["loaded"])
            self.assertNotIn("Quetes", window.page_factories)
            self.assertEqual(type(window.page_widgets["Quetes"]).__name__, "QLabel")
            self.assertEqual(window.active_page_name(), "Quetes")
            loaded_page = window.page_widgets["Quetes"]

            window.show_page("Organizer")
            app.processEvents()
            window.show_page("Quetes")
            app.processEvents()

            self.assertEqual(calls, ["loaded"])
            self.assertIs(window.page_widgets["Quetes"], loaded_page)
        finally:
            window.quit_requested = True
            window.close()
            app.processEvents()

    def test_atlas_window_keeps_current_page_until_existing_target_is_ready(self):
        app = QApplication.instance() or QApplication([])
        window = AtlasWindow()
        window.preload_started = True
        callbacks = []
        ready = {"value": False}
        window.page_factories.pop("Equipement", None)
        page = window.page_widgets["Equipement"]

        def is_ready():
            return ready["value"]

        def prepare(callback):
            callbacks.append(callback)
            return False

        try:
            page.is_navigation_ready = is_ready
            page.prepare_for_navigation = prepare

            window.show_page("Equipement")

            self.assertEqual(window.active_page_name(), "Home")
            self.assertEqual(len(callbacks), 1)

            ready["value"] = True
            callbacks[0]()

            self.assertEqual(window.active_page_name(), "Equipement")
            self.assertIs(window.page_widgets["Equipement"], page)

            window.show_page("Organizer")
            app.processEvents()
            window.show_page("Equipement")

            self.assertEqual(window.active_page_name(), "Equipement")
            self.assertEqual(len(callbacks), 1)
            self.assertIs(window.page_widgets["Equipement"], page)
        finally:
            window.quit_requested = True
            window.close()
            app.processEvents()

    def test_equipment_page_preparation_reuses_webengine_instance(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.equipment_page as equipment_module

        class FakeSignal:
            def __init__(self):
                self.callback = None

            def connect(self, callback):
                self.callback = callback

        class FakeWebView(QLabel):
            created = 0
            load_calls = 0

            def __init__(self):
                super().__init__("web")
                type(self).created += 1
                self.loadFinished = FakeSignal()
                self._page = None

            def setZoomFactor(self, _factor):
                return None

            def setPage(self, page):
                self._page = page

            def page(self):
                return self._page

            def load(self, _url):
                type(self).load_calls += 1

        class FakeWebPage:
            def __init__(self, _parent=None):
                pass

            def runJavaScript(self, _script, callback=None):
                if callback is not None:
                    callback(None)

        previous_view = equipment_module.QWebEngineView
        previous_attempted = equipment_module._QWEBENGINE_IMPORT_ATTEMPTED
        previous_page_class = equipment_module._RESTRICTED_PAGE_CLASS
        equipment_module.QWebEngineView = FakeWebView
        equipment_module._QWEBENGINE_IMPORT_ATTEMPTED = True
        equipment_module._RESTRICTED_PAGE_CLASS = FakeWebPage
        callbacks: list[str] = []
        page = equipment_module.EquipmentPage(lambda _text: None)
        try:
            self.assertTrue(page.prepare_for_navigation(lambda: callbacks.append("ready")))
            self.assertTrue(page.is_navigation_ready())
            self.assertFalse(page.web_loaded)
            page.show()
            QTest.qWait(equipment_module.WEBENGINE_START_DELAY_MS + 20)
            app.processEvents()

            self.assertTrue(page.web_loaded)
            self.assertEqual(callbacks[0], "ready")
            self.assertEqual(FakeWebView.created, 1)
            self.assertEqual(FakeWebView.load_calls, 1)

            self.assertTrue(page.prepare_for_navigation(lambda: callbacks.append("again")))
            page.ensure_web_loaded()
            app.processEvents()

            self.assertEqual(FakeWebView.created, 1)
            self.assertEqual(FakeWebView.load_calls, 1)
        finally:
            page.deleteLater()
            equipment_module.QWebEngineView = previous_view
            equipment_module._QWEBENGINE_IMPORT_ATTEMPTED = previous_attempted
            equipment_module._RESTRICTED_PAGE_CLASS = previous_page_class
            app.processEvents()

    def test_atlas_window_minimize_stays_in_taskbar(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            hide_calls = []
            try:
                window = AtlasWindow()
                window.hide_to_tray = lambda: hide_calls.append(True)
                window.show()
                app.processEvents()

                window.showMinimized()
                app.processEvents()

                self.assertTrue(window.isMinimized())
                self.assertFalse(hide_calls)
                self.assertFalse(window.isHidden())
                window.quit_requested = True
                window.close()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_craft_page_uses_preloaded_payload_without_local_cache(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.craft_page as craft_module

        previous_cache = craft_module.local_data_cache
        craft_module.local_data_cache = None
        try:
            preload = {
                "items": [
                    {"name": "Anneau test", "ankama_id": 101, "level": 12, "type": "Anneau"},
                ],
                "jobs": [
                    {"name": "Mineur", "ankama_id": 1, "image_path": "", "type": "job"},
                ],
                "guides": {"guides": {}},
                "selection": {
                    101: {"item": {"name": "Anneau test", "ankama_id": 101}, "quantity": 2},
                },
                "lookup_items": [
                    {"name": "Fer", "ankama_id": 201, "image_path": ""},
                ],
            }
            page = CraftPage(lambda _text: None, preload=preload)
            self.assertEqual(len(page.items), 1)
            self.assertEqual(page.items[0]["_search_name"], "anneau_test")
            self.assertIn("Mineur", {job["name"] for job in page.jobs})
            self.assertIn(101, page.selection)
            self.assertIn("fer", page.item_lookup_cache)
            page.deleteLater()
            app.processEvents()
        finally:
            craft_module.local_data_cache = previous_cache

    def test_craft_resource_popup_is_independent_from_main_window(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.craft_page as craft_module

        class FakeCraftCache:
            @staticmethod
            def get_recipe_for_item(_ident):
                return {"found": True, "ingredients": [{"name": "Fer", "quantity": 2}]}

        previous_cache = craft_module.local_data_cache
        craft_module.local_data_cache = FakeCraftCache
        try:
            preload = {
                "items": [],
                "jobs": [],
                "guides": {"guides": {}},
                "selection": {
                    101: {"item": {"name": "Anneau test", "ankama_id": 101}, "quantity": 3},
                },
                "lookup_items": [],
            }
            page = CraftPage(lambda _text: None, preload=preload)
            page.show_resources()
            app.processEvents()

            self.assertIsNotNone(page.resource_dialog)
            self.assertIsNone(page.resource_dialog.parent())
            self.assertFalse(page.resource_dialog.isModal())

            page.resource_dialog.close()
            page.deleteLater()
            app.processEvents()
        finally:
            craft_module.local_data_cache = previous_cache

    def test_organizer_exports_switch_double_click_hotkey(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            start_calls = []
            try:
                page = organizer.OrganizerPage(lambda _text: None, lambda *args: start_calls.append(args))
                legacy_refresh_attr = "refresh_" + "".join(["a", "h", "k"]) + "_button"
                self.assertFalse(hasattr(page, legacy_refresh_attr))
                self.assertEqual(page.quick_actions_title.text(), "Action rapide")
                self.assertEqual(page.reload_runtime_button.text(), "Relancer scripts")
                self.assertEqual(page.debug_button.text(), "Debug")
                self.assertFalse(hasattr(page, "scan_button"))
                self.assertTrue(hasattr(page, "sessions_refresh_button"))
                self.assertEqual(page.macro_panel.height(), page.quick_actions_panel.height())
                self.assertEqual(page.stop_script_button.objectName(), "dangerButton")
                self.assertEqual(page.stop_script_button.width(), page.script_speed_title.width())
                page.sessions = [{"nom": "Perso 1", "hwnd": 12345}]
                page.profiles[KEY_SWITCH_CLICK] = True
                page.profiles[KEY_CLICK_HOTKEY] = "F8"
                page.profiles[KEY_SWITCH_DOUBLE_CLICK] = True
                page.profiles[KEY_DEBUG_MODE] = True
                page.begin_capture("double_click")
                page.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_F8, Qt.NoModifier))

                self.assertNotIn(KEY_DOUBLE_CLICK_HOTKEY, page.profiles)
                self.assertEqual(page.double_click_button.text(), "...")
                self.assertFalse(start_calls)

                page.begin_capture("double_click")
                page.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_F9, Qt.NoModifier))

                self.assertEqual(page.profiles[KEY_CLICK_HOTKEY], "F8")
                self.assertEqual(page.profiles[KEY_DOUBLE_CLICK_HOTKEY], "F9")
                self.assertEqual(page.click_button.text(), "F8")
                self.assertEqual(page.double_click_button.text(), "F9")
                self.assertTrue(start_calls)

                page.begin_capture("client", slot=0)
                page.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_F8, Qt.NoModifier))
                self.assertNotEqual(page.slot_hotkey_label(0), "F8")

                page.profiles[organizer.client_slot_hotkey_key(0)] = "F10"
                page.begin_capture("click")
                page.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_F10, Qt.NoModifier))
                self.assertEqual(page.profiles[KEY_CLICK_HOTKEY], "F8")

                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertTrue(payload["global_hotkeys"]["click_enabled"])
                self.assertEqual(payload["global_hotkeys"]["click_hotkey"], "F8")
                self.assertTrue(payload["global_hotkeys"]["double_click_enabled"])
                self.assertEqual(payload["global_hotkeys"]["double_click_hotkey"], "F9")
                self.assertTrue(payload["global_hotkeys"]["debug_enabled"])
                ini_text = organizer.CLIENT_INDEX_INI.read_text(encoding="utf-8")
                self.assertIn("click_enabled=1", ini_text)
                self.assertIn("click_hotkey=F8", ini_text)
                self.assertIn("double_click_enabled=1", ini_text)
                self.assertIn("double_click_hotkey=F9", ini_text)
                self.assertIn("debug_enabled=1", ini_text)
                page.profiles[KEY_SWITCH_DOUBLE_CLICK] = False
                page.export_client_index()
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertFalse(payload["global_hotkeys"]["double_click_enabled"])
                self.assertEqual(payload["global_hotkeys"]["double_click_hotkey"], "")
                ini_text = organizer.CLIENT_INDEX_INI.read_text(encoding="utf-8")
                self.assertIn("double_click_enabled=0", ini_text)
                self.assertIn("double_click_hotkey=", ini_text)
                self.assertNotIn("double_click_hotkey=F9", ini_text)
                page.profiles[KEY_SWITCH_DOUBLE_CLICK] = True
                page.profiles[KEY_DOUBLE_CLICK_HOTKEY] = "F9"
                page.clear_global_hotkey(KEY_DOUBLE_CLICK_HOTKEY)
                self.assertFalse(page.profiles[KEY_SWITCH_DOUBLE_CLICK])
                start_calls.clear()
                page.reload_runtime()
                self.assertEqual(start_calls, [(True,)])
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_organizer_quick_actions_reload_and_debug(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            reload_calls = []
            statuses = []
            try:
                page = organizer.OrganizerPage(statuses.append, lambda *args: reload_calls.append(args))
                self.assertEqual(page.quick_actions_title.text(), "Action rapide")
                self.assertEqual(page.debug_button.objectName(), "secondaryButton")
                self.assertFalse(hasattr(page, "scan_button"))
                self.assertTrue(hasattr(page, "sessions_refresh_button"))
                self.assertEqual(page.macro_panel.height(), page.quick_actions_panel.height())
                self.assertEqual(page.script_speed_title.width(), page.stop_script_button.width())
                self.assertEqual(page.script_speed_normal.height(), page.script_speed_fast.height())

                page.reload_runtime_button.click()
                self.assertEqual(reload_calls[-1], (True,))

                reload_calls.clear()
                page.debug_button.click()
                self.assertTrue(page.profiles[KEY_DEBUG_MODE])
                self.assertEqual(page.debug_button.objectName(), "primaryButton")
                self.assertEqual(reload_calls, [(True,)])
                self.assertIn("Debug actif", statuses[-1])
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertTrue(payload["global_hotkeys"]["debug_enabled"])
                ini_text = organizer.CLIENT_INDEX_INI.read_text(encoding="utf-8")
                self.assertIn("debug_enabled=1", ini_text)

                reload_calls.clear()
                page.debug_button.click()
                self.assertFalse(page.profiles[KEY_DEBUG_MODE])
                self.assertEqual(page.debug_button.objectName(), "secondaryButton")
                self.assertEqual(reload_calls, [(True,)])
                self.assertIn("Debug inactif", statuses[-1])
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertFalse(payload["global_hotkeys"]["debug_enabled"])
                ini_text = organizer.CLIENT_INDEX_INI.read_text(encoding="utf-8")
                self.assertIn("debug_enabled=0", ini_text)

                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_organizer_does_not_export_implicit_client_hotkeys(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            organizer.CLIENT_INDEX_JSON.write_text(
                json.dumps(
                    {
                        "clients": [
                            {"index": 1, "label": "Perso 1", "handle": 101, "binding": "F5"},
                            {"index": 2, "label": "Perso 2", "handle": 202, "binding": "F6"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            try:
                page = organizer.OrganizerPage(lambda _text: None, lambda *args: None)
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertEqual(payload["clients"], [])
                self.assertNotIn("binding=F5", organizer.CLIENT_INDEX_INI.read_text(encoding="utf-8"))
                self.assertNotIn("binding=F6", organizer.CLIENT_INDEX_INI.read_text(encoding="utf-8"))

                page.sessions = page.build_session_slots([
                    {"nom": "Perso 1", "hwnd": 101},
                    {"nom": "Perso 2", "hwnd": 202},
                ])
                page.profiles["__raccourci_personnage_2__"] = "F8"
                page.export_client_index()
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertEqual([client["binding"] for client in payload["clients"]], ["", "F8"])
                self.assertEqual([client["binding_explicit"] for client in payload["clients"]], [False, True])
                ini_text = organizer.CLIENT_INDEX_INI.read_text(encoding="utf-8")
                self.assertIn("binding_explicit=0", ini_text)
                self.assertIn("binding_explicit=1", ini_text)
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_organizer_auto_group_sends_invites_to_runtime_for_all_detected_clients(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            start_calls = []
            auto_group_calls = []
            try:
                page = organizer.OrganizerPage(
                    lambda _text: None,
                    lambda *args: start_calls.append(args),
                    launch_auto_group_callback=lambda entries: auto_group_calls.append(entries),
                )
                page.sessions = [
                    {"nom": "Chef - Pandawa", "hwnd": 111},
                    {"nom": "Perso-Deux - Cra", "hwnd": 222},
                    {"nom": "Perso Trois - Enutrof", "hwnd": 333},
                ]
                start_calls.clear()

                self.assertEqual(page.switch_fake.text(), "Auto-groupe")
                page.launch_auto_group()

                self.assertFalse(start_calls)
                self.assertEqual(
                    auto_group_calls[-1],
                    [
                        {"name": "Chef", "handle": 111},
                        {"name": "Perso-Deux", "handle": 222},
                        {"name": "Perso Trois", "handle": 333},
                    ],
                )
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_organizer_ignores_legacy_travel_ui_and_export(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            organizer.PROFILE_FILE.write_text(
                json.dumps({organizer.KEY_TRAVEL_TEXT: "/travel -23,34"}),
                encoding="utf-8",
            )
            try:
                page = organizer.OrganizerPage(lambda _text: None, lambda *args: None)

                labels = [label.text() for label in page.findChildren(QLabel)]
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                ini_text = organizer.CLIENT_INDEX_INI.read_text(encoding="utf-8")

                self.assertFalse(hasattr(page, "travel_edit"))
                self.assertIn("Zaap", labels)
                self.assertNotIn("Travel & Zaap", labels)
                self.assertNotIn(organizer.KEY_TRAVEL_TEXT, page.profiles)
                self.assertNotIn("travel_text", payload["global_hotkeys"])
                self.assertNotIn("travel_text=", ini_text)
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_organizer_resolves_class_icons_from_window_names(self):
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_dirs = organizer.CLASS_ICON_DIRS
            try:
                organizer.CLASS_ICON_DIRS = (tmp_path,)
                (tmp_path / "pandawa.png").write_bytes(b"icon")
                (tmp_path / "cra.png").write_bytes(b"icon")

                self.assertEqual(organizer.dofus_class_key_from_window_name("Bob - Pandawa"), "pandawa")
                self.assertEqual(organizer.dofus_class_key_from_window_name("Perso-Deux - Crâ"), "cra")
                self.assertIsNone(organizer.dofus_class_key_from_window_name("Montagne des Craqueleurs"))
                self.assertEqual(organizer.class_icon_path_for_window_name("Bob - Pandawa"), tmp_path / "pandawa.png")
                self.assertEqual(organizer.class_icon_path_for_window_name("Perso-Deux - Cra"), tmp_path / "cra.png")
            finally:
                organizer.CLASS_ICON_DIRS = previous_dirs

    def test_organizer_session_order_is_reapplied_after_scan(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            try:
                page = organizer.OrganizerPage(lambda _text: None, lambda *args: None)
                page.sessions = page.build_session_slots([
                    {"nom": "Bob - Pandawa", "hwnd": 10},
                    {"nom": "Charlie - Enutrof", "hwnd": 20},
                    {"nom": "Dana - Sadida", "hwnd": 30},
                ])
                page.save_session_order()

                scanned = [
                    {"nom": "Dana - Sadida", "hwnd": 300},
                    {"nom": "Charlie - Enutrof", "hwnd": 200},
                    {"nom": "Bob - Pandawa", "hwnd": 100},
                    {"nom": "Nouveau - Cra", "hwnd": 400},
                ]
                ordered = page.build_session_slots(scanned)

                self.assertEqual([row["nom"] for row in ordered[:4]], [
                    "Bob - Pandawa",
                    "Charlie - Enutrof",
                    "Dana - Sadida",
                    "Nouveau - Cra",
                ])
                self.assertEqual(page.profiles[KEY_SESSION_ORDER], [
                    "bob_pandawa",
                    "charlie_enutrof",
                    "dana_sadida",
                    "",
                    "",
                    "",
                    "",
                    "",
                ])
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_organizer_primary_star_toggles_favorite(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            try:
                page = organizer.OrganizerPage(lambda _text: None, lambda *args: None)
                page.sessions = page.build_session_slots([
                    {"nom": "Perso 1", "hwnd": 101},
                    {"nom": "Perso 2", "hwnd": 202},
                ])

                page.set_primary_window(page.sessions[1])
                self.assertEqual(page.profiles[organizer.KEY_PRIMARY_WINDOW], "hwnd:202")
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertEqual(payload["global_hotkeys"]["primary_handle"], 202)

                page.set_primary_window(page.sessions[1])
                self.assertEqual(page.profiles[organizer.KEY_PRIMARY_WINDOW], "")
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertEqual(payload["global_hotkeys"]["primary_handle"], 0)
                self.assertFalse(any(client["primary"] for client in payload["clients"]))
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_organizer_clears_closed_windows_to_empty_slots(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
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
                self.assertEqual(page.sessions[0]["hwnd"], 10)
                self.assertEqual(page.sessions[1]["nom"], "")
                self.assertEqual(page.sessions[1]["hwnd"], 0)
                self.assertEqual(page.sessions[2]["nom"], "")
                self.assertEqual(page.sessions[2]["hwnd"], 0)
                self.assertEqual(page.profiles[KEY_SESSION_ORDER], ["bob_pandawa", "", "", "", "", "", "", ""])
                self.assertNotIn("Charlie - Enutrof", page.profiles)

                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertEqual(payload["count"], 1)
                self.assertEqual([client["label"] for client in payload["clients"]], ["Personnage 1"])
                self.assertEqual([client["index"] for client in payload["clients"]], [1])
                self.assertEqual(payload["clients"][0]["character_name"], "Bob")
                self.assertEqual(payload["clients"][0]["slot"], 1)
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_organizer_retries_new_unity_release_titles(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            try:
                page = organizer.OrganizerPage(lambda _text: None, lambda *args: None)
                page.sessions = page.build_session_slots(
                    [{"nom": "Dofus 3.6.10.11 Release", "hwnd": 10, "pid": 99}]
                )
                self.assertTrue(page.sessions_have_generic_names())
                page.sessions = page.build_session_slots(
                    [{"nom": "Bob - Pandawa", "hwnd": 10, "pid": 99}]
                )
                self.assertFalse(page.sessions_have_generic_names())
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_organizer_release_retries_are_bounded_and_temporary(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            try:
                page = organizer.OrganizerPage(lambda _text: None, lambda *args: None)
                page.session_event_watcher.stop()
                page.sessions = page.build_session_slots(
                    [
                        {"nom": "Bob - Pandawa", "hwnd": 10, "pid": 98},
                        {"nom": "Dofus 3.6.10.11 Release", "hwnd": 11, "pid": 99},
                    ]
                )
                self.assertTrue(page.sessions_have_generic_names())

                generic_sessions = [
                    {"nom": "Bob - Pandawa", "hwnd": 10, "pid": 98},
                    {"nom": "Dofus 3.6.10.11 Release", "hwnd": 11, "pid": 99},
                ]
                with patch.object(
                    organizer,
                    "scan_unity_sessions",
                    return_value=generic_sessions,
                ) as scan:
                    page.begin_release_identity_retries()
                    for expected_delay in organizer.RELEASE_RETRY_DELAYS_MS:
                        self.assertTrue(page.release_retry_timer.isActive())
                        self.assertEqual(page.release_retry_timer.interval(), expected_delay)
                        page.release_retry_timer.stop()
                        page.retry_release_identity()

                self.assertEqual(scan.call_count, len(organizer.RELEASE_RETRY_DELAYS_MS))
                self.assertFalse(page.release_retry_timer.isActive())
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_organizer_notifies_shell_when_release_title_becomes_character_name(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            notifications = []
            try:
                page = organizer.OrganizerPage(
                    lambda _text: None,
                    lambda *args: None,
                    sessions_changed_callback=lambda: notifications.append(
                        page.session_identity_signature()
                    ),
                )
                with patch.object(
                    organizer,
                    "scan_unity_sessions",
                    side_effect=[
                        [{"nom": "Dofus 3.6.10.11 Release", "hwnd": 10, "pid": 99}],
                        [{"nom": "Bob - Pandawa", "hwnd": 10, "pid": 99}],
                        [{"nom": "Bob - Pandawa", "hwnd": 10, "pid": 99}],
                    ],
                ):
                    page.refresh_sessions_and_export()
                    page.refresh_sessions_and_export()
                    page.refresh_sessions_and_export()

                self.assertEqual(len(notifications), 2)
                self.assertEqual(notifications[-1][0], (1, "Bob", 10, 99))
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertEqual(payload["clients"][0]["character_name"], "Bob")
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_organizer_window_event_detects_dofus_started_after_atlas(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            notifications = []
            try:
                page = organizer.OrganizerPage(
                    lambda _text: None,
                    lambda *args: None,
                    sessions_changed_callback=lambda: notifications.append(
                        page.session_identity_signature()
                    ),
                )
                page.session_event_watcher.stop()
                self.assertFalse(hasattr(page, "session_monitor_timer"))
                self.assertTrue(page.window_event_refresh_timer.isSingleShot())
                self.assertTrue(page.release_retry_timer.isSingleShot())
                detected = [{"nom": "Alice - Eliotrope", "hwnd": 20, "pid": 1324}]
                with patch.object(organizer, "scan_unity_sessions", return_value=detected):
                    page.refresh_sessions_from_window_event()
                    page.refresh_sessions_from_window_event()

                self.assertEqual(len(notifications), 1)
                self.assertEqual(notifications[0][0], (1, "Alice", 20, 1324))
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertEqual(payload["clients"][0]["character_name"], "Alice")
                self.assertEqual(page.profiles[KEY_SESSION_ORDER][0], "alice")

                with patch.object(organizer, "scan_unity_sessions", return_value=[]):
                    page.refresh_sessions_from_window_event()
                self.assertEqual(len(notifications), 2)
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_shell_refreshes_connected_character_name_after_organizer_scan(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer
        import main as main_module

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            profile_path = tmp_path / "client_profiles.json"
            client_index_path = tmp_path / "client_index.json"
            client_index_ini_path = tmp_path / "client_index.ini"
            with (
                patch.object(main_module, "PROFILE_FILE", profile_path),
                patch.object(main_module, "CLIENT_INDEX_JSON", client_index_path),
                patch.object(organizer, "PROFILE_FILE", profile_path),
                patch.object(organizer, "CLIENT_INDEX_JSON", client_index_path),
                patch.object(organizer, "CLIENT_INDEX_INI", client_index_ini_path),
                patch.object(
                    main_module,
                    "load_quest_characters",
                    return_value=[QuestCharacter("character:1", "Alpha", 1, False)],
                ) as character_loader,
            ):
                window = AtlasWindow(initial_preload={"_test": True})
                self.assertEqual(window.character_combo.currentText(), "")

                character_loader.return_value = [QuestCharacter("character:1", "Bob", 1, True)]
                organizer_page = window.page_widgets["Organizer"]
                organizer_page.sessions = organizer_page.build_session_slots(
                    [{"nom": "Bob - Pandawa", "hwnd": 10, "pid": 99}]
                )
                organizer_page.export_client_index()
                organizer_page.notify_sessions_changed()

                self.assertEqual(window.character_combo.currentText(), "Bob")
                self.assertEqual(window.home_page.character_name.text(), "Bob")
                window.deleteLater()
                app.processEvents()

    def test_shell_follows_only_connected_character_without_organizer_favorite(self):
        app = QApplication.instance() or QApplication([])
        import main as main_module

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            profile_path = tmp_path / "client_profiles.json"
            client_index_path = tmp_path / "client_index.json"
            client_index_path.write_text(
                json.dumps({"clients": [{"character_name": "Alice", "primary": False}]}),
                encoding="utf-8",
            )
            with (
                patch.object(main_module, "PROFILE_FILE", profile_path),
                patch.object(main_module, "CLIENT_INDEX_JSON", client_index_path),
                patch.object(
                    main_module,
                    "load_quest_characters",
                    return_value=[QuestCharacter("character:1", "Alice", 1, True)],
                ) as character_loader,
            ):
                window = AtlasWindow(initial_preload={"_test": True})
                self.assertEqual(window.current_character_key, "character:1")

                character_loader.return_value = [
                    QuestCharacter("character:1", "Alice", 1, False),
                    QuestCharacter("character:9", "Bob", 9, True),
                ]
                client_index_path.write_text(
                    json.dumps({"clients": [{"character_name": "Bob", "primary": False}]}),
                    encoding="utf-8",
                )
                window.on_network_character_activated("character:9")

                self.assertEqual(window.current_character_key, "character:9")
                self.assertEqual(window.character_combo.currentText(), "Bob")
                self.assertEqual(window.home_page.character_name.text(), "Bob")
                self.assertEqual(window.character_combo.itemText(0), "Bob")
                stored = json.loads(profile_path.read_text(encoding="utf-8"))
                self.assertEqual(stored["__personnage_selectionne_ui__"], "character:9")
                window.deleteLater()
                app.processEvents()

    def test_shell_follows_organizer_favorite_character_after_network_identity(self):
        app = QApplication.instance() or QApplication([])
        import main as main_module

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            profile_path = tmp_path / "client_profiles.json"
            client_index_path = tmp_path / "client_index.json"
            client_index_path.write_text(
                json.dumps(
                    {
                        "clients": [
                            {
                                "character_name": "Bob",
                                "primary": True,
                                "pid": 99,
                                "slot": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(main_module, "PROFILE_FILE", profile_path),
                patch.object(main_module, "CLIENT_INDEX_JSON", client_index_path),
                patch.object(
                    main_module,
                    "load_quest_characters",
                    return_value=[QuestCharacter("character:1", "Alice", 1, True)],
                ) as character_loader,
            ):
                window = AtlasWindow(initial_preload={"_test": True})
                character_loader.return_value = [
                    QuestCharacter("character:1", "Alice", 1, True),
                    QuestCharacter("character:9", "Bob", 9, True),
                ]

                window.on_network_character_activated("character:9")

                self.assertEqual(window.current_character_key, "character:9")
                self.assertEqual(window.character_combo.currentText(), "Bob")
                self.assertEqual(window.home_page.character_name.text(), "Bob")
                stored = json.loads(profile_path.read_text(encoding="utf-8"))
                self.assertEqual(stored["__personnage_selectionne_ui__"], "character:9")
                window.deleteLater()
                app.processEvents()

    def test_shell_hides_slot_placeholders_when_no_character_is_connected(self):
        app = QApplication.instance() or QApplication([])
        import main as main_module

        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "client_profiles.json"
            with (
                patch.object(main_module, "PROFILE_FILE", profile_path),
                patch.object(main_module, "load_quest_characters", return_value=[]),
            ):
                window = AtlasWindow(initial_preload={"_test": True})

                self.assertEqual(window.character_combo.count(), 0)
                self.assertEqual(
                    window.home_page.character_name.text(),
                    "Aucun personnage connecté",
                )
                window.deleteLater()
                app.processEvents()

    def test_organizer_can_move_session_to_exact_empty_slot(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
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
                self.assertEqual(page.profiles[KEY_SESSION_ORDER], ["", "perso_2", "perso_3", "", "", "", "", "perso_1"])
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertEqual([client["label"] for client in payload["clients"]], [
                    "Personnage 1",
                    "Personnage 2",
                    "Personnage 3",
                ])
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_organizer_drag_can_move_first_session_to_last_position_and_persist(self):
        app = QApplication.instance() or QApplication([])
        import app.pages.organizer_page as organizer

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            previous_paths = {
                "PROFILE_FILE": organizer.PROFILE_FILE,
                "CLIENT_INDEX_JSON": organizer.CLIENT_INDEX_JSON,
                "CLIENT_INDEX_INI": organizer.CLIENT_INDEX_INI,
            }
            organizer.PROFILE_FILE = tmp_path / "client_profiles.json"
            organizer.CLIENT_INDEX_JSON = tmp_path / "client_index.json"
            organizer.CLIENT_INDEX_INI = tmp_path / "client_index.ini"
            try:
                page = organizer.OrganizerPage(lambda _text: None, lambda *args: None)
                page.sessions = [{"nom": f"Perso {index}", "hwnd": 100 + index} for index in range(1, 9)]
                page.render_sessions()
                page.drag_session_index = 0
                page.drag_session_row = page.session_row_widgets[0][0]
                page.drag_session_key = page.session_drag_key(page.sessions[0])

                moved = page.move_dragged_session_to_drop_index(len(page.sessions))
                page.drag_drop_index = len(page.sessions)
                page.finish_session_drag(None)

                self.assertTrue(moved)
                self.assertEqual([session["nom"] for session in page.sessions], [
                    "Perso 8",
                    "Perso 2",
                    "Perso 3",
                    "Perso 4",
                    "Perso 5",
                    "Perso 6",
                    "Perso 7",
                    "Perso 1",
                ])
                self.assertEqual(page.profiles[KEY_SESSION_ORDER], [
                    "perso_8",
                    "perso_2",
                    "perso_3",
                    "perso_4",
                    "perso_5",
                    "perso_6",
                    "perso_7",
                    "perso_1",
                ])
                payload = json.loads(organizer.CLIENT_INDEX_JSON.read_text(encoding="utf-8"))
                self.assertEqual([client["label"] for client in payload["clients"]], [
                    "Personnage 1",
                    "Personnage 2",
                    "Personnage 3",
                    "Personnage 4",
                    "Personnage 5",
                    "Personnage 6",
                    "Personnage 7",
                    "Personnage 8",
                ])
                page.deleteLater()
                app.processEvents()
            finally:
                for name, value in previous_paths.items():
                    setattr(organizer, name, value)

    def test_python_runtime_hotkeys_and_timings_replace_external_script(self):
        simple, error = parse_hotkey("F12")
        self.assertFalse(error)
        self.assertEqual(simple.canonical, "F12")

        combo, error = parse_hotkey("Ctrl+Alt+F12")
        self.assertFalse(error)
        self.assertEqual(combo.canonical, "CTRL+ALT+F12")

        self.assertEqual(timings_for_speed("normal").switch_background_pre_click_ms, 35)
        self.assertEqual(timings_for_speed("rapide").switch_background_pre_click_ms, 18)
        self.assertEqual(
            ZaapTimings(),
            ZaapTimings(
                focus_settle_ms=10,
                activate_attempts=5,
                activate_retry_ms=2,
                open_wait_ms=1200,
                click_settle_ms=250,
                submit_settle_ms=70,
                input_click_down_ms=1,
                input_double_gap_ms=5,
                reliable_click_pre_ms=35,
                reliable_click_post_ms=25,
            ),
        )

        settings = load_settings()
        actions = build_hotkey_actions(settings)
        action_ids = {action.action_id for action in actions}
        self.assertTrue(all("window" not in action_id for action_id in action_ids))

    def test_press_hotkey_fires_once_until_release_even_after_reset(self):
        from app.input.input_state import InputState

        calls = []
        input_state = InputState()
        registry = HotkeyRegistry(input_state, logging.getLogger("test_hotkeys"), lambda action_id, payload: calls.append(action_id))
        report = registry.register_hotkeys(
            [
                HotkeyAction(
                    action_id="stop_script",
                    label="Stop urgence",
                    hotkey_text="F10",
                    kind="press",
                )
            ]
        )
        self.assertTrue(report.ok)
        vk_f10 = next(iter(report.actions[0].spec.keys))

        input_state.set_key(vk_f10, True)
        registry._dispatch_matching_hotkeys()
        input_state.reset_armed()
        input_state.set_key(vk_f10, True)
        registry._dispatch_matching_hotkeys()
        self.assertEqual(calls, ["stop_script"])

        input_state.set_key(vk_f10, False)
        registry._dispatch_matching_hotkeys()
        input_state.set_key(vk_f10, True)
        registry._dispatch_matching_hotkeys()
        self.assertEqual(calls, ["stop_script", "stop_script"])

    def test_general_timings_are_not_too_low_for_reliable_macros(self):
        rapide = timings_for_speed("rapide")
        normal = timings_for_speed("normal")
        self.assertGreaterEqual(rapide.click_focus_settle_ms, 8)
        self.assertGreaterEqual(rapide.activate_retry_ms, 12)
        self.assertGreaterEqual(rapide.auto_group_paste_settle_ms, 45)
        self.assertGreaterEqual(normal.auto_group_invite_gap_ms, rapide.auto_group_invite_gap_ms)

    def test_hwnd_value_handles_null_windows_handle(self):
        self.assertEqual(hwnd_value(None), 0)
        self.assertEqual(hwnd_value(123), 123)


if __name__ == "__main__":
    unittest.main()

