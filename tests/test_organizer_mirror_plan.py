from __future__ import annotations

import unittest

from app.macros.mirror_plan import (
    MirrorCapability, delivery_mode, mirror_delivery_targets, mirror_targets,
)


class OrganizerMirrorPlanTests(unittest.TestCase):
    def test_only_registered_selected_windows_are_destinations(self) -> None:
        self.assertEqual(mirror_targets([101, 202, 303], {202, 303, 999}, 101), (202, 303))
        self.assertEqual(mirror_targets([101, 202], {202}, 999), ())

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


if __name__ == "__main__":
    unittest.main()
