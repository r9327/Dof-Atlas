from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.macros.auto_group import AutoGroupMacro
from app.macros.switch_character import SwitchCharacterMacro
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

    def test_roster_skips_corrupt_handles_and_keeps_valid_client_order(self) -> None:
        runtime = _runtime()
        valid = [
            SimpleNamespace(index=2, handle=202),
            SimpleNamespace(index=3, handle=303),
        ]
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=float("inf")),
            valid[0],
            SimpleNamespace(index=4, handle=None),
            valid[1],
        ]
        with patch("app.macros.switch_character.is_unity_window", return_value=True):
            ordered = SwitchCharacterMacro(runtime).ordered_clients_from_source(303)
        self.assertEqual([c.handle for c in ordered], [303, 202])
        self.assertEqual(runtime.logger.warning.call_count, 2)

    def test_roster_handles_overflowing_source_without_fanning_to_invalid_windows(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=101),
            SimpleNamespace(index=2, handle=202),
        ]
        macro = SwitchCharacterMacro(runtime)
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch.object(macro, "logical_active_client", return_value=runtime.settings.clients[1]),
        ):
            ordered = macro.ordered_clients_from_source(float("inf"))
        self.assertEqual([c.handle for c in ordered], [202, 101])


    def test_auto_group_overflowing_session_handles_do_not_abort_other_invites(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader",
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", return_value=101),
            patch("app.macros.auto_group.send_chat_command", return_value=True) as sender,
        ):
            AutoGroupMacro(runtime)._run([
                {"name": "Friend1", "handle": float("inf")},
                {"name": "Friend2", "handle": 303},
            ])
        self.assertEqual(
            [call.args[0] for call in sender.call_args_list],
            ["/invite Friend1", "/invite Friend2"],
        )
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "termine", 2, 2, 2, 101,
        )

    def test_auto_group_restores_favorite_after_invitation_failure(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader"
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", return_value=101),
            patch("app.macros.auto_group.send_chat_command", side_effect=RuntimeError("chat failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "chat failed"):
                AutoGroupMacro(runtime)._run([{"name": "Friend", "handle": 202}])
        runtime.switch_character.restore_preferred_client.assert_called_once_with("Auto groupe")

    def test_auto_group_does_not_steal_focus_after_last_invite_on_2_4_6_8(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.settings.timings.auto_group_invite_gap_ms = 0
                runtime.switch_character.logical_active_client.return_value = (
                    SimpleNamespace(handle=101, display_name="Leader")
                )
                active = [101]
                entries = [
                    {"name": f"Friend{index}", "handle": 101 + index}
                    for index in range(1, count)
                ]
                completed = [0]

                def send(*_args, **_kwargs):
                    completed[0] += 1
                    if completed[0] == count - 1:
                        active[0] = 999
                    return True

                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
                    patch("app.macros.auto_group.activate_window", return_value=True),
                    patch("app.macros.auto_group.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.auto_group.send_chat_command",
                          side_effect=send) as chat,
                ):
                    AutoGroupMacro(runtime)._run(entries)
                self.assertEqual(chat.call_count, count - 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Auto groupe: retour favori ignoré, focus utilisateur changé."
                )
                runtime.logger.info.assert_any_call(
                    "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
                    "interrompu", count - 1, count - 1, count - 1, 101,
                )

    def test_auto_group_cleanup_failure_to_read_foreground_never_refocuses(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = (
            SimpleNamespace(handle=101, display_name="Leader")
        )
        checks = [0]

        def foreground():
            checks[0] += 1
            if checks[0] > 1:
                raise OSError("GetForegroundWindow refused")
            return 101

        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", side_effect=foreground),
            patch("app.macros.auto_group.send_chat_command",
                  return_value=True) as chat,
        ):
            AutoGroupMacro(runtime)._run([{"name": "Friend", "handle": 202}])
        chat.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.exception.assert_any_call(
            "Auto groupe: focus illisible avant retour au favori."
        )

    def test_auto_group_never_restores_favorite_changed_after_last_invite(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.settings.primary_handle = 101
                runtime.settings.timings.auto_group_invite_gap_ms = 0
                runtime.switch_character.logical_active_client.return_value = (
                    SimpleNamespace(handle=101, display_name="Leader")
                )
                entries = [
                    {"name": f"Friend{index}", "handle": 101 + index}
                    for index in range(1, count)
                ]
                sent = [0]

                def chat(*_args, **_kwargs):
                    sent[0] += 1
                    if sent[0] == count - 1:
                        runtime.settings.primary_handle = 101 + count
                    return True

                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
                    patch("app.macros.auto_group.activate_window", return_value=True),
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command",
                          side_effect=chat) as sender,
                ):
                    AutoGroupMacro(runtime)._run(entries)
                self.assertEqual(sender.call_count, count - 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Auto groupe: retour favori ignoré, favori changé."
                )

    def test_auto_group_aborts_when_focus_is_stolen_between_invitations(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader"
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
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
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
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
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
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
        for count in (2, 4, 6, 8):
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
                    patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
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

    def test_auto_group_reports_no_eligible_recipient(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader"
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.send_chat_command") as sender,
        ):
            AutoGroupMacro(runtime)._run([{"name": "Leader", "handle": 101}])
        sender.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "ignore", 0, 0, 1, 101,
        )

    def test_auto_group_counts_sent_invite_when_stop_arrives_after_send(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader"
        )
        stopped = False

        def stop_after_send(*_args, **_kwargs) -> bool:
            nonlocal stopped
            stopped = True
            return True

        runtime.macro_lock.should_stop.side_effect = lambda: stopped
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", return_value=101),
            patch("app.macros.auto_group.send_chat_command",
                  side_effect=stop_after_send),
        ):
            AutoGroupMacro(runtime)._run([{"name": "Friend", "handle": 202}])
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "interrompu", 1, 1, 1, 101,
        )

    def test_auto_group_mid_command_focus_loss_cancels_remaining_invites(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = (
            SimpleNamespace(handle=101, display_name="Leader")
        )
        focus = [101]

        def fake_chat(_command, _logger, **kwargs):
            self.assertFalse(kwargs["should_stop"]())
            focus[0] = 999
            self.assertTrue(kwargs["should_stop"]())
            return False

        with (
            patch("app.macros.auto_group.foreground_window",
                  side_effect=lambda: focus[0]),
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.send_chat_command",
                  side_effect=fake_chat) as send,
        ):
            AutoGroupMacro(runtime)._run([
                {"name": "Friend1", "handle": 202},
                {"name": "Friend2", "handle": 303},
            ])
        send.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "interrompu", 0, 1, 2, 101,
        )

    def test_zaap_no_focus_steal_after_last_chat_on_2_4_6_8_clients(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=101 + index)
                    for index in range(count)
                ]
                active = [101]
                sent = [0]

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def send(*_args, **_kwargs):
                    sent[0] += 1
                    if sent[0] == count:
                        active[0] = 999
                    return True

                with (
                    patch("app.macros.zaap.is_unity_window", return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                    patch("app.macros.zaap.activate_window", side_effect=activate),
                    patch("app.macros.zaap.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.zaap.send_chat_command",
                          side_effect=send) as chat,
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                self.assertEqual(chat.call_count, count)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Auto zaap: retour favori ignoré, focus utilisateur changé."
                )
                runtime.logger.info.assert_any_call(
                    "Auto zaap %s: envoyes=%s/%s", "interrompu", count, count,
                )

    def test_zaap_cleanup_foreground_error_never_forces_favorite(self) -> None:
        runtime = _runtime()
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101),
        ]
        active = [101]
        calls = [0]

        def foreground():
            calls[0] += 1
            if calls[0] > 1:
                raise OSError("GetForegroundWindow failed")
            return active[0]

        with (
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.foreground_window", side_effect=foreground),
            patch("app.macros.zaap.send_chat_command",
                  return_value=True) as chat,
        ):
            ZaapMacro(runtime)._run("/zaap 1,2")
        chat.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.exception.assert_any_call(
            "Auto zaap: focus illisible avant retour au favori."
        )

    def test_zaap_does_not_restore_new_favorite_selected_mid_broadcast(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.settings.primary_handle = 101
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=101 + index)
                    for index in range(count)
                ]
                active = [101]
                sent = [0]

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def chat(*_args, **_kwargs):
                    sent[0] += 1
                    if sent[0] == count:
                        runtime.settings.primary_handle = 999
                    return True

                with (
                    patch("app.macros.zaap.is_unity_window", return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                    patch("app.macros.zaap.activate_window", side_effect=activate),
                    patch("app.macros.zaap.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.zaap.send_chat_command",
                          side_effect=chat) as send,
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                self.assertEqual(send.call_count, count)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Auto zaap: retour favori ignoré, favori changé."
                )

    def test_zaap_mid_command_focus_loss_aborts_following_clients(self) -> None:
        runtime = _runtime()
        focus = [101]

        def fake_chat(_command, _logger, **kwargs):
            self.assertFalse(kwargs["should_stop"]())
            focus[0] = 999
            self.assertTrue(kwargs["should_stop"]())
            return False

        with (
            patch("app.macros.zaap.foreground_window",
                  side_effect=lambda: focus[0]),
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.send_chat_command",
                  side_effect=fake_chat) as send,
        ):
            ZaapMacro(runtime)._run("/zaap 1,2")
        send.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto zaap %s: envoyes=%s/%s", "interrompu", 0, 2,
        )

    def test_direction_with_no_clients_reports_ignored(self) -> None:
        runtime = _runtime()
        runtime.settings.client_by_handle.return_value = object()
        runtime.switch_character.ordered_clients_from_source.return_value = []
        with (
            patch("app.macros.direction.foreground_window", return_value=101),
            patch("app.macros.direction.is_unity_window", return_value=True),
            patch("app.macros.direction.is_dofus_unity_process", return_value=True),
            patch("app.macros.direction.press_key") as press,
        ):
            DirectionMacro(runtime)._run("HOME")
        press.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Switch deplacement %s: envoyes=%s/%s", "ignore", 0, 0,
        )

    def test_direction_counts_completed_key_before_stop(self) -> None:
        runtime = _runtime()
        runtime.settings.client_by_handle.return_value = object()
        stopped = False

        def stop_after_key(*_args, **_kwargs):
            nonlocal stopped
            stopped = True

        runtime.macro_lock.should_stop.side_effect = lambda: stopped
        with (
            patch("app.macros.direction.foreground_window", return_value=101),
            patch("app.macros.direction.is_unity_window", return_value=True),
            patch("app.macros.direction.is_dofus_unity_process", return_value=True),
            patch("app.macros.direction.activate_window", return_value=True),
            patch("app.macros.direction.press_key", side_effect=stop_after_key) as press,
        ):
            DirectionMacro(runtime)._run("HOME")
        press.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Switch deplacement %s: envoyes=%s/%s",
            "interrompu", 1, 2,
        )

    def test_auto_group_skips_duplicate_sessions_and_sender(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader"
        )
        entries = [
            {"name": "Leader", "handle": 101},
            {"name": "Friend1", "handle": 202},
            {"name": "Friend1", "handle": 202},
            {"name": "Friend2", "handle": 303},
            {"name": "", "handle": 404},
        ]
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", return_value=101),
            patch("app.macros.auto_group.send_chat_command", return_value=True) as sender,
        ):
            AutoGroupMacro(runtime)._run(entries)
        self.assertEqual(
            [call.args[0] for call in sender.call_args_list],
            ["/invite Friend1", "/invite Friend2"],
        )
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "termine", 2, 2, len(entries), 101,
        )

    def test_switch_character_confirms_foreground_before_reporting_success(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=0, handle=101, display_name="Leader"),
            SimpleNamespace(index=1, handle=202, display_name="Friend"),
        ]
        runtime.active_client_handle = 101
        runtime._spawn_macro.return_value = True
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window", return_value=202),
        ):
            self.assertTrue(SwitchCharacterMacro(runtime).activate_by_index(1))
            runtime._spawn_macro.call_args.args[1]()
        self.assertEqual(runtime.active_client_handle, 202)

    def test_switch_character_rejects_stolen_focus_without_false_success(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=0, handle=101, display_name="Leader"),
            SimpleNamespace(index=1, handle=202, display_name="Friend"),
        ]
        runtime.active_client_handle = 101
        runtime._spawn_macro.return_value = True
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window", return_value=999),
        ):
            self.assertTrue(SwitchCharacterMacro(runtime).activate_by_index(1))
            runtime._spawn_macro.call_args.args[1]()
        self.assertEqual(runtime.active_client_handle, 101)
        runtime.logger.warning.assert_any_call(
            "Activation client ignoree: focus non confirme hwnd=%s", 202,
        )
        self.assertFalse(
            any(
                "Activation par raccourci client" in str(call.args[0])
                for call in runtime.logger.info.call_args_list
            )
        )

    def test_switch_character_does_not_mark_success_after_emergency_stop(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=202, display_name="Friend"),
        ]
        runtime.active_client_handle = 101
        runtime.macro_lock.should_stop.return_value = True
        runtime._spawn_macro.return_value = True
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window") as foreground,
        ):
            self.assertTrue(SwitchCharacterMacro(runtime).activate_by_index(1))
            runtime._spawn_macro.call_args.args[1]()
        foreground.assert_not_called()
        self.assertEqual(runtime.active_client_handle, 101)

    def test_switch_click_preserves_native_down_up_on_source(self) -> None:
        from app.core.runtime_state import AtlasRuntime
        from app.macros.switch_click import SwitchClickContext

        runtime = _runtime()
        runtime._running = True
        runtime._admin_ok = True
        runtime.macro_lock.active_label = ""
        runtime.settings.macro_mode = "macro"
        runtime.settings.clients = [
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        ]
        runtime.registry.switch_action_for_pressed_keys.return_value = SimpleNamespace(
            action_id="switch_click",
            payload={"click_count": 1, "label": "Switch clique"},
        )
        context = SwitchClickContext(101, 25, 30, 0.2, 0.3, "cursor")
        runtime.switch_click._capture_trigger_context.return_value = context
        with (
            patch("app.windows.unity_windows.find_known_client_from_point", return_value=101),
            patch("app.windows.unity_windows.foreground_window", return_value=101),
            patch("app.macros.mirror_plan.is_dofus_unity_process", return_value=True),
        ):
            self.assertFalse(AtlasRuntime._handle_mouse_click(runtime, "Left", 150, 160))
            runtime.switch_click.run_async.assert_not_called()
            self.assertTrue(AtlasRuntime._handle_mouse_release(runtime, "Left", 150, 160))
        runtime.switch_click.run_async.assert_called_once_with(
            "Left", 150, 160, 1, "Switch clique",
            captured_context=context, physical_source_delivered=True,
        )
        self.assertIsNone(runtime._pending_physical_switch)

    def test_busy_switch_does_not_consume_foreign_application_click(self) -> None:
        from app.core.runtime_state import AtlasRuntime

        runtime = _runtime()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings.macro_mode = "macro"
        runtime.settings.clients = [
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        ]
        runtime.macro_lock.active_label = "Switch clique"
        runtime.registry.switch_action_for_pressed_keys.return_value = (
            SimpleNamespace(action_id="switch_click", payload={"click_count": 1})
        )
        with (
            patch("app.windows.unity_windows.foreground_window",
                  return_value=999),
            patch("app.windows.unity_windows.find_known_client_from_point") as point,
            patch("app.macros.mirror_plan.is_dofus_unity_process") as probe,
        ):
            self.assertFalse(
                AtlasRuntime._handle_mouse_click(runtime, "Left", 40, 60)
            )
        point.assert_not_called()
        probe.assert_not_called()
        runtime.switch_click.run_async.assert_not_called()

    def test_busy_switch_refuses_wrong_window_under_pointer(self) -> None:
        from app.core.runtime_state import AtlasRuntime

        runtime = _runtime()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings.macro_mode = "macro"
        runtime.settings.clients = [
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        ]
        runtime.macro_lock.active_label = "Switch clique"
        runtime.registry.switch_action_for_pressed_keys.return_value = (
            SimpleNamespace(action_id="switch_click", payload={"click_count": 1})
        )
        with (
            patch("app.windows.unity_windows.foreground_window", return_value=101),
            patch("app.windows.unity_windows.find_known_client_from_point",
                  return_value=888),
            patch("app.macros.mirror_plan.is_dofus_unity_process") as probe,
        ):
            self.assertFalse(
                AtlasRuntime._handle_mouse_click(runtime, "Right", 40, 60)
            )
        probe.assert_not_called()
        runtime.switch_click.run_async.assert_not_called()

    def test_busy_switch_consumes_only_trusted_focused_game_window(self) -> None:
        from app.core.runtime_state import AtlasRuntime

        for trusted in (True, False):
            with self.subTest(trusted=trusted):
                runtime = _runtime()
                runtime._running = True
                runtime._admin_ok = True
                runtime.settings.macro_mode = "macro"
                runtime.settings.clients = [
                    SimpleNamespace(handle=101), SimpleNamespace(handle=202),
                ]
                runtime.macro_lock.active_label = "Switch clique"
                runtime.registry.switch_action_for_pressed_keys.return_value = (
                    SimpleNamespace(
                        action_id="switch_click", payload={"click_count": 1},
                    )
                )
                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=101),
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          return_value=101),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=trusted),
                ):
                    self.assertEqual(
                        AtlasRuntime._handle_mouse_click(
                            runtime, "Left", 40, 60,
                        ),
                        trusted,
                    )
                runtime.switch_click.run_async.assert_not_called()
                if trusted:
                    runtime.logger.debug.assert_any_call(
                        "Clic switch consomme: macro deja active=%s button=%s x=%s y=%s",
                        "Switch clique", "Left", 40, 60,
                    )

    def test_native_overlapping_downs_cancel_replay_without_swallowing_either(self) -> None:
        from app.core.runtime_state import AtlasRuntime
        from app.macros.switch_click import SwitchClickContext

        for second_button in ("Left", "Right"):
            with self.subTest(second_button=second_button):
                runtime = _runtime()
                runtime._running = True
                runtime._admin_ok = True
                runtime.settings.macro_mode = "macro"
                runtime.macro_lock.active_label = ""
                runtime.settings.clients = [
                    SimpleNamespace(handle=101), SimpleNamespace(handle=202),
                ]
                runtime.registry.switch_action_for_pressed_keys.return_value = SimpleNamespace(
                    action_id="switch_click",
                    payload={"click_count": 1, "label": "Switch clique"},
                )
                context = SwitchClickContext(101, 25, 30, 0.2, 0.3, "cursor")
                runtime.switch_click._capture_trigger_context.return_value = context
                with (
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          return_value=101),
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=101),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=True),
                ):
                    # The first DOWN passes naturally to the favorite.
                    self.assertFalse(
                        AtlasRuntime._handle_mouse_click(runtime, "Left", 150, 160)
                    )
                    self.assertIsInstance(runtime._pending_physical_switch, tuple)
                    # Another DOWN cannot overwrite the owner of the
                    # first physical click's future UP.
                    self.assertFalse(
                        AtlasRuntime._handle_mouse_click(
                            runtime, second_button, 152, 160,
                        )
                    )
                    self.assertIsNone(runtime._pending_physical_switch)
                    self.assertFalse(
                        AtlasRuntime._handle_mouse_release(runtime, "Left", 150, 160)
                    )
                    self.assertFalse(
                        AtlasRuntime._handle_mouse_release(
                            runtime, second_button, 152, 160,
                        )
                    )
                runtime.switch_click.run_async.assert_not_called()
                runtime.logger.debug.assert_any_call(
                    "Clic natif non recopié: cause=overlapping_down button=%s",
                    second_button,
                )

    def test_native_source_release_without_valid_pending_state_passes_through(self) -> None:
        from app.core.runtime_state import AtlasRuntime

        runtime = _runtime()
        for pending in (None, "invalid", (), ("Left",)):
            with self.subTest(pending=pending):
                runtime._pending_physical_switch = pending
                self.assertFalse(
                    AtlasRuntime._handle_mouse_release(runtime, "Left", 150, 160)
                )
        runtime.switch_click.run_async.assert_not_called()

    def test_double_click_remains_existing_synthetic_sequence(self) -> None:
        from app.core.runtime_state import AtlasRuntime

        runtime = _runtime()
        runtime._running = True
        runtime._admin_ok = True
        runtime.macro_lock.active_label = ""
        runtime.settings.macro_mode = "macro"
        runtime.registry.switch_action_for_pressed_keys.return_value = SimpleNamespace(
            action_id="double_click",
            payload={"click_count": 2, "label": "Switch double clic"},
        )
        runtime.switch_click.run_async.return_value = True
        self.assertTrue(
            AtlasRuntime._handle_mouse_click(runtime, "Left", 150, 160)
        )
        runtime.switch_click.run_async.assert_called_once_with(
            "Left", 150, 160, 2, "Switch double clic",
        )
        # Never start a separate native-source UP replay for double-click.
        self.assertFalse(
            AtlasRuntime._handle_mouse_release(runtime, "Left", 150, 160)
        )

    def test_native_source_drag_is_not_replayed(self) -> None:
        from time import monotonic
        from app.core.runtime_state import AtlasRuntime
        from app.macros.switch_click import SwitchClickContext

        runtime = _runtime()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings.macro_mode = "macro"
        runtime.macro_lock.active_label = ""
        runtime._pending_physical_switch = (
            "Left", 20, 40, 1, "Switch clique",
            SwitchClickContext(101, 12, 18, 0.5, 0.5, "cursor"),
            monotonic(),
        )
        with (
            patch("app.windows.unity_windows.foreground_window", return_value=101),
            patch("app.macros.mirror_plan.is_dofus_unity_process", return_value=True),
        ):
            self.assertTrue(AtlasRuntime._handle_mouse_release(runtime, "Left", 130, 180))
        self.assertIsNone(runtime._pending_physical_switch)
        runtime.switch_click.run_async.assert_not_called()

    def test_native_source_stop_or_stale_click_never_replays(self) -> None:
        from time import monotonic
        from app.core.runtime_state import AtlasRuntime
        from app.macros.switch_click import SwitchClickContext

        for stopped, age in ((True, 0), (False, 5)):
            with self.subTest(stopped=stopped, age=age):
                runtime = _runtime()
                runtime._running = True
                runtime._admin_ok = True
                runtime.settings.macro_mode = "macro"
                runtime.macro_lock.active_label = ""
                runtime.macro_lock.should_stop.return_value = stopped
                runtime._pending_physical_switch = (
                    "Left", 20, 40, 1, "Switch clique",
                    SwitchClickContext(101, 12, 18, 0.5, 0.5, "cursor"),
                    monotonic() - age,
                )
                with patch("app.windows.unity_windows.foreground_window", return_value=101):
                    self.assertTrue(AtlasRuntime._handle_mouse_release(runtime, "Left", 20, 40))
                runtime.switch_click.run_async.assert_not_called()

    def test_native_source_replay_refusal_is_visible_but_up_passes_through(self) -> None:
        from time import monotonic
        from app.core.runtime_state import AtlasRuntime
        from app.macros.switch_click import SwitchClickContext

        runtime = _runtime()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings.macro_mode = "macro"
        runtime.macro_lock.active_label = ""
        runtime.switch_click.run_async.return_value = False
        context = SwitchClickContext(101, 12, 18, 0.5, 0.5, "cursor")
        runtime._pending_physical_switch = (
            "Left", 20, 40, 1, "Switch clique", context, monotonic(),
        )
        with (
            patch("app.windows.unity_windows.foreground_window", return_value=101),
            patch("app.macros.mirror_plan.is_dofus_unity_process", return_value=True),
        ):
            self.assertTrue(AtlasRuntime._handle_mouse_release(runtime, "Left", 20, 40))
        runtime.logger.warning.assert_any_call(
            "Clic natif non recopié: cause=dispatch_refused button=%s", "Left",
        )
        self.assertIsNone(runtime._pending_physical_switch)

    def test_native_source_skipped_replays_have_distinct_safe_reasons(self) -> None:
        from time import monotonic
        from app.core.runtime_state import AtlasRuntime
        from app.macros.switch_click import SwitchClickContext

        for reason in (
            "emergency_stop", "worker_busy", "expired",
            "drag_or_moved", "focus_changed", "source_untrusted",
            "mode_changed",
        ):
            with self.subTest(reason=reason):
                runtime = _runtime()
                runtime._running = True
                runtime._admin_ok = True
                runtime.settings.macro_mode = (
                    "mirror" if reason == "mode_changed" else "macro"
                )
                runtime.macro_lock.active_label = (
                    "Miroir" if reason == "worker_busy" else ""
                )
                runtime.macro_lock.should_stop.return_value = (
                    reason == "emergency_stop"
                )
                captured = monotonic() - (5 if reason == "expired" else 0)
                runtime._pending_physical_switch = (
                    "Left", 20, 40, 1, "Switch clique",
                    SwitchClickContext(101, 12, 18, 0.5, 0.5, "cursor"),
                    captured,
                )
                x, y = (150, 180) if reason == "drag_or_moved" else (20, 40)
                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=999 if reason == "focus_changed" else 101),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=reason != "source_untrusted"),
                ):
                    self.assertTrue(
                        AtlasRuntime._handle_mouse_release(runtime, "Left", x, y)
                    )
                runtime.switch_click.run_async.assert_not_called()
                runtime.logger.debug.assert_any_call(
                    "Clic natif non recopié: cause=%s button=%s",
                    reason, "Left",
                )
                self.assertIsNone(runtime._pending_physical_switch)

    def test_native_source_click_skips_source_in_secondary_replay(self) -> None:
        from app.macros.switch_click import SwitchClickContext, SwitchClickMacro

        runtime = _runtime()
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101, display_name="source"),
            SimpleNamespace(handle=202, display_name="target"),
        ]
        timings = runtime.settings.timings
        timings.switch_background_pre_click_ms = 18
        timings.switch_click_down_ms = 1
        timings.input_double_gap_ms = 5
        timings.switch_background_post_up_ms = 0
        timings.switch_client_settle_ms = 0
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        macro = SwitchClickMacro(runtime)
        context = SwitchClickContext(101, 32, 24, 0.5, 0.5, "cursor")

        with (
            patch.object(macro, "_validated_context", return_value=context),
            patch.object(macro, "_target_point", return_value=(32, 24)),
            patch("app.macros.switch_click.current_cursor_pos", return_value=(150, 170)),
            patch("app.macros.switch_click.set_cursor_pos"),
            patch("app.macros.switch_click.is_unity_window", return_value=True),
            patch("app.macros.switch_click.activate_window", return_value=True),
            patch("app.macros.switch_click.foreground_window", return_value=202),
            patch("app.macros.switch_click.send_client_click", return_value=True) as send,
        ):
            macro._run(
                "Left", 1, "Switch clique", context,
                mouse_block_started=True, physical_source_delivered=True,
            )
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], 202)
        self.assertGreaterEqual(send.call_args.args[5], 35)
        self.assertGreaterEqual(send.call_args.args[7], 50)
        runtime.macro_lock.wait.assert_called_once_with(60)

    def test_native_single_client_bypasses_worker_and_mouse_block(self) -> None:
        from app.macros.switch_click import SwitchClickContext, SwitchClickMacro

        runtime = _runtime()
        runtime.settings.clients = [SimpleNamespace(handle=101)]
        context = SwitchClickContext(101, 32, 24, 0.5, 0.5, "cursor")
        self.assertTrue(SwitchClickMacro(runtime).run_async(
            "Left", 100, 200, 1, "Switch clique",
            captured_context=context, physical_source_delivered=True,
        ))
        runtime._spawn_macro.assert_not_called()
        runtime.input_state.begin_mouse_block.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_native_two_client_click_still_uses_single_macro_worker(self) -> None:
        from app.macros.switch_click import SwitchClickContext, SwitchClickMacro

        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        ]
        runtime._spawn_macro.return_value = True
        context = SwitchClickContext(101, 32, 24, 0.5, 0.5, "cursor")
        self.assertTrue(SwitchClickMacro(runtime).run_async(
            "Left", 100, 200, 1, "Switch clique",
            captured_context=context, physical_source_delivered=True,
        ))
        runtime._spawn_macro.assert_called_once()
        runtime.input_state.begin_mouse_block.assert_called_once_with("Switch clique")

    def test_single_client_native_click_never_reinjects_or_steals_focus(self) -> None:
        from app.macros.switch_click import SwitchClickContext, SwitchClickMacro

        runtime = _runtime()
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101, display_name="source"),
        ]
        runtime.macro_lock.should_stop.return_value = False
        macro = SwitchClickMacro(runtime)
        context = SwitchClickContext(101, 32, 24, 0.5, 0.5, "cursor")
        with (
            patch.object(macro, "_validated_context", return_value=context),
            patch("app.macros.switch_click.current_cursor_pos", return_value=(1, 2)),
            patch("app.macros.switch_click.set_cursor_pos") as move,
            patch("app.macros.switch_click.activate_window") as activate,
            patch("app.macros.switch_click.send_client_click") as send,
        ):
            macro._run(
                "Left", 1, "Switch clique", context,
                mouse_block_started=True, physical_source_delivered=True,
            )
        activate.assert_not_called()
        send.assert_not_called()
        runtime.macro_lock.wait.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_called_once()
        # A purely physical single-client click must not move the user's
        # cursor even for a harmless-looking redundant restoration.
        move.assert_not_called()

    def test_native_source_rejects_implicit_fallback_context(self) -> None:
        from app.macros.switch_click import SwitchClickContext, SwitchClickMacro

        runtime = _runtime()
        context = SwitchClickContext(
            101, 30, 25, 0.5, 0.5, "preferred_last_client_point",
        )
        self.assertFalse(SwitchClickMacro(runtime).run_async(
            "Left", 100, 100, 1, "Switch clique",
            captured_context=context, physical_source_delivered=True,
        ))
        runtime._spawn_macro.assert_not_called()

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
            patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
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
            patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.foreground_window", return_value=101),
            patch("app.macros.zaap.send_chat_command", side_effect=stop_during_chat),
        ):
            ZaapMacro(runtime)._run("/zaap -5,12")
        runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_direction_rejects_focus_stolen_during_native_process_check(self) -> None:
        runtime = _runtime()
        runtime.settings.client_by_handle.return_value = object()
        active = [101]
        probes = [0]

        def check_process(_hwnd):
            probes[0] += 1
            if probes[0] == 3:
                active[0] = 999
            return True

        with (
            patch("app.macros.direction.foreground_window",
                  side_effect=lambda: active[0]),
            patch("app.macros.direction.is_unity_window", return_value=True),
            patch("app.macros.direction.is_dofus_unity_process",
                  side_effect=check_process),
            patch("app.macros.direction.activate_window", return_value=True),
            patch("app.macros.direction.press_key") as press,
        ):
            DirectionMacro(runtime)._run("HOME")
        press.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Switch deplacement %s: envoyes=%s/%s", "interrompu", 0, 2,
        )

    def test_direction_stop_during_final_identity_check_prevents_key(self) -> None:
        runtime = _runtime()
        runtime.settings.client_by_handle.return_value = object()
        stopped = [False]
        probes = [0]
        runtime.macro_lock.should_stop.side_effect = lambda: stopped[0]

        def check_process(_hwnd):
            probes[0] += 1
            if probes[0] == 3:
                stopped[0] = True
            return True

        with (
            patch("app.macros.direction.foreground_window", return_value=101),
            patch("app.macros.direction.is_unity_window", return_value=True),
            patch("app.macros.direction.is_dofus_unity_process",
                  side_effect=check_process),
            patch("app.macros.direction.activate_window", return_value=True),
            patch("app.macros.direction.press_key") as press,
        ):
            DirectionMacro(runtime)._run("HOME")
        press.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Switch deplacement %s: envoyes=%s/%s", "interrompu", 0, 2,
        )

    def test_auto_group_rejects_focus_change_or_stop_during_final_probe(self) -> None:
        for change in ("focus", "stop"):
            with self.subTest(change=change):
                runtime = _runtime()
                runtime.settings.timings.auto_group_invite_gap_ms = 0
                runtime.switch_character.logical_active_client.return_value = (
                    SimpleNamespace(handle=101, display_name="Leader")
                )
                active = [101]
                stopped = [False]
                probes = [0]
                runtime.macro_lock.should_stop.side_effect = lambda: stopped[0]

                def process_probe(_hwnd):
                    probes[0] += 1
                    if probes[0] == 2:
                        if change == "focus":
                            active[0] = 999
                        else:
                            stopped[0] = True
                    return True

                with (
                    patch("app.macros.auto_group.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.auto_group.is_unity_window",
                          return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process",
                          side_effect=process_probe),
                    patch("app.macros.auto_group.activate_window",
                          return_value=True),
                    patch("app.macros.auto_group.send_chat_command") as chat,
                ):
                    AutoGroupMacro(runtime)._run([{"name": "Friend", "handle": 202}])
                chat.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
                    "interrompu", 0, 1, 1, 101,
                )

    def test_zaap_rejects_focus_change_or_stop_during_final_probe(self) -> None:
        for change in ("focus", "stop"):
            with self.subTest(change=change):
                runtime = _runtime()
                active = [101]
                stopped = [False]
                probes = [0]
                runtime.macro_lock.should_stop.side_effect = lambda: stopped[0]

                def process_probe(_hwnd):
                    probes[0] += 1
                    if probes[0] == 2:
                        if change == "focus":
                            active[0] = 999
                        else:
                            stopped[0] = True
                    return True

                with (
                    patch("app.macros.zaap.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.zaap.is_unity_window",
                          return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process",
                          side_effect=process_probe),
                    patch("app.macros.zaap.activate_window",
                          return_value=True),
                    patch("app.macros.zaap.send_chat_command") as chat,
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                chat.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Auto zaap %s: envoyes=%s/%s", "interrompu", 0, 2,
                )

    def test_auto_group_failed_chat_probe_cannot_hide_stolen_focus(self) -> None:
        runtime = _runtime()
        runtime.switch_character.logical_active_client.return_value = (
            SimpleNamespace(handle=101, display_name="Leader")
        )
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        active = [101]
        probes = [0]

        def probe(_hwnd):
            probes[0] += 1
            if probes[0] == 3:
                active[0] = 999
            return True

        with (
            patch("app.macros.auto_group.foreground_window",
                  side_effect=lambda: active[0]),
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", side_effect=probe),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.send_chat_command",
                  return_value=False) as chat,
        ):
            AutoGroupMacro(runtime)._run([
                {"name": "Friend1", "handle": 202},
                {"name": "Friend2", "handle": 303},
            ])
        chat.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "interrompu", 0, 1, 2, 101,
        )

    def test_zaap_failed_chat_probe_cannot_hide_stolen_focus(self) -> None:
        runtime = _runtime()
        active = [101]
        probes = [0]

        def probe(_hwnd):
            probes[0] += 1
            if probes[0] == 3:
                active[0] = 999
            return True

        with (
            patch("app.macros.zaap.foreground_window",
                  side_effect=lambda: active[0]),
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.is_dofus_unity_process", side_effect=probe),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.send_chat_command",
                  return_value=False) as chat,
        ):
            ZaapMacro(runtime)._run("/zaap 1,2")
        chat.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto zaap %s: envoyes=%s/%s", "interrompu", 0, 2,
        )

    def test_direction_reports_partial_when_client_activation_fails(self) -> None:
        runtime = _runtime()
        runtime.settings.client_by_handle.return_value = object()
        with (
            patch("app.macros.direction.foreground_window", return_value=101),
            patch("app.macros.direction.is_unity_window", return_value=True),
            patch("app.macros.direction.is_dofus_unity_process", return_value=True),
            patch("app.macros.direction.activate_window", side_effect=[True, False]),
            patch("app.macros.direction.press_key") as press,
        ):
            DirectionMacro(runtime)._run("HOME")
        press.assert_called_once()
        runtime.logger.info.assert_any_call(
            "Switch deplacement: activation echec hwnd=%s", 202,
        )
        runtime.logger.info.assert_any_call(
            "Switch deplacement %s: envoyes=%s/%s", "partiel", 1, 2,
        )

    def test_direction_two_four_eight_windows_delivered_once(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.settings.client_by_handle.return_value = object()
                handles = list(range(101, 101 + count))
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=hwnd) for hwnd in handles
                ]
                with (
                    patch("app.macros.direction.foreground_window",
                          side_effect=[handles[0], *handles, handles[-1]]),
                    patch("app.macros.direction.is_unity_window", return_value=True),
                    patch("app.macros.direction.is_dofus_unity_process", return_value=True),
                    patch("app.macros.direction.activate_window", return_value=True),
                    patch("app.macros.direction.press_key") as press,
                ):
                    DirectionMacro(runtime)._run("HOME")
                self.assertEqual(press.call_count, count)
                runtime.logger.info.assert_any_call(
                    "Switch deplacement %s: envoyes=%s/%s",
                    "termine", count, count,
                )

    def test_direction_never_reactivates_favorite_after_user_focus_change(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.settings.client_by_handle.return_value = object()
                handles = list(range(101, 101 + count))
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=hwnd) for hwnd in handles
                ]
                active = [101]
                sent = [0]

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def press(*_args, **_kwargs):
                    sent[0] += 1
                    if sent[0] == count:
                        active[0] = 999

                with (
                    patch("app.macros.direction.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.direction.is_unity_window",
                          return_value=True),
                    patch("app.macros.direction.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.direction.activate_window",
                          side_effect=activate),
                    patch("app.macros.direction.press_key",
                          side_effect=press) as keyboard,
                ):
                    DirectionMacro(runtime)._run("HOME")
                self.assertEqual(keyboard.call_count, count)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch deplacement: retour favori ignoré, focus utilisateur changé."
                )
                runtime.logger.info.assert_any_call(
                    "Switch deplacement %s: envoyes=%s/%s",
                    "interrompu", count, count,
                )

    def test_direction_cleanup_focus_read_error_never_restores(self) -> None:
        runtime = _runtime()
        runtime.settings.client_by_handle.return_value = object()
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101),
        ]
        calls = [0]

        def foreground():
            calls[0] += 1
            if calls[0] == 3:
                raise OSError("foreground refused")
            return 101

        with (
            patch("app.macros.direction.foreground_window",
                  side_effect=foreground),
            patch("app.macros.direction.is_unity_window", return_value=True),
            patch("app.macros.direction.is_dofus_unity_process", return_value=True),
            patch("app.macros.direction.activate_window", return_value=True),
            patch("app.macros.direction.press_key") as press,
        ):
            DirectionMacro(runtime)._run("HOME")
        press.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.exception.assert_any_call(
            "Switch deplacement: focus illisible avant retour au favori."
        )
        runtime.logger.info.assert_any_call(
            "Switch deplacement %s: envoyes=%s/%s", "interrompu", 1, 1,
        )

    def test_direction_does_not_restore_changed_favorite_after_keys(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.settings.primary_handle = 101
                runtime.settings.client_by_handle.return_value = object()
                handles = list(range(101, 101 + count))
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=hwnd) for hwnd in handles
                ]
                active = [101]
                sent = [0]

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def press(*_args, **_kwargs):
                    sent[0] += 1
                    if sent[0] == count:
                        runtime.settings.primary_handle = 999

                with (
                    patch("app.macros.direction.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.direction.is_unity_window",
                          return_value=True),
                    patch("app.macros.direction.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.direction.activate_window",
                          side_effect=activate),
                    patch("app.macros.direction.press_key",
                          side_effect=press) as keyboard,
                ):
                    DirectionMacro(runtime)._run("HOME")
                self.assertEqual(keyboard.call_count, count)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch deplacement: retour favori ignoré, favori changé."
                )

    def test_direction_restores_favorite_on_input_exception(self) -> None:
        runtime = _runtime()
        runtime.settings.client_by_handle.return_value = object()
        with (
            patch("app.macros.direction.foreground_window", return_value=101),
            patch("app.macros.direction.is_unity_window", return_value=True),
            patch("app.macros.direction.is_dofus_unity_process", return_value=True),
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
            patch("app.macros.direction.is_dofus_unity_process", return_value=True),
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
            patch("app.macros.direction.is_dofus_unity_process", return_value=True),
            patch("app.macros.direction.activate_window", return_value=True),
            patch("app.macros.direction.press_key", side_effect=stop_during_key),
        ):
            DirectionMacro(runtime)._run("HOME")
        runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_zaap_never_sends_chat_when_focus_was_stolen(self) -> None:
        runtime = _runtime()
        with (
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
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
            patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.foreground_window", side_effect=[101, 202, 202]),
            patch("app.macros.zaap.send_chat_command", side_effect=[True, False]),
        ):
            ZaapMacro(runtime)._run("/zaap 1,2")
        runtime.logger.info.assert_any_call("Auto zaap %s: envoyes=%s/%s", "partiel", 1, 2)


    def test_switch_character_rejects_invalid_index_without_worker(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=202, display_name="Friend"),
        ]
        macro = SwitchCharacterMacro(runtime)
        for invalid in (None, "invalid", object(), True, float("inf")):
            with self.subTest(value=repr(invalid)):
                self.assertFalse(macro.activate_by_index(invalid))
        runtime._spawn_macro.assert_not_called()

    def test_switch_character_return_does_not_report_stolen_focus(self) -> None:
        runtime = _runtime()
        runtime.active_client_handle = 101
        runtime.settings.preferred_client.return_value = SimpleNamespace(handle=202)
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window", return_value=999),
        ):
            SwitchCharacterMacro(runtime).restore_preferred_client("Macro")
        self.assertEqual(runtime.active_client_handle, 101)
        runtime.logger.warning.assert_any_call(
            "%s retour non confirmé: focus différent hwnd=%s", "Macro", 202,
        )

    def test_switch_character_return_does_not_mark_success_after_stop(self) -> None:
        runtime = _runtime()
        runtime.active_client_handle = 101
        runtime.settings.preferred_client.return_value = SimpleNamespace(handle=202)
        runtime.macro_lock.should_stop.side_effect = [False, True]
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window") as foreground,
        ):
            SwitchCharacterMacro(runtime).restore_preferred_client("Macro")
        foreground.assert_not_called()
        self.assertEqual(runtime.active_client_handle, 101)

    def test_switch_character_return_updates_active_only_after_confirmed_focus(self) -> None:
        runtime = _runtime()
        runtime.active_client_handle = 101
        runtime.settings.preferred_client.return_value = SimpleNamespace(handle=202)
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window", return_value=202),
        ):
            SwitchCharacterMacro(runtime).restore_preferred_client("Macro")
        self.assertEqual(runtime.active_client_handle, 202)


    def test_auto_group_failed_chat_with_stolen_focus_aborts_next_invite(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader"
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", side_effect=[101, 999]),
            patch("app.macros.auto_group.send_chat_command", return_value=False) as send,
        ):
            AutoGroupMacro(runtime)._run([
                {"name": "Friend1", "handle": 202},
                {"name": "Friend2", "handle": 303},
            ])
        send.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.warning.assert_any_call(
            "Auto groupe interrompu: focus ou identité DOFUS perdus après échec du chat hwnd=%s",
            101,
        )
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "interrompu", 0, 1, 2, 101,
        )


    def test_zaap_failed_chat_with_stolen_focus_aborts_other_windows(self) -> None:
        runtime = _runtime()
        with (
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.foreground_window", side_effect=[101, 999]),
            patch("app.macros.zaap.send_chat_command", return_value=False) as send,
        ):
            ZaapMacro(runtime)._run("/zaap 1,2")
        send.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.warning.assert_any_call(
            "Auto zaap interrompu: focus ou identité DOFUS perdus après échec du chat hwnd=%s",
            101,
        )
        runtime.logger.info.assert_any_call(
            "Auto zaap %s: envoyes=%s/%s", "interrompu", 0, 2,
        )



    def test_auto_group_rejects_sender_process_swap_before_invitation(self) -> None:
        runtime = _runtime()
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader",
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process",
                  side_effect=[True, False]),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", return_value=101),
            patch("app.macros.auto_group.send_chat_command") as send,
        ):
            AutoGroupMacro(runtime)._run([{"name": "Friend", "handle": 202}])
        send.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "interrompu", 0, 1, 1, 101,
        )

    def test_direction_rejects_foreign_window_after_focus_activation(self) -> None:
        runtime = _runtime()
        runtime.settings.client_by_handle.return_value = object()
        with (
            patch("app.macros.direction.foreground_window", return_value=101),
            patch("app.macros.direction.is_unity_window", return_value=True),
            patch("app.macros.direction.is_dofus_unity_process",
                  side_effect=[True, True, False]),
            patch("app.macros.direction.activate_window", return_value=True),
            patch("app.macros.direction.press_key") as press,
        ):
            DirectionMacro(runtime)._run("HOME")
        press.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Switch deplacement %s: envoyes=%s/%s", "interrompu", 0, 2,
        )

    def test_zaap_rejects_foreign_window_after_focus_activation(self) -> None:
        runtime = _runtime()
        with (
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.is_dofus_unity_process",
                  side_effect=[True, False]),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.foreground_window", return_value=101),
            patch("app.macros.zaap.send_chat_command") as send,
        ):
            ZaapMacro(runtime)._run("/zaap 1,2")
        send.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto zaap %s: envoyes=%s/%s", "interrompu", 0, 2,
        )

    def test_zaap_aborts_after_first_client_if_second_is_not_dofus(self) -> None:
        runtime = _runtime()
        with (
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.is_dofus_unity_process",
                  side_effect=[True, True, False]),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.foreground_window", return_value=101),
            patch("app.macros.zaap.send_chat_command", return_value=True) as send,
        ):
            ZaapMacro(runtime)._run("/zaap 1,2")
        send.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto zaap %s: envoyes=%s/%s", "interrompu", 1, 2,
        )



    def test_zaap_stop_before_first_client_skips_process_probe_and_restore(self) -> None:
        runtime = _runtime()
        runtime.macro_lock.should_stop.return_value = True
        with (
            patch("app.macros.zaap.is_unity_window") as unity,
            patch("app.macros.zaap.is_dofus_unity_process") as identity,
            patch("app.macros.zaap.activate_window") as activate,
            patch("app.macros.zaap.send_chat_command") as send,
        ):
            ZaapMacro(runtime)._run("/zaap 1,2")
        unity.assert_not_called()
        identity.assert_not_called()
        activate.assert_not_called()
        send.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto zaap %s: envoyes=%s/%s", "interrompu", 0, 2,
        )



    def test_auto_group_stop_between_identity_check_and_restore(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = SimpleNamespace(
            handle=101, display_name="Leader",
        )
        runtime.macro_lock.should_stop.side_effect = [False, False, False, True, True]
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", return_value=101),
            patch("app.macros.auto_group.send_chat_command", return_value=True),
        ):
            AutoGroupMacro(runtime)._run([{"name": "Friend", "handle": 202}])
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "interrompu", 1, 1, 1, 101,
        )

    def test_zaap_stop_between_identity_check_and_restore(self) -> None:
        runtime = _runtime()
        runtime.macro_lock.should_stop.side_effect = [False, False, False, True, True]
        with (
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
            patch("app.macros.zaap.activate_window", return_value=True),
            patch("app.macros.zaap.foreground_window", side_effect=[101, 202]),
            patch("app.macros.zaap.send_chat_command", return_value=True) as send,
        ):
            ZaapMacro(runtime)._run("/zaap 1,2")
        self.assertEqual(send.call_count, 2)
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto zaap %s: envoyes=%s/%s", "interrompu", 2, 2,
        )


if __name__ == "__main__":
    unittest.main()
