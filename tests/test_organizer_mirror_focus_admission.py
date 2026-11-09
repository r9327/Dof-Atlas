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
        runtime.macro_lock.active_generation = 1
        runtime.macro_lock.owns.side_effect = lambda label, generation: (
            runtime.macro_lock.active_label == label
            and runtime.macro_lock.active_generation == generation
        )
        runtime.macro_lock.snapshot_active.side_effect = lambda: (
            (runtime.macro_lock.active_label, runtime.macro_lock.active_generation)
            if runtime.macro_lock.active_label else None
        )
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




    def test_busy_secondary_native_fallback_2_4_6_8_no_pointer_lease(self):
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel"):
                with self.subTest(count=count, kind=kind):
                    runtime, source = self._runtime(count)
                    runtime.input_state = InputState()
                    runtime.macro_lock.active_label = "Miroir clavier"
                    secondary = 101
                    self.assertNotEqual(source, secondary)
                    with (
                        patch(
                            "app.windows.unity_windows.foreground_window",
                            return_value=secondary,
                        ),
                        patch(
                            "app.macros.mirror_plan.is_dofus_unity_process",
                            return_value=True,
                        ),
                    ):
                        if kind == "key":
                            consumed = AtlasRuntime._handle_mirror_key(
                                runtime, 65, True,
                            )
                        else:
                            consumed = AtlasRuntime._handle_mirror_wheel(
                                runtime, 120, 20, 25, False,
                            )
                    self.assertFalse(consumed)
                    runtime._emit_status.assert_called_once_with(
                        "Miroir desynchronise : geste non diffuse sur tous les comptes."
                    )
                    runtime.mirror_input.run_key.assert_not_called()
                    runtime.mirror_input.run_wheel.assert_not_called()

    def test_busy_secondary_pointer_lease_remains_guarded(self):
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel"):
                with self.subTest(count=count, kind=kind):
                    runtime, _source = self._runtime(count)
                    runtime.input_state = InputState()
                    runtime.input_state.begin_mouse_block("Miroir molette")
                    runtime.macro_lock.active_label = "Miroir molette"
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
                        if kind == "key":
                            consumed = AtlasRuntime._handle_mirror_key(
                                runtime, 65, True,
                            )
                        else:
                            consumed = AtlasRuntime._handle_mirror_wheel(
                                runtime, 120, 20, 25, False,
                            )
                    self.assertTrue(consumed)
                    runtime.mirror_input.run_key.assert_not_called()
                    runtime.mirror_input.run_wheel.assert_not_called()
                    runtime.input_state.end_mouse_block()

    def test_runtime_stop_during_native_identity_never_consumes_click_key_or_wheel(self):
        for count in (2, 4, 6, 8):
            for kind in ("click", "key", "wheel"):
                with self.subTest(count=count, kind=kind):
                    runtime, source = self._runtime(count)
                    def identity(hwnd):
                        if hwnd != source:
                            runtime._running = False
                        return True
                    with (
                        patch("app.windows.unity_windows.foreground_window",
                              return_value=source),
                        patch("app.windows.unity_windows.is_unity_window",
                              return_value=True),
                        patch("app.macros.mirror_plan.is_dofus_unity_process",
                              side_effect=identity),
                        patch("app.windows.unity_windows.find_known_client_from_point",
                              return_value=source),
                        patch("app.windows.unity_windows.screen_to_client",
                              return_value=(10, 10)),
                        patch("app.windows.unity_windows.client_point_ratio",
                              return_value=(0.4, 0.4)),
                    ):
                        if kind == "click":
                            consumed = AtlasRuntime._handle_mirror_click(
                                runtime, "Left", 10, 10,
                            )
                        elif kind == "key":
                            consumed = AtlasRuntime._handle_mirror_key(
                                runtime, 65, True,
                            )
                        else:
                            consumed = AtlasRuntime._handle_mirror_wheel(
                                runtime, 120, 10, 10, False,
                            )
                    self.assertFalse(consumed)
                    runtime.switch_click.run_async.assert_not_called()
                    runtime.mirror_input.run_key.assert_not_called()
                    runtime.mirror_input.run_wheel.assert_not_called()

    def test_runtime_stop_during_wheel_coordinates_releases_physical_tick(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime, source = self._runtime(count)
                def convert(*_args):
                    runtime._running = False
                    return (0.3, 0.7)
                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=source),
                    patch("app.windows.unity_windows.is_unity_window",
                          return_value=True),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=True),
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          return_value=source),
                    patch("app.windows.unity_windows.screen_to_client",
                          return_value=(5, 8)),
                    patch("app.windows.unity_windows.client_point_ratio",
                          side_effect=convert),
                ):
                    self.assertFalse(AtlasRuntime._handle_mirror_wheel(
                        runtime, 120, 12, 18, False,
                    ))
                runtime.mirror_input.run_wheel.assert_not_called()



    def test_busy_no_pointer_lease_skips_expensive_native_identity(self):
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel"):
                with self.subTest(clients=count, kind=kind):
                    runtime, source = self._runtime(count)
                    runtime.input_state = InputState()
                    runtime.macro_lock.active_label = "Miroir clavier"
                    self.assertNotEqual(source, 101)
                    with (
                        patch("app.windows.unity_windows.foreground_window",
                              return_value=101),
                        patch("app.macros.mirror_plan.is_dofus_unity_process",
                              side_effect=AssertionError("unneeded Win32 probe")) as identity,
                    ):
                        if kind == "key":
                            consumed = AtlasRuntime._handle_mirror_key(
                                runtime, 65, True,
                            )
                        else:
                            consumed = AtlasRuntime._handle_mirror_wheel(
                                runtime, 120, 12, 13, False,
                            )
                    self.assertFalse(consumed)
                    identity.assert_not_called()
                    runtime.mirror_input.run_key.assert_not_called()
                    runtime.mirror_input.run_wheel.assert_not_called()
                    runtime._emit_status.assert_called_once_with(
                        "Miroir desynchronise : geste non diffuse sur tous les comptes."
                    )

    def test_busy_no_pointer_lease_does_not_report_foreign_application(self):
        from app.input.input_state import InputState

        for kind in ("key", "wheel"):
            with self.subTest(kind=kind):
                runtime, _source = self._runtime(8)
                runtime.input_state = InputState()
                runtime.macro_lock.active_label = "Miroir clavier"
                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=999),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          side_effect=AssertionError("foreign app probed")) as identity,
                ):
                    consumed = (
                        AtlasRuntime._handle_mirror_key(runtime, 65, True)
                        if kind == "key" else
                        AtlasRuntime._handle_mirror_wheel(
                            runtime, 120, 12, 13, False,
                        )
                    )
                self.assertFalse(consumed)
                identity.assert_not_called()
                runtime._emit_status.assert_not_called()



    def test_busy_secondary_new_same_named_worker_never_consumes_old_input(self):
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            for gesture in ("key", "wheel"):
                for mutation in ("probe", "status"):
                    with self.subTest(count=count, gesture=gesture, mutation=mutation):
                        runtime, source = self._runtime(count)
                        runtime.input_state = InputState()
                        runtime.input_state.begin_mouse_block("Miroir molette")
                        runtime.macro_lock.active_label = "Miroir molette"
                        runtime.macro_lock.active_generation = 42

                        def during_probe(_hwnd):
                            if mutation == "probe":
                                runtime.macro_lock.active_generation = 43
                            return True

                        def during_status(_runtime, _kind):
                            if mutation == "status":
                                runtime.macro_lock.active_generation = 43

                        with (
                            patch("app.windows.unity_windows.foreground_window",
                                  return_value=101),
                            patch("app.macros.mirror_plan.is_dofus_unity_process",
                                  side_effect=during_probe),
                            patch.object(AtlasRuntime, "_report_mirror_busy_input",
                                         side_effect=during_status) as notice,
                        ):
                            if gesture == "key":
                                consumed = AtlasRuntime._handle_mirror_key(
                                    runtime, 65, True,
                                )
                            else:
                                consumed = AtlasRuntime._handle_mirror_wheel(
                                    runtime, 120, 20, 25, False,
                                )
                        self.assertFalse(consumed)
                        self.assertNotEqual(source, 101)
                        self.assertEqual(notice.call_count, int(mutation == "status"))
                        runtime.mirror_input.run_key.assert_not_called()
                        runtime.mirror_input.run_wheel.assert_not_called()
                        runtime.input_state.end_mouse_block()



    def test_atomic_owner_replaced_during_hook_snapshot_keeps_native_input(self):
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            for gesture in ("key", "wheel", "click"):
                with self.subTest(count=count, gesture=gesture):
                    runtime, source = self._runtime(count)
                    runtime.input_state = InputState()
                    runtime.input_state.begin_mouse_block("Miroir")
                    runtime.macro_lock.active_label = "Miroir"
                    runtime.macro_lock.active_generation = 17

                    def swapped_snapshot():
                        runtime.macro_lock.active_generation = 18
                        return ("Miroir", 17)

                    runtime.macro_lock.snapshot_active.side_effect = swapped_snapshot
                    with (
                        patch("app.windows.unity_windows.foreground_window",
                              return_value=source),
                        patch("app.macros.mirror_plan.is_dofus_unity_process") as probe,
                    ):
                        if gesture == "key":
                            accepted = AtlasRuntime._handle_mirror_key(
                                runtime, 65, True,
                            )
                        elif gesture == "wheel":
                            accepted = AtlasRuntime._handle_mirror_wheel(
                                runtime, 120, 20, 25, False,
                            )
                        else:
                            accepted = AtlasRuntime._handle_mirror_click(
                                runtime, "Left", 20, 25,
                            )
                    self.assertFalse(accepted)
                    probe.assert_not_called()
                    runtime.mirror_input.run_key.assert_not_called()
                    runtime.mirror_input.run_wheel.assert_not_called()
                    runtime.switch_click.run_async.assert_not_called()
                    runtime.input_state.end_mouse_block()



    def test_restarted_worker_during_foreground_probe_keeps_old_input_native(self):
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            for gesture in ("key", "wheel"):
                with self.subTest(accounts=count, gesture=gesture):
                    runtime, source = self._runtime(count)
                    runtime.input_state = InputState()
                    runtime.input_state.begin_mouse_block("Miroir")
                    runtime.macro_lock.active_label = "Miroir"
                    runtime.macro_lock.active_generation = 61

                    def native_focus_probe():
                        # Native Win32 query yields while an old worker ends
                        # and a new Miroir takes the same label/pointer.
                        runtime.macro_lock.active_generation = 62
                        return 101

                    with (
                        patch("app.windows.unity_windows.foreground_window",
                              side_effect=native_focus_probe),
                        patch("app.macros.mirror_plan.is_dofus_unity_process") as native,
                    ):
                        if gesture == "key":
                            accepted = AtlasRuntime._handle_mirror_key(
                                runtime, 65, True,
                            )
                        else:
                            accepted = AtlasRuntime._handle_mirror_wheel(
                                runtime, 120, 20, 25, False,
                            )
                    self.assertFalse(accepted)
                    self.assertNotEqual(source, 101)
                    native.assert_not_called()
                    runtime._emit_status.assert_not_called()
                    runtime.mirror_input.run_key.assert_not_called()
                    runtime.mirror_input.run_wheel.assert_not_called()
                    runtime.input_state.end_mouse_block()



    def test_malformed_client_handle_remains_native_2_4_6_8(self):
        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel", "click"):
                with self.subTest(accounts=count, kind=kind):
                    runtime, source = self._runtime(count)
                    runtime.settings.clients = (
                        object(), *runtime.settings.clients[1:],
                    )
                    with (
                        patch("app.windows.unity_windows.foreground_window",
                              return_value=source),
                        patch("app.windows.unity_windows.is_unity_window",
                              side_effect=AssertionError("unexpected native probe")),
                        patch("app.windows.unity_windows.find_known_client_from_point",
                              return_value=source),
                    ):
                        if kind == "key":
                            consumed = AtlasRuntime._handle_mirror_key(
                                runtime, 65, True,
                            )
                        elif kind == "wheel":
                            consumed = AtlasRuntime._handle_mirror_wheel(
                                runtime, 120, 20, 25, False,
                            )
                        else:
                            consumed = AtlasRuntime._handle_mirror_click(
                                runtime, "Left", 20, 25,
                            )
                    self.assertFalse(consumed)
                    runtime.mirror_input.run_key.assert_not_called()
                    runtime.mirror_input.run_wheel.assert_not_called()
                    runtime.switch_click.run_async.assert_not_called()

    def test_malformed_client_appears_during_process_scan(self):
        for count in (2, 4, 6, 8):
            runtime, source = self._runtime(count)
            def mutate(hwnd):
                if hwnd != source:
                    runtime.settings.clients = (
                        object(), *runtime.settings.clients[1:],
                    )
                return True
            with (
                patch("app.windows.unity_windows.is_unity_window",
                      return_value=True),
                patch("app.macros.mirror_plan.is_dofus_unity_process",
                      side_effect=mutate),
            ):
                self.assertIsNone(
                    AtlasRuntime._mirror_gesture_targets(runtime)
                )
            runtime.mirror_input.run_key.assert_not_called()



    def test_detached_profile_does_not_consume_native_gestures(self):
        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                runtime, source = self._runtime(count)
                runtime.settings = None
                with (
                    patch(
                        "app.windows.unity_windows.foreground_window",
                        side_effect=AssertionError("unexpected Win32 focus probe"),
                    ),
                    patch(
                        "app.windows.unity_windows.is_unity_window",
                        side_effect=AssertionError("unexpected Unity probe"),
                    ),
                    patch(
                        "app.macros.mirror_plan.is_dofus_unity_process",
                        side_effect=AssertionError("unexpected process probe"),
                    ),
                ):
                    self.assertIsNone(
                        AtlasRuntime._mirror_gesture_targets(runtime)
                    )
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_key(runtime, 65, True)
                    )
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_wheel(
                            runtime, 120, 20, 25, False,
                        )
                    )
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_click(
                            runtime, "Left", 20, 25,
                        )
                    )
                    self.assertFalse(
                        AtlasRuntime._handle_mouse_click(
                            runtime, "Left", 20, 25,
                        )
                    )
                runtime.mirror_input.run_key.assert_not_called()
                runtime.mirror_input.run_wheel.assert_not_called()
                runtime.switch_click.run_async.assert_not_called()


    def test_missing_or_failed_favorite_lookup_preserves_native_click(self):
        for count in (2, 4, 6, 8):
            for failure in ("missing", "raises"):
                with self.subTest(accounts=count, failure=failure):
                    runtime, source = self._runtime(count)
                    if failure == "missing":
                        runtime.settings.client_by_handle = None
                    else:
                        runtime.settings.client_by_handle = Mock(
                            side_effect=RuntimeError("detached lookup"),
                        )
                    with (
                        patch(
                            "app.windows.unity_windows.foreground_window",
                            return_value=source,
                        ),
                        patch(
                            "app.windows.unity_windows.find_known_client_from_point",
                            return_value=source,
                        ),
                        patch(
                            "app.windows.unity_windows.is_unity_window",
                            side_effect=AssertionError("unexpected Unity probe"),
                        ),
                        patch(
                            "app.macros.mirror_plan.is_dofus_unity_process",
                            side_effect=AssertionError("unexpected process probe"),
                        ),
                    ):
                        self.assertIsNone(
                            AtlasRuntime._mirror_gesture_targets(runtime)
                        )
                        self.assertFalse(
                            AtlasRuntime._handle_mirror_click(
                                runtime, "Left", 20, 25,
                            )
                        )
                    runtime.switch_click.run_async.assert_not_called()
                    if failure == "raises":
                        self.assertTrue(runtime.logger.exception.called)


    def test_client_roster_detaches_between_native_hook_reads(self):
        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                runtime, source = self._runtime(count)
                original = runtime.settings
                original_clients = original.clients

                class FlippingProfile:
                    macro_mode = "mirror"
                    primary_handle = source

                    def __init__(self):
                        # Instance binding prevents a function-valued
                        # resolver from becoming an implicit bound method.
                        self.client_by_handle = original.client_by_handle
                        self.reads = 0

                    @property
                    def clients(self):
                        self.reads += 1
                        if self.reads == 1:
                            return original_clients
                        return None

                runtime.settings = FlippingProfile()
                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=source),
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          return_value=source),
                    patch("app.windows.unity_windows.is_unity_window",
                          return_value=True),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=True),
                ):
                    self.assertFalse(AtlasRuntime._handle_mirror_click(
                        runtime, "Left", 20, 25,
                    ))
                self.assertEqual(runtime.settings.reads, 2)
                runtime.switch_click.run_async.assert_not_called()


if __name__ == "__main__":
    unittest.main()
