from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.config import ensure_directories
from local_dofus_data.data_store import DataStore
from local_dofus_data.image_integrity import build_image_integrity_report

from tests.helpers import make_config


class ImageIntegrityTests(unittest.TestCase):
    def test_reports_missing_image_without_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            ensure_directories(config)
            store = DataStore(config=config)
            store.initialize()
            store.upsert_entity(
                "items",
                {
                    "ankama_id": 42,
                    "name_fr": "Item",
                    "image_path": "data/images/items/missing.png",
                    "source": "test",
                },
            )
            report = build_image_integrity_report(store, config, verify_readable=False)
            self.assertEqual(report["missing_count"], 1)
            self.assertTrue((config.reports_dir / "image_integrity_report.json").exists())
            store.close()


if __name__ == "__main__":
    unittest.main()
