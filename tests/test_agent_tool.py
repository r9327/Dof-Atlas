from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import agent


ROOT = Path(__file__).resolve().parents[1]


class AgentToolTests(unittest.TestCase):
    def test_doctor_accepts_current_router(self) -> None:
        payload = agent.doctor_payload(ROOT)
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["context_index_current"])
        self.assertEqual(payload["scope_count"], 23)
        self.assertEqual(payload["errors"], [])

    def test_inspect_combines_scope_manifest_and_existing_rules(self) -> None:
        payload = agent.inspect_scope(ROOT, "encyclopedia_guide")
        self.assertEqual(payload["kind"], "feature")
        self.assertIn("AGENTS.md", payload["rules"])
        self.assertIn("data/AGENTS.md", payload["rules"])
        self.assertIn("PHASE_CERTIFICATION.md", payload["rules"])
        self.assertIn(
            "data/routes/guide_ultime_manual/manifest_v1.json",
            payload["canonical_entries"],
        )
        self.assertIn(
            "app/modules/encyclopedia/views/guides_view.py",
            payload["working_set"],
        )
        self.assertIn("persistence_identity", payload["shared_dependencies"])

    def test_inspect_preserves_placeholder_state(self) -> None:
        payload = agent.inspect_scope(ROOT, "encyclopedia_bestiary")
        self.assertEqual(payload["implementation"], "placeholder")
        self.assertEqual(payload["canonical_entries"], [])

    def test_impact_routes_only_declared_working_set_anchors(self) -> None:
        path = "app/modules/encyclopedia/views/guides_view.py"
        payload = agent.impact_payload(ROOT, [path])
        self.assertEqual(payload["scope_matches"][path], ["encyclopedia_guide"])
        self.assertEqual(payload["scopes"], ["encyclopedia_guide"])
        self.assertIn("persistence_identity", payload["shared_dependencies"])
        self.assertIn(
            "data/routes/guide_ultime_manual/manifest_v1.json",
            payload["canonical_entries"],
        )
        self.assertIn("tests.test_guide_ultime_manual_prerequisites", payload["recommended_tests"])

    def test_symbols_indexes_only_declared_python_scope_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".ai/scopes").mkdir(parents=True)
            (root / "src/pkg").mkdir(parents=True)
            (root / ".ai/context-map.yaml").write_text(
                """schema_version: 2
rule_defaults:
  - AGENTS.md
scopes:
  demo:
    kind: feature
    manifest: .ai/scopes/demo.yaml
    rule_entries: []
    canonical_entries:
      - src/canonical.py
""",
                encoding="utf-8",
            )
            (root / ".ai/scopes/demo.yaml").write_text(
                """schema_version: 1
scope: demo
kind: feature
working_set:
  - src/sample.py
  - src/pkg/
shared_dependencies: []
context_entries:
  - src/context.py
""",
                encoding="utf-8",
            )
            (root / "src/sample.py").write_text(
                """class Demo:
    pass

def helper():
    def nested():
        return 1
    return nested()

async def async_task():
    return None
""",
                encoding="utf-8",
            )
            (root / "src/pkg/second.py").write_text("class Second:\n    pass\n", encoding="utf-8")
            (root / "src/context.py").write_text("def context_helper():\n    return 1\n", encoding="utf-8")
            (root / "src/canonical.py").write_text("VALUE = 1\n", encoding="utf-8")

            payload = agent.symbols_payload(root, "demo")

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["source"], "scope-declared-python-ast")
        self.assertEqual(payload["scope"], "demo")
        self.assertEqual(payload["file_count"], 4)
        self.assertEqual(
            set(payload["files"]),
            {"src/sample.py", "src/pkg/second.py", "src/context.py", "src/canonical.py"},
        )
        sample_symbols = payload["files"]["src/sample.py"]
        self.assertEqual([symbol["name"] for symbol in sample_symbols], ["Demo", "helper", "async_task"])
        self.assertEqual([symbol["kind"] for symbol in sample_symbols], ["class", "function", "async_function"])
        self.assertNotIn("nested", {symbol["name"] for symbol in sample_symbols})
        self.assertEqual(payload["files"]["src/canonical.py"], [])

    def test_symbols_real_scope_stays_inside_declared_python_surface(self) -> None:
        payload = agent.symbols_payload(ROOT, "encyclopedia_guide")
        self.assertGreater(payload["file_count"], 0)
        self.assertGreater(payload["symbol_count"], 0)
        self.assertIn("app/modules/encyclopedia/views/guides_view.py", payload["files"])
        self.assertIn("app/quest_catalog.py", payload["files"])
        self.assertNotIn("data/routes/guide_ultime_manual/manifest_v1.json", payload["files"])
        self.assertTrue(all(path.endswith(".py") for path in payload["files"]))

    def test_symbols_rejects_unknown_scope(self) -> None:
        with self.assertRaisesRegex(agent.AgentConfigError, "unknown scope"):
            agent.symbols_payload(ROOT, "missing_scope")

    def test_validate_delegates_directly_to_atlas_integrity(self) -> None:
        arguments = ["critical", "--base-ref", "origin/main", "--json"]
        with mock.patch.object(agent.atlas_integrity, "main", return_value=7) as delegated:
            exit_code = agent.main(["validate", *arguments])
        self.assertEqual(exit_code, 7)
        delegated.assert_called_once_with(arguments)


if __name__ == "__main__":
    unittest.main()
