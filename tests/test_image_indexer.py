from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.data_store import DataStore
from local_dofus_data.image_indexer import ImageIndexer
from tests.helpers import make_config


class ImageIndexerTests(unittest.TestCase):
    def test_index_item_image_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            store = DataStore(config=config)
            store.initialize()
            store.upsert_entity("items", {"ankama_id": 42, "name_fr": "Item", "image_path": "data/images/items/42.png", "source": "test"})
            config.image_items_dir.mkdir(parents=True, exist_ok=True)
            (config.image_items_dir / "42.png").write_bytes(b"png")
            result = ImageIndexer(store, config).index()
            self.assertEqual(result["indexed"], 1)
            self.assertTrue(store.query_one("SELECT path FROM image_assets WHERE path LIKE ?", ("%42.png",)))
            store.close()


if __name__ == "__main__":
    unittest.main()
