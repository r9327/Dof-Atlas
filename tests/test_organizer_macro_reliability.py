from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
    def test_switch_click_world_interactions_receive_hover_and_press_frames(self) -> None:
        from app.macros.switch_click import SwitchClickContext, SwitchClickMacro

        runtime = _runtime()
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101, display_name="source"),
            SimpleNamespace(handle=202, display_name="target"),
        ]
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        runtime.settings.timings.input_double_gap_ms = 5
        runtime.settings.timings.switch_click_down_ms = 1
        runtime.settings.timings.switch_background_pre_click_ms = 18
        runtime.settings.timings.switch_background_post_up_ms = 5
        runtime.settings.timings.switch_client_settle_ms = 0
        macro = SwitchClickMacro(runtime)
        context = SwitchClickContext(101, 32, 24, 0.5, 0.5, "cursor")

        with (
            patch.object(macro, "_validated_context", return_value=context),
            patch.object(macro, "_target_point", return_value=(32, 24)),
            patch("app.macros.switch_click.current_cursor_pos", return_value=(150, 170)),
            patch("app.macros.switch_click.set_cursor_pos"),
            patch("app.macros.switch_click.is_unity_window", return_value=True),
            patch("app.macros.switch_click.activate_window", return_value=True),
            patch("app.macros.switch_click.send_client_click", return_value=True) as send,
        ):
            macro._run("Left", 1, "Switch clique", context, mouse_block_started=True)

        self.assertEqual(send.call_count, 2)
        for sent in send.call_args_list:
            self.assertGreaterEqual(sent.args[5], 35, "button held across Unity update")
            self.assertGreaterEqual(sent.args[7], 50, "pointer settles before Unity click")
            self.assertEqual(sent.args[4], 1)
        runtime.input_state.end_mouse_block.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_called_once_with("Switch clique")

    def test_native_source_click_skips_reinjection_and_replays_only_targets(self) -> None:
        from app.macros.switch_click import SwitchClickContext, SwitchClickMacro

        runtime = _runtime()
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101, display_name="source"),
            SimpleNamespace(handle=202, display_name="target"),
        ]
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        runtime.settings.timings.input_double_gap_ms = 5
        runtime.settings.timings.switch_click_down_ms = 1
        runtime.settings.timings.switch_background_pre_click_ms = 18
        runtime.settings.timings.switch_background_post_up_ms = 5
        runtime.settings.timings.switch_client_settle_ms = 0
        macro = SwitchClickMacro(runtime)
        context = SwitchClickContext(101, 32, 24, 0.5, 0.5, "cursor")

        with (
            patch.object(macro, "_validated_context", return_value=context),
            patch.object(macro, "_target_point", return_value=(32, 24)),
            patch("app.macros.switch_click.current_cursor_pos", return_value=(150, 170)),
            patch("app.macros.switch_click.set_cursor_pos"),
            patch("app.macros.switch_click.is_unity_window", return_value=True),
            patch("app.macros.switch_click.activate_window", return_value=True),
            patch("app.macros.switch_click.send_client_click", return_value=True) as send,
        ):
            macro._run(
                "Left", 1, "Switch clique", context,
                mouse_block_started=True, physical_source_delivered=True,
            )

        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], 202)
        runtime.macro_lock.wait.assert_called_once_with(60)
        runtime.switch_character.restore_preferred_client.assert_called_once_with("Switch clique")

    def test_source_click_is_not_replayed_if_native_event_was_not_confirmed(self) -> None:
        from app.macros.switch_click import SwitchClickContext, SwitchClickMacro

        runtime = _runtime()
        context = SwitchClickContext(101, 30, 25, 0.5, 0.5, "preferred_last_client_point")
        macro = SwitchClickMacro(runtime)
        self.assertFalse(macro.run_async(
            "Left", 100, 100, 1, "Switch clique",
            captured_context=context, physical_source_delivered=True,
        ))
        runtime._spawn_macro.assert_not_called()

    def test_switch_click_native_source_down_and_up_are_forwarded(self) -> None:
        from app.core.runtime_state import AtlasRuntime
        from app.macros.switch_click import SwitchClickContext

        runtime = _runtime()
        runtime._running = True
        runtime._admin_ok = True
        runtime.macro_lock.active_label = ""
        runtime.macro_lock.should_stop.return_value = False
        runtime.registry.switch_action_for_pressed_keys.return_value = SimpleNamespace(
            action_id="switch_click",
            payload={"click_count": 1, "label": "Switch clique"},
        )
        runtime.settings.clients = [SimpleNamespace(handle=101)]
        context = SwitchClickContext(101, 25, 30, 0.2, 0.3, "cursor")
        runtime.switch_click._capture_trigger_context.return_value = context

        with (
            patch("app.windows.unity_windows.find_known_client_from_point", return_value=101),
            patch("app.windows.unity_windows.foreground_window", return_value=101),
        ):
            # False means pass-through, not "macro unavailable".
            self.assertFalse(AtlasRuntime._handle_mouse_click(runtime, "Left", 150, 160))
            runtime.switch_click.run_async.assert_not_called()
            self.assertTrue(AtlasRuntime._handle_mouse_release(runtime, "Left", 150, 160))

        runtime.switch_click.run_async.assert_called_once_with(
            "Left", 150, 160, 1, "Switch clique",
            captured_context=context, physical_source_delivered=True,
        )
        self.assertIsNone(runtime._pending_physical_switch)

    def test_physical_mouse_drag_keeps_source_release_without_replay(self) -> None:
        from app.core.runtime_state import AtlasRuntime
        from app.macros.switch_click import SwitchClickContext

        runtime = _runtime()
        runtime._running = True
        runtime._admin_ok = True
        runtime._pending_physical_switch = (
            "Left", 20, 40, 1, "Switch clique",
            SwitchClickContext(101, 12, 18, 0.5, 0.5, "cursor"),
        )
        self.assertTrue(AtlasRuntime._handle_mouse_release(runtime, "Left", 130, 180))
        self.assertIsNone(runtime._pending_physical_switch)
        runtime.switch_click.run_async.assert_not_called()

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
