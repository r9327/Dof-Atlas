from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.data_store import DataStore
from local_dofus_data.image_downloader import ImageDownloader
from tests.helpers import make_config


class ImageDownloaderTests(unittest.TestCase):
    def test_collect_missing_craft_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            store = DataStore(config=config)
            store.initialize()
            store.upsert_entity(
                "items",
                {
                    "ankama_id": 200,
                    "name_fr": "Anneau",
                    "image_path": "data/images/items/200.png",
                    "source": "test",
                    "metadata_json": {"image_url": "https://example.test/200.png"},
                },
            )
            recipe_id = store.upsert_entity("recipes", {"result_ankama_id": 200, "result_name_fr": "Anneau", "source": "test"}, "result_ankama_id")
            store.replace_recipe_ingredients(
                recipe_id,
                [
                    {
                        "ingredient_ankama_id": 100,
                        "name_fr": "Fer",
                        "quantity": 2,
                        "image_path": "data/images/items/100.png",
                        "source": "test",
                        "metadata_json": {"raw": {"iconId": 100}},
                    }
                ],
            )
            tasks = ImageDownloader(config, store).collect_missing("craft")
            self.assertEqual(len(tasks), 2)
            store.close()


if __name__ == "__main__":
    unittest.main()
