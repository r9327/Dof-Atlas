from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from tools import work_spec


class WorkSpecTests(unittest.TestCase):
    def test_requires_repository_derived_scope_or_path(self) -> None:
        with self.assertRaisesRegex(work_spec.WorkSpecError, "scope or path"):
            work_spec.build_spec(Path.cwd(), "Refondre le Guide")

    @patch("tools.work_spec.agent_planner.build_plan")
    @patch("tools.work_spec.agent.impact_payload")
    @patch("tools.work_spec.agent.inspect_scope")
    def test_build_spec_composes_existing_agent_and_planner(
        self,
        inspect_scope,
        impact_payload,
        build_plan,
    ) -> None:
        inspect_scope.return_value = {
            "scope": "encyclopedia_guide",
            "kind": "feature",
            "manifest": ".ai/scopes/encyclopedia_guide.yaml",
            "working_set": ["app/modules/encyclopedia/views/guides_view.py"],
        }
        impact_payload.return_value = {
            "scopes": ["encyclopedia_guide"],
            "working_set": ["app/modules/encyclopedia/views/guides_view.py"],
            "shared_dependencies": ["persistence_identity"],
            "rules": ["AGENTS.md", "DEVELOPMENT_GUARDRAILS.md"],
            "canonical_entries": ["data/routes/guide_ultime_manual/"],
            "context_entries": ["AI_CONTEXT.md"],
        }
        build_plan.return_value = {
            "status": "READY",
            "automation_safe": True,
            "level": "HARD",
            "integrity_mode": "FULL",
            "required_groups": ["GUIDE"],
            "planning_reasons": ["Scope comes from the Agent map."],
            "recommended_tests": ["tests.test_guide_ultime_manual_runtime_service"],
            "test_command": [],
            "validation_command": ["py", "-3.13", "-m", "tools.agent", "validate", "full", "--json"],
            "tests_delegated_to_integrity": True,
            "ownership": {"review_required": False, "unowned_paths": [], "ambiguous_paths": []},
            "unsafe_recommended_tools": [],
            "non_automated_recommended_tools": [],
            "missing_validation_tools": [],
        }

        spec = work_spec.build_spec(
            Path.cwd(),
            "Moderniser le moteur Guide sans casser la progression",
            scopes=["encyclopedia_guide"],
            structural=True,
        )

        self.assertEqual(spec["schema_version"], 1)
        self.assertEqual(spec["status"], "READY")
        self.assertEqual(spec["scope_selection"]["resolved"], ["encyclopedia_guide"])
        self.assertEqual(spec["execution"]["work_level"], "HARD")
        self.assertEqual(spec["execution"]["integrity_mode"], "FULL")
        self.assertFalse(spec["decision_policy"]["ask_user_by_default"])
        self.assertIn("material product/behavior choice", spec["decision_policy"]["ask_user_only_when"])
        build_plan.assert_called_once()
        self.assertTrue(build_plan.call_args.kwargs["structural"])

    @patch("tools.work_spec.agent_planner.build_plan")
    @patch("tools.work_spec.agent.impact_payload")
    def test_repository_ambiguity_requests_repository_review_not_user_question(
        self,
        impact_payload,
        build_plan,
    ) -> None:
        impact_payload.return_value = {
            "scopes": [],
            "working_set": [],
            "shared_dependencies": [],
            "rules": [],
            "canonical_entries": [],
            "context_entries": [],
        }
        build_plan.return_value = {
            "status": "REVIEW_REQUIRED",
            "automation_safe": False,
            "level": "MEDIUM",
            "integrity_mode": "CRITICAL",
            "required_groups": [],
            "planning_reasons": [],
            "recommended_tests": [],
            "test_command": [],
            "validation_command": [],
            "tests_delegated_to_integrity": False,
            "ownership": {
                "review_required": True,
                "unowned_paths": ["new_area/file.py"],
                "ambiguous_paths": [],
            },
            "unsafe_recommended_tools": [],
            "non_automated_recommended_tools": [],
            "missing_validation_tools": [],
        }

        spec = work_spec.build_spec(
            Path.cwd(),
            "Ajouter une nouvelle zone",
            paths=["new_area/file.py"],
        )

        self.assertEqual(spec["status"], "REVIEW_REQUIRED")
        self.assertTrue(spec["decision_policy"]["repository_review_required"])
        self.assertFalse(spec["decision_policy"]["ask_user_by_default"])
        self.assertIn("unowned path: new_area/file.py", spec["decision_policy"]["repository_review_reasons"])

    def test_tool_spec_is_read_only_and_has_targeted_test(self) -> None:
        self.assertEqual(work_spec.TOOL_SPEC["side_effects"], "read_only")
        self.assertTrue(work_spec.TOOL_SPEC["canonical"])
        self.assertIn("tests.test_work_spec", work_spec.TOOL_SPEC["recommended_tests"])


if __name__ == "__main__":
    unittest.main()
