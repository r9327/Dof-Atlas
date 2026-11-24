"""Pure contract for shared Guide / Macro DOFUS coordinate validation."""
from __future__ import annotations

import unittest

from app.core.map_coordinates import (
    extract_bracketed_coordinates, extract_bracketed_position, normalize_coordinate_pair,
)


class NormalizeCoordinatePairTests(unittest.TestCase):
    def test_all_guide_coordinate_consumers_import_one_compiled_source_pattern(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        consumers = {
            "app/modules/encyclopedia/views/guides_view.py":
                "BRACKETED_POSITION_RE as TRAVEL_COORD_RE",
            "app/modules/encyclopedia/views/guide_ultime_manual_view.py":
                "BRACKETED_POSITION_RE as _COORD_RE",
            "app/modules/encyclopedia/services/guide_quest_view_model.py":
                "BRACKETED_POSITION_RE as COORD_RE",
        }
        for relative_path, source_alias in consumers.items():
            with self.subTest(path=relative_path):
                source = (root / relative_path).read_text(encoding="utf-8")
                self.assertIn(source_alias, source)
                self.assertNotIn('re.compile(r"\\[\\s*(-?\\d+)', source)

    def test_source_bracketed_coordinate_keeps_original_search_contract(self):
        for raw, expected in (("[ -3, 004 ]", "-3,4"),
                              ("Étape en [2, -10] zone", "2,-10"),
                              ("sans coordonnées", None), (None, None),
                              ("[1;2]", None)):
            with self.subTest(raw=raw):
                self.assertEqual(extract_bracketed_position(raw), expected)

    def test_oversized_bracketed_source_does_not_crash(self):
        self.assertIsNone(extract_bracketed_position("[" + "9" * 5000 + ",1]"))
        self.assertIsNone(extract_bracketed_position("[1," + "9" * 5000 + "]"))

    def test_coordinate_tuple_and_text_share_one_source_parser(self):
        for raw, expected in (
            ("[ -03, 004 ]", (-3, 4)),
            ("[0,0] puis [1,2]", (0, 0)),
            ("[-2147483648,1]", (-2147483648, 1)),
            ("[1;2]", None),
            ("[" + "9" * 5000 + ",1]", None),
        ):
            with self.subTest(raw=raw[:40]):
                self.assertEqual(extract_bracketed_coordinates(raw), expected)
                text = f"{expected[0]},{expected[1]}" if expected is not None else None
                self.assertEqual(extract_bracketed_position(raw), text)

    def test_normalization_and_negative_values(self):
        self.assertEqual(normalize_coordinate_pair("003", "-06"), "3,-6")
        self.assertEqual(normalize_coordinate_pair("0", "2147483647"), "0,2147483647")
        self.assertEqual(normalize_coordinate_pair("-2147483647", "1"), "-2147483647,1")

    def test_overflow_and_untrusted_inputs_fail_closed(self):
        for x, y in (
            ("-2147483648", "0"),
            ("2147483648", "0"),
            ("0", "2147483648"),
            ("9" * 5000, "1"),
            ("", "1"),
            ("2.5", "3"),
        ):
            with self.subTest(x=x[:20], y=y):
                self.assertIsNone(normalize_coordinate_pair(x, y))

    def test_caller_may_preserve_its_source_lower_bound(self):
        self.assertIsNone(
            normalize_coordinate_pair("-9", "1", lower_exclusive=-9),
        )
        self.assertEqual(
            normalize_coordinate_pair("-8", "1", lower_exclusive=-9),
            "-8,1",
        )


if __name__ == "__main__":
    unittest.main()
