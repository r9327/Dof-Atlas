from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.data_store import DataStore
from local_dofus_data.repositories import RecipeRepository
from tests.helpers import make_config


class RepositoryTests(unittest.TestCase):
    def test_recipe_and_shopping_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            store = DataStore(config=config)
            store.initialize()
            recipe_id = store.upsert_entity("recipes", {"result_ankama_id": 200, "result_name_fr": "Anneau", "source": "test"}, "result_ankama_id")
            store.replace_recipe_ingredients(recipe_id, [{"ingredient_ankama_id": 100, "name_fr": "Fer", "quantity": 3, "source": "test"}])
            repo = RecipeRepository(store, config)
            self.assertEqual(repo.get_by_result_item(200)["result_name_fr"], "Anneau")
            shopping = repo.build_shopping_list({200: 2})
            self.assertEqual(shopping[0]["quantity"], 6)
            store.close()


if __name__ == "__main__":
    unittest.main()
