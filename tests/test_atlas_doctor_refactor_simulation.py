from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib.refactor_simulation import simulate_refactor


class RefactorSimulationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "app").mkdir()
        (self.root / "app/mod.py").write_text("def old(): pass\n")

    def test_stale_graph_blocks_preview(self):
        with patch("tools.agent.reverse_impact_payload", return_value={
            "status": "REVIEW", "graph": {"status": "STALE"}, "reason": "outdated"
        }):
            result = simulate_refactor(self.root, ["app/mod.py"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["proposed_edits"], [])

    def test_simulation_preserves_hard_validation_and_never_edits(self):
        before = (self.root / "app/mod.py").read_text()
        impact = {"status": "PASS", "graph": {"status": "PASS"},
                  "impacted_files": ["app/mod.py", "app/use.py"],
                  "confirmed_relationships": [{"consumer": "app/use.py", "dependency": "app/mod.py"}]}
        plan = {"status": "READY", "integrity_mode": "FULL",
                "execution_tests": [], "recommended_tests": ["tests.test_use"],
                "required_groups": ["guide"]}
        with patch("tools.agent.reverse_impact_payload", return_value=impact), \
             patch("tools.agent.plan_payload", return_value=plan):
            result = simulate_refactor(self.root, ["app/mod.py"], action="move", replacement="app/new.py")
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["consumer_files"], ["app/use.py"])
        self.assertEqual(result["certification"]["status"], "DEFERRED_NOT_WAIVED")
        self.assertEqual(result["certification"]["minimum_mode"], "FULL")
        self.assertEqual((self.root / "app/mod.py").read_text(), before)
        self.assertFalse((self.root / "app/new.py").exists())
        self.assertFalse(result["tests_executed"])

    def test_move_rejects_ambiguous_or_clobbering_destination(self):
        (self.root / "app/existing.py").write_text("pass\\n")
        (self.root / "app/second.py").write_text("pass\\n")
        with self.assertRaisesRegex(ValueError, "already exists"):
            simulate_refactor(self.root, ["app/mod.py"],
                              action="move", replacement="app/existing.py")
        with self.assertRaisesRegex(ValueError, "cannot overwrite"):
            simulate_refactor(self.root, ["app/mod.py"],
                              action="move", replacement="app/mod.py")
        (self.root / "app/alias.py").symlink_to(self.root / "app/existing.py")
        with self.assertRaisesRegex(ValueError, "symlink"):
            simulate_refactor(self.root, ["app/mod.py"],
                              action="consolidate", replacement="app/alias.py")
        with self.assertRaisesRegex(ValueError, "multiple files"):
            simulate_refactor(self.root, ["app/mod.py", "app/second.py"],
                              action="move", replacement="app/new.py")
        with self.assertRaises(ValueError):
            simulate_refactor(self.root, ["app/mod.py"],
                              action="move", replacement="../outside.py")
        with self.assertRaises(ValueError):
            simulate_refactor(self.root, ["app/mod.py"],
                              action="move", replacement="app/not_python.json")

    def test_source_and_parent_symlinks_are_not_safe_refactor_inputs(self):
        original = self.root / "app/mod.py"
        alias = self.root / "app/source_alias.py"
        folder_alias = self.root / "alias_app"
        try:
            alias.symlink_to(original)
            folder_alias.symlink_to(self.root / "app", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable on this runner")
        for name in ("app/source_alias.py", "alias_app/mod.py"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "symlink"):
                simulate_refactor(self.root, [name])
        with self.assertRaisesRegex(ValueError, "symlink"):
            simulate_refactor(self.root, ["app/mod.py"],
                              action="move", replacement="alias_app/new.py")

    def test_windows_destination_separators_are_normalized(self):
        impact = {"status": "PASS", "graph": {"status": "PASS"},
                  "impacted_files": [], "confirmed_relationships": []}
        plan = {"status": "READY", "integrity_mode": "FAST",
                "execution_tests": [], "required_groups": []}
        with patch("tools.agent.reverse_impact_payload", return_value=impact), \
             patch("tools.agent.plan_payload", return_value=plan):
            report = simulate_refactor(self.root, ["app/mod.py"],
                                       action="move", replacement="app\\new.py")
        self.assertEqual(report["replacement"], "app/new.py")

    def test_paths_and_operations_must_be_bounded(self):
        with self.assertRaises(ValueError):
            simulate_refactor(self.root, ["../bad.py"])
        with self.assertRaises(ValueError):
            simulate_refactor(self.root, ["app/mod.py"], action="move")


if __name__ == "__main__":
    unittest.main()
