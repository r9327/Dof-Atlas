from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.import_manager import run_import
from local_dofus_data.utils import save_json_atomic
from tests.helpers import make_config


class ImportManagerTests(unittest.TestCase):
    def test_full_import_exports_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            save_json_atomic(config.raw_json_dir / "Items.json", [{"id": 1, "name": "Fer", "type": "Minerai", "level": 1}])
            report = run_import(full=True, offline=True, config=config)
            self.assertTrue(config.sqlite_path.exists())
            self.assertTrue((config.exports_dir / "items.json").exists())
            self.assertGreaterEqual(report["summary"]["counts"]["items"], 1)


if __name__ == "__main__":
    unittest.main()
