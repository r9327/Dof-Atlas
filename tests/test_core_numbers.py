"""Shared strict positive-integer behavior used by Guide and network contracts."""
from __future__ import annotations

import unittest

from app.core.numbers import clamped_percent, coerce_positive_int, exact_native_integer, format_grouped_int, optional_int, positive_int, valid_int_ids
from app.core.item_identity import item_id


class ItemIdCompatibilityTests(unittest.TestCase):
    def test_priority_and_optional_conversion_remain_unchanged(self):
        self.assertEqual(item_id({"id_dofus": "42", "ankama_id": 99}), 42)
        self.assertEqual(item_id({"id_dofus": 0, "ankama_id": "17"}), 17)
        self.assertEqual(item_id({"id": True}), 1)
        self.assertIsNone(item_id({"id": "invalide"}))
        self.assertIsNone(item_id({}))


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


class ExactNativeIntegerTests(unittest.TestCase):
    def test_exact_native_bounds_and_optional_zero(self):
        for value, expected in ((42, 42), (" 42 ", 42), (0, None), ("0", None),
                                (True, None), (42.0, None), ("４２", None),
                                ("-3", None), (2**64, None), ("9" * 5000, None)):
            with self.subTest(value=repr(value)[:35]):
                self.assertEqual(exact_native_integer(value, 2**64 - 1), expected)
        self.assertEqual(exact_native_integer("0", 100, allow_zero=True), 0)
        self.assertIsNone(exact_native_integer(-1, 100, allow_zero=True))
        self.assertIsNone(exact_native_integer(101, 100, allow_zero=True))


class ValidIntIdTests(unittest.TestCase):
    def test_invalid_ids_are_skipped_and_legacy_coercion_is_preserved(self):
        self.assertEqual(
            valid_int_ids(["42", 42, True, "bad", None, -3, 1.9, ""]),
            frozenset({42, 1, -3}),
        )
        self.assertEqual(valid_int_ids(()), frozenset())

    def test_decode_only_once_per_candidate(self):
        calls = []

        class Counted:
            def __int__(self):
                calls.append(1)
                return 19

        self.assertEqual(valid_int_ids([Counted(), Counted()]), frozenset({19}))
        self.assertEqual(len(calls), 2)


class OptionalIntTests(unittest.TestCase):
    def test_map_manifest_reexports_shared_optional_integer_codec(self):
        from app.services.maps import map_manifest

        self.assertIs(map_manifest.optional_int, optional_int)
        for value, expected in (
            (None, None), ("", None), ("-12", -12), (0, 0),
            (True, 1), ("invalid", None),
        ):
            with self.subTest(value=repr(value)):
                self.assertEqual(map_manifest.optional_int(value), expected)
        row = map_manifest.MapEntry.from_dict(
            {"id": "map", "x": "-12", "y": "", "world": "Amakna"},
        )
        self.assertEqual((row.x, row.y), (-12, None))

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
