from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

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


def test_zaap_restores_favorite_after_chat_failure() -> None:
    runtime = _runtime()
    macro = ZaapMacro(runtime)
    with (
        patch("app.macros.zaap.is_unity_window", return_value=True),
        patch("app.macros.zaap.activate_window", return_value=True),
        patch("app.macros.zaap.send_chat_command", side_effect=RuntimeError("chat failed")),
    ):
        with pytest.raises(RuntimeError, match="chat failed"):
            macro._run("/zaap 1,2")
    runtime.switch_character.restore_preferred_client.assert_called_once_with("Auto zaap")


def test_zaap_never_refocuses_after_emergency_stop() -> None:
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
        patch("app.macros.zaap.send_chat_command", side_effect=stop_during_chat),
    ):
        ZaapMacro(runtime)._run("/zaap -5,12")
    runtime.switch_character.restore_preferred_client.assert_not_called()


def test_direction_restores_favorite_on_input_exception() -> None:
    runtime = _runtime()
    runtime.settings.client_by_handle.return_value = object()
    with (
        patch("app.macros.direction.foreground_window", return_value=101),
        patch("app.macros.direction.is_unity_window", return_value=True),
        patch("app.macros.direction.activate_window", return_value=True),
        patch("app.macros.direction.press_key", side_effect=RuntimeError("key failed")),
    ):
        with pytest.raises(RuntimeError, match="key failed"):
            DirectionMacro(runtime)._run("HOME")
    runtime.switch_character.restore_preferred_client.assert_called_once_with("Switch deplacement")


def test_direction_does_not_restore_on_stop() -> None:
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


def test_zaap_partial_delivery_is_not_reported_as_complete() -> None:
    runtime = _runtime()
    with (
        patch("app.macros.zaap.is_unity_window", return_value=True),
        patch("app.macros.zaap.activate_window", return_value=True),
        patch("app.macros.zaap.send_chat_command", side_effect=[True, False]),
    ):
        ZaapMacro(runtime)._run("/zaap 1,2")
    runtime.logger.info.assert_any_call("Auto zaap %s: envoyes=%s/%s", "partiel", 1, 2)
