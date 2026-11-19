"""Shared strict positive-integer behavior used by Guide and network contracts."""
from __future__ import annotations

import unittest

from app.core.numbers import optional_int, positive_int


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

    def test_invalid_values_return_none(self):
        for raw in (None, "bad", {}, float("nan")):
            with self.subTest(raw=repr(raw)):
                self.assertIsNone(optional_int(raw))


if __name__ == "__main__":
    unittest.main()
