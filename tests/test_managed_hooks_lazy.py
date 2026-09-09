from __future__ import annotations

import subprocess
import sys
import types
import unittest
from unittest.mock import patch

from app.input.input_state import InputState
from app.input.managed_hooks import ManagedHotkeyRegistry, ManagedMouseHook, build_runtime_hotkey_actions


class _Logger:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class _SyntheticGuard:
    pass


class ManagedHooksLazyTests(unittest.TestCase):
    def test_import_does_not_load_hook_backends(self) -> None:
        code = (
            "import sys; "
            "import app.input.managed_hooks; "
            "assert 'app.input.hotkeys' not in sys.modules; "
            "assert 'app.input.mouse_hooks' not in sys.modules"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_input_tools_import_does_not_restore_hotkey_backend(self) -> None:
        code = (
            "import sys; "
            "import app.macros.input_tools; "
            "assert 'app.input.hotkeys' not in sys.modules"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_keyboard_backend_is_created_once_and_reused_across_restart(self) -> None:
        module = types.ModuleType("app.input.hotkeys")
        instances = []

        class FakeRegistry:
            def __init__(self, input_state, logger, callback):
                self.input_state = input_state
                self.logger = logger
                self.callback = callback
                self.calls = []
                instances.append(self)

            def register_hotkeys(self, actions):
                self.calls.append(("register", tuple(actions)))
                return "report"

            def start(self):
                self.calls.append(("start",))
                return True

            def stop(self):
                self.calls.append(("stop",))

            def switch_action_for_pressed_keys(self):
                return "switch"

            def armed_switch_action(self):
                return "armed"

        module.HotkeyRegistry = FakeRegistry
        module.build_hotkey_actions = lambda settings: [settings]

        registry = ManagedHotkeyRegistry(InputState(), _Logger(), lambda *_args: None)
        self.assertIsNone(registry._backend)
        registry.stop()
        self.assertEqual(instances, [])

        with patch.dict(sys.modules, {"app.input.hotkeys": module}):
            self.assertEqual(registry.register_hotkeys(["a"]), "report")
            self.assertTrue(registry.start())
            registry.stop()
            self.assertTrue(registry.start())
            self.assertEqual(registry.switch_action_for_pressed_keys(), "switch")
            self.assertEqual(registry.armed_switch_action(), "armed")

        self.assertEqual(len(instances), 1)
        self.assertIs(registry._backend, instances[0])
        self.assertEqual(
            instances[0].calls,
            [("register", ("a",)), ("start",), ("stop",), ("start",)],
        )

    def test_mouse_backend_is_created_once_and_reused_across_restart(self) -> None:
        module = types.ModuleType("app.input.mouse_hooks")
        instances = []

        class FakeMouseHook:
            def __init__(self, input_state, synthetic_guard, logger, callback):
                self.input_state = input_state
                self.synthetic_guard = synthetic_guard
                self.logger = logger
                self.callback = callback
                self.calls = []
                instances.append(self)

            def start(self):
                self.calls.append("start")
                return True

            def stop(self):
                self.calls.append("stop")

        module.MouseHook = FakeMouseHook
        hook = ManagedMouseHook(
            InputState(),
            _SyntheticGuard(),
            _Logger(),
            lambda *_args: False,
        )
        self.assertIsNone(hook._backend)
        hook.stop()
        self.assertEqual(instances, [])

        with patch.dict(sys.modules, {"app.input.mouse_hooks": module}):
            self.assertTrue(hook.start())
            hook.stop()
            self.assertTrue(hook.start())

        self.assertEqual(len(instances), 1)
        self.assertIs(hook._backend, instances[0])
        self.assertEqual(instances[0].calls, ["start", "stop", "start"])

    def test_hotkey_action_builder_import_is_deferred_until_call(self) -> None:
        module = types.ModuleType("app.input.hotkeys")
        module.build_hotkey_actions = lambda settings: ["built", settings]
        with patch.dict(sys.modules, {"app.input.hotkeys": module}):
            self.assertEqual(build_runtime_hotkey_actions("settings"), ["built", "settings"])

    def test_input_vk_keeps_existing_hotkey_codes(self) -> None:
        from app.macros import input_tools

        module = types.ModuleType("app.input.hotkeys")
        module.NAMED_KEYS = {"HOME": 0x24}
        module.VK_CONTROL = 0x11
        module.VK_MENU = 0x12
        module.VK_SHIFT = 0x10
        module.VK_LWIN = 0x5B
        with patch.dict(sys.modules, {"app.input.hotkeys": module}):
            self.assertEqual(input_tools._vk("CTRL"), 0x11)
            self.assertEqual(input_tools._vk("ALT"), 0x12)
            self.assertEqual(input_tools._vk("SHIFT"), 0x10)
            self.assertEqual(input_tools._vk("WIN"), 0x5B)
            self.assertEqual(input_tools._vk("HOME"), 0x24)
            self.assertEqual(input_tools._vk("A"), ord("A"))


if __name__ == "__main__":
    unittest.main()
