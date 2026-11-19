from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.macros.travel import TravelMacro, normalize_guide_travel_command


class GuideTravelPreflightTests(unittest.TestCase):
    @staticmethod
    def _macro(*clients):
        runtime = SimpleNamespace(
            settings=SimpleNamespace(clients=list(clients)),
            logger=Mock(),
            _emit_status=Mock(),
            _spawn_macro=Mock(return_value=True),
        )
        return TravelMacro(runtime), runtime

    def test_offline_team_is_refused_before_spawning(self):
        macro, runtime = self._macro()
        self.assertFalse(macro.run_async("/travel 3,-6", ("character:1",)))
        runtime._spawn_macro.assert_not_called()
        runtime._emit_status.assert_called_once()
        self.assertIn("hors ligne", runtime._emit_status.call_args.args[0])

    def test_selected_connected_character_can_launch(self):
        client = SimpleNamespace(handle=123, character_key="character:1")
        macro, runtime = self._macro(client)
        with (
            patch("app.macros.travel.is_unity_window", return_value=True),
            patch("app.macros.travel.is_dofus_unity_process", return_value=True),
        ):
            self.assertTrue(macro.run_async("/travel 3,-6", ("character:1",)))
        runtime._spawn_macro.assert_called_once()

    def test_closed_dofus_window_is_refused_even_if_settings_still_list_it(self):
        client = SimpleNamespace(handle=123, character_key="character:1")
        macro, runtime = self._macro(client)
        with patch("app.macros.travel.is_unity_window", return_value=False):
            self.assertFalse(macro.run_async("/travel 3,-6", ("character:1",)))
        runtime._spawn_macro.assert_not_called()
        self.assertIn("aucune fenêtre", runtime._emit_status.call_args.args[0])

    def test_other_unity_game_never_receives_guide_travel(self):
        client = SimpleNamespace(handle=123, character_key="character:1")
        macro, runtime = self._macro(client)
        with (
            patch("app.macros.travel.is_unity_window", return_value=True),
            patch("app.macros.travel.is_dofus_unity_process", return_value=False),
        ):
            self.assertFalse(macro.run_async("/travel 3,-6", ("character:1",)))
        runtime._spawn_macro.assert_not_called()

    def test_invalid_coordinates_fail_without_throwing(self):
        for text in (
            "/travel 2147483648,3",
            "/travel -2147483648,3",
            "/travel " + "9" * 5000 + ",3",
            "/zaap 1,2 ; /travel 3,2147483648",
            "/zaap 1,-2147483648 ; /travel 3,4",
        ):
            with self.subTest(length=len(text)):
                self.assertIsNone(normalize_guide_travel_command(text))
        self.assertEqual(
            normalize_guide_travel_command("/zaap 01,02 ; /travel 003,-06"),
            "/zaap 1,2 ; /travel 3,-6",
        )

    @staticmethod
    def _running_macro(*clients):
        times = SimpleNamespace(
            travel_focus_settle_ms=0,
            activate_attempts=1, activate_retry_ms=0,
            auto_group_chat_open_ms=0,
            auto_group_key_step_ms=0,
            auto_group_paste_settle_ms=0,
        )
        settings = SimpleNamespace(
            clients=list(clients), primary_handle=clients[0].handle,
            macro_mode="mirror", timings=times,
        )
        restore = Mock()
        runtime = SimpleNamespace(
            settings=settings, logger=Mock(), _emit_status=Mock(),
            macro_lock=SimpleNamespace(should_stop=lambda: False),
            switch_character=SimpleNamespace(
                ordered_clients_from_source=lambda: list(clients),
                restore_preferred_client=restore,
            ),
        )
        return TravelMacro(runtime), runtime, restore

    def test_verified_multistep_zaap_travel_dispatches_chat_to_dofus(self):
        client = SimpleNamespace(handle=123, character_key="character:1")
        macro, runtime, restore = self._running_macro(client)
        with (
            patch("app.macros.travel.is_unity_window", return_value=True),
            patch("app.macros.travel.is_dofus_unity_process", return_value=True),
            patch("app.macros.travel.foreground_window", return_value=123),
            patch("app.macros.travel.activate_window", return_value=True),
            patch("app.macros.travel.send_chat_command", return_value=True) as send,
        ):
            macro._run(
                "/zaap 1,2 ; /travel 3,-6", ("character:1",),
                settings_at_dispatch=runtime.settings,
            )
        self.assertEqual(send.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in send.call_args_list],
            ["/zaap 1,2", "/travel 3,-6"],
        )
        restore.assert_called_once_with("Travel")
        self.assertIn("1/1", runtime._emit_status.call_args.args[0])

    def test_focus_stolen_after_zaap_never_sends_following_travel(self):
        client = SimpleNamespace(handle=123, character_key="character:1")
        macro, runtime, restore = self._running_macro(client)
        foreground = {"hwnd": 123}

        def send_once(_command, _logger, **_kwargs):
            foreground["hwnd"] = 999  # Browser steals focus after /zaap.
            return True

        with (
            patch("app.macros.travel.is_unity_window", return_value=True),
            patch("app.macros.travel.is_dofus_unity_process", return_value=True),
            patch("app.macros.travel.foreground_window", side_effect=lambda: foreground["hwnd"]),
            patch("app.macros.travel.activate_window", return_value=True),
            patch("app.macros.travel.send_chat_command", side_effect=send_once) as send,
        ):
            macro._run(
                "/zaap 1,2 ; /travel 3,-6", ("character:1",),
                settings_at_dispatch=runtime.settings,
            )
        send.assert_called_once()
        restore.assert_not_called()
        self.assertIn("0/1", runtime._emit_status.call_args.args[0])

    def test_profile_changed_between_clients_stops_broadcast(self):
        first = SimpleNamespace(handle=123, character_key="character:1")
        second = SimpleNamespace(handle=456, character_key="character:2")
        macro, runtime, restore = self._running_macro(first, second)

        def changed_profile(_command, _logger, **_kwargs):
            runtime.settings = SimpleNamespace(clients=[])
            return True

        with (
            patch("app.macros.travel.is_unity_window", return_value=True),
            patch("app.macros.travel.is_dofus_unity_process", return_value=True),
            patch("app.macros.travel.foreground_window", return_value=123),
            patch("app.macros.travel.activate_window", return_value=True) as activate,
            patch("app.macros.travel.send_chat_command", side_effect=changed_profile) as send,
        ):
            macro._run(
                "/travel 3,-6", ("character:1", "character:2"),
                settings_at_dispatch=runtime.settings,
            )
        send.assert_called_once()
        activate.assert_called_once()
        restore.assert_not_called()

    def test_invalid_command_never_reports_accepted_request(self):
        client = SimpleNamespace(handle=123, character_key="character:1")
        macro, runtime = self._macro(client)
        self.assertFalse(macro.run_async("/travel position inconnue", ("character:1",)))
        runtime._spawn_macro.assert_not_called()


if __name__ == "__main__":
    unittest.main()
