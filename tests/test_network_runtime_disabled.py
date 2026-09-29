from __future__ import annotations

import sys
import unittest

from app.network.runtime_gate import (
    NETWORK_RUNTIME_DISABLED_REASON,
    NETWORK_RUNTIME_ENABLED,
)
from app.ui.network_bridge import NetworkRuntimeStatus, NetworkUiBridge


class NetworkRuntimeDisabledTests(unittest.TestCase):
    def test_network_runtime_is_hard_disabled_until_repair(self) -> None:
        self.assertFalse(NETWORK_RUNTIME_ENABLED)
        before = "app.network.application_coordinator" in sys.modules
        bridge = NetworkUiBridge()
        self.assertIsNone(bridge.coordinator)
        self.assertFalse(bridge._timer.isActive())
        self.assertFalse(bridge._progress_timer.isActive())
        self.assertFalse(bridge.last_status.running)
        self.assertFalse(bridge.last_status.calibrating)
        self.assertEqual(bridge.last_status.reason, NETWORK_RUNTIME_DISABLED_REASON)
        self.assertFalse(bridge.request_calibration())
        self.assertFalse(bridge.prepare_capture())
        self.assertFalse(bridge.request_verified_runtime())
        self.assertTrue(bridge.stop())
        if not before:
            self.assertNotIn("app.network.application_coordinator", sys.modules)

    def test_disabled_status_is_explicit(self) -> None:
        status = NetworkRuntimeStatus()
        self.assertEqual(status.reason, NETWORK_RUNTIME_DISABLED_REASON)


if __name__ == "__main__":
    unittest.main()
