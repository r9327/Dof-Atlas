from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.agent_planner import build_plan, minimum_integrity_mode, required_groups


class AgentPlannerTests(unittest.TestCase):
    @staticmethod
    def _policy() -> dict:
        return {
            "schema_version": 1,
            "modes": {
                "FAST": ["META_INTEGRITY", "DIFF_TARGETS"],
                "CRITICAL": [
                    "META_INTEGRITY",
                    "DIFF_TARGETS",
                    "GOLDEN_FLOWS",
                    "PERSISTENCE",
                    "TEST_INTEGRITY",
                    "CI_INTEGRITY",
                ],
                "FULL": [
                    "META_INTEGRITY",
                    "DIFF_TARGETS",
                    "GOLDEN_FLOWS",
                    "PERSISTENCE",
                    "TEST_INTEGRITY",
                    "CI_INTEGRITY",
                    "DATA_INTEGRITY",
                ],
                "DEEP": [
                    "META_INTEGRITY",
                    "DIFF_TARGETS",
                    "GOLDEN_FLOWS",
                    "PERSISTENCE",
                    "TEST_INTEGRITY",
                    "CI_INTEGRITY",
                    "DATA_INTEGRITY",
                    "TIMING_PERFORMANCE",
                ],
            },
            "risk_requirements": {
                "LOW": [],
                "MEDIUM": ["GOLDEN_FLOWS"],
                "HIGH": ["PERSISTENCE"],
                "CRITICAL": ["TEST_INTEGRITY", "CI_INTEGRITY"],
            },
        }

    @staticmethod
    def _catalog(*, atlas_safe: bool = True) -> dict:
        def row(path: str, *, safe: bool = True) -> dict:
            return {
                "path": path,
                "invocation": f"py -3.13 -m {path[:-3].replace('/', '.')}",
                "readiness": "agent_ready" if safe else "review_before_agent_use",
                "safe_for_agent": safe,
                "automation_ready": safe,
                "cost_hint": "variable",
            }

        return {
            "tools": [
                row("tools/atlas_integrity.py", safe=atlas_safe),
                row("tools/guide_integrity.py"),
                row("tools/ai_context.py"),
            ]
        }

    def test_minimum_mode_is_derived_from_policy_requirements(self) -> None:
        policy = self._policy()
        medium = {"risk": "MEDIUM", "affected_groups": []}
        data = {"risk": "LOW", "affected_groups": ["DATA_INTEGRITY"]}
        deep = {"risk": "LOW", "affected_groups": ["TIMING_PERFORMANCE"]}

        self.assertEqual(required_groups(policy, medium), ["GOLDEN_FLOWS"])
        self.assertEqual(minimum_integrity_mode(policy, medium), "CRITICAL")
        self.assertEqual(minimum_integrity_mode(policy, data), "FULL")
        self.assertEqual(minimum_integrity_mode(policy, deep), "DEEP")

    def test_ready_plan_combines_tests_validation_and_guide_tooling(self) -> None:
        impact = {
            "scopes": ["encyclopedia_guide"],
            "unowned_paths": [],
            "ambiguous_paths": [],
            "recommended_tests": ["tests.test_alpha", "tests.test_beta"],
            "rules": ["AGENTS.md"],
            "canonical_entries": ["app/modules/encyclopedia/guide.py"],
            "context_entries": ["ROAD_IA.md"],
            "working_set": ["app/modules/encyclopedia/"],
        }
        with tempfile.TemporaryDirectory() as directory:
            plan = build_plan(
                Path(directory),
                ["docs/guide-note.md"],
                impact,
                policy=self._policy(),
                catalog_report=self._catalog(),
            )

        self.assertEqual(plan["status"], "READY")
        self.assertTrue(plan["automation_safe"])
        self.assertEqual(plan["minimum_integrity_mode"], "FAST")
        self.assertEqual(
            plan["validation_command"],
            ["py", "-3.13", "-m", "tools.agent", "validate", "fast", "--json"],
        )
        self.assertEqual(
            plan["test_command"],
            [
                "py",
                "-3.13",
                "-m",
                "unittest",
                "tests.test_alpha",
                "tests.test_beta",
            ],
        )
        recommended = {row["path"] for row in plan["recommended_tools"]}
        self.assertIn("tools/atlas_integrity.py", recommended)
        self.assertIn("tools/guide_integrity.py", recommended)

    def test_unowned_path_requires_review(self) -> None:
        impact = {
            "scopes": [],
            "unowned_paths": ["misc/new_file.py"],
            "ambiguous_paths": [],
            "recommended_tests": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            plan = build_plan(
                Path(directory),
                ["misc/new_file.py"],
                impact,
                policy=self._policy(),
                catalog_report=self._catalog(),
            )

        self.assertEqual(plan["status"], "REVIEW_REQUIRED")
        self.assertFalse(plan["automation_safe"])
        self.assertTrue(plan["ownership"]["review_required"])

    def test_unsafe_canonical_validation_tool_blocks_automatic_plan(self) -> None:
        impact = {
            "scopes": [],
            "unowned_paths": [],
            "ambiguous_paths": [],
            "recommended_tests": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            plan = build_plan(
                Path(directory),
                ["README.md"],
                impact,
                policy=self._policy(),
                catalog_report=self._catalog(atlas_safe=False),
            )

        self.assertEqual(plan["status"], "REVIEW_REQUIRED")
        self.assertFalse(plan["automation_safe"])
        self.assertEqual(plan["unsafe_recommended_tools"], ["tools/atlas_integrity.py"])

    def test_ai_context_change_recommends_context_tool(self) -> None:
        impact = {
            "scopes": [],
            "unowned_paths": [],
            "ambiguous_paths": [],
            "recommended_tests": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            plan = build_plan(
                Path(directory),
                [".ai/context-map.yaml"],
                impact,
                policy=self._policy(),
                catalog_report=self._catalog(),
            )

        recommended = {row["path"] for row in plan["recommended_tools"]}
        self.assertIn("tools/ai_context.py", recommended)
        self.assertIn("tools/atlas_integrity.py", recommended)


if __name__ == "__main__":
    unittest.main()
