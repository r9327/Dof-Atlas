from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.d2o_importer import D2OImporter
from local_dofus_data.utils import save_json_atomic
from tests.helpers import make_config


class D2OImporterTests(unittest.TestCase):
    def test_import_d2o_recipe_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            save_json_atomic(
                config.raw_d2o_dir / "Recipes.json",
                [{"id": 1, "resultId": 200, "resultName": {"fr": "Anneau"}, "ingredientIds": [100], "quantities": [2]}],
            )
            bundle = D2OImporter(config).import_directory()
            self.assertEqual(bundle["recipes"][0][0]["result_ankama_id"], 200)


if __name__ == "__main__":
    unittest.main()
