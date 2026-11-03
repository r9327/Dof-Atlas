from __future__ import annotations

import threading
from logging import Logger
from typing import TYPE_CHECKING, Any, Callable

from app.input.input_state import InputState, SyntheticInputGuard
from app.startup_timing import startup_flush, startup_mark

if TYPE_CHECKING:
    from app.input.hotkeys import HotkeyAction, HotkeyReport, HotkeyRegistry
    from app.input.mouse_hooks import MouseHook


HotkeyCallback = Callable[[str, dict[str, object]], None]
MouseCallback = Callable[[str, int, int], bool]


def build_runtime_hotkey_actions(settings):
    """Compatibility entry point for runtime hotkey construction.

    Keep the Win32 keyboard backend out of the import path used before the first
    application paint. The real builder is needed only when the runtime worker
    reloads its bindings.
    """
    from app.input.hotkeys import build_hotkey_actions

    return build_hotkey_actions(settings)


class ManagedHotkeyRegistry:
    """Lazy compatibility wrapper around the lifecycle-safe keyboard registry.

    Runtime construction happens before the first window paint, while keyboard
    parsing/hooks are only needed when the asynchronous runtime startup begins.
    Keep one backend instance for the whole wrapper lifetime so stop/start
    semantics remain exactly those of ``HotkeyRegistry``.
    """

    def __init__(self, input_state: InputState, logger: Logger, callback: HotkeyCallback):
        self.input_state = input_state
        self.logger = logger
        self.callback = callback
        self._backend: HotkeyRegistry | None = None
        self._backend_lock = threading.Lock()

    def _ensure_backend(self) -> HotkeyRegistry:
        backend = self._backend
        if backend is not None:
            return backend
        with self._backend_lock:
            backend = self._backend
            if backend is None:
                from app.input.hotkeys import HotkeyRegistry

                backend = HotkeyRegistry(self.input_state, self.logger, self.callback)
                self._backend = backend
        return backend

    def register_hotkeys(self, actions: list[HotkeyAction]) -> HotkeyReport:
        return self._ensure_backend().register_hotkeys(actions)

    def start(self) -> bool:
        startup_mark("runtime_hotkey_start")
        started = bool(self._ensure_backend().start())
        if started:
            startup_mark("runtime_hotkey_ready")
            startup_flush("runtime_hotkey_ready")
        return started

    def stop(self) -> None:
        backend = self._backend
        if backend is not None:
            backend.stop()

    def switch_action_for_pressed_keys(self) -> HotkeyAction | None:
        backend = self._backend
        if backend is None:
            return None
        return backend.switch_action_for_pressed_keys()

    def armed_switch_action(self) -> HotkeyAction | None:
        backend = self._backend
        if backend is None:
            return None
        return backend.armed_switch_action()

    def __getattr__(self, name: str) -> Any:
        # Preserve compatibility for diagnostics/tests that inspect backend
        # lifecycle fields which historically lived directly on this object.
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(self._ensure_backend(), name)


class ManagedMouseHook:
    """Lazy compatibility wrapper around the lifecycle-safe mouse hook."""

    def __init__(
        self,
        input_state: InputState,
        synthetic_guard: SyntheticInputGuard,
        logger: Logger,
        callback: MouseCallback,
    ):
        self.input_state = input_state
        self.synthetic_guard = synthetic_guard
        self.logger = logger
        self.callback = callback
        self._backend: MouseHook | None = None
        self._backend_lock = threading.Lock()

    def _ensure_backend(self) -> MouseHook:
        backend = self._backend
        if backend is not None:
            return backend
        with self._backend_lock:
            backend = self._backend
            if backend is None:
                from app.input.mouse_hooks import MouseHook

                backend = MouseHook(
                    self.input_state,
                    self.synthetic_guard,
                    self.logger,
                    self.callback,
                )
                self._backend = backend
        return backend

    def start(self) -> bool:
        startup_mark("runtime_mouse_start")
        started = bool(self._ensure_backend().start())
        if started:
            startup_mark("runtime_mouse_ready")
            startup_flush("runtime_mouse_ready")
        return started

    def stop(self) -> None:
        backend = self._backend
        if backend is not None:
            backend.stop()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(self._ensure_backend(), name)