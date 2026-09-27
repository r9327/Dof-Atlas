from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import agent


ROOT = Path(__file__).resolve().parents[1]


class AgentScopeTestMappingTests(unittest.TestCase):
    def test_current_scope_test_map_is_explicit_and_resolves_existing_modules(self) -> None:
        context_map = agent._load_context_map(ROOT)
        self.assertEqual(len(context_map["scopes"]), 23)
        self.assertEqual(agent._scope_test_mapping_errors(ROOT, context_map), [])
        self.assertTrue(all("test_entries" in config for config in context_map["scopes"].values()))

    def test_inspect_exposes_scope_tests_without_inventing_placeholder_tests(self) -> None:
        guide = agent.inspect_scope(ROOT, "encyclopedia_guide")
        self.assertIn("tests.test_guide_ultime_manual_prerequisites", guide["test_entries"])
        self.assertIn("tests.test_guide_ultime_final_coverage_catalog", guide["test_entries"])

        bestiary = agent.inspect_scope(ROOT, "encyclopedia_bestiary")
        self.assertEqual(bestiary["implementation"], "placeholder")
        self.assertEqual(bestiary["test_entries"], [])

    def test_impact_prioritizes_scope_tests_before_generic_fallbacks(self) -> None:
        path = "app/modules/encyclopedia/views/guides_view.py"
        payload = agent.impact_payload(ROOT, [path])

        self.assertEqual(payload["scopes"], ["encyclopedia_guide"])
        self.assertEqual(
            payload["scope_tests"][:2],
            [
                "tests.test_guide_ultime_manual_prerequisites",
                "tests.test_guide_ultime_final_coverage_catalog",
            ],
        )
        self.assertEqual(payload["recommended_tests"][: len(payload["scope_tests"])], payload["scope_tests"])

    def test_mapping_validation_rejects_missing_and_invalid_test_modules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests/test_present.py").write_text("", encoding="utf-8")
            context_map = {
                "scopes": {
                    "demo": {
                        "test_entries": [
                            "tests.test_present",
                            "tests.test_missing",
                            "not_tests.module",
                        ]
                    },
                    "implicit": {},
                }
            }

            errors = agent._scope_test_mapping_errors(root, context_map)

        self.assertIn("demo: missing test module tests.test_missing", errors)
        self.assertIn("demo: invalid test module not_tests.module", errors)
        self.assertIn("implicit: test_entries must be an explicit list", errors)


if __name__ == "__main__":
    unittest.main()
