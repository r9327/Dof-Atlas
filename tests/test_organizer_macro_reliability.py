from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.macros.auto_group import AutoGroupMacro
from app.macros.direction import DirectionMacro
from app.macros.zaap import ZaapMacro


def _runtime() -> Mock:
    runtime = Mock()
    runtime.settings.timings = Mock()
    runtime.macro_lock.should_stop.return_value = False
    runtime.switch_character.ordered_clients_from_source.return_value = [
        SimpleNamespace(handle=101), SimpleNamespace(handle=202),
    ]
    return runtime


class OrganizerMacroReliabilityTests(unittest.TestCase):
    def test_auto_group_restores_favorite_after_invitation_failure(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader"
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", return_value=101),
            patch("app.macros.auto_group.send_chat_command", side_effect=RuntimeError("chat failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "chat failed"):
                AutoGroupMacro(runtime)._run([{"name": "Friend", "handle": 202}])
        runtime.switch_character.restore_preferred_client.assert_called_once_with("Auto groupe")

    def test_auto_group_aborts_when_focus_is_stolen_between_invitations(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader"
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", side_effect=[101, 999]),
            patch("app.macros.auto_group.send_chat_command", return_value=True) as send,
        ):
            AutoGroupMacro(runtime)._run([
                {"name": "Friend1", "handle": 202},
                {"name": "Friend2", "handle": 303},
            ])
        send.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "interrompu", 1, 2, 2, 101,
        )

    def test_auto_group_reports_partial_delivery_without_false_success(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader"
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", return_value=101),
            patch("app.macros.auto_group.send_chat_command", side_effect=[True, False]) as send,
        ):
            AutoGroupMacro(runtime)._run([
                {"name": "Friend1", "handle": 202},
                {"name": "Friend2", "handle": 303},
            ])
        self.assertEqual(send.call_count, 2)
        runtime.switch_character.restore_preferred_client.assert_called_once_with("Auto groupe")
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "partiel", 1, 2, 2, 101,
        )

    def test_auto_group_never_restores_favorite_after_emergency_stop(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader"
        )
        stopped = False

        def should_stop() -> bool:
            return stopped

        def stop_during_invite(*_args, **_kwargs) -> bool:
            nonlocal stopped
            stopped = True
            return False

        runtime.macro_lock.should_stop.side_effect = should_stop
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", return_value=101),
            patch("app.macros.auto_group.send_chat_command", side_effect=stop_during_invite),
        ):
            AutoGroupMacro(runtime)._run([{"name": "Friend", "handle": 202}])
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "interrompu", 0, 1, 1, 101,
        )

    def test_auto_group_two_four_eight_targets_no_duplicates(self) -> None:
        for count in (2, 4, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.settings.timings.auto_group_invite_gap_ms = 0
                runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
                    handle=101, display_name="Leader"
                )
                targets = [
                    {"name": f"Friend{index}", "handle": 101 + index}
                    for index in range(1, count)
                ]
                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.activate_window", return_value=True),
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command", return_value=True) as send,
                ):
                    AutoGroupMacro(runtime)._run(targets)
                self.assertEqual(send.call_count, count - 1)
                self.assertEqual(
                    [call.args[0] for call in send.call_args_list],
                    [f"/invite Friend{index}" for index in range(1, count)],
                )
                runtime.logger.info.assert_any_call(
                    "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
                    "termine", count - 1, count - 1, count - 1, 101,
                )

    def test_invalid_zaap_does_not_start_or_reserve_macro(self) -> None:
        runtime = _runtime()
        self.assertFalse(ZaapMacro(runtime).run_async("/zaap fake"))
        self.assertFalse(ZaapMacro(runtime).run_async("/zaap 1,2 ; /travel 3,4"))
        runtime._spawn_macro.assert_not_called()

    def test_zaap_rejects_out_of_range_and_huge_coordinates(self) -> None:
        from app.macros.zaap import parse_zaap_command
        huge = "9" * 5000
        self.assertIsNone(parse_zaap_command("/zaap " + huge + ",1"))
        self.assertIsNone(parse_zaap_command("/zaap 2147483648,1"))
        self.assertIsNone(parse_zaap_command("/zaap -2147483648,1"))
        self.assertEqual(parse_zaap_command("/zaap -2147483647,2147483647"),
                         (-2147483647, 2147483647))
        runtime = _runtime()
        self.assertFalse(ZaapMacro(runtime).run_async("/zaap " + huge + ",1"))
        runtime._spawn_macro.assert_not_called()

    def test_valid_zaap_still_uses_existing_macro_runner(self) -> None:
        runtime = _runtime()
        runtime._spawn_macro.return_value = True
        self.assertTrue(ZaapMacro(runtime).run_async("/ZAAP -5,12"))
        self.assertEqual(runtime._spawn_macro.call_count, 1)
        self.assertEqual(runtime._spawn_macro.call_args.args[0], "Auto zaap")

    def test_zaap_restores_favorite_after_chat_failure(self) -> None:
        runtime = _runtime()
        with (
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.foreground_window", return_value=101),
            patch("app.macros.zaap.send_chat_command", side_effect=RuntimeError("chat failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "chat failed"):
                ZaapMacro(runtime)._run("/zaap 1,2")
        runtime.switch_character.restore_preferred_client.assert_called_once_with("Auto zaap")

    def test_zaap_never_refocuses_after_emergency_stop(self) -> None:
        runtime = _runtime()
        stopped = False

        def should_stop() -> bool:
            return stopped

        def stop_during_chat(*_args, **_kwargs) -> bool:
            nonlocal stopped
            stopped = True
            return False

        runtime.macro_lock.should_stop.side_effect = should_stop
        with (
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.foreground_window", return_value=101),
            patch("app.macros.zaap.send_chat_command", side_effect=stop_during_chat),
        ):
            ZaapMacro(runtime)._run("/zaap -5,12")
        runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_direction_restores_favorite_on_input_exception(self) -> None:
        runtime = _runtime()
        runtime.settings.client_by_handle.return_value = object()
        with (
            patch("app.macros.direction.foreground_window", return_value=101),
            patch("app.macros.direction.is_unity_window", return_value=True),
            patch("app.macros.direction.activate_window", return_value=True),
            patch("app.macros.direction.press_key", side_effect=RuntimeError("key failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "key failed"):
                DirectionMacro(runtime)._run("HOME")
        runtime.switch_character.restore_preferred_client.assert_called_once_with("Switch deplacement")

    def test_direction_skips_all_keys_if_focus_is_stolen(self) -> None:
        runtime = _runtime()
        runtime.settings.client_by_handle.return_value = object()
        with (
            patch("app.macros.direction.foreground_window", side_effect=[101, 999, 999]),
            patch("app.macros.direction.is_unity_window", return_value=True),
            patch("app.macros.direction.activate_window", return_value=True),
            patch("app.macros.direction.press_key") as press,
        ):
            DirectionMacro(runtime)._run("HOME")
        press.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_direction_does_not_restore_on_stop(self) -> None:
        runtime = _runtime()
        runtime.settings.client_by_handle.return_value = object()
        stopped = False

        def should_stop() -> bool:
            return stopped

        def stop_during_key(*_args, **_kwargs) -> None:
            nonlocal stopped
            stopped = True

        runtime.macro_lock.should_stop.side_effect = should_stop
        with (
            patch("app.macros.direction.foreground_window", return_value=101),
            patch("app.macros.direction.is_unity_window", return_value=True),
            patch("app.macros.direction.activate_window", return_value=True),
            patch("app.macros.direction.press_key", side_effect=stop_during_key),
        ):
            DirectionMacro(runtime)._run("HOME")
        runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_zaap_never_sends_chat_when_focus_was_stolen(self) -> None:
        runtime = _runtime()
        with (
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.foreground_window", return_value=999),
            patch("app.macros.zaap.send_chat_command") as send,
        ):
            ZaapMacro(runtime)._run("/zaap 1,2")
        send.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto zaap %s: envoyes=%s/%s", "interrompu", 0, 2
        )

    def test_zaap_partial_delivery_is_not_reported_complete(self) -> None:
        runtime = _runtime()
        with (
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.foreground_window", side_effect=[101, 202]),
            patch("app.macros.zaap.send_chat_command", side_effect=[True, False]),
        ):
            ZaapMacro(runtime)._run("/zaap 1,2")
        runtime.logger.info.assert_any_call("Auto zaap %s: envoyes=%s/%s", "partiel", 1, 2)


if __name__ == "__main__":
    unittest.main()
