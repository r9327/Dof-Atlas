from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

import app.ui.network_bridge as real_bridge_module
from app.pages.lazy_network_bridge import LazyNetworkUiBridge


class _FakeBridge(QObject):
    statusChanged = Signal(object)
    progressChanged = Signal(str)
    characterActivated = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.last_status = object()
        self.configure_calls: list[dict[str, object]] = []
        self.prepare_calls = 0
        self.calibration_calls = 0
        self.runtime_calls = 0
        self.stop_calls = 0

    def configure_context(self, **kwargs) -> bool:
        self.configure_calls.append(dict(kwargs))
        return True

    def request_calibration(self) -> bool:
        self.calibration_calls += 1
        return True

    def prepare_capture(self) -> bool:
        self.prepare_calls += 1
        return True

    def request_verified_runtime(self) -> bool:
        self.runtime_calls += 1
        return True

    def stop(self) -> bool:
        self.stop_calls += 1
        return True


class LazyNetworkBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])

    def test_initial_status_does_not_construct_real_bridge(self) -> None:
        proxy = LazyNetworkUiBridge()
        try:
            with patch.object(real_bridge_module, "network_ui_bridge") as factory:
                self.assertFalse(proxy.is_hydrated)
                self.assertEqual(proxy.last_status.reason, "waiting_context")
                self.assertFalse(proxy.last_status.running)
                self.assertFalse(proxy.last_status.calibrating)
                factory.assert_not_called()
                self.assertTrue(proxy.stop())
                factory.assert_not_called()
        finally:
            proxy.deleteLater()
            self.app.processEvents()

    def test_configure_hydrates_once_and_forwards_context_and_signals(self) -> None:
        proxy = LazyNetworkUiBridge()
        fake = _FakeBridge()
        statuses: list[object] = []
        characters: list[str] = []
        activations: list[str] = []
        proxy.statusChanged.connect(statuses.append)
        proxy.progressChanged.connect(characters.append)
        proxy.characterActivated.connect(activations.append)
        catalog = object()
        achievements = object()
        guides = object()
        try:
            with patch.object(real_bridge_module, "network_ui_bridge", return_value=fake) as factory:
                self.assertTrue(
                    proxy.configure_context(
                        quest_catalog=catalog,
                        achievement_provider=achievements,
                        guide_provider=guides,
                    )
                )
                self.assertTrue(proxy.is_hydrated)
                self.assertIs(proxy.last_status, fake.last_status)
                self.assertEqual(factory.call_count, 1)
                self.assertEqual(
                    fake.configure_calls,
                    [
                        {
                            "quest_catalog": catalog,
                            "achievement_provider": achievements,
                            "guide_provider": guides,
                        }
                    ],
                )

                fake.statusChanged.emit("running")
                fake.progressChanged.emit("slot:2")
                fake.characterActivated.emit("slot:9")
                self.app.processEvents()
                self.assertEqual(statuses, ["running"])
                self.assertEqual(characters, ["slot:2"])
                self.assertEqual(activations, ["slot:9"])

                self.assertTrue(proxy.prepare_capture())
                self.assertTrue(proxy.request_calibration())
                self.assertTrue(proxy.request_verified_runtime())
                self.assertTrue(proxy.stop())
                self.assertEqual(factory.call_count, 1)
                self.assertEqual(fake.prepare_calls, 1)
                self.assertEqual(fake.calibration_calls, 1)
                self.assertEqual(fake.runtime_calls, 1)
                self.assertEqual(fake.stop_calls, 1)
        finally:
            proxy.deleteLater()
            fake.deleteLater()
            self.app.processEvents()

if __name__ == "__main__":
    unittest.main()
