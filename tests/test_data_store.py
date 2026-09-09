from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.data_store import DataStore
from local_dofus_data.repositories import ResourceRepository
from tests.helpers import make_config


class DataStoreTests(unittest.TestCase):
    def test_insert_and_get_resource_by_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            store = DataStore(config=config)
            store.initialize()
            row_id = store.upsert_entity(
                "resources",
                {
                    "ankama_id": 100,
                    "gid": 100,
                    "name_fr": "Fer",
                    "type": "Minerai",
                    "category": "resource",
                    "level": 1,
                    "source": "test",
                    "metadata_json": {},
                },
            )
            repo = ResourceRepository(store, config)
            resource = repo.get_by_id(row_id)
            self.assertEqual(resource["name_fr"], "Fer")
            self.assertEqual(repo.get_by_ankama_id(100)["type"], "Minerai")
            store.close()


if __name__ == "__main__":
    unittest.main()
