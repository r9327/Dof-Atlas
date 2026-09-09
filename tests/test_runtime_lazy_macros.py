from __future__ import annotations

import logging
import subprocess
import sys
import threading
import types

import app.core.runtime_state as runtime_module
from app.core.runtime_state import AtlasRuntime


_MACRO_MODULES = (
    "app.macros.auto_group",
    "app.macros.direction",
    "app.macros.switch_character",
    "app.macros.switch_click",
    "app.macros.travel",
    "app.macros.zaap",
)


def _bare_runtime() -> AtlasRuntime:
    runtime = AtlasRuntime.__new__(AtlasRuntime)
    runtime._macro_init_lock = threading.RLock()
    runtime._switch_character = None
    runtime._switch_click = None
    runtime._direction = None
    runtime._travel = None
    runtime._zaap = None
    runtime._auto_group = None
    return runtime


def test_importing_runtime_does_not_import_macro_backends() -> None:
    script = """
import sys
import app.core.runtime_state
names = (
    'app.macros.auto_group',
    'app.macros.direction',
    'app.macros.switch_character',
    'app.macros.switch_click',
    'app.macros.travel',
    'app.macros.zaap',
)
loaded = [name for name in names if name in sys.modules]
raise SystemExit(0 if not loaded else 3)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_first_property_access_builds_macro_once_and_reuses_it(monkeypatch) -> None:
    runtime = _bare_runtime()
    created: list[object] = []

    class FakeTravelMacro:
        def __init__(self, owner) -> None:
            self.owner = owner
            created.append(self)

    fake_module = types.ModuleType("app.macros.travel")
    fake_module.TravelMacro = FakeTravelMacro
    monkeypatch.setitem(sys.modules, "app.macros.travel", fake_module)

    first = runtime.travel
    second = runtime.travel

    assert first is second
    assert first.owner is runtime
    assert created == [first]


def test_macro_property_setter_preserves_test_and_runtime_injection() -> None:
    runtime = _bare_runtime()
    fake = object()

    runtime.switch_click = fake

    assert runtime.switch_click is fake
    assert runtime._switch_click is fake


def test_emergency_stop_does_not_materialize_unused_macros(monkeypatch) -> None:
    runtime = _bare_runtime()
    events: list[tuple[str, object]] = []

    class FakeMacroLock:
        def request_stop(self, reason: str) -> None:
            events.append(("stop", reason))

    class FakeInputState:
        def reset_armed(self) -> None:
            events.append(("armed", None))

        def clear_mouse_block(self) -> None:
            events.append(("mouse", None))

    class FakeSyntheticGuard:
        def reset(self) -> None:
            events.append(("synthetic", None))

    runtime.macro_lock = FakeMacroLock()
    runtime.input_state = FakeInputState()
    runtime.synthetic_guard = FakeSyntheticGuard()
    runtime.logger = logging.getLogger("test-runtime-lazy-macros")
    runtime._emit_status = lambda text: events.append(("status", text))
    monkeypatch.setattr(runtime_module, "release_common_inputs", lambda: events.append(("release", None)))

    for name in _MACRO_MODULES:
        monkeypatch.delitem(sys.modules, name, raising=False)

    runtime.emergency_stop("test")

    assert runtime._switch_click is None
    assert runtime._direction is None
    assert all(name not in sys.modules for name in _MACRO_MODULES)
    assert ("stop", "test") in events
    assert ("release", None) in events


def test_emergency_stop_resets_only_materialized_macros(monkeypatch) -> None:
    runtime = _bare_runtime()
    resets: list[str] = []

    class FakeSwitchClick:
        def reset(self) -> None:
            resets.append("click")

    class FakeDirection:
        def release_virtual_inputs(self) -> None:
            resets.append("direction")

    class NoopMacroLock:
        def request_stop(self, _reason: str) -> None:
            pass

    class NoopInputState:
        def reset_armed(self) -> None:
            pass

        def clear_mouse_block(self) -> None:
            pass

    class NoopGuard:
        def reset(self) -> None:
            pass

    runtime._switch_click = FakeSwitchClick()
    runtime._direction = FakeDirection()
    runtime.macro_lock = NoopMacroLock()
    runtime.input_state = NoopInputState()
    runtime.synthetic_guard = NoopGuard()
    runtime.logger = logging.getLogger("test-runtime-lazy-macros-materialized")
    runtime._emit_status = lambda _text: None
    monkeypatch.setattr(runtime_module, "release_common_inputs", lambda: None)

    runtime.emergency_stop("test")

    assert resets == ["click", "direction"]
