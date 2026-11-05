"""Regression contracts: switching the Organizer favorite invalidates active fan-outs.

These are isolated simulations. They do not prove DOFUS Unity input delivery.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.macros.auto_group import AutoGroupMacro
from app.macros.direction import DirectionMacro
from app.macros.zaap import ZaapMacro


def _runtime(client_count: int) -> Mock:
    runtime = Mock()
    runtime.settings.primary_handle = 101
    runtime.settings.timings.auto_group_invite_gap_ms = 0
    runtime.settings.timings.switch_client_settle_ms = 0
    runtime.macro_lock.should_stop.return_value = False
    runtime.switch_character.ordered_clients_from_source.return_value = [
        SimpleNamespace(handle=101 + i) for i in range(client_count)
    ]
    runtime.switch_character.logical_active_client.return_value = (
        SimpleNamespace(handle=101, display_name="Leader")
    )
    runtime.settings.client_by_handle.return_value = object()
    return runtime


class OrganizerFavoriteInflightTests(unittest.TestCase):
    def test_auto_group_stops_following_invitations_after_favorite_change(self):
        for count in (4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                entries = [
                    {"name": f"Friend{i}", "handle": 101 + i}
                    for i in range(1, count)
                ]
                def send(*_args, **_kwargs):
                    runtime.settings.primary_handle = 999
                    return True

                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
                    patch("app.macros.auto_group.activate_window", return_value=True),
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command", side_effect=send) as sender,
                ):
                    AutoGroupMacro(runtime)._run(entries)
                self.assertEqual(sender.call_count, 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                self.assertIn("interrompu : 1/", runtime._emit_status.call_args.args[0])

    def test_auto_group_favorite_changed_during_focus_blocks_first_invite(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                def activate(*_args, **_kwargs):
                    runtime.settings.primary_handle = 999
                    return True

                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
                    patch("app.macros.auto_group.activate_window", side_effect=activate),
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command", return_value=True) as sender,
                ):
                    AutoGroupMacro(runtime)._run([{"name": "Friend", "handle": 202}])
                sender.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                self.assertIn("interrompu : 0/", runtime._emit_status.call_args.args[0])

    def test_auto_group_chat_abort_on_new_favorite_does_not_continue(self):
        for count in (4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                entries = [
                    {"name": f"Friend{i}", "handle": 101 + i}
                    for i in range(1, count)
                ]
                def refuse(*_args, **_kwargs):
                    runtime.settings.primary_handle = 999
                    return False

                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
                    patch("app.macros.auto_group.activate_window", return_value=True),
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command", side_effect=refuse) as sender,
                ):
                    AutoGroupMacro(runtime)._run(entries)
                self.assertEqual(sender.call_count, 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                self.assertIn("interrompu : 0/", runtime._emit_status.call_args.args[0])

    def test_zaap_stops_following_clients_after_favorite_change(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                active = [101]
                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def send(*_args, **_kwargs):
                    runtime.settings.primary_handle = 999
                    return True

                with (
                    patch("app.macros.zaap.is_unity_window", return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                    patch("app.macros.zaap.activate_window", side_effect=activate),
                    patch("app.macros.zaap.foreground_window", side_effect=lambda: active[0]),
                    patch("app.macros.zaap.send_chat_command", side_effect=send) as sender,
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                self.assertEqual(sender.call_count, 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                self.assertIn("interrompu : 1/", runtime._emit_status.call_args.args[0])

    def test_zaap_favorite_changed_during_focus_blocks_chat(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                def activate(*_args, **_kwargs):
                    runtime.settings.primary_handle = 999
                    return True

                with (
                    patch("app.macros.zaap.is_unity_window", return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                    patch("app.macros.zaap.activate_window", side_effect=activate),
                    patch("app.macros.zaap.foreground_window", return_value=101),
                    patch("app.macros.zaap.send_chat_command", return_value=True) as sender,
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                sender.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                self.assertIn("interrompu : 0/", runtime._emit_status.call_args.args[0])

    def test_zaap_chat_abort_on_new_favorite_does_not_continue(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                active = [101]
                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def refuse(*_args, **_kwargs):
                    runtime.settings.primary_handle = 999
                    return False

                with (
                    patch("app.macros.zaap.is_unity_window", return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                    patch("app.macros.zaap.activate_window", side_effect=activate),
                    patch("app.macros.zaap.foreground_window", side_effect=lambda: active[0]),
                    patch("app.macros.zaap.send_chat_command", side_effect=refuse) as sender,
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                self.assertEqual(sender.call_count, 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                self.assertIn("interrompu : 0/", runtime._emit_status.call_args.args[0])

    def test_direction_stops_following_clients_after_favorite_change(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                active = [101]
                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def send(*_args, **_kwargs):
                    runtime.settings.primary_handle = 999

                with (
                    patch("app.macros.direction.is_unity_window", return_value=True),
                    patch("app.macros.direction.is_dofus_unity_process", return_value=True),
                    patch("app.macros.direction.activate_window", side_effect=activate),
                    patch("app.macros.direction.foreground_window", side_effect=lambda: active[0]),
                    patch("app.macros.direction.press_key", side_effect=send) as sender,
                ):
                    DirectionMacro(runtime)._run("HOME")
                self.assertEqual(sender.call_count, 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch deplacement %s: envoyes=%s/%s",
                    "interrompu", 1, count,
                )

    def test_direction_favorite_changed_during_focus_blocks_key(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                def activate(*_args, **_kwargs):
                    runtime.settings.primary_handle = 999
                    return True

                with (
                    patch("app.macros.direction.is_unity_window", return_value=True),
                    patch("app.macros.direction.is_dofus_unity_process", return_value=True),
                    patch("app.macros.direction.activate_window", side_effect=activate),
                    patch("app.macros.direction.foreground_window", return_value=101),
                    patch("app.macros.direction.press_key") as sender,
                ):
                    DirectionMacro(runtime)._run("HOME")
                sender.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch deplacement %s: envoyes=%s/%s",
                    "interrompu", 0, count,
                )


    def test_auto_group_queued_worker_rejects_mode_or_favorite_change(self):
        for count in (2, 4, 6, 8):
            for field, replacement in (("primary_handle", 999), ("macro_mode", "mirror")):
                with self.subTest(clients=count, field=field):
                    runtime = _runtime(count)
                    runtime.settings.macro_mode = "macro"

                    def spawn(_label, worker):
                        setattr(runtime.settings, field, replacement)
                        worker()
                        return True

                    runtime._spawn_macro.side_effect = spawn
                    with patch(
                        "app.macros.auto_group.is_unity_window",
                        side_effect=AssertionError("Native probe after stale dispatch"),
                    ):
                        self.assertTrue(AutoGroupMacro(runtime).run_async(
                            [{"name": "Friend", "handle": 202}]
                        ))
                    runtime.switch_character.logical_active_client.assert_not_called()
                    self.assertIn("interrompu", runtime._emit_status.call_args.args[0])

    def test_zaap_queued_worker_rejects_mode_or_favorite_change(self):
        for count in (2, 4, 6, 8):
            for field, replacement in (("primary_handle", 999), ("macro_mode", "mirror")):
                with self.subTest(clients=count, field=field):
                    runtime = _runtime(count)
                    runtime.settings.macro_mode = "macro"

                    def spawn(_label, worker):
                        setattr(runtime.settings, field, replacement)
                        worker()
                        return True

                    runtime._spawn_macro.side_effect = spawn
                    self.assertTrue(ZaapMacro(runtime).run_async("/zaap 1,2"))
                    runtime.switch_character.ordered_clients_from_source.assert_not_called()
                    self.assertIn("interrompu", runtime._emit_status.call_args.args[0])

    def test_direction_queued_worker_rejects_mode_or_favorite_change(self):
        for count in (2, 4, 6, 8):
            for field, replacement in (("primary_handle", 999), ("macro_mode", "mirror")):
                with self.subTest(clients=count, field=field):
                    runtime = _runtime(count)
                    runtime.settings.macro_mode = "macro"

                    def spawn(_label, worker):
                        setattr(runtime.settings, field, replacement)
                        worker()
                        return True

                    runtime._spawn_macro.side_effect = spawn
                    with patch(
                        "app.macros.direction.foreground_window",
                        side_effect=AssertionError("Native probe after stale dispatch"),
                    ):
                        self.assertTrue(DirectionMacro(runtime).run_async("HOME"))
                    runtime.switch_character.ordered_clients_from_source.assert_not_called()

    def test_auto_group_mode_switch_aborts_remaining_invitations(self):
        for count in (4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                runtime.settings.macro_mode = "macro"
                entries = [
                    {"name": f"Friend{i}", "handle": 101 + i}
                    for i in range(1, count)
                ]
                def send(*_args, **_kwargs):
                    runtime.settings.macro_mode = "mirror"
                    return True

                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process", return_value=True),
                    patch("app.macros.auto_group.activate_window", return_value=True),
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command", side_effect=send) as sender,
                ):
                    AutoGroupMacro(runtime)._run(entries)
                self.assertEqual(sender.call_count, 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                self.assertIn("interrompu : 1/", runtime._emit_status.call_args.args[0])

    def test_zaap_mode_switch_aborts_remaining_clients(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                runtime.settings.macro_mode = "macro"
                active = [101]
                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def send(*_args, **_kwargs):
                    runtime.settings.macro_mode = "mirror"
                    return True

                with (
                    patch("app.macros.zaap.is_unity_window", return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                    patch("app.macros.zaap.activate_window", side_effect=activate),
                    patch("app.macros.zaap.foreground_window", side_effect=lambda: active[0]),
                    patch("app.macros.zaap.send_chat_command", side_effect=send) as sender,
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                self.assertEqual(sender.call_count, 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                self.assertIn("interrompu : 1/", runtime._emit_status.call_args.args[0])

    def test_direction_mode_switch_aborts_remaining_clients(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                runtime.settings.macro_mode = "macro"
                active = [101]
                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def send(*_args, **_kwargs):
                    runtime.settings.macro_mode = "mirror"

                with (
                    patch("app.macros.direction.is_unity_window", return_value=True),
                    patch("app.macros.direction.is_dofus_unity_process", return_value=True),
                    patch("app.macros.direction.activate_window", side_effect=activate),
                    patch("app.macros.direction.foreground_window", side_effect=lambda: active[0]),
                    patch("app.macros.direction.press_key", side_effect=send) as sender,
                ):
                    DirectionMacro(runtime)._run("HOME")
                self.assertEqual(sender.call_count, 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch deplacement %s: envoyes=%s/%s",
                    "interrompu", 1, count,
                )


    def test_auto_group_favorite_or_mode_mutated_during_source_lookup_aborts(self):
        for count in (2, 4, 6, 8):
            for field, replacement in (("primary_handle", 999), ("macro_mode", "mirror")):
                with self.subTest(clients=count, field=field):
                    runtime = _runtime(count)
                    runtime.settings.macro_mode = "macro"

                    def resolve_source():
                        setattr(runtime.settings, field, replacement)
                        return SimpleNamespace(handle=101, display_name="Leader")

                    runtime.switch_character.logical_active_client.side_effect = resolve_source
                    with patch(
                        "app.macros.auto_group.is_unity_window",
                        side_effect=AssertionError("Stale source reached Win32"),
                    ):
                        AutoGroupMacro(runtime)._run(
                            [{"name": "Friend", "handle": 202}],
                        )
                    runtime.switch_character.logical_active_client.assert_called_once()
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    self.assertIn("interrompu", runtime._emit_status.call_args.args[0])

    def test_zaap_favorite_or_mode_mutated_during_roster_lookup_aborts(self):
        for count in (2, 4, 6, 8):
            for field, replacement in (("primary_handle", 999), ("macro_mode", "mirror")):
                with self.subTest(clients=count, field=field):
                    runtime = _runtime(count)
                    runtime.settings.macro_mode = "macro"

                    def resolve_clients():
                        setattr(runtime.settings, field, replacement)
                        return [SimpleNamespace(handle=101 + i) for i in range(count)]

                    runtime.switch_character.ordered_clients_from_source.side_effect = resolve_clients
                    with patch(
                        "app.macros.zaap.is_unity_window",
                        side_effect=AssertionError("Stale roster reached Win32"),
                    ):
                        ZaapMacro(runtime)._run("/zaap 1,2")
                    runtime.switch_character.ordered_clients_from_source.assert_called_once()
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    self.assertIn("interrompu", runtime._emit_status.call_args.args[0])


    def test_auto_group_late_mode_change_during_cleanup_never_restores(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                runtime.settings.macro_mode = "macro"
                entries = [
                    {"name": f"Friend{i}", "handle": 101 + i}
                    for i in range(1, count)
                ]
                completed = [False]
                sent_count = [0]

                def send(*_args, **_kwargs):
                    sent_count[0] += 1
                    completed[0] = sent_count[0] == count - 1
                    return True

                def probe(_hwnd):
                    if completed[0]:
                        runtime.settings.macro_mode = "mirror"
                    return True

                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process", side_effect=probe),
                    patch("app.macros.auto_group.activate_window", return_value=True),
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command", side_effect=send) as sender,
                ):
                    AutoGroupMacro(runtime)._run(entries)
                self.assertEqual(sender.call_count, count - 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                self.assertIn("interrompu : ", runtime._emit_status.call_args.args[0])

    def test_zaap_late_mode_change_during_cleanup_never_restores(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                runtime.settings.macro_mode = "macro"
                active = [101]
                completed = [False]
                sent_count = [0]

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def send(*_args, **_kwargs):
                    sent_count[0] += 1
                    completed[0] = sent_count[0] == count
                    return True

                def probe(_hwnd):
                    if completed[0]:
                        runtime.settings.macro_mode = "mirror"
                    return True

                with (
                    patch("app.macros.zaap.is_unity_window", return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process", side_effect=probe),
                    patch("app.macros.zaap.activate_window", side_effect=activate),
                    patch("app.macros.zaap.foreground_window", side_effect=lambda: active[0]),
                    patch("app.macros.zaap.send_chat_command", side_effect=send) as sender,
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                self.assertEqual(sender.call_count, count)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                self.assertIn("interrompu : ", runtime._emit_status.call_args.args[0])

    def test_direction_late_mode_change_during_cleanup_never_restores(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                runtime.settings.macro_mode = "macro"
                active = [101]
                sent_count = [0]

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def send(*_args, **_kwargs):
                    sent_count[0] += 1

                def probe(_hwnd):
                    if sent_count[0] == count:
                        runtime.settings.macro_mode = "mirror"
                    return True

                with (
                    patch("app.macros.direction.is_unity_window", return_value=True),
                    patch("app.macros.direction.is_dofus_unity_process", side_effect=probe),
                    patch("app.macros.direction.activate_window", side_effect=activate),
                    patch("app.macros.direction.foreground_window", side_effect=lambda: active[0]),
                    patch("app.macros.direction.press_key", side_effect=send) as sender,
                ):
                    DirectionMacro(runtime)._run("HOME")
                self.assertEqual(sender.call_count, count)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch deplacement %s: envoyes=%s/%s",
                    "interrompu", count, count,
                )


    def test_preferred_restore_rejects_late_mode_or_favorite_change(self):
        from app.macros.switch_character import SwitchCharacterMacro

        for count in (2, 4, 6, 8):
            for field, replacement in (("primary_handle", 303), ("macro_mode", "mirror")):
                with self.subTest(clients=count, field=field):
                    runtime = _runtime(count)
                    runtime.settings.primary_handle = 202
                    runtime.settings.macro_mode = "macro"
                    runtime.settings.preferred_client.return_value = (
                        SimpleNamespace(handle=202)
                    )
                    runtime.active_client_handle = 101
                    inspected = [0]

                    def process_probe(_hwnd):
                        inspected[0] += 1
                        if inspected[0] == 2:
                            setattr(runtime.settings, field, replacement)
                        return True

                    with (
                        patch("app.macros.switch_character.is_unity_window",
                              return_value=True),
                        patch("app.macros.switch_character.is_dofus_unity_process",
                              side_effect=process_probe),
                        patch("app.macros.switch_character.activate_window",
                              return_value=True) as focus,
                        patch("app.macros.switch_character.foreground_window",
                              return_value=202),
                    ):
                        SwitchCharacterMacro(runtime).restore_preferred_client(
                            "Auto groupe",
                        )
                    focus.assert_called_once()
                    self.assertEqual(runtime.active_client_handle, 101)
                    self.assertEqual(inspected[0], 2)

    def test_preferred_restore_rejects_mode_changed_during_activation(self):
        from app.macros.switch_character import SwitchCharacterMacro

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime(count)
                runtime.settings.primary_handle = 202
                runtime.settings.macro_mode = "macro"
                runtime.settings.preferred_client.return_value = (
                    SimpleNamespace(handle=202)
                )
                runtime.active_client_handle = 101

                def activate(*_args, **_kwargs):
                    runtime.settings.macro_mode = "mirror"
                    return True

                with (
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.switch_character.activate_window",
                          side_effect=activate) as focus,
                    patch("app.macros.switch_character.foreground_window") as foreground,
                ):
                    SwitchCharacterMacro(runtime).restore_preferred_client(
                        "Switch deplacement",
                    )
                focus.assert_called_once()
                foreground.assert_not_called()
                self.assertEqual(runtime.active_client_handle, 101)


    def test_character_hotkey_worker_refuses_stale_mode_or_favorite(self):
        from app.macros.switch_character import SwitchCharacterMacro

        for count in (2, 4, 6, 8):
            for field, replacement in (("primary_handle", 999), ("macro_mode", "mirror")):
                with self.subTest(clients=count, field=field):
                    runtime = _runtime(count)
                    runtime.settings.macro_mode = "macro"
                    runtime.settings.clients = [
                        SimpleNamespace(index=i + 1, handle=101 + i,
                                        display_name=f"Player{i + 1}")
                        for i in range(count)
                    ]
                    runtime.active_client_handle = 101

                    def spawn(_label, worker):
                        setattr(runtime.settings, field, replacement)
                        worker()
                        return True

                    runtime._spawn_macro.side_effect = spawn
                    with (
                        patch("app.macros.switch_character.is_unity_window",
                              side_effect=AssertionError("Stale hotkey reached Win32")),
                        patch("app.macros.switch_character.activate_window") as focus,
                    ):
                        self.assertTrue(
                            SwitchCharacterMacro(runtime).activate_by_index(1)
                        )
                    focus.assert_not_called()
                    self.assertEqual(runtime.active_client_handle, 101)

    def test_character_hotkey_focus_ignores_late_mode_or_favorite(self):
        from app.macros.switch_character import SwitchCharacterMacro

        for count in (2, 4, 6, 8):
            for field, replacement in (("primary_handle", 999), ("macro_mode", "mirror")):
                with self.subTest(clients=count, field=field):
                    runtime = _runtime(count)
                    runtime.settings.macro_mode = "macro"
                    runtime.settings.clients = [
                        SimpleNamespace(index=i + 1, handle=101 + i,
                                        display_name=f"Player{i + 1}")
                        for i in range(count)
                    ]
                    runtime.active_client_handle = 888

                    def spawn(_label, worker):
                        worker()
                        return True

                    def activate(*_args, **_kwargs):
                        setattr(runtime.settings, field, replacement)
                        return True

                    runtime._spawn_macro.side_effect = spawn
                    with (
                        patch("app.macros.switch_character.is_unity_window",
                              return_value=True),
                        patch("app.macros.switch_character.is_dofus_unity_process",
                              return_value=True),
                        patch("app.macros.switch_character.activate_window",
                              side_effect=activate) as focus,
                        patch("app.macros.switch_character.foreground_window") as foreground,
                    ):
                        self.assertTrue(
                            SwitchCharacterMacro(runtime).activate_by_index(1)
                        )
                    focus.assert_called_once()
                    foreground.assert_not_called()
                    self.assertEqual(runtime.active_client_handle, 888)


    def test_next_character_scan_rejects_mode_or_favorite_change(self):
        from app.macros.switch_character import SwitchCharacterMacro

        for count in (2, 4, 6, 8):
            for field, replacement in (("primary_handle", 999), ("macro_mode", "mirror")):
                with self.subTest(clients=count, field=field):
                    runtime = _runtime(count)
                    runtime.settings.macro_mode = "macro"
                    runtime.settings.clients = [
                        SimpleNamespace(index=i + 1, handle=101 + i,
                                        display_name=f"Player{i + 1}")
                        for i in range(count)
                    ]

                    def process_probe(_hwnd):
                        setattr(runtime.settings, field, replacement)
                        return True

                    macro = SwitchCharacterMacro(runtime)
                    with (
                        patch("app.macros.switch_character.is_unity_window",
                              return_value=True),
                        patch("app.macros.switch_character.is_dofus_unity_process",
                              side_effect=process_probe) as process,
                        patch.object(macro, "logical_active_client") as active,
                    ):
                        self.assertFalse(macro.activate_next())
                    process.assert_called_once()
                    active.assert_not_called()
                    runtime._spawn_macro.assert_not_called()

    def test_next_character_source_lookup_cannot_handoff_stale_action(self):
        from app.macros.switch_character import SwitchCharacterMacro

        for count in (2, 4, 6, 8):
            for field, replacement in (("primary_handle", 999), ("macro_mode", "mirror")):
                with self.subTest(clients=count, field=field):
                    runtime = _runtime(count)
                    runtime.settings.macro_mode = "macro"
                    runtime.settings.clients = [
                        SimpleNamespace(index=i + 1, handle=101 + i,
                                        display_name=f"Player{i + 1}")
                        for i in range(count)
                    ]

                    def source():
                        setattr(runtime.settings, field, replacement)
                        return runtime.settings.clients[0]

                    macro = SwitchCharacterMacro(runtime)
                    with (
                        patch("app.macros.switch_character.is_unity_window",
                              return_value=True),
                        patch("app.macros.switch_character.is_dofus_unity_process",
                              return_value=True),
                        patch.object(macro, "logical_active_client",
                                     side_effect=source) as active,
                        patch.object(macro, "activate_by_index") as dispatch,
                    ):
                        self.assertFalse(macro.activate_next())
                    active.assert_called_once()
                    dispatch.assert_not_called()
                    runtime._spawn_macro.assert_not_called()


if __name__ == "__main__":
    unittest.main()
