from __future__ import annotations

import unittest

from local_dofus_data.compatibility_adapter import (
    LocalCompatibilityAdapter,
    decorate_craft_items,
)


class _CraftItems:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[bool] = []

    def legacy_list(self, *, craftable_only: bool) -> list[dict[str, object]]:
        self.calls.append(craftable_only)
        return self.rows


class CraftCompatibilityAdapterTests(unittest.TestCase):
    def test_decorator_precomputes_search_and_category(self) -> None:
        rows = [{"name": "Cape Test", "type": "Cape", "family": "", "category": ""}]

        result = decorate_craft_items(rows)

        self.assertIs(result, rows)
        self.assertEqual(rows[0]["_search_name"], "cape_test")
        self.assertEqual(rows[0]["_craft_category"], "equipment")

    def test_list_craft_items_decorates_repository_rows_in_canonical_adapter(self) -> None:
        rows = [{"name": "Prysmaradite Test", "type": "", "family": "", "category": ""}]
        items = _CraftItems(rows)
        adapter = object.__new__(LocalCompatibilityAdapter)
        adapter.items = items

        result = adapter.list_craft_items()

        self.assertIs(result, rows)
        self.assertEqual(items.calls, [True])
        self.assertEqual(rows[0]["_search_name"], "prysmaradite_test")
        self.assertEqual(rows[0]["_craft_category"], "trophy_prysma")


if __name__ == "__main__":
    unittest.main()
