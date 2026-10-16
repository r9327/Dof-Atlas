from __future__ import annotations

import unittest
from pathlib import Path

from tools.tool_catalog import catalog


ROOT = Path(__file__).resolve().parents[1]


class CanonicalToolSpecTests(unittest.TestCase):
    def test_guide_integrity_uses_explicit_static_tool_spec(self) -> None:
        report = catalog(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        guide = rows["tools/guide_integrity.py"]

        self.assertEqual(guide["tool_spec_source"], "explicit")
        self.assertEqual(guide["preferred_role"], "guide_validation_orchestrator")
        self.assertEqual(guide["canonicality"], "preferred")
        self.assertEqual(guide["capabilities"], ["validation", "guide"])
        self.assertEqual(guide["modes"], ["fast", "full", "list"])
        self.assertEqual(guide["cost_hint"], "variable")
        self.assertEqual(guide["side_effects"], "artifact_output")
        self.assertIn("tests.test_guide_integrity", guide["declared_tests"])
        self.assertEqual(guide["target_scopes"], ["encyclopedia_guide"])
        self.assertFalse(guide["json_cli_flag"])
        self.assertTrue(guide["safe_for_agent"])
        self.assertTrue(guide["automation_ready"])


if __name__ == "__main__":
    unittest.main()
