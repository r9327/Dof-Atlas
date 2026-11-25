from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget
from shiboken6 import isValid

from app.modules.encyclopedia.constants import GUIDES_TAB, ACHIEVEMENTS_TAB, QUESTS_TAB

import app.ui.network_bridge as network_bridge_module
from main import AtlasWindow


class AtlasWindowRuntimeCleanupTests(unittest.TestCase):
    def tearDown(self) -> None:
        bridge = getattr(network_bridge_module, "_BRIDGE", None)
        if bridge is not None:
            bridge.stop()
        network_bridge_module._BRIDGE = None

    def test_topmost_projection_preserves_outer_signal_block(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QCheckBox
        app = QApplication.instance() or QApplication([])
        checkbox = QCheckBox()
        shell = SimpleNamespace(settings_topmost_check=checkbox, topmost_enabled=True)
        try:
            for previous in (True, False):
                checkbox.blockSignals(previous)
                AtlasWindow.update_topmost_button(shell)
                self.assertEqual(checkbox.signalsBlocked(), previous)
                self.assertTrue(checkbox.isChecked())
        finally:
            checkbox.deleteLater()

    def test_network_closed_session_updates_connected_list_without_selection(self):
        shell = Mock()
        AtlasWindow.on_network_connections_changed(
            shell, ("character:2", "character:1")
        )
        shell.refresh_global_characters.assert_called_once_with(
            allow_default_selection=False, network_refresh=True,
        )
        shell.on_network_character_activated.assert_not_called()
        shell.character_combo.setCurrentIndex.assert_not_called()

    def test_network_closed_session_rejects_unverified_or_empty_identity(self):
        shell = Mock()
        for payload in (
            (), None, "", {"character:1"},
            ("slot:1", "character:0", None),
            ("character:01", "character:-1"),
            ("character:" + "9" * 5000,),
        ):
            AtlasWindow.on_network_connections_changed(shell, payload)
        shell.refresh_global_characters.assert_not_called()
        shell.on_network_character_activated.assert_not_called()
        AtlasWindow.on_network_connections_changed(
            shell, ("slot:1", "character:9")
        )
        shell.refresh_global_characters.assert_called_once_with(
            allow_default_selection=False, network_refresh=True,
        )

    def test_canonical_character_parser_rejects_unbounded_numeric_key(self):
        from app.core.character_identity import (
            character_id_from_key, is_character_key,
        )

        invalid = "character:" + "9" * 5000
        self.assertIsNone(character_id_from_key(invalid))
        self.assertFalse(is_character_key(invalid))
        self.assertFalse(is_character_key("character:01"))
        self.assertTrue(is_character_key("character:123456"))

    def test_network_identity_batch_refreshes_multiple_accounts_once(self):
        shell = Mock()
        AtlasWindow.on_network_characters_identified(
            shell, ("character:3", "character:2", "character:3")
        )

        shell.refresh_global_characters.assert_called_once_with(
            allow_default_selection=False, network_refresh=True,
        )
        shell.on_network_character_activated.assert_not_called()
        shell.character_combo.setCurrentIndex.assert_not_called()

    def test_network_identity_batch_preserves_single_identity_selection(self):
        shell = Mock()
        AtlasWindow.on_network_characters_identified(
            shell, ("character:7", "character:7")
        )

        shell.on_network_character_activated.assert_called_once_with("character:7")
        shell.refresh_global_characters.assert_not_called()

    def test_network_identity_batch_rejects_empty_or_invalid_payloads(self):
        shell = Mock()
        for payload in (None, "", (), ("", None), {"character:1"}):
            AtlasWindow.on_network_characters_identified(shell, payload)

        shell.refresh_global_characters.assert_not_called()
        shell.on_network_character_activated.assert_not_called()

    def test_network_initial_selection_uses_verified_key_not_window_name(self):
        from types import SimpleNamespace

        shell = Mock()
        shell.current_character_key = ""
        shell._last_active_dofus_hwnd = 234
        shell.character_combo.count.return_value = 2
        # Same displayed name can exist on two servers: only the verified
        # network-resolved character ID may select the account.
        shell.character_combo.itemText.side_effect = lambda _index: "Witsis"
        shell.character_combo.itemData.side_effect = lambda index: SimpleNamespace(
            key=("character:1", "character:2")[index],
        )
        with patch("main.read_json",
                   side_effect=AssertionError("do not guess from client index")):
            AtlasWindow.on_network_character_activated(shell, "character:1")

        shell.refresh_global_characters.assert_called_once_with(
            verified_initial_key="character:1", allow_default_selection=False,
            network_refresh=True,
        )
        shell.character_combo.setCurrentIndex.assert_not_called()
        shell.on_global_character_changed.assert_not_called()

    def test_network_initial_selection_rejects_missing_verified_key(self):
        from types import SimpleNamespace

        shell = Mock()
        shell.current_character_key = ""
        shell.character_combo.count.return_value = 2
        shell.character_combo.itemData.side_effect = lambda index: SimpleNamespace(
            key=("character:1", "character:2")[index],
        )
        with patch("main.read_json",
                   side_effect=AssertionError("do not guess from client index")):
            AtlasWindow.on_network_character_activated(shell, "character:999")

        shell.refresh_global_characters.assert_called_once_with(
            verified_initial_key="character:999", allow_default_selection=False,
            network_refresh=True,
        )
        shell.character_combo.setCurrentIndex.assert_not_called()
        shell.on_global_character_changed.assert_not_called()

    def test_network_initial_selection_does_not_pick_duplicate_key(self):
        from types import SimpleNamespace

        shell = Mock()
        shell.current_character_key = ""
        shell.character_combo.count.return_value = 2
        shell.character_combo.itemData.side_effect = lambda _index: SimpleNamespace(
            key="character:1",
        )

        AtlasWindow.on_network_character_activated(shell, "character:1")

        shell.character_combo.setCurrentIndex.assert_not_called()
        shell.on_global_character_changed.assert_not_called()

    def test_network_activation_does_not_repersist_already_selected_character(self):
        from types import SimpleNamespace

        shell = Mock()
        shell.current_character_key = "character:7"
        shell.character_combo.count.return_value = 1
        shell.character_combo.itemData.return_value = SimpleNamespace(
            key="character:7",
        )

        AtlasWindow.on_network_character_activated(shell, "character:7")

        shell.refresh_global_characters.assert_called_once_with(
            verified_initial_key="character:7", allow_default_selection=False,
            network_refresh=True,
        )
        shell.character_combo.setCurrentIndex.assert_not_called()
        shell.on_global_character_changed.assert_not_called()

    def test_network_background_login_never_overrides_manual_character(self):
        shell = Mock()
        shell.current_character_key = "character:2"

        # These are real verified session identities, but neither proves
        # that its corresponding DOFUS window currently has the focus.
        AtlasWindow.on_network_character_activated(shell, "character:1")
        AtlasWindow.on_network_character_activated(shell, "character:3")

        self.assertEqual(shell.refresh_global_characters.call_count, 2)
        shell.character_combo.setCurrentIndex.assert_not_called()
        shell.on_global_character_changed.assert_not_called()

    def test_verified_initial_identity_selects_only_matching_connected_account(self):
        from app.quest_catalog import QuestCharacter

        QApplication.instance() or QApplication([])
        shell = Mock()
        shell.current_character_key = ""
        shell._known_characters.return_value = [
            QuestCharacter("character:1", "Witsis", 1),
            QuestCharacter("character:2", "Lokidor", 2),
        ]
        shell._connected_characters.return_value = shell._known_characters.return_value
        shell.character_icon_path.return_value = ""
        shell.character_combo.blockSignals.return_value = False
        with patch("main.record_validation"):
            AtlasWindow.refresh_global_characters(
                shell, verified_initial_key="character:2",
                allow_default_selection=False, network_refresh=True,
            )

        self.assertEqual(shell.current_character_key, "character:2")
        self.assertEqual(shell.current_character_label, "Lokidor")
        shell.character_combo.setCurrentIndex.assert_called_once_with(1)
        shell.persist_selected_character.assert_called_once_with()
        shell.home_page.set_character.assert_called_once()

    def test_concurrent_login_without_selection_stays_unselected(self):
        from app.quest_catalog import QuestCharacter

        QApplication.instance() or QApplication([])
        shell = Mock()
        shell.current_character_key = ""
        shell._known_characters.return_value = [
            QuestCharacter("character:1", "Witsis", 1),
            QuestCharacter("character:2", "Lokidor", 2),
        ]
        shell._connected_characters.return_value = shell._known_characters.return_value
        shell.character_icon_path.return_value = ""
        shell.character_combo.blockSignals.return_value = False
        with patch("main.record_validation"):
            AtlasWindow.refresh_global_characters(
                shell, allow_default_selection=False,
                network_refresh=True,
            )

        self.assertEqual(shell.current_character_key, "")
        self.assertEqual(shell.current_character_label, "Aucun personnage sélectionné")
        shell.character_combo.setCurrentIndex.assert_called_once_with(-1)
        # A neutral network batch cannot rewrite a persisted manual choice
        # merely because it has no selected identity to report.
        shell.persist_selected_character.assert_not_called()

    def test_repeated_network_identification_does_not_rewrite_selected_profile(self):
        from app.quest_catalog import QuestCharacter

        QApplication.instance() or QApplication([])
        shell = Mock()
        shell.current_character_key = "character:2"
        shell._character_combo_signature = (
            ("character:1", "Witsis", "", ""),
            ("character:2", "Lokidor", "", ""),
        )
        shell._known_characters.return_value = [
            QuestCharacter("character:1", "Witsis", 1),
            QuestCharacter("character:2", "Lokidor", 2),
        ]
        shell._connected_characters.return_value = shell._known_characters.return_value
        shell.character_icon_path.return_value = ""
        shell.character_combo.blockSignals.return_value = False
        with patch("main.record_validation"):
            AtlasWindow.refresh_global_characters(
                shell, verified_initial_key="character:1",
                allow_default_selection=False, network_refresh=True,
            )
        self.assertEqual(shell.current_character_key, "character:2")
        shell.character_combo.setCurrentIndex.assert_called_once_with(1)
        shell.persist_selected_character.assert_not_called()
        shell.character_combo.clear.assert_not_called()
        shell.sync_selected_character_to_pages.assert_not_called()
        shell._refresh_visible_guide_connections.assert_called_once_with()
        # Client-window hotkeys still need reconciling even when the
        # account and its UI projection have not changed.
        shell._refresh_runtime_hotkeys_for_client_mapping.assert_called_once()

    def test_network_guide_refresh_never_materializes_or_repaints_hidden_pages(self):
        from types import SimpleNamespace

        class Page:
            def __init__(self):
                self.visible = True
                self.guides_view = Mock()
            def isVisible(self):
                return self.visible

        page = Page()
        shell = SimpleNamespace(page_factories={"Quetes": object()},
                                page_widgets={"Quetes": page})
        with patch("main._resolve_encyclopedia_page", return_value=Page) as resolve:
            AtlasWindow._refresh_visible_guide_connections(shell)
            resolve.assert_not_called()
            shell.page_factories.clear()
            page.visible = False
            AtlasWindow._refresh_visible_guide_connections(shell)
            resolve.assert_not_called()
            page.guides_view.refresh_connection_state.assert_not_called()
            page.visible = True
            AtlasWindow._refresh_visible_guide_connections(shell)
            page.guides_view.refresh_connection_state.assert_called_once_with()
            page.guides_view.refresh_external_progress.assert_not_called()
            page.guides_view.set_character_key.assert_not_called()

    def test_new_verified_class_updates_live_pages_without_rewriting_selection(self):
        from app.quest_catalog import QuestCharacter

        QApplication.instance() or QApplication([])
        shell = Mock()
        shell.current_character_key = "character:2"
        shell._character_combo_signature = (
            ("character:1", "Witsis", "", ""),
            ("character:2", "Lokidor", "", ""),
        )
        shell._known_characters.return_value = [
            QuestCharacter("character:1", "Witsis", 1),
            QuestCharacter("character:2", "Lokidor", 2, class_key="huppermage"),
        ]
        shell._connected_characters.return_value = shell._known_characters.return_value
        shell.character_icon_path.return_value = ""
        shell.character_combo.blockSignals.return_value = False
        with patch("main.record_validation"):
            AtlasWindow.refresh_global_characters(
                shell, allow_default_selection=False,
                network_refresh=True,
            )

        self.assertEqual(shell.current_character_key, "character:2")
        shell.character_combo.clear.assert_called_once_with()
        shell.sync_selected_character_to_pages.assert_called_once_with()
        shell.persist_selected_character.assert_not_called()
        shell._refresh_runtime_hotkeys_for_client_mapping.assert_called_once()

    def test_network_initialization_rejects_duplicate_key_and_preserves_manual_choice(self):
        from app.quest_catalog import QuestCharacter

        QApplication.instance() or QApplication([])
        shell = Mock()
        shell.current_character_key = ""
        shell._known_characters.return_value = [
            QuestCharacter("character:1", "Compte A", 1),
            QuestCharacter("character:1", "Compte B", 2),
        ]
        shell._connected_characters.return_value = shell._known_characters.return_value
        shell.character_icon_path.return_value = ""
        shell.character_combo.blockSignals.return_value = False
        with patch("main.record_validation"):
            AtlasWindow.refresh_global_characters(
                shell, verified_initial_key="character:1",
                allow_default_selection=False, network_refresh=True,
            )
        self.assertEqual(shell.current_character_key, "")
        shell.character_combo.setCurrentIndex.assert_called_once_with(-1)

        shell.character_combo.reset_mock()
        shell.current_character_key = "character:2"
        shell._known_characters.return_value = [
            QuestCharacter("character:2", "Manuel", 3),
            QuestCharacter("character:1", "Réseau", 1),
        ]
        shell._connected_characters.return_value = shell._known_characters.return_value
        with patch("main.record_validation"):
            AtlasWindow.refresh_global_characters(
                shell, verified_initial_key="character:1",
                allow_default_selection=False, network_refresh=True,
            )
        self.assertEqual(shell.current_character_key, "character:2")
        shell.character_combo.setCurrentIndex.assert_called_once_with(0)

    def test_organizer_foreground_handle_never_implies_a_character_identity(self):
        shell = Mock()
        shell._last_active_dofus_hwnd = 0

        AtlasWindow.on_organizer_active_window(shell, 1432)
        self.assertEqual(shell._last_active_dofus_hwnd, 1432)
        shell.refresh_global_characters.assert_called_once_with(
            allow_default_selection=False,
        )

        shell.refresh_global_characters.reset_mock()
        AtlasWindow.on_organizer_active_window(shell, "not-a-window")
        shell.refresh_global_characters.assert_not_called()
        self.assertEqual(shell._last_active_dofus_hwnd, 1432)

        AtlasWindow.on_organizer_active_window(shell, 0)
        self.assertEqual(shell._last_active_dofus_hwnd, 0)
        shell.refresh_global_characters.assert_called_once_with(
            allow_default_selection=False,
        )

    def test_manual_refresh_persists_cleared_selection_even_when_key_precleared(self):
        from app.quest_catalog import QuestCharacter

        QApplication.instance() or QApplication([])
        shell = Mock()
        # The Character page clears this field before refresh after deletion.
        shell.current_character_key = ""
        shell._known_characters.return_value = [
            QuestCharacter("character:1", "Un autre compte", 1),
        ]
        shell._connected_characters.return_value = []
        shell.character_icon_path.return_value = ""
        shell.character_combo.blockSignals.return_value = False
        shell._character_combo_signature = ()
        with patch("main.record_validation"):
            AtlasWindow.refresh_global_characters(shell)

        self.assertEqual(shell.current_character_key, "")
        shell.persist_selected_character.assert_called_once_with()
        shell.sync_selected_character_to_pages.assert_called_once_with()

    def test_manual_offline_profile_edit_refreshes_pages_with_unchanged_combo(self):
        from app.quest_catalog import QuestCharacter

        QApplication.instance() or QApplication([])
        shell = Mock()
        shell.current_character_key = "character:1"
        online = QuestCharacter("character:1", "Connecté", 1)
        offline = QuestCharacter("character:2", "Nouveau hors ligne", 2)
        shell._known_characters.return_value = [online, offline]
        shell._connected_characters.return_value = [online]
        shell._character_combo_signature = (
            ("character:1", "Connecté", "", ""),
        )
        shell.character_icon_path.return_value = ""
        shell.character_combo.blockSignals.return_value = False
        with patch("main.record_validation"):
            AtlasWindow.refresh_global_characters(shell)

        shell.character_combo.clear.assert_not_called()
        shell.persist_selected_character.assert_called_once_with()
        shell.sync_selected_character_to_pages.assert_called_once_with()
        shell._refresh_runtime_hotkeys_for_client_mapping.assert_called_once_with()

    def test_network_progress_hidden_encyclopedia_refreshes_only_on_return(self):
        shell = Mock()
        shell.current_character_key = "character:1"
        shell._pending_network_progress_character = ""
        shell.page_indexes = {"Quetes": 0}
        shell.page_factories = {}
        shell.page_nav_group = {"Quetes": "Encyclopédie"}
        page = Mock()
        page.objectName.return_value = "EncyclopediaPage"
        page.isVisible.return_value = False
        page.current_character_key = "character:1"
        shell.page_widgets = {"Quetes": page}
        current = page.tabs.currentWidget.return_value

        AtlasWindow.on_network_progress_changed(shell, "character:1")
        self.assertEqual(shell._pending_network_progress_character, "character:1")
        current.refresh_external_progress.assert_not_called()

        with patch("main._resolve_encyclopedia_page", return_value=type(page)):
            AtlasWindow.switch_to_page(shell, "Quetes")
        current.refresh_external_progress.assert_called_once_with()
        self.assertEqual(shell._pending_network_progress_character, "")
        page.set_character_key.assert_called_once_with("character:1")

    def test_network_progress_hidden_encyclopedia_ignores_other_character(self):
        shell = Mock()
        shell.current_character_key = "character:1"
        shell._pending_network_progress_character = ""
        page = Mock()
        page.objectName.return_value = "EncyclopediaPage"
        page.isVisible.return_value = False
        page.current_character_key = "character:1"
        shell.page_widgets = {"Quetes": page}

        AtlasWindow.on_network_progress_changed(shell, "character:2")
        self.assertEqual(shell._pending_network_progress_character, "")
        page.tabs.currentWidget.return_value.refresh_external_progress.assert_not_called()

    def test_tray_restore_replays_deferred_network_progress_without_tab_switch(self):
        shell = Mock()
        shell.current_character_key = "character:1"
        shell._pending_network_progress_character = "character:1"
        page = Mock()
        page.objectName.return_value = "EncyclopediaPage"
        page.isVisible.return_value = False
        page.current_character_key = "character:1"
        shell.page_widgets = {"Quetes": page}
        shell.on_network_progress_changed = (
            lambda key: AtlasWindow.on_network_progress_changed(shell, key)
        )
        callbacks = []
        shell._schedule_owned_callback.side_effect = (
            lambda delay, callback: callbacks.append((delay, callback))
        )

        AtlasWindow.restore_from_tray(shell)
        shell.showNormal.assert_called_once_with()
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(callbacks[0][0], 0)
        page.tabs.currentWidget.return_value.refresh_external_progress.assert_not_called()

        # The owned callback fires after Qt has shown the page again.
        page.isVisible.return_value = True
        callbacks[0][1]()
        page.tabs.currentWidget.return_value.refresh_external_progress.assert_called_once_with()
        self.assertEqual(shell._pending_network_progress_character, "")

    def test_tray_restore_does_not_replay_stale_character(self):
        shell = Mock()
        shell.current_character_key = "character:2"
        shell._pending_network_progress_character = "character:1"

        AtlasWindow.restore_from_tray(shell)
        shell._schedule_owned_callback.assert_not_called()

    def test_guide_travel_dispatch_returns_real_result_without_reloading_active_macro(self):
        shell = Mock()
        shell.quit_requested = False
        shell._background_services_stopped = False
        shell.runtime.macro_lock.active_label = "Travel"
        shell.runtime.macro_lock.emergency_latched = False

        self.assertFalse(AtlasWindow.launch_guide_travel(
            shell, "/travel 4,-3", ["character:1"],
        ))
        shell.reload_runtime.assert_not_called()
        shell._ensure_runtime.assert_not_called()

        shell.runtime.macro_lock.active_label = ""
        shell.runtime.macro_lock.emergency_latched = True
        self.assertFalse(AtlasWindow.launch_guide_travel(
            shell, "/travel 4,-3", ["character:1"],
        ))
        shell.reload_runtime.assert_not_called()

        shell.runtime.macro_lock.emergency_latched = False
        shell._ensure_runtime.return_value.launch_guide_travel.return_value = False
        self.assertFalse(AtlasWindow.launch_guide_travel(
            shell, "/travel 4,-3", ["character:1"],
        ))
        shell._ensure_runtime.return_value.launch_guide_travel.assert_called_once_with(
            "/travel 4,-3", ("character:1",),
        )

        shell._ensure_runtime.return_value.launch_guide_travel.return_value = True
        self.assertTrue(AtlasWindow.launch_guide_travel(
            shell, "/travel 4,-3", ["character:1"],
        ))

        shell.quit_requested = True
        shell.reload_runtime.reset_mock()
        self.assertFalse(AtlasWindow.launch_guide_travel(
            shell, "/travel 4,-3", ["character:1"],
        ))
        shell.reload_runtime.assert_not_called()

    def test_deferred_organizer_reload_after_close_cannot_restart_runtime(self) -> None:
        app = QApplication.instance() or QApplication([])
        with patch.object(AtlasWindow, "setup_tray", return_value=None):
            window = AtlasWindow()
        runtime = window._ensure_runtime()
        organizer = window.ensure_page_loaded("Organizer")
        bridge = Mock()
        bridge.stop.return_value = True
        window.home_page.network_bridge = bridge
        try:
            with (
                patch.object(runtime, "start") as start_runtime,
                patch.object(runtime, "reload_hotkeys") as reload_hotkeys,
            ):
                window.quit_requested = True
                window.close()
                app.processEvents()
                organizer.reload_runtime_callback()
                app.processEvents()

                start_runtime.assert_not_called()
                reload_hotkeys.assert_not_called()

            self.assertTrue(window._background_services_stopped)
            bridge.stop.assert_called_once_with()
        finally:
            window.quit_requested = True
            window.close()
            window.deleteLater()
            app.processEvents()

    def test_quests_guides_success_navigation_releases_heavy_page_on_home(self) -> None:
        # Real Atlas navigation methods and Qt widgets, with fake data
        # providers: neither a real user profile nor a huge catalog is opened.
        app = QApplication.instance() or QApplication([])
        shell = type("MinimalAtlasShell", (), {})()
        shell.stack = QStackedWidget()
        home, encyclopedia = QWidget(), QWidget()
        home.release_encyclopedia_context = Mock()
        home.refresh_progress = Mock()
        encyclopedia.release_runtime = Mock()
        shell.stack.addWidget(home)
        shell.stack.addWidget(encyclopedia)
        shell.home_page = home
        shell.page_widgets = {"Home": home, "Quetes": encyclopedia}
        shell.page_indexes = {"Home": 0, "Quetes": 1}
        shell.pages = [("Home", home), ("Quetes", encyclopedia)]
        shell.page_factories = {}
        shell.page_nav_group = {"Home": "Accueil", "Quetes": "Encyclopédie"}
        shell.pending_encyclopedia_tab = ""
        shell.pending_page_name = ""
        shell.current_character_key = None
        shell.hide_module_subnav = Mock()
        shell.refresh_nav_selection = Mock()
        shell.refresh_global_characters = Mock()
        shell.finish_pending_encyclopedia_tab = Mock()
        shell.finish_pending_guide_target = Mock()
        shell._schedule_owned_callback = Mock()
        shell.page_ready_for_navigation = lambda widget: True
        shell.loading_page = lambda name: QWidget()
        shell.create_encyclopedia_page = lambda: QWidget()
        shell.create_craft_page = lambda: QWidget()
        shell.create_equipment_page = lambda: QWidget()
        shell.create_dev_ui_page = lambda: QWidget()
        shell.rebuild_page_indexes = lambda: setattr(
            shell, "page_indexes",
            {name: shell.stack.indexOf(widget)
             for name, widget in shell.page_widgets.items()},
        )
        shell.switch_to_page = lambda name: AtlasWindow.switch_to_page(shell, name)
        shell.show_page = lambda name: AtlasWindow.show_page(shell, name)
        shell.release_reconstructible_page = (
            lambda name, factory: AtlasWindow.release_reconstructible_page(
                shell, name, factory
            )
        )
        # Bind real cleanup methods added to AtlasWindow, not no-op mocks:
        # this test uses a minimal shell but must exercise production Home logic.
        shell._hibernate_world_scan_on_home = (
            lambda: AtlasWindow._hibernate_world_scan_on_home(shell)
        )
        shell.release_transient_placeholders = (
            lambda: AtlasWindow.release_transient_placeholders(shell)
        )
        shell.collect_released_page_cycles = AtlasWindow.collect_released_page_cycles

        try:
            for tab in (QUESTS_TAB, GUIDES_TAB, ACHIEVEMENTS_TAB):
                AtlasWindow.open_encyclopedia_tab(shell, tab)
                self.assertEqual(shell.pending_encyclopedia_tab, tab)
                self.assertIs(shell.stack.currentWidget(), encyclopedia)
                self.assertNotIn("Quetes", shell.page_factories)

            shell.show_page("Home")
            self.assertIs(shell.stack.currentWidget(), home)
            encyclopedia.release_runtime.assert_called_once_with()
            home.release_encyclopedia_context.assert_called_once_with(
                preserve_display=True
            )
            home.refresh_progress.assert_called_once_with()
            self.assertIn("Quetes", shell.page_factories)
            self.assertIsNot(shell.page_widgets["Quetes"], encyclopedia)
            self.assertEqual(shell.stack.indexOf(shell.page_widgets["Quetes"]), 1)

            # Reopening must queue the lazy canonical factory.
            AtlasWindow.open_encyclopedia_tab(shell, GUIDES_TAB)
            self.assertEqual(shell.pending_encyclopedia_tab, GUIDES_TAB)
            self.assertEqual(shell.pending_page_name, "Quetes")
            self.assertIs(shell.stack.currentWidget(), home)
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            self.assertFalse(isValid(encyclopedia))
        finally:
            shell.stack.close()
            shell.stack.deleteLater()
            app.processEvents()

    def test_failed_network_stop_cannot_leave_active_badge(self) -> None:
        from app.ui.network_bridge import NetworkUiBridge

        bridge = NetworkUiBridge()
        observed = []
        bridge.statusChanged.connect(observed.append)
        try:
            with patch.object(bridge.coordinator, "stop", return_value=False) as stop:
                self.assertFalse(bridge.stop())
                # A second shutdown (aboutToQuit) must not hide a failed stop.
                self.assertFalse(bridge.stop())
                stop.assert_called_once_with()
            self.assertFalse(bridge.last_status.running)
            self.assertEqual(bridge.last_status.reason, "stop_failed")
            self.assertEqual(len(observed), 1)
            self.assertEqual(observed[0].reason, "stop_failed")
        finally:
            bridge.deleteLater()

    def test_network_stop_exception_keeps_failed_status_and_no_second_stop(self) -> None:
        from app.ui.network_bridge import NetworkUiBridge

        bridge = NetworkUiBridge()
        observed = []
        bridge.statusChanged.connect(observed.append)
        try:
            with (
                patch.object(
                    bridge.coordinator, "stop",
                    side_effect=RuntimeError("coordinator cleanup failed"),
                ) as stop,
                patch("app.core.logger.get_runtime_logger") as get_logger,
            ):
                self.assertFalse(bridge.stop())
                self.assertFalse(bridge.stop())
                stop.assert_called_once_with()
                get_logger.return_value.exception.assert_called_once_with(
                    "Network coordinator shutdown failed."
                )
            self.assertFalse(bridge.last_status.running)
            self.assertEqual(bridge.last_status.reason, "stop_failed")
            self.assertEqual([status.reason for status in observed], ["stop_failed"])
        finally:
            bridge.deleteLater()

    def test_failed_network_stop_cannot_spawn_second_coordinator(self) -> None:
        QApplication.instance() or QApplication([])
        first = network_bridge_module.network_ui_bridge()
        try:
            with patch.object(first.coordinator, "stop", return_value=False) as stop:
                self.assertFalse(first.stop())
                with patch.object(network_bridge_module, "NetworkUiBridge") as factory:
                    # A possibly live capture worker must not be duplicated.
                    self.assertIs(network_bridge_module.network_ui_bridge(), first)
                    factory.assert_not_called()
                stop.assert_called_once_with()
            self.assertEqual(first.last_status.reason, "stop_failed")
        finally:
            # The fake failure does not execute real coordinator cleanup.
            first.coordinator.stop()

    def test_stopped_network_bridge_is_recreated(self) -> None:
        QApplication.instance() or QApplication([])
        first = network_bridge_module.network_ui_bridge()
        observed = []
        first.statusChanged.connect(observed.append)
        self.assertTrue(first.stop())
        self.assertEqual(first.last_status.reason, "stopped")
        self.assertFalse(first.last_status.running)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0].reason, "stopped")
        second = network_bridge_module.network_ui_bridge()
        self.assertIsNot(first, second)
        self.assertFalse(second._stopped)
        self.assertTrue(second.stop())


if __name__ == "__main__":
    unittest.main()
