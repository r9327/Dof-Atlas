from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import local_data_cache


class LocalDataCacheLazyImportTests(unittest.TestCase):
    def test_clean_import_does_not_load_compatibility_or_import_manager(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = (
            "import json, sys; "
            "import app.local_data_cache; "
            "print(json.dumps({"
            "'compat': 'local_dofus_data.compatibility_adapter' in sys.modules, "
            "'import_manager': 'local_dofus_data.import_manager' in sys.modules"
            "}))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload, {"compat": False, "import_manager": False})

    def test_legacy_wrapper_api_delegates_with_same_arguments(self) -> None:
        calls: list[tuple[str, tuple, dict]] = []

        class FakeAdapterModule:
            def search_items(self, query, limit=50):
                calls.append(("search_items", (query,), {"limit": limit}))
                return [{"name": "Result"}]

            def get_recipe_for_item(self, item_id, force_refresh=False):
                calls.append(
                    (
                        "get_recipe_for_item",
                        (item_id,),
                        {"force_refresh": force_refresh},
                    )
                )
                return {"found": True}

            def list_craft_items(self):
                calls.append(("list_craft_items", (), {}))
                return [{"name": "Craft"}]

            def get_item_set_for_item(self, item_id):
                calls.append(("get_item_set_for_item", (item_id,), {}))
                return {"id": item_id}

        fake = FakeAdapterModule()
        with patch.object(local_data_cache, "_compatibility_adapter", return_value=fake):
            self.assertEqual(local_data_cache.search_items("cape", limit=8), [{"name": "Result"}])
            self.assertEqual(
                local_data_cache.get_recipe_for_item(123, force_refresh=True),
                {"found": True},
            )
            self.assertEqual(local_data_cache.list_craft_items(), [{"name": "Craft"}])
            self.assertEqual(local_data_cache.get_item_set_for_item(77), {"id": 77})

        self.assertEqual(
            calls,
            [
                ("search_items", ("cape",), {"limit": 8}),
                ("get_recipe_for_item", (123,), {"force_refresh": True}),
                ("list_craft_items", (), {}),
                ("get_item_set_for_item", (77,), {}),
            ],
        )

    def test_recipe_index_keeps_legacy_projection(self) -> None:
        recipes = [
            {
                "result_id": 2,
                "result_name": "Deux",
                "level": 20,
                "job_id": 5,
            },
            {
                "result_id": 1,
                "result_name": "Un",
                "level": 10,
                "job_id": 4,
            },
            {
                "result_id": 2,
                "result_name": "Deux bis",
                "level": 21,
                "job_id": 5,
            },
        ]
        with patch.object(local_data_cache, "list_recipes", return_value=recipes):
            payload = local_data_cache.load_or_fetch_recipe_index()

        self.assertEqual(payload["source"], "local_dofus_data")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["result_ids"], [1, 2])
        self.assertEqual(
            payload["recipes"][0],
            {"result_id": 2, "name": "Deux", "level": 20, "job_id": 5},
        )


if __name__ == "__main__":
    unittest.main()
