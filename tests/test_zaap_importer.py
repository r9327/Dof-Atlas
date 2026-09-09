from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from local_dofus_data.config import ensure_directories
from local_dofus_data.data_store import DataStore
from local_dofus_data.zaap_importer import ZaapImporter

from tests.helpers import make_config


class ZaapImporterTests(unittest.TestCase):
    def test_build_labels_with_map_position_subarea(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            ensure_directories(config)
            api_dir = config.raw_json_dir / "api_static"
            api_dir.mkdir(parents=True, exist_ok=True)
            (api_dir / "dofusdb_subareas.json").write_text(
                json.dumps(
                    {
                        "data": [
                            {"id": 10, "name": {"fr": "Baie de Cania"}, "associatedZaapMapId": 123},
                            {"id": 20, "name": {"fr": "Routes Rocailleuses"}, "associatedZaapMapId": 123},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (api_dir / "dofusdb_map_position_123.json").write_text(
                json.dumps({"id": 123, "posX": -20, "posY": -20, "subAreaId": 20}),
                encoding="utf-8",
            )
            store = DataStore(config=config)
            report = ZaapImporter(config, store).build(online=False, include_supplemental=False)
            labels = [row["label"] for row in report["zaaps"]]
            self.assertIn("Routes Rocailleuses [-20,-20]", labels)
            self.assertEqual(store.query_one("SELECT COUNT(*) AS count FROM maps")["count"], 1)
            store.close()


if __name__ == "__main__":
    unittest.main()
