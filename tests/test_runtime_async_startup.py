from __future__ import annotations

import os
import threading
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.core import runtime_state
from app.core.settings import AtlasSettings, ZaapTimings, timings_for_speed


class ControlledHook:
    def __init__(self, *, result: bool = True, blocked: bool = False) -> None:
        self.result = bool(result)
        self.started = threading.Event()
        self.release = threading.Event()
        if not blocked:
            self.release.set()
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> bool:
        self.start_calls += 1
        self.started.set()
        self.release.wait(1.0)
        return self.result

    def stop(self) -> None:
        self.stop_calls += 1


def _settings() -> AtlasSettings:
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
        timings=timings_for_speed("normal"),
        zaap_timings=ZaapTimings(),
    )


def _runtime(monkeypatch):
    statuses: list[str] = []
    active_states: list[bool] = []
    monkeypatch.setattr(runtime_state, "load_settings", _settings)
    monkeypatch.setattr(runtime_state, "set_debug_logging", lambda _enabled: None)
    monkeypatch.setattr(runtime_state, "enable_dpi_awareness", lambda: None)
    runtime = runtime_state.AtlasRuntime(statuses.append, active_states.append)
    # These tests validate the runtime state machine itself. Keep them independent
    # from whether another test created a QApplication earlier in the process.
    runtime._callback_bridge = None
    runtime.reload_hotkeys = lambda force_restart=False: setattr(runtime, "_admin_ok", True)
    runtime.emergency_stop = lambda reason="stop urgence": None
    return runtime, statuses, active_states


def test_runtime_callback_bridge_discards_stale_worker_active_state() -> None:
    app = QApplication.instance() or QApplication([])
    active_states: list[bool] = []
    bridge = runtime_state._RuntimeCallbackBridge(lambda _text: None, active_states.append)

    # Simulate a worker finishing startup and queueing `True` just before the UI
    # processes a newer stop request. The queued old value must be ignored.
    worker = threading.Thread(target=lambda: bridge.publish_active(True))
    worker.start()
    worker.join()

    bridge.publish_active(False)
    app.processEvents()

    assert active_states == [False]


def test_runtime_start_returns_while_keyboard_hook_is_still_starting(monkeypatch) -> None:
    runtime, _statuses, active_states = _runtime(monkeypatch)
    keyboard = ControlledHook(blocked=True)
    mouse = ControlledHook()
    runtime.registry = keyboard
    runtime.mouse_hook = mouse

    started_at = monotonic()
    runtime.start()
    elapsed = monotonic() - started_at

    assert elapsed < 0.25
    assert keyboard.started.wait(0.25)
    assert runtime.is_starting is True
    assert runtime._running is False

    keyboard.release.set()
    assert runtime.wait_for_startup(1.0) is True
    assert runtime.is_starting is False
    assert runtime._running is True
    assert active_states[-1] is True

    runtime.stop()


def test_runtime_partial_hook_failure_tears_down_both_hooks(monkeypatch) -> None:
    runtime, statuses, active_states = _runtime(monkeypatch)
    keyboard = ControlledHook(result=True)
    mouse = ControlledHook(result=False)
    runtime.registry = keyboard
    runtime.mouse_hook = mouse

    runtime.start()
    assert runtime.wait_for_startup(1.0) is False

    assert runtime._running is False
    assert keyboard.stop_calls >= 1
    assert mouse.stop_calls >= 1
    assert active_states[-1] is False
    assert any("Hooks Python indisponibles" in text for text in statuses)


def test_runtime_second_start_during_hook_start_reloads_latest_settings(monkeypatch) -> None:
    runtime, _statuses, _active_states = _runtime(monkeypatch)
    keyboard = ControlledHook(result=True, blocked=True)
    mouse = ControlledHook(result=True)
    runtime.registry = keyboard
    runtime.mouse_hook = mouse
    reload_calls = 0

    def reload_hotkeys(force_restart: bool = False) -> None:
        nonlocal reload_calls
        reload_calls += 1
        runtime._admin_ok = True

    runtime.reload_hotkeys = reload_hotkeys

    runtime.start()
    assert keyboard.started.wait(0.25)
    assert reload_calls == 1

    # Mirrors Organizer exporting a fresher CLIENT_INDEX_JSON while the first
    # Win32 hook is still inside its bounded startup wait.
    runtime.start()
    keyboard.release.set()

    assert runtime.wait_for_startup(1.0) is True
    assert reload_calls >= 2
    assert runtime._running is True

    runtime.stop()


def test_runtime_stop_during_startup_then_restart_has_no_duplicate_state(monkeypatch) -> None:
    runtime, _statuses, active_states = _runtime(monkeypatch)
    keyboard = ControlledHook(result=True)
    mouse = ControlledHook(result=True, blocked=True)
    runtime.registry = keyboard
    runtime.mouse_hook = mouse

    runtime.start()
    assert mouse.started.wait(0.25)
    assert runtime.is_starting is True

    threading.Timer(0.05, mouse.release.set).start()
    runtime.stop()

    assert runtime.is_starting is False
    assert runtime._running is False
    first_keyboard_starts = keyboard.start_calls
    first_mouse_starts = mouse.start_calls

    runtime.start()
    assert runtime.wait_for_startup(1.0) is True
    assert runtime._running is True
    assert keyboard.start_calls == first_keyboard_starts + 1
    assert mouse.start_calls == first_mouse_starts + 1
    assert active_states[-1] is True

    runtime.stop()
