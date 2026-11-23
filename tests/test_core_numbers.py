"""Shared strict positive-integer behavior used by Guide and network contracts."""
from __future__ import annotations

import unittest

from app.core.numbers import clamped_percent, coerce_positive_int, format_grouped_int, optional_int, positive_int


class PositiveIntTests(unittest.TestCase):
    def test_accepts_positive_integer_and_decimal_text(self):
        for raw, expected in ((1, 1), (" 02 ", 2), (9.0, 9), (2**40, 2**40)):
            with self.subTest(raw=raw):
                self.assertEqual(positive_int(raw), expected)

    def test_rejects_bool_non_positive_and_invalid(self):
        for raw in (True, False, 0, -1, "-4", None, "", "invalid", float("nan"), float("inf")):
            with self.subTest(raw=repr(raw)):
                self.assertIsNone(positive_int(raw))

    def test_rejects_overflow_without_crashing(self):
        class OverflowInt:
            def __int__(self):
                raise OverflowError("out of range")
        self.assertIsNone(positive_int(OverflowInt()))


class OptionalIntTests(unittest.TestCase):
    def test_accepts_existing_guide_coercion_semantics(self):
        for raw, expected in ((True, 1), (False, 0), ("-8", -8), (4.9, 4), (0, 0)):
            with self.subTest(raw=repr(raw)):
                self.assertEqual(optional_int(raw), expected)

    def test_custom_default_preserves_achievement_and_quest_graph_contract(self):
        self.assertEqual(optional_int("25", 7), 25)
        self.assertEqual(optional_int(True, 7), 1)
        self.assertEqual(optional_int("-6", 7), -6)
        for raw in (None, "bad", {}, float("nan")):
            with self.subTest(raw=repr(raw)):
                self.assertEqual(optional_int(raw, 7), 7)

    def test_invalid_values_return_none(self):
        for raw in (None, "bad", {}, float("nan")):
            with self.subTest(raw=repr(raw)):
                self.assertIsNone(optional_int(raw))


class CoercePositiveIntTests(unittest.TestCase):
    def test_preserves_legacy_network_numeric_conversion(self):
        for raw, expected in ((True, 1), (False, None), ("02", 2), (9.7, 9), (0, None), (-1, None)):
            with self.subTest(raw=repr(raw)):
                self.assertEqual(coerce_positive_int(raw), expected)

    def test_invalid_and_overflow_return_none(self):
        class Overflow:
            def __int__(self):
                raise OverflowError("out of range")

        for raw in (None, "", {}, float("nan"), Overflow()):
            with self.subTest(raw=repr(raw)):
                self.assertIsNone(coerce_positive_int(raw))


class FormatGroupedIntTests(unittest.TestCase):
    def test_grouping_preserves_sign_and_one_digit(self):
        for raw, expected in ((0, "0"), (1, "1"), (12345, "12 345"), (-1234567, "-1 234 567"), (True, "1")):
            with self.subTest(raw=raw):
                self.assertEqual(format_grouped_int(raw), expected)

    def test_invalid_input_keeps_int_conversion_errors(self):
        with self.assertRaises(ValueError):
            format_grouped_int("not a number")


class ClampedPercentTests(unittest.TestCase):
    def test_rounding_zero_total_and_out_of_bounds(self):
        for completed, total, expected in ((0, 0, 0), (2, 3, 67), (1, 3, 33),
                                           (1, 8, 12), (3, 2, 100), (-3, 10, 0),
                                           (50, 100, 50), (1, -10, 0)):
            with self.subTest(completed=completed, total=total):
                self.assertEqual(clamped_percent(completed, total), expected)


if __name__ == "__main__":
    unittest.main()
