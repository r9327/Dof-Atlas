from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.resource_lifecycle import inspect_resource_lifecycle


class DoctorResourceLifecycleSourceTests(unittest.TestCase):
    def test_qt_alias_and_qualified_imports_are_recognized_without_native_proof(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "module.py"
            path.write_text(
                "from PySide6.QtCore import QTimer as Timer\n"
                "from PySide6 import QtCore as QC\n"
                "import PySide6.QtWebEngineCore as WC\n"
                "one = Timer(parent=object())\n"
                "two = QC.QTimer(object())\n"
                "three = WC.QWebEnginePage()\n",
                encoding="utf-8",
            )
            report = inspect_resource_lifecycle(root, ["module.py"])
            self.assertEqual(report["status"], "REVIEW")
            found = report["findings"]
            self.assertEqual(len(found), 3)
            self.assertEqual(found[0]["qt_type"], "QTimer")
            self.assertEqual(found[0]["parent_evidence"], "KEYWORD_PARENT_PRESENT")
            self.assertEqual(found[1]["parent_evidence"],
                             "POSITIONAL_ARGUMENTS_OWNERSHIP_UNRESOLVED")
            self.assertEqual(found[2]["qt_type"], "QWebEnginePage")
            self.assertFalse(report["native_ownership_proven"])
            self.assertFalse(report["memory_leak_proven"])

    def test_unrelated_class_named_like_qt_type_is_not_mislabeled(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "file.py").write_text(
                "class QTimer:\n"
                "    def __init__(self): pass\n"
                "value = QTimer()\n",
                encoding="utf-8",
            )
            report = inspect_resource_lifecycle(root, ["file.py"])
            self.assertEqual(report["findings"], [])
            self.assertEqual(report["status"], "PASS")
            self.assertFalse(report["tests_executed"])


if __name__ == "__main__":
    unittest.main()
