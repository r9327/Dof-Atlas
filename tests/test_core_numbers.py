"""Shared strict positive-integer behavior used by Guide and network contracts."""
from __future__ import annotations

import unittest

from app.core.numbers import positive_int


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


if __name__ == "__main__":
    unittest.main()
