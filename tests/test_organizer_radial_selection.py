from __future__ import annotations

import math
import unittest

from app.pages.organizer.radial_selection import (
    confirmed_radial_target,
    selected_slice,
    sector_layout,
    slice_count,
    visible_characters,
)


class OrganizerRadialSelectionTests(unittest.TestCase):
    def test_slice_count_matches_explicit_inclusions(self) -> None:
        sessions = [{"nom": f"Perso {i}", "hwnd": i} for i in range(1, 9)]
        for count in (2, 3, 4, 6, 8):
            with self.subTest(count=count):
                visible = visible_characters(sessions, set(range(1, count + 1)))
                self.assertEqual(slice_count(visible), count)
                self.assertEqual(
                    [row["hwnd"] for row in visible], list(range(1, count + 1))
                )

    def test_detected_or_invalid_windows_never_create_extra_slices(self) -> None:
        sessions = [
            {"nom": "Alpha", "hwnd": 11},
            {"nom": "Beta", "hwnd": 22},
            {"nom": "", "hwnd": 33},
            {"nom": "Gamma", "hwnd": 44, "_empty_slot": True},
            {"nom": "Alpha copy", "hwnd": 11},
            {"nom": "Disabled", "hwnd": 55, "enabled": False},
        ]
        self.assertEqual(
            [row["hwnd"] for row in visible_characters(
                sessions, {11, 22, 33, 44, 55, 999}
            )],
            [11, 22],
        )
        self.assertEqual(visible_characters(sessions, set()), [])

    def test_invalid_and_stale_handles_do_not_crash_or_create_slices(self) -> None:
        sessions = [
            {"nom": "Alpha", "hwnd": 12},
            {"nom": "Bad handle", "hwnd": "unknown"},
            {"nom": "Stale", "hwnd": 0},
            None,  # corrupted legacy cache entry
            "invalid session",
        ]
        selected = visible_characters(sessions, {12, "unknown", None, 0})
        self.assertEqual([row["hwnd"] for row in selected], [12])

    def test_clockwise_vectors_select_each_equal_sector(self) -> None:
        for count in (2, 3, 4, 6, 8):
            for index in range(count):
                with self.subTest(count=count, index=index):
                    angle = index * math.tau / count
                    dx, dy = 100 * math.sin(angle), -100 * math.cos(angle)
                    self.assertEqual(selected_slice(dx, dy, count), index)

    def test_releasing_after_window_is_closed_or_reused_cancels(self) -> None:
        snapshot = [
            {"hwnd": 12, "nom": "Alpha", "pid": 121, "character_key": "character:1"},
            {"hwnd": 13, "nom": "Beta", "pid": 131, "character_key": "character:2"},
        ]
        self.assertEqual(confirmed_radial_target(snapshot, snapshot[::-1], 0), 12)
        self.assertIsNone(confirmed_radial_target(snapshot, snapshot[1:], 0))
        self.assertIsNone(confirmed_radial_target(snapshot, [
            {"hwnd": 12, "nom": "Other", "pid": 121, "character_key": "character:9"}
        ], 0))
        self.assertIsNone(confirmed_radial_target(snapshot, [
            {"hwnd": 12, "nom": "Alpha", "pid": 999, "character_key": "character:1"}
        ], 0))
        self.assertIsNone(confirmed_radial_target(snapshot, [], None))

    def test_sector_layout_matches_hit_testing_and_covers_full_circle(self) -> None:
        for count in (2, 3, 4, 6, 8):
            with self.subTest(count=count):
                sectors = sector_layout(count, label_radius=100)
                self.assertEqual(len(sectors), count)
                span = math.tau / count
                self.assertAlmostEqual(sum(end - start for start, end, _, _ in sectors), math.tau)
                for index, (start, end, x, y) in enumerate(sectors):
                    self.assertAlmostEqual(end - start, span)
                    self.assertAlmostEqual(math.hypot(x, y), 100)
                    self.assertEqual(selected_slice(x, y, count), index)
        self.assertEqual(sector_layout(0), [])

    def test_center_and_empty_selection_cancel(self) -> None:
        self.assertIsNone(selected_slice(0, 0, 8))
        self.assertIsNone(selected_slice(15, 15, 4))
        self.assertIsNone(selected_slice(100, 0, 0))

    def test_order_is_the_organizer_order(self) -> None:
        visible = visible_characters(
            [{"nom": "Beta", "hwnd": 2}, {"nom": "Alpha", "hwnd": 1}],
            {1, 2},
        )
        self.assertEqual([row["nom"] for row in visible], ["Beta", "Alpha"])
        self.assertEqual(visible[selected_slice(0, -100, 2)]["nom"], "Beta")
        self.assertEqual(visible[selected_slice(0, 100, 2)]["nom"], "Alpha")


if __name__ == "__main__":
    unittest.main()
