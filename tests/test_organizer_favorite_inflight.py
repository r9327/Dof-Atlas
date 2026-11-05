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


if __name__ == "__main__":
    unittest.main()
