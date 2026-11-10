"""Direct regression contracts for the runtime emergency Stop owner.

Other Organizer suites exercise cross-module flows; these tests pin the
canonical cleanup contract for app/core/runtime_state.py specifically.
"""
from __future__ import annotations

import threading
import unittest
from unittest.mock import Mock, patch

from app.core.runtime_state import AtlasRuntime


def _runtime() -> AtlasRuntime:
    runtime = object.__new__(AtlasRuntime)
    runtime.logger = Mock()
    runtime.macro_lock = Mock()
    runtime.input_state = Mock()
    runtime.synthetic_guard = Mock()
    runtime._macro_init_lock = threading.RLock()
    runtime._switch_click = Mock()
    runtime._direction = Mock()
    runtime._pending_physical_switch = object()
    runtime._emit_status = Mock()
    runtime._emit_active = Mock()
    return runtime


class RuntimeStopOwnerTests(unittest.TestCase):
    def test_stop_runs_every_cleanup_after_failed_previous_cleanup_2_to_8(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                runtime = _runtime()
                runtime.logger.exception.side_effect = RuntimeError("logging down")
                runtime.logger.warning.side_effect = RuntimeError("logging down")
                runtime.input_state.reset_armed.side_effect = OSError("state")
                runtime._switch_click.reset.side_effect = OSError("switch")
                runtime._direction.release_virtual_inputs.side_effect = OSError("keys")
                with patch(
                    "app.core.runtime_state.release_common_inputs",
                    side_effect=OSError("mouse"),
                ) as common:
                    runtime.emergency_stop("P0")
                runtime.macro_lock.request_stop.assert_called_once_with("P0", latch=True)
                runtime.input_state.reset_armed.assert_called_once()
                runtime.input_state.clear_mouse_block.assert_called_once()
                runtime.synthetic_guard.reset.assert_called_once()
                runtime._switch_click.reset.assert_called_once()
                runtime._direction.release_virtual_inputs.assert_called_once()
                common.assert_called_once()
                self.assertIsNone(runtime._pending_physical_switch)
                runtime._emit_status.assert_called_once_with(
                    "Stop urgence: interruption demandée, relâchements à vérifier."
                )
                runtime._emit_active.assert_called_once_with(False)

    def test_native_release_false_reports_incomplete_stop_without_exception(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                runtime = _runtime()
                runtime._direction.release_virtual_inputs.return_value = False
                with patch(
                    "app.core.runtime_state.release_common_inputs",
                    return_value=False,
                ) as common:
                    runtime.emergency_stop("P0")
                runtime.macro_lock.request_stop.assert_called_once_with("P0", latch=True)
                runtime.input_state.clear_mouse_block.assert_called_once()
                runtime.synthetic_guard.reset.assert_called_once()
                runtime._direction.release_virtual_inputs.assert_called_once()
                common.assert_called_once()
                runtime.logger.warning.assert_any_call(
                    "Stop urgence: relachement refuse step=%s", "direction",
                )
                runtime.logger.warning.assert_any_call(
                    "Stop urgence: relachement refuse step=%s", "common_inputs",
                )
                runtime.logger.warning.assert_any_call(
                    "Stop urgence Python: nettoyage incomplet steps=%s",
                    "direction,common_inputs",
                )
                runtime._emit_status.assert_called_once_with(
                    "Stop urgence: interruption demandée, relâchements à vérifier."
                )

    def test_stop_without_lazy_macros_still_releases_inputs_2_to_8(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                runtime = _runtime()
                runtime._switch_click = None
                runtime._direction = None
                events = []
                runtime.macro_lock.request_stop.side_effect = (
                    lambda _reason, **_kwargs: events.append("stop")
                )
                runtime.input_state.reset_armed.side_effect = (
                    lambda: events.append("armed")
                )
                runtime.input_state.clear_mouse_block.side_effect = (
                    lambda: events.append("pointer")
                )
                runtime.synthetic_guard.reset.side_effect = (
                    lambda: events.append("guard")
                )
                with patch(
                    "app.core.runtime_state.release_common_inputs",
                    side_effect=lambda: events.append("release"),
                ) as common:
                    runtime.emergency_stop()
                self.assertEqual(events, [
                    "stop", "armed", "pointer", "guard", "release",
                ])
                common.assert_called_once()
                runtime._emit_status.assert_called_once_with(
                    "Stop urgence: macros Python arretees."
                )

    def test_hotkey_stop_runs_before_logger_and_survives_logging_failure(self):
        # The native keyboard callback must never lose emergency Stop
        # because an optional telemetry sink raises. Independent of roster.
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                runtime = _runtime()
                order = []
                runtime.macro_lock.request_stop.side_effect = (
                    lambda reason, **_kwargs: order.append(("stop", reason))
                )
                def broken_warning(*_args):
                    order.append(("log", None))
                    raise OSError("log unavailable")

                runtime.logger.warning.side_effect = broken_warning
                with patch(
                    "app.core.runtime_state.release_common_inputs",
                    return_value=True,
                ) as common:
                    runtime._handle_hotkey("stop_script", {})
                self.assertEqual(order[0], ("stop", "raccourci"))
                self.assertEqual(order[-1], ("log", None))
                runtime.input_state.clear_mouse_block.assert_called_once()
                runtime.synthetic_guard.reset.assert_called_once()
                common.assert_called_once()
                runtime._emit_status.assert_called_once_with(
                    "Stop urgence: macros Python arretees."
                )


if __name__ == "__main__":
    unittest.main()
