from __future__ import annotations

import inspect
import unittest

from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualView
from app.modules.encyclopedia.views.guide_ultime_generated_view import GuideUltimeGeneratedView


class _ReloadCountingService:
    def __init__(self) -> None:
        self.reload_calls = 0

    def reload_progress(self) -> None:
        self.reload_calls += 1


class _RefreshProbe:
    def __init__(self) -> None:
        self.service = _ReloadCountingService()
        self.refresh_calls: list[bool] = []

    def refresh(self, *, reset_to_active: bool = False) -> None:
        self.service.reload_progress()
        self.refresh_calls.append(bool(reset_to_active))


class GuideUltimeRefreshPerformanceTests(unittest.TestCase):
    def test_external_progress_refresh_uses_single_reload_owner(self):
        probe = _RefreshProbe()

        GuideUltimeGeneratedView.refresh_external_progress(probe)

        self.assertEqual(probe.refresh_calls, [False])
        self.assertEqual(probe.service.reload_calls, 1)

    def test_manual_render_does_not_force_global_qt_event_drain(self):
        source = inspect.getsource(GuideUltimeManualView._render_window)

        self.assertNotIn("processEvents", source)


if __name__ == "__main__":
    unittest.main()
