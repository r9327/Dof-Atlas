"""Shared Doduda-array decoding used by Quest and Guide adapters."""
from __future__ import annotations

import unittest

from app.core.doduda_rows import array_rows


class DodudaRowsTests(unittest.TestCase):
    def test_unwraps_only_list_payloads(self):
        examples = (
            ({"Array": [1, 2]}, [1, 2]),
            ([3], [3]),
            ({}, []),
            ({"Array": "not a list"}, []),
            ({"Array": None}, []),
            (None, []),
            ("text", []),
            (42, []),
        )
        for raw, expected in examples:
            with self.subTest(raw=raw):
                self.assertEqual(array_rows(raw), expected)

    def test_existing_lists_are_not_copied(self):
        original = [{"id": 1}]
        self.assertIs(array_rows(original), original)
        self.assertIs(array_rows({"Array": original}), original)


if __name__ == "__main__":
    unittest.main()
