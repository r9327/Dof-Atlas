from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_dofus_data import compatibility_adapter

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


    def test_validation_getter_runs_real_importer_without_overwriting_source_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = make_config(root / "source")
            config.local_dir.mkdir(parents=True)
            snapshot = config.local_dir / "zaaps.json"
            before = b'{"source":"existing-test-snapshot","zaaps":[]}\n'
            snapshot.write_bytes(before)
            sandbox = root / "validation"
            with patch.dict(os.environ, {"DOFUS_ATLAS_VALIDATION_DATA_DIR": str(sandbox)}), \
                 patch.object(compatibility_adapter, "DEFAULT_CONFIG", config), \
                 patch.object(compatibility_adapter, "_ADAPTER", None):
                adapter = compatibility_adapter.get_adapter()
                try:
                    self.assertEqual(adapter.config.raw_json_dir, config.raw_json_dir)
                    self.assertEqual(adapter.config.images_dir, config.images_dir)
                    self.assertEqual(snapshot.read_bytes(), before)
                    generated = json.loads((sandbox / "local/zaaps.json").read_text(encoding="utf-8"))
                    self.assertEqual(generated["count"], 6)
                    self.assertEqual(len(generated["zaaps"]), 6)
                    self.assertTrue(adapter.config.sqlite_path.is_file())
                    self.assertIs(compatibility_adapter.get_adapter(), adapter)
                finally:
                    adapter.close()

    def test_normal_getter_keeps_existing_default_constructor_contract(self):
        with patch.dict(os.environ), patch.object(compatibility_adapter, "_ADAPTER", None), \
             patch.object(compatibility_adapter, "LocalCompatibilityAdapter") as constructor:
            os.environ.pop("DOFUS_ATLAS_VALIDATION_DATA_DIR", None)
            self.assertIs(compatibility_adapter.get_adapter(), constructor.return_value)
            constructor.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
