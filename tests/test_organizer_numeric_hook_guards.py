from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.runtime_state import AtlasRuntime
from app.core.settings import int_value
from app.windows.unity_windows import find_known_client_from_point


class OrganizerNumericHookGuardsTests(unittest.TestCase):
    def test_infinite_hotkey_client_index_never_starts_a_switch(self):
        runtime = Mock()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings.macro_mode = "macro"
        for value in (float("inf"), -float("inf"), float("nan")):
            with self.subTest(value=str(value)):
                AtlasRuntime._handle_hotkey(
                    runtime, "client:1", {"client_index": value},
                )
        runtime.switch_character.activate_by_index.assert_not_called()
        self.assertEqual(runtime.logger.debug.call_count, 3)

    def test_client_hotkey_rejects_fractional_and_bool_slot_aliases(self):
        runtime = Mock()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings.macro_mode = "macro"
        for value in (True, False, 1.0, 1.75, -1.5):
            with self.subTest(value=repr(value)):
                AtlasRuntime._handle_hotkey(runtime, "client:1", {"client_index": value})
        runtime.switch_character.activate_by_index.assert_not_called()
        self.assertEqual(runtime.logger.debug.call_count, 5)
        # Keep the persisted textual slot contract and legitimate int path.
        AtlasRuntime._handle_hotkey(runtime, "client:1", {"client_index": "1"})
        AtlasRuntime._handle_hotkey(runtime, "client:2", {"client_index": 2})
        self.assertEqual(
            [c.args[0] for c in runtime.switch_character.activate_by_index.call_args_list],
            [1, 2],
        )

    def test_bound_hotkey_requires_integer_session_slot_2_to_8(self):
        for count in (2, 4, 6, 8):
            for bad_index in (True, 1.0, "1", False):
                with self.subTest(clients=count, slot=repr(bad_index)):
                    runtime = Mock()
                    runtime._running = True
                    runtime._admin_ok = True
                    profile = SimpleNamespace(
                        macro_mode="macro", switch_character_enabled=True,
                        clients=[SimpleNamespace(index=i + 1, handle=101 + i)
                                 for i in range(count)],
                    )
                    runtime.settings = profile
                    profile.clients[0].index = bad_index
                    AtlasRuntime._handle_hotkey(
                        runtime, "client:1", {"client_index": "1", "handle": 101},
                    )
                    runtime.switch_character.activate_by_index.assert_not_called()
                    # A valid integer slot keeps the existing behavior.
                    profile.clients[0].index = 1
                    AtlasRuntime._handle_hotkey(
                        runtime, "client:1", {"client_index": 1, "handle": 101},
                    )
                    runtime.switch_character.activate_by_index.assert_called_once_with(
                        1, expected_profile=profile,
                    )

    def test_stale_slot_hotkey_cannot_activate_reassigned_client_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = Mock()
                runtime._running = True
                runtime._admin_ok = True
                runtime.settings.macro_mode = "macro"
                runtime.settings.switch_character_enabled = True
                runtime.settings.clients = [
                    SimpleNamespace(index=i + 1, handle=101 + i)
                    for i in range(count)
                ]
                action = "client:1"
                payload = {"client_index": 1, "handle": 101}
                AtlasRuntime._handle_hotkey(runtime, action, payload)
                runtime.switch_character.activate_by_index.assert_called_once_with(
                    1, expected_profile=runtime.settings,
                )
                runtime.settings.clients[0].handle = 901
                AtlasRuntime._handle_hotkey(runtime, action, payload)
                runtime.switch_character.activate_by_index.assert_called_once_with(
                    1, expected_profile=runtime.settings,
                )
                runtime.settings.switch_character_enabled = False
                AtlasRuntime._handle_hotkey(
                    runtime, action, {"client_index": 1, "handle": 901},
                )
                runtime.switch_character.activate_by_index.assert_called_once_with(
                    1, expected_profile=runtime.settings,
                )

    def test_hotkey_action_and_payload_must_agree(self):
        runtime = Mock()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings.macro_mode = "macro"
        runtime.settings.switch_character_enabled = True
        runtime.settings.movement_enabled = True
        runtime.settings.clients = [SimpleNamespace(index=1, handle=101)]
        # A corrupted or stale action may not target another slot.
        AtlasRuntime._handle_hotkey(
            runtime, "client:2", {"client_index": 1, "handle": 101},
        )
        AtlasRuntime._handle_hotkey(
            runtime, "client:1", {"client_index": 1, "handle": True},
        )
        runtime.switch_character.activate_by_index.assert_not_called()
        # Movement keys are owned by their canonical action and toggle.
        for action, key in (
            ("direction:HOME", "DELETE"),
            ("direction:HOME", "F10"),
            ("direction:HOME", 1),
        ):
            AtlasRuntime._handle_hotkey(runtime, action, {"key_name": key})
        runtime.direction.run_async.assert_not_called()
        AtlasRuntime._handle_hotkey(
            runtime, "direction:HOME", {"key_name": "HOME"},
        )
        runtime.direction.run_async.assert_called_once_with(
            "HOME", expected_profile=runtime.settings,
        )
        runtime.settings.movement_enabled = False
        AtlasRuntime._handle_hotkey(
            runtime, "direction:DELETE", {"key_name": "DELETE"},
        )
        runtime.direction.run_async.assert_called_once_with(
            "HOME", expected_profile=runtime.settings,
        )

    def test_client_hotkey_reload_during_native_slot_binding_never_dispatches(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = Mock()
                runtime._running = True
                runtime._admin_ok = True
                replacement = SimpleNamespace(
                    macro_mode="macro",
                    switch_character_enabled=True,
                    clients=[
                        SimpleNamespace(index=i + 1, handle=101 + i)
                        for i in range(count)
                    ],
                )

                class ReloadingRoster:
                    def __iter__(self):
                        # Loading the HWND binding can yield to a concurrent
                        # Organizer replacement with identical-looking slots.
                        runtime.settings = replacement
                        return iter(replacement.clients)

                old = SimpleNamespace(
                    macro_mode="macro",
                    switch_character_enabled=True,
                    clients=ReloadingRoster(),
                )
                runtime.settings = old
                AtlasRuntime._handle_hotkey(
                    runtime, "client:1",
                    {"client_index": 1, "handle": 101},
                )
                runtime.switch_character.activate_by_index.assert_not_called()
                runtime.logger.debug.assert_any_call(
                    "Raccourci personnage abandonné: profil Organizer modifié."
                )

    def test_hotkey_reload_while_evaluating_toggle_rejects_next_and_direction(self):
        for count in (2, 4, 6, 8):
            for action in ("next_character", "direction:HOME"):
                with self.subTest(clients=count, action=action):
                    runtime = Mock()
                    runtime._running = True
                    runtime._admin_ok = True
                    replacement = SimpleNamespace(
                        macro_mode="macro",
                        switch_character_enabled=True,
                        movement_enabled=True,
                    )

                    class ReloadOnToggle:
                        def __bool__(self):
                            runtime.settings = replacement
                            return True

                    old = SimpleNamespace(
                        macro_mode="macro",
                        switch_character_enabled=ReloadOnToggle(),
                        movement_enabled=ReloadOnToggle(),
                    )
                    runtime.settings = old
                    payload = {"key_name": "HOME"} if action.startswith("direction:") else {}
                    AtlasRuntime._handle_hotkey(runtime, action, payload)
                    runtime.switch_character.activate_next.assert_not_called()
                    runtime.direction.run_async.assert_not_called()

    def test_healthy_native_hotkey_profile_binding_all_client_counts(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = Mock()
                runtime._running = True
                runtime._admin_ok = True
                profile = SimpleNamespace(
                    macro_mode="macro",
                    switch_character_enabled=True,
                    movement_enabled=True,
                    clients=[
                        SimpleNamespace(index=i + 1, handle=101 + i)
                        for i in range(count)
                    ],
                )
                runtime.settings = profile
                AtlasRuntime._handle_hotkey(runtime, f"client:{count}", {
                    "client_index": count, "handle": 100 + count,
                })
                AtlasRuntime._handle_hotkey(
                    runtime, "direction:HOME", {"key_name": "HOME"},
                )
                AtlasRuntime._handle_hotkey(runtime, "next_character", {})
                runtime.switch_character.activate_by_index.assert_called_once_with(
                    count, expected_profile=profile,
                )
                runtime.switch_character.activate_next.assert_called_once_with(
                    expected_profile=profile,
                )
                runtime.direction.run_async.assert_called_once_with(
                    "HOME", expected_profile=profile,
                )

    def test_infinite_click_binding_falls_back_to_single_native_click(self):
        for value in (float("inf"), -float("inf"), float("nan")):
            with self.subTest(value=str(value)):
                runtime = Mock()
                runtime._running = True
                runtime._admin_ok = True
                runtime._pending_physical_switch = None
                runtime.settings.macro_mode = "macro"
                runtime.settings.clients = ()
                runtime.macro_lock.active_label = None
                runtime.registry.switch_action_for_pressed_keys.return_value = (
                    SimpleNamespace(
                        action_id="switch_click",
                        payload={"click_count": value, "label": "Switch clique"},
                    )
                )
                runtime.switch_click.run_async.return_value = True
                with patch(
                    "app.windows.unity_windows.find_known_client_from_point",
                    return_value=0,
                ):
                    self.assertTrue(
                        AtlasRuntime._handle_mouse_click(runtime, "Left", 10, 20)
                    )
                runtime.switch_click.run_async.assert_called_once_with(
                    "Left", 10, 20, 1, "Switch clique",
                    expected_profile=runtime.settings,
                )
                runtime.logger.debug.assert_any_call(
                    "Payload switch invalide: action=%s payload=%s",
                    "switch_click", {"click_count": value, "label": "Switch clique"},
                )

    def test_untrusted_overflowing_hwnds_are_ignored_during_hit_test(self):
        with (
            patch("app.windows.unity_windows.window_from_point",
                  return_value=101) as point,
            patch("app.windows.unity_windows.is_unity_window",
                  return_value=True) as unity,
        ):
            self.assertEqual(find_known_client_from_point(
                20, 30, [float("inf"), float("-inf"), float("nan"), None, 101],
            ), 101)
        point.assert_called_once_with(20, 30)
        unity.assert_called_once_with(101)

    def test_invalid_only_roster_does_not_produce_trusted_source(self):
        with (
            patch("app.windows.unity_windows.window_from_point",
                  return_value=101),
            patch("app.windows.unity_windows.is_unity_window",
                  return_value=True),
        ):
            self.assertEqual(find_known_client_from_point(
                20, 30, (float("inf"), float("-inf"), float("nan"), None),
            ), 0)

    def test_settings_integer_conversion_preserves_default_on_overflow(self):
        for value in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=str(value)):
                self.assertEqual(int_value(value, default=37), 37)
        self.assertEqual(int_value("21", default=37), 21)
        self.assertEqual(int_value(0, default=37), 0)


if __name__ == "__main__":
    unittest.main()
