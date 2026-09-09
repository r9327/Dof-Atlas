from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.existing_cache_importer import ExistingCacheImporter
from local_dofus_data.utils import save_json_atomic
from tests.helpers import make_config


class ExistingCacheImporterTests(unittest.TestCase):
    def test_import_legacy_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            save_json_atomic(config.legacy_cache_api_dir / "items.json", [{"id": 1, "id_dofus": 10, "name": "Fer", "type": "Minerai", "family": "RESSOURCE"}])
            save_json_atomic(config.legacy_cache_api_dir / "jobs.json", [{"id": 1, "id_dofus": 2, "name": "Mineur"}])
            save_json_atomic(config.legacy_cache_recipes_dir / "20.json", {"found": True, "result_id": 20, "result_name": "Anneau", "ingredients": [{"id": 10, "name": "Fer", "quantity": 2}]})
            bundle = ExistingCacheImporter(config).import_cache()
            self.assertTrue(bundle["items"])
            self.assertTrue(bundle["recipes"])
            self.assertTrue(bundle["jobs"])


if __name__ == "__main__":
    unittest.main()
