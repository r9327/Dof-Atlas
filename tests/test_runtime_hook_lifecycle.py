from __future__ import annotations

import inspect
import logging
import unittest

from app.core.runtime_state import AtlasRuntime
from app.core.settings import AtlasSettings, MacroTimings, ZaapTimings
from app.input import hotkeys as hotkeys_module
from app.input import mouse_hooks as mouse_hooks_module
from app.input.hook_lifecycle import stop_message_hook
from app.input.hotkeys import HotkeyRegistry, build_hotkey_actions
from app.input.input_state import InputState, SyntheticInputGuard
from app.input.managed_hooks import ManagedHotkeyRegistry, ManagedMouseHook, build_runtime_hotkey_actions
from app.input.mouse_hooks import MouseHook


class RuntimeHookLifecycleTests(unittest.TestCase):
    def _settings(self) -> AtlasSettings:
        return AtlasSettings(
            clients=(),
            switch_character_enabled=False,
            switch_click_enabled=False,
            switch_click_hotkey="",
            switch_double_click_enabled=False,
            switch_double_click_hotkey="",
            movement_enabled=False,
            stop_hotkey="",
            script_speed="normal",
            debug_enabled=False,
            travel_text="",
            primary_handle=0,
            zaap_click_position=(0, 0),
            zaap_click_ratios=None,
            timings=MacroTimings(
                click_focus_settle_ms=0,
                input_click_down_ms=0,
                input_double_gap_ms=0,
                travel_focus_settle_ms=0,
                activate_min_settle_ms=0,
                activate_retry_ms=0,
                activate_attempts=1,
                switch_client_settle_ms=0,
                switch_click_down_ms=0,
                switch_click_post_up_ms=0,
                switch_background_pre_click_ms=0,
                switch_background_post_up_ms=0,
                switch_humanize_min_ms=0,
                switch_humanize_max_ms=0,
                auto_group_chat_open_ms=0,
                auto_group_key_step_ms=0,
                auto_group_paste_settle_ms=0,
                auto_group_invite_gap_ms=0,
                movement_key_hold_ms=0,
            ),
            zaap_timings=ZaapTimings(),
        )

    def test_empty_optional_stop_hotkey_is_not_an_action_or_error(self) -> None:
        registry = HotkeyRegistry(InputState(), logging.getLogger("test"), lambda *_args: None)
        base_actions = build_hotkey_actions(self._settings())
        runtime_actions = build_runtime_hotkey_actions(self._settings())

        self.assertFalse(any(action.action_id == "stop_script" for action in base_actions))
        self.assertEqual(base_actions, runtime_actions)
        report = registry.register_hotkeys(runtime_actions)
        self.assertTrue(report.ok)
        self.assertEqual(report.errors, ())

    def test_base_hooks_use_shared_deterministic_message_loop_shutdown(self) -> None:
        keyboard_stop = inspect.getsource(HotkeyRegistry.stop)
        mouse_stop = inspect.getsource(MouseHook.stop)
        helper = inspect.getsource(stop_message_hook)

        self.assertIn("stop_message_hook(self)", keyboard_stop)
        self.assertIn("stop_message_hook(self)", mouse_stop)
        self.assertIn("PostThreadMessageW", helper)
        self.assertIn("WM_QUIT", helper)
        self.assertIn("thread.join", helper)
        self.assertIn("thread.is_alive", helper)
        self.assertIn("owner._thread = thread", helper)

    def test_base_hooks_record_native_thread_identity(self) -> None:
        keyboard_run = inspect.getsource(HotkeyRegistry._run_hook)
        mouse_run = inspect.getsource(MouseHook._run_hook)
        self.assertIn("current_native_thread_id", keyboard_run)
        self.assertIn("current_native_thread_id", mouse_run)
        self.assertIn("self._hook_thread_id = 0", keyboard_run)
        self.assertIn("self._hook_thread_id = 0", mouse_run)

    def test_hook_callback_types_remain_importable_off_windows(self) -> None:
        portable_factory = 'getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)'
        self.assertIn(portable_factory, inspect.getsource(hotkeys_module))
        self.assertIn(portable_factory, inspect.getsource(mouse_hooks_module))

    def test_managed_hooks_are_lazy_compatibility_wrappers(self) -> None:
        logger = logging.getLogger("test_managed_hooks")
        input_state = InputState()
        keyboard = ManagedHotkeyRegistry(input_state, logger, lambda *_args: None)
        mouse = ManagedMouseHook(
            input_state,
            SyntheticInputGuard(logger),
            logger,
            lambda *_args: False,
        )

        self.assertIsNone(keyboard._backend)
        self.assertIsNone(mouse._backend)
        keyboard.stop()
        mouse.stop()
        self.assertIsNone(keyboard._backend)
        self.assertIsNone(mouse._backend)

    def test_hotkey_reload_reports_actual_runtime_activity(self) -> None:
        source = inspect.getsource(AtlasRuntime.reload_hotkeys)
        self.assertIn("self._running and self._admin_ok", source)
        self.assertNotIn("active_callback(report.ok", source)
        self.assertIn("Raccourcis recharges avec avertissement", source)


if __name__ == "__main__":
    unittest.main()
