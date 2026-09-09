from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.json_importer import JsonImporter
from local_dofus_data.utils import save_json_atomic
from tests.helpers import make_config


class JsonImporterTests(unittest.TestCase):
    def test_import_item_json_without_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            path = config.raw_json_dir / "Items.json"
            save_json_atomic(path, [{"id": 1, "name": "Bois de Frene", "type": "Bois", "level": 1}])
            bundle = JsonImporter(config).import_directory()
            self.assertEqual(len(bundle["items"]), 1)
            self.assertEqual(bundle["items"][0]["name_fr"], "Bois de Frene")

    def test_corrupt_json_generates_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            config.raw_json_dir.mkdir(parents=True, exist_ok=True)
            (config.raw_json_dir / "broken.json").write_text("{bad", encoding="utf-8")
            bundle = JsonImporter(config).import_directory()
            self.assertTrue(bundle["warnings"])


if __name__ == "__main__":
    unittest.main()
