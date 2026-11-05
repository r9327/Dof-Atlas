from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.runtime_state import AtlasRuntime


class MirrorFocusAdmissionTests(unittest.TestCase):
    """Never swallow physical input after focus changes during Win32 preflight."""

    def _runtime(self, count: int):
        handles = tuple(range(101, 101 + count))
        source = handles[-1]  # A favorite may be in the final Organizer slot.
        clients = tuple(SimpleNamespace(handle=hwnd) for hwnd in handles)
        settings = SimpleNamespace(
            macro_mode="mirror",
            primary_handle=source,
            clients=clients,
            client_by_handle=lambda hwnd: next(
                (client for client in clients if client.handle == hwnd), None
            ),
        )
        runtime = Mock()
        runtime.settings = settings
        runtime._running = True
        runtime._admin_ok = True
        runtime.macro_lock.active_label = ""
        runtime.macro_lock.should_stop.return_value = False
        runtime._mirror_gesture_targets.side_effect = (
            lambda: AtlasRuntime._mirror_gesture_targets(runtime)
        )
        runtime.mirror_input.run_key.return_value = True
        runtime.mirror_input.run_wheel.return_value = True
        runtime.switch_click.run_async.return_value = True
        return runtime, source

    def test_source_focus_stolen_during_identity_probe_2_4_6_8(self):
        for count in (2, 4, 6, 8):
            for gesture in ("key", "wheel", "click"):
                with self.subTest(count=count, gesture=gesture):
                    runtime, source = self._runtime(count)
                    focused = [source]

                    def probe(hwnd):
                        if hwnd != source:
                            focused[0] = 999  # A non-DOFUS app took focus.
                        return True

                    with (
                        patch(
                            "app.windows.unity_windows.foreground_window",
                            side_effect=lambda: focused[0],
                        ),
                        patch(
                            "app.windows.unity_windows.is_unity_window",
                            return_value=True,
                        ),
                        patch(
                            "app.macros.mirror_plan.is_dofus_unity_process",
                            side_effect=probe,
                        ),
                        patch(
                            "app.windows.unity_windows.find_known_client_from_point",
                            return_value=source,
                        ),
                        patch(
                            "app.windows.unity_windows.screen_to_client",
                            return_value=(5, 10),
                        ),
                        patch(
                            "app.windows.unity_windows.client_point_ratio",
                            return_value=(0.5, 0.5),
                        ),
                    ):
                        if gesture == "key":
                            consumed = AtlasRuntime._handle_mirror_key(
                                runtime, 65, True,
                            )
                        elif gesture == "wheel":
                            consumed = AtlasRuntime._handle_mirror_wheel(
                                runtime, 120, 20, 25, False,
                            )
                        else:
                            consumed = AtlasRuntime._handle_mirror_click(
                                runtime, "Left", 20, 25,
                            )
                    self.assertEqual(focused[0], 999)
                    self.assertFalse(consumed)
                    runtime.mirror_input.run_key.assert_not_called()
                    runtime.mirror_input.run_wheel.assert_not_called()
                    runtime.switch_click.run_async.assert_not_called()

    def test_focus_lost_during_wheel_coordinate_conversion_2_4_6_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime, source = self._runtime(count)
                focused = [source]

                def convert(*_args):
                    focused[0] = 999
                    return (0.5, 0.5)

                with (
                    patch(
                        "app.windows.unity_windows.foreground_window",
                        side_effect=lambda: focused[0],
                    ),
                    patch(
                        "app.windows.unity_windows.is_unity_window",
                        return_value=True,
                    ),
                    patch(
                        "app.macros.mirror_plan.is_dofus_unity_process",
                        return_value=True,
                    ),
                    patch(
                        "app.windows.unity_windows.find_known_client_from_point",
                        return_value=source,
                    ),
                    patch(
                        "app.windows.unity_windows.screen_to_client",
                        return_value=(5, 10),
                    ),
                    patch(
                        "app.windows.unity_windows.client_point_ratio",
                        side_effect=convert,
                    ),
                ):
                    consumed = AtlasRuntime._handle_mirror_wheel(
                        runtime, 120, 20, 25, False,
                    )
                self.assertEqual(focused[0], 999)
                self.assertFalse(consumed)
                runtime.mirror_input.run_wheel.assert_not_called()


    def test_busy_secondary_focus_stolen_during_identity_probe(self):
        for count in (2, 4, 6, 8):
            for gesture in ("key", "wheel"):
                with self.subTest(count=count, gesture=gesture):
                    runtime, source = self._runtime(count)
                    runtime.macro_lock.active_label = "Miroir"
                    focused = [101]  # A registered secondary, not the favorite.

                    def probe(hwnd):
                        self.assertEqual(hwnd, 101)
                        focused[0] = 999
                        return True

                    with (
                        patch(
                            "app.windows.unity_windows.foreground_window",
                            side_effect=lambda: focused[0],
                        ),
                        patch(
                            "app.macros.mirror_plan.is_dofus_unity_process",
                            side_effect=probe,
                        ),
                    ):
                        if gesture == "key":
                            consumed = AtlasRuntime._handle_mirror_key(
                                runtime, 65, True,
                            )
                        else:
                            consumed = AtlasRuntime._handle_mirror_wheel(
                                runtime, 120, 20, 25, False,
                            )
                    self.assertNotEqual(focused[0], source)
                    self.assertFalse(consumed)
                    runtime._emit_status.assert_not_called()
                    runtime.mirror_input.run_key.assert_not_called()
                    runtime.mirror_input.run_wheel.assert_not_called()

    def test_busy_secondary_current_roster_remains_fail_closed(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime, _source = self._runtime(count)
                runtime.macro_lock.active_label = "Miroir"
                with (
                    patch(
                        "app.windows.unity_windows.foreground_window",
                        return_value=101,
                    ),
                    patch(
                        "app.macros.mirror_plan.is_dofus_unity_process",
                        return_value=True,
                    ),
                ):
                    self.assertTrue(AtlasRuntime._handle_mirror_key(
                        runtime, 65, True,
                    ))
                    self.assertTrue(AtlasRuntime._handle_mirror_wheel(
                        runtime, 120, 20, 25, False,
                    ))
                runtime.mirror_input.run_key.assert_not_called()
                runtime.mirror_input.run_wheel.assert_not_called()




if __name__ == "__main__":
    unittest.main()
