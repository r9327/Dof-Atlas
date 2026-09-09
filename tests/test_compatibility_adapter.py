from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.compatibility_adapter import LocalCompatibilityAdapter
from local_dofus_data.data_store import DataStore
from tests.helpers import make_config


class CompatibilityAdapterTests(unittest.TestCase):
    def test_adapter_starts_offline_and_returns_recipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            store = DataStore(config=config)
            store.initialize()
            store.upsert_entity("items", {"ankama_id": 200, "name_fr": "Anneau", "source": "test"})
            recipe_id = store.upsert_entity("recipes", {"result_ankama_id": 200, "result_name_fr": "Anneau", "source": "test"}, "result_ankama_id")
            store.replace_recipe_ingredients(recipe_id, [{"ingredient_ankama_id": 100, "name_fr": "Fer", "quantity": 2, "source": "test"}])
            adapter = LocalCompatibilityAdapter(config, auto_initialize=False)
            recipe = adapter.get_recipe_for_item(200)
            self.assertTrue(recipe["found"])
            self.assertEqual(recipe["ingredients"][0]["name"], "Fer")
            adapter.close()
            store.close()


if __name__ == "__main__":
    unittest.main()
