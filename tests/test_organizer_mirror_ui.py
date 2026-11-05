from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.constants import KEY_ORGANIZER_MACRO_MODE, KEY_RADIAL_ENABLED
from app.core.runtime_state import AtlasRuntime
from app.input.hotkeys import build_hotkey_actions
from app.pages.organizer_page import OrganizerPage


class OrganizerMirrorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def test_three_cards_and_compact_mode_with_persisted_classic_preferences(self):
        import app.pages.organizer_page as organizer
        import app.pages.organizer.character_sessions as sessions

        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "profiles.json"
            index = Path(directory) / "client_index.json"
            ini = Path(directory) / "client_index.ini"
            profile.write_text("{}", encoding="utf-8")
            index.write_text(json.dumps({"clients": []}), encoding="utf-8")
            on_stop, on_reload = Mock(), Mock()
            with (
                patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}),
                patch.object(organizer, "PROFILE_FILE", profile),
                patch.object(organizer, "CLIENT_INDEX_JSON", index),
                patch.object(organizer, "CLIENT_INDEX_INI", ini),
                patch.object(sessions, "PROFILE_FILE", profile),
                patch.object(sessions, "CLIENT_INDEX_JSON", index),
                patch.object(sessions, "CLIENT_INDEX_INI", ini),
                patch.object(organizer.UnityWindowEventWatcher, "start",
                             side_effect=AssertionError("Native watcher started")),
            ):
                page = OrganizerPage(Mock(), on_reload, stop_runtime_callback=on_stop)
                try:
                    self.assertIsNone(page.scan_unity_sessions_callback)
                    self.assertTrue(page.profiles[KEY_RADIAL_ENABLED])
                    self.assertEqual(page.radial_select_button.objectName(), "primaryButton")
                    page.radial_select_button.click()
                    self.assertFalse(page.profiles[KEY_RADIAL_ENABLED])
                    self.assertEqual(page.radial_select_button.objectName(), "secondaryButton")
                    page.radial_select_button.click()
                    self.assertTrue(page.profiles[KEY_RADIAL_ENABLED])
                    self.assertEqual(page.radial_select_button.objectName(), "primaryButton")
                    self.assertTrue(page.macro_panel.isAncestorOf(page.macro_mode_button))
                    self.assertTrue(page.macro_panel.isAncestorOf(page.mirror_mode_button))
                    self.assertTrue(page.macro_panel.isAncestorOf(page.switch_click))
                    self.assertTrue(page.quick_actions_panel.isAncestorOf(page.switch_fake))
                    self.assertTrue(page.quick_actions_panel.isAncestorOf(page.radial_select_button))
                    self.assertTrue(page.quick_actions_panel.isAncestorOf(page.script_speed_fast))
                    self.assertTrue(page.controls_panel.isAncestorOf(page.reload_runtime_button))
                    self.assertTrue(page.controls_panel.isAncestorOf(page.debug_button))
                    self.assertTrue(page.controls_panel.isAncestorOf(page.stop_script_button))
                    self.assertIsNone(page.macro_grid_host.graphicsEffect())
                    self.assertTrue(page.macro_grid_host.isEnabled())
                    page.mirror_mode_button.click()
                    self.assertEqual(page.profiles[KEY_ORGANIZER_MACRO_MODE], "mirror")
                    self.assertFalse(page.macro_grid_host.isEnabled())
                    self.assertTrue(page.stop_script_button.isEnabled())
                    self.assertTrue(page.radial_select_button.isEnabled())
                    on_stop.assert_called_once()
                    page.macro_mode_button.click()
                    self.assertEqual(page.profiles[KEY_ORGANIZER_MACRO_MODE], "macro")
                    self.assertTrue(page.macro_grid_host.isEnabled())
                    self.assertEqual(on_stop.call_count, 2)
                    self.assertEqual(
                        json.loads(profile.read_text(encoding="utf-8"))[KEY_ORGANIZER_MACRO_MODE],
                        "macro",
                    )
                finally:
                    page.stop_session_event_watcher()
                    page.deleteLater()

    def test_mirror_disables_classic_hotkeys_but_keeps_emergency_stop(self):
        actions = build_hotkey_actions(
            SimpleNamespace(macro_mode="mirror", stop_hotkey="F12"),
        )
        self.assertEqual([action.action_id for action in actions], ["stop_script"])
        self.assertEqual(
            build_hotkey_actions(SimpleNamespace(macro_mode="mirror", stop_hotkey="")),
            [],
        )

    def _runtime(self, *, primary=101, handles=(101, 202, 303)):
        clients = tuple(SimpleNamespace(handle=h) for h in handles)
        settings = SimpleNamespace(
            macro_mode="mirror", primary_handle=primary, clients=clients,
            client_by_handle=lambda h: next((c for c in clients if c.handle == h), None),
        )
        runtime = Mock()
        runtime.settings = settings
        runtime.macro_lock.active_label = ""
        runtime.switch_click.run_async.return_value = True
        return runtime

    def test_mirror_keyboard_and_wheel_start_from_favorite_in_another_slot(self):
        runtime = self._runtime(primary=202, handles=(101, 202, 303))
        runtime._running = True
        runtime._admin_ok = True
        with (
            patch("app.windows.unity_windows.is_unity_window", return_value=True),
            patch("app.macros.mirror_plan.is_dofus_unity_process", return_value=True),
        ):
            self.assertEqual(
                AtlasRuntime._mirror_gesture_targets(runtime),
                (202, (202, 101, 303)),
            )

    def test_mirror_snapshot_never_drops_foreign_client_for_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                slots = tuple(range(101, 101 + count))
                foreign = slots[-1]
                runtime = self._runtime(primary=slots[0], handles=slots)
                runtime._running = True
                runtime._admin_ok = True
                with (
                    patch("app.windows.unity_windows.is_unity_window",
                          return_value=True),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          side_effect=lambda hwnd: hwnd != foreign),
                ):
                    self.assertIsNone(
                        AtlasRuntime._mirror_gesture_targets(runtime)
                    )

    def test_mirror_rejects_duplicate_or_non_integral_roster_before_replay(self):
        for handles in (
            (101, 202, 202), (101, 202.0, 303),
            (101, None, 303), (101, 2**64, 303),
            tuple(range(101, 110)),
        ):
            with self.subTest(handles=handles):
                runtime = self._runtime(primary=101, handles=handles)
                runtime._running = True
                runtime._admin_ok = True
                with (
                    patch("app.windows.unity_windows.is_unity_window",
                          return_value=True),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=True),
                ):
                    self.assertIsNone(
                        AtlasRuntime._mirror_gesture_targets(runtime)
                    )

    def test_invalid_secondary_never_consumes_real_key_wheel_or_click(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                slots = tuple(range(101, 101 + count))
                source = slots[-1]  # favorite need not be slot zero
                stale = slots[0]
                runtime = self._runtime(primary=source, handles=slots)
                runtime._running = True
                runtime._admin_ok = True
                runtime._mirror_gesture_targets.side_effect = (
                    lambda: AtlasRuntime._mirror_gesture_targets(runtime)
                )
                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=source),
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          return_value=source),
                    patch("app.windows.unity_windows.is_unity_window",
                          return_value=True),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          side_effect=lambda hwnd: hwnd != stale),
                    patch("app.windows.unity_windows.screen_to_client") as point,
                ):
                    self.assertFalse(AtlasRuntime._handle_mirror_key(runtime, 65, True))
                    self.assertFalse(AtlasRuntime._handle_mirror_wheel(
                        runtime, 120, 20, 25, False,
                    ))
                    self.assertFalse(AtlasRuntime._handle_mirror_click(
                        runtime, "Left", 20, 25,
                    ))
                point.assert_not_called()
                runtime.mirror_input.run_key.assert_not_called()
                runtime.mirror_input.run_wheel.assert_not_called()
                runtime.switch_click.run_async.assert_not_called()

    def test_mirror_snapshot_refuses_profile_reload_during_identity_probe(self):
        runtime = self._runtime(primary=101, handles=(101, 202, 303))
        runtime._running = True
        runtime._admin_ok = True
        initial = runtime.settings

        def probe(hwnd):
            if hwnd == 202:
                runtime.settings = self._runtime(
                    primary=303, handles=(101, 202, 303),
                ).settings
            return True

        with (
            patch("app.windows.unity_windows.is_unity_window", return_value=True),
            patch("app.macros.mirror_plan.is_dofus_unity_process",
                  side_effect=probe),
        ):
            self.assertIsNone(AtlasRuntime._mirror_gesture_targets(runtime))
        self.assertIsNot(runtime.settings, initial)
        runtime.mirror_input.run_key.assert_not_called()
        runtime.mirror_input.run_wheel.assert_not_called()

    def test_click_stays_native_if_profile_reloads_during_identity_probe(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                slots = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=slots[0], handles=slots)
                original_settings = runtime.settings

                def probe(hwnd):
                    if hwnd == slots[1]:
                        runtime.settings = self._runtime(
                            primary=slots[-1], handles=slots,
                        ).settings
                    return True

                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=slots[0]),
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          return_value=slots[0]),
                    patch("app.windows.unity_windows.is_unity_window",
                          return_value=True),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          side_effect=probe),
                ):
                    self.assertFalse(AtlasRuntime._handle_mirror_click(
                        runtime, "Left", 20, 25,
                    ))
                self.assertIsNot(runtime.settings, original_settings)
                runtime.switch_click.run_async.assert_not_called()


    def test_mirror_queued_input_rejects_identical_profile_reload_2_to_8(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel"):
                with self.subTest(clients=count, kind=kind):
                    handles = tuple(range(101, 101 + count))
                    runtime = self._runtime(
                        primary=handles[-1], handles=handles,
                    )
                    runtime._spawn_macro.return_value = True
                    macro = MirrorInputMacro(runtime)
                    order = (handles[-1], *handles[:-1])
                    if kind == "key":
                        accepted = macro.run_key(65, handles[-1], order)
                    else:
                        accepted = macro.run_wheel(
                            120, False, 0.4, 0.6, handles[-1], order,
                        )
                    self.assertTrue(accepted)
                    worker = runtime._spawn_macro.call_args.args[1]
                    profile = runtime.settings
                    # A profile reload with exactly the same visible clients
                    # must invalidate the queued physical gesture.
                    replacement = SimpleNamespace(
                        macro_mode=profile.macro_mode,
                        primary_handle=profile.primary_handle,
                        clients=profile.clients,
                        timings=getattr(profile, "timings", None),
                    )
                    runtime.settings = replacement
                    with (
                        patch("app.macros.mirror_input.current_cursor_pos") as cursor,
                        patch("app.macros.mirror_input.is_dofus_unity_process") as probe,
                        patch("app.macros.mirror_input.activate_window") as activate,
                        patch("app.macros.mirror_input.send_screen_wheel") as wheel,
                        patch("app.macros.input_tools.key_down") as key,
                    ):
                        worker()
                    cursor.assert_not_called()
                    probe.assert_not_called()
                    activate.assert_not_called()
                    wheel.assert_not_called()
                    key.assert_not_called()
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    runtime._emit_status.assert_called_once_with(
                        "Miroir non diffusé : profil Organizer modifié."
                    )
                    runtime.logger.warning.assert_any_call(
                        "Miroir %s annulé: profil Organizer remplacé avant worker.",
                        kind,
                    )

    def test_mirror_dispatch_rejects_profile_changed_before_acceptance(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel"):
                with self.subTest(clients=count, kind=kind):
                    handles = tuple(range(101, 101 + count))
                    runtime = self._runtime(primary=handles[0], handles=handles)
                    old = runtime.settings
                    runtime.settings = SimpleNamespace(
                        macro_mode=old.macro_mode,
                        primary_handle=old.primary_handle,
                        clients=old.clients,
                        timings=getattr(old, "timings", None),
                    )
                    mirror = MirrorInputMacro(runtime)
                    if kind == "key":
                        accepted = mirror.run_key(
                            65, handles[0], handles, expected_profile=old,
                        )
                    else:
                        accepted = mirror.run_wheel(
                            120, False, 0.25, 0.75, handles[0], handles,
                            expected_profile=old,
                        )
                    self.assertFalse(accepted)
                    runtime._spawn_macro.assert_not_called()

    def test_mirror_admission_rejects_changed_roster_before_worker_2_to_8(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel"):
                for stale in ("mode", "favorite", "replaced_client",
                              "favorite_alias", "float_alias", "invalid_hwnd"):
                    with self.subTest(clients=count, kind=kind, stale=stale):
                        handles = tuple(range(101, 101 + count))
                        runtime = self._runtime(primary=handles[0], handles=handles)
                        if stale == "mode":
                            runtime.settings.macro_mode = "macro"
                            candidates = handles
                        elif stale == "favorite":
                            runtime.settings.primary_handle = handles[-1]
                            candidates = handles
                        elif stale == "replaced_client":
                            runtime.settings.clients[-1].handle = 999
                            candidates = handles
                        elif stale == "favorite_alias":
                            runtime.settings.primary_handle = float(handles[0])
                            candidates = handles
                        elif stale == "float_alias":
                            # 202.0 equals 202 numerically, but is not a
                            # trustworthy Win32 HWND and must not be accepted.
                            runtime.settings.clients[-1].handle = float(handles[-1])
                            candidates = handles
                        else:
                            candidates = (*handles[:-1], 2**64)

                        macro = MirrorInputMacro(runtime)
                        if kind == "key":
                            self.assertFalse(macro.run_key(
                                65, handles[0], candidates,
                            ))
                        else:
                            self.assertFalse(macro.run_wheel(
                                120, False, 0.4, 0.6, handles[0], candidates,
                            ))
                        runtime._spawn_macro.assert_not_called()
                        runtime.input_state.begin_mouse_block.assert_not_called()
                        runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_mirror_inplace_mutation_during_admission_never_consumes_key_or_wheel(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel"):
                for change in ("mode", "favorite", "roster", "float_alias"):
                    with self.subTest(clients=count, kind=kind, change=change):
                        handles = tuple(range(101, 101 + count))
                        runtime = self._runtime(primary=handles[0], handles=handles)
                        queued = []

                        def spawn(_label, worker):
                            queued.append(worker)
                            if change == "mode":
                                runtime.settings.macro_mode = "macro"
                            elif change == "favorite":
                                runtime.settings.primary_handle = handles[-1]
                            elif change == "float_alias":
                                runtime.settings.clients[-1].handle = float(handles[-1])
                            else:
                                runtime.settings.clients[-1].handle = 999
                            return True

                        runtime._spawn_macro.side_effect = spawn
                        macro = MirrorInputMacro(runtime)
                        if kind == "key":
                            self.assertFalse(macro.run_key(
                                65, handles[0], handles,
                            ))
                        else:
                            self.assertFalse(macro.run_wheel(
                                120, False, 0.4, 0.6, handles[0], handles,
                            ))
                        self.assertEqual(len(queued), 1)
                        with (
                            patch("app.macros.mirror_input.current_cursor_pos") as cursor,
                            patch("app.macros.mirror_input.activate_window") as focus,
                            patch("app.macros.mirror_input.is_dofus_unity_process") as process,
                            patch("app.macros.mirror_input.send_screen_wheel") as wheel,
                            patch("app.macros.input_tools.key_down") as key,
                        ):
                            queued[0]()
                        cursor.assert_not_called()
                        focus.assert_not_called()
                        process.assert_not_called()
                        wheel.assert_not_called()
                        key.assert_not_called()
                        runtime.input_state.begin_mouse_block.assert_not_called()
                        runtime.switch_character.restore_preferred_client.assert_not_called()
                        runtime._emit_status.assert_called_once_with(
                            "Miroir non diffusé : profil Organizer modifié."
                        )

    def test_mirror_admission_rejects_profile_reloaded_during_spawn_2_to_8(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel"):
                with self.subTest(clients=count, kind=kind):
                    handles = tuple(range(101, 101 + count))
                    runtime = self._runtime(primary=handles[0], handles=handles)
                    captured = runtime.settings
                    queued = []

                    def spawn(_label, worker):
                        queued.append(worker)
                        # The native hook is still deciding whether to consume
                        # the real event when the UI reloads Organizer.
                        runtime.settings = SimpleNamespace(
                            macro_mode=captured.macro_mode,
                            primary_handle=captured.primary_handle,
                            clients=captured.clients,
                            timings=getattr(captured, "timings", None),
                        )
                        return True

                    runtime._spawn_macro.side_effect = spawn
                    mirror = MirrorInputMacro(runtime)
                    if kind == "key":
                        self.assertFalse(mirror.run_key(
                            65, handles[0], handles,
                            expected_profile=captured,
                        ))
                    else:
                        self.assertFalse(mirror.run_wheel(
                            120, False, 0.4, 0.6, handles[0], handles,
                            expected_profile=captured,
                        ))
                    self.assertEqual(len(queued), 1)
                    with (
                        patch("app.macros.mirror_input.current_cursor_pos") as cursor,
                        patch("app.macros.mirror_input.is_dofus_unity_process") as probe,
                        patch("app.macros.mirror_input.activate_window") as activate,
                        patch("app.macros.mirror_input.send_screen_wheel") as wheel,
                        patch("app.macros.input_tools.key_down") as key,
                    ):
                        queued[0]()
                    cursor.assert_not_called()
                    probe.assert_not_called()
                    activate.assert_not_called()
                    wheel.assert_not_called()
                    key.assert_not_called()
                    runtime.input_state.begin_mouse_block.assert_not_called()
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    runtime._emit_status.assert_called_once_with(
                        "Miroir non diffusé : profil Organizer modifié."
                    )

    def test_mirror_callbacks_do_not_consume_profile_reloaded_after_snapshot(self):
        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel"):
                with self.subTest(clients=count, kind=kind):
                    handles = tuple(range(101, 101 + count))
                    runtime = self._runtime(primary=handles[0], handles=handles)
                    runtime._running = True
                    runtime._admin_ok = True
                    runtime.macro_lock.active_label = ""
                    old = runtime.settings
                    def reload_after_snapshot():
                        runtime.settings = SimpleNamespace(
                            macro_mode=old.macro_mode,
                            primary_handle=old.primary_handle,
                            clients=old.clients,
                            timings=getattr(old, "timings", None),
                        )
                        return handles[0], handles

                    runtime._mirror_gesture_targets.side_effect = reload_after_snapshot
                    with (
                        patch("app.windows.unity_windows.foreground_window",
                              return_value=handles[0]),
                        patch("app.windows.unity_windows.find_known_client_from_point",
                              return_value=handles[0]),
                        patch("app.windows.unity_windows.screen_to_client",
                              return_value=(12, 15)),
                        patch("app.windows.unity_windows.client_point_ratio",
                              return_value=(0.2, 0.3)),
                    ):
                        if kind == "key":
                            consumed = AtlasRuntime._handle_mirror_key(runtime, 65, True)
                        else:
                            consumed = AtlasRuntime._handle_mirror_wheel(
                                runtime, 120, 80, 95, False,
                            )
                    self.assertFalse(consumed)
                    runtime.mirror_input.run_key.assert_not_called()
                    runtime.mirror_input.run_wheel.assert_not_called()


    def test_mirror_accepted_gesture_binds_worker_timing_and_generation(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel"):
                with self.subTest(clients=count, kind=kind):
                    handles = tuple(range(101, 101 + count))
                    runtime = self._runtime(primary=handles[0], handles=handles)
                    runtime._spawn_macro.return_value = True
                    macro = MirrorInputMacro(runtime)
                    with patch("app.macros.mirror_input.perf_counter", return_value=123.25):
                        if kind == "key":
                            self.assertTrue(macro.run_key(65, handles[0], handles))
                        else:
                            self.assertTrue(macro.run_wheel(
                                120, False, 0.3, 0.6, handles[0], handles,
                            ))
                    worker = runtime._spawn_macro.call_args.args[1]
                    with patch.object(macro, "_run") as runner:
                        worker()
                    self.assertEqual(runner.call_args.kwargs, {
                        "profile_at_dispatch": runtime.settings,
                        "dispatch_at": 123.25,
                    })

    def test_mirror_worker_reports_emission_not_unity_render_latency(self):
        from app.macros.mirror_input import MirrorInputMacro
        from time import perf_counter

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0,
                    activate_attempts=1,
                    activate_retry_ms=0,
                    switch_click_down_ms=10,
                    switch_client_settle_ms=0,
                )
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.mirror_input.activate_window",
                          return_value=True),
                    patch("app.macros.mirror_input.foreground_window",
                          side_effect=[*handles, handles[-1]]),
                    patch("app.macros.input_tools.key_down") as down,
                    patch("app.macros.input_tools.key_up") as up,
                ):
                    MirrorInputMacro(runtime)._run(
                        "key", 65, handles[0], handles,
                        dispatch_at=perf_counter() - 0.025,
                    )
                self.assertEqual(down.call_count, count)
                self.assertEqual(up.call_count, count)
                logs = [
                    call for call in runtime.logger.info.call_args_list
                    if call.args and "dispatch_to_last_emit_ms" in str(call.args[0])
                ]
                self.assertEqual(len(logs), 1)
                self.assertEqual(logs[0].args[1], "key")
                self.assertNotEqual(logs[0].args[3], "NOT_MEASURED")
                self.assertGreaterEqual(logs[0].args[2], 0.0)
                self.assertIn("pas rendu Unity", logs[0].args[0])

    def test_mirror_worker_accepts_nonfirst_favorite_and_rejects_roster_drift(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = self._runtime(primary=202, handles=(101, 202, 303))
        macro = MirrorInputMacro(runtime)
        self.assertTrue(macro._still_current(202, (202, 101, 303)))
        self.assertFalse(macro._still_current(202, (101, 202, 303)))
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=303),
            SimpleNamespace(handle=202),
        )
        self.assertFalse(macro._still_current(202, (202, 101, 303)))

    def test_mirror_keyboard_dispatch_with_nonfirst_favorite_two_to_eight(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                slots = tuple(range(101, 101 + count))
                favorite = slots[-1]
                handles = (favorite, *slots[:-1])
                runtime = self._runtime(primary=favorite, handles=slots)
                runtime.settings.timings = SimpleNamespace()
                timings = runtime.settings.timings
                timings.switch_background_pre_click_ms = 0
                timings.activate_attempts = 1
                timings.activate_retry_ms = 0
                timings.switch_click_down_ms = 10
                timings.switch_client_settle_ms = 0
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                events = []
                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.mirror_input.activate_window",
                          return_value=True) as activate,
                    patch("app.macros.mirror_input.foreground_window",
                          side_effect=[*handles, handles[-1]]),
                    patch("app.macros.input_tools.key_down",
                          side_effect=lambda vk: events.append(("down", vk))),
                    patch("app.macros.input_tools.key_up",
                          side_effect=lambda vk: events.append(("up", vk))),
                ):
                    MirrorInputMacro(runtime)._run("key", 65, favorite, handles)
                self.assertEqual(activate.call_count, count)
                self.assertEqual(
                    [call.args[0] for call in activate.call_args_list],
                    list(handles),
                )
                self.assertEqual(events, [("down", 65), ("up", 65)] * count)
                runtime._emit_status.assert_called_once_with(
                    f"Miroir Clavier : {count}/{count} fenêtres."
                )

    def test_mirror_wheel_dispatch_from_last_favorite_two_to_eight(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                slots = tuple(range(101, 101 + count))
                favorite = slots[-1]
                handles = (favorite, *slots[:-1])
                runtime = self._runtime(primary=favorite, handles=slots)
                runtime.settings.timings = SimpleNamespace()
                timings = runtime.settings.timings
                timings.switch_background_pre_click_ms = 0
                timings.activate_attempts = 1
                timings.activate_retry_ms = 0
                timings.switch_client_settle_ms = 0
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                focus_sequence = [h for h in handles for _ in range(2)] + [handles[-1]] * 2
                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.mirror_input.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.mirror_input.activate_window",
                          return_value=True) as activate,
                    patch("app.macros.mirror_input.foreground_window",
                          side_effect=focus_sequence),
                    patch("app.macros.mirror_input.client_point_from_ratio",
                          return_value=(8, 9)),
                    patch("app.macros.mirror_input.client_to_screen",
                          return_value=(80, 90)),
                    patch("app.macros.mirror_input.set_cursor_pos") as move,
                    patch("app.macros.mirror_input.send_screen_wheel",
                          return_value=True) as sender,
                ):
                    MirrorInputMacro(runtime)._run(
                        "wheel", (-120, False, 0.5, 0.5), favorite, handles,
                    )
                self.assertEqual(activate.call_count, count)
                self.assertEqual(
                    [call.args[0] for call in activate.call_args_list],
                    list(handles),
                )
                self.assertEqual(sender.call_count, count)
                self.assertTrue(
                    all(call.args == (-120,) and
                        call.kwargs == {"horizontal": False}
                        for call in sender.call_args_list)
                )
                self.assertEqual(move.call_count, count + 1)
                move.assert_any_call(12, 14)
                runtime._emit_status.assert_called_once_with(
                    f"Miroir Molette : {count}/{count} fenêtres."
                )

    def test_favorite_click_reuses_existing_sender_once(self):
        runtime = self._runtime()
        with (
            patch("app.windows.unity_windows.is_unity_window", return_value=True),
            patch("app.macros.mirror_plan.is_dofus_unity_process", return_value=True),
            patch("app.windows.unity_windows.foreground_window", return_value=101),
            patch("app.windows.unity_windows.find_known_client_from_point", return_value=101),
        ):
            self.assertTrue(AtlasRuntime._handle_mirror_click(runtime, "Left", 12, 28))
        runtime.switch_click.run_async.assert_called_once_with(
            "Left", 12, 28, 1, "Miroir", exact_source_handle=101,
            mirror_target_handles=(101, 202, 303),
            expected_profile=runtime.settings,
        )

    def test_mirror_click_rejects_profile_reload_between_snapshot_and_dispatch(self):
        from app.macros.mirror_plan import mirror_delivery_targets as original_targets

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[-1], handles=handles)
                old = runtime.settings

                def reload_after_targets(*args, **kwargs):
                    destinations = original_targets(*args, **kwargs)
                    runtime.settings = SimpleNamespace(
                        macro_mode=old.macro_mode,
                        primary_handle=old.primary_handle,
                        clients=old.clients,
                        timings=getattr(old, "timings", None),
                    )
                    return destinations

                with (
                    patch("app.windows.unity_windows.is_unity_window", return_value=True),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=True),
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=handles[-1]),
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          return_value=handles[-1]),
                    patch("app.macros.mirror_plan.mirror_delivery_targets",
                          side_effect=reload_after_targets),
                ):
                    # No click is consumed if an identical-looking profile was
                    # replaced after native HWND authentication.
                    self.assertFalse(AtlasRuntime._handle_mirror_click(
                        runtime, "Left", 20, 25,
                    ))
                runtime.switch_click.run_async.assert_not_called()

    def test_click_sender_refuses_stale_generation_before_context_capture(self):
        from app.macros.switch_click import SwitchClickMacro

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                old = runtime.settings
                runtime.settings = SimpleNamespace(
                    macro_mode=old.macro_mode,
                    primary_handle=old.primary_handle,
                    clients=old.clients,
                    timings=getattr(old, "timings", None),
                )
                sender = SwitchClickMacro(runtime)
                with patch.object(sender, "_capture_trigger_context") as capture:
                    self.assertFalse(sender.run_async(
                        "left", 20, 25, 1, "Miroir",
                        expected_profile=old,
                    ))
                capture.assert_not_called()
                runtime._spawn_macro.assert_not_called()

    def test_invalid_key_callback_never_scans_foreground_or_roster(self):
        runtime = self._runtime()
        runtime._running = True
        runtime._admin_ok = True
        for vk, pressed in (
            (0, True), (0x5B, True), (0xA2, True), (65.0, True),
            (True, True), ("65", True), (65, 1), (65, None),
        ):
            with self.subTest(vk=repr(vk), pressed=pressed):
                with patch("app.windows.unity_windows.foreground_window") as foreground:
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_key(runtime, vk, pressed)
                    )
                foreground.assert_not_called()
        runtime._mirror_gesture_targets.assert_not_called()
        runtime.mirror_input.run_key.assert_not_called()

    def test_invalid_wheel_callback_preserves_physical_event_without_probes(self):
        runtime = self._runtime()
        runtime._running = True
        runtime._admin_ok = True
        events = [
            (0, 20, 25, False),
            (32768, 20, 25, False),
            (True, 20, 25, False),
            ("120", 20, 25, False),
            (120, float("inf"), 25, False),
            (120, 20, True, False),
            (120, -(2**31) - 1, 25, False),
            (120, 20, 2**31, False),
            (120, 20, 25, 1),
        ]
        for values in events:
            with self.subTest(values=values):
                with patch("app.windows.unity_windows.foreground_window") as foreground:
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_wheel(runtime, *values)
                    )
                foreground.assert_not_called()
        runtime._mirror_gesture_targets.assert_not_called()
        runtime.mirror_input.run_wheel.assert_not_called()

    def test_mirror_click_rejects_mode_changed_to_macro_before_native_probes(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.settings.macro_mode = "macro"
                with (
                    patch("app.windows.unity_windows.foreground_window") as foreground,
                    patch("app.windows.unity_windows.find_known_client_from_point") as hit,
                    patch("app.macros.mirror_plan.is_dofus_unity_process") as probe,
                ):
                    self.assertFalse(AtlasRuntime._handle_mirror_click(
                        runtime, "Left", 20, 25,
                    ))
                foreground.assert_not_called()
                hit.assert_not_called()
                probe.assert_not_called()
                runtime.switch_click.run_async.assert_not_called()

    def test_racing_mode_toggle_during_physical_click_cannot_dispatch_mirror(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[-1], handles=handles)
                runtime._running = True
                runtime._admin_ok = True
                runtime._pending_physical_switch = None
                replacement = SimpleNamespace(
                    macro_mode="macro",
                    primary_handle=handles[-1],
                    clients=runtime.settings.clients,
                )

                class ReloadingProfile:
                    @property
                    def macro_mode(self):
                        runtime.settings = replacement
                        return "mirror"

                runtime.settings = ReloadingProfile()
                runtime._handle_mirror_click.side_effect = (
                    lambda *args: AtlasRuntime._handle_mirror_click(runtime, *args)
                )
                with (
                    patch("app.windows.unity_windows.foreground_window") as focus,
                    patch("app.windows.unity_windows.find_known_client_from_point") as hit,
                    patch("app.macros.mirror_plan.is_dofus_unity_process") as probe,
                ):
                    self.assertFalse(AtlasRuntime._handle_mouse_click(
                        runtime, "Left", 20, 25,
                    ))
                focus.assert_not_called()
                hit.assert_not_called()
                probe.assert_not_called()
                runtime.switch_click.run_async.assert_not_called()

    def test_invalid_click_callback_never_consults_favorite_or_consumes(self):
        runtime = self._runtime()
        for values in (
            ("Middle", 20, 25), (None, 20, 25),
            ("Left", float("nan"), 25), ("Right", 20, "25"),
            ("Left", True, 25), ("Left", 20, 2**31),
        ):
            with self.subTest(values=values):
                with patch("app.windows.unity_windows.foreground_window") as foreground:
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_click(runtime, *values)
                    )
                foreground.assert_not_called()
        runtime.switch_click.run_async.assert_not_called()

    def test_healthy_favorite_and_roster_still_dispatch_2_to_8_clients(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                slots = tuple(range(101, 101 + count))
                source = slots[-1]
                ordered = (source, *slots[:-1])
                runtime = self._runtime(primary=source, handles=slots)
                runtime._running = True
                runtime._admin_ok = True
                runtime._mirror_gesture_targets.side_effect = (
                    lambda: AtlasRuntime._mirror_gesture_targets(runtime)
                )
                runtime.mirror_input.run_key.return_value = True
                runtime.mirror_input.run_wheel.return_value = True
                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=source),
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          return_value=source),
                    patch("app.windows.unity_windows.is_unity_window",
                          return_value=True),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=True),
                    patch("app.windows.unity_windows.screen_to_client",
                          return_value=(10, 20)),
                    patch("app.windows.unity_windows.client_point_ratio",
                          return_value=(0.25, 0.75)),
                ):
                    self.assertTrue(
                        AtlasRuntime._handle_mirror_key(runtime, 65, True)
                    )
                    self.assertTrue(
                        AtlasRuntime._handle_mirror_wheel(
                            runtime, -120, 20, 25, False,
                        )
                    )
                    self.assertTrue(
                        AtlasRuntime._handle_mirror_click(
                            runtime, "Left", 20, 25,
                        )
                    )
                runtime.mirror_input.run_key.assert_called_once_with(
                    65, source, ordered, expected_profile=runtime.settings,
                )
                runtime.mirror_input.run_wheel.assert_called_once_with(
                    -120, False, 0.25, 0.75, source, ordered,
                    expected_profile=runtime.settings,
                )
                runtime.switch_click.run_async.assert_called_once_with(
                    "Left", 20, 25, 1, "Miroir",
                    exact_source_handle=source, mirror_target_handles=ordered,
                    expected_profile=runtime.settings,
                )

    def test_foreign_input_never_scans_unrelated_unity_sessions(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(handles=handles)
                runtime._running = True
                runtime._admin_ok = True
                runtime.macro_lock.active_label = ""
                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=999),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          side_effect=AssertionError("foreign app probed")) as probe,
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          side_effect=AssertionError("foreign pointer queried")),
                ):
                    self.assertFalse(AtlasRuntime._handle_mirror_key(runtime, 65, True))
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_wheel(
                            runtime, 120, 30, 40, False,
                        )
                    )
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_click(runtime, "Left", 30, 40)
                    )
                runtime._mirror_gesture_targets.assert_not_called()
                runtime.switch_click.run_async.assert_not_called()
                runtime.mirror_input.run_key.assert_not_called()
                runtime.mirror_input.run_wheel.assert_not_called()
                probe.assert_not_called()

    def test_switch_click_discard_queued_worker_after_identical_profile_reload(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime._spawn_macro.return_value = True
                macro = SwitchClickMacro(runtime)
                captured = SwitchClickContext(
                    handles[0], 20, 30, 0.5, 0.5, "cursor",
                )
                with patch.object(macro, "_capture_trigger_context",
                                  return_value=captured):
                    self.assertTrue(macro.run_async(
                        "Left", 20, 30, 1, "Miroir",
                        exact_source_handle=handles[0],
                        mirror_target_handles=handles,
                    ))
                runtime.settings = SimpleNamespace(**vars(runtime.settings))
                with (
                    patch("app.macros.switch_click.current_cursor_pos") as cursor,
                    patch("app.macros.switch_click.activate_window") as focus,
                    patch("app.macros.switch_click.send_client_click") as send,
                ):
                    runtime._spawn_macro.call_args.args[1]()
                cursor.assert_not_called()
                focus.assert_not_called()
                send.assert_not_called()
                runtime.input_state.begin_mouse_block.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_switch_click_identical_profile_reload_after_activation_never_clicks(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0,
                    activate_attempts=1, activate_retry_ms=0,
                    switch_click_down_ms=35, input_double_gap_ms=5,
                    switch_background_post_up_ms=0,
                    switch_client_settle_ms=0,
                )
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=h, display_name=str(h))
                    for h in handles
                ]
                runtime.macro_lock.should_stop.return_value = False
                context = SwitchClickContext(
                    handles[0], 20, 30, 0.5, 0.5, "cursor",
                )
                macro = SwitchClickMacro(runtime)

                def activate_and_reload(_hwnd, *_args, **kwargs):
                    runtime.settings = SimpleNamespace(**vars(runtime.settings))
                    self.assertTrue(kwargs["should_stop"]())
                    return True

                with (
                    patch.object(macro, "_validated_context", return_value=context),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.switch_click.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.switch_click.activate_window",
                          side_effect=activate_and_reload) as focus,
                    patch("app.macros.switch_click.foreground_window") as foreground,
                    patch("app.macros.switch_click.send_client_click") as send,
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=handles[0],
                        mirror_target_handles=handles,
                    )
                focus.assert_called_once()
                foreground.assert_not_called()
                send.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime._emit_status.assert_called_once_with(
                    f"Miroir interrompu : 0/{count} fenêtres."
                )

    def test_mirror_click_wrong_window_under_cursor_skips_roster_scan(self):
        runtime = self._runtime()
        runtime._running = True
        runtime._admin_ok = True
        with (
            patch("app.windows.unity_windows.foreground_window",
                  return_value=101),
            patch("app.windows.unity_windows.find_known_client_from_point",
                  return_value=777),
            patch("app.windows.unity_windows.is_unity_window",
                  side_effect=AssertionError("source should not be probed")),
            patch("app.macros.mirror_plan.is_dofus_unity_process",
                  side_effect=AssertionError("identity should not be probed")),
        ):
            self.assertFalse(
                AtlasRuntime._handle_mirror_click(runtime, "Left", 30, 40)
            )
        runtime.switch_click.run_async.assert_not_called()

    def test_no_favorite_foreign_focus_one_client_or_too_many_fail_closed(self):
        cases = [
            (self._runtime(primary=0), 101, 101),
            (self._runtime(), 777, 101),
            (self._runtime(), 101, 777),
            (self._runtime(handles=(101,)), 101, 101),
            (self._runtime(handles=tuple(range(101, 110))), 101, 101),
        ]
        for runtime, foreground, under_cursor in cases:
            with self.subTest(primary=runtime.settings.primary_handle, foreground=foreground):
                with (
                    patch("app.windows.unity_windows.is_unity_window", return_value=True),
            patch("app.macros.mirror_plan.is_dofus_unity_process", return_value=True),
                    patch("app.windows.unity_windows.foreground_window", return_value=foreground),
                    patch("app.windows.unity_windows.find_known_client_from_point", return_value=under_cursor),
                ):
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_click(runtime, "Left", 12, 28)
                    )
                runtime.switch_click.run_async.assert_not_called()

    def test_busy_keyboard_lets_real_click_through_without_second_worker(self):
        runtime = self._runtime()
        runtime.macro_lock.active_label = "Miroir clavier"
        with (
            patch("app.windows.unity_windows.is_unity_window", return_value=True),
            patch("app.macros.mirror_plan.is_dofus_unity_process", return_value=True),
            patch("app.windows.unity_windows.foreground_window", return_value=101),
            patch("app.windows.unity_windows.find_known_client_from_point",
                  return_value=101),
        ):
            self.assertFalse(AtlasRuntime._handle_mirror_click(
                runtime, "Left", 12, 28,
            ))
        runtime.switch_click.run_async.assert_not_called()

    def test_key_worker_does_not_block_physical_mouse_for_2_4_6_8(self):
        from app.macros.mirror_input import MirrorInputMacro
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.input_state = InputState()
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0,
                    activate_attempts=1, activate_retry_ms=0,
                    switch_click_down_ms=10, switch_client_settle_ms=0,
                )
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                emitted = []
                def key_event(vk):
                    self.assertFalse(runtime.input_state.is_mouse_blocked())
                    emitted.append(vk)
                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.mirror_input.activate_window",
                          return_value=True),
                    patch("app.macros.mirror_input.foreground_window",
                          side_effect=[*handles, handles[-1]]),
                    patch("app.macros.input_tools.key_down", side_effect=key_event),
                    patch("app.macros.input_tools.key_up", side_effect=key_event),
                ):
                    MirrorInputMacro(runtime)._run("key", 65, handles[0], handles)
                self.assertEqual(emitted, [65] * (2 * count))
                self.assertFalse(runtime.input_state.is_mouse_blocked())
                runtime._emit_status.assert_called_once_with(
                    f"Miroir Clavier : {count}/{count} fenêtres."
                )

    def test_wheel_preflight_stays_unblocked_and_never_activates_invalid_roster(self):
        from app.macros.mirror_input import MirrorInputMacro
        from app.input.input_state import InputState

        runtime = self._runtime(primary=101, handles=(101, 202))
        runtime.input_state = InputState()
        runtime.settings.timings = SimpleNamespace()
        runtime.macro_lock.should_stop.return_value = False
        seen = []
        def identity(hwnd):
            seen.append(runtime.input_state.is_mouse_blocked())
            return hwnd != 202
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  side_effect=identity),
            patch("app.macros.mirror_input.current_cursor_pos",
                  return_value=(10, 20)),
            patch("app.macros.mirror_input.activate_window") as activate,
        ):
            MirrorInputMacro(runtime)._run(
                "wheel", (120, False, 0.5, 0.5), 101, (101, 202),
            )
        self.assertEqual(seen, [False, False])
        self.assertFalse(runtime.input_state.is_mouse_blocked())
        activate.assert_not_called()

    def test_wheel_worker_blocks_only_during_delivery_for_2_4_6_8(self):
        from app.macros.mirror_input import MirrorInputMacro
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.input_state = InputState()
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0,
                    activate_attempts=1, activate_retry_ms=0,
                    switch_client_settle_ms=0,
                )
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                def activate(_hwnd, *_args, **_kwargs):
                    self.assertTrue(runtime.input_state.is_mouse_blocked())
                    return True
                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.mirror_input.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.mirror_input.activate_window",
                          side_effect=activate) as activator,
                    patch("app.macros.mirror_input.foreground_window",
                          side_effect=[*(h for h in handles for _ in range(2)),
                                       handles[-1], handles[-1]]),
                    patch("app.macros.mirror_input.client_point_from_ratio",
                          return_value=(8, 9)),
                    patch("app.macros.mirror_input.client_to_screen",
                          return_value=(80, 90)),
                    patch("app.macros.mirror_input.set_cursor_pos"),
                    patch("app.macros.mirror_input.send_screen_wheel",
                          return_value=True) as send,
                ):
                    MirrorInputMacro(runtime)._run(
                        "wheel", (120, False, 0.5, 0.5), handles[0], handles,
                    )
                self.assertEqual(activator.call_count, count)
                self.assertEqual(send.call_count, count)
                self.assertFalse(runtime.input_state.is_mouse_blocked())

    def test_busy_non_mouse_work_does_not_probe_8_processes_in_native_hook(self):
        for count in (2, 4, 6, 8):
            for busy in ("Miroir clavier", "Miroir molette"):
                with self.subTest(count=count, busy=busy):
                    slots = tuple(range(101, 101 + count))
                    runtime = self._runtime(primary=slots[0], handles=slots)
                    runtime.macro_lock.active_label = busy
                    runtime.input_state.is_mouse_blocked.return_value = False
                    with (
                        patch("app.windows.unity_windows.foreground_window") as focus,
                        patch("app.windows.unity_windows.is_unity_window") as unity,
                        patch("app.macros.mirror_plan.is_dofus_unity_process") as identity,
                        patch("app.windows.unity_windows.find_known_client_from_point") as point,
                    ):
                        self.assertFalse(
                            AtlasRuntime._handle_mirror_click(
                                runtime, "Left", 12, 28,
                            )
                        )
                    focus.assert_not_called()
                    unity.assert_not_called()
                    identity.assert_not_called()
                    point.assert_not_called()
                    runtime.switch_click.run_async.assert_not_called()

    def test_wheel_preflight_passes_click_then_blocks_only_during_delivery(self):
        runtime = self._runtime()
        runtime.macro_lock.active_label = "Miroir molette"
        runtime.input_state.is_mouse_blocked.return_value = False
        with (
            patch("app.windows.unity_windows.is_unity_window", return_value=True),
            patch("app.macros.mirror_plan.is_dofus_unity_process", return_value=True),
            patch("app.windows.unity_windows.foreground_window", return_value=101),
            patch("app.windows.unity_windows.find_known_client_from_point",
                  return_value=101),
        ):
            self.assertFalse(
                AtlasRuntime._handle_mirror_click(runtime, "Left", 12, 28)
            )
            runtime.input_state.is_mouse_blocked.return_value = True
            self.assertTrue(
                AtlasRuntime._handle_mirror_click(runtime, "Left", 12, 28)
            )
        runtime.switch_click.run_async.assert_not_called()

    def test_native_mouse_down_up_survive_busy_keyboard_for_2_to_8(self):
        import ctypes
        from app.input.input_state import InputState
        from app.input.mouse_hooks import (
            MouseHook, MSLLHOOKSTRUCT, WM_LBUTTONDOWN, WM_LBUTTONUP,
        )
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                slots = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=slots[0], handles=slots)
                runtime._running = True
                runtime._admin_ok = True
                runtime.macro_lock.active_label = "Miroir clavier"
                runtime.input_state = InputState()
                callback = lambda button, x, y: AtlasRuntime._handle_mouse_click(
                    runtime, button, x, y,
                )
                hook = MouseHook(
                    runtime.input_state, Mock(), Mock(), callback,
                )
                event = MSLLHOOKSTRUCT()
                event.pt.x = 20
                event.pt.y = 25
                event.flags = 0
                event.dwExtraInfo = None
                next_hook = Mock(return_value=37)
                with (
                    patch("app.windows.unity_windows.is_unity_window",
                          return_value=True),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=True),
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=slots[0]),
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          return_value=slots[0]),
                    patch.object(ctypes, "windll",
                          SimpleNamespace(user32=SimpleNamespace(
                              CallNextHookEx=next_hook,
                          )), create=True),
                ):
                    ptr = ctypes.addressof(event)
                    self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, ptr), 37)
                    self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, ptr), 37)
                self.assertFalse(hook._consumed_releases)
                self.assertEqual(next_hook.call_count, 2)
                runtime.switch_click.run_async.assert_not_called()

    def test_queued_mirror_click_keeps_physical_click_native_until_blocked(self):
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.input_state = InputState()
                runtime.macro_lock.active_label = "Miroir"
                with (
                    patch("app.windows.unity_windows.foreground_window") as focus,
                    patch("app.windows.unity_windows.find_known_client_from_point") as point,
                    patch("app.windows.unity_windows.is_unity_window") as unity,
                    patch("app.macros.mirror_plan.is_dofus_unity_process") as identity,
                ):
                    self.assertFalse(AtlasRuntime._handle_mirror_click(
                        runtime, "Left", 20, 25,
                    ))
                focus.assert_not_called()
                point.assert_not_called()
                unity.assert_not_called()
                identity.assert_not_called()
                runtime.switch_click.run_async.assert_not_called()

    def test_active_mirror_click_keeps_second_worker_off_during_mouse_block(self):
        from app.input.input_state import InputState

        runtime = self._runtime(primary=101, handles=(101, 202))
        runtime.input_state = InputState()
        runtime.input_state.begin_mouse_block("Miroir")
        runtime.macro_lock.active_label = "Miroir"
        with (
            patch("app.windows.unity_windows.foreground_window",
                  return_value=101),
            patch("app.windows.unity_windows.find_known_client_from_point",
                  return_value=101),
            patch("app.windows.unity_windows.is_unity_window",
                  return_value=True),
            patch("app.macros.mirror_plan.is_dofus_unity_process",
                  return_value=True),
        ):
            self.assertTrue(AtlasRuntime._handle_mirror_click(
                runtime, "Left", 20, 25,
            ))
        runtime.switch_click.run_async.assert_not_called()
        runtime.input_state.end_mouse_block()

    def test_macro_busy_consumes_without_starting_a_second_delivery(self):
        runtime = self._runtime()
        runtime.macro_lock.active_label = "Miroir"
        with (
            patch("app.windows.unity_windows.is_unity_window", return_value=True),
            patch("app.macros.mirror_plan.is_dofus_unity_process", return_value=True),
            patch("app.windows.unity_windows.foreground_window", return_value=101),
            patch("app.windows.unity_windows.find_known_client_from_point", return_value=101),
        ):
            self.assertTrue(AtlasRuntime._handle_mirror_click(runtime, "Left", 12, 28))
        runtime.switch_click.run_async.assert_not_called()


    def test_classic_switch_dispatch_failure_leaves_native_click_unconsumed(self):
        for result in (False, RuntimeError("spawn failed")):
            with self.subTest(result=str(result)):
                runtime = self._runtime()
                runtime._running = True
                runtime._admin_ok = True
                runtime.settings.macro_mode = "macro"
                runtime.registry.switch_action_for_pressed_keys.return_value = (
                    SimpleNamespace(
                        action_id="switch:click",
                        payload={"click_count": 1, "label": "Switch clique"},
                    )
                )
                if isinstance(result, Exception):
                    runtime.switch_click.run_async.side_effect = result
                else:
                    runtime.switch_click.run_async.return_value = result
                self.assertFalse(
                    AtlasRuntime._handle_mouse_click(runtime, "Left", 15, 20)
                )
                runtime.switch_click.run_async.assert_called_once_with(
                    "Left", 15, 20, 1, "Switch clique",
                )

    def test_exact_source_guard_does_not_consume_another_window_or_fallback(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext
        runtime = Mock()
        mirror = SwitchClickMacro(runtime)
        for handle, reason in ((202, "cursor"), (101, "preferred_center")):
            with self.subTest(handle=handle, reason=reason):
                context = SwitchClickContext(handle, 10, 10, 0.4, 0.4, reason)
                with patch.object(mirror, "_capture_trigger_context", return_value=context):
                    self.assertFalse(mirror.run_async(
                        "Left", 50, 60, 1, "Miroir", exact_source_handle=101,
                    ))
        runtime._spawn_macro.assert_not_called()
        runtime.input_state.begin_mouse_block.assert_not_called()

    def test_sequential_sender_visits_2_4_6_8_clients_exactly_once(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                clients = [SimpleNamespace(handle=h, display_name=str(h)) for h in handles]
                runtime = Mock()
                runtime.switch_character.ordered_clients_from_source.return_value = clients
                runtime.settings.client_by_handle.return_value = clients[0]
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0,
                    activate_attempts=1, activate_retry_ms=0,
                    input_double_gap_ms=5, switch_click_down_ms=1,
                    switch_background_post_up_ms=0, switch_client_settle_ms=0,
                )
                macro = SwitchClickMacro(runtime)
                context = SwitchClickContext(handles[0], 20, 30, 0.5, 0.5, "cursor")
                with (
                    patch("app.macros.switch_click.current_cursor_pos", return_value=(100, 200)),
                    patch("app.macros.switch_click.set_cursor_pos"),
                    patch("app.macros.switch_click.is_unity_window", return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process", return_value=True),
                    patch("app.macros.switch_click.activate_window", return_value=True),
                    patch("app.macros.switch_click.foreground_window", side_effect=list(handles)),
                    patch("app.macros.switch_click.send_client_click", return_value=True) as sender,
                    patch.object(macro, "_target_point", return_value=(20, 30)),
                ):
                    macro._run("Left", 1, "Miroir", context)
                self.assertEqual(sender.call_count, count)
                self.assertEqual(
                    [call.args[0] for call in sender.call_args_list], list(handles),
                )
                runtime.switch_character.restore_preferred_client.assert_called_once_with("Miroir")
                runtime._emit_status.assert_called_once_with(
                    f"Miroir : {count}/{count} fenêtres."
                )
                focus_logs = [
                    call for call in runtime.logger.info.call_args_list
                    if call.args and "focus_activation_ms" in str(call.args[0])
                ]
                self.assertEqual(len(focus_logs), 1)
                self.assertEqual(focus_logs[0].args[1]["n"], count)


    def test_switch_click_dispatch_leaves_mouse_native_while_worker_is_queued(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.input_state = InputState()
                runtime._spawn_macro.return_value = True
                context = SwitchClickContext(handles[0], 20, 25, 0.3, 0.4, "cursor")
                self.assertTrue(SwitchClickMacro(runtime).run_async(
                    "Left", 100, 120, 1, "Miroir",
                    exact_source_handle=handles[0],
                    mirror_target_handles=handles,
                    captured_context=context,
                ))
                self.assertFalse(runtime.input_state.is_mouse_blocked())
                runtime._spawn_macro.assert_called_once()

    def test_switch_click_preflight_is_native_and_delivery_is_guarded_2_to_8(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.input_state = InputState()
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=35,
                    input_double_gap_ms=5, switch_background_post_up_ms=0,
                    switch_client_settle_ms=0,
                )
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=hwnd, display_name=str(hwnd))
                    for hwnd in handles
                ]
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                context = SwitchClickContext(handles[0], 20, 25, 0.3, 0.4, "cursor")
                macro = SwitchClickMacro(runtime)
                preflight = []
                emitted = []
                active = [handles[0]]

                def check_context(_context, _label):
                    preflight.append(runtime.input_state.is_mouse_blocked())
                    return context

                def roster_check(hwnd):
                    preflight.append(runtime.input_state.is_mouse_blocked())
                    return [
                        SimpleNamespace(handle=h, display_name=str(h))
                        for h in (hwnd, *(target for target in handles if target != hwnd))
                    ]

                def focus(hwnd, *_args, **_kwargs):
                    self.assertTrue(runtime.input_state.is_mouse_blocked())
                    active[0] = hwnd
                    return True

                def send(hwnd, *_args, **_kwargs):
                    self.assertTrue(runtime.input_state.is_mouse_blocked())
                    self.assertEqual(active[0], hwnd)
                    emitted.append(hwnd)
                    return True

                with (
                    patch.object(macro, "_validated_context",
                                 side_effect=check_context),
                    patch.object(macro, "_target_point",
                                 return_value=(20, 25)),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(11, 12)),
                    patch("app.macros.switch_click.set_cursor_pos"),
                    patch("app.macros.switch_click.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process",
                          return_value=True),
                    patch.object(runtime.switch_character,
                                 "ordered_clients_from_source",
                                 side_effect=roster_check),
                    patch("app.macros.switch_click.activate_window",
                          side_effect=focus),
                    patch("app.macros.switch_click.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.switch_click.send_client_click",
                          side_effect=send),
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=handles[0],
                        mirror_target_handles=handles,
                    )
                self.assertEqual(preflight, [False, False])
                self.assertEqual(emitted, list(handles))
                self.assertFalse(runtime.input_state.is_mouse_blocked())
                runtime.logger.info.assert_any_call(
                    "%s blocage_souris_ms=%.2f cibles=%s",
                    "Miroir", unittest.mock.ANY, count,
                )

    def test_switch_click_invalid_roster_does_not_block_or_inject(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext
        from app.input.input_state import InputState

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.input_state = InputState()
                runtime.macro_lock.should_stop.return_value = False
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=h, display_name=str(h))
                    for h in handles[:-1]
                ]
                macro = SwitchClickMacro(runtime)
                context = SwitchClickContext(handles[0], 20, 25, 0.3, 0.4, "cursor")
                with (
                    patch.object(macro, "_validated_context",
                                 return_value=context),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(11, 12)),
                    patch("app.macros.switch_click.activate_window") as activate,
                    patch("app.macros.switch_click.send_client_click") as send,
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=handles[0],
                        mirror_target_handles=handles,
                    )
                self.assertFalse(runtime.input_state.is_mouse_blocked())
                activate.assert_not_called()
                send.assert_not_called()

    def test_switch_click_stop_before_delivery_never_takes_mouse_block(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext
        from app.input.input_state import InputState

        runtime = self._runtime(primary=101, handles=(101, 202))
        runtime.input_state = InputState()
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101, display_name="A"),
            SimpleNamespace(handle=202, display_name="B"),
        ]
        runtime.macro_lock.should_stop.return_value = True
        macro = SwitchClickMacro(runtime)
        context = SwitchClickContext(101, 20, 25, 0.3, 0.4, "cursor")
        with (
            patch.object(macro, "_validated_context", return_value=context),
            patch("app.macros.switch_click.current_cursor_pos",
                  return_value=(11, 12)),
            patch("app.macros.switch_click.activate_window") as activate,
        ):
            macro._run(
                "Left", 1, "Miroir", context,
                exact_source_handle=101,
                mirror_target_handles=(101, 202),
            )
        self.assertFalse(runtime.input_state.is_mouse_blocked())
        activate.assert_not_called()

    def test_switch_click_spawn_refusal_or_exception_keeps_native_mouse_free(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext
        from app.input.input_state import InputState

        for failure in ("refused", "exception"):
            with self.subTest(failure=failure):
                runtime = self._runtime(primary=101, handles=(101, 202))
                runtime.input_state = InputState()
                runtime._spawn_macro.side_effect = (
                    RuntimeError("thread creation refused")
                    if failure == "exception" else None
                )
                runtime._spawn_macro.return_value = False
                context = SwitchClickContext(101, 20, 25, 0.3, 0.4, "cursor")
                macro = SwitchClickMacro(runtime)
                if failure == "exception":
                    with self.assertRaisesRegex(RuntimeError, "thread creation refused"):
                        macro.run_async("Left", 20, 25, 1, "Miroir",
                                        captured_context=context)
                else:
                    self.assertFalse(macro.run_async(
                        "Left", 20, 25, 1, "Miroir",
                        captured_context=context,
                    ))
                self.assertFalse(runtime.input_state.is_mouse_blocked())

    def test_queued_mirror_click_owns_physical_down_up_before_worker_2_to_8(self):
        import ctypes
        from app.core.runtime_state import AtlasRuntime
        from app.input.input_state import InputState
        from app.input.mouse_hooks import (
            MouseHook, MSLLHOOKSTRUCT, WM_LBUTTONDOWN, WM_LBUTTONUP,
        )
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime._running = True
                runtime._admin_ok = True
                runtime.input_state = InputState()
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=35,
                    input_double_gap_ms=5, switch_background_post_up_ms=0,
                    switch_client_settle_ms=0,
                )
                runtime._spawn_macro.return_value = True
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=h, display_name=str(h))
                    for h in handles
                ]
                macro = SwitchClickMacro(runtime)
                runtime.switch_click = macro
                context = SwitchClickContext(handles[0], 20, 25, 0.25, 0.5, "cursor")
                hook = MouseHook(
                    runtime.input_state, Mock(), Mock(),
                    lambda button, x, y: AtlasRuntime._handle_mouse_click(
                        runtime, button, x, y,
                    ),
                )
                event = MSLLHOOKSTRUCT()
                event.pt.x = 20
                event.pt.y = 25
                event.flags = 0
                event.dwExtraInfo = None
                native = Mock(return_value=77)
                active = [handles[0]]
                sent = []
                def focus(hwnd, *_args, **_kwargs):
                    self.assertTrue(runtime.input_state.is_mouse_blocked())
                    active[0] = hwnd
                    return True
                def send(hwnd, *_args, **_kwargs):
                    self.assertTrue(runtime.input_state.is_mouse_blocked())
                    sent.append(hwnd)
                    return True

                with (
                    patch.object(macro, "_capture_trigger_context",
                                 return_value=context),
                    patch.object(macro, "_validated_context",
                                 return_value=context),
                    patch.object(macro, "_target_point",
                                 return_value=(20, 25)),
                    patch("app.windows.unity_windows.is_unity_window",
                          return_value=True),
                    patch("app.windows.unity_windows.find_known_client_from_point",
                          return_value=handles[0]),
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=handles[0]),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.switch_click.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.switch_click.set_cursor_pos"),
                    patch("app.macros.switch_click.activate_window",
                          side_effect=focus),
                    patch("app.macros.switch_click.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.switch_click.send_client_click",
                          side_effect=send),
                    patch.object(ctypes, "windll",
                        SimpleNamespace(user32=SimpleNamespace(
                            CallNextHookEx=native,
                        )), create=True),
                ):
                    ptr = ctypes.addressof(event)
                    # The source DOWN is consumed by the hook exactly once.
                    self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, ptr), 1)
                    self.assertIn(WM_LBUTTONUP, hook._consumed_releases)
                    self.assertFalse(runtime.input_state.is_mouse_blocked())
                    # Even with no physical block yet, the paired UP is owned
                    # by the hook and must not leak to a different client.
                    self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, ptr), 1)
                    self.assertFalse(hook._consumed_releases)
                    native.assert_not_called()
                    runtime._spawn_macro.assert_called_once()
                    runtime._spawn_macro.call_args.args[1]()
                self.assertEqual(sent, list(handles))
                self.assertFalse(runtime.input_state.is_mouse_blocked())

    def test_queued_mirror_click_rejected_preflight_never_leaks_native_up(self):
        import ctypes
        from app.input.input_state import InputState
        from app.input.mouse_hooks import (
            MouseHook, MSLLHOOKSTRUCT, WM_LBUTTONDOWN, WM_LBUTTONUP,
        )
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        runtime = self._runtime(primary=101, handles=(101, 202))
        runtime._running = True
        runtime._admin_ok = True
        runtime.input_state = InputState()
        runtime.macro_lock.should_stop.return_value = False
        runtime._spawn_macro.return_value = True
        macro = SwitchClickMacro(runtime)
        runtime.switch_click = macro
        context = SwitchClickContext(101, 20, 25, 0.25, 0.5, "cursor")
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101, display_name="source"),
        ]
        hook = MouseHook(
            runtime.input_state, Mock(), Mock(),
            lambda button, x, y: AtlasRuntime._handle_mouse_click(
                runtime, button, x, y,
            ),
        )
        event = MSLLHOOKSTRUCT()
        event.pt.x = 20
        event.pt.y = 25
        native = Mock(return_value=77)
        with (
            patch.object(macro, "_capture_trigger_context",
                         return_value=context),
            patch.object(macro, "_validated_context",
                         return_value=context),
            patch("app.windows.unity_windows.is_unity_window",
                  return_value=True),
            patch("app.windows.unity_windows.foreground_window",
                  return_value=101),
            patch("app.windows.unity_windows.find_known_client_from_point",
                  return_value=101),
            patch("app.macros.mirror_plan.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.switch_click.current_cursor_pos",
                  return_value=(12, 14)),
            patch("app.macros.switch_click.activate_window") as activate,
            patch("app.macros.switch_click.send_client_click") as sender,
            patch.object(ctypes, "windll",
                SimpleNamespace(user32=SimpleNamespace(
                    CallNextHookEx=native,
                )), create=True),
        ):
            ptr = ctypes.addressof(event)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, ptr), 1)
            runtime._spawn_macro.call_args.args[1]()
            self.assertFalse(runtime.input_state.is_mouse_blocked())
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, ptr), 1)
        activate.assert_not_called()
        sender.assert_not_called()
        native.assert_not_called()
        self.assertFalse(hook._consumed_releases)

    def test_mirror_click_failed_send_stops_remaining_clients_and_restoration(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for successful_before_failure in (0, 1):
            with self.subTest(successful_before_failure=successful_before_failure):
                runtime = Mock()
                runtime.settings.primary_handle = 101
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=35,
                    input_double_gap_ms=5, switch_background_post_up_ms=0,
                    switch_client_settle_ms=0,
                )
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=h, display_name=str(h))
                    for h in (101, 202, 303)
                ]
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
                macro = SwitchClickMacro(runtime)
                sent_results = [True] * successful_before_failure + [False]
                focus_sequence = (
                    [101] if successful_before_failure == 0
                    else [101, 202, 202]
                )
                if successful_before_failure == 0:
                    focus_sequence.append(101)
                with (
                    patch.object(macro, "_validated_context", return_value=context),
                    patch.object(macro, "_target_point", return_value=(20, 30)),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.switch_click.set_cursor_pos") as move,
                    patch("app.macros.switch_click.is_unity_window", return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process", return_value=True),
                    patch("app.macros.switch_click.activate_window",
                          return_value=True) as activate,
                    patch("app.macros.switch_click.foreground_window",
                          side_effect=focus_sequence),
                    patch("app.macros.switch_click.send_client_click",
                          side_effect=sent_results) as send,
                ):
                    macro._run("Left", 1, "Miroir", context)
                self.assertEqual(send.call_count, successful_before_failure + 1)
                self.assertEqual(activate.call_count, successful_before_failure + 1)
                move.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once()
                runtime._emit_status.assert_called_once_with(
                    f"Miroir incomplet : {successful_before_failure}/3 fenêtres."
                )
                runtime.logger.warning.assert_any_call(
                    "%s interrompu: SendInput clic refusé hwnd=%s",
                    "Miroir", 101 if not successful_before_failure else 202,
                )

    def test_switch_click_sender_refusal_after_focus_theft_never_restores(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        runtime = Mock()
        runtime.settings.primary_handle = 101
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101, display_name="source"),
            SimpleNamespace(handle=202, display_name="next"),
        ]
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0,
            activate_attempts=1, activate_retry_ms=0,
            input_double_gap_ms=5, switch_click_down_ms=1,
            switch_background_post_up_ms=0, switch_client_settle_ms=0,
        )
        runtime.macro_lock.should_stop.return_value = False
        context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
        macro = SwitchClickMacro(runtime)
        with (
            patch.object(macro, "_validated_context", return_value=context),
            patch.object(macro, "_target_point", return_value=(20, 30)),
            patch("app.macros.switch_click.current_cursor_pos",
                  return_value=(12, 14)),
            patch("app.macros.switch_click.set_cursor_pos") as move,
            patch("app.macros.switch_click.is_unity_window", return_value=True),
            patch("app.macros.switch_click.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_click.activate_window", return_value=True),
            patch("app.macros.switch_click.foreground_window",
                  side_effect=[101, 999]),
            patch("app.macros.switch_click.send_client_click",
                  return_value=False) as send,
        ):
            macro._run("Left", 1, "Miroir", context)
        send.assert_called_once()
        move.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_called_once()
        runtime._emit_status.assert_called_once_with(
            "Miroir interrompu : 0/2 fenêtres."
        )

    def test_switch_click_stop_during_delivery_never_restores_cursor_or_favorite(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for label in ("Miroir", "Switch clique"):
            with self.subTest(label=label):
                runtime = Mock()
                runtime.settings.primary_handle = 101
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=35,
                    input_double_gap_ms=5, switch_background_post_up_ms=0,
                    switch_client_settle_ms=0,
                )
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=101, display_name="source"),
                    SimpleNamespace(handle=202, display_name="target"),
                ]
                stopped = [False]
                runtime.macro_lock.should_stop.side_effect = lambda: stopped[0]
                context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
                macro = SwitchClickMacro(runtime)

                def stop_during_send(*_args, **_kwargs):
                    stopped[0] = True
                    return True

                with (
                    patch.object(macro, "_validated_context", return_value=context),
                    patch.object(macro, "_target_point", return_value=(20, 30)),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.switch_click.set_cursor_pos") as move,
                    patch("app.macros.switch_click.is_unity_window", return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process", return_value=True),
                    patch("app.macros.switch_click.activate_window", return_value=True),
                    patch("app.macros.switch_click.foreground_window", return_value=101),
                    patch("app.macros.switch_click.send_client_click",
                          side_effect=stop_during_send) as sender,
                ):
                    macro._run("Left", 1, label, context)
                sender.assert_called_once()
                move.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once()

    def test_switch_click_aborts_when_focus_stolen_before_input(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        handles = (101, 202, 303)
        runtime = Mock()
        runtime.settings.primary_handle = 101
        runtime.settings.macro_mode = "mirror"
        runtime.settings.clients = [
            SimpleNamespace(handle=handle) for handle in handles
        ]
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=handle, display_name=str(handle))
            for handle in handles
        ]
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0,
            activate_attempts=1, activate_retry_ms=0,
            input_double_gap_ms=5, switch_click_down_ms=1,
            switch_background_post_up_ms=0, switch_client_settle_ms=0,
        )
        macro = SwitchClickMacro(runtime)
        context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
        with (
            patch("app.macros.switch_click.current_cursor_pos", return_value=(100, 200)),
            patch("app.macros.switch_click.set_cursor_pos"),
            patch("app.macros.switch_click.is_unity_window", return_value=True),
            patch("app.macros.switch_click.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_click.activate_window", return_value=True),
            patch("app.macros.switch_click.foreground_window", side_effect=[101, 999]),
            patch("app.macros.switch_click.send_client_click", return_value=True) as sender,
            patch.object(macro, "_target_point", return_value=(20, 30)),
        ):
            macro._run(
                "Left", 1, "Miroir", context,
                exact_source_handle=101, mirror_target_handles=handles,
            )
        sender.assert_called_once()
        self.assertEqual(sender.call_args.args[0], 101)
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.warning.assert_any_call(
            "%s interrompu: focus perdu avant clic hwnd=%s", "Miroir", 202,
        )
        runtime.input_state.end_mouse_block.assert_called_once()
        runtime._emit_status.assert_called_once_with(
            "Miroir interrompu : 1/3 fenêtres."
        )

    def test_switch_click_never_sends_when_first_target_focus_unconfirmed(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        handles = (101, 202)
        runtime = Mock()
        runtime.settings.primary_handle = 101
        runtime.settings.macro_mode = "mirror"
        runtime.settings.clients = [
            SimpleNamespace(handle=handle) for handle in handles
        ]
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=handle, display_name=str(handle))
            for handle in handles
        ]
        runtime.macro_lock.should_stop.return_value = False
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0,
            activate_attempts=1, activate_retry_ms=0,
            input_double_gap_ms=5, switch_click_down_ms=1,
            switch_background_post_up_ms=0, switch_client_settle_ms=0,
        )
        macro = SwitchClickMacro(runtime)
        context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
        with (
            patch("app.macros.switch_click.current_cursor_pos", return_value=(100, 200)),
            patch("app.macros.switch_click.set_cursor_pos"),
            patch("app.macros.switch_click.is_unity_window", return_value=True),
            patch("app.macros.switch_click.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_click.activate_window", return_value=True),
            patch("app.macros.switch_click.foreground_window", return_value=999),
            patch("app.macros.switch_click.send_client_click") as sender,
        ):
            macro._run(
                "Left", 1, "Miroir", context,
                exact_source_handle=101, mirror_target_handles=handles,
            )
        sender.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_called_once()

    def test_switch_click_without_confirmed_target_never_steals_focus(self):
        from app.macros.switch_click import SwitchClickContext, SwitchClickMacro

        for visible, activated in ((False, False), (True, False)):
            with self.subTest(visible=visible, activated=activated):
                runtime = Mock()
                runtime.macro_lock.should_stop.return_value = False
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=101, display_name="source"),
                    SimpleNamespace(handle=202, display_name="target"),
                ]
                macro = SwitchClickMacro(runtime)
                context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
                with (
                    patch.object(macro, "_validated_context", return_value=context),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(15, 20)),
                    patch("app.macros.switch_click.set_cursor_pos") as move,
                    patch("app.macros.switch_click.is_unity_window",
                          return_value=visible),
                    patch("app.macros.switch_click.activate_window",
                          return_value=activated) as focus,
                    patch("app.macros.switch_click.send_client_click") as send,
                ):
                    macro._run("Left", 1, "Miroir", context)
                send.assert_not_called()
                move.assert_not_called()
                if not visible:
                    focus.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once()
                runtime._emit_status.assert_called_once_with(
                    "Miroir incomplet : 0/2 fenêtres."
                )

    def test_switch_click_focus_exception_preserves_user_cursor_and_focus(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        handles = (101, 202)
        runtime = Mock()
        runtime.settings.primary_handle = 101
        runtime.settings.macro_mode = "mirror"
        runtime.settings.clients = [
            SimpleNamespace(handle=handle) for handle in handles
        ]
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=hwnd, display_name=str(hwnd))
            for hwnd in handles
        ]
        runtime.macro_lock.should_stop.return_value = False
        macro = SwitchClickMacro(runtime)
        context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
        with (
            patch.object(macro, "_validated_context", return_value=context),
            patch("app.macros.switch_click.current_cursor_pos", return_value=(10, 15)),
            patch("app.macros.switch_click.set_cursor_pos") as move,
            patch("app.macros.switch_click.is_unity_window", return_value=True),
            patch("app.macros.switch_click.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_click.activate_window",
                  side_effect=RuntimeError("focus denied")),
            patch("app.macros.switch_click.send_client_click") as send,
        ):
            macro._run(
                "Left", 1, "Miroir", context,
                exact_source_handle=101, mirror_target_handles=handles,
            )
        send.assert_not_called()
        move.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_called_once()
        runtime._emit_status.assert_called_once_with(
            "Miroir interrompu : 0/2 fenêtres."
        )

    def test_switchclick_mirror_rejects_changes_during_target_lookup(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for change in ("roster", "process", "stop"):
            with self.subTest(change=change):
                handles = (101, 202)
                runtime = Mock()
                runtime.settings.primary_handle = 101
                runtime.settings.macro_mode = "mirror"
                runtime.settings.clients = [
                    SimpleNamespace(handle=hwnd) for hwnd in handles
                ]
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0,
                    activate_attempts=1, activate_retry_ms=0,
                )
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=hwnd, display_name=str(hwnd))
                    for hwnd in handles
                ]
                stopped = [False]
                trusted = [True]
                runtime.macro_lock.should_stop.side_effect = lambda: stopped[0]
                macro = SwitchClickMacro(runtime)
                context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")

                def lookup(_hwnd, _context):
                    if change == "roster":
                        runtime.settings.clients = [
                            SimpleNamespace(handle=101),
                            SimpleNamespace(handle=303),
                        ]
                    elif change == "process":
                        trusted[0] = False
                    else:
                        stopped[0] = True
                    return (20, 30)

                with (
                    patch.object(macro, "_validated_context", return_value=context),
                    patch.object(macro, "_target_point", side_effect=lookup),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(20, 30)),
                    patch("app.macros.switch_click.set_cursor_pos") as cursor,
                    patch("app.macros.switch_click.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process",
                          side_effect=lambda _hwnd: trusted[0]),
                    patch("app.macros.switch_click.activate_window",
                          return_value=True) as focus,
                    patch("app.macros.switch_click.foreground_window",
                          return_value=101),
                    patch("app.macros.switch_click.send_client_click") as send,
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=101,
                        mirror_target_handles=handles,
                    )
                focus.assert_called_once()
                send.assert_not_called()
                cursor.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once()
                status = "Miroir interrompu" if change == "stop" else "Miroir incomplet"
                runtime._emit_status.assert_called_once_with(
                    f"{status} : 0/2 fenêtres."
                )

    def test_mirror_partial_delivery_is_not_reported_complete(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        runtime = Mock()
        clients = [
            SimpleNamespace(handle=101, display_name="source"),
            SimpleNamespace(handle=202, display_name="offline"),
        ]
        runtime.settings.primary_handle = 101
        runtime.settings.macro_mode = "mirror"
        runtime.settings.clients = clients
        runtime.settings.client_by_handle.return_value = clients[0]
        runtime.switch_character.ordered_clients_from_source.return_value = clients
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0,
            activate_attempts=1, activate_retry_ms=0,
            input_double_gap_ms=5, switch_click_down_ms=1,
            switch_background_post_up_ms=0, switch_client_settle_ms=0,
        )
        macro = SwitchClickMacro(runtime)
        context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
        with (
            patch("app.macros.switch_click.current_cursor_pos", return_value=(20, 30)),
            patch("app.macros.switch_click.set_cursor_pos"),
            patch("app.macros.switch_click.is_unity_window",
                  side_effect=lambda hwnd: hwnd == 101),
            patch("app.macros.switch_click.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_click.activate_window", return_value=True),
            patch("app.macros.switch_click.foreground_window", return_value=101),
            patch("app.macros.switch_click.send_client_click", return_value=True) as sender,
            patch.object(macro, "_target_point", return_value=(20, 30)),
        ):
            macro._run(
                "Left", 1, "Miroir", context,
                exact_source_handle=101, mirror_target_handles=(101, 202),
            )
        sender.assert_called_once()
        runtime._emit_status.assert_called_once_with(
            "Miroir incomplet : 1/2 fenêtres."
        )

    def test_consumed_physical_down_swallows_matching_up_without_affecting_other_buttons(self):
        import ctypes
        import logging
        from app.input.mouse_hooks import (
            MouseHook, MSLLHOOKSTRUCT, WM_LBUTTONDOWN, WM_LBUTTONUP,
            WM_RBUTTONUP, LLMHF_INJECTED,
        )
        from app.input.input_state import InputState, SyntheticInputGuard

        logger = logging.getLogger("test_mirror_mouse_pair")
        cb = Mock(return_value=True)
        hook = MouseHook(InputState(), SyntheticInputGuard(logger), logger, cb)
        event = MSLLHOOKSTRUCT()
        event.pt.x, event.pt.y = 50, 80
        user32 = SimpleNamespace(CallNextHookEx=Mock(return_value=37))
        with patch.object(ctypes, "windll", SimpleNamespace(user32=user32), create=True):
            pointer = ctypes.addressof(event)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, pointer), 1)
            self.assertEqual(cb.call_count, 1)
            self.assertEqual(hook._consumed_releases, {WM_LBUTTONUP})
            # Synthetic ups do not discharge the user's pending physical up.
            event.flags = LLMHF_INJECTED
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, pointer), 37)
            self.assertEqual(hook._consumed_releases, {WM_LBUTTONUP})
            event.flags = 0
            self.assertEqual(hook._mouse_proc(0, WM_RBUTTONUP, pointer), 37)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, pointer), 1)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, pointer), 37)
            self.assertEqual(hook._consumed_releases, set())

    def test_pending_physical_release_is_consumed_even_during_mouse_block(self):
        import ctypes
        import logging
        from app.input.mouse_hooks import (
            MouseHook, MSLLHOOKSTRUCT, WM_RBUTTONDOWN, WM_RBUTTONUP,
        )
        from app.input.input_state import InputState, SyntheticInputGuard

        logger = logging.getLogger("test_mirror_release_during_block")
        state = InputState()
        hook = MouseHook(state, SyntheticInputGuard(logger), logger, Mock(return_value=True))
        event = MSLLHOOKSTRUCT()
        event.pt.x, event.pt.y = 10, 20
        user32 = SimpleNamespace(CallNextHookEx=Mock(return_value=37))
        with patch.object(ctypes, "windll", SimpleNamespace(user32=user32), create=True):
            pointer = ctypes.addressof(event)
            self.assertEqual(hook._mouse_proc(0, WM_RBUTTONDOWN, pointer), 1)
            state.begin_mouse_block("Miroir")
            self.assertEqual(hook._mouse_proc(0, WM_RBUTTONUP, pointer), 1)
            state.end_mouse_block()
            self.assertEqual(hook._mouse_proc(0, WM_RBUTTONUP, pointer), 37)
            self.assertEqual(hook._consumed_releases, set())

    def test_mirror_worker_refuses_source_change_after_click_consumption(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext
        runtime = Mock()
        runtime.settings.primary_handle = 202
        runtime.macro_lock.should_stop.return_value = False
        macro = SwitchClickMacro(runtime)
        old = SwitchClickContext(101, 12, 23, 0.4, 0.5, "cursor")
        recovered = SwitchClickContext(202, 12, 23, 0.4, 0.5, "recovered")
        with (
            patch.object(macro, "_validated_context", return_value=recovered),
            patch("app.macros.switch_click.current_cursor_pos", return_value=(40, 50)),
            patch("app.macros.switch_click.set_cursor_pos"),
            patch("app.macros.switch_click.send_client_click") as sender,
        ):
            macro._run("Left", 1, "Miroir", old, exact_source_handle=101)
        sender.assert_not_called()
        runtime.switch_character.ordered_clients_from_source.assert_not_called()


    def test_captured_mirror_click_respects_favorite_last_for_two_to_eight(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                slots = tuple(range(101, 101 + count))
                favorite = slots[-1]
                handles = (favorite, *slots[:-1])
                runtime = Mock()
                runtime.settings.primary_handle = favorite
                runtime.settings.macro_mode = "mirror"
                runtime.settings.clients = [
                    SimpleNamespace(handle=h) for h in slots
                ]
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=35,
                    input_double_gap_ms=5, switch_background_post_up_ms=0,
                    switch_client_settle_ms=0,
                )
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=h, display_name=str(h))
                    for h in handles
                ]
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                context = SwitchClickContext(
                    favorite, 20, 30, 0.5, 0.5, "cursor",
                )
                macro = SwitchClickMacro(runtime)
                with (
                    patch.object(macro, "_validated_context", return_value=context),
                    patch.object(macro, "_target_point", return_value=(20, 30)),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.switch_click.set_cursor_pos") as move,
                    patch("app.macros.switch_click.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.switch_click.activate_window",
                          return_value=True) as activate,
                    patch("app.macros.switch_click.foreground_window",
                          side_effect=[*handles, handles[-1], handles[-1]]),
                    patch("app.macros.switch_click.send_client_click",
                          return_value=True) as send,
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=favorite,
                        mirror_target_handles=handles,
                    )
                self.assertEqual(activate.call_count, count)
                self.assertEqual(
                    [c.args[0] for c in send.call_args_list], list(handles),
                )
                move.assert_called_once_with(12, 14)
                runtime.switch_character.restore_preferred_client.assert_called_once_with(
                    "Miroir",
                )
                runtime._emit_status.assert_called_once_with(
                    f"Miroir : {count}/{count} fenêtres."
                )

    def test_mirror_does_not_restore_cursor_or_favorite_after_user_focus_change(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = Mock()
                runtime.settings.primary_handle = handles[0]
                runtime.settings.macro_mode = "mirror"
                runtime.settings.clients = [
                    SimpleNamespace(handle=h) for h in handles
                ]
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0,
                    activate_attempts=1, activate_retry_ms=0,
                    switch_click_down_ms=35, input_double_gap_ms=5,
                    switch_background_post_up_ms=0, switch_client_settle_ms=0,
                )
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=h, display_name=str(h))
                    for h in handles
                ]
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                macro = SwitchClickMacro(runtime)
                context = SwitchClickContext(
                    handles[0], 20, 30, 0.5, 0.5, "cursor",
                )
                with (
                    patch.object(macro, "_validated_context", return_value=context),
                    patch.object(macro, "_target_point", return_value=(20, 30)),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.switch_click.set_cursor_pos") as move,
                    patch("app.macros.switch_click.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.switch_click.activate_window",
                          return_value=True) as focus,
                    # After the last successful click, the user focuses
                    # another app before cleanup begins.
                    patch("app.macros.switch_click.foreground_window",
                          side_effect=[*handles, 999]),
                    patch("app.macros.switch_click.send_client_click",
                          return_value=True) as send,
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=handles[0],
                        mirror_target_handles=handles,
                    )
                self.assertEqual(focus.call_count, count)
                self.assertEqual(send.call_count, count)
                move.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once()
                runtime.logger.info.assert_any_call(
                    "%s: restauration ignorée, focus utilisateur changé.", "Miroir",
                )
                runtime._emit_status.assert_called_once_with(
                    f"Miroir : {count}/{count} fenêtres."
                )

    def test_mirror_cleanup_rejects_stale_roster_after_last_successful_send(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            for change in ("roster", "favorite", "mode"):
                with self.subTest(count=count, change=change):
                    handles = tuple(range(101, 101 + count))
                    runtime = Mock()
                    runtime.settings.primary_handle = handles[0]
                    runtime.settings.macro_mode = "mirror"
                    runtime.settings.clients = [
                        SimpleNamespace(handle=h) for h in handles
                    ]
                    runtime.settings.timings = SimpleNamespace(
                        switch_background_pre_click_ms=0, activate_attempts=1,
                        activate_retry_ms=0, switch_click_down_ms=35,
                        input_double_gap_ms=5, switch_background_post_up_ms=0,
                        switch_client_settle_ms=0,
                    )
                    runtime.switch_character.ordered_clients_from_source.return_value = [
                        SimpleNamespace(handle=h, display_name=str(h))
                        for h in handles
                    ]
                    runtime.macro_lock.should_stop.return_value = False
                    runtime.macro_lock.wait.return_value = False
                    active = [handles[0]]
                    sent = [0]

                    def change_roster():
                        if change == "roster":
                            runtime.settings.clients = [
                                SimpleNamespace(handle=h)
                                for h in (*handles[:-1], 999)
                            ]
                        elif change == "favorite":
                            runtime.settings.primary_handle = handles[-1]
                        else:
                            runtime.settings.macro_mode = "macro"

                    def activate(hwnd, *_args, **_kwargs):
                        active[0] = hwnd
                        return True

                    def sender(*_args, **_kwargs):
                        sent[0] += 1
                        if sent[0] == count:
                            change_roster()
                        return True

                    macro = SwitchClickMacro(runtime)
                    context = SwitchClickContext(
                        handles[0], 20, 30, 0.5, 0.5, "cursor",
                    )
                    with (
                        patch.object(macro, "_validated_context", return_value=context),
                        patch.object(macro, "_target_point", return_value=(20, 30)),
                        patch("app.macros.switch_click.current_cursor_pos",
                              return_value=(12, 14)),
                        patch("app.macros.switch_click.set_cursor_pos") as move,
                        patch("app.macros.switch_click.is_unity_window",
                              return_value=True),
                        patch("app.macros.switch_click.is_dofus_unity_process",
                              return_value=True),
                        patch("app.macros.switch_click.activate_window",
                              side_effect=activate),
                        patch("app.macros.switch_click.foreground_window",
                              side_effect=lambda: active[0]),
                        patch("app.macros.switch_click.send_client_click",
                              side_effect=sender) as send,
                    ):
                        macro._run(
                            "Left", 1, "Miroir", context,
                            exact_source_handle=handles[0],
                            mirror_target_handles=handles,
                        )
                    self.assertEqual(send.call_count, count)
                    move.assert_not_called()
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    runtime.input_state.end_mouse_block.assert_called_once()
                    runtime.logger.info.assert_any_call(
                        "%s: restauration ignorée, favori ou roster changé.", "Miroir",
                    )
                    runtime._emit_status.assert_called_once_with(
                        f"Miroir : {count}/{count} fenêtres."
                    )

    def test_mirror_cleanup_rechecks_favorite_changed_during_cursor_restore(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = Mock()
                runtime.settings.primary_handle = handles[0]
                runtime.settings.macro_mode = "mirror"
                runtime.settings.clients = [
                    SimpleNamespace(handle=h) for h in handles
                ]
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=35,
                    input_double_gap_ms=5, switch_background_post_up_ms=0,
                    switch_client_settle_ms=0,
                )
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=h, display_name=str(h))
                    for h in handles
                ]
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                active = [handles[0]]

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def move(x, y):
                    if (x, y) == (12, 14):
                        runtime.settings.primary_handle = handles[-1]

                macro = SwitchClickMacro(runtime)
                context = SwitchClickContext(
                    handles[0], 20, 30, 0.5, 0.5, "cursor",
                )
                with (
                    patch.object(macro, "_validated_context", return_value=context),
                    patch.object(macro, "_target_point", return_value=(20, 30)),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.switch_click.set_cursor_pos",
                          side_effect=move) as cursor,
                    patch("app.macros.switch_click.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.switch_click.activate_window",
                          side_effect=activate),
                    patch("app.macros.switch_click.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.switch_click.send_client_click",
                          return_value=True) as send,
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=handles[0],
                        mirror_target_handles=handles,
                    )
                self.assertEqual(send.call_count, count)
                cursor.assert_called_once_with(12, 14)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once()
                runtime.logger.info.assert_any_call(
                    "%s: retour au favori ignoré, roster changé après curseur.",
                    "Miroir",
                )
                runtime._emit_status.assert_called_once_with(
                    f"Miroir : {count}/{count} fenêtres."
                )

    def test_mirror_does_not_steal_focus_if_cursor_restoration_switches_apps(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = Mock()
                runtime.settings.primary_handle = handles[0]
                runtime.settings.macro_mode = "mirror"
                runtime.settings.clients = [
                    SimpleNamespace(handle=h) for h in handles
                ]
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0,
                    activate_attempts=1, activate_retry_ms=0,
                    switch_click_down_ms=35, input_double_gap_ms=5,
                    switch_background_post_up_ms=0, switch_client_settle_ms=0,
                )
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=h, display_name=str(h))
                    for h in handles
                ]
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                active = [handles[0]]

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def move(x, y):
                    if (x, y) == (12, 14):
                        active[0] = 999

                macro = SwitchClickMacro(runtime)
                context = SwitchClickContext(
                    handles[0], 20, 30, 0.5, 0.5, "cursor",
                )
                with (
                    patch.object(macro, "_validated_context", return_value=context),
                    patch.object(macro, "_target_point", return_value=(20, 30)),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.switch_click.set_cursor_pos",
                          side_effect=move) as cursor,
                    patch("app.macros.switch_click.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.switch_click.activate_window",
                          side_effect=activate),
                    patch("app.macros.switch_click.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.switch_click.send_client_click",
                          return_value=True) as send,
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=handles[0],
                        mirror_target_handles=handles,
                    )
                self.assertEqual(send.call_count, count)
                cursor.assert_called_once_with(12, 14)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once()
                runtime.logger.info.assert_any_call(
                    "%s: retour au favori ignoré, focus changé après curseur.",
                    "Miroir",
                )
                runtime._emit_status.assert_called_once_with(
                    f"Miroir : {count}/{count} fenêtres."
                )

    def test_mirror_click_cleanup_unblocks_if_final_foreground_probe_fails(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        handles = (101, 202)
        runtime = Mock()
        runtime.settings.primary_handle = 101
        runtime.settings.macro_mode = "mirror"
        runtime.settings.clients = [
            SimpleNamespace(handle=h) for h in handles
        ]
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0, activate_attempts=1,
            activate_retry_ms=0, switch_click_down_ms=35,
            input_double_gap_ms=5, switch_background_post_up_ms=0,
            switch_client_settle_ms=0,
        )
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=h, display_name=str(h)) for h in handles
        ]
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
        macro = SwitchClickMacro(runtime)
        with (
            patch.object(macro, "_validated_context", return_value=context),
            patch.object(macro, "_target_point", return_value=(20, 30)),
            patch("app.macros.switch_click.current_cursor_pos",
                  return_value=(12, 14)),
            patch("app.macros.switch_click.set_cursor_pos") as move,
            patch("app.macros.switch_click.is_unity_window",
                  return_value=True),
            patch("app.macros.switch_click.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.switch_click.activate_window",
                  return_value=True),
            patch("app.macros.switch_click.foreground_window",
                  side_effect=[101, 202, OSError("foreground refused")]),
            patch("app.macros.switch_click.send_client_click",
                  return_value=True) as send,
        ):
            macro._run(
                "Left", 1, "Miroir", context,
                exact_source_handle=101, mirror_target_handles=handles,
            )
        self.assertEqual(send.call_count, 2)
        move.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_called_once()
        runtime.logger.exception.assert_any_call(
            "%s: focus non vérifiable avant restauration.", "Miroir",
        )

    def test_mirror_click_aborts_during_hover_when_roster_becomes_stale(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            for change in ("roster", "favorite", "mode", "stop"):
                with self.subTest(clients=count, change=change):
                    handles = tuple(range(101, 101 + count))
                    runtime = Mock()
                    runtime.settings.primary_handle = handles[0]
                    runtime.settings.macro_mode = "mirror"
                    runtime.settings.clients = [
                        SimpleNamespace(handle=h) for h in handles
                    ]
                    runtime.settings.timings = SimpleNamespace(
                        switch_background_pre_click_ms=0,
                        activate_attempts=1, activate_retry_ms=0,
                        switch_click_down_ms=35, input_double_gap_ms=5,
                        switch_background_post_up_ms=0,
                        switch_client_settle_ms=0,
                    )
                    runtime.switch_character.ordered_clients_from_source.return_value = [
                        SimpleNamespace(handle=h, display_name=str(h))
                        for h in handles
                    ]
                    stopped = [False]
                    runtime.macro_lock.should_stop.side_effect = lambda: stopped[0]
                    runtime.macro_lock.wait.return_value = False
                    macro = SwitchClickMacro(runtime)
                    context = SwitchClickContext(
                        handles[0], 20, 30, 0.5, 0.5, "cursor",
                    )

                    def sender(*_args, **kwargs):
                        self.assertFalse(kwargs["should_stop"]())
                        if change == "roster":
                            # Reversing a two-client roster leaves the
                            # favorite-first delivery order unchanged. Use a
                            # genuine HWND replacement for every team size.
                            runtime.settings.clients = [
                                SimpleNamespace(handle=h)
                                for h in (*handles[:-1], 999)
                            ]
                        elif change == "favorite":
                            runtime.settings.primary_handle = handles[-1]
                        elif change == "mode":
                            runtime.settings.macro_mode = "macro"
                        else:
                            stopped[0] = True
                        self.assertTrue(kwargs["should_stop"]())
                        return False

                    with (
                        patch.object(macro, "_validated_context", return_value=context),
                        patch.object(macro, "_target_point", return_value=(20, 30)),
                        patch("app.macros.switch_click.current_cursor_pos",
                              return_value=(12, 14)),
                        patch("app.macros.switch_click.set_cursor_pos") as move,
                        patch("app.macros.switch_click.is_unity_window",
                              return_value=True),
                        patch("app.macros.switch_click.is_dofus_unity_process",
                              return_value=True),
                        patch("app.macros.switch_click.activate_window",
                              return_value=True) as activate,
                        patch("app.macros.switch_click.foreground_window",
                              return_value=handles[0]),
                        patch("app.macros.switch_click.send_client_click",
                              side_effect=sender) as send,
                    ):
                        macro._run(
                            "Left", 1, "Miroir", context,
                            exact_source_handle=handles[0],
                            mirror_target_handles=handles,
                        )
                    activate.assert_called_once()
                    send.assert_called_once()
                    move.assert_not_called()
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    runtime.input_state.end_mouse_block.assert_called_once()
                    state = "interrompu" if change == "stop" else "incomplet"
                    runtime._emit_status.assert_called_once_with(
                        f"Miroir {state} : 0/{count} fenêtres."
                    )

    def test_mirror_click_roster_reordered_during_first_send_stops_fanout(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        runtime = Mock()
        runtime.settings.primary_handle = 101
        runtime.settings.macro_mode = "mirror"
        runtime.settings.clients = [
            SimpleNamespace(handle=h) for h in (101, 202, 303)
        ]
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0, activate_attempts=1,
            activate_retry_ms=0, switch_click_down_ms=35,
            input_double_gap_ms=5, switch_background_post_up_ms=0,
            switch_client_settle_ms=0,
        )
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=h, display_name=str(h))
            for h in (101, 202, 303)
        ]
        runtime.macro_lock.should_stop.return_value = False
        context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
        macro = SwitchClickMacro(runtime)

        def send_then_reorder(*_args, **_kwargs):
            runtime.settings.clients = [
                SimpleNamespace(handle=h) for h in (101, 303, 202)
            ]
            return True

        with (
            patch.object(macro, "_validated_context", return_value=context),
            patch.object(macro, "_target_point", return_value=(20, 30)),
            patch("app.macros.switch_click.current_cursor_pos",
                  return_value=(12, 14)),
            patch("app.macros.switch_click.set_cursor_pos") as move,
            patch("app.macros.switch_click.is_unity_window", return_value=True),
            patch("app.macros.switch_click.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_click.activate_window",
                  return_value=True) as activate,
            patch("app.macros.switch_click.foreground_window", return_value=101),
            patch("app.macros.switch_click.send_client_click",
                  side_effect=send_then_reorder) as send,
        ):
            macro._run(
                "Left", 1, "Miroir", context,
                exact_source_handle=101,
                mirror_target_handles=(101, 202, 303),
            )
        activate.assert_called_once()
        send.assert_called_once()
        move.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Miroir incomplet : 1/3 fenêtres."
        )
        runtime.logger.warning.assert_any_call(
            "%s interrompu: roster changé avant clic hwnd=%s", "Miroir", 202,
        )

    def test_mirror_click_favorite_changed_during_activation_sends_nothing(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        runtime = Mock()
        runtime.settings.primary_handle = 101
        runtime.settings.macro_mode = "mirror"
        runtime.settings.clients = [
            SimpleNamespace(handle=h) for h in (101, 202)
        ]
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0, activate_attempts=1,
            activate_retry_ms=0, switch_click_down_ms=35,
            input_double_gap_ms=5, switch_background_post_up_ms=0,
            switch_client_settle_ms=0,
        )
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=h, display_name=str(h))
            for h in (101, 202)
        ]
        runtime.macro_lock.should_stop.return_value = False
        context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
        macro = SwitchClickMacro(runtime)

        def change_favorite(*_args, **_kwargs):
            runtime.settings.primary_handle = 202
            return True

        with (
            patch.object(macro, "_validated_context", return_value=context),
            patch.object(macro, "_target_point", return_value=(20, 30)),
            patch("app.macros.switch_click.current_cursor_pos",
                  return_value=(12, 14)),
            patch("app.macros.switch_click.set_cursor_pos") as move,
            patch("app.macros.switch_click.is_unity_window", return_value=True),
            patch("app.macros.switch_click.is_dofus_unity_process", return_value=True),
            patch("app.macros.switch_click.activate_window",
                  side_effect=change_favorite) as activate,
            patch("app.macros.switch_click.foreground_window", return_value=101),
            patch("app.macros.switch_click.send_client_click") as send,
        ):
            macro._run(
                "Left", 1, "Miroir", context,
                exact_source_handle=101,
                mirror_target_handles=(101, 202),
            )
        activate.assert_called_once()
        send.assert_not_called()
        move.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Miroir incomplet : 0/2 fenêtres."
        )
        runtime.logger.warning.assert_any_call(
            "%s interrompu: roster changé après focus hwnd=%s", "Miroir", 101,
        )

    def test_mirror_sender_aborts_when_clients_change_after_capture(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        runtime = Mock()
        runtime.settings.primary_handle = 101
        runtime.macro_lock.should_stop.return_value = False
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101),
            SimpleNamespace(handle=202),
            SimpleNamespace(handle=404),
        ]
        macro = SwitchClickMacro(runtime)
        original = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
        with (
            patch.object(macro, "_validated_context", return_value=original),
            patch("app.macros.switch_click.current_cursor_pos", return_value=(100, 200)),
            patch("app.macros.switch_click.set_cursor_pos"),
            patch("app.macros.switch_click.activate_window") as focus,
            patch("app.macros.switch_click.send_client_click") as sender,
        ):
            macro._run(
                "Left", 1, "Miroir", original,
                exact_source_handle=101,
                mirror_target_handles=(101, 202, 303),
            )
        focus.assert_not_called()
        sender.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()


    def test_native_organizer_scanner_rejects_unrelated_unity_processes(self):
        import app.pages.organizer_page as organizer
        import app.pages.organizer.character_sessions as sessions
        from app.pages.organizer.character_sessions import CharacterSessionsMixin
        rows = [{"nom": "Player 1", "hwnd": 101}, {"nom": "Other Unity", "hwnd": 202}]
        def fake_native_scan():
            return list(rows)
        dummy = SimpleNamespace(scan_unity_sessions_callback=None)
        with (
            patch.object(organizer, "scan_unity_sessions", new=fake_native_scan),
            patch.object(sessions, "scan_unity_sessions", new=fake_native_scan),
            patch("app.macros.mirror_plan.is_dofus_unity_process",
                  side_effect=lambda hwnd: hwnd == 101),
        ):
            result = CharacterSessionsMixin._scan_unity_sessions(dummy)
        self.assertEqual([item["hwnd"] for item in result], [101])


    def test_native_wheel_hook_preserves_signed_delta_and_ignores_synthetic(self):
        import ctypes
        import logging
        from app.input.mouse_hooks import MouseHook, MSLLHOOKSTRUCT, WM_MOUSEWHEEL, LLMHF_INJECTED
        from app.input.input_state import InputState, SyntheticInputGuard

        logger = logging.getLogger("mirror_wheel_hook")
        wheel = Mock(return_value=True)
        hook = MouseHook(InputState(), SyntheticInputGuard(logger), logger, Mock(), wheel_callback=wheel)
        event = MSLLHOOKSTRUCT()
        event.mouseData = (0xFF88 << 16)  # signed -120
        event.pt.x = 15
        event.pt.y = 25
        user32 = SimpleNamespace(CallNextHookEx=Mock(return_value=37))
        with patch.object(ctypes, "windll", SimpleNamespace(user32=user32), create=True):
            ptr = ctypes.addressof(event)
            self.assertEqual(hook._mouse_proc(0, WM_MOUSEWHEEL, ptr), 1)
            wheel.assert_called_once_with(-120, 15, 25, False)
            event.flags = LLMHF_INJECTED
            self.assertEqual(hook._mouse_proc(0, WM_MOUSEWHEEL, ptr), 37)
            wheel.assert_called_once()

    def test_mirror_keyboard_refused_down_never_sends_orphaned_up(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        timings = runtime.settings.timings
        timings.switch_background_pre_click_ms = 0
        timings.activate_attempts = 1
        timings.activate_retry_ms = 0
        timings.switch_click_down_ms = 10
        timings.switch_client_settle_ms = 0
        runtime.macro_lock.should_stop.return_value = False
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.mirror_input.activate_window", return_value=True),
            patch("app.macros.mirror_input.foreground_window", return_value=101),
            patch("app.macros.input_tools.key_down",
                  side_effect=OSError("SendInput refused")) as key_down,
            patch("app.macros.input_tools.key_up") as key_up,
        ):
            MirrorInputMacro(runtime)._run("key", 65, 101, (101, 202))
        key_down.assert_called_once_with(65)
        key_up.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Miroir Clavier incomplet : 0/2 fenêtres."
        )
        runtime.input_state.end_mouse_block.assert_not_called()

    def test_mirror_keyboard_failed_key_up_reports_incomplete_delivery(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        timings = runtime.settings.timings
        timings.switch_background_pre_click_ms = 0
        timings.activate_attempts = 1
        timings.activate_retry_ms = 0
        timings.switch_click_down_ms = 10
        timings.switch_client_settle_ms = 0
        runtime.macro_lock.should_stop.return_value = False
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.mirror_input.activate_window", return_value=True),
            patch("app.macros.mirror_input.foreground_window", return_value=101),
            patch("app.macros.input_tools.key_down") as down,
            patch("app.macros.input_tools.key_up",
                  side_effect=OSError("SendInput UP refused")) as up,
        ):
            MirrorInputMacro(runtime)._run("key", 65, 101, (101, 202))
        down.assert_called_once_with(65)
        self.assertEqual(up.call_count, 2)
        up.assert_any_call(65)
        runtime.logger.warning.assert_any_call(
            "Miroir clavier: relâchement refusé, tentative de secours vk=%s", 65,
        )
        runtime._emit_status.assert_called_once_with(
            "Miroir Clavier incomplet : 0/2 fenêtres."
        )
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.logger.exception.assert_any_call(
            "Miroir %s: échec SendInput.", "key",
        )

    def test_mirror_keyboard_keyup_retry_recovers_and_continues(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        timings = runtime.settings.timings
        timings.switch_background_pre_click_ms = 0
        timings.activate_attempts = 1
        timings.activate_retry_ms = 0
        timings.switch_click_down_ms = 10
        timings.switch_client_settle_ms = 0
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.mirror_input.activate_window", return_value=True),
            patch("app.macros.mirror_input.foreground_window",
                  side_effect=[101, 202, 202]),
            patch("app.macros.input_tools.key_down") as down,
            patch("app.macros.input_tools.key_up",
                  side_effect=[OSError("first KEYUP refused"), None, None]) as up,
        ):
            MirrorInputMacro(runtime)._run("key", 65, 101, (101, 202))
        self.assertEqual(down.call_count, 2)
        self.assertEqual(up.call_count, 3)
        runtime.logger.warning.assert_any_call(
            "Miroir clavier: relâchement refusé, tentative de secours vk=%s", 65,
        )
        runtime.switch_character.restore_preferred_client.assert_called_once()
        runtime._emit_status.assert_called_once_with(
            "Miroir Clavier : 2/2 fenêtres."
        )

    def test_mirror_wheel_send_failure_never_restores_favorite(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        timings = runtime.settings.timings
        timings.switch_background_pre_click_ms = 0
        timings.activate_attempts = 1
        timings.activate_retry_ms = 0
        timings.switch_client_settle_ms = 0
        runtime.macro_lock.should_stop.return_value = False
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.mirror_input.current_cursor_pos",
                  return_value=(12, 14)),
            patch("app.macros.mirror_input.activate_window",
                  return_value=True),
            patch("app.macros.mirror_input.foreground_window",
                  side_effect=[101, 101]),
            patch("app.macros.mirror_input.client_point_from_ratio",
                  return_value=(8, 9)),
            patch("app.macros.mirror_input.client_to_screen",
                  return_value=(80, 90)),
            patch("app.macros.mirror_input.set_cursor_pos") as move,
            patch("app.macros.mirror_input.send_screen_wheel",
                  return_value=False) as send,
        ):
            MirrorInputMacro(runtime)._run(
                "wheel", (120, False, 0.5, 0.5), 101, (101, 202),
            )
        send.assert_called_once_with(120, horizontal=False)
        move.assert_called_once_with(80, 90)
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_called_once()
        runtime._emit_status.assert_called_once_with(
            "Miroir Molette incomplet : 0/2 fenêtres."
        )

    def test_mirror_wheel_stop_after_send_keeps_user_cursor_untouched(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        timings = runtime.settings.timings
        timings.switch_background_pre_click_ms = 0
        timings.activate_attempts = 1
        timings.activate_retry_ms = 0
        timings.switch_client_settle_ms = 0
        stopped = [False]
        runtime.macro_lock.should_stop.side_effect = lambda: stopped[0]

        def stop_after_wheel(*_args, **_kwargs):
            stopped[0] = True
            return True

        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.mirror_input.current_cursor_pos",
                  return_value=(12, 14)),
            patch("app.macros.mirror_input.activate_window",
                  return_value=True),
            patch("app.macros.mirror_input.foreground_window",
                  side_effect=[101, 101]),
            patch("app.macros.mirror_input.client_point_from_ratio",
                  return_value=(8, 9)),
            patch("app.macros.mirror_input.client_to_screen",
                  return_value=(80, 90)),
            patch("app.macros.mirror_input.set_cursor_pos") as move,
            patch("app.macros.mirror_input.send_screen_wheel",
                  side_effect=stop_after_wheel) as send,
        ):
            MirrorInputMacro(runtime)._run(
                "wheel", (120, False, 0.5, 0.5), 101, (101, 202),
            )
        send.assert_called_once_with(120, horizontal=False)
        move.assert_called_once_with(80, 90)
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_called_once()
        runtime._emit_status.assert_called_once_with(
            "Miroir Molette incomplet : 1/2 fenêtres."
        )

    def test_mirror_wheel_roster_change_never_moves_pointer_back(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        timings = runtime.settings.timings
        timings.switch_background_pre_click_ms = 0
        timings.activate_attempts = 1
        timings.activate_retry_ms = 0
        timings.switch_client_settle_ms = 0
        runtime.macro_lock.should_stop.return_value = False

        def reorder_after_wheel(*_args, **_kwargs):
            runtime.settings.clients = (
                SimpleNamespace(handle=202), SimpleNamespace(handle=101),
            )
            return True

        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.mirror_input.current_cursor_pos",
                  return_value=(12, 14)),
            patch("app.macros.mirror_input.activate_window",
                  return_value=True) as activate,
            patch("app.macros.mirror_input.foreground_window",
                  side_effect=[101, 101]),
            patch("app.macros.mirror_input.client_point_from_ratio",
                  return_value=(8, 9)),
            patch("app.macros.mirror_input.client_to_screen",
                  return_value=(80, 90)),
            patch("app.macros.mirror_input.set_cursor_pos") as move,
            patch("app.macros.mirror_input.send_screen_wheel",
                  side_effect=reorder_after_wheel) as send,
        ):
            MirrorInputMacro(runtime)._run(
                "wheel", (120, False, 0.5, 0.5), 101, (101, 202),
            )
        activate.assert_called_once()
        send.assert_called_once_with(120, horizontal=False)
        move.assert_called_once_with(80, 90)
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Miroir Molette incomplet : 1/2 fenêtres."
        )

    def test_mirror_wheel_cursor_snapshot_failure_reports_incomplete(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        with (
            patch("app.macros.mirror_input.current_cursor_pos",
                  side_effect=OSError("GetCursorPos failed")),
            patch("app.macros.mirror_input.activate_window") as activate,
            patch("app.macros.mirror_input.set_cursor_pos") as move,
        ):
            MirrorInputMacro(runtime)._run(
                "wheel", (120, False, 0.5, 0.5), 101, (101, 202),
            )
        activate.assert_not_called()
        move.assert_not_called()
        runtime.input_state.begin_mouse_block.assert_not_called()
        runtime.input_state.end_mouse_block.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Miroir Molette incomplet : 0/2 fenêtres."
        )

    def test_mirror_keyboard_hold_interrupted_still_releases_successful_down(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        timings = runtime.settings.timings
        timings.switch_background_pre_click_ms = 0
        timings.activate_attempts = 1
        timings.activate_retry_ms = 0
        timings.switch_click_down_ms = 10
        timings.switch_client_settle_ms = 0
        stopped = False

        def interrupt_hold(_ms):
            nonlocal stopped
            stopped = True
            return True

        runtime.macro_lock.should_stop.side_effect = lambda: stopped
        runtime.macro_lock.wait.side_effect = interrupt_hold
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.mirror_input.activate_window", return_value=True),
            patch("app.macros.mirror_input.foreground_window", return_value=101),
            patch("app.macros.input_tools.key_down") as key_down,
            patch("app.macros.input_tools.key_up") as key_up,
        ):
            MirrorInputMacro(runtime)._run("key", 65, 101, (101, 202))
        key_down.assert_called_once_with(65)
        key_up.assert_called_once_with(65)
        runtime._emit_status.assert_called_once_with(
            "Miroir Clavier incomplet : 1/2 fenêtres."
        )
        runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_sequential_mirror_keyboard_balances_down_up_on_each_client(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        runtime.settings.timings.switch_background_pre_click_ms = 0
        runtime.settings.timings.activate_attempts = 1
        runtime.settings.timings.activate_retry_ms = 0
        runtime.settings.timings.switch_click_down_ms = 10
        runtime.settings.timings.switch_client_settle_ms = 0
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        macro = MirrorInputMacro(runtime)
        events = []
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process", return_value=True),
            patch("app.macros.mirror_input.activate_window", return_value=True),
            patch("app.macros.mirror_input.foreground_window", side_effect=[101, 202, 202]),
            patch("app.macros.input_tools.key_down", side_effect=lambda vk: events.append(("down", vk))),
            patch("app.macros.input_tools.key_up", side_effect=lambda vk: events.append(("up", vk))),
        ):
            macro._run("key", 65, 101, (101, 202))
        self.assertEqual(events, [("down", 65), ("up", 65)] * 2)
        runtime.input_state.begin_mouse_block.assert_not_called()
        runtime.input_state.end_mouse_block.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_called_once()

    def test_mirror_keyboard_delivery_two_four_six_eight_and_no_final_gap(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = Mock()
                runtime.settings.macro_mode = "mirror"
                runtime.settings.primary_handle = handles[0]
                runtime.settings.clients = tuple(
                    SimpleNamespace(handle=h) for h in handles
                )
                timings = runtime.settings.timings
                timings.switch_background_pre_click_ms = 0
                timings.activate_attempts = 1
                timings.activate_retry_ms = 0
                timings.switch_click_down_ms = 10
                timings.switch_client_settle_ms = 9
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                events = []
                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          return_value=True) as process_probe,
                    patch("app.macros.mirror_input.activate_window",
                          return_value=True) as activate,
                    patch("app.macros.mirror_input.foreground_window",
                          side_effect=[*handles, handles[-1]]),
                    patch("app.macros.input_tools.key_down",
                          side_effect=lambda vk: events.append(("down", vk))),
                    patch("app.macros.input_tools.key_up",
                          side_effect=lambda vk: events.append(("up", vk))),
                ):
                    MirrorInputMacro(runtime)._run("key", 65, handles[0], handles)
                self.assertEqual(events, [("down", 65), ("up", 65)] * count)
                self.assertEqual(activate.call_count, count)
                # Full roster once, then before AND after each activation,
                # plus one source check for restoration: still O(n), never n².
                self.assertEqual(process_probe.call_count, 3 * count + 1)
                # One hold for each key and one gap BETWEEN clients, never
                # an unnecessary gap after the final recipient.
                self.assertEqual(runtime.macro_lock.wait.call_count, 2 * count - 1)
                runtime._emit_status.assert_called_once_with(
                    f"Miroir Clavier : {count}/{count} fenêtres."
                )
                perf_logs = [
                    call for call in runtime.logger.info.call_args_list
                    if call.args and "focus_activation_ms" in str(call.args[0])
                ]
                self.assertEqual(len(perf_logs), 1)
                self.assertEqual(perf_logs[0].args[-2]["n"], count)
                self.assertEqual(perf_logs[0].args[-1]["n"], count)

    def test_mirror_keyboard_rechecks_roster_and_process_after_activation(self):
        from app.macros.mirror_input import MirrorInputMacro

        # Both races occur inside native SetForegroundWindow retries. Neither
        # may deliver a physical key to an obsolete or replaced DOFUS client.
        for change in ("roster", "process"):
            with self.subTest(change=change):
                runtime = self._runtime(primary=101, handles=(101, 202))
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=10,
                    switch_client_settle_ms=0,
                )
                runtime.macro_lock.should_stop.return_value = False
                trusted = [True]

                def activate(_hwnd, *_args, **_kwargs):
                    if change == "roster":
                        runtime.settings.clients = (
                            SimpleNamespace(handle=101),
                            SimpleNamespace(handle=303),
                        )
                    else:
                        trusted[0] = False
                    return True

                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          side_effect=lambda _hwnd: trusted[0]),
                    patch("app.macros.mirror_input.activate_window",
                          side_effect=activate) as focus,
                    patch("app.macros.mirror_input.foreground_window",
                          return_value=101),
                    patch("app.macros.input_tools.key_down") as key_down,
                    patch("app.macros.input_tools.key_up") as key_up,
                ):
                    MirrorInputMacro(runtime)._run("key", 65, 101, (101, 202))
                focus.assert_called_once()
                key_down.assert_not_called()
                key_up.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_not_called()
                runtime._emit_status.assert_called_once_with(
                    "Miroir Clavier incomplet : 0/2 fenêtres."
                )

    def test_mirror_identical_profile_reload_cancels_focus_before_key_send_2_to_8(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=10,
                    switch_client_settle_ms=0,
                )
                runtime.macro_lock.should_stop.return_value = False

                def reload_during_focus(_hwnd, *_args, **kwargs):
                    # Replacement keeps every visible setting identical.
                    # Its identity nevertheless invalidates the old gesture.
                    runtime.settings = SimpleNamespace(**vars(runtime.settings))
                    self.assertTrue(kwargs["should_stop"]())
                    return True  # Exercise the post-activation guard too.

                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.mirror_input.activate_window",
                          side_effect=reload_during_focus) as activate,
                    patch("app.macros.mirror_input.foreground_window") as foreground,
                    patch("app.macros.input_tools.key_down") as down,
                    patch("app.macros.input_tools.key_up") as up,
                ):
                    MirrorInputMacro(runtime)._run(
                        "key", 65, handles[0], handles,
                    )
                activate.assert_called_once()
                foreground.assert_not_called()
                down.assert_not_called()
                up.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime._emit_status.assert_called_once_with(
                    f"Miroir Clavier incomplet : 0/{count} fenêtres."
                )

    def test_mirror_identical_profile_reload_after_cursor_move_skips_wheel_2_to_8(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_client_settle_ms=0,
                )
                runtime.macro_lock.should_stop.return_value = False

                def move_and_reload(_x, _y):
                    runtime.settings = SimpleNamespace(**vars(runtime.settings))

                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.mirror_input.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.mirror_input.activate_window",
                          return_value=True),
                    patch("app.macros.mirror_input.foreground_window",
                          return_value=handles[0]),
                    patch("app.macros.mirror_input.client_point_from_ratio",
                          return_value=(8, 9)),
                    patch("app.macros.mirror_input.client_to_screen",
                          return_value=(80, 90)),
                    patch("app.macros.mirror_input.set_cursor_pos",
                          side_effect=move_and_reload) as move,
                    patch("app.macros.mirror_input.send_screen_wheel") as send,
                ):
                    MirrorInputMacro(runtime)._run(
                        "wheel", (120, False, 0.5, 0.5), handles[0], handles,
                    )
                move.assert_called_once_with(80, 90)
                send.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime._emit_status.assert_called_once_with(
                    f"Miroir Molette incomplet : 0/{count} fenêtres."
                )

    def test_mirror_identical_profile_reload_after_final_key_never_restores(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=10,
                    switch_client_settle_ms=0,
                )
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                active = [handles[0]]
                released = [0]

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def release(_vk):
                    released[0] += 1
                    if released[0] == count:
                        runtime.settings = SimpleNamespace(**vars(runtime.settings))

                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.mirror_input.activate_window",
                          side_effect=activate),
                    patch("app.macros.mirror_input.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.input_tools.key_down") as down,
                    patch("app.macros.input_tools.key_up",
                          side_effect=release) as up,
                ):
                    MirrorInputMacro(runtime)._run(
                        "key", 65, handles[0], handles,
                    )
                self.assertEqual(down.call_count, count)
                self.assertEqual(up.call_count, count)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_not_called()
                runtime._emit_status.assert_called_once_with(
                    f"Miroir Clavier : {count}/{count} fenêtres "
                    "(profil modifié après envoi)."
                )

    def test_mirror_wheel_after_final_send_reports_profile_change_without_faking_loss(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_client_settle_ms=0,
                )
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                active = [handles[0]]
                sent = [0]

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def wheel(_delta, *, horizontal):
                    self.assertFalse(horizontal)
                    sent[0] += 1
                    if sent[0] == count:
                        runtime.settings = SimpleNamespace(**vars(runtime.settings))
                    return True

                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.mirror_input.activate_window",
                          side_effect=activate),
                    patch("app.macros.mirror_input.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.mirror_input.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.mirror_input.client_point_from_ratio",
                          return_value=(8, 9)),
                    patch("app.macros.mirror_input.client_to_screen",
                          return_value=(80, 90)),
                    patch("app.macros.mirror_input.set_cursor_pos") as move,
                    patch("app.macros.mirror_input.send_screen_wheel",
                          side_effect=wheel) as send,
                ):
                    MirrorInputMacro(runtime)._run(
                        "wheel", (120, False, 0.5, 0.5),
                        handles[0], handles,
                    )
                self.assertEqual(send.call_count, count)
                self.assertEqual(move.call_count, count)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once_with()
                runtime._emit_status.assert_called_once_with(
                    f"Miroir Molette : {count}/{count} fenêtres "
                    "(profil modifié après envoi)."
                )

    def test_mirror_key_last_send_inplace_roster_change_is_reported(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[0], handles=handles)
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=10,
                    switch_client_settle_ms=0,
                )
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                active = [handles[0]]
                released = [0]

                def activate(hwnd, *_args, **_kwargs):
                    active[0] = hwnd
                    return True

                def release(_vk):
                    released[0] += 1
                    if released[0] == count:
                        runtime.settings.clients[-1].handle = 999

                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.mirror_input.activate_window",
                          side_effect=activate),
                    patch("app.macros.mirror_input.foreground_window",
                          side_effect=lambda: active[0]),
                    patch("app.macros.input_tools.key_down") as down,
                    patch("app.macros.input_tools.key_up",
                          side_effect=release) as up,
                ):
                    MirrorInputMacro(runtime)._run(
                        "key", 65, handles[0], handles,
                    )
                self.assertEqual(down.call_count, count)
                self.assertEqual(up.call_count, count)
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime._emit_status.assert_called_once_with(
                    f"Miroir Clavier : {count}/{count} fenêtres "
                    "(profil modifié après envoi)."
                )

    def test_mirror_wheel_rechecks_stop_roster_and_identity_after_cursor_move(self):
        from app.macros.mirror_input import MirrorInputMacro

        for change in ("stop", "roster", "process"):
            with self.subTest(change=change):
                runtime = self._runtime(primary=101, handles=(101, 202))
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_client_settle_ms=0,
                )
                stopped = [False]
                trusted = [True]
                runtime.macro_lock.should_stop.side_effect = lambda: stopped[0]

                def move(_x, _y):
                    if change == "stop":
                        stopped[0] = True
                    elif change == "roster":
                        runtime.settings.primary_handle = 202
                    else:
                        trusted[0] = False

                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          side_effect=lambda _hwnd: trusted[0]),
                    patch("app.macros.mirror_input.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.mirror_input.activate_window",
                          return_value=True),
                    patch("app.macros.mirror_input.foreground_window",
                          return_value=101),
                    patch("app.macros.mirror_input.client_point_from_ratio",
                          return_value=(8, 9)),
                    patch("app.macros.mirror_input.client_to_screen",
                          return_value=(80, 90)),
                    patch("app.macros.mirror_input.set_cursor_pos",
                          side_effect=move) as cursor,
                    patch("app.macros.mirror_input.send_screen_wheel") as wheel,
                ):
                    MirrorInputMacro(runtime)._run(
                        "wheel", (120, False, 0.5, 0.5), 101, (101, 202),
                    )
                cursor.assert_called_once_with(80, 90)
                wheel.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once()
                runtime._emit_status.assert_called_once_with(
                    "Miroir Molette incomplet : 0/2 fenêtres."
                )

    def test_mirror_key_process_probe_steals_focus_before_send(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = self._runtime(primary=101, handles=(101, 202))
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0, activate_attempts=1,
            activate_retry_ms=0, switch_click_down_ms=10,
            switch_client_settle_ms=0,
        )
        runtime.macro_lock.should_stop.return_value = False
        active = [101]
        probes = [0]

        def process_probe(_hwnd):
            probes[0] += 1
            if probes[0] == 4:
                active[0] = 303
            return True

        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  side_effect=process_probe),
            patch("app.macros.mirror_input.activate_window",
                  return_value=True) as activate,
            patch("app.macros.mirror_input.foreground_window",
                  side_effect=lambda: active[0]),
            patch("app.macros.input_tools.key_down") as down,
            patch("app.macros.input_tools.key_up") as up,
        ):
            MirrorInputMacro(runtime)._run("key", 65, 101, (101, 202))
        activate.assert_called_once()
        down.assert_not_called()
        up.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Miroir Clavier incomplet : 0/2 fenêtres."
        )

    def test_mirror_wheel_process_probe_steals_focus_after_cursor_move(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = self._runtime(primary=101, handles=(101, 202))
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0, activate_attempts=1,
            activate_retry_ms=0, switch_client_settle_ms=0,
        )
        runtime.macro_lock.should_stop.return_value = False
        active = [101]
        probes = [0]

        def process_probe(_hwnd):
            probes[0] += 1
            if probes[0] == 5:
                active[0] = 303
            return True

        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  side_effect=process_probe),
            patch("app.macros.mirror_input.current_cursor_pos",
                  return_value=(12, 14)),
            patch("app.macros.mirror_input.activate_window",
                  return_value=True),
            patch("app.macros.mirror_input.foreground_window",
                  side_effect=lambda: active[0]),
            patch("app.macros.mirror_input.client_point_from_ratio",
                  return_value=(8, 9)),
            patch("app.macros.mirror_input.client_to_screen",
                  return_value=(80, 90)),
            patch("app.macros.mirror_input.set_cursor_pos") as cursor,
            patch("app.macros.mirror_input.send_screen_wheel") as wheel,
        ):
            MirrorInputMacro(runtime)._run(
                "wheel", (120, False, 0.5, 0.5), 101, (101, 202),
            )
        cursor.assert_called_once_with(80, 90)
        wheel.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_called_once()
        runtime._emit_status.assert_called_once_with(
            "Miroir Molette incomplet : 0/2 fenêtres."
        )

    def test_mirror_key_and_wheel_release_mouse_block_if_final_focus_read_fails(self):
        from app.macros.mirror_input import MirrorInputMacro

        for kind in ("key", "wheel"):
            with self.subTest(kind=kind):
                runtime = self._runtime(primary=101, handles=(101, 202))
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=10,
                    switch_client_settle_ms=0,
                )
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                focus_sequence = (
                    [101, 202, OSError("focus unknown")]
                    if kind == "key"
                    else [101, 101, 202, 202, OSError("focus unknown")]
                )
                with (
                    patch("app.macros.mirror_input.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.mirror_input.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.mirror_input.activate_window",
                          return_value=True),
                    patch("app.macros.mirror_input.foreground_window",
                          side_effect=focus_sequence),
                    patch("app.macros.mirror_input.client_point_from_ratio",
                          return_value=(8, 9)),
                    patch("app.macros.mirror_input.client_to_screen",
                          return_value=(80, 90)),
                    patch("app.macros.mirror_input.set_cursor_pos") as move,
                    patch("app.macros.mirror_input.send_screen_wheel",
                          return_value=True) as wheel,
                    patch("app.macros.input_tools.key_down") as down,
                    patch("app.macros.input_tools.key_up") as up,
                ):
                    if kind == "key":
                        MirrorInputMacro(runtime)._run(
                            "key", 65, 101, (101, 202),
                        )
                        self.assertEqual(down.call_count, 2)
                        self.assertEqual(up.call_count, 2)
                        label = "Clavier"
                        move.assert_not_called()
                    else:
                        MirrorInputMacro(runtime)._run(
                            "wheel", (120, False, 0.5, 0.5), 101, (101, 202),
                        )
                        self.assertEqual(wheel.call_count, 2)
                        self.assertEqual(move.call_count, 2)
                        label = "Molette"
                runtime.switch_character.restore_preferred_client.assert_not_called()
                if kind == "wheel":
                    runtime.input_state.end_mouse_block.assert_called_once()
                else:
                    runtime.input_state.end_mouse_block.assert_not_called()
                runtime.logger.exception.assert_any_call(
                    "Miroir %s: focus non vérifiable avant restauration.", kind,
                )
                runtime._emit_status.assert_called_once_with(
                    f"Miroir {label} : 2/2 fenêtres."
                )

    def test_mirror_key_and_wheel_preserve_user_focus_after_final_send(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel"):
                with self.subTest(count=count, kind=kind):
                    handles = tuple(range(101, 101 + count))
                    runtime = self._runtime(primary=handles[0], handles=handles)
                    runtime.settings.timings = SimpleNamespace(
                        switch_background_pre_click_ms=0, activate_attempts=1,
                        activate_retry_ms=0, switch_click_down_ms=10,
                        switch_client_settle_ms=0,
                    )
                    runtime.macro_lock.should_stop.return_value = False
                    runtime.macro_lock.wait.return_value = False
                    # A new browser or other app is focused AFTER all
                    # synthetic deliveries but before the restoration.
                    foregrounds = (
                        [*handles, 999] if kind == "key"
                        else [h for h in handles for _ in range(2)] + [999]
                    )
                    with (
                        patch("app.macros.mirror_input.is_dofus_unity_process",
                              return_value=True),
                        patch("app.macros.mirror_input.activate_window",
                              return_value=True),
                        patch("app.macros.mirror_input.foreground_window",
                              side_effect=foregrounds),
                        patch("app.macros.mirror_input.current_cursor_pos",
                              return_value=(12, 14)),
                        patch("app.macros.mirror_input.client_point_from_ratio",
                              return_value=(8, 9)),
                        patch("app.macros.mirror_input.client_to_screen",
                              return_value=(80, 90)),
                        patch("app.macros.mirror_input.set_cursor_pos") as move,
                        patch("app.macros.mirror_input.send_screen_wheel",
                              return_value=True) as wheel,
                        patch("app.macros.input_tools.key_down") as down,
                        patch("app.macros.input_tools.key_up") as up,
                    ):
                        if kind == "key":
                            MirrorInputMacro(runtime)._run(
                                "key", 65, handles[0], handles,
                            )
                        else:
                            MirrorInputMacro(runtime)._run(
                                "wheel", (120, False, 0.5, 0.5),
                                handles[0], handles,
                            )
                    if kind == "key":
                        self.assertEqual(down.call_count, count)
                        self.assertEqual(up.call_count, count)
                        move.assert_not_called()
                        label = "Clavier"
                    else:
                        self.assertEqual(wheel.call_count, count)
                        self.assertEqual(move.call_count, count)
                        move.assert_any_call(80, 90)
                        label = "Molette"
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    if kind == "wheel":
                        runtime.input_state.end_mouse_block.assert_called_once()
                    else:
                        runtime.input_state.end_mouse_block.assert_not_called()
                    runtime.logger.info.assert_any_call(
                        "Miroir %s: restauration ignorée, focus utilisateur changé.",
                        kind,
                    )
                    runtime._emit_status.assert_called_once_with(
                        f"Miroir {label} : {count}/{count} fenêtres."
                    )

    def test_mirror_wheel_does_not_restore_favorite_after_cursor_focus_change(self):
        from app.macros.mirror_input import MirrorInputMacro

        for count in (2, 4, 6, 8):
            for effect in ("focus", "error"):
                with self.subTest(count=count, effect=effect):
                    handles = tuple(range(101, 101 + count))
                    runtime = self._runtime(primary=handles[0], handles=handles)
                    runtime.settings.timings = SimpleNamespace(
                        switch_background_pre_click_ms=0,
                        activate_attempts=1, activate_retry_ms=0,
                        switch_client_settle_ms=0,
                    )
                    runtime.macro_lock.should_stop.return_value = False
                    runtime.macro_lock.wait.return_value = False
                    active = [handles[0]]

                    def activate(hwnd, *_args, **_kwargs):
                        active[0] = hwnd
                        return True

                    def move(x, y):
                        if (x, y) == (12, 14):
                            if effect == "error":
                                raise OSError("pointer restore refused")
                            active[0] = 999

                    with (
                        patch("app.macros.mirror_input.is_dofus_unity_process",
                              return_value=True),
                        patch("app.macros.mirror_input.current_cursor_pos",
                              return_value=(12, 14)),
                        patch("app.macros.mirror_input.activate_window",
                              side_effect=activate),
                        patch("app.macros.mirror_input.foreground_window",
                              side_effect=lambda: active[0]),
                        patch("app.macros.mirror_input.client_point_from_ratio",
                              return_value=(8, 9)),
                        patch("app.macros.mirror_input.client_to_screen",
                              return_value=(80, 90)),
                        patch("app.macros.mirror_input.set_cursor_pos",
                              side_effect=move) as cursor,
                        patch("app.macros.mirror_input.send_screen_wheel",
                              return_value=True) as wheel,
                    ):
                        MirrorInputMacro(runtime)._run(
                            "wheel", (120, False, 0.5, 0.5),
                            handles[0], handles,
                        )
                    self.assertEqual(wheel.call_count, count)
                    self.assertEqual(cursor.call_count, count + 1)
                    cursor.assert_any_call(12, 14)
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    runtime.input_state.end_mouse_block.assert_called_once()
                    if effect == "focus":
                        runtime.logger.info.assert_any_call(
                            "Miroir %s: retour au favori ignoré, focus changé après curseur.",
                            "wheel",
                        )
                    else:
                        runtime.logger.exception.assert_any_call(
                            "Miroir molette: restauration curseur impossible."
                        )
                    runtime._emit_status.assert_called_once_with(
                        f"Miroir Molette : {count}/{count} fenêtres."
                    )

    def test_mirror_mouse_block_stays_active_during_cursor_and_focus_restore(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = self._runtime(primary=101, handles=(101, 202))
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0, activate_attempts=1,
            activate_retry_ms=0, switch_client_settle_ms=0,
        )
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        events = []
        runtime.input_state.begin_mouse_block.side_effect = lambda _label: events.append("block")
        runtime.input_state.end_mouse_block.side_effect = lambda: events.append("unblock")
        runtime.switch_character.restore_preferred_client.side_effect = (
            lambda _label: events.append("restore_focus")
        )
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.mirror_input.current_cursor_pos",
                  return_value=(12, 14)),
            patch("app.macros.mirror_input.activate_window",
                  return_value=True),
            patch("app.macros.mirror_input.foreground_window",
                  side_effect=[101, 101, 202, 202, 202, 202]),
            patch("app.macros.mirror_input.client_point_from_ratio",
                  return_value=(8, 9)),
            patch("app.macros.mirror_input.client_to_screen",
                  return_value=(80, 90)),
            patch("app.macros.mirror_input.set_cursor_pos",
                  side_effect=lambda x, y: events.append(("move", x, y))),
            patch("app.macros.mirror_input.send_screen_wheel",
                  return_value=True) as wheel,
        ):
            MirrorInputMacro(runtime)._run(
                "wheel", (120, False, 0.5, 0.5), 101, (101, 202),
            )
        self.assertEqual(wheel.call_count, 2)
        self.assertEqual(events[0], "block")
        self.assertEqual(
            events[-3:], [("move", 12, 14), "restore_focus", "unblock"],
        )
        runtime._emit_status.assert_called_once_with(
            "Miroir Molette : 2/2 fenêtres."
        )

    def test_mirror_mouse_block_is_released_if_restoration_check_raises(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = self._runtime(primary=101, handles=(101, 202))
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0, activate_attempts=1,
            activate_retry_ms=0, switch_client_settle_ms=0,
        )
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        macro = MirrorInputMacro(runtime)
        initial_check = macro._still_current
        checks = [0]

        def check_current(source, handles):
            checks[0] += 1
            if checks[0] == 8:
                raise RuntimeError("runtime settings inaccessible during restore")
            return initial_check(source, handles)

        macro._still_current = check_current
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.mirror_input.current_cursor_pos",
                  return_value=(12, 14)),
            patch("app.macros.mirror_input.activate_window",
                  return_value=True),
            patch("app.macros.mirror_input.foreground_window",
                  side_effect=[101, 101, 202, 202, 202]),
            patch("app.macros.mirror_input.client_point_from_ratio",
                  return_value=(8, 9)),
            patch("app.macros.mirror_input.client_to_screen",
                  return_value=(80, 90)),
            patch("app.macros.mirror_input.set_cursor_pos"),
            patch("app.macros.mirror_input.send_screen_wheel",
                  return_value=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "during restore"):
                macro._run("wheel", (120, False, 0.5, 0.5), 101, (101, 202))
        self.assertEqual(checks[0], 8)
        runtime.input_state.end_mouse_block.assert_called_once()
        runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_mirror_does_not_steal_foreground_after_failed_activation(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        runtime.macro_lock.should_stop.return_value = False
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.mirror_input.activate_window", return_value=False),
            patch("app.macros.mirror_input.foreground_window") as foreground,
            patch("app.macros.input_tools.key_down") as key_down,
        ):
            MirrorInputMacro(runtime)._run("key", 65, 101, (101, 202))
        foreground.assert_not_called()
        key_down.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Miroir Clavier incomplet : 0/2 fenêtres."
        )

    def test_mirror_activation_exception_cannot_steal_favorite_back(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        runtime.macro_lock.should_stop.return_value = False
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.mirror_input.activate_window",
                  side_effect=RuntimeError("Win32 activation refused")),
            patch("app.macros.mirror_input.foreground_window") as foreground,
            patch("app.macros.input_tools.key_down") as key_down,
        ):
            MirrorInputMacro(runtime)._run("key", 65, 101, (101, 202))
        foreground.assert_not_called()
        key_down.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Miroir Clavier incomplet : 0/2 fenêtres."
        )

    def test_mirror_wheel_refuses_focus_stolen_after_cursor_move(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        timings = runtime.settings.timings
        timings.switch_background_pre_click_ms = 0
        timings.activate_attempts = 1
        timings.activate_retry_ms = 0
        timings.switch_client_settle_ms = 0
        runtime.macro_lock.should_stop.return_value = False
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  return_value=True),
            patch("app.macros.mirror_input.current_cursor_pos",
                  return_value=(12, 14)),
            patch("app.macros.mirror_input.activate_window", return_value=True),
            patch("app.macros.mirror_input.foreground_window",
                  side_effect=[101, 999]),
            patch("app.macros.mirror_input.client_point_from_ratio",
                  return_value=(8, 9)),
            patch("app.macros.mirror_input.client_to_screen",
                  return_value=(80, 90)),
            patch("app.macros.mirror_input.set_cursor_pos") as move,
            patch("app.macros.mirror_input.send_screen_wheel") as send,
        ):
            MirrorInputMacro(runtime)._run(
                "wheel", (120, False, 0.5, 0.5), 101, (101, 202),
            )
        move.assert_called_once_with(80, 90)
        send.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Miroir Molette incomplet : 0/2 fenêtres."
        )

    def test_wheel_executor_cancels_on_foreign_process(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        runtime.macro_lock.should_stop.return_value = False
        macro = MirrorInputMacro(runtime)
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  side_effect=lambda hwnd: hwnd != 202),
            patch("app.macros.mirror_input.current_cursor_pos", return_value=(12, 14)),
            patch("app.macros.mirror_input.activate_window") as activate,
            patch("app.macros.mirror_input.send_screen_wheel") as send,
            patch("app.macros.mirror_input.set_cursor_pos"),
        ):
            macro._run("wheel", (120, False, 0.4, 0.5), 101, (101, 202))
        activate.assert_not_called()
        send.assert_not_called()
        runtime.input_state.end_mouse_block.assert_called_once()


    def test_mirror_stop_during_key_hold_still_releases_virtual_key(self):
        from app.macros.mirror_input import MirrorInputMacro
        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        timing = runtime.settings.timings
        timing.switch_background_pre_click_ms = 0
        timing.activate_attempts = 1
        timing.activate_retry_ms = 0
        timing.switch_click_down_ms = 30
        timing.switch_client_settle_ms = 0
        runtime.macro_lock.should_stop.side_effect = [False, False, False, True]
        runtime.macro_lock.wait.return_value = True
        macro = MirrorInputMacro(runtime)
        events = []
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process", return_value=True),
            patch("app.macros.mirror_input.activate_window", return_value=True),
            patch("app.macros.mirror_input.foreground_window", return_value=101),
            patch("app.macros.input_tools.key_down", side_effect=lambda vk: events.append(("down", vk))),
            patch("app.macros.input_tools.key_up", side_effect=lambda vk: events.append(("up", vk))),
        ):
            macro._run("key", 65, 101, (101, 202))
        self.assertEqual(events, [("down", 65), ("up", 65)])
        runtime.input_state.end_mouse_block.assert_not_called()



    def test_held_radial_key_is_not_broadcast_as_discrete_mirror_tap(self):
        from app.input.hotkeys import parsed_hotkey_keys

        runtime = self._runtime()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings.radial_hotkey = "F6"
        runtime.settings.radial_enabled = True
        self.assertIn(0x75, parsed_hotkey_keys("F6"))
        with patch("app.windows.unity_windows.foreground_window") as focus:
            self.assertFalse(AtlasRuntime._handle_mirror_key(
                runtime, 0x75, True,
            ))
        focus.assert_not_called()
        runtime.mirror_input.run_key.assert_not_called()

    def test_keyboard_and_wheel_callbacks_use_frozen_favorite_roster(self):
        runtime = self._runtime()
        runtime._running = True
        runtime._admin_ok = True
        runtime._mirror_gesture_targets.return_value = (101, (101, 202, 303))
        runtime.mirror_input.run_key.return_value = True
        runtime.mirror_input.run_wheel.return_value = True
        with (
            patch("app.windows.unity_windows.foreground_window", return_value=101),
            patch("app.windows.unity_windows.find_known_client_from_point", return_value=101),
            patch("app.windows.unity_windows.screen_to_client", return_value=(20, 25)),
            patch("app.windows.unity_windows.client_point_ratio", return_value=(0.2, 0.5)),
        ):
            self.assertTrue(AtlasRuntime._handle_mirror_key(runtime, 65, True))
            self.assertFalse(AtlasRuntime._handle_mirror_key(runtime, 65, False))
            self.assertTrue(AtlasRuntime._handle_mirror_wheel(runtime, -120, 80, 95, False))
        runtime.mirror_input.run_key.assert_called_once_with(
            65, 101, (101, 202, 303), expected_profile=runtime.settings,
        )
        runtime.mirror_input.run_wheel.assert_called_once_with(
            -120, False, 0.2, 0.5, 101, (101, 202, 303),
            expected_profile=runtime.settings,
        )

    def test_busy_favorite_key_and_wheel_remain_native_for_2_4_6_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=handles[-1], handles=handles)
                runtime._running = True
                runtime._admin_ok = True
                runtime.macro_lock.active_label = "Miroir"
                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=handles[-1]),
                    patch("app.macros.mirror_plan.is_dofus_unity_process") as probe,
                ):
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_key(runtime, 65, True)
                    )
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_wheel(
                            runtime, 120, 20, 25, False,
                        )
                    )
                probe.assert_not_called()
                runtime.mirror_input.run_key.assert_not_called()
                runtime.mirror_input.run_wheel.assert_not_called()
                runtime._mirror_gesture_targets.assert_not_called()
                runtime._emit_status.assert_called_once_with(
                    "Miroir desynchronise : geste non diffuse sur tous les comptes."
                )

    def test_busy_secondary_key_wheel_do_not_swallow_on_profile_reload(self):
        for count in (2, 4, 6, 8):
            for kind in ("key", "wheel"):
                with self.subTest(clients=count, kind=kind):
                    handles = tuple(range(101, 101 + count))
                    runtime = self._runtime(primary=handles[0], handles=handles)
                    runtime._running = True
                    runtime._admin_ok = True
                    runtime.macro_lock.active_label = "Miroir"
                    old = runtime.settings
                    secondary = handles[-1]

                    def reload_on_process(_hwnd):
                        runtime.settings = SimpleNamespace(
                            macro_mode="macro",
                            primary_handle=old.primary_handle,
                            clients=old.clients,
                        )
                        return True

                    with (
                        patch("app.windows.unity_windows.foreground_window",
                              return_value=secondary),
                        patch("app.macros.mirror_plan.is_dofus_unity_process",
                              side_effect=reload_on_process) as process,
                    ):
                        if kind == "key":
                            self.assertFalse(
                                AtlasRuntime._handle_mirror_key(runtime, 65, True),
                            )
                        else:
                            self.assertFalse(AtlasRuntime._handle_mirror_wheel(
                                runtime, 120, 20, 25, False,
                            ))
                    process.assert_called_once_with(secondary)
                    runtime._report_mirror_busy_input.assert_not_called()
                    runtime._emit_status.assert_not_called()
                    runtime.mirror_input.run_key.assert_not_called()
                    runtime.mirror_input.run_wheel.assert_not_called()

    def test_busy_secondary_input_reports_loss_without_replay(self):
        runtime = self._runtime(primary=101, handles=(101, 202))
        runtime._running = True
        runtime._admin_ok = True
        runtime.macro_lock.active_label = "Miroir"
        with (
            patch("app.windows.unity_windows.foreground_window", return_value=202),
            patch("app.macros.mirror_plan.is_dofus_unity_process", return_value=True),
        ):
            self.assertTrue(AtlasRuntime._handle_mirror_key(runtime, 65, True))
            self.assertTrue(
                AtlasRuntime._handle_mirror_wheel(runtime, -120, 20, 25, False)
            )
        runtime._emit_status.assert_called_once_with(
            "Miroir desynchronise : geste non diffuse sur tous les comptes."
        )
        runtime.mirror_input.run_key.assert_not_called()
        runtime.mirror_input.run_wheel.assert_not_called()

    def test_queued_non_mouse_macro_preserves_native_click_without_probes(self):
        from app.input.input_state import InputState

        for busy in ("Auto groupe", "Auto zaap", "Miroir"):
            with self.subTest(busy=busy):
                runtime = self._runtime(primary=101, handles=(101, 202))
                runtime.input_state = InputState()
                runtime.macro_lock.active_label = busy
                with (
                    patch("app.windows.unity_windows.foreground_window") as focus,
                    patch("app.windows.unity_windows.is_unity_window") as unity,
                    patch("app.macros.mirror_plan.is_dofus_unity_process") as process,
                ):
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_click(
                            runtime, "Left", 20, 25,
                        )
                    )
                focus.assert_not_called()
                unity.assert_not_called()
                process.assert_not_called()
                runtime.switch_click.run_async.assert_not_called()

    def test_busy_keyboard_uses_only_current_tracked_foreground(self):
        for foreground, trusted, consumed in (
            (101, True, False),
            (202, True, True),
            (777, False, False),
            (101, False, False),
        ):
            with self.subTest(foreground=foreground, trusted=trusted):
                runtime = self._runtime()
                runtime._running = True
                runtime._admin_ok = True
                runtime.macro_lock.active_label = "Miroir"
                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=foreground),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=trusted) as probe,
                ):
                    self.assertEqual(
                        AtlasRuntime._handle_mirror_key(runtime, 65, True),
                        consumed,
                    )
                runtime._mirror_gesture_targets.assert_not_called()
                runtime.mirror_input.run_key.assert_not_called()
                self.assertEqual(
                    probe.call_count,
                    int(foreground in (101, 202, 303) and foreground != 101),
                )

    def test_busy_wheel_avoids_full_roster_and_never_touches_foreign_app(self):
        for foreground, trusted, consumed in (
            (101, True, False),
            (303, True, True),
            (888, False, False),
            (303, False, False),
        ):
            with self.subTest(foreground=foreground, trusted=trusted):
                runtime = self._runtime()
                runtime._running = True
                runtime._admin_ok = True
                runtime.macro_lock.active_label = "Miroir"
                with (
                    patch("app.windows.unity_windows.foreground_window",
                          return_value=foreground),
                    patch("app.macros.mirror_plan.is_dofus_unity_process",
                          return_value=trusted) as probe,
                ):
                    self.assertEqual(
                        AtlasRuntime._handle_mirror_wheel(
                            runtime, -120, 20, 25, False,
                        ),
                        consumed,
                    )
                runtime._mirror_gesture_targets.assert_not_called()
                runtime.mirror_input.run_wheel.assert_not_called()
                self.assertEqual(
                    probe.call_count,
                    int(foreground in (101, 202, 303) and foreground != 101),
                )

    def test_busy_gestures_pass_when_mirror_mode_is_not_active(self):
        runtime = self._runtime()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings.macro_mode = "macro"
        runtime.macro_lock.active_label = "Miroir"
        with patch("app.windows.unity_windows.foreground_window") as foreground:
            self.assertFalse(AtlasRuntime._handle_mirror_key(runtime, 65, True))
            self.assertFalse(
                AtlasRuntime._handle_mirror_wheel(runtime, 120, 20, 25, False)
            )
        foreground.assert_not_called()
        runtime._mirror_gesture_targets.assert_not_called()

    def test_keyboard_and_wheel_leave_other_apps_untouched(self):
        runtime = self._runtime()
        runtime._running = True
        runtime._admin_ok = True
        runtime._mirror_gesture_targets.return_value = (101, (101, 202, 303))
        with patch("app.windows.unity_windows.foreground_window", return_value=777):
            self.assertFalse(AtlasRuntime._handle_mirror_key(runtime, 65, True))
            self.assertFalse(AtlasRuntime._handle_mirror_wheel(runtime, 120, 80, 95, False))
        runtime.mirror_input.run_key.assert_not_called()
        runtime.mirror_input.run_wheel.assert_not_called()

    def test_keyboard_hook_consumes_exact_key_pair_and_preserves_modifiers(self):
        import ctypes
        import logging
        from app.input.hotkeys import (
            HotkeyRegistry, KBDLLHOOKSTRUCT, WM_KEYDOWN, WM_KEYUP,
        )
        from app.input.input_state import InputState

        registry = HotkeyRegistry(InputState(), logging.getLogger("mirror_keyboard_test"), Mock())
        physical = Mock(return_value=True)
        registry.physical_key_callback = physical
        event = KBDLLHOOKSTRUCT()
        event.vkCode = 65
        next_hook = Mock(return_value=37)
        with patch.object(
            ctypes, "windll",
            SimpleNamespace(user32=SimpleNamespace(CallNextHookEx=next_hook)),
            create=True,
        ):
            ptr = ctypes.addressof(event)
            self.assertEqual(registry._keyboard_proc(0, WM_KEYDOWN, ptr), 1)
            self.assertEqual(registry._keyboard_proc(0, WM_KEYDOWN, ptr), 1)
            physical.assert_called_once_with(65, True)
            self.assertEqual(registry._keyboard_proc(0, WM_KEYUP, ptr), 1)
            self.assertEqual(registry._keyboard_proc(0, WM_KEYUP, ptr), 37)
            event.vkCode = 0xA4  # ALT modifier must pass through.
            self.assertEqual(registry._keyboard_proc(0, WM_KEYDOWN, ptr), 37)
        physical.assert_called_once()


    def test_mirror_abort_does_not_switch_to_new_favorite(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        runtime.macro_lock.should_stop.return_value = False
        mirror = MirrorInputMacro(runtime)
        with (
            patch.object(mirror, "_still_current", side_effect=[True, False, False]),
            patch("app.macros.mirror_input.is_dofus_unity_process") as probe,
            patch("app.macros.mirror_input.activate_window") as activate,
        ):
            mirror._run("key", 65, 101, (101, 202))
        activate.assert_not_called()
        # Preflight validates the roster exactly once; its later in-memory
        # drift check prevents any activation or sending.
        self.assertEqual(probe.call_count, 2)
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_not_called()



    def test_input_sender_rejects_system_keys_and_invalid_wheel_coords(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        mirror = MirrorInputMacro(runtime)
        for vk in (0x5B, 0x5C, 0xA2, 0xA4, 0x10, 0, 255):
            with self.subTest(vk=vk):
                self.assertFalse(mirror.run_key(vk, 101, (101, 202)))
        for x, y in ((float("nan"), 0.5), (float("inf"), 0.5),
                     (-0.1, 0.5), (0.5, 1.1), ("0.4", 0.5)):
            with self.subTest(x=x, y=y):
                self.assertFalse(mirror.run_wheel(120, False, x, y, 101, (101, 202)))
        runtime._spawn_macro.assert_not_called()


    def test_mirror_rejects_unregistered_numeric_vk_codes(self):
        from app.input.hotkeys import MIRROR_DISCRETE_KEYS
        from app.macros.mirror_input import MirrorInputMacro

        self.assertTrue({ord("A"), ord("Z"), ord("0"), ord("9")} <= MIRROR_DISCRETE_KEYS)
        self.assertFalse(MIRROR_DISCRETE_KEYS.intersection(range(0x3A, 0x41)))
        mirror = MirrorInputMacro(Mock())
        for vk_code in range(0x3A, 0x41):
            with self.subTest(vk=vk_code):
                self.assertFalse(mirror.run_key(vk_code, 101, (101, 202)))

    def test_mirror_worker_requires_source_first_and_valid_hwnds(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = Mock()
        runtime.settings.macro_mode = "mirror"
        runtime.settings.primary_handle = 101
        runtime.settings.clients = (
            SimpleNamespace(handle=101), SimpleNamespace(handle=202),
        )
        mirror = MirrorInputMacro(runtime)
        with patch("app.macros.mirror_input.is_dofus_unity_process", return_value=True):
            for handles in ((202, 101), (101, 101), (101, -1),
                            (101, True), (101, 202.0),
                            (101, 2**64), (101, 2**65), (101,), ()):
                with self.subTest(handles=handles):
                    self.assertFalse(mirror._still_current(101, handles))
            self.assertTrue(mirror._still_current(101, (101, 202)))
            runtime.settings.clients = (
                SimpleNamespace(handle=202), SimpleNamespace(handle=101),
            )
            self.assertFalse(mirror._still_current(101, (101, 202)))



    def test_mirror_late_process_replacement_never_restores_favorite(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = self._runtime(primary=101, handles=(101, 202))
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0, activate_attempts=1,
            activate_retry_ms=0, switch_click_down_ms=10, switch_client_settle_ms=0,
        )
        runtime.macro_lock.should_stop.return_value = False
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  side_effect=[True, True, False]),
            patch("app.macros.mirror_input.activate_window") as activate,
            patch("app.macros.input_tools.key_down") as key_down,
        ):
            MirrorInputMacro(runtime)._run("key", 65, 101, (101, 202))
        activate.assert_not_called()
        key_down.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Miroir Clavier incomplet : 0/2 fenêtres."
        )
        runtime.input_state.end_mouse_block.assert_not_called()

    def test_mirror_partial_wheel_process_replacement_does_not_restore_pointer(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = self._runtime(primary=101, handles=(101, 202))
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0, activate_attempts=1,
            activate_retry_ms=0, switch_client_settle_ms=0,
        )
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process",
                  # Roster preflight (2) + before/after first focus (2)
                  # + after first cursor move (1), then reject client 2.
                  side_effect=[True, True, True, True, True, False]),
            patch("app.macros.mirror_input.current_cursor_pos", return_value=(12, 14)),
            patch("app.macros.mirror_input.activate_window", return_value=True),
            patch("app.macros.mirror_input.foreground_window", return_value=101),
            patch("app.macros.mirror_input.client_point_from_ratio", return_value=(8, 9)),
            patch("app.macros.mirror_input.client_to_screen", return_value=(80, 90)),
            patch("app.macros.mirror_input.set_cursor_pos") as move,
            patch("app.macros.mirror_input.send_screen_wheel", return_value=True) as send,
        ):
            MirrorInputMacro(runtime)._run(
                "wheel", (120, False, 0.5, 0.5), 101, (101, 202),
            )
        send.assert_called_once_with(120, horizontal=False)
        move.assert_called_once_with(80, 90)
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Miroir Molette incomplet : 1/2 fenêtres."
        )

    def test_mirror_wheel_missing_target_coordinates_never_restores_pointer(self):
        from app.macros.mirror_input import MirrorInputMacro

        runtime = self._runtime(primary=101, handles=(101, 202))
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0, activate_attempts=1,
            activate_retry_ms=0, switch_client_settle_ms=0,
        )
        runtime.macro_lock.should_stop.return_value = False
        with (
            patch("app.macros.mirror_input.is_dofus_unity_process", return_value=True),
            patch("app.macros.mirror_input.current_cursor_pos", return_value=(12, 14)),
            patch("app.macros.mirror_input.activate_window", return_value=True),
            patch("app.macros.mirror_input.foreground_window", return_value=101),
            patch("app.macros.mirror_input.client_point_from_ratio", return_value=None),
            patch("app.macros.mirror_input.set_cursor_pos") as move,
            patch("app.macros.mirror_input.send_screen_wheel") as send,
        ):
            MirrorInputMacro(runtime)._run(
                "wheel", (120, False, 0.5, 0.5), 101, (101, 202),
            )
        move.assert_not_called()
        send.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime._emit_status.assert_called_once_with(
            "Miroir Molette incomplet : 0/2 fenêtres."
        )


    def test_mirror_click_late_target_refusal_never_restores_or_continues(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for cause in ("process", "focus", "coordinates"):
            with self.subTest(cause=cause):
                runtime = Mock()
                runtime.settings.primary_handle = 101
                runtime.settings.macro_mode = "mirror"
                runtime.settings.clients = [
                    SimpleNamespace(handle=101), SimpleNamespace(handle=202),
                ]
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=35,
                    input_double_gap_ms=5, switch_background_post_up_ms=0,
                    switch_client_settle_ms=0,
                )
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=101, display_name="source"),
                    SimpleNamespace(handle=202, display_name="other"),
                ]
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
                macro = SwitchClickMacro(runtime)
                process_results = [True, False] if cause == "process" else True
                focus_results = [True, False] if cause == "focus" else True
                point_results = [(20, 30), None] if cause == "coordinates" else (20, 30)
                foreground = [101, 202] if cause == "coordinates" else [101]
                with (
                    patch.object(macro, "_validated_context", return_value=context),
                    patch.object(macro, "_target_point", side_effect=(
                        point_results if isinstance(point_results, list) else None
                    ), return_value=(
                        point_results if not isinstance(point_results, list) else None
                    )),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.switch_click.set_cursor_pos") as move,
                    patch("app.macros.switch_click.is_unity_window", return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process",
                          side_effect=(
                              process_results if isinstance(process_results, list)
                              else None
                          ), return_value=(
                              process_results if not isinstance(process_results, list)
                              else None
                          )),
                    patch("app.macros.switch_click.activate_window",
                          side_effect=(
                              focus_results if isinstance(focus_results, list)
                              else None
                          ), return_value=(
                              focus_results if not isinstance(focus_results, list)
                              else None
                          )),
                    patch("app.macros.switch_click.foreground_window",
                          side_effect=foreground),
                    patch("app.macros.switch_click.send_client_click",
                          return_value=True) as send,
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=101, mirror_target_handles=(101, 202),
                    )
                send.assert_called_once()
                move.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once()
                expected = (
                    "Miroir interrompu" if cause == "focus"
                    else "Miroir incomplet"
                )
                runtime._emit_status.assert_called_once_with(
                    f"{expected} : 1/2 fenêtres."
                )


    def test_switch_click_admission_preserves_native_mouse_on_reload_2_to_8(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            for label in ("Miroir", "Switch double clic"):
                with self.subTest(clients=count, action=label):
                    runtime = self._runtime(
                        primary=101, handles=tuple(range(101, 101 + count)),
                    )
                    old = runtime.settings
                    queued = []
                    context = SwitchClickContext(
                        101, 20, 30, 0.5, 0.5, "cursor",
                    )

                    def spawn(_action_label, worker):
                        queued.append(worker)
                        # A reload with identical visible DOFUS clients is
                        # still a new Organizer generation.
                        runtime.settings = SimpleNamespace(
                            macro_mode=old.macro_mode,
                            primary_handle=old.primary_handle,
                            clients=old.clients,
                            timings=old.timings,
                        )
                        return True

                    runtime._spawn_macro.side_effect = spawn
                    macro = SwitchClickMacro(runtime)
                    with patch.object(macro, "_capture_trigger_context",
                                      return_value=context):
                        self.assertFalse(macro.run_async(
                            "Left", 20, 30, 1 if label == "Miroir" else 2,
                            label, exact_source_handle=101 if label == "Miroir" else None,
                            mirror_target_handles=(
                                tuple(range(101, 101 + count))
                                if label == "Miroir" else None
                            ),
                        ))
                    self.assertEqual(len(queued), 1)
                    with (
                        patch("app.macros.switch_click.current_cursor_pos") as cursor,
                        patch("app.macros.switch_click.activate_window") as focus,
                        patch("app.macros.switch_click.send_client_click") as send,
                    ):
                        queued[0]()
                    cursor.assert_not_called()
                    focus.assert_not_called()
                    send.assert_not_called()
                    runtime.input_state.begin_mouse_block.assert_not_called()
                    runtime.switch_character.restore_preferred_client.assert_not_called()

    def test_click_inplace_roster_mutation_during_admission_leaves_native_down(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            for action in ("Miroir", "Switch double clic"):
                for alteration in ("reassign", "append", "mode"):
                    with self.subTest(count=count, action=action, change=alteration):
                        handles = tuple(range(101, 101 + count))
                        runtime = self._runtime(primary=101, handles=handles)
                        old = runtime.settings
                        old.macro_mode = "mirror" if action == "Miroir" else "macro"
                        queued = []
                        context = SwitchClickContext(
                            101, 20, 30, 0.5, 0.5, "cursor",
                        )

                        def spawn(_action, worker):
                            queued.append(worker)
                            if alteration == "reassign":
                                old.clients[-1].handle = 999
                            elif alteration == "append":
                                old.clients = (*old.clients, SimpleNamespace(handle=999))
                            else:
                                old.macro_mode = "macro" if action == "Miroir" else "mirror"
                            return True

                        runtime._spawn_macro.side_effect = spawn
                        macro = SwitchClickMacro(runtime)
                        with patch.object(macro, "_capture_trigger_context",
                                          return_value=context):
                            self.assertFalse(macro.run_async(
                                "Left", 20, 30, 1 if action == "Miroir" else 2,
                                action,
                                exact_source_handle=101 if action == "Miroir" else None,
                                mirror_target_handles=handles if action == "Miroir" else None,
                            ))
                        self.assertEqual(len(queued), 1)
                        with (
                            patch.object(macro, "_run") as runner,
                            patch("app.macros.switch_click.activate_window") as focus,
                            patch("app.macros.switch_click.send_client_click") as send,
                        ):
                            queued[0]()
                        runner.assert_not_called()
                        focus.assert_not_called()
                        send.assert_not_called()
                        runtime.input_state.begin_mouse_block.assert_not_called()

    def test_click_inplace_roster_mutation_before_worker_keeps_focus_native(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                runtime = self._runtime(primary=101, handles=handles)
                runtime._spawn_macro.return_value = True
                context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
                macro = SwitchClickMacro(runtime)
                with patch.object(macro, "_capture_trigger_context",
                                  return_value=context):
                    self.assertTrue(macro.run_async(
                        "Left", 20, 30, 2, "Switch double clic",
                    ))
                queued = runtime._spawn_macro.call_args.args[1]
                runtime.settings.clients[-1].handle = 999
                with (
                    patch.object(macro, "_run") as runner,
                    patch("app.macros.switch_click.activate_window") as focus,
                    patch("app.macros.switch_click.send_client_click") as send,
                ):
                    queued()
                runner.assert_not_called()
                focus.assert_not_called()
                send.assert_not_called()

    def test_native_click_capture_does_not_publish_stale_point_during_probe(self):
        from app.macros.switch_click import SwitchClickMacro

        for count in (2, 4, 6, 8):
            for altered in ("hit_test", "point", "mode", "favorite"):
                with self.subTest(clients=count, phase=altered):
                    handles = tuple(range(101, 101 + count))
                    runtime = self._runtime(primary=101, handles=handles)
                    runtime.last_client_point = SimpleNamespace(
                        valid=False, hwnd=0, x=0, y=0,
                        x_ratio=None, y_ratio=None,
                    )
                    macro = SwitchClickMacro(runtime)

                    def mutate():
                        if altered in ("hit_test", "point"):
                            runtime.settings.clients[-1].handle = 999
                        elif altered == "mode":
                            runtime.settings.macro_mode = "macro"
                        else:
                            runtime.settings.primary_handle = handles[-1]

                    def hit(*_args):
                        if altered == "hit_test":
                            mutate()
                        return 101

                    def ratio(*_args):
                        if altered != "hit_test":
                            mutate()
                        return (0.5, 0.5)

                    with (
                        patch("app.macros.switch_click.find_known_client_from_point",
                              side_effect=hit),
                        patch("app.macros.switch_click.is_unity_window",
                              return_value=True),
                        patch("app.macros.switch_click.screen_to_client",
                              return_value=(5, 6)),
                        patch("app.macros.switch_click.clamp_client_point",
                              return_value=(5, 6)),
                        patch("app.macros.switch_click.client_point_ratio",
                              side_effect=ratio),
                    ):
                        self.assertIsNone(
                            macro._capture_trigger_context(
                                20, 30, "Switch clique",
                            )
                        )
                    self.assertFalse(runtime.last_client_point.valid)
                    self.assertEqual(runtime.last_client_point.hwnd, 0)
                    runtime.switch_character.preferred_client.assert_not_called()

    def test_switch_click_capture_to_worker_native_probe_rejects_inplace_edits(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            for action in ("Miroir", "Switch double clic"):
                for edited in ("mode", "favorite", "new_client", "reassigned_hwnd"):
                    with self.subTest(clients=count, action=action, change=edited):
                        handles = tuple(range(101, 101 + count))
                        runtime = self._runtime(primary=101, handles=handles)
                        runtime.settings.macro_mode = (
                            "mirror" if action == "Miroir" else "macro"
                        )
                        runtime._spawn_macro.return_value = True
                        context = SwitchClickContext(
                            101, 20, 30, 0.5, 0.5, "cursor",
                        )
                        macro = SwitchClickMacro(runtime)
                        with patch.object(macro, "_capture_trigger_context",
                                          return_value=context):
                            self.assertTrue(macro.run_async(
                                "Left", 20, 30, 1 if action == "Miroir" else 2,
                                action,
                                exact_source_handle=101 if action == "Miroir" else None,
                                mirror_target_handles=handles if action == "Miroir" else None,
                            ))
                        worker = runtime._spawn_macro.call_args.args[1]

                        def mutate_and_return(*_args):
                            if edited == "mode":
                                runtime.settings.macro_mode = (
                                    "macro" if action == "Miroir" else "mirror"
                                )
                            elif edited == "favorite":
                                runtime.settings.primary_handle = handles[-1]
                            elif edited == "new_client":
                                runtime.settings.clients = (
                                    *runtime.settings.clients,
                                    SimpleNamespace(handle=999),
                                )
                            else:
                                runtime.settings.clients[-1].handle = 999
                            return context

                        with (
                            patch.object(macro, "_validated_context",
                                         side_effect=mutate_and_return),
                            patch("app.macros.switch_click.current_cursor_pos",
                                  return_value=(12, 14)),
                            patch("app.macros.switch_click.activate_window") as focus,
                            patch("app.macros.switch_click.send_client_click") as send,
                        ):
                            worker()
                        focus.assert_not_called()
                        send.assert_not_called()
                        runtime.input_state.begin_mouse_block.assert_not_called()
                        runtime.switch_character.restore_preferred_client.assert_not_called()
                        runtime.logger.info.assert_any_call(
                            "%s annulé: profil ou roster modifié durant preflight.",
                            action,
                        )

    def test_switch_click_admission_refuses_favorite_change_during_spawn(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            for action in ("Miroir", "Switch double clic"):
                with self.subTest(clients=count, action=action):
                    handles = tuple(range(101, 101 + count))
                    runtime = self._runtime(primary=101, handles=handles)
                    runtime.settings.macro_mode = (
                        "mirror" if action == "Miroir" else "macro"
                    )
                    queued = []
                    context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")

                    def spawn(_label, worker):
                        queued.append(worker)
                        runtime.settings.primary_handle = handles[-1]
                        return True

                    runtime._spawn_macro.side_effect = spawn
                    macro = SwitchClickMacro(runtime)
                    with patch.object(macro, "_capture_trigger_context",
                                      return_value=context):
                        self.assertFalse(macro.run_async(
                            "Left", 20, 30, 1 if action == "Miroir" else 2,
                            action,
                            exact_source_handle=101 if action == "Miroir" else None,
                            mirror_target_handles=handles if action == "Miroir" else None,
                        ))
                    self.assertEqual(len(queued), 1)
                    with patch.object(macro, "_run") as run:
                        queued[0]()
                    run.assert_not_called()
                    runtime.input_state.begin_mouse_block.assert_not_called()

    def test_switch_click_healthy_admission_still_accepts_2_to_8(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            for label in ("Miroir", "Switch double clic"):
                with self.subTest(clients=count, action=label):
                    runtime = self._runtime(
                        primary=101, handles=tuple(range(101, 101 + count)),
                    )
                    runtime._spawn_macro.return_value = True
                    context = SwitchClickContext(
                        101, 20, 30, 0.5, 0.5, "cursor",
                    )
                    macro = SwitchClickMacro(runtime)
                    with patch.object(macro, "_capture_trigger_context",
                                      return_value=context):
                        self.assertTrue(macro.run_async(
                            "Left", 20, 30, 1 if label == "Miroir" else 2, label,
                            exact_source_handle=101 if label == "Miroir" else None,
                            mirror_target_handles=(
                                tuple(range(101, 101 + count))
                                if label == "Miroir" else None
                            ),
                        ))
                    runtime._spawn_macro.assert_called_once()

    def test_classic_click_frozen_hwnd_rejects_native_mutation_2_to_8(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            for phase in ("process", "activation", "point", "send", "favorite", "mode"):
                with self.subTest(clients=count, phase=phase):
                    runtime = Mock()
                    runtime.settings.primary_handle = 101
                    runtime.settings.timings = SimpleNamespace(
                        switch_background_pre_click_ms=0, activate_attempts=1,
                        activate_retry_ms=0, switch_click_down_ms=35,
                        input_double_gap_ms=5, switch_background_post_up_ms=0,
                        switch_client_settle_ms=0,
                    )
                    clients = [
                        SimpleNamespace(handle=101 + i,
                                        display_name=f"Player{i + 1}")
                        for i in range(count)
                    ]
                    runtime.switch_character.ordered_clients_from_source.return_value = clients
                    runtime.macro_lock.should_stop.return_value = False
                    runtime.macro_lock.wait.return_value = False
                    context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
                    macro = SwitchClickMacro(runtime)
                    target = clients[1]
                    sent = []

                    def process(_hwnd):
                        if phase == "process":
                            target.handle = 999
                        return True

                    def activate(hwnd, *_args, **kwargs):
                        self.assertEqual(hwnd, 102)
                        if phase == "activation":
                            target.handle = 999
                            self.assertTrue(kwargs["should_stop"]())
                        elif phase == "favorite":
                            runtime.settings.primary_handle = 102
                            self.assertTrue(kwargs["should_stop"]())
                        elif phase == "mode":
                            runtime.settings.macro_mode = "mirror"
                            self.assertTrue(kwargs["should_stop"]())
                        return True

                    def point(hwnd, _context):
                        self.assertEqual(hwnd, 102)
                        if phase == "point":
                            target.handle = 999
                        return (20, 30)

                    def send(hwnd, *_args, **kwargs):
                        self.assertEqual(hwnd, 102)
                        sent.append(hwnd)
                        if phase == "send":
                            target.handle = 999
                            self.assertTrue(kwargs["should_stop"]())
                        return True

                    with (
                        patch.object(macro, "_validated_context", return_value=context),
                        patch.object(macro, "_target_point", side_effect=point),
                        patch("app.macros.switch_click.current_cursor_pos",
                              return_value=(12, 14)),
                        patch("app.macros.switch_click.set_cursor_pos") as move,
                        patch("app.macros.switch_click.is_unity_window",
                              return_value=True),
                        patch("app.macros.switch_click.is_dofus_unity_process",
                              side_effect=process if phase == "process" else None,
                              return_value=True),
                        patch("app.macros.switch_click.activate_window",
                              side_effect=activate) as focus,
                        patch("app.macros.switch_click.foreground_window",
                              return_value=102),
                        patch("app.macros.switch_click.send_client_click",
                              side_effect=send) as click,
                    ):
                        macro._run(
                            "Left", 1, "Switch clique", context,
                            physical_source_delivered=True,
                        )
                    self.assertEqual(focus.call_count, 0 if phase == "process" else 1)
                    self.assertEqual(click.call_count, 1 if phase == "send" else 0)
                    self.assertEqual(sent, [102] if phase == "send" else [])
                    move.assert_not_called()
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    runtime.input_state.end_mouse_block.assert_called_once()

    def test_classic_click_refuses_foreign_unity_target_before_activation(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        runtime = Mock()
        runtime.settings.primary_handle = 101
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0, activate_attempts=1,
            activate_retry_ms=0, switch_click_down_ms=35,
            input_double_gap_ms=5, switch_background_post_up_ms=0,
            switch_client_settle_ms=0,
        )
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101, display_name="source"),
            SimpleNamespace(handle=202, display_name="other"),
        ]
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
        macro = SwitchClickMacro(runtime)
        with (
            patch.object(macro, "_validated_context", return_value=context),
            patch("app.macros.switch_click.current_cursor_pos", return_value=(12, 14)),
            patch("app.macros.switch_click.is_unity_window", return_value=True),
            patch("app.macros.switch_click.is_dofus_unity_process", return_value=False),
            patch("app.macros.switch_click.activate_window") as activate,
            patch("app.macros.switch_click.send_client_click") as send,
        ):
            macro._run(
                "Left", 1, "Switch clique", context,
                physical_source_delivered=True,
            )
        activate.assert_not_called()
        send.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_called_once()

    def test_classic_click_refuses_process_replacement_after_point_calculation(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        runtime = Mock()
        runtime.settings.primary_handle = 101
        runtime.settings.timings = SimpleNamespace(
            switch_background_pre_click_ms=0, activate_attempts=1,
            activate_retry_ms=0, switch_click_down_ms=35,
            input_double_gap_ms=5, switch_background_post_up_ms=0,
            switch_client_settle_ms=0,
        )
        runtime.switch_character.ordered_clients_from_source.return_value = [
            SimpleNamespace(handle=101, display_name="source"),
            SimpleNamespace(handle=202, display_name="other"),
        ]
        runtime.macro_lock.should_stop.return_value = False
        runtime.macro_lock.wait.return_value = False
        context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
        macro = SwitchClickMacro(runtime)
        with (
            patch.object(macro, "_validated_context", return_value=context),
            patch.object(macro, "_target_point", return_value=(20, 30)),
            patch("app.macros.switch_click.current_cursor_pos", return_value=(12, 14)),
            patch("app.macros.switch_click.set_cursor_pos") as move,
            patch("app.macros.switch_click.is_unity_window", return_value=True),
            patch("app.macros.switch_click.is_dofus_unity_process",
                  side_effect=[True, False]),
            patch("app.macros.switch_click.activate_window", return_value=True),
            patch("app.macros.switch_click.foreground_window", return_value=202),
            patch("app.macros.switch_click.send_client_click") as send,
        ):
            macro._run(
                "Left", 1, "Switch clique", context,
                physical_source_delivered=True,
            )
        send.assert_not_called()
        move.assert_not_called()
        runtime.switch_character.restore_preferred_client.assert_not_called()
        runtime.input_state.end_mouse_block.assert_called_once()


    def test_mirror_cleanup_skips_restore_when_native_probe_changes_favorite_mode_or_stop(self):
        from app.macros.mirror_input import MirrorInputMacro

        # The last source-process check can release the GIL and permit
        # Organizer to change the live profile without replacing its object.
        for count in (2, 4, 6, 8):
            for mutation in ("favorite", "mode", "stop"):
                with self.subTest(clients=count, mutation=mutation):
                    handles = tuple(range(101, 101 + count))
                    runtime = self._runtime(primary=handles[0], handles=handles)
                    runtime.settings.timings = SimpleNamespace(
                        switch_background_pre_click_ms=0,
                        activate_attempts=1,
                        activate_retry_ms=0,
                        switch_click_down_ms=10,
                        switch_client_settle_ms=0,
                    )
                    runtime.macro_lock.should_stop.return_value = False
                    runtime.macro_lock.wait.return_value = False
                    probes = []

                    def native_probe(hwnd):
                        probes.append(hwnd)
                        if len(probes) == 3 * count + 1:
                            self.assertEqual(hwnd, handles[0])
                            if mutation == "favorite":
                                runtime.settings.primary_handle = handles[-1]
                            elif mutation == "mode":
                                runtime.settings.macro_mode = "macro"
                            else:
                                runtime.macro_lock.should_stop.return_value = True
                        return True

                    with (
                        patch("app.macros.mirror_input.is_dofus_unity_process",
                              side_effect=native_probe),
                        patch("app.macros.mirror_input.activate_window",
                              return_value=True),
                        patch("app.macros.mirror_input.foreground_window",
                              side_effect=[*handles, handles[-1]]),
                        patch("app.macros.input_tools.key_down") as down,
                        patch("app.macros.input_tools.key_up") as up,
                    ):
                        MirrorInputMacro(runtime)._run(
                            "key", 65, handles[0], handles,
                        )
                    self.assertEqual(len(probes), 3 * count + 1)
                    self.assertEqual(down.call_count, count)
                    self.assertEqual(up.call_count, count)
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    runtime._emit_status.assert_called_once()
                    status = runtime._emit_status.call_args.args[0]
                    if mutation == "stop":
                        self.assertIn("incomplet", status)
                    else:
                        self.assertIn("profil modifié après envoi", status)


    def test_mirror_click_stop_during_cleanup_focus_probe_never_moves_cursor(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                handles = tuple(range(101, 101 + count))
                runtime = Mock()
                runtime.settings.primary_handle = handles[0]
                runtime.settings.macro_mode = "mirror"
                runtime.settings.clients = [SimpleNamespace(handle=h) for h in handles]
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0, activate_attempts=1,
                    activate_retry_ms=0, switch_click_down_ms=35,
                    input_double_gap_ms=5, switch_background_post_up_ms=0,
                    switch_client_settle_ms=0,
                )
                runtime.switch_character.ordered_clients_from_source.return_value = [
                    SimpleNamespace(handle=h, display_name=str(h)) for h in handles
                ]
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                context = SwitchClickContext(101, 20, 30, 0.5, 0.5, "cursor")
                probes = []

                def foreground():
                    probes.append(True)
                    if len(probes) == count + 1:
                        runtime.macro_lock.should_stop.return_value = True
                    return handles[min(len(probes) - 1, count - 1)]

                macro = SwitchClickMacro(runtime)
                with (
                    patch.object(macro, "_validated_context", return_value=context),
                    patch.object(macro, "_target_point", return_value=(20, 30)),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(12, 14)),
                    patch("app.macros.switch_click.set_cursor_pos") as cursor,
                    patch("app.macros.switch_click.is_unity_window",
                          return_value=True),
                    patch("app.macros.switch_click.is_dofus_unity_process",
                          return_value=True),
                    patch("app.macros.switch_click.activate_window",
                          return_value=True),
                    patch("app.macros.switch_click.foreground_window",
                          side_effect=foreground),
                    patch("app.macros.switch_click.send_client_click",
                          return_value=True) as send,
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=101,
                        mirror_target_handles=handles,
                    )
                self.assertEqual(send.call_count, count)
                self.assertEqual(len(probes), count + 1)
                cursor.assert_not_called()
                runtime.switch_character.restore_preferred_client.assert_not_called()
                runtime.input_state.end_mouse_block.assert_called_once()


if __name__ == "__main__":
    unittest.main()
