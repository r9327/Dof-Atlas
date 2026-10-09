from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.boundary_intelligence import layer_boundary_review


class LayerBoundaryTests(unittest.TestCase):
    def test_actual_core_to_ui_import_is_an_advisory_not_auto_fix(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app/core").mkdir(parents=True)
            (root / "app/pages").mkdir(parents=True)
            (root / "app/pages/home.py").write_text("class View: pass\n")
            src = root / "app/core/catalog.py"
            src.write_text("from app.pages.home import View\n")
            result = layer_boundary_review(root, ["app/core/catalog.py"])
            self.assertEqual(result["status"], "REVIEW")
            self.assertEqual(result["total_findings"], 1)
            self.assertEqual(result["findings"][0]["rule"], "LOWER_LAYER_IMPORTS_UI")
            self.assertEqual(result["findings"][0]["line"], 1)
            self.assertFalse(result["safe_to_refactor"])

    def test_text_strings_missing_targets_and_third_party_are_not_confirmed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app/core").mkdir(parents=True)
            (root / "app/core/core.py").write_text(
                "x = 'import app.pages.missing'\n"
                "from app.pages.missing import foo\n"
                "import os\n")
            report = layer_boundary_review(root, ["app/core/core.py"])
            self.assertEqual(report["total_findings"], 0)
            self.assertEqual(report["status"], "PASS")

    def test_invalid_path_yields_review_not_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            actual = layer_boundary_review(root, ["../outside.py"])
            self.assertEqual(actual["status"], "REVIEW")
            self.assertTrue(actual["errors"])


if __name__ == "__main__":
    unittest.main()
