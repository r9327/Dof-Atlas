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

    def test_preferred_client_rejects_inflight_favorite_or_mode_changes_2_to_8(self):
        for count in (2, 4, 6, 8):
            for change in ("favorite", "mode", "fallback_selection"):
                with self.subTest(clients=count, change=change):
                    runtime = _runtime()
                    clients = [SimpleNamespace(index=i + 1, handle=101 + i,
                                               primary=(i == 0))
                               for i in range(count)]
                    profile = SimpleNamespace(
                        clients=clients, primary_handle=101, macro_mode="macro",
                    )
                    if change == "fallback_selection":
                        profile.primary_handle = 0
                        profile.preferred_client = lambda: next(
                            (item for item in clients if item.primary), clients[0],
                        )
                    else:
                        profile.preferred_client = lambda: next(
                            (item for item in clients
                             if item.handle == profile.primary_handle), None,
                        )
                    runtime.settings = profile
                    macro = SwitchCharacterMacro(runtime)

                    def during_process_check(_hwnd):
                        if change == "favorite":
                            profile.primary_handle = clients[-1].handle
                        elif change == "mode":
                            profile.macro_mode = "mirror"
                        else:
                            clients[0].primary = False
                            clients[-1].primary = True
                        return True

                    with (
                        patch("app.macros.switch_character.is_unity_window", return_value=True),
                        patch("app.macros.switch_character.is_dofus_unity_process",
                              side_effect=during_process_check),
                    ):
                        self.assertIsNone(macro.preferred_client())
                    runtime._spawn_macro.assert_not_called()

    def test_preferred_client_still_accepts_unchanged_favorite_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [SimpleNamespace(index=i + 1, handle=101 + i)
                           for i in range(count)]
                profile = SimpleNamespace(
                    clients=clients, primary_handle=clients[-1].handle,
                    macro_mode="macro",
                )
                profile.preferred_client = lambda: clients[-1]
                runtime.settings = profile
                macro = SwitchCharacterMacro(runtime)
                with (
                    patch("app.macros.switch_character.is_unity_window", return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
                ):
                    self.assertIs(macro.preferred_client(), clients[-1])

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

    def test_roster_rejects_invalid_explicit_source_instead_of_favorite_fallback(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=101),
            SimpleNamespace(index=2, handle=202),
        ]
        macro = SwitchCharacterMacro(runtime)
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
            patch.object(macro, "logical_active_client") as fallback,
        ):
            for raw in (float("inf"), float("nan"), 101.9, 101.0, True,
                        -1, 2**64, "101", object()):
                with self.subTest(source=repr(raw)):
                    self.assertEqual(macro.ordered_clients_from_source(raw), [])
        fallback.assert_not_called()


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


    def test_roster_rejects_current_or_previous_hwnd_mutated_during_native_scan(self):
        for count in (2, 4, 6, 8):
            for mutation in ("current", "previous"):
                with self.subTest(clients=count, mutation=mutation):
                    runtime = _runtime()
                    clients = [
                        SimpleNamespace(index=i + 1, handle=101 + i)
                        for i in range(count)
                    ]
                    runtime.settings.clients = clients

                    def process_check(hwnd):
                        if (mutation == "current" and hwnd == 101
                                or mutation == "previous" and hwnd == 102):
                            clients[0].handle = 999
                        return True

                    macro = SwitchCharacterMacro(runtime)
                    with (
                        patch("app.macros.switch_character.is_unity_window",
                              return_value=True),
                        patch("app.macros.switch_character.is_dofus_unity_process",
                              side_effect=process_check) as process,
                        patch.object(macro, "logical_active_client") as fallback,
                    ):
                        self.assertEqual(
                            macro.ordered_clients_from_source(101), [],
                        )
                    self.assertEqual(process.call_count, 1 if mutation == "current" else 2)
                    fallback.assert_not_called()

    def test_next_character_never_dispatches_mutated_inplace_slot_2_to_8(self):
        for count in (2, 4, 6, 8):
            for mutation in ("current", "previous"):
                with self.subTest(clients=count, mutation=mutation):
                    runtime = _runtime()
                    clients = [
                        SimpleNamespace(index=i + 1, handle=101 + i,
                                        display_name=f"Player{i + 1}")
                        for i in range(count)
                    ]
                    runtime.settings.clients = clients

                    def process_check(hwnd):
                        if (mutation == "current" and hwnd == 101
                                or mutation == "previous" and hwnd == 102):
                            clients[0].handle = 999
                        return True

                    macro = SwitchCharacterMacro(runtime)
                    with (
                        patch("app.macros.switch_character.is_unity_window",
                              return_value=True),
                        patch("app.macros.switch_character.is_dofus_unity_process",
                              side_effect=process_check),
                        patch.object(macro, "activate_by_index") as activate,
                        patch.object(macro, "logical_active_client") as active,
                    ):
                        self.assertFalse(macro.activate_next())
                    activate.assert_not_called()
                    active.assert_not_called()
                    runtime._spawn_macro.assert_not_called()

    def test_roster_healthy_preserves_favorite_first_order_2_to_8(self):
        for count in (2, 4, 6, 8):
            for source_index in (0, count - 1):
                with self.subTest(clients=count, source_index=source_index):
                    runtime = _runtime()
                    clients = [
                        SimpleNamespace(index=i + 1, handle=101 + i)
                        for i in range(count)
                    ]
                    runtime.settings.clients = clients
                    source = clients[source_index].handle
                    with (
                        patch("app.macros.switch_character.is_unity_window",
                              return_value=True),
                        patch("app.macros.switch_character.is_dofus_unity_process",
                              return_value=True) as identity,
                    ):
                        result = SwitchCharacterMacro(runtime).ordered_clients_from_source(
                            source
                        )
                    expected = [clients[source_index]] + [
                        client for i, client in enumerate(clients)
                        if i != source_index
                    ]
                    self.assertEqual(result, expected)
                    self.assertEqual(identity.call_count, count)

    def test_next_character_rejects_identical_profile_reload_while_scanning(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i, display_name=str(i))
                    for i in range(count)
                ]
                runtime.settings.clients = clients
                original = runtime.settings

                def process_check(_hwnd):
                    # Simulates Organizer hot-reload during an expensive native
                    # verification of the first of 2/4/6/8 Unity clients.
                    replacement = Mock()
                    replacement.clients = clients
                    replacement.timings = original.timings
                    runtime.settings = replacement
                    return True

                macro = SwitchCharacterMacro(runtime)
                with (
                    patch("app.macros.switch_character.is_unity_window", return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          side_effect=process_check),
                    patch.object(macro, "activate_by_index") as activate,
                    patch.object(macro, "logical_active_client") as source,
                ):
                    self.assertFalse(macro.activate_next())
                activate.assert_not_called()
                source.assert_not_called()
                runtime._spawn_macro.assert_not_called()

    def test_next_character_dispatch_refuses_replaced_same_slot_profile(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i, display_name=str(i))
                    for i in range(count)
                ]
                runtime.settings.clients = clients
                original = runtime.settings
                new_profile = Mock()
                new_profile.clients = clients
                new_profile.timings = original.timings
                runtime.settings = new_profile
                self.assertFalse(SwitchCharacterMacro(runtime).activate_by_index(
                    2, expected_profile=original,
                ))
                runtime._spawn_macro.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Activation client annulée: profil Organizer remplacé avant dispatch.",
                )

    def test_next_character_nominal_wrap_after_final_slot_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i, display_name=str(i))
                    for i in range(count)
                ]
                runtime.settings.clients = clients
                runtime._spawn_macro.return_value = True
                macro = SwitchCharacterMacro(runtime)
                with (
                    patch("app.macros.switch_character.is_unity_window", return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
                    patch.object(macro, "logical_active_client", return_value=clients[-1]),
                ):
                    self.assertTrue(macro.activate_next())
                # The chosen character wraps to the first slot, but execution
                # still belongs to the original immutable Organizer profile.
                runtime._spawn_macro.assert_called_once()
                self.assertEqual(runtime._spawn_macro.call_args.args[0], "Activation client")


    def test_switch_worker_aborts_before_focus_if_native_identity_reloads_profile(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i, display_name=str(i))
                    for i in range(count)
                ]
                runtime.settings.clients = clients
                runtime._spawn_macro.return_value = True
                macro = SwitchCharacterMacro(runtime)
                self.assertTrue(macro.activate_by_index(2))
                worker = runtime._spawn_macro.call_args.args[1]
                old = runtime.settings
                def reload_at_identity(_hwnd):
                    newer = Mock()
                    newer.clients = clients
                    newer.timings = old.timings
                    runtime.settings = newer
                    return True
                with (
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          side_effect=reload_at_identity),
                    patch("app.macros.switch_character.activate_window") as activate,
                ):
                    worker()
                activate.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Activation client annulée: profil ou Stop changé après contrôle natif.",
                )

    def test_switch_roster_cannot_return_partial_clients_after_profile_reload(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i)
                    for i in range(count)
                ]
                runtime.settings.clients = clients
                old = runtime.settings
                macro = SwitchCharacterMacro(runtime)
                def reload_at_identity(_hwnd):
                    newer = Mock()
                    newer.clients = clients
                    runtime.settings = newer
                    return True
                with (
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          side_effect=reload_at_identity),
                    patch.object(macro, "logical_active_client") as fallback,
                ):
                    self.assertEqual(macro.ordered_clients_from_source(0), [])
                fallback.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch: roster abandonné, profil Organizer remplacé pendant scan.",
                )


    def test_switch_hotkey_refuses_corrupt_target_hwnd_before_spawning(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i, display_name=str(i))
                    for i in range(count)
                ]
                runtime.settings.clients = clients
                macro = SwitchCharacterMacro(runtime)
                for bad in (101.0, 101.9, True, False, 2**64, -1, "101"):
                    clients[0].handle = bad
                    with self.subTest(hwnd=repr(bad)):
                        self.assertFalse(macro.activate_by_index(1))
                runtime._spawn_macro.assert_not_called()
                clients[0].handle = 101
                runtime._spawn_macro.return_value = True
                self.assertTrue(macro.activate_by_index(1))
                runtime._spawn_macro.assert_called_once()

    def test_switch_hotkey_cannot_publish_old_client_after_final_win32_probe(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.active_client_handle = 101
                clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i, display_name=str(i))
                    for i in range(count)
                ]
                runtime.settings.clients = clients
                runtime._spawn_macro.return_value = True
                macro = SwitchCharacterMacro(runtime)
                self.assertTrue(macro.activate_by_index(2))
                worker = runtime._spawn_macro.call_args.args[1]
                original = runtime.settings
                calls = [0]

                def native_probe(_hwnd):
                    calls[0] += 1
                    if calls[0] == 2:
                        replacement = Mock()
                        replacement.clients = clients
                        replacement.timings = original.timings
                        runtime.settings = replacement
                    return True

                with (
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          side_effect=native_probe),
                    patch("app.macros.switch_character.activate_window",
                          return_value=True) as activate,
                    patch("app.macros.switch_character.foreground_window",
                          return_value=102),
                ):
                    worker()
                activate.assert_called_once()
                self.assertEqual(calls, [2])
                self.assertEqual(runtime.active_client_handle, 101)
                runtime.logger.info.assert_any_call(
                    "Activation client non publiée: profil ou Stop changé après contrôle final.",
                )

    def test_preferred_restore_never_publishes_stale_hwnd_after_final_probe(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.active_client_handle = 999
                preferred = SimpleNamespace(handle=101, display_name="favori")
                original = runtime.settings
                original.clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i)
                    for i in range(count)
                ]
                original.preferred_client.return_value = preferred
                runtime.macro_lock.should_stop.return_value = False
                macro = SwitchCharacterMacro(runtime)
                calls = [0]

                def native_probe(_hwnd):
                    calls[0] += 1
                    if calls[0] == 2:
                        replacement = Mock()
                        replacement.clients = original.clients
                        replacement.timings = original.timings
                        runtime.settings = replacement
                    return True

                with (
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          side_effect=native_probe),
                    patch("app.macros.switch_character.activate_window",
                          return_value=True),
                    patch("app.macros.switch_character.foreground_window",
                          return_value=101),
                ):
                    macro.restore_preferred_client("Switch clique")
                self.assertEqual(calls, [2])
                self.assertEqual(runtime.active_client_handle, 999)
                runtime.logger.info.assert_any_call(
                    "%s retour non publié: profil ou Stop changé après contrôle final.",
                    "Switch clique",
                )


    def test_logical_active_client_does_not_publish_stale_profile_after_win32_probe(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i, display_name=str(i))
                    for i in range(count)
                ]
                old = runtime.settings
                old.clients = clients
                old.client_by_handle.side_effect = (
                    lambda h: next((c for c in clients if c.handle == h), None)
                )
                runtime.active_client_handle = 999

                def reload_during_process_check(_hwnd):
                    newer = Mock()
                    newer.clients = clients
                    newer.timings = old.timings
                    runtime.settings = newer
                    return True

                with (
                    patch("app.macros.switch_character.foreground_window",
                          return_value=101),
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          side_effect=reload_during_process_check),
                ):
                    self.assertIsNone(SwitchCharacterMacro(runtime).logical_active_client())
                self.assertEqual(runtime.active_client_handle, 999)

    def test_preferred_lookup_does_not_return_old_favorite_after_native_reload(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                original = runtime.settings
                original.clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i, display_name=str(i))
                    for i in range(count)
                ]
                original.preferred_client.return_value = original.clients[0]

                def reload_during_process_check(_hwnd):
                    newer = Mock()
                    newer.clients = original.clients
                    newer.preferred_client.return_value = original.clients[-1]
                    runtime.settings = newer
                    return True

                with (
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          side_effect=reload_during_process_check),
                ):
                    self.assertIsNone(SwitchCharacterMacro(runtime).preferred_client())
                self.assertIsNot(runtime.settings, original)

    def test_favorite_probe_rejects_inplace_hwnd_mutation_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i,
                                    display_name=str(i + 1))
                    for i in range(count)
                ]
                runtime.settings.clients = clients
                favorite = clients[-1]
                accepted_hwnd = favorite.handle
                runtime.settings.preferred_client.return_value = favorite

                def process_check(hwnd):
                    self.assertEqual(hwnd, accepted_hwnd)
                    favorite.handle = 999
                    return True

                with (
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True) as unity,
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          side_effect=process_check) as process,
                ):
                    self.assertIsNone(SwitchCharacterMacro(runtime).preferred_client())
                unity.assert_called_once_with(accepted_hwnd)
                process.assert_called_once_with(accepted_hwnd)

    def test_logical_foreground_rejects_session_mutated_during_lookup(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i)
                    for i in range(count)
                ]
                runtime.settings.clients = clients
                runtime.active_client_handle = 0

                def lookup(hwnd):
                    self.assertEqual(hwnd, 101)
                    clients[0].handle = 999
                    return clients[0]

                runtime.settings.client_by_handle.side_effect = lookup
                with (
                    patch("app.macros.switch_character.foreground_window",
                          return_value=101),
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          return_value=True),
                ):
                    self.assertIsNone(
                        SwitchCharacterMacro(runtime).logical_active_client()
                    )
                self.assertEqual(runtime.active_client_handle, 0)

    def test_logical_remembered_rejects_hwnd_changed_during_process_check(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i)
                    for i in range(count)
                ]
                runtime.settings.clients = clients
                runtime.settings.client_by_handle.return_value = clients[0]
                runtime.active_client_handle = 101

                def process_check(hwnd):
                    self.assertEqual(hwnd, 101)
                    clients[0].handle = 999
                    return True

                with (
                    patch("app.macros.switch_character.foreground_window",
                          return_value=0),
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True) as unity,
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          side_effect=process_check) as process,
                ):
                    self.assertIsNone(
                        SwitchCharacterMacro(runtime).logical_active_client()
                    )
                unity.assert_called_once_with(101)
                process.assert_called_once_with(101)
                self.assertEqual(runtime.active_client_handle, 101)

    def test_logical_fallback_rejects_mutated_handle_after_native_probe(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i)
                    for i in range(count)
                ]
                runtime.settings.clients = clients
                runtime.settings.preferred_client.return_value = None
                runtime.active_client_handle = 0

                def process_check(hwnd):
                    self.assertEqual(hwnd, 101)
                    clients[0].handle = 999
                    return True

                with (
                    patch("app.macros.switch_character.foreground_window",
                          return_value=0),
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True) as unity,
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          side_effect=process_check) as process,
                ):
                    self.assertIsNone(
                        SwitchCharacterMacro(runtime).logical_active_client()
                    )
                unity.assert_called_once_with(101)
                process.assert_called_once_with(101)
                self.assertEqual(runtime.active_client_handle, 0)

    def test_logical_rejects_invalid_physical_and_remembered_hwnd_before_win32(self):
        for invalid in (None, True, 101.5, "101", float("inf"), -1, 2**64):
            with self.subTest(hwnd=repr(invalid)):
                runtime = _runtime()
                runtime.active_client_handle = invalid
                runtime.settings.clients = []
                runtime.settings.preferred_client.return_value = None
                with (
                    patch("app.macros.switch_character.foreground_window",
                          return_value=invalid),
                    patch("app.macros.switch_character.is_unity_window") as unity,
                    patch("app.macros.switch_character.is_dofus_unity_process") as process,
                ):
                    self.assertIsNone(
                        SwitchCharacterMacro(runtime).logical_active_client()
                    )
                unity.assert_not_called()
                process.assert_not_called()

    def test_character_hotkey_rejects_fractional_slot_without_spawning(self) -> None:
        runtime = _runtime()
        runtime.settings.clients = [
            SimpleNamespace(index=1, handle=101, display_name="Friend"),
        ]
        macro = SwitchCharacterMacro(runtime)
        from decimal import Decimal
        from fractions import Fraction

        for malformed in (
            True, 1.9, 1.0, float("nan"), float("inf"),
            Fraction(3, 2), Decimal("1.9"), complex(1, 0),
        ):
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


    def test_auto_group_never_truncates_corrupt_hwnd_into_sender_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.macro_lock.wait.return_value = False
                runtime.settings.timings.auto_group_invite_gap_ms = 0
                runtime.switch_character.logical_active_client.return_value = (
                    SimpleNamespace(handle=101, display_name="Leader")
                )
                invalid_hwnds = [
                    101.9, 101.0, True, False, float("nan"), float("inf"),
                    2**64, -1, object(),
                ]
                entries = [
                    {"name": "Leader", "handle": 101},
                    *(
                        {"name": f"Friend{i}", "handle": invalid_hwnds[i]}
                        for i in range(count - 1)
                    ),
                    # A valid old textual HWND must still identify the sender
                    # even when a corrupted name differs from the leader's.
                    {"name": "FakeLeader", "handle": " 101 "},
                ]
                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.auto_group.activate_window",
                          return_value=True) as activate,
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command",
                          return_value=True) as send,
                ):
                    AutoGroupMacro(runtime)._run(entries)
                activate.assert_called_once()
                self.assertEqual(
                    [c.args[0] for c in send.call_args_list],
                    [f"/invite Friend{i}" for i in range(count - 1)],
                )
                runtime.logger.info.assert_any_call(
                    "Auto groupe préparé: invitations=%s doublons=%s lanceur=%s vides=%s",
                    count - 1, 0, 2, 0,
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
        runtime.macro_lock.active_label = ""
        runtime.auto_group.run_async.return_value = False
        with patch("app.core.runtime_state.load_settings", return_value=runtime.settings):
            self.assertFalse(AtlasRuntime.launch_auto_group(
                runtime, [{"name": "Friend", "handle": 202}]
            ))
        runtime.auto_group.run_async.assert_called_once()


    def test_busy_quick_actions_do_not_replace_worker_generation_2_to_8(self):
        from app.core.runtime_state import AtlasRuntime

        for count in (2, 4, 6, 8):
            for busy in ("Miroir clavier", "Miroir molette", "Switch clique",
                         "Auto zaap", "Auto groupe"):
                for action in ("zaap", "auto_group"):
                    with self.subTest(clients=count, busy=busy, action=action):
                        runtime = _runtime()
                        runtime.settings.clients = [
                            SimpleNamespace(handle=101 + i) for i in range(count)
                        ]
                        runtime.macro_lock.active_label = busy
                        captured = runtime.settings
                        with patch("app.core.runtime_state.load_settings") as load:
                            if action == "zaap":
                                result = AtlasRuntime.launch_zaap(
                                    runtime, "/zaap 1,2",
                                )
                            else:
                                result = AtlasRuntime.launch_auto_group(
                                    runtime, [{"name": "Friend", "handle": 202}],
                                )
                        self.assertFalse(result)
                        load.assert_not_called()
                        self.assertIs(runtime.settings, captured)
                        runtime.zaap.run_async.assert_not_called()
                        runtime.auto_group.run_async.assert_not_called()
                        runtime._spawn_macro.assert_not_called()

    def test_idle_quick_actions_keep_existing_runtime_contract(self):
        from app.core.runtime_state import AtlasRuntime

        for count in (2, 4, 6, 8):
            for action in ("zaap", "auto_group"):
                with self.subTest(clients=count, action=action):
                    runtime = _runtime()
                    runtime.macro_lock.active_label = ""
                    loaded = Mock()
                    loaded.clients = [
                        SimpleNamespace(handle=101 + i) for i in range(count)
                    ]
                    runtime.zaap.run_async.return_value = True
                    runtime.auto_group.run_async.return_value = True
                    with patch("app.core.runtime_state.load_settings",
                               return_value=loaded) as load:
                        if action == "zaap":
                            self.assertTrue(AtlasRuntime.launch_zaap(
                                runtime, "/zaap 1,2",
                            ))
                            runtime.zaap.run_async.assert_called_once_with(
                                "/zaap 1,2", click_position=None,
                                click_ratios=None,
                            )
                        else:
                            self.assertTrue(AtlasRuntime.launch_auto_group(
                                runtime, [{"name": "Friend", "handle": 202}],
                            ))
                            runtime.auto_group.run_async.assert_called_once()
                    load.assert_called_once_with()
                    self.assertIs(runtime.settings, loaded)

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
            expected_profile=runtime.settings,
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


    def test_native_source_release_never_replays_after_profile_replacement(self):
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
        runtime.switch_click._capture_trigger_context.return_value = (
            SwitchClickContext(101, 25, 30, 0.2, 0.3, "cursor")
        )
        with (
            patch("app.windows.unity_windows.find_known_client_from_point",
                  return_value=101),
            patch("app.windows.unity_windows.foreground_window",
                  return_value=101),
            patch("app.macros.mirror_plan.is_dofus_unity_process",
                  return_value=True),
        ):
            self.assertFalse(AtlasRuntime._handle_mouse_click(
                runtime, "Left", 150, 160,
            ))
            self.assertEqual(len(runtime._pending_physical_switch), 8)
            # The new roster happens to retain the same HWNDs. Identity,
            # not equality of the visible slots, must cancel this replay.
            prior = runtime.settings
            runtime.settings = Mock()
            runtime.settings.macro_mode = prior.macro_mode
            runtime.settings.clients = prior.clients
            self.assertTrue(AtlasRuntime._handle_mouse_release(
                runtime, "Left", 150, 160,
            ))
        runtime.switch_click.run_async.assert_not_called()
        runtime.logger.debug.assert_any_call(
            "Clic natif non recopié: cause=%s button=%s",
            "profile_replaced", "Left",
        )

    def test_native_click_profile_reload_during_capture_preserves_physical_down(self):
        from app.core.runtime_state import AtlasRuntime
        from app.macros.switch_click import SwitchClickContext

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime._pending_physical_switch = None
                runtime._running = True
                runtime._admin_ok = True
                runtime.macro_lock.active_label = ""
                runtime.settings.macro_mode = "macro"
                runtime.settings.clients = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]
                runtime.registry.switch_action_for_pressed_keys.return_value = SimpleNamespace(
                    action_id="switch_click",
                    payload={"click_count": 1, "label": "Switch clique"},
                )
                def capture(*_args):
                    replacement = Mock()
                    replacement.macro_mode = "macro"
                    replacement.clients = runtime.settings.clients
                    runtime.settings = replacement
                    return SwitchClickContext(101, 25, 30, 0.2, 0.3, "cursor")

                runtime.switch_click._capture_trigger_context.side_effect = capture
                with (
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          return_value=101),
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=101),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=True),
                ):
                    self.assertFalse(AtlasRuntime._handle_mouse_click(
                        runtime, "Left", 150, 160,
                    ))
                runtime.switch_click.run_async.assert_not_called()
                self.assertIsNone(runtime._pending_physical_switch)
                runtime.logger.debug.assert_any_call(
                    "Clic natif non recopié: cause=profile_changed_during_capture"
                )

    def test_settings_replacement_clears_native_replay_before_release(self):
        import threading
        from app.core.runtime_state import AtlasRuntime

        # The actual property setter owns the generation transition.
        runtime = AtlasRuntime.__new__(AtlasRuntime)
        runtime._settings_lock = threading.RLock()
        runtime._settings = object()
        runtime._pending_physical_switch = ("pending",)
        replacement = object()
        AtlasRuntime.settings.fset(runtime, replacement)
        self.assertIs(runtime.settings, replacement)
        self.assertIsNone(runtime._pending_physical_switch)

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
            expected_profile=runtime.settings,
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

    def test_native_source_release_preserves_up_after_probe_profile_reload(self):
        from time import monotonic
        from app.core.runtime_state import AtlasRuntime
        from app.macros.switch_click import SwitchClickContext

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime._running = True
                runtime._admin_ok = True
                runtime.settings.macro_mode = "macro"
                runtime.settings.clients = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]
                runtime.macro_lock.active_label = ""
                old = runtime.settings
                runtime._pending_physical_switch = (
                    "Left", 20, 40, 1, "Switch clique",
                    SwitchClickContext(101, 12, 18, 0.5, 0.5, "cursor"),
                    monotonic(), old,
                )
                def reload_at_identity(_hwnd):
                    runtime.settings = Mock()
                    runtime.settings.macro_mode = "macro"
                    runtime.settings.clients = old.clients
                    return True
                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=101),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          side_effect=reload_at_identity),
                ):
                    self.assertTrue(AtlasRuntime._handle_mouse_release(
                        runtime, "Left", 20, 40,
                    ))
                runtime.switch_click.run_async.assert_not_called()
                runtime.logger.debug.assert_any_call(
                    "Clic natif non recopié: cause=%s button=%s",
                    "profile_replaced", "Left",
                )

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

    def test_switch_hotkey_rejects_in_place_session_mutation_2_to_8(self):
        # The existing client record itself can be modified in place while
        # the hotkey worker is queued; the accepted HWND/index must be frozen.
        for count in (2, 4, 6, 8):
            for changed in ("handle", "index"):
                with self.subTest(clients=count, changed=changed):
                    runtime = _runtime()
                    runtime.settings.clients = [
                        SimpleNamespace(index=i + 1, handle=101 + i,
                                        display_name=f"Client {i + 1}")
                        for i in range(count)
                    ]
                    runtime._spawn_macro.return_value = True
                    macro = SwitchCharacterMacro(runtime)
                    self.assertTrue(macro.activate_by_index(count))
                    worker = runtime._spawn_macro.call_args.args[1]
                    runtime.active_client_handle = 101
                    selected = runtime.settings.clients[-1]
                    if changed == "handle":
                        selected.handle = 999
                    else:
                        selected.index = 99
                    with (
                        patch("app.macros.switch_character.is_unity_window") as unity,
                        patch("app.macros.switch_character.is_dofus_unity_process") as identity,
                        patch("app.macros.switch_character.activate_window") as activate,
                    ):
                        worker()
                    unity.assert_not_called()
                    identity.assert_not_called()
                    activate.assert_not_called()
                    self.assertEqual(runtime.active_client_handle, 101)
                    runtime.logger.info.assert_any_call(
                        "Activation client annulée: slot modifié index=%s", count,
                    )

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

    def test_queued_character_activation_cancel_callback_sees_inplace_slot_change(self):
        for count in (2, 4, 6, 8):
            for changed in ("index", "handle"):
                with self.subTest(clients=count, changed=changed):
                    runtime = _runtime()
                    selected = SimpleNamespace(
                        index=count, handle=100 + count, display_name="Target",
                    )
                    runtime.settings.clients = [
                        SimpleNamespace(index=i, handle=100 + i, display_name=str(i))
                        for i in range(1, count)
                    ] + [selected]
                    runtime.active_client_handle = 101
                    runtime._spawn_macro.return_value = True
                    macro = SwitchCharacterMacro(runtime)
                    self.assertTrue(macro.activate_by_index(count))
                    worker = runtime._spawn_macro.call_args.args[1]

                    def mutate_during_activation(_hwnd, *_args, **kwargs):
                        if changed == "handle":
                            selected.handle = 999
                        else:
                            selected.index = 99
                        self.assertTrue(kwargs["should_stop"]())
                        return False

                    with (
                        patch("app.macros.switch_character.is_unity_window",
                              return_value=True),
                        patch("app.macros.switch_character.is_dofus_unity_process",
                              return_value=True),
                        patch("app.macros.switch_character.activate_window",
                              side_effect=mutate_during_activation) as focus,
                        patch("app.macros.switch_character.foreground_window") as foreground,
                    ):
                        worker()
                    focus.assert_called_once()
                    foreground.assert_not_called()
                    self.assertEqual(runtime.active_client_handle, 101)

    def test_favorite_restore_freezes_hwnd_through_native_activation_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.active_client_handle = 101
                runtime.settings.clients = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]
                favorite = runtime.settings.clients[-1]
                runtime.settings.preferred_client.return_value = favorite

                def mutate_during_activation(hwnd, *_args, **kwargs):
                    self.assertEqual(hwnd, 100 + count)
                    favorite.handle = 999
                    self.assertTrue(kwargs["should_stop"]())
                    return True

                with (
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.switch_character.activate_window",
                          side_effect=mutate_during_activation) as focus,
                    patch("app.macros.switch_character.foreground_window") as foreground,
                ):
                    SwitchCharacterMacro(runtime).restore_preferred_client("Miroir")
                focus.assert_called_once()
                foreground.assert_not_called()
                self.assertEqual(runtime.active_client_handle, 101)
                runtime.logger.info.assert_any_call(
                    "%s retour non publié: favori modifié.", "Miroir",
                )

    def test_invalid_favorite_handle_never_reaches_native_helpers_2_to_8(self):
        for count in (2, 4, 6, 8):
            for invalid in (None, True, "101", 101.5, float("inf"), 0, -1, 2**64):
                with self.subTest(clients=count, hwnd=repr(invalid)):
                    runtime = _runtime()
                    runtime.settings.clients = [
                        SimpleNamespace(handle=101 + i) for i in range(count)
                    ]
                    runtime.settings.preferred_client.return_value = (
                        SimpleNamespace(handle=invalid)
                    )
                    with (
                        patch("app.macros.switch_character.is_unity_window") as unity,
                        patch("app.macros.switch_character.is_dofus_unity_process") as process,
                    ):
                        self.assertIsNone(SwitchCharacterMacro(runtime).preferred_client())
                    unity.assert_not_called()
                    process.assert_not_called()

    def test_logical_active_skips_corrupt_roster_before_win32_probe(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                invalids = (True, 101.5, "101", float("inf"), 2**64)
                valid = SimpleNamespace(index=count, handle=303, display_name="Real")
                runtime.settings.clients = [
                    SimpleNamespace(index=i + 1, handle=invalids[i % len(invalids)])
                    for i in range(count - 1)
                ] + [valid]
                runtime.settings.client_by_handle.return_value = None
                runtime.active_client_handle = 0
                runtime.settings.preferred_client.return_value = None
                with (
                    patch("app.macros.switch_character.foreground_window", return_value=0),
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True) as unity,
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          return_value=True) as process,
                ):
                    self.assertIs(
                        SwitchCharacterMacro(runtime).logical_active_client(), valid,
                    )
                unity.assert_called_once_with(303)
                process.assert_called_once_with(303)

    def test_favorite_restore_rejects_non_integer_hwnd_before_native_focus(self):
        for invalid in (True, 202.5, "202", 0, -3, 2**64):
            with self.subTest(hwnd=repr(invalid)):
                runtime = _runtime()
                runtime.settings.preferred_client.return_value = (
                    SimpleNamespace(handle=invalid)
                )
                with (
                    patch("app.macros.switch_character.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.switch_character.activate_window") as focus,
                ):
                    SwitchCharacterMacro(runtime).restore_preferred_client("Miroir")
                focus.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "%s retour ignore: favori/premier indisponible.", "Miroir",
                )

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

    def test_direction_refused_foreign_hotkey_never_sends_unowned_keyups(self):
        for count in (2, 4, 6, 8):
            for reason in ("foreign_window", "foreign_process",
                           "not_in_organizer", "profile_reload"):
                with self.subTest(clients=count, reason=reason):
                    runtime = _runtime()
                    runtime.settings.clients = [
                        SimpleNamespace(handle=101 + i) for i in range(count)
                    ]
                    runtime.settings.client_by_handle.return_value = (
                        None if reason == "not_in_organizer" else object()
                    )
                    macro = DirectionMacro(runtime)

                    def native_process(_hwnd):
                        if reason == "profile_reload":
                            runtime.settings = Mock()
                        return reason != "foreign_process"

                    with (
                        patch("app.macros.direction.foreground_window",
                              return_value=999 if reason == "foreign_window" else 101),
                        patch("app.macros.direction.is_unity_window",
                              return_value=reason != "foreign_window"),
                        patch("app.macros.direction.is_dofus_unity_process",
                              side_effect=native_process),
                        patch("app.macros.direction.activate_window") as focus,
                        patch("app.macros.direction.press_key") as press,
                        patch("app.macros.direction.key_up") as release,
                        patch.object(macro, "release_virtual_inputs") as emergency_release,
                    ):
                        macro._run("HOME")
                    focus.assert_not_called()
                    press.assert_not_called()
                    release.assert_not_called()
                    emergency_release.assert_not_called()
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    runtime.logger.info.assert_any_call(
                        "Switch deplacement ignore: fenetre active non Unity."
                    )

    def test_direction_explicit_emergency_release_remains_available(self):
        runtime = _runtime()
        macro = DirectionMacro(runtime)
        with (
            patch("app.macros.direction._vk", side_effect=lambda name: len(name)),
            patch("app.macros.direction.key_up") as release,
        ):
            macro.release_virtual_inputs()
        self.assertEqual(release.call_count, 4)

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


    def test_direction_no_successful_activation_cannot_restore_favorite_2_to_8(self) -> None:
        # An activation refusal must not steal the user's focus merely
        # because a valid DOFUS source was present at dispatch time.
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.settings.client_by_handle.return_value = object()
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]
                with (
                    patch("app.macros.direction.foreground_window", return_value=101),
                    patch("app.macros.direction.is_unity_window", return_value=True),
                    patch("app.macros.direction.is_dofus_unity_process", return_value=True),
                    patch("app.macros.direction.activate_window", return_value=False),
                    patch("app.macros.direction.press_key") as send,
                ):
                    DirectionMacro(runtime)._run("HOME")
                send.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch deplacement %s: envoyes=%s/%s", "partiel", 0, count,
                )

    def test_zaap_no_successful_activation_cannot_restore_favorite_2_to_8(self) -> None:
        # Refused focus does not authorize a gratuitous preferred-client
        # activation after the attempted /zaap broadcast.
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]
                with (
                    patch("app.macros.zaap.is_unity_window", return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                    patch("app.macros.zaap.activate_window", return_value=False),
                    patch("app.macros.zaap.send_chat_command") as send,
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                send.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime._emit_status.assert_called_once_with(
                    f"Auto zaap partiel : 0/{count} commandes émises "
                    "(réception DOFUS non vérifiée)."
                )

    def test_direction_empty_roster_never_restores_or_emits(self) -> None:
        runtime = _runtime()
        runtime.settings.client_by_handle.return_value = object()
        runtime.switch_character.ordered_clients_from_source.return_value = []
        with (
            patch("app.macros.direction.foreground_window", return_value=101),
            patch("app.macros.direction.is_unity_window", return_value=True),
            patch("app.macros.direction.is_dofus_unity_process", return_value=True),
            patch("app.macros.direction.activate_window") as activate,
            patch("app.macros.direction.press_key") as send,
        ):
            DirectionMacro(runtime)._run("HOME")
        activate.assert_not_called()
        send.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()


    def test_direction_rejects_outdated_hotkey_before_starting_worker_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                old = runtime.settings
                newer = Mock()
                newer.clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i)
                    for i in range(count)
                ]
                runtime.settings = newer
                self.assertFalse(
                    DirectionMacro(runtime).run_async(
                        "HOME", expected_profile=old,
                    )
                )
                runtime._spawn_macro.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch deplacement annulé: profil Organizer remplacé avant dispatch.",
                )


    def test_zaap_in_place_hwnd_change_never_sends_or_restores_2_to_8(self):
        for count in (2, 4, 6, 8):
            for phase in ("activate", "chat"):
                with self.subTest(clients=count, phase=phase):
                    runtime = _runtime()
                    clients = [
                        SimpleNamespace(handle=101 + index) for index in range(count)
                    ]
                    runtime.switch_character.ordered_clients_from_source.return_value = clients
                    runtime.macro_lock.should_stop.return_value = False
                    runtime.settings.primary_handle = 101
                    calls = []

                    def activate(*_args, **_kwargs):
                        if phase == "activate":
                            clients[0].handle = 999
                        return True

                    def chat(command, logger, **kwargs):
                        calls.append(command)
                        clients[0].handle = 999
                        self.assertTrue(kwargs["should_stop"]())
                        return False

                    with (
                        patch("app.macros.zaap.is_unity_window", return_value=True),
                        patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                        patch("app.macros.zaap.activate_window",
                              side_effect=activate) as focus,
                        patch("app.macros.zaap.foreground_window", return_value=101),
                        patch("app.macros.zaap.send_chat_command",
                              side_effect=chat) as send,
                    ):
                        ZaapMacro(runtime)._run("/zaap 1,2")
                    focus.assert_called_once()
                    self.assertEqual(send.call_count, int(phase == "chat"))
                    self.assertEqual(calls, ["/zaap 1,2"] if phase == "chat" else [])
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    runtime._emit_status.assert_called_once_with(
                        f"Auto zaap interrompu : 0/{count} commandes émises "
                        "(réception DOFUS non vérifiée)."
                    )

    def test_direction_in_place_hwnd_change_prevents_keypress_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                clients = [
                    SimpleNamespace(handle=101 + index) for index in range(count)
                ]
                runtime.switch_character.ordered_clients_from_source.return_value = clients
                runtime.settings.client_by_handle.return_value = clients[0]
                runtime.macro_lock.should_stop.return_value = False

                def activate(*_args, **_kwargs):
                    clients[0].handle = 999
                    return True

                with (
                    patch("app.macros.direction.foreground_window", return_value=101),
                    patch("app.macros.direction.is_unity_window", return_value=True),
                    patch("app.macros.direction.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.direction.activate_window",
                          side_effect=activate) as focus,
                    patch("app.macros.direction.press_key") as key,
                ):
                    DirectionMacro(runtime)._run("HOME")
                focus.assert_called_once()
                key.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch deplacement %s: envoyes=%s/%s",
                    "interrompu", 0, count,
                )

    def test_auto_group_in_place_sender_change_never_invites_new_hwnd(self):
        for count in (2, 4, 6, 8):
            for phase in ("activate", "chat"):
                with self.subTest(clients=count, phase=phase):
                    runtime = _runtime()
                    runtime.macro_lock.should_stop.return_value = False
                    runtime.settings.timings.auto_group_invite_gap_ms = 0
                    sender = SimpleNamespace(handle=101, display_name="Leader")
                    runtime.switch_character.logical_active_client.return_value = sender
                    recipients = [
                        {"name": f"Friend{index}", "handle": 101 + index}
                        for index in range(1, count)
                    ]

                    def activate(*_args, **_kwargs):
                        if phase == "activate":
                            sender.handle = 999
                        return True

                    def chat(command, logger, **kwargs):
                        sender.handle = 999
                        self.assertTrue(kwargs["should_stop"]())
                        return False

                    with (
                        patch("app.macros.auto_group.is_unity_window", return_value=True),
                        patch("app.macros.auto_group.is_dofus_unity_process",
                              return_value=True),
                        patch("app.macros.auto_group.activate_window",
                              side_effect=activate) as focus,
                        patch("app.macros.auto_group.foreground_window",
                              return_value=101),
                        patch("app.macros.auto_group.send_chat_command",
                              side_effect=chat) as send,
                    ):
                        AutoGroupMacro(runtime)._run(recipients)
                    focus.assert_called_once()
                    self.assertEqual(send.call_count, int(phase == "chat"))
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    runtime._emit_status.assert_called_once_with(
                        f"Auto-groupe interrompu : 0/{count - 1} commandes émises "
                        "(réception DOFUS non vérifiée)."
                    )


    def test_successful_send_then_hwnd_reassignment_stays_interrupted_2_to_8(self):
        for count in (2, 4, 6, 8):
            for kind in ("zaap", "auto_group", "direction"):
                with self.subTest(clients=count, macro=kind):
                    runtime = _runtime()
                    runtime.macro_lock.should_stop.return_value = False
                    runtime.settings.timings.auto_group_invite_gap_ms = 0
                    clients = [
                        SimpleNamespace(handle=101 + i, index=i + 1,
                                        display_name=f"Client{i + 1}")
                        for i in range(count)
                    ]
                    sender = clients[0]
                    runtime.settings.primary_handle = 101
                    runtime.settings.client_by_handle.return_value = sender
                    runtime.switch_character.logical_active_client.return_value = sender
                    runtime.switch_character.ordered_clients_from_source.return_value = clients
                    sent = []

                    def chat(command, logger, **_kwargs):
                        sent.append(command)
                        sender.handle = 999
                        return True

                    def key(name, hold):
                        sent.append(name)
                        sender.handle = 999

                    with (
                        patch("app.macros.zaap.is_unity_window", return_value=True),
                        patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                        patch("app.macros.zaap.activate_window",
                              return_value=True) as zaap_focus,
                        patch("app.macros.zaap.foreground_window", return_value=101),
                        patch("app.macros.zaap.send_chat_command",
                              side_effect=chat) as zaap_send,
                        patch("app.macros.auto_group.is_unity_window", return_value=True),
                        patch("app.macros.auto_group.is_dofus_unity_process",
                              return_value=True),
                        patch("app.macros.auto_group.activate_window",
                              return_value=True) as group_focus,
                        patch("app.macros.auto_group.foreground_window",
                              return_value=101),
                        patch("app.macros.auto_group.send_chat_command",
                              side_effect=chat) as group_send,
                        patch("app.macros.direction.is_unity_window", return_value=True),
                        patch("app.macros.direction.is_dofus_unity_process",
                              return_value=True),
                        patch("app.macros.direction.activate_window",
                              return_value=True) as direction_focus,
                        patch("app.macros.direction.foreground_window",
                              return_value=101),
                        patch("app.macros.direction.press_key", side_effect=key) as key_send,
                    ):
                        if kind == "zaap":
                            ZaapMacro(runtime)._run("/zaap 1,2")
                            zaap_focus.assert_called_once()
                            zaap_send.assert_called_once()
                            runtime._emit_status.assert_called_once_with(
                                f"Auto zaap interrompu : 1/{count} commandes émises "
                                "(réception DOFUS non vérifiée)."
                            )
                        elif kind == "auto_group":
                            AutoGroupMacro(runtime)._run([
                                {"name": f"Friend{i}", "handle": 101 + i}
                                for i in range(1, count)
                            ])
                            group_focus.assert_called_once()
                            group_send.assert_called_once()
                            runtime._emit_status.assert_called_once_with(
                                f"Auto-groupe interrompu : 1/{count - 1} commandes émises "
                                "(réception DOFUS non vérifiée)."
                            )
                        else:
                            DirectionMacro(runtime)._run("HOME")
                            direction_focus.assert_called_once()
                            key_send.assert_called_once()
                            runtime.logger.info.assert_any_call(
                                "Switch deplacement %s: envoyes=%s/%s",
                                "interrompu", 1, count,
                            )
                    self.assertEqual(len(sent), 1)
                    runtime.switch_character.restore_preferred_client.assert_not_called()


    def test_frozen_roster_stops_on_failed_activation_with_mutated_hwnd(self):
        for count in (2, 4, 6, 8):
            for kind in ("zaap", "direction"):
                with self.subTest(clients=count, kind=kind):
                    runtime = _runtime()
                    clients = [
                        SimpleNamespace(handle=101 + i) for i in range(count)
                    ]
                    runtime.settings.primary_handle = 101
                    runtime.macro_lock.should_stop.return_value = False
                    runtime.switch_character.ordered_clients_from_source.return_value = clients
                    runtime.settings.client_by_handle.return_value = clients[0]

                    def activate(*_args, **_kwargs):
                        clients[0].handle = 999
                        return False

                    if kind == "zaap":
                        with (
                            patch("app.macros.zaap.is_unity_window",
                                  return_value=True),
                            patch("app.macros.zaap.is_dofus_unity_process",
                                  return_value=True),
                            patch("app.macros.zaap.activate_window",
                                  side_effect=activate) as focus,
                            patch("app.macros.zaap.foreground_window",
                                  return_value=101),
                            patch("app.macros.zaap.send_chat_command") as chat,
                        ):
                            ZaapMacro(runtime)._run("/zaap 1,2")
                        chat.assert_not_called()
                        runtime._emit_status.assert_called_once_with(
                            f"Auto zaap interrompu : 0/{count} commandes émises "
                            "(réception DOFUS non vérifiée)."
                        )
                    else:
                        with (
                            patch("app.macros.direction.foreground_window",
                                  return_value=101),
                            patch("app.macros.direction.is_unity_window",
                                  return_value=True),
                            patch("app.macros.direction.is_dofus_unity_process",
                                  return_value=True),
                            patch("app.macros.direction.activate_window",
                                  side_effect=activate) as focus,
                            patch("app.macros.direction.press_key") as press,
                        ):
                            DirectionMacro(runtime)._run("HOME")
                        press.assert_not_called()
                        runtime.logger.info.assert_any_call(
                            "Switch deplacement %s: envoyes=%s/%s",
                            "interrompu", 0, count,
                        )
                    focus.assert_called_once()
                    runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_frozen_roster_stops_if_previous_client_mutates_during_next_focus(self):
        for count in (2, 4, 6, 8):
            for kind in ("zaap", "direction"):
                with self.subTest(clients=count, kind=kind):
                    runtime = _runtime()
                    clients = [
                        SimpleNamespace(handle=101 + i) for i in range(count)
                    ]
                    runtime.settings.primary_handle = 101
                    runtime.macro_lock.should_stop.return_value = False
                    runtime.switch_character.ordered_clients_from_source.return_value = clients
                    runtime.settings.client_by_handle.return_value = clients[0]
                    activations = []

                    def activate(hwnd, *_args, **_kwargs):
                        activations.append(hwnd)
                        if hwnd == 102:
                            clients[0].handle = 999
                        return True

                    if kind == "zaap":
                        with (
                            patch("app.macros.zaap.is_unity_window",
                                  return_value=True),
                            patch("app.macros.zaap.is_dofus_unity_process",
                                  return_value=True),
                            patch("app.macros.zaap.activate_window",
                                  side_effect=activate),
                            patch("app.macros.zaap.foreground_window",
                                  side_effect=lambda: activations[-1]),
                            patch("app.macros.zaap.send_chat_command",
                                  return_value=True) as chat,
                        ):
                            ZaapMacro(runtime)._run("/zaap 1,2")
                        chat.assert_called_once()
                        runtime._emit_status.assert_called_once_with(
                            f"Auto zaap interrompu : 1/{count} commandes émises "
                            "(réception DOFUS non vérifiée)."
                        )
                    else:
                        with (
                            patch("app.macros.direction.foreground_window",
                                  side_effect=lambda: activations[-1] if activations else 101),
                            patch("app.macros.direction.is_unity_window",
                                  return_value=True),
                            patch("app.macros.direction.is_dofus_unity_process",
                                  return_value=True),
                            patch("app.macros.direction.activate_window",
                                  side_effect=activate),
                            patch("app.macros.direction.press_key") as press,
                        ):
                            DirectionMacro(runtime)._run("HOME")
                        press.assert_called_once()
                        runtime.logger.info.assert_any_call(
                            "Switch deplacement %s: envoyes=%s/%s",
                            "interrompu", 1, count,
                        )
                    self.assertEqual(activations, [101, 102])
                    runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_frozen_roster_still_skips_only_genuine_unavailable_target(self):
        for count in (2, 4, 6, 8):
            for kind in ("zaap", "direction"):
                with self.subTest(clients=count, kind=kind):
                    runtime = _runtime()
                    clients = [
                        SimpleNamespace(handle=101 + i) for i in range(count)
                    ]
                    runtime.settings.primary_handle = 101
                    runtime.macro_lock.should_stop.return_value = False
                    runtime.switch_character.ordered_clients_from_source.return_value = clients
                    runtime.settings.client_by_handle.return_value = clients[0]
                    activated = []

                    def activate(hwnd, *_args, **_kwargs):
                        activated.append(hwnd)
                        return hwnd != 101

                    if kind == "zaap":
                        with (
                            patch("app.macros.zaap.is_unity_window",
                                  return_value=True),
                            patch("app.macros.zaap.is_dofus_unity_process",
                                  return_value=True),
                            patch("app.macros.zaap.activate_window",
                                  side_effect=activate),
                            patch("app.macros.zaap.foreground_window",
                                  side_effect=lambda: activated[-1]),
                            patch("app.macros.zaap.send_chat_command",
                                  return_value=True) as chat,
                        ):
                            ZaapMacro(runtime)._run("/zaap 1,2")
                        self.assertEqual(chat.call_count, count - 1)
                    else:
                        with (
                            patch("app.macros.direction.foreground_window",
                                  side_effect=lambda: activated[-1] if activated else 101),
                            patch("app.macros.direction.is_unity_window",
                                  return_value=True),
                            patch("app.macros.direction.is_dofus_unity_process",
                                  return_value=True),
                            patch("app.macros.direction.activate_window",
                                  side_effect=activate),
                            patch("app.macros.direction.press_key") as press,
                        ):
                            DirectionMacro(runtime)._run("HOME")
                        self.assertEqual(press.call_count, count - 1)
                    self.assertEqual(activated, [101 + i for i in range(count)])


    def test_activation_failure_from_stop_or_reload_never_continues_fanout(self):
        for count in (2, 4, 6, 8):
            for kind in ("zaap", "direction"):
                for reason in ("stop", "reload"):
                    with self.subTest(clients=count, kind=kind, reason=reason):
                        runtime = _runtime()
                        clients = [
                            SimpleNamespace(handle=101 + i) for i in range(count)
                        ]
                        runtime.settings.primary_handle = 101
                        runtime.macro_lock.should_stop.return_value = False
                        runtime.switch_character.ordered_clients_from_source.return_value = clients
                        runtime.settings.client_by_handle.return_value = clients[0]
                        old = runtime.settings

                        def activation(*_args, **_kwargs):
                            if reason == "stop":
                                runtime.macro_lock.should_stop.return_value = True
                            else:
                                new = Mock()
                                new.primary_handle = old.primary_handle
                                new.clients = old.clients
                                runtime.settings = new
                            return False

                        if kind == "zaap":
                            with (
                                patch("app.macros.zaap.is_unity_window",
                                      return_value=True),
                                patch("app.macros.zaap.is_dofus_unity_process",
                                      return_value=True),
                                patch("app.macros.zaap.activate_window",
                                      side_effect=activation) as focus,
                                patch("app.macros.zaap.send_chat_command") as chat,
                            ):
                                ZaapMacro(runtime)._run("/zaap 1,2")
                            chat.assert_not_called()
                            runtime._emit_status.assert_called_once_with(
                                f"Auto zaap interrompu : 0/{count} commandes émises "
                                "(réception DOFUS non vérifiée)."
                            )
                        else:
                            with (
                                patch("app.macros.direction.foreground_window",
                                      return_value=101),
                                patch("app.macros.direction.is_unity_window",
                                      return_value=True),
                                patch("app.macros.direction.is_dofus_unity_process",
                                      return_value=True),
                                patch("app.macros.direction.activate_window",
                                      side_effect=activation) as focus,
                                patch("app.macros.direction.press_key") as key,
                            ):
                                DirectionMacro(runtime)._run("HOME")
                            key.assert_not_called()
                            runtime.logger.info.assert_any_call(
                                "Switch deplacement %s: envoyes=%s/%s",
                                "interrompu", 0, count,
                            )
                        focus.assert_called_once()
                        runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_process_probe_roster_mutation_blocks_activation_before_focus(self):
        for count in (2, 4, 6, 8):
            for kind in ("zaap", "direction"):
                with self.subTest(clients=count, kind=kind):
                    runtime = _runtime()
                    clients = [
                        SimpleNamespace(handle=101 + i) for i in range(count)
                    ]
                    runtime.settings.primary_handle = 101
                    runtime.switch_character.ordered_clients_from_source.return_value = clients
                    runtime.settings.client_by_handle.return_value = clients[0]
                    runtime.macro_lock.should_stop.return_value = False

                    def process(_hwnd):
                        clients[-1].handle = 999
                        return True

                    if kind == "zaap":
                        with (
                            patch("app.macros.zaap.is_unity_window",
                                  return_value=True),
                            patch("app.macros.zaap.is_dofus_unity_process",
                                  side_effect=process),
                            patch("app.macros.zaap.activate_window") as focus,
                            patch("app.macros.zaap.send_chat_command") as chat,
                        ):
                            ZaapMacro(runtime)._run("/zaap 1,2")
                        chat.assert_not_called()
                        runtime._emit_status.assert_called_once_with(
                            f"Auto zaap interrompu : 0/{count} commandes émises "
                            "(réception DOFUS non vérifiée)."
                        )
                    else:
                        with (
                            patch("app.macros.direction.foreground_window",
                                  return_value=101),
                            patch("app.macros.direction.is_unity_window",
                                  return_value=True),
                            patch("app.macros.direction.is_dofus_unity_process",
                                  side_effect=process),
                            patch("app.macros.direction.activate_window") as focus,
                            patch("app.macros.direction.press_key") as key,
                        ):
                            DirectionMacro(runtime)._run("HOME")
                        key.assert_not_called()
                        runtime.logger.info.assert_any_call(
                            "Switch deplacement %s: envoyes=%s/%s",
                            "interrompu", 0, count,
                        )
                    focus.assert_not_called()
                    runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_all_existing_macro_workers_reject_prestart_profile_reload_2_to_8(self):
        # A queued action belongs to the generation at its hotkey dispatch,
        # even if Organizer rebuilds the same visible HWND roster.
        for count in (2, 4, 6, 8):
            for kind in ("direction", "zaap", "auto_group"):
                with self.subTest(clients=count, kind=kind):
                    runtime = _runtime()
                    runtime._spawn_macro.return_value = True
                    runtime.settings.clients = [
                        SimpleNamespace(handle=101 + i) for i in range(count)
                    ]
                    if kind == "direction":
                        started = DirectionMacro(runtime).run_async("HOME")
                    elif kind == "zaap":
                        started = ZaapMacro(runtime).run_async("/zaap 1,2")
                    else:
                        started = AutoGroupMacro(runtime).run_async([
                            {"name": "Friend", "handle": 102},
                        ])
                    self.assertTrue(started)
                    worker = runtime._spawn_macro.call_args.args[1]
                    original = runtime.settings
                    new_profile = Mock()
                    new_profile.clients = original.clients
                    new_profile.primary_handle = original.primary_handle
                    new_profile.timings = original.timings
                    runtime.settings = new_profile
                    with (
                        patch("app.macros.direction.foreground_window") as d_focus,
                        patch("app.macros.direction.activate_window") as d_activate,
                        patch("app.macros.direction.press_key") as d_key,
                        patch("app.macros.zaap.activate_window") as z_activate,
                        patch("app.macros.zaap.send_chat_command") as z_chat,
                        patch("app.macros.auto_group.activate_window") as g_activate,
                        patch("app.macros.auto_group.send_chat_command") as g_chat,
                    ):
                        worker()
                    d_focus.assert_not_called()
                    d_activate.assert_not_called()
                    d_key.assert_not_called()
                    z_activate.assert_not_called()
                    z_chat.assert_not_called()
                    g_activate.assert_not_called()
                    g_chat.assert_not_called()
                    runtime.switch_character.logical_active_client.assert_not_called()
                    runtime.switch_character.ordered_clients_from_source.assert_not_called()
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    if kind == "direction":
                        runtime.logger.info.assert_any_call(
                            "Switch deplacement annulé: profil Organizer remplacé avant worker.",
                        )
                    elif kind == "zaap":
                        runtime._emit_status.assert_called_once_with(
                            "Auto zaap interrompu : profil Organizer modifié.",
                        )
                    else:
                        runtime._emit_status.assert_called_once_with(
                            "Auto-groupe interrompu : profil Organizer modifié.",
                        )


    def test_classic_click_binding_reload_preserves_native_down_2_to_8(self):
        from app.core.runtime_state import AtlasRuntime

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime._running = True
                runtime._admin_ok = True
                runtime._pending_physical_switch = None
                old = runtime.settings
                old.macro_mode = "macro"
                old.clients = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]
                newer = Mock()
                newer.macro_mode = "macro"
                newer.clients = old.clients

                def reload_during_binding():
                    runtime.settings = newer
                    return SimpleNamespace(
                        action_id="switch_click",
                        payload={"click_count": 2, "label": "Switch double clic"},
                    )

                runtime.registry.switch_action_for_pressed_keys.side_effect = reload_during_binding
                with (
                    patch("app.windows.unity_windows.foreground_window") as focus,
                    patch("app.windows.unity_windows.find_known_client_from_point") as hit,
                ):
                    self.assertFalse(
                        AtlasRuntime._handle_mouse_click(runtime, "Left", 20, 25),
                    )
                focus.assert_not_called()
                hit.assert_not_called()
                runtime.switch_click.run_async.assert_not_called()
                self.assertIsNone(runtime._pending_physical_switch)
                runtime.logger.debug.assert_any_call(
                    "Clic switch abandonné: profil Organizer modifié pendant raccourci."
                )

    def test_classic_click_reload_during_hit_test_prevents_replay_2_to_8(self):
        from app.core.runtime_state import AtlasRuntime

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime._running = True
                runtime._admin_ok = True
                runtime._pending_physical_switch = None
                old = runtime.settings
                old.macro_mode = "macro"
                old.clients = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]
                runtime.macro_lock.active_label = ""
                runtime.registry.switch_action_for_pressed_keys.return_value = (
                    SimpleNamespace(
                        action_id="switch_click",
                        payload={"click_count": 1, "label": "Switch clique"},
                    )
                )
                newer = Mock()
                newer.macro_mode = "macro"
                newer.clients = old.clients

                def reload_during_hit(*_args):
                    runtime.settings = newer
                    return 101

                with (
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          side_effect=reload_during_hit),
                    patch("app.windows.unity_windows.foreground_window") as focus,
                    patch("app.macros.mirror_plan.is_dofus_unity_process") as identity,
                ):
                    self.assertFalse(
                        AtlasRuntime._handle_mouse_click(runtime, "Left", 20, 25),
                    )
                focus.assert_not_called()
                identity.assert_not_called()
                runtime.switch_click.run_async.assert_not_called()
                self.assertIsNone(runtime._pending_physical_switch)

    def test_busy_classic_click_never_swallows_after_native_profile_reload(self):
        from app.core.runtime_state import AtlasRuntime

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime._running = True
                runtime._admin_ok = True
                runtime.settings.macro_mode = "macro"
                runtime.settings.clients = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]
                runtime.macro_lock.active_label = "Switch clique"
                runtime.input_state.is_mouse_blocked.return_value = True
                runtime.registry.switch_action_for_pressed_keys.return_value = (
                    SimpleNamespace(action_id="switch_click", payload={})
                )
                original = runtime.settings

                def reload_during_process(_hwnd):
                    newer = Mock()
                    newer.macro_mode = "macro"
                    newer.clients = original.clients
                    runtime.settings = newer
                    return True

                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=101),
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          return_value=101),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          side_effect=reload_during_process),
                ):
                    self.assertFalse(
                        AtlasRuntime._handle_mouse_click(runtime, "Left", 20, 25),
                    )
                runtime.switch_click.run_async.assert_not_called()

    def test_classic_double_click_uses_profile_generation_2_to_8(self):
        from app.core.runtime_state import AtlasRuntime

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime._running = True
                runtime._admin_ok = True
                runtime.settings.macro_mode = "macro"
                runtime.settings.clients = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]
                runtime.macro_lock.active_label = ""
                runtime.registry.switch_action_for_pressed_keys.return_value = (
                    SimpleNamespace(
                        action_id="double_click",
                        payload={"click_count": 2, "label": "Switch double clic"},
                    )
                )
                runtime.switch_click.run_async.return_value = True
                self.assertTrue(AtlasRuntime._handle_mouse_click(
                    runtime, "Left", 20, 25,
                ))
                runtime.switch_click.run_async.assert_called_once_with(
                    "Left", 20, 25, 2, "Switch double clic",
                    expected_profile=runtime.settings,
                )

    def test_click_capture_profile_change_aborts_before_worker_creation(self):
        from app.macros.switch_click import SwitchClickContext, SwitchClickMacro

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                old = runtime.settings
                old.clients = [
                    SimpleNamespace(handle=101 + i) for i in range(count)
                ]
                sender = SwitchClickMacro(runtime)
                context = SwitchClickContext(101, 12, 15, 0.5, 0.5, "cursor")

                def reload_during_capture(*_args):
                    newer = Mock()
                    newer.clients = old.clients
                    runtime.settings = newer
                    return context

                with patch.object(sender, "_capture_trigger_context",
                                  side_effect=reload_during_capture):
                    self.assertFalse(sender.run_async(
                        "Left", 20, 25, 2, "Switch double clic",
                        expected_profile=old,
                    ))
                runtime._spawn_macro.assert_not_called()



    def test_auto_group_native_cleanup_mutation_never_restores_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.settings.primary_handle = 101
                runtime.settings.macro_mode = "macro"
                runtime.settings.timings.auto_group_invite_gap_ms = 0
                sender = SimpleNamespace(handle=101, display_name="Leader")
                runtime.switch_character.logical_active_client.return_value = sender
                entries = [
                    {"name": f"Friend{i}", "handle": 101 + i}
                    for i in range(1, count)
                ]
                probes = []

                def probe(hwnd):
                    probes.append(hwnd)
                    if len(probes) == count + 1:
                        self.assertEqual(hwnd, 101)
                        sender.handle = 999
                    return True

                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process",
                          side_effect=probe),
                    patch("app.macros.auto_group.activate_window", return_value=True),
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command",
                          return_value=True) as send,
                ):
                    AutoGroupMacro(runtime)._run(entries)
                self.assertEqual(send.call_count, count - 1)
                self.assertEqual(len(probes), count + 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                self.assertIn("interrompu", runtime._emit_status.call_args.args[0])

    def test_direction_native_cleanup_mutation_never_restores_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.settings.primary_handle = 101
                runtime.settings.macro_mode = "macro"
                clients = [SimpleNamespace(handle=101 + i) for i in range(count)]
                handles = tuple(client.handle for client in clients)
                runtime.switch_character.ordered_clients_from_source.return_value = clients
                runtime.settings.client_by_handle.return_value = clients[0]
                probes = []

                def probe(hwnd):
                    probes.append(hwnd)
                    if len(probes) == 2 * count + 2:
                        self.assertEqual(hwnd, 101)
                        clients[0].handle = 999
                    return True

                with (
                    patch("app.macros.direction.foreground_window",
                          side_effect=[101, *handles, handles[-1]]),
                    patch("app.macros.direction.is_unity_window", return_value=True),
                    patch("app.macros.direction.is_dofus_unity_process",
                          side_effect=probe),
                    patch("app.macros.direction.activate_window", return_value=True),
                    patch("app.macros.direction.press_key") as press,
                ):
                    DirectionMacro(runtime)._run("HOME")
                self.assertEqual(press.call_count, count)
                self.assertEqual(len(probes), 2 * count + 2)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch deplacement %s: envoyes=%s/%s", "interrompu", count, count,
                )

    def test_zaap_native_cleanup_mutation_never_restores_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.settings.primary_handle = 101
                runtime.settings.macro_mode = "macro"
                clients = [SimpleNamespace(handle=101 + i) for i in range(count)]
                runtime.switch_character.ordered_clients_from_source.return_value = clients
                active = [101]
                probes = []

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def probe(hwnd):
                    probes.append(hwnd)
                    if len(probes) == 2 * count + 1:
                        self.assertEqual(hwnd, clients[-1].handle)
                        clients[0].handle = 999
                    return True

                with (
                    patch("app.macros.zaap.is_unity_window", return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process",
                          side_effect=probe),
                    patch("app.macros.zaap.activate_window", side_effect=activate),
                    patch("app.macros.zaap.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.zaap.send_chat_command",
                          return_value=True) as send,
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                self.assertEqual(send.call_count, count)
                self.assertEqual(len(probes), 2 * count + 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                self.assertIn("interrompu", runtime._emit_status.call_args.args[0])


    def test_auto_group_last_invite_favorite_change_is_interrupted_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.settings.primary_handle = 101
                runtime.settings.macro_mode = "macro"
                runtime.settings.timings.auto_group_invite_gap_ms = 0
                runtime.switch_character.logical_active_client.return_value = (
                    SimpleNamespace(handle=101, display_name="Leader")
                )
                entries = [
                    {"name": f"Friend{i}", "handle": 101 + i}
                    for i in range(1, count)
                ]
                sent = []

                def chat(*_args, **_kwargs):
                    sent.append(True)
                    if len(sent) == count - 1:
                        runtime.settings.primary_handle = 101 + count - 1
                    return True

                with (
                    patch("app.macros.auto_group.is_unity_window", return_value=True),
                    patch("app.macros.auto_group.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.auto_group.activate_window", return_value=True),
                    patch("app.macros.auto_group.foreground_window", return_value=101),
                    patch("app.macros.auto_group.send_chat_command",
                          side_effect=chat),
                ):
                    AutoGroupMacro(runtime)._run(entries)
                self.assertEqual(len(sent), count - 1)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
                    "interrompu", count - 1, count - 1, count - 1, 101,
                )

    def test_direction_last_key_favorite_change_is_interrupted_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.settings.primary_handle = 101
                runtime.settings.macro_mode = "macro"
                clients = [SimpleNamespace(handle=101 + i) for i in range(count)]
                runtime.switch_character.ordered_clients_from_source.return_value = clients
                runtime.settings.client_by_handle.return_value = clients[0]
                active = [101]
                emitted = []

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def send(*_args):
                    emitted.append(True)
                    if len(emitted) == count:
                        runtime.settings.primary_handle = 101 + count - 1

                with (
                    patch("app.macros.direction.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.direction.is_unity_window", return_value=True),
                    patch("app.macros.direction.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.direction.activate_window",
                          side_effect=activate),
                    patch("app.macros.direction.press_key",
                          side_effect=send),
                ):
                    DirectionMacro(runtime)._run("HOME")
                self.assertEqual(len(emitted), count)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Switch deplacement %s: envoyes=%s/%s",
                    "interrompu", count, count,
                )

    def test_zaap_last_command_favorite_change_is_interrupted_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = _runtime()
                runtime.settings.primary_handle = 101
                runtime.settings.macro_mode = "macro"
                clients = [SimpleNamespace(handle=101 + i) for i in range(count)]
                runtime.switch_character.ordered_clients_from_source.return_value = clients
                active = [101]
                sent = []

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def chat(*_args, **_kwargs):
                    sent.append(True)
                    if len(sent) == count:
                        runtime.settings.primary_handle = 101 + count - 1
                    return True

                with (
                    patch("app.macros.zaap.is_unity_window", return_value=True),
                    patch("app.macros.zaap.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.zaap.activate_window",
                          side_effect=activate),
                    patch("app.macros.zaap.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.zaap.send_chat_command",
                          side_effect=chat),
                ):
                    ZaapMacro(runtime)._run("/zaap 1,2")
                self.assertEqual(len(sent), count)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.logger.info.assert_any_call(
                    "Auto zaap %s: envoyes=%s/%s", "interrompu", count, count,
                )


    def test_existing_macro_dispatch_rejects_inplace_or_replaced_profile_during_admission(self):
        for count in (2, 4, 6, 8):
            for action in ("group", "direction", "zaap"):
                for mutation in ("favorite", "mode", "replace"):
                    with self.subTest(clients=count, action=action, mutation=mutation):
                        runtime = _runtime()
                        original = SimpleNamespace(
                            primary_handle=101, macro_mode="macro",
                            clients=[SimpleNamespace(handle=101 + i)
                                     for i in range(count)],
                        )
                        runtime.settings = original
                        queued = []

                        def spawn(_label, worker):
                            queued.append(worker)
                            if mutation == "favorite":
                                original.primary_handle = original.clients[-1].handle
                            elif mutation == "mode":
                                original.macro_mode = "mirror"
                            else:
                                runtime.settings = SimpleNamespace(
                                    primary_handle=101, macro_mode="macro",
                                    clients=original.clients,
                                )
                            return True

                        runtime._spawn_macro.side_effect = spawn
                        if action == "group":
                            accepted = AutoGroupMacro(runtime).run_async(
                                [{"name": "Friend", "handle": 102}],
                            )
                        elif action == "direction":
                            accepted = DirectionMacro(runtime).run_async(
                                "HOME", expected_profile=original,
                            )
                        else:
                            accepted = ZaapMacro(runtime).run_async("/zaap 1,2")
                        self.assertFalse(accepted)
                        self.assertEqual(len(queued), 1)

    def test_existing_macro_dispatch_accepts_unchanged_profile_2_to_8(self):
        for count in (2, 4, 6, 8):
            for action in ("group", "direction", "zaap"):
                with self.subTest(clients=count, action=action):
                    runtime = _runtime()
                    runtime.settings = SimpleNamespace(
                        primary_handle=101, macro_mode="macro",
                        clients=[SimpleNamespace(handle=101 + i)
                                 for i in range(count)],
                    )
                    runtime._spawn_macro.return_value = True
                    if action == "group":
                        accepted = AutoGroupMacro(runtime).run_async(
                            [{"name": "Friend", "handle": 102}],
                        )
                    elif action == "direction":
                        accepted = DirectionMacro(runtime).run_async(
                            "HOME", expected_profile=runtime.settings,
                        )
                    else:
                        accepted = ZaapMacro(runtime).run_async("/zaap 1,2")
                    self.assertTrue(accepted)
                    runtime._spawn_macro.assert_called_once()


    def test_existing_macro_admission_stop_is_not_reported_accepted_2_to_8(self):
        for count in (2, 4, 6, 8):
            for action in ("group", "direction", "zaap"):
                with self.subTest(clients=count, action=action):
                    runtime = _runtime()
                    runtime.settings = SimpleNamespace(
                        primary_handle=101, macro_mode="macro",
                        clients=[SimpleNamespace(handle=101 + i)
                                 for i in range(count)],
                    )

                    def stop_during_admission(_label, _worker):
                        runtime.macro_lock.should_stop.return_value = True
                        return True

                    runtime._spawn_macro.side_effect = stop_during_admission
                    if action == "group":
                        accepted = AutoGroupMacro(runtime).run_async(
                            [{"name": "Friend", "handle": 102}],
                        )
                    elif action == "direction":
                        accepted = DirectionMacro(runtime).run_async(
                            "HOME", expected_profile=runtime.settings,
                        )
                    else:
                        accepted = ZaapMacro(runtime).run_async("/zaap 1,2")
                    self.assertFalse(accepted)
                    runtime._spawn_macro.assert_called_once()


if __name__ == "__main__":
    unittest.main()
