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
            "data/local/example.json": "data",
            "tests/test_repository_git_hooks.py": "tests",
            "tools/atlas_integrity.py": "quality",
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

    def test_committed_context_index_matches_head(self) -> None:
        index_path = ROOT / ai_context.INDEX_PATH
        self.assertTrue(index_path.is_file(), index_path)
        actual = json.loads(index_path.read_text(encoding="utf-8"))
        expected = ai_context.build_index(ROOT, ai_context.committed_tree_sha(ROOT))
        self.assertEqual(actual, expected)

    def test_agent_contract_routes_through_compact_context(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("tools.ai_context status", agents)
        self.assertIn("AI_CONTEXT.md", agents)
        hook = (ROOT / "tools/git_hook.py").read_text(encoding="utf-8")
        self.assertIn("sync_index", hook)


if __name__ == "__main__":
    unittest.main()
