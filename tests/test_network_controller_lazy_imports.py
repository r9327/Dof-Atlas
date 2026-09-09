from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


class NetworkControllerLazyImportTests(unittest.TestCase):
    def test_application_coordinator_import_does_not_load_capture_bootstraps(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
from app.network.application_coordinator import NetworkApplicationCoordinator
print(json.dumps({
    "runtime_bootstrap": "app.network.bootstrap" in sys.modules,
    "calibration_bootstrap": "app.network.calibration_bootstrap" in sys.modules,
    "windows_capture": "app.network.windows_capture" in sys.modules,
    "network_runtime": "app.network.runtime" in sys.modules,
    "calibration_runtime": "app.network.calibration_runtime" in sys.modules,
}))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(
            payload,
            {
                "runtime_bootstrap": False,
                "calibration_bootstrap": False,
                "windows_capture": False,
                "network_runtime": False,
                "calibration_runtime": False,
            },
        )

    def test_controllers_do_not_import_bootstrap_when_started_without_context(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
from app.network.calibration_controller import ProtocolCalibrationController
from app.network.controller import NetworkRuntimeController
runtime = NetworkRuntimeController(lambda: ())
calibration = ProtocolCalibrationController(lambda: ())
runtime_status = runtime.start_if_ready()
calibration_status = calibration.start()
print(json.dumps({
    "runtime_reason": runtime_status.reason,
    "calibration_reason": calibration_status.reason,
    "runtime_bootstrap": "app.network.bootstrap" in sys.modules,
    "calibration_bootstrap": "app.network.calibration_bootstrap" in sys.modules,
    "windows_capture": "app.network.windows_capture" in sys.modules,
}))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["runtime_reason"], "waiting_context")
        self.assertEqual(payload["calibration_reason"], "waiting_context")
        self.assertFalse(payload["runtime_bootstrap"])
        self.assertFalse(payload["calibration_bootstrap"])
        self.assertFalse(payload["windows_capture"])


if __name__ == "__main__":
    unittest.main()
