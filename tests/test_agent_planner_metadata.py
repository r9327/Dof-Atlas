from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from tools.agent_planner import build_plan
from tools.tool_catalog import _validated_tool_spec, _json_cli_flag
from tests import test_agent_planner as planner_fixtures


class MetadataPlannerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.policy = planner_fixtures.AgentPlannerTests._policy()
        self.report = planner_fixtures.AgentPlannerTests._catalog()
        self.impact = {"scopes": ["custom_feature"], "unowned_paths": [],
                       "ambiguous_paths": [], "recommended_tests": ["tests.test_existing"]}

    def custom(self, **changes):
        row = copy.deepcopy(self.report["tools"][1])
        row.update(path="tools/custom_validator.py",
                   preferred_role="custom_validation_orchestrator",
                   target_scopes=["custom_feature"], cost_hint="cheap",
                   declared_tests=["tests.test_custom_contract"],
                   invocation="py -3.13 -m tools.custom_validator")
        row.update(changes)
        self.report["tools"].append(row)
        return row

    def plan(self, paths=None):
        return build_plan(self.root, paths or ["docs/local-note.md"], self.impact,
                          policy=self.policy, catalog_report=self.report)

    def test_arbitrary_canonical_validator_is_discovered_from_metadata(self):
        self.custom()
        plan = self.plan()
        paths = [row["path"] for row in plan["recommended_tools"]]
        self.assertIn("tools/custom_validator.py", paths)
        self.assertNotIn("tools/guide_integrity.py", paths)
        self.assertIn("tests.test_custom_contract", plan["recommended_tests"])
        row = next(row for row in plan["recommended_tools"] if row["path"] == "tools/custom_validator.py")
        self.assertEqual(row["mode"], "fast")
        self.assertEqual(row["cost_hint"], "cheap")
        self.assertIn("custom_feature", row["reason"])
        self.assertEqual(plan["selection_source"], "tools.tool_catalog.select_tools")

    def test_guide_word_alone_does_not_route_a_specialized_engine(self):
        plan = self.plan(["docs/guide-note.md"])
        self.assertEqual([row["path"] for row in plan["recommended_tools"]],
                         ["tools/atlas_integrity.py"])

    def test_metadata_routes_guide_scope_without_a_guide_named_path(self):
        self.impact["scopes"] = ["encyclopedia_guide"]
        plan = self.plan(["docs/local-note.md"])
        self.assertIn("tools/guide_integrity.py",
                      [row["path"] for row in plan["recommended_tools"]])

    def test_changed_specialized_facade_selects_itself_without_scope_guessing(self):
        self.custom()
        self.impact["scopes"] = []
        row = next(row for row in self.plan(["tools/custom_validator.py"])["recommended_tools"]
                   if row["path"] == "tools/custom_validator.py")
        self.assertIn("itself", row["reason"])

    def test_unsafe_or_not_automated_required_metadata_remains_review(self):
        for field in ("safe_for_agent", "automation_ready"):
            with self.subTest(field=field):
                self.report = planner_fixtures.AgentPlannerTests._catalog()
                self.custom(**{field: False})
                self.assertEqual(self.plan()["status"], "REVIEW_REQUIRED")

    def test_unsupported_fast_mode_is_not_silently_executed_as_full(self):
        self.custom(modes=["full"], cost_hint="expensive")
        plan = self.plan()
        self.assertEqual(plan["status"], "REVIEW_REQUIRED")
        row = next(row for row in plan["recommended_tools"] if row["path"] == "tools/custom_validator.py")
        self.assertIsNone(row["mode"])
        self.assertEqual(row["command"], [])

    def test_noncanonical_domain_and_competing_global_authority_are_excluded(self):
        self.custom(preferred_for_agent=False, tool_spec={"canonical": False})
        self.custom(path="tools/second_authority.py",
                    preferred_role="repository_validation_orchestrator")
        self.assertEqual([row["path"] for row in self.plan()["recommended_tools"]],
                         ["tools/atlas_integrity.py"])

    def test_json_artifact_is_not_a_json_cli_option(self):
        self.assertFalse(_json_cli_flag("import json\nprint(json.dumps({}))"))
        self.assertTrue(_json_cli_flag("import argparse\np=argparse.ArgumentParser()\np.add_argument('--json')"))
        self.custom(structured_output=True, json_cli_flag=False)
        row = next(row for row in self.plan()["recommended_tools"] if row["path"] == "tools/custom_validator.py")
        self.assertNotIn("--json", row["command"])

    def test_optional_target_scopes_are_validated_statically(self):
        spec = {"schema_version": 1, "id": "example", "role": "example_validation_orchestrator",
                "capabilities": ["validation"], "modes": ["fast"], "cost_hint": "cheap",
                "side_effects": "read_only", "structured_output": True, "canonical": True,
                "recommended_tests": [], "target_scopes": ["custom_feature"]}
        parsed, errors = _validated_tool_spec("TOOL_SPEC = " + repr(spec), "tools/example.py")
        self.assertEqual(errors, [])
        self.assertEqual(parsed["target_scopes"], ["custom_feature"])
        spec["target_scopes"] = "custom_feature"
        parsed, errors = _validated_tool_spec("TOOL_SPEC = " + repr(spec), "tools/example.py")
        self.assertIsNone(parsed)
        self.assertTrue(any("target_scopes" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
