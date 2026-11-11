from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.input.hotkeys import HotkeyRegistry, build_hotkey_actions
from app.input.input_state import InputState


class OrganizerStopHotkeyPriorityTests(unittest.TestCase):
    @staticmethod
    def _settings(**changes):
        defaults = dict(
            macro_mode="macro",
            switch_click_enabled=True,
            switch_click_hotkey="F12",
            switch_double_click_enabled=True,
            switch_double_click_hotkey="F12",
            stop_hotkey="F12",
            switch_character_enabled=True,
            next_character_hotkey="F12",
            clients=[SimpleNamespace(index=1, handle=101, binding="F12")],
            radial_enabled=False,
            radial_hotkey="",
            movement_enabled=False,
        )
        defaults.update(changes)
        return SimpleNamespace(**defaults)

    def test_emergency_stop_wins_stale_click_double_slot_and_next_conflicts(self):
        settings = self._settings()
        actions = build_hotkey_actions(settings)
        self.assertEqual(actions[0].action_id, "stop_script")
        state = InputState()
        callback = Mock()
        registry = HotkeyRegistry(state, Mock(), callback)
        report = registry.register_hotkeys(actions)
        self.assertEqual(
            [action.action_id for action in report.actions], ["stop_script"],
        )
        self.assertEqual(len(registry._stop_actions), 1)
        self.assertEqual(len(registry._switch_actions), 0)
        self.assertEqual(len(report.errors), 4)

        # F12 is 0x7B. Repeated held DOWN must invoke Stop only once.
        state.set_key(0x7B, True)
        self.assertTrue(registry._dispatch_priority_stop(0x7B, True))
        self.assertTrue(registry._dispatch_priority_stop(0x7B, True))
        callback.assert_called_once_with("stop_script", {})
        state.set_key(0x7B, False)
        self.assertFalse(registry._dispatch_priority_stop(0x7B, False))

    def test_stop_wins_direction_binding_with_existing_windows_key(self):
        settings = self._settings(
            switch_click_enabled=False,
            switch_click_hotkey="",
            switch_double_click_enabled=False,
            switch_double_click_hotkey="",
            switch_character_enabled=False,
            clients=[],
            stop_hotkey="HOME",
            movement_enabled=True,
        )
        registry = HotkeyRegistry(InputState(), Mock(), Mock())
        report = registry.register_hotkeys(build_hotkey_actions(settings))
        self.assertEqual(report.actions[0].action_id, "stop_script")
        self.assertNotIn("direction:HOME", [a.action_id for a in report.actions])
        self.assertIn("direction:DELETE", [a.action_id for a in report.actions])
        self.assertEqual(len(registry._stop_actions), 1)

    def test_nonconflicting_macro_bindings_remain_unchanged(self):
        settings = self._settings(
            switch_click_hotkey="F9",
            switch_double_click_hotkey="F10",
            next_character_hotkey="F11",
            clients=[SimpleNamespace(index=1, handle=101, binding="F8")],
        )
        registry = HotkeyRegistry(InputState(), Mock(), Mock())
        report = registry.register_hotkeys(build_hotkey_actions(settings))
        self.assertEqual(report.errors, ())
        self.assertEqual(
            {a.action_id for a in report.actions},
            {"stop_script", "switch_click", "switch_double_click",
             "next_character", "client:1"},
        )

    def test_mirror_mode_preserves_stop_and_navigation_but_not_classic_macros(self):
        settings = self._settings(macro_mode="mirror")
        actions = build_hotkey_actions(settings)
        self.assertEqual([a.action_id for a in actions], ["stop_script", "next_character"])
        registry = HotkeyRegistry(InputState(), Mock(), Mock())
        report = registry.register_hotkeys(actions)
        # A duplicate F12 binding still belongs exclusively to Stop urgence.
        self.assertEqual([a.action_id for a in report.actions], ["stop_script"])
        self.assertEqual(len(report.errors), 1)


if __name__ == "__main__":
    unittest.main()
