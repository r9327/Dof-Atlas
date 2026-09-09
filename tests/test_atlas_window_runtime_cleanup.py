from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

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
        runtime = window.runtime
        organizer = window.page_widgets["Organizer"]
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
