from __future__ import annotations

import importlib.util
import os
import runpy
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.runtime_observation import RuntimeObserver


@unittest.skipUnless(importlib.util.find_spec("PySide6") and
                     os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                     "Needs opt-in offscreen PySide6 runtime (never starts a browser)")
class RealEquipmentScenarioTests(unittest.TestCase):
    def test_equipment_page_callback_lifecycle_is_real_qt(self):
        root = Path(__file__).resolve().parents[1]
        # Import Qt dependencies before tracing to focus the observed app scenario.
        from app.pages.equipment_page import EquipmentPage  # noqa: F401
        observer = RuntimeObserver(root, max_events=50000)
        with observer:
            runpy.run_module("tools.atlas_doctor_lib.app_ui_smoke_scenario",
                             run_name="__main__", alter_sys=True)
        events = observer.report()["events"]
        self.assertTrue(any(row.get("type") == "qt_destroyed_observed"
                            and row.get("label") == "equipment-page" for row in events))
        self.assertTrue(any(row.get("type") == "weak_watch_snapshot" for row in events))
        self.assertTrue(any(row.get("type") == "python_call_edge"
                            and row.get("target") == "app/pages/equipment_page.py"
                            for row in events))
        self.assertFalse(observer.report()["truncated"])


if __name__ == "__main__":
    unittest.main()
