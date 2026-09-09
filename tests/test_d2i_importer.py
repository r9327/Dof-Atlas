from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_dofus_data.d2i_importer import D2IImporter
from local_dofus_data.utils import save_json_atomic
from tests.helpers import make_config


class D2IImporterTests(unittest.TestCase):
    def test_import_texts(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            save_json_atomic(config.raw_d2i_dir / "texts.json", {"123": {"fr": "Bonjour", "en": "Hello"}})
            bundle = D2IImporter(config).import_directory()
            self.assertEqual(len(bundle["texts"]), 2)


if __name__ == "__main__":
    unittest.main()
