"""Pure contract for shared Guide / Macro DOFUS coordinate validation."""
from __future__ import annotations

import unittest

from app.core.map_coordinates import normalize_coordinate_pair


class NormalizeCoordinatePairTests(unittest.TestCase):
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
