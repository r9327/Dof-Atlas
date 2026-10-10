from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.source_impact import source_reverse_impact


class SourceImpactTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="doctor-source-impact-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        sources = {
            "app/__init__.py": "",
            "app/core/__init__.py": "",
            "app/core/catalog.py": "def entry():\n    return 7\n",
            "app/pages/__init__.py": "",
            "app/pages/guide.py": "from ..core import catalog\n\nvalue = catalog.entry()\n",
            "app/pages/dynamic.py": (
                "from importlib import import_module\n"
                "def find():\n"
                "    return import_module('app.core.catalog')\n"
            ),
            "app/pages/read_source.py": (
                "from pathlib import Path\n"
                "def read():\n"
                "    return Path('app/core/catalog.py').read_text()\n"
            ),
        }
        for relative, body in sources.items():
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root,
                       capture_output=True, check=True, timeout=10)
        subprocess.run(["git", "add", "--", "app"], cwd=self.root,
                       capture_output=True, check=True, timeout=10)

    def test_static_relative_import_and_literal_dynamic_lead_are_separate(self):
        result = source_reverse_impact(self.root, ["app/core/catalog.py"])
        self.assertEqual(result["status"], "SOURCE_CONFIRMED")
        consumers = {row["path"] for row in result["consumer_files"]}
        self.assertIn("app/pages/guide.py", consumers)
        self.assertNotIn("app/pages/dynamic.py", consumers)
        self.assertNotIn("app/pages/read_source.py", consumers)
        candidates = {row["importer"] for row in
                      result["literal_dynamic_import_candidates"]}
        self.assertIn("app/pages/dynamic.py", candidates)
        self.assertFalse(result["safe_to_delete"])
        self.assertFalse(result["tests_executed"])
        self.assertFalse(result["graph_rebuilt"])

    def test_invalid_paths_fail_closed_and_cannot_be_deleted(self):
        result = source_reverse_impact(self.root, ["../outside.py"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["safe_to_delete"])
        with self.assertRaises(ValueError):
            source_reverse_impact(self.root, ["app/core/catalog.py"], depth=4)


if __name__ == "__main__":
    unittest.main()
