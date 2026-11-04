from __future__ import annotations

import unittest

from app.macros.mirror_plan import (
    MirrorCapability, delivery_mode, mirror_delivery_targets, mirror_targets,
    mirror_latency_percentiles_ms,
    is_dofus_unity_executable, is_dofus_unity_process,
    MirrorHeldKeys, mirror_key_transition, mirror_release_all_keys,
)


class OrganizerMirrorPlanTests(unittest.TestCase):
    def test_dofus_process_filename_is_not_any_unity_executable(self) -> None:
        self.assertTrue(is_dofus_unity_executable(r"C:\Ankama\zaap\dofus\DOFUS.EXE"))
        for name in ("Dofus.exe", r"C:\Other\Unity.exe", r"C:\Other\Dofus.exe.bak", ""):
            self.assertFalse(is_dofus_unity_executable(name))

    def test_dofus_process_hwnd_rejects_unknown_images_and_other_games(self) -> None:
        from unittest.mock import patch
        import app.windows_embed as embed
        with (
            patch.object(embed, "window_class", return_value="UnityWndClass"),
            patch.object(embed, "window_process_id", return_value=42),
            patch.object(embed, "process_image_path", return_value=r"D:\Games\Dofus.exe"),
        ):
            self.assertTrue(is_dofus_unity_process(101))
        with (
            patch.object(embed, "window_class", return_value="UnityWndClass"),
            patch.object(embed, "window_process_id", return_value=42),
            patch.object(embed, "process_image_path", return_value=r"D:\Games\OtherUnity.exe"),
        ):
            self.assertFalse(is_dofus_unity_process(101))
        self.assertFalse(is_dofus_unity_process(0))

    def test_invalid_hwnds_cannot_reach_native_process_queries(self) -> None:
        from unittest.mock import patch
        import app.windows_embed as embed

        for hwnd in (None, False, True, 0, -1, 101.0, 2**64, "101"):
            with self.subTest(hwnd=repr(hwnd)):
                with patch.object(embed, "window_class") as native_class:
                    self.assertFalse(is_dofus_unity_process(hwnd))
                native_class.assert_not_called()

    def test_invalid_pids_cannot_be_queried_as_dofus_executables(self) -> None:
        from unittest.mock import patch
        import app.windows_embed as embed

        for pid in (None, False, True, 0, -1, 42.0, "42", 2**32):
            with self.subTest(pid=repr(pid)):
                with (
                    patch.object(embed, "window_class", return_value="UnityWndClass"),
                    patch.object(embed, "window_process_id", return_value=pid),
                    patch.object(embed, "process_image_path") as image,
                ):
                    self.assertFalse(is_dofus_unity_process(101))
                image.assert_not_called()

    def test_maximum_valid_win32_pid_keeps_existing_identity_contract(self) -> None:
        from unittest.mock import patch
        import app.windows_embed as embed

        with (
            patch.object(embed, "window_class", return_value="UnityWndClass"),
            patch.object(embed, "window_process_id", return_value=(2**32 - 1)),
            patch.object(embed, "process_image_path", return_value=r"C:\Games\Dofus.exe"),
        ):
            self.assertTrue(is_dofus_unity_process(2**64 - 1))

    def test_measured_mirror_percentiles_ignore_invalid_samples(self) -> None:
        self.assertEqual(
            mirror_latency_percentiles_ms([8, 12, 20, 17]),
            {"n": 4, "p50": 12, "p95": 20, "p99": 20},
        )
        self.assertEqual(
            mirror_latency_percentiles_ms(["invalid", None, -1, float("nan")]),
            None,
        )
        self.assertEqual(
            mirror_latency_percentiles_ms([7.5]),
            {"n": 1, "p50": 7.5, "p95": 7.5, "p99": 7.5},
        )

    def test_only_registered_selected_windows_are_destinations(self) -> None:
        self.assertEqual(mirror_targets([101, 202, 303], {202, 303, 999}, 101), (202, 303))
        self.assertEqual(mirror_targets([101, 202], {202}, 999), ())


    def test_scalar_roster_and_selection_fail_closed(self) -> None:
        for roster in (None, 101, "101", b"101", True):
            with self.subTest(roster=roster):
                self.assertEqual(mirror_targets(roster, [202], 101), ())
                self.assertEqual(mirror_delivery_targets(
                    roster, [202], 101, source_was_consumed=True,
                ), ())
        for selection in (None, 202, "202", b"202", True):
            with self.subTest(selection=selection):
                self.assertEqual(mirror_targets([101, 202], selection, 101), ())
                self.assertEqual(mirror_delivery_targets(
                    [101, 202], selection, 101, source_was_consumed=True,
                ), ())

    def test_fractional_window_handles_must_not_be_coerced(self) -> None:
        self.assertEqual(mirror_targets([101.9, 202], [202], 101), ())
        self.assertEqual(mirror_targets([101, 202.3], [202], 101), ())
        self.assertEqual(mirror_delivery_targets(
            [101, 202], [202], 101.5, source_was_consumed=True,
        ), ())
        # Numeric strings inside genuine iterable lists remain supported
        # for persisted JSON indexes.
        self.assertEqual(mirror_targets(["101", "202"], ["202"], 101), (202,))

    def test_source_click_is_never_duplicated(self) -> None:
        self.assertEqual(mirror_targets([101, 202, 202, 303], {101, 202, 303}, 101), (202, 303))
        self.assertEqual(mirror_targets([101], {101}, 101), ())

    def test_configured_order_is_stable(self) -> None:
        self.assertEqual(mirror_targets([303, 101, 202], {202, 303}, 101), (303, 202))

    def test_background_delivery_is_disabled_until_verified_adapter_exists(self) -> None:
        self.assertEqual(delivery_mode(MirrorCapability()), "sequential")
        self.assertEqual(delivery_mode(MirrorCapability(targeted_win32_tested=True)), "sequential")
        self.assertEqual(delivery_mode(MirrorCapability(dofus_unity_confirmed=True)), "sequential")
        # Boolean declarations alone are not a Windows/Unity proof.
        self.assertEqual(delivery_mode(MirrorCapability(True, True)), "sequential")

    def test_corrupt_handles_and_duplicate_targets_fail_closed(self) -> None:
        self.assertEqual(
            mirror_targets([101, None, "garbled", 202, 202, False, 303],
                           [202, "303", 999, None], 101),
            (202, 303),
        )
        self.assertEqual(mirror_targets([101, 202], {202}, "invalid"), ())
        self.assertEqual(mirror_targets([101, 202], {202}, True), ())
        self.assertEqual(mirror_targets([101, 202], {202}, 999), ())
        self.assertEqual(mirror_targets([101, 202], {202}, -1), ())

    def test_mirror_source_is_excluded_when_physical_click_passed_through(self) -> None:
        targets = mirror_delivery_targets(
            [101, 202, 303], {101, 202, 303}, 101,
            source_was_consumed=False,
        )
        self.assertEqual(targets, (202, 303))

    def test_mirror_includes_source_once_when_hook_suppressed_original(self) -> None:
        targets = mirror_delivery_targets(
            [101, 101, 202, 303], {202, 303}, 101,
            source_was_consumed=True,
        )
        self.assertEqual(targets, (101, 202, 303))

    def test_mirror_refuses_ambiguous_consumption_and_unregistered_source(self) -> None:
        self.assertEqual(mirror_delivery_targets(
            [101, 202], {202}, 101, source_was_consumed=None,
        ), ())
        self.assertEqual(mirror_delivery_targets(
            [101, 202], {202}, 999, source_was_consumed=True,
        ), ())

    def test_mirror_refuses_unreviewed_more_than_eight_clients(self) -> None:
        self.assertEqual(mirror_targets(range(1, 10), set(range(2, 10)), 1), ())
        self.assertEqual(
            mirror_targets(range(1, 9), set(range(2, 9)), 1),
            tuple(range(2, 9)),
        )


    def test_balanced_key_and_suppressed_autorepeat(self) -> None:
        state = MirrorHeldKeys()
        state, event = mirror_key_transition(state, 65, True)
        self.assertEqual(event, ("down", 65))
        same, event = mirror_key_transition(state, 65, True)
        self.assertEqual(same, state)
        self.assertIsNone(event)
        state, event = mirror_key_transition(state, 65, False)
        self.assertEqual((state.pressed, event), ((), ("up", 65)))
        state, event = mirror_key_transition(state, 65, False)
        self.assertIsNone(event)

    def test_modifier_release_order_and_emergency_stop(self) -> None:
        state = MirrorHeldKeys()
        for vk in (17, 16, 65):
            state, _ = mirror_key_transition(state, vk, True)
        state, events = mirror_release_all_keys(state)
        self.assertEqual(events, (("up", 65), ("up", 16), ("up", 17)))
        self.assertEqual(state, MirrorHeldKeys())

    def test_invalid_key_events_fail_closed(self) -> None:
        state = MirrorHeldKeys()
        for vk, press in (
            (True, True), (0, True), (255, True), (-1, True),
            (65.0, True), (65, 1), ("A", True),
        ):
            same, event = mirror_key_transition(state, vk, press)
            self.assertEqual(same, state)
            self.assertIsNone(event)

    def test_unmatched_release_does_not_discard_other_hold(self) -> None:
        state, _ = mirror_key_transition(MirrorHeldKeys(), 65, True)
        same, event = mirror_key_transition(state, 66, False)
        self.assertEqual(state, same)
        self.assertIsNone(event)



if __name__ == "__main__":
    unittest.main()
