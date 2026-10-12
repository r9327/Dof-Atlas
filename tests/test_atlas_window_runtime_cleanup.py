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

    def test_stopped_network_bridge_is_recreated(self) -> None:
        QApplication.instance() or QApplication([])
        first = network_bridge_module.network_ui_bridge()
        self.assertTrue(first.stop())
        second = network_bridge_module.network_ui_bridge()
        self.assertIsNot(first, second)
        self.assertFalse(second._stopped)
        self.assertTrue(second.stop())


if __name__ == "__main__":
    unittest.main()
