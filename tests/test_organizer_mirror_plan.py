from __future__ import annotations

import unittest

from app.macros.mirror_plan import MirrorCapability, delivery_mode, mirror_targets


class OrganizerMirrorPlanTests(unittest.TestCase):
    def test_only_registered_selected_windows_are_destinations(self) -> None:
        self.assertEqual(mirror_targets([101, 202, 303], {202, 303, 999}, 101), (202, 303))
        self.assertEqual(mirror_targets([101, 202], {202}, 999), ())

    def test_source_click_is_never_duplicated(self) -> None:
        self.assertEqual(mirror_targets([101, 202, 202, 303], {101, 202, 303}, 101), (202, 303))
        self.assertEqual(mirror_targets([101], {101}, 101), ())

    def test_configured_order_is_stable(self) -> None:
        self.assertEqual(mirror_targets([303, 101, 202], {202, 303}, 101), (303, 202))

    def test_background_delivery_requires_both_real_proofs(self) -> None:
        self.assertEqual(delivery_mode(MirrorCapability()), "sequential")
        self.assertEqual(delivery_mode(MirrorCapability(targeted_win32_tested=True)), "sequential")
        self.assertEqual(delivery_mode(MirrorCapability(dofus_unity_confirmed=True)), "sequential")
        self.assertEqual(delivery_mode(MirrorCapability(True, True)), "targeted")


if __name__ == "__main__":
    unittest.main()
