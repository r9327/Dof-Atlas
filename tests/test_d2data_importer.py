from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.d2data_importer import D2DataImporter
from local_dofus_data.utils import save_json_atomic
from tests.helpers import make_config


class D2DataImporterTests(unittest.TestCase):
    def test_import_d2data_item_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            save_json_atomic(config.raw_d2data_dir / "Items.json", [{"Id": 10, "Fields": {"name": "Potion", "level": 1, "type": "potion"}}])
            bundle = D2DataImporter(config).import_directory()
            self.assertEqual(bundle["items"][0]["ankama_id"], 10)


if __name__ == "__main__":
    unittest.main()
