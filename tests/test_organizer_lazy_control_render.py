from __future__ import annotations

import unittest
from unittest.mock import patch

from app.pages.organizer_lazy_page import OrganizerPage, _EagerOrganizerPage


class _ControlHarness:
    def __init__(self, *, visible: bool = False) -> None:
        self.visible = visible
        self._controls_render_dirty = False
        self._runtime_status_dirty = False
        self._runtime_status_value = False
        self._pending_shadow_frames = []
        self._sessions_render_dirty = False

    def isVisible(self) -> bool:
        return self.visible

    def _defer_control_refresh_if_hidden(self) -> bool:
        return OrganizerPage._defer_control_refresh_if_hidden(self)


class OrganizerLazyControlRenderTests(unittest.TestCase):
    def test_hidden_control_updates_coalesce_without_base_repolish(self) -> None:
        harness = _ControlHarness(visible=False)
        with (
            patch.object(_EagerOrganizerPage, "update_switch_buttons") as switches,
            patch.object(_EagerOrganizerPage, "update_global_buttons") as globals_,
            patch.object(_EagerOrganizerPage, "update_script_speed_buttons") as speed,
            patch.object(_EagerOrganizerPage, "update_debug_button") as debug,
            patch.object(_EagerOrganizerPage, "set_runtime_active") as runtime,
        ):
            OrganizerPage.update_switch_buttons(harness)
            OrganizerPage.update_global_buttons(harness)
            OrganizerPage.update_script_speed_buttons(harness)
            OrganizerPage.update_debug_button(harness)
            OrganizerPage.set_runtime_active(harness, True)

            switches.assert_not_called()
            globals_.assert_not_called()
            speed.assert_not_called()
            debug.assert_not_called()
            runtime.assert_not_called()
            self.assertTrue(harness._controls_render_dirty)
            self.assertTrue(harness._runtime_status_dirty)
            self.assertTrue(harness._runtime_status_value)

            harness.visible = True
            OrganizerPage._hydrate_hidden_visuals(harness)

            switches.assert_called_once_with(harness)
            globals_.assert_called_once_with(harness)
            speed.assert_called_once_with(harness)
            debug.assert_called_once_with(harness)
            runtime.assert_called_once_with(harness, True)
            self.assertFalse(harness._controls_render_dirty)
            self.assertFalse(harness._runtime_status_dirty)

            OrganizerPage._hydrate_hidden_visuals(harness)
            self.assertEqual(switches.call_count, 1)
            self.assertEqual(globals_.call_count, 1)
            self.assertEqual(speed.call_count, 1)
            self.assertEqual(debug.call_count, 1)
            self.assertEqual(runtime.call_count, 1)

    def test_visible_control_update_remains_immediate(self) -> None:
        harness = _ControlHarness(visible=True)
        harness._controls_render_dirty = True
        with patch.object(_EagerOrganizerPage, "update_debug_button") as debug:
            OrganizerPage.update_debug_button(harness)
        debug.assert_called_once_with(harness)
        self.assertFalse(harness._controls_render_dirty)

    def test_hidden_runtime_status_keeps_latest_value_only(self) -> None:
        harness = _ControlHarness(visible=False)
        with patch.object(_EagerOrganizerPage, "set_runtime_active") as runtime:
            OrganizerPage.set_runtime_active(harness, True)
            OrganizerPage.set_runtime_active(harness, False)
            OrganizerPage.set_runtime_active(harness, True)
            runtime.assert_not_called()
            self.assertTrue(harness._runtime_status_value)

            harness.visible = True
            OrganizerPage._hydrate_hidden_visuals(harness)
            runtime.assert_called_once_with(harness, True)


if __name__ == "__main__":
    unittest.main()
