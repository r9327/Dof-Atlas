from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools import ai_context


ROOT = Path(__file__).resolve().parents[1]


class AiContextTests(unittest.TestCase):
    def test_route_classifies_major_project_areas(self) -> None:
        cases = {
            "app/core/character_identity.py": "core",
            "app/modules/encyclopedia/views/guides_view.py": "guide",
            "app/modules/encyclopedia/providers/achievement_provider.py": "encyclopedia",
            "app/ui/theme.py": "ui",
            "app/preload.py": "runtime",
            "local_dofus_data/catalog.py": "runtime",
            "data/local/example.json": "data",
            "config/example.json": "data",
            "tests/test_repository_git_hooks.py": "tests",
            "tools/atlas_integrity.py": "quality",
            ".github/workflows/app-ci.yml": "quality",
            ".githooks/pre-commit": "quality",
            "ROAD_IA.md": "quality",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(ai_context.classify_path(path), expected)

    def test_context_recommendations_are_scoped(self) -> None:
        guide_docs = ai_context.recommended_context(
            ["app/modules/encyclopedia/views/guides_view.py"]
        )
        self.assertIn("GUIDE_ULTIME_STATUS.md", guide_docs)
        self.assertIn("PERFORMANCE_GUARDRAILS.md", guide_docs)
        self.assertNotIn("ZERO_TRUST_RULES.md", guide_docs)

        quality_docs = ai_context.recommended_context(["tools/atlas_integrity.py"])
        self.assertIn("ZERO_TRUST_RULES.md", quality_docs)
        self.assertIn("PHASE_CERTIFICATION.md", quality_docs)

    def test_impact_recommendations_use_existing_tests_and_canonical_anchors(self) -> None:
        guide_path = "app/modules/encyclopedia/views/guides_view.py"
        guide_tests = ai_context.recommended_tests(ROOT, [guide_path])
        guide_anchors = ai_context.recommended_canonical_paths(ROOT, [guide_path])
        self.assertIn("tests.test_guide_ultime_manual_prerequisites", guide_tests)
        self.assertIn("data/routes/guide_ultime_manual/manifest_v1.json", guide_anchors)

        quality_tests = ai_context.recommended_tests(ROOT, ["tools/ai_context.py"])
        self.assertIn("tests.test_ai_context", quality_tests)
        self.assertIn("tests.test_repository_git_hooks", quality_tests)

    def test_committed_context_index_matches_head(self) -> None:
        index_path = ROOT / ai_context.INDEX_PATH
        self.assertTrue(index_path.is_file(), index_path)
        actual = json.loads(index_path.read_text(encoding="utf-8"))
        expected = ai_context.build_index(ROOT, ai_context.committed_tree_sha(ROOT))
        self.assertEqual(actual, expected)
        self.assertEqual(actual["schema_version"], 2)
        self.assertNotIn(".ai", actual["entries"])
        self.assertIn("app", actual["entries"])
        self.assertIn("local_dofus_data", actual["entries"])

    def test_drift_warns_without_blocking_unknown_routes(self) -> None:
        report = ai_context.drift_report(ROOT, ["future_area/new_service.py"])
        self.assertTrue(report["index_current"])
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["unclassified_changes"], ["future_area/new_service.py"])

    def test_handoff_render_is_compact_and_explicit(self) -> None:
        payload = {
            "branch": "feature/example",
            "sha": "abc123",
            "base_ref": "main",
            "objective": "Fix example",
            "changed_files": ["app/example.py"],
            "working_tree": [],
            "verified": ["root cause confirmed"],
            "tests_run": ["tests.test_example"],
            "blockers": [],
            "next_action": "Run full validation.",
            "suggested_tests": ["tests.test_example"],
        }
        rendered = ai_context.render_handoff(payload)
        self.assertIn("Branch: `feature/example`", rendered)
        self.assertIn("SHA: `abc123`", rendered)
        self.assertIn("root cause confirmed", rendered)
        self.assertIn("Run full validation.", rendered)
        self.assertNotIn("full logs", rendered.casefold())

    def test_agent_contract_routes_through_compact_context(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("tools.ai_context status", agents)
        self.assertIn("AI_CONTEXT.md", agents)
        hook = (ROOT / "tools/git_hook.py").read_text(encoding="utf-8")
        self.assertIn("sync_index", hook)


if __name__ == "__main__":
    unittest.main()
