from __future__ import annotations

import importlib.util
import os
import runpy
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.runtime_observation import RuntimeObserver


@unittest.skipUnless(importlib.util.find_spec("PySide6") and
                     os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                     "Needs opt-in offscreen Qt; no catalog or progress access")
class DeferredEncyclopediaSmokeTests(unittest.TestCase):
    def test_real_guide_success_widgets_keep_deferred_contract(self):
        # Import before profile activation so the trace focuses on the actual
        # deferred QWidget lifecycle rather than the Python module loader.
        from app.modules.encyclopedia.views.guides_view import GuidesView  # noqa: F401
        from app.modules.encyclopedia.views.achievements_view import AchievementsView  # noqa: F401
        root = Path(__file__).resolve().parents[1]
        observer = RuntimeObserver(root, max_events=50000)
        with observer:
            runpy.run_module("tools.atlas_doctor_lib.encyclopedia_deferred_smoke",
                             run_name="__main__", alter_sys=True)
        result = observer.report()
        self.assertFalse(result["truncated"])
        destroyed = {event.get("label") for event in result["events"]
                     if event.get("type") == "qt_destroyed_observed"}
        self.assertTrue({"guides-deferred", "success-deferred"}.issubset(destroyed))
        seen = {event.get("target") for event in result["events"]
                if event.get("type") == "python_call_edge"}
        self.assertIn("app/modules/encyclopedia/views/guides_view.py", seen)
        self.assertIn("app/modules/encyclopedia/views/achievements_view.py", seen)


if __name__ == "__main__":
    unittest.main()
