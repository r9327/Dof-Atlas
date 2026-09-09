from __future__ import annotations

from types import SimpleNamespace

from app.core import runtime_state


def test_runtime_constructor_does_not_load_settings(monkeypatch) -> None:
    load_calls = 0
    debug_values: list[bool] = []

    def fake_load_settings():
        nonlocal load_calls
        load_calls += 1
        return SimpleNamespace(debug_enabled=True)

    monkeypatch.setattr(runtime_state, "load_settings", fake_load_settings)
    monkeypatch.setattr(runtime_state, "set_debug_logging", debug_values.append)

    runtime = runtime_state.AtlasRuntime()

    assert load_calls == 0
    assert debug_values == []
    assert runtime._settings is None


def test_runtime_settings_load_once_on_first_access(monkeypatch) -> None:
    load_calls = 0
    debug_values: list[bool] = []
    expected = SimpleNamespace(debug_enabled=True)

    def fake_load_settings():
        nonlocal load_calls
        load_calls += 1
        return expected

    monkeypatch.setattr(runtime_state, "load_settings", fake_load_settings)
    monkeypatch.setattr(runtime_state, "set_debug_logging", debug_values.append)
    runtime = runtime_state.AtlasRuntime()

    first = runtime.settings
    second = runtime.settings

    assert first is expected
    assert second is expected
    assert load_calls == 1
    assert debug_values == [True]


def test_runtime_settings_injection_does_not_trigger_disk_load(monkeypatch) -> None:
    load_calls = 0
    injected = SimpleNamespace(debug_enabled=False)

    def fake_load_settings():
        nonlocal load_calls
        load_calls += 1
        return SimpleNamespace(debug_enabled=True)

    monkeypatch.setattr(runtime_state, "load_settings", fake_load_settings)
    runtime = runtime_state.AtlasRuntime()

    runtime.settings = injected

    assert runtime.settings is injected
    assert load_calls == 0
