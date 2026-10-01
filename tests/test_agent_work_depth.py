from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import agent, agent_planner
from tests import test_agent_planner as fixtures


class AgentWorkDepthTests(unittest.TestCase):
    def depth(self, paths=None, risk="LOW", minimum="FAST", **options):
        return agent_planner.choose_work_depth(paths or ["tools/local.py"], {"scopes": ["quality_ci"]},
                                               {"risk": risk}, minimum, **options)

    def test_local_low_risk_is_soft_without_full_or_extra_performance(self):
        result = self.depth()
        self.assertEqual(result["level"], "SOFT")
        self.assertEqual(result["integrity_mode"], "FAST")
        self.assertEqual(result["escalations"], [])
        self.assertEqual(result["graph_depth"], 1)

    def test_multifile_work_escalates_soft_to_medium(self):
        result = self.depth(paths=["tools/a.py", "tools/b.py"], requested="SOFT")
        self.assertEqual(result["level"], "MEDIUM")
        self.assertEqual(result["integrity_mode"], "CRITICAL")
        self.assertEqual(result["escalations"][0]["from"], "SOFT")

    def test_canonical_risk_floor_cannot_be_lowered(self):
        result = self.depth(risk="HIGH", minimum="CRITICAL", requested="SOFT")
        self.assertEqual(result["level"], "MEDIUM")
        self.assertEqual(result["integrity_mode"], "CRITICAL")

    def test_critical_and_structural_require_hard(self):
        for options in ({"risk": "CRITICAL"}, {"structural": True}):
            with self.subTest(options=options):
                result = self.depth(**options)
                self.assertEqual(result["level"], "HARD")
                self.assertEqual(result["integrity_mode"], "FULL")
                self.assertEqual(result["graph_depth"], 2)

    def test_explicit_higher_overrides_and_required_deep_are_preserved(self):
        self.assertEqual(self.depth(requested="MEDIUM")["level"], "MEDIUM")
        self.assertEqual(self.depth(requested="HARD")["integrity_mode"], "FULL")
        self.assertEqual(self.depth(minimum="DEEP", requested="SOFT")["integrity_mode"], "DEEP")
        with self.assertRaises(ValueError):
            self.depth(requested="UNKNOWN")

    def test_hard_delegates_full_suite_to_the_canonical_authority(self):
        impact = {"scopes": [], "recommended_tests": ["tests.test_existing"],
                  "unowned_paths": [], "ambiguous_paths": []}
        with tempfile.TemporaryDirectory() as directory:
            plan = agent_planner.build_plan(Path(directory), ["docs/note.md"], impact,
                policy=fixtures.AgentPlannerTests._policy(), catalog_report=fixtures.AgentPlannerTests._catalog(),
                level="HARD")
        self.assertEqual(plan["level"], "HARD")
        self.assertEqual(plan["execution_tests"], [])
        self.assertEqual(plan["test_command"], [])
        self.assertTrue(plan["tests_delegated_to_integrity"])
        self.assertEqual(plan["validation_command"][-2:], ["full", "--json"])

    def test_soft_uses_real_catalog_test_consumers_when_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests/test_direct.py").write_text("", encoding="utf-8")
            report = {"tools": [{"path": "tools/local.py", "targeted_tests": ["tests/test_direct.py"]}]}
            selected = agent_planner._execution_tests(root, ["tools/local.py"],
                ["tests.test_broad"], report, "SOFT")
        self.assertEqual(selected, ["tests.test_direct"])

    def test_cli_override_is_forwarded_without_new_validation_authority(self):
        impact = {"scopes": [], "recommended_tests": [], "unowned_paths": [], "ambiguous_paths": []}
        with patch.object(agent, "impact_payload", return_value=impact), \
             patch.object(agent.agent_planner, "build_plan", return_value={}) as planner, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(agent.main(["plan", "tools/agent.py", "--medium", "--json"]), 0)
        self.assertEqual(planner.call_args.kwargs, {"level": "MEDIUM"})

    def test_cli_modes_are_mutually_exclusive_and_documented(self):
        with redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as result:
            agent.main(["plan", "--help"])
        self.assertEqual(result.exception.code, 0)
        for flag in ("--soft", "--medium", "--hard"):
            self.assertIn(flag, output.getvalue())


if __name__ == "__main__":
    unittest.main()
