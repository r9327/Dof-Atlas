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
    def test_noop_runtime_reload_preserves_mirror_consent_but_profile_change_revokes_it(self):
        from types import SimpleNamespace
        from app.core.macro_lock import MacroLock

        runtime = object.__new__(AtlasRuntime)
        runtime._settings_lock = threading.RLock()
        initial = SimpleNamespace(
            macro_mode="mirror", primary_handle=101, debug_enabled=False,
            mirror_toggle_hotkey="F8",
            clients=(
                SimpleNamespace(index=1, handle=101),
                SimpleNamespace(index=2, handle=202),
            ),
        )
        runtime._settings = initial
        runtime._mirror_armed = True
        runtime._mirror_arm_epoch = 1
        runtime._running = True
        runtime._admin_ok = True
        runtime.registry = Mock()
        runtime.registry.register_hotkeys.return_value = SimpleNamespace(errors=[])
        runtime.synthetic_guard = Mock()
        runtime.input_state = Mock()
        runtime.macro_lock = MacroLock(Mock())
        runtime.logger = Mock()
        runtime._emit_active = Mock()
        runtime._emit_status = Mock()
        runtime._pending_physical_switch = None
        identical = SimpleNamespace(**initial.__dict__)
        changed = SimpleNamespace(**{**initial.__dict__, "primary_handle": 202})

        with (
            patch("app.core.runtime_state.load_settings", side_effect=[identical, changed]),
            patch("app.core.runtime_state.set_debug_logging"),
            patch("app.core.runtime_state.build_runtime_hotkey_actions", return_value=[]),
            patch("app.core.runtime_state.audit_client_admin_rights",
                  return_value=SimpleNamespace(ok=True)),
        ):
            runtime.reload_hotkeys()
            self.assertTrue(runtime.mirror_armed)
            self.assertIs(runtime.settings, identical)
            runtime.reload_hotkeys()
            self.assertFalse(runtime.mirror_armed)
            self.assertIs(runtime.settings, changed)

    def test_reload_does_not_rearm_mirror_after_concurrent_stop_epoch_change(self):
        from types import SimpleNamespace
        from app.core.macro_lock import MacroLock

        runtime = object.__new__(AtlasRuntime)
        runtime._settings_lock = threading.RLock()
        profile = SimpleNamespace(
            macro_mode="mirror", primary_handle=101, debug_enabled=False,
            clients=(SimpleNamespace(handle=101), SimpleNamespace(handle=202)),
        )
        runtime._settings = profile
        runtime._mirror_armed = True
        runtime._mirror_arm_epoch = 3
        runtime._running = True
        runtime._admin_ok = True
        runtime.registry = Mock()
        runtime.registry.register_hotkeys.return_value = SimpleNamespace(errors=[])
        runtime.synthetic_guard = Mock()
        runtime.input_state = Mock()
        runtime.macro_lock = MacroLock(Mock())
        runtime.logger = Mock()
        runtime._emit_active = Mock()
        runtime._emit_status = Mock()

        def concurrent_stop():
            runtime._mirror_arm_epoch += 1
            runtime._mirror_armed = False
            runtime.macro_lock.request_stop("bouton stop", latch=True)
            return SimpleNamespace(**profile.__dict__)

        with (
            patch("app.core.runtime_state.load_settings", side_effect=concurrent_stop),
            patch("app.core.runtime_state.set_debug_logging"),
            patch("app.core.runtime_state.build_runtime_hotkey_actions", return_value=[]),
            patch("app.core.runtime_state.audit_client_admin_rights",
                  return_value=SimpleNamespace(ok=True)),
        ):
            runtime.reload_hotkeys()
        self.assertFalse(runtime.mirror_armed)
        self.assertTrue(runtime.macro_lock.emergency_latched)

    def test_disarmed_mirror_never_probes_or_consumes_native_input(self):
        from types import SimpleNamespace
        from app.core.macro_lock import MacroLock
        fake = SimpleNamespace(
            _mirror_armed=False, _running=True, _admin_ok=True,
            settings=SimpleNamespace(
                macro_mode="mirror", primary_handle=101,
                clients=[SimpleNamespace(handle=101), SimpleNamespace(handle=102)],
            ),
            macro_lock=MacroLock(Mock()),
        )
        with patch("app.windows.unity_windows.foreground_window") as native:
            self.assertFalse(AtlasRuntime._handle_mirror_click(fake, "left", 10, 20))
            self.assertFalse(AtlasRuntime._handle_mirror_key(fake, 0x41, True))
            self.assertFalse(AtlasRuntime._handle_mirror_wheel(fake, 120, 10, 20, False))
        native.assert_not_called()

    def test_zaap_and_auto_group_reject_latched_stop_before_native_actions(self):
        from app.core.macro_lock import MacroLock

        runtime = object.__new__(AtlasRuntime)
        runtime.macro_lock = MacroLock(Mock())
        runtime._zaap = Mock()
        runtime._auto_group = Mock()
        runtime._emit_status = Mock()
        runtime.logger = Mock()
        runtime.macro_lock.request_stop("bouton stop", latch=True)
        self.assertFalse(runtime.launch_zaap("/zaap 1,2"))
        self.assertFalse(runtime.launch_auto_group([{"name": "Panda", "handle": 101}]))
        runtime._zaap.run_async.assert_not_called()
        runtime._auto_group.run_async.assert_not_called()
        self.assertEqual(runtime._emit_status.call_count, 2)
        self.assertIn("Stop urgence actif", runtime._emit_status.call_args.args[0])

    def test_runtime_indicator_remains_red_during_emergency_latch(self):
        from app.core.macro_lock import MacroLock

        runtime = object.__new__(AtlasRuntime)
        runtime.macro_lock = MacroLock(Mock())
        runtime._callback_bridge = None
        runtime.active_callback = Mock()
        runtime._emit_active(True)
        runtime.active_callback.assert_called_with(True)
        runtime.macro_lock.request_stop("bouton stop", latch=True)
        runtime._emit_active(True)  # A routine hotkey reload cannot turn green.
        runtime.active_callback.assert_called_with(False)
        self.assertTrue(runtime.macro_lock.resume_after_stop())
        runtime._emit_active(True)
        runtime.active_callback.assert_called_with(True)

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
