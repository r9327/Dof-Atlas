from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.constants import KEY_SCRIPT_SPEED, KEY_SCRIPT_SPEED_SCHEMA
from app.core.macro_lock import MacroLock
from app.pages.organizer.organizer_hotkeys import OrganizerHotkeysMixin


class OrganizerSpeedAndLeaseTests(unittest.TestCase):
    def _owner(self, initial="normal"):
        events = []
        def on_stop():
            events.append("stop")
        def save(_profiles):
            events.append("save")
        def export():
            events.append("export")
        def reload():
            events.append("reload")
        owner = SimpleNamespace(
            profiles={KEY_SCRIPT_SPEED: initial, KEY_SCRIPT_SPEED_SCHEMA: 2},
            stop_runtime_callback=Mock(side_effect=on_stop),
            save_profiles=Mock(side_effect=save),
            export_client_index=Mock(side_effect=export),
            update_script_speed_buttons=Mock(),
            reload_runtime_callback=Mock(side_effect=reload),
            status_callback=Mock(),
        )
        return owner, events

    def test_changed_effective_speed_stops_before_writing_new_profile(self):
        for initial, changed in (
            ("classique", "normal"), ("normal", "rapide"),
            ("rapide", "instantane"), ("instantane", "classique"),
        ):
            with self.subTest(initial=initial, changed=changed):
                owner, events = self._owner(initial)
                OrganizerHotkeysMixin.set_script_speed(owner, changed)
                self.assertEqual(events, ["stop", "save", "export", "reload"])
                self.assertEqual(owner.profiles[KEY_SCRIPT_SPEED], changed)
                owner.stop_runtime_callback.assert_called_once()

    def test_reselecting_same_speed_does_not_interrupt_inflight_macro(self):
        for speed in ("classique", "normal", "rapide", "instantane"):
            with self.subTest(speed=speed):
                owner, events = self._owner(speed)
                OrganizerHotkeysMixin.set_script_speed(owner, speed)
                self.assertEqual(events, ["save", "export", "reload"])
                owner.stop_runtime_callback.assert_not_called()

    def test_legacy_speed_label_migration_does_not_stop_when_delays_equal(self):
        owner, events = self._owner("rapide")
        owner.profiles[KEY_SCRIPT_SPEED_SCHEMA] = 1
        OrganizerHotkeysMixin.set_script_speed(owner, "normal")
        self.assertEqual(events, ["save", "export", "reload"])
        self.assertEqual(owner.profiles[KEY_SCRIPT_SPEED_SCHEMA], 2)
        owner.stop_runtime_callback.assert_not_called()

    def test_wrong_owner_cannot_release_active_macro_lease(self):
        for current in ("Miroir clavier", "Miroir molette", "Auto zaap"):
            with self.subTest(current=current):
                logger = Mock()
                lease = MacroLock(logger)
                self.assertTrue(lease.try_begin(current))
                lease.end("stale worker")
                self.assertEqual(lease.active_label, current)
                self.assertFalse(lease.try_begin("Other macro"))
                lease.end(current)
                self.assertEqual(lease.active_label, "")
                self.assertTrue(lease.try_begin("Other macro"))
                lease.end("Other macro")
                logger.warning.assert_any_call(
                    "Macro fin refusée: owner=%s caller=%s", current,
                    "stale worker",
                )

    def test_stop_event_survives_matching_end_until_next_accepted_start(self):
        lease = MacroLock(Mock())
        self.assertTrue(lease.try_begin("Miroir"))
        lease.request_stop()
        self.assertTrue(lease.should_stop())
        lease.end("Other macro")
        self.assertTrue(lease.should_stop())
        self.assertEqual(lease.active_label, "Miroir")
        lease.end("Miroir")
        self.assertEqual(lease.active_label, "")
        self.assertTrue(lease.should_stop())
        self.assertTrue(lease.try_begin("Macro"))
        self.assertFalse(lease.should_stop())
        lease.end("Macro")


if __name__ == "__main__":
    unittest.main()
