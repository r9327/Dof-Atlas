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

    def test_network_character_activation_ignores_bad_legacy_handle(self):
        from types import SimpleNamespace

        shell = Mock()
        shell._last_active_dofus_hwnd = 234
        shell.current_character_key = "character:7"
        shell.character_combo.count.return_value = 1
        shell.character_combo.itemText.return_value = "Witsis"
        shell.character_combo.currentData.return_value = SimpleNamespace(
            key="character:7",
        )
        clients = [
            {"handle": "invalid", "character_name": "Inconnu"},
            {"handle": "234", "character_name": "Witsis"},
        ]
        with patch("main.read_json", return_value={"clients": clients}):
            AtlasWindow.on_network_character_activated(shell, "character:7")

        shell.refresh_global_characters.assert_called_once_with()
        shell.character_combo.setCurrentIndex.assert_called_once_with(0)
        shell.on_global_character_changed.assert_not_called()

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
