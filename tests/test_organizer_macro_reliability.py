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
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
        ):
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
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
            patch.object(macro, "logical_active_client", return_value=runtime.settings.clients[1]),
        ):
            ordered = macro.ordered_clients_from_source(float("inf"))
        self.assertEqual([c.handle for c in ordered], [202, 101])


    def test_roster_does_not_cast_foreign_or_fractional_hwnd_into_trusted_client(self) -> None:
        runtime = _runtime()
        trusted = SimpleNamespace(index=9, handle=101)
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=101.9),
            SimpleNamespace(index=2, handle=True),
            SimpleNamespace(index=3, handle="101"),
            SimpleNamespace(index=4, handle=2**64),
            trusted,
        ]
        with (
            patch("app.macros.switch_character.is_unity_window",
                  return_value=True) as unity,
            patch("app.macros.switch_character.is_dofus_unity_process",
                  return_value=True) as process,
        ):
            ordered = SwitchCharacterMacro(runtime).ordered_clients_from_source(101)
        self.assertEqual(ordered, [trusted])
        unity.assert_called_once_with(101)
        process.assert_called_once_with(101)
        self.assertEqual(runtime.logger.warning.call_count, 4)

    def test_character_hotkey_rejects_fractional_slot_without_spawning(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=101, display_name="Friend"),
        ]
        macro = SwitchCharacterMacro(runtime)
        for malformed in (True, 1.9, 1.0, float("nan"), float("inf")):
            with self.subTest(index=repr(malformed)):
                self.assertFalse(macro.activate_by_index(malformed))
        runtime._spawn_macro.assert_not_called()
        # Legacy textual slot indices are still accepted.
        runtime._spawn_macro.return_value = True
        self.assertTrue(macro.activate_by_index("1"))
        runtime._spawn_macro.assert_called_once()

    def test_explicit_detached_source_never_falls_back_to_favorite(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.settings.clients = [
                    SimpleNamespace(index=i, handle=101 + i)
                    for i in range(count)
                ]
                macro = SwitchCharacterMacro(runtime)
                with (
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          return_value=True),
                    patch.object(macro, "logical_active_client") as fallback,
                ):
                    self.assertEqual(
                        macro.ordered_clients_from_source(999), []
                    )
                fallback.assert_not_called()

    def test_source_zero_preserves_implicit_active_character_fallback(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=101),
            SimpleNamespace(index=2, handle=202),
        ]
        macro = SwitchCharacterMacro(runtime)
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
            patch.object(macro, "logical_active_client",
                         return_value=runtime.settings.clients[1]),
        ):
            self.assertEqual(
                [client.handle for client in macro.ordered_clients_from_source(0)],
                [202, 101],
            )

    def test_roster_never_includes_foreign_unity_process(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=101),
            SimpleNamespace(index=2, handle=202),
            SimpleNamespace(index=3, handle=303),
        ]
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process",
                  side_effect=lambda hwnd: hwnd != 202),
        ):
            ordered = SwitchCharacterMacro(runtime).ordered_clients_from_source(303)
        self.assertEqual([client.handle for client in ordered], [303, 101])

    def test_roster_with_only_foreign_unity_windows_is_empty(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [SimpleNamespace(index=1, handle=101)]
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=False),
        ):
            self.assertEqual(SwitchCharacterMacro(runtime).ordered_clients_from_source(101), [])

    def test_active_client_never_falls_back_to_foreign_unity_window(self) -> None:
        runtime = _runtime()
        foreign = SimpleNamespace(index=1, handle=101)
        trusted = SimpleNamespace(index=2, handle=202)
        runtime.settings.clients = [foreign, trusted]
        runtime.settings.client_by_handle.side_effect = (
            lambda hwnd: next((c for c in runtime.settings.clients if c.handle == hwnd), None)
        )
        runtime.settings.preferred_client.return_value = foreign
        runtime.active_client_handle = 101
        with (
            patch("app.macros.switch_character.foreground_window", return_value=101),
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process",
                  side_effect=lambda hwnd: hwnd == 202),
        ):
            found = SwitchCharacterMacro(runtime).logical_active_client()
        self.assertIs(found, trusted)
        self.assertEqual(runtime.active_client_handle, 202)

    def test_no_trusted_client_keeps_last_active_handle_unchanged(self) -> None:
        runtime = _runtime()
        foreign = SimpleNamespace(index=1, handle=101)
        runtime.settings.clients = [foreign]
        runtime.settings.client_by_handle.return_value = foreign
        runtime.settings.preferred_client.return_value = foreign
        runtime.active_client_handle = 303
        with (
            patch("app.macros.switch_character.foreground_window", return_value=101),
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=False),
        ):
            self.assertIsNone(SwitchCharacterMacro(runtime).logical_active_client())
        self.assertEqual(runtime.active_client_handle, 303)

    def test_profile_reload_during_auto_group_chat_cancels_remaining_2_to_8(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.settings.primary_handle = 101
                runtime.settings.timings.auto_group_invite_gap_ms = 0
                runtime.switch_character.logical_active_client.return_value = (
                    SimpleNamespace(handle=101, display_name="Leader")
                )
                entries = [
                    {"name": f"Friend{i}", "handle": 101 + i}
                    for i in range(1, count)
                ]

                def replace_profile(_command, _logger, **kwargs):
                    original = runtime.settings
                    replacement = Mock()
                    replacement.primary_handle = original.primary_handle
                    replacement.timings = original.timings
                    runtime.settings = replacement
                    self.assertTrue(kwargs["should_stop"]())
                    return False

                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
                    patch("app.macros.auto_group.activate_window", return_value=True),
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command",
                          side_effect=replace_profile) as send,
                ):
                    AutoGroupMacro(runtime)._run(entries)
                send.assert_called_once()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime._emit_status.assert_called_once_with(
                    f"Auto-groupe interrompu : 0/{count - 1} commandes émises "
                    "(réception DOFUS non vérifiée)."
                )

    def test_profile_reload_during_zaap_activation_cancels_chat_2_to_8(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.settings.primary_handle = 101
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]

                def activate_and_reload(_hwnd, *_args, **kwargs):
                    original = runtime.settings
                    replacement = Mock()
                    replacement.primary_handle = original.primary_handle
                    replacement.timings = original.timings
                    runtime.settings = replacement
                    self.assertTrue(kwargs["should_stop"]())
                    return True

                with (
                    patch("app.macros.zaap.is_unity_window", return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                    patch("app.macros.zaap.activate_window",
                          side_effect=activate_and_reload) as activate,
                    patch("app.macros.zaap.foreground_window") as foreground,
                    patch("app.macros.zaap.send_chat_command") as send,
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                activate.assert_called_once()
                foreground.assert_not_called()
                send.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime._emit_status.assert_called_once_with(
                    f"Auto zaap interrompu : 0/{count} commandes émises "
                    "(réception DOFUS non vérifiée)."
                )

    def test_profile_reload_during_direction_activation_skips_keys_2_to_8(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.settings.primary_handle = 101
                runtime.settings.client_by_handle.return_value = object()
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]

                def activate_and_reload(_hwnd, *_args, **kwargs):
                    original = runtime.settings
                    replacement = Mock()
                    replacement.primary_handle = original.primary_handle
                    replacement.timings = original.timings
                    runtime.settings = replacement
                    self.assertTrue(kwargs["should_stop"]())
                    return True

                with (
                    patch("app.macros.direction.foreground_window", return_value=101),
                    patch("app.macros.direction.is_unity_window", return_value=True),
                    patch("app.macros.direction.is_dofus_unity_process", return_value=True),
                    patch("app.macros.direction.activate_window",
                          side_effect=activate_and_reload) as activate,
                    patch("app.macros.direction.press_key") as send,
                ):
                    DirectionMacro(runtime)._run("HOME")
                activate.assert_called_once()
                send.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch deplacement %s: envoyes=%s/%s",
                    "interrompu", 0, count,
                )

    def test_auto_group_rejects_empty_queued_requests_before_spawning_worker(self) -> None:
        runtime = _runtime()
        macro = AutoGroupMacro(runtime)
        self.assertFalse(macro.run_async([]))
        self.assertFalse(macro.run_async([None, "", 5]))
        runtime._spawn_macro.assert_not_called()

    def test_auto_group_preplans_2_4_6_8_before_focus_and_skips_final_gap(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.settings.timings.auto_group_invite_gap_ms = 250
                runtime.macro_lock.wait.return_value = False
                runtime.switch_character.logical_active_client.return_value = (
                    SimpleNamespace(handle=101, display_name="Leader")
                )
                entries = [
                    {"name": "Leader", "handle": 101},
                    *({"name": f"Friend{i}", "handle": i + 101}
                      for i in range(1, count)),
                    {"name": "friend1", "handle": 202},
                    {"name": "", "handle": 999},
                ]
                observed = []
                def activate(*_args, **_kwargs):
                    observed.append("focus")
                    return True
                def send(text, *_args, **_kwargs):
                    observed.append(text)
                    return True
                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
                    patch("app.macros.auto_group.activate_window",
                          side_effect=activate),
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command", side_effect=send),
                ):
                    macro = AutoGroupMacro(runtime)
                    macro._run(entries)
                self.assertEqual(observed, [
                    "focus", *(f"/invite Friend{i}" for i in range(1, count))
                ])
                self.assertEqual(runtime.macro_lock.wait.call_count, max(0, count - 2))
                runtime.logger.info.assert_any_call(
                    "Auto groupe préparé: invitations=%s doublons=%s lanceur=%s vides=%s",
                    count - 1, 1, 1, 1,
                )
                runtime.logger.info.assert_any_call(
                    "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
                    "termine", count - 1, count - 1, len(entries), 101,
                )

    def test_auto_group_one_client_does_not_activate_or_restore_window(self) -> None:
        runtime = _runtime()
        runtime.switch_character.logical_active_client.return_value = (
            SimpleNamespace(handle=101, display_name="Leader")
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window") as activate,
            patch("app.macros.auto_group.send_chat_command") as send,
        ):
            AutoGroupMacro(runtime)._run([{"name": "Leader", "handle": 101}])
        activate.assert_not_called()
        send.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "ignore", 0, 0, 1, 101,
        )

    def test_auto_group_stop_prevents_any_focus_or_chat_before_preflight(self) -> None:
        runtime = _runtime()
        runtime.macro_lock.should_stop.return_value = True
        with (
            patch("app.macros.auto_group.is_unity_window") as unity,
            patch("app.macros.auto_group.activate_window") as activate,
            patch("app.macros.auto_group.send_chat_command") as send,
        ):
            AutoGroupMacro(runtime)._run([{"name": "Friend", "handle": 202}])
        unity.assert_not_called()
        activate.assert_not_called()
        send.assert_not_called()

    def test_auto_group_failed_last_invitation_never_waits_after_failure(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 200
        runtime.macro_lock.wait.return_value = False
        runtime.switch_character.logical_active_client.return_value = (
            SimpleNamespace(handle=101, display_name="Leader")
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", return_value=101),
            patch("app.macros.auto_group.send_chat_command",
                  side_effect=[True, False]) as send,
        ):
            AutoGroupMacro(runtime)._run([
                {"name": "Friend1", "handle": 202},
                {"name": "Friend2", "handle": 303},
            ])
        self.assertEqual(send.call_count, 2)
        runtime.macro_lock.wait.assert_called_once_with(200)
        runtime.logger.info.assert_any_call(
            "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
            "partiel", 1, 2, 2, 101,
        )

    def test_auto_group_runtime_propagates_spawn_refusal(self) -> None:
        from app.core.runtime_state import AtlasRuntime

        runtime = _runtime()
        runtime.auto_group.run_async.return_value = False
        with patch("app.core.runtime_state.load_settings", return_value=runtime.settings):
            self.assertFalse(AtlasRuntime.launch_auto_group(
                runtime, [{"name": "Friend", "handle": 202}]
            ))
        runtime.auto_group.run_async.assert_called_once()

    def test_auto_group_worker_publishes_sent_count_for_2_4_6_8(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                runtime.settings.timings.auto_group_invite_gap_ms = 0
                runtime.switch_character.logical_active_client.return_value = (
                    SimpleNamespace(handle=101, display_name="Leader")
                )
                entries = [
                    {"name": f"Friend{i}", "handle": 101 + i}
                    for i in range(1, count)
                ]
                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
                    patch("app.macros.auto_group.activate_window", return_value=True),
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command", return_value=True),
                ):
                    AutoGroupMacro(runtime)._run(entries)
                runtime._emit_status.assert_called_once_with(
                    f"Auto-groupe termine : {count-1}/{count-1} commandes émises "
                    "(réception DOFUS non vérifiée)."
                )

    def test_auto_group_worker_reports_partial_emission_not_completion(self) -> None:
        runtime = _runtime()
        runtime.settings.timings.auto_group_invite_gap_ms = 0
        runtime.switch_character.logical_active_client.return_value = (
            SimpleNamespace(handle=101, display_name="Leader")
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window", return_value=True),
            patch("app.macros.auto_group.foreground_window", return_value=101),
            patch("app.macros.auto_group.send_chat_command", side_effect=[True, False]),
        ):
            AutoGroupMacro(runtime)._run([
                {"name": "Friend1", "handle": 202},
                {"name": "Friend2", "handle": 303},
            ])
        runtime._emit_status.assert_called_once_with(
            "Auto-groupe partiel : 1/2 commandes émises "
            "(réception DOFUS non vérifiée)."
        )

    def test_auto_group_one_character_reports_ignored_without_focus(self) -> None:
        runtime = _runtime()
        runtime.switch_character.logical_active_client.return_value = (
            SimpleNamespace(handle=101, display_name="Leader")
        )
        with (
            patch("app.macros.auto_group.is_unity_window", return_value=True),
            patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
            patch("app.macros.auto_group.activate_window") as activate,
        ):
            AutoGroupMacro(runtime)._run([{"name": "Leader", "handle": 101}])
        activate.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Auto-groupe ignoré : aucun autre personnage à inviter."
        )

    def test_auto_group_pre_stopped_sends_final_stop_status_without_focus(self) -> None:
        runtime = _runtime()
        runtime.macro_lock.should_stop.return_value = True
        with patch("app.macros.auto_group.activate_window") as activation:
            AutoGroupMacro(runtime)._run([{"name": "Friend", "handle": 202}])
        activation.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Auto-groupe arrêté avant lancement."
        )

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
                    "termine", count - 1, count - 1, count - 1, 101,
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
                runtime.logger.info.assert_any_call(
                    "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
                    "termine", count - 1, count - 1, count - 1, 101,
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

    def test_zaap_invalid_command_cannot_claim_worker_started(self) -> None:
        runtime = _runtime()
        self.assertFalse(ZaapMacro(runtime).run_async("/zaap not-allowed"))
        runtime._spawn_macro.assert_not_called()

    def test_zaap_busy_worker_rejection_is_propagated(self) -> None:
        runtime = _runtime()
        runtime._spawn_macro.return_value = False
        self.assertFalse(ZaapMacro(runtime).run_async("/zaap 1,2"))
        runtime._spawn_macro.assert_called_once()

    def test_zaap_worker_reports_emitted_commands_for_2_4_6_8(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(handle=101 + index)
                    for index in range(count)
                ]
                runtime.switch_character.ordered_clients_from_source.return_value = clients
                focus = [101]
                def activation(hwnd, *_args, **_kwargs):
                    focus[0] = hwnd
                    return True
                with (
                    patch("app.macros.zaap.is_unity_window", return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                    patch("app.macros.zaap.activate_window", side_effect=activation),
                    patch("app.macros.zaap.foreground_window", side_effect=lambda: focus[0]),
                    patch("app.macros.zaap.send_chat_command", return_value=True),
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                runtime._emit_status.assert_called_once_with(
                    f"Auto zaap termine : {count}/{count} commandes émises "
                    "(réception DOFUS non vérifiée)."
                )

    def test_zaap_worker_reports_partial_failure_with_real_counts(self) -> None:
        runtime = _runtime()
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        ]
        focus = [101]
        def activation(hwnd, *_args, **_kwargs):
            focus[0] = hwnd
            return True
        with (
            patch("app.macros.zaap.is_unity_window", return_value=True),
            patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
            patch("app.macros.zaap.activate_window", side_effect=activation),
            patch("app.macros.zaap.foreground_window", side_effect=lambda: focus[0]),
            patch("app.macros.zaap.send_chat_command", side_effect=[True, False]),
        ):
            ZaapMacro(runtime)._run("/zaap 1,2")
        runtime._emit_status.assert_called_once_with(
            "Auto zaap partiel : 1/2 commandes émises "
            "(réception DOFUS non vérifiée)."
        )

    def test_zaap_worker_reports_no_clients_as_ignored(self) -> None:
        runtime = _runtime()
        runtime.switch_character.ordered_clients_from_source.return_value = []
        ZaapMacro(runtime)._run("/zaap 1,2")
        runtime._emit_status.assert_called_once_with(
            "Auto zaap ignoré : aucune fenêtre DOFUS disponible."
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
                    "Auto zaap %s: envoyes=%s/%s", "termine", count, count,
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
                runtime.logger.info.assert_any_call(
                    "Auto zaap %s: envoyes=%s/%s", "termine", count, count,
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
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
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
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window", return_value=999),
        ):
            self.assertTrue(SwitchCharacterMacro(runtime).activate_by_index(1))
            runtime._spawn_macro.call_args.args[1]()
        self.assertEqual(runtime.active_client_handle, 101)
        runtime.logger.warning.assert_any_call(
            "Activation client ignoree: identite ou focus non confirme hwnd=%s", 202,
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
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window") as foreground,
        ):
            self.assertTrue(SwitchCharacterMacro(runtime).activate_by_index(1))
            runtime._spawn_macro.call_args.args[1]()
        foreground.assert_not_called()
        self.assertEqual(runtime.active_client_handle, 101)

    def test_switch_click_rejects_nonfinite_cursor_without_worker(self) -> None:
        from app.macros.switch_click import SwitchClickMacro
        for coord in (float("inf"), -float("inf"), float("nan")):
            for axis in ("x", "y"):
                with self.subTest(coord=coord, axis=axis):
                    runtime = _runtime()
                    macro = SwitchClickMacro(runtime)
                    pos = (coord, 20) if axis == "x" else (20, coord)
                    with patch.object(macro, "_capture_trigger_context") as capture:
                        self.assertFalse(macro.run_async(
                            "left", *pos, 2, "Miroir",
                        ))
                    capture.assert_not_called()
                    runtime._spawn_macro.assert_not_called()
                    runtime.input_state.begin_mouse_block.assert_not_called()

    def test_switch_click_infinite_count_cannot_crash_busy_worker(self) -> None:
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext
        runtime = _runtime()
        runtime._spawn_macro.return_value = False
        macro = SwitchClickMacro(runtime)
        context = SwitchClickContext(101, 10, 20, 0.2, 0.4, "cursor")
        self.assertFalse(macro.run_async(
            "left", 10, 20, float("inf"), "Miroir",
            captured_context=context,
        ))
        runtime._spawn_macro.assert_called_once()
        runtime.input_state.begin_mouse_block.assert_not_called()
        runtime.input_state.end_mouse_block.assert_not_called()

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

    def test_queued_classic_switch_keeps_mouse_native_until_pointer_ownership(self):
        from app.core.runtime_state import AtlasRuntime
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.input_state = InputState()
                runtime._running = True
                runtime._admin_ok = True
                runtime.settings.macro_mode = "macro"
                runtime.settings.clients = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]
                runtime.macro_lock.active_label = "Switch clique"
                runtime.registry.switch_action_for_pressed_keys.return_value = (
                    SimpleNamespace(
                        action_id="switch_click",
                        payload={"click_count": 1},
                    )
                )
                with (
                    patch("app.windows.unity_windows.foreground_window") as focus,
                    patch("app.windows.unity_windows.find_known_client_from_point") as point,
                    patch("app.macros.mirror_plan.is_dofus_unity_process") as process,
                ):
                    self.assertFalse(
                        AtlasRuntime._handle_mouse_click(runtime, "Left", 20, 25)
                    )
                focus.assert_not_called()
                point.assert_not_called()
                process.assert_not_called()
                runtime.switch_click.run_async.assert_not_called()

    def test_active_classic_switch_still_blocks_extra_click_during_delivery(self):
        from app.core.runtime_state import AtlasRuntime
        from app.input.input_state import InputState

        runtime = _runtime()
        runtime.input_state = InputState()
        runtime.input_state.begin_mouse_block("Switch clique")
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
                  return_value=101),
            patch("app.macros.mirror_plan.is_dofus_unity_process",
                  return_value=True),
        ):
            self.assertTrue(AtlasRuntime._handle_mouse_click(
                runtime, "Left", 20, 25,
            ))
        runtime.switch_click.run_async.assert_not_called()
        runtime.input_state.end_mouse_block()

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
            patch("app.macros.switch_click.is_dofus_unity_process", return_value=True),
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
        runtime.input_state.begin_mouse_block.assert_not_called()

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
                    "termine", count, count,
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
            "Switch deplacement %s: envoyes=%s/%s", "termine", 1, 1,
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
                runtime.logger.info.assert_any_call(
                    "Switch deplacement %s: envoyes=%s/%s",
                    "termine", count, count,
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

    def test_hotkey_never_activates_reassigned_slot_while_worker_waits(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.settings.clients = [
                    SimpleNamespace(index=i, handle=100 + i, display_name=f"Client {i}")
                    for i in range(1, count + 1)
                ]
                runtime.active_client_handle = 101
                runtime._spawn_macro.return_value = True
                macro = SwitchCharacterMacro(runtime)
                self.assertTrue(macro.activate_by_index(count))
                runtime.settings.clients[-1] = SimpleNamespace(
                    index=count, handle=999, display_name="Replacement",
                )
                with (
                    patch("app.macros.switch_character.is_unity_window") as unity,
                    patch("app.macros.switch_character.is_dofus_unity_process") as identity,
                    patch("app.macros.switch_character.activate_window") as activate,
                ):
                    runtime._spawn_macro.call_args.args[1]()
                unity.assert_not_called()
                identity.assert_not_called()
                activate.assert_not_called()
                self.assertEqual(runtime.active_client_handle, 101)

    def test_hotkey_does_not_publish_focus_after_slot_changed_during_activation(self):
        runtime = _runtime()
        original = SimpleNamespace(index=1, handle=202, display_name="Friend")
        runtime.settings.clients = [original]
        runtime.active_client_handle = 101
        runtime._spawn_macro.return_value = True
        macro = SwitchCharacterMacro(runtime)
        self.assertTrue(macro.activate_by_index(1))

        def replace_target(*_args, **_kwargs):
            runtime.settings.clients = [
                SimpleNamespace(index=1, handle=303, display_name="New"),
            ]
            return True

        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_character.activate_window",
                  side_effect=replace_target) as activate,
            patch("app.macros.switch_character.foreground_window") as foreground,
        ):
            runtime._spawn_macro.call_args.args[1]()
        activate.assert_called_once()
        foreground.assert_not_called()
        self.assertEqual(runtime.active_client_handle, 101)

    def test_hotkey_allows_unrelated_slot_refresh_if_target_is_unchanged(self):
        runtime = _runtime()
        target = SimpleNamespace(index=1, handle=202, display_name="Friend")
        runtime.settings.clients = [target, SimpleNamespace(index=2, handle=303)]
        runtime.active_client_handle = 101
        runtime._spawn_macro.return_value = True
        macro = SwitchCharacterMacro(runtime)
        self.assertTrue(macro.activate_by_index(1))
        runtime.settings.clients = [target, SimpleNamespace(index=2, handle=404)]
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window", return_value=202),
        ):
            runtime._spawn_macro.call_args.args[1]()
        self.assertEqual(runtime.active_client_handle, 202)

    def test_queued_character_activation_rejects_identical_profile_reload_2_to_8(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(index=i, handle=101 + i, display_name=f"Player{i}")
                    for i in range(1, count + 1)
                ]
                runtime.settings.clients = clients
                runtime.active_client_handle = 101
                runtime._spawn_macro.return_value = True
                self.assertTrue(SwitchCharacterMacro(runtime).activate_by_index(1))
                former = runtime.settings
                newer = Mock()
                newer.clients = list(clients)
                newer.timings = former.timings
                runtime.settings = newer
                with (
                    patch("app.macros.switch_character.is_unity_window") as unity,
                    patch("app.macros.switch_character.activate_window") as activate,
                ):
                    runtime._spawn_macro.call_args.args[1]()
                unity.assert_not_called()
                activate.assert_not_called()
                self.assertEqual(runtime.active_client_handle, 101)

    def test_character_activation_rejects_identical_profile_reload_during_focus(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=202, display_name="Friend"),
        ]
        runtime.active_client_handle = 101
        runtime._spawn_macro.return_value = True
        self.assertTrue(SwitchCharacterMacro(runtime).activate_by_index(1))

        def activate_and_reload(*_args, **kwargs):
            old = runtime.settings
            newer = Mock()
            newer.clients = list(old.clients)
            newer.timings = old.timings
            runtime.settings = newer
            self.assertTrue(kwargs["should_stop"]())
            return True

        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_character.activate_window",
                  side_effect=activate_and_reload) as activate,
            patch("app.macros.switch_character.foreground_window") as foreground,
        ):
            runtime._spawn_macro.call_args.args[1]()
        activate.assert_called_once()
        foreground.assert_not_called()
        self.assertEqual(runtime.active_client_handle, 101)

    def test_favorite_restore_rejects_identical_profile_reload_during_activation(self) -> None:
        runtime = _runtime()
        runtime.active_client_handle = 101
        runtime.settings.preferred_client.return_value = SimpleNamespace(handle=202)

        def activate_and_reload(*_args, **kwargs):
            old = runtime.settings
            newer = Mock()
            newer.clients = old.clients
            newer.timings = old.timings
            newer.preferred_client.return_value = SimpleNamespace(handle=202)
            runtime.settings = newer
            self.assertTrue(kwargs["should_stop"]())
            return True

        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_character.activate_window",
                  side_effect=activate_and_reload) as activate,
            patch("app.macros.switch_character.foreground_window") as foreground,
        ):
            SwitchCharacterMacro(runtime).restore_preferred_client("Macro")
        activate.assert_called_once()
        foreground.assert_not_called()
        self.assertEqual(runtime.active_client_handle, 101)

    def test_shortcut_rejects_foreign_unity_process_without_activation(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=202, display_name="Friend"),
        ]
        runtime.active_client_handle = 101
        runtime._spawn_macro.return_value = True
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=False),
            patch("app.macros.switch_character.activate_window") as activate,
        ):
            self.assertTrue(SwitchCharacterMacro(runtime).activate_by_index(1))
            runtime._spawn_macro.call_args.args[1]()
        activate.assert_not_called()
        self.assertEqual(runtime.active_client_handle, 101)

    def test_shortcut_rejects_process_replacement_after_activation(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=202, display_name="Friend"),
        ]
        runtime.active_client_handle = 101
        runtime._spawn_macro.return_value = True
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process",
                  side_effect=[True, False]),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window") as foreground,
        ):
            self.assertTrue(SwitchCharacterMacro(runtime).activate_by_index(1))
            runtime._spawn_macro.call_args.args[1]()
        foreground.assert_not_called()
        self.assertEqual(runtime.active_client_handle, 101)

    def test_favorite_restore_does_not_publish_old_favorite_after_change(self) -> None:
        runtime = _runtime()
        runtime.active_client_handle = 101
        runtime.settings.preferred_client.side_effect = [
            SimpleNamespace(handle=202), SimpleNamespace(handle=303),
        ]
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_character.activate_window", return_value=True) as activate,
            patch("app.macros.switch_character.foreground_window") as foreground,
        ):
            SwitchCharacterMacro(runtime).restore_preferred_client("Macro")
        activate.assert_called_once()
        foreground.assert_not_called()
        self.assertEqual(runtime.active_client_handle, 101)

    def test_favorite_restore_does_not_publish_when_favorite_removed(self) -> None:
        runtime = _runtime()
        runtime.active_client_handle = 101
        runtime.settings.preferred_client.side_effect = [
            SimpleNamespace(handle=202), None,
        ]
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window") as foreground,
        ):
            SwitchCharacterMacro(runtime).restore_preferred_client("Macro")
        foreground.assert_not_called()
        self.assertEqual(runtime.active_client_handle, 101)

    def test_favorite_restore_refuses_foreign_unity_process(self) -> None:
        runtime = _runtime()
        runtime.active_client_handle = 101
        runtime.settings.preferred_client.return_value = SimpleNamespace(handle=202)
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=False),
            patch("app.macros.switch_character.activate_window") as activate,
        ):
            SwitchCharacterMacro(runtime).restore_preferred_client("Macro")
        activate.assert_not_called()
        self.assertEqual(runtime.active_client_handle, 101)

    def test_favorite_restore_refuses_process_replacement_after_activation(self) -> None:
        runtime = _runtime()
        runtime.active_client_handle = 101
        runtime.settings.preferred_client.return_value = SimpleNamespace(handle=202)
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process",
                  side_effect=[True, False]),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window") as foreground,
        ):
            SwitchCharacterMacro(runtime).restore_preferred_client("Macro")
        foreground.assert_not_called()
        self.assertEqual(runtime.active_client_handle, 101)

    def test_switch_character_return_does_not_report_stolen_focus(self) -> None:
        runtime = _runtime()
        runtime.active_client_handle = 101
        runtime.settings.preferred_client.return_value = SimpleNamespace(handle=202)
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_character.activate_window", return_value=True),
            patch("app.macros.switch_character.foreground_window", return_value=999),
        ):
            SwitchCharacterMacro(runtime).restore_preferred_client("Macro")
        self.assertEqual(runtime.active_client_handle, 101)
        runtime.logger.warning.assert_any_call(
            "%s retour non confirmé: identite ou focus différent hwnd=%s", "Macro", 202,
        )

    def test_switch_character_return_does_not_mark_success_after_stop(self) -> None:
        runtime = _runtime()
        runtime.active_client_handle = 101
        runtime.settings.preferred_client.return_value = SimpleNamespace(handle=202)
        runtime.macro_lock.should_stop.side_effect = [False, True]
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
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
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
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
