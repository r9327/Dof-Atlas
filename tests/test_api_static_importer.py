from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.api_static_importer import ApiStaticImporter
from tests.helpers import make_config


class ApiStaticImporterTests(unittest.TestCase):
    def test_fetch_dofusdb_recipes_writes_raw_and_normalizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            importer = ApiStaticImporter(config)
            original = ApiStaticImporter._fetch_json
            try:
                ApiStaticImporter._fetch_json = staticmethod(
                    lambda _url, timeout=45: {
                        "total": 1,
                        "limit": 500,
                        "skip": 0,
                        "data": [
                            {
                                "id": 1,
                                "resultId": 200,
                                "resultLevel": 10,
                                "jobId": 11,
                                "resultName": {"fr": "Anneau test"},
                                "ingredientIds": [100],
                                "quantities": [3],
                                "ingredients": [
                                    {"id": 100, "name": {"fr": "Fer"}, "type": {"name": {"fr": "Minerai"}}, "iconId": 1000}
                                ],
                                "result": {
                                    "id": 200,
                                    "name": {"fr": "Anneau test"},
                                    "type": {"name": {"fr": "Anneau"}},
                                    "effects": [{"effectId": 118, "from": 1, "to": 2}],
                                    "craftVisibleCriterion": "SC!5",
                                },
                            }
                        ],
                    }
                )
                bundle = importer.fetch_dofusdb_recipes()
            finally:
                ApiStaticImporter._fetch_json = original

            self.assertTrue((config.raw_json_dir / "api_static" / "dofusdb_recipes.json").exists())
            self.assertEqual(bundle["recipes"][0][0]["result_ankama_id"], 200)
            self.assertEqual(bundle["recipes"][0][1][0]["name_fr"], "Fer")
            self.assertTrue(any(item["ankama_id"] == 100 for item in bundle["items"]))
            self.assertTrue(any(effect["ankama_id"] == 118 for effect in bundle["effects"]))
            self.assertTrue(any(condition["expression"] == "SC!5" for condition in bundle["conditions"]))


if __name__ == "__main__":
    unittest.main()
