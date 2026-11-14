from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app.core.settings as settings
from app.constants import KEY_SCRIPT_SPEED, KEY_SCRIPT_SPEED_SCHEMA


class OrganizerSpeedPresetsTests(unittest.TestCase):
    def test_legacy_names_keep_their_existing_effective_delays(self):
        self.assertEqual(settings.normalize_script_speed("normal", legacy=True), "classique")
        self.assertEqual(settings.normalize_script_speed("rapide", legacy=True), "normal")
        self.assertEqual(settings.normalize_script_speed("fast", legacy=True), "normal")
        self.assertEqual(settings.normalize_script_speed("classique", legacy=True), "classique")

    def test_v2_names_are_not_reinterpreted_as_legacy_names(self):
        for mode in ("classique", "normal", "rapide", "instantane"):
            self.assertEqual(settings.normalize_script_speed(mode), mode)
        self.assertEqual(settings.normalize_script_speed("Instantané"), "instantane")
        self.assertEqual(settings.normalize_script_speed("instant"), "instantane")

    def test_all_presets_keep_reliability_floors_and_speed_order(self):
        modes = ("classique", "normal", "rapide", "instantane")
        timings = [settings.timings_for_speed(mode) for mode in modes]
        for attr in (
            "click_focus_settle_ms", "travel_focus_settle_ms",
            "activate_retry_ms", "switch_background_pre_click_ms",
            "auto_group_chat_open_ms", "auto_group_key_step_ms",
            "auto_group_paste_settle_ms", "auto_group_invite_gap_ms",
            "movement_key_hold_ms",
        ):
            with self.subTest(attribute=attr):
                values = [getattr(timing, attr) for timing in timings]
                self.assertEqual(values, sorted(values, reverse=True))
                self.assertGreater(values[-1], 0)
        for timing in timings:
            self.assertGreaterEqual(timing.activate_attempts, 1)
            self.assertGreaterEqual(timing.input_click_down_ms, 1)
            self.assertGreaterEqual(timing.switch_click_down_ms, 1)

    def test_legacy_rapid_profile_maps_to_new_normal_even_without_ui(self):
        index = {"clients": [], "global_hotkeys": {"script_speed": "rapide"}}
        with (
            patch.object(settings, "read_json_file", return_value=index),
            patch.object(settings, "load_profile_payload",
                         return_value={KEY_SCRIPT_SPEED: "rapide"}),
            patch.object(settings, "read_zaap_button_ratios", return_value=None),
        ):
            loaded = settings.load_settings()
        self.assertEqual(loaded.script_speed, "normal")
        self.assertEqual(
            loaded.timings.switch_background_pre_click_ms, 18,
        )

    def test_new_instantane_export_schema_stays_instantane_when_loaded(self):
        index = {"clients": [], "global_hotkeys": {
            "script_speed": "instantane", "script_speed_schema": 2,
        }}
        with (
            patch.object(settings, "read_json_file", return_value=index),
            patch.object(settings, "load_profile_payload",
                         return_value={KEY_SCRIPT_SPEED: "rapide"}),
            patch.object(settings, "read_zaap_button_ratios", return_value=None),
        ):
            loaded = settings.load_settings()
        self.assertEqual(loaded.script_speed, "instantane")
        self.assertEqual(loaded.timings.auto_group_chat_open_ms, 45)

    def test_chat_cadence_is_identical_across_switch_presets(self):
        modes = ("classique", "normal", "rapide", "instantane")
        fields = (
            "auto_group_chat_open_ms", "auto_group_key_step_ms",
            "auto_group_paste_settle_ms", "auto_group_invite_gap_ms",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(
                    len({getattr(settings.timings_for_speed(mode), field) for mode in modes}),
                    1,
                )

    def test_zaap_and_auto_group_consume_all_three_actual_speed_presets_in_both_modes(self):
        from app.macros.auto_group import AutoGroupMacro
        from app.macros.zaap import ZaapMacro
        from tests.test_organizer_macro_reliability import _runtime

        for mode in ("macro", "mirror"):
            for speed in ("normal", "rapide", "instantane"):
                with self.subTest(mode=mode, speed=speed):
                    timing = settings.timings_for_speed(speed)
                    zaap = _runtime()
                    zaap.settings.macro_mode = mode
                    zaap.settings.timings = timing
                    zaap.switch_character.ordered_clients_from_source.return_value = [
                        SimpleNamespace(handle=101)
                    ]
                    with (
                        patch("app.macros.zaap.is_unity_window", return_value=True),
                        patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                        patch("app.macros.zaap.activate_window", return_value=True),
                        patch("app.macros.zaap.foreground_window", return_value=101),
                        patch("app.macros.zaap.send_chat_command", return_value=True) as send_zaap,
                    ):
                        ZaapMacro(zaap)._run("/zaap 1,2")
                    send_zaap.assert_called_once()
                    self.assertEqual(send_zaap.call_args.args[0], "/zaap 1,2")
                    for key, value in (
                        ("chat_open_ms", timing.auto_group_chat_open_ms),
                        ("key_step_ms", timing.auto_group_key_step_ms),
                        ("paste_settle_ms", timing.auto_group_paste_settle_ms),
                    ):
                        self.assertEqual(send_zaap.call_args.kwargs[key], value)
                    self.assertTrue(send_zaap.call_args.kwargs["submit_twice"])

                    group = _runtime()
                    group.settings.macro_mode = mode
                    group.settings.timings = timing
                    group.switch_character.logical_active_client.return_value = (
                        SimpleNamespace(handle=101, display_name="Leader")
                    )
                    with (
                        patch("app.macros.auto_group.is_unity_window", return_value=True),
                        patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
                        patch("app.macros.auto_group.activate_window", return_value=True),
                        patch("app.macros.auto_group.foreground_window", return_value=101),
                        patch("app.macros.auto_group.send_chat_command", return_value=True) as send_group,
                    ):
                        AutoGroupMacro(group)._run([{"name": "Friend", "handle": 202}])
                    send_group.assert_called_once()
                    self.assertEqual(send_group.call_args.args[0], "/invite Friend")
                    for key, value in (
                        ("chat_open_ms", timing.auto_group_chat_open_ms),
                        ("key_step_ms", timing.auto_group_key_step_ms),
                        ("paste_settle_ms", timing.auto_group_paste_settle_ms),
                    ):
                        self.assertEqual(send_group.call_args.kwargs[key], value)

    def test_organizer_switch_saves_schema_and_refreshes_once(self):
        from app.pages.organizer.organizer_hotkeys import OrganizerHotkeysMixin
        owner = SimpleNamespace(
            profiles={KEY_SCRIPT_SPEED: "rapide"},
            save_profiles=Mock(), export_client_index=Mock(),
            update_script_speed_buttons=Mock(), reload_runtime_callback=Mock(),
            status_callback=Mock(),
        )
        for mode in ("normal", "rapide", "instantane", "classique"):
            with self.subTest(mode=mode):
                OrganizerHotkeysMixin.set_script_speed(owner, mode)
                self.assertEqual(owner.profiles[KEY_SCRIPT_SPEED], mode)
                self.assertEqual(owner.profiles[KEY_SCRIPT_SPEED_SCHEMA], 2)
        self.assertEqual(owner.save_profiles.call_count, 4)
        self.assertEqual(owner.export_client_index.call_count, 4)
        self.assertEqual(owner.update_script_speed_buttons.call_count, 4)
        self.assertEqual(owner.reload_runtime_callback.call_count, 4)

    def test_organizer_legacy_display_matches_effective_speed(self):
        from app.pages.organizer.organizer_hotkeys import OrganizerHotkeysMixin
        owner = SimpleNamespace(profiles={KEY_SCRIPT_SPEED: "rapide"})
        self.assertEqual(OrganizerHotkeysMixin.script_speed(owner), "normal")
        owner.profiles[KEY_SCRIPT_SPEED] = "normal"
        self.assertEqual(OrganizerHotkeysMixin.script_speed(owner), "classique")
        owner.profiles[KEY_SCRIPT_SPEED_SCHEMA] = 2
        self.assertEqual(OrganizerHotkeysMixin.script_speed(owner), "normal")


if __name__ == "__main__":
    unittest.main()
