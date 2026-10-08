from __future__ import annotations

import ast
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib.change_intelligence import (
    _imports_deleted_module, build_change_plan, removed_python_modules, stale_removed_imports,
)


class ChangeIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Atlas")
        self.git("config", "user.email", "atlas@example.invalid")
        self.write("app/pages/obsolete.py", "def old(): pass\n")
        self.write("app/pages/consumer.py", "from app.pages.obsolete import old\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "initial")
        self.base = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(self, path, content):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def test_deleted_module_import_is_proven_and_linenumbered(self):
        (self.root / "app/pages/obsolete.py").unlink()
        self.git("add", "-A")
        self.assertEqual(removed_python_modules(self.root, self.base), ["app/pages/obsolete.py"])
        result = stale_removed_imports(self.root, ["app/pages/obsolete.py"])
        self.assertEqual(result["findings"], [{"consumer": "app/pages/consumer.py", "line": 1,
            "removed_module": "app.pages.obsolete", "evidence": "CURRENT_SOURCE_IMPORT", "confidence": "CONFIRMED_STATIC"}])
        self.assertFalse(result["truncated"])

    def test_plain_text_is_not_an_import(self):
        self.write("app/pages/consumer.py", "name = 'obsolete'\n")
        self.assertEqual(stale_removed_imports(self.root, ["app/pages/obsolete.py"])["findings"], [])

    def test_relative_and_dynamic_literals_are_detected(self):
        body = "from . import obsolete\nfrom .obsolete import old\nimportlib.import_module('app.pages.obsolete')\n"
        self.assertEqual(_imports_deleted_module(ast.parse(body), "app/pages/consumer.py", "app.pages.obsolete"), [1, 2, 3])

    def test_non_literal_dynamic_import_is_not_confirmed(self):
        body = "importlib.import_module(prefix + '.obsolete')\ngetattr(obj, 'obsolete')\n"
        self.assertEqual(_imports_deleted_module(ast.parse(body), "app/pages/consumer.py", "app.pages.obsolete"), [])

    def test_change_plan_never_executes_tests_or_rebuilds_graph(self):
        self.write("app/pages/consumer.py", "print('ok')\n")
        plan = {"status": "READY", "architecture_preflight": {},
                "integrity_mode": "FAST", "execution_tests": ["tests.test_example"],
                "test_command": ["py", "-3.13", "-m", "unittest", "tests.test_example"]}
        with patch("tools.agent.plan_payload", return_value=plan), \
             patch("tools.atlas_doctor_lib.architecture.graph_status", return_value={"status": "STALE", "reason": "Rebuild required"}), \
             patch("tools.agent.reverse_impact_payload", side_effect=AssertionError("stale graph must not be used")):
            result = build_change_plan(self.root, base_ref=self.base)
        self.assertEqual(result["status"], "REVIEW")
        self.assertFalse(result["tests_executed"])
        self.assertFalse(result["graph_rebuilt"])
        self.assertEqual(result["targeted_tests"], ["tests.test_example"])

    def test_deleted_consumer_blocks_even_if_planner_is_ready(self):
        (self.root / "app/pages/obsolete.py").unlink()
        plan = {"status": "READY", "architecture_preflight": {},
                "integrity_mode": "FULL", "execution_tests": []}
        with patch("tools.agent.plan_payload", return_value=plan), \
             patch("tools.atlas_doctor_lib.architecture.graph_status", return_value={"status": "STALE"}):
            result = build_change_plan(self.root, base_ref=self.base)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(len(result["structural_findings"]), 1)
        self.assertEqual(result["full_suite"]["status"], "DEFERRED_NOT_WAIVED")


if __name__ == "__main__":
    unittest.main()
