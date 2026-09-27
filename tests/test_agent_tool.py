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
        self.assertEqual(payload["ownership_conflicts"], [])
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
        self.assertEqual(payload["ownership"][path]["status"], "OWNED")
        self.assertEqual(payload["ownership"][path]["primary_scope"], "encyclopedia_guide")
        self.assertEqual(payload["unowned_paths"], [])
        self.assertEqual(payload["ambiguous_paths"], [])
        self.assertIn("persistence_identity", payload["shared_dependencies"])
        self.assertIn(
            "data/routes/guide_ultime_manual/manifest_v1.json",
            payload["canonical_entries"],
        )
        self.assertIn("tests.test_guide_ultime_manual_prerequisites", payload["recommended_tests"])

    def test_ownership_distinguishes_specific_placeholder_ambiguous_and_unowned_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".ai/scopes").mkdir(parents=True)
            (root / ".ai/context-map.yaml").write_text(
                """schema_version: 2
rule_defaults:
  - AGENTS.md
scopes:
  broad:
    kind: shared_infrastructure
    manifest: .ai/scopes/broad.yaml
    rule_entries: []
    canonical_entries: []
  feature:
    kind: feature
    manifest: .ai/scopes/feature.yaml
    rule_entries: []
    canonical_entries: []
  conflict_a:
    kind: feature
    manifest: .ai/scopes/conflict_a.yaml
    rule_entries: []
    canonical_entries: []
  conflict_b:
    kind: feature
    manifest: .ai/scopes/conflict_b.yaml
    rule_entries: []
    canonical_entries: []
  shell:
    kind: feature
    manifest: .ai/scopes/shell.yaml
    rule_entries: []
    canonical_entries: []
  placeholder:
    kind: feature
    implementation: placeholder
    manifest: .ai/scopes/placeholder.yaml
    rule_entries: []
    canonical_entries: []
""",
                encoding="utf-8",
            )
            manifests = {
                "broad": """schema_version: 1
scope: broad
kind: shared_infrastructure
working_set:
  - src/
shared_dependencies: []
context_entries: []
""",
                "feature": """schema_version: 1
scope: feature
kind: feature
working_set:
  - src/feature.py
shared_dependencies: []
context_entries: []
""",
                "conflict_a": """schema_version: 1
scope: conflict_a
kind: feature
working_set:
  - src/conflict.py
shared_dependencies: []
context_entries: []
""",
                "conflict_b": """schema_version: 1
scope: conflict_b
kind: feature
working_set:
  - src/conflict.py
shared_dependencies: []
context_entries: []
""",
                "shell": """schema_version: 1
scope: shell
kind: feature
working_set:
  - src/shell.py
shared_dependencies: []
context_entries: []
""",
                "placeholder": """schema_version: 1
scope: placeholder
kind: feature
implementation: placeholder
working_set:
  - src/shell.py
shared_dependencies: []
context_entries: []
""",
            }
            for scope, content in manifests.items():
                (root / f".ai/scopes/{scope}.yaml").write_text(content, encoding="utf-8")

            payload = agent.ownership_payload(
                root,
                ["src/feature.py", "src/conflict.py", "src/shell.py", "other/new.py"],
            )
            conflicts = agent.ownership_conflicts(root)

        feature = payload["paths"]["src/feature.py"]
        self.assertEqual(feature["status"], "OWNED")
        self.assertEqual(feature["primary_scope"], "feature")
        self.assertEqual(feature["shadowed_scopes"], ["broad"])

        conflict = payload["paths"]["src/conflict.py"]
        self.assertEqual(conflict["status"], "AMBIGUOUS")
        self.assertEqual(set(conflict["candidate_scopes"]), {"conflict_a", "conflict_b"})
        self.assertEqual(
            set(conflict["review_manifests"]),
            {".ai/scopes/conflict_a.yaml", ".ai/scopes/conflict_b.yaml"},
        )

        shell = payload["paths"]["src/shell.py"]
        self.assertEqual(shell["status"], "OWNED")
        self.assertEqual(shell["primary_scope"], "shell")
        self.assertEqual(shell["placeholder_scopes"], ["placeholder"])

        self.assertEqual(payload["paths"]["other/new.py"]["status"], "UNOWNED")
        self.assertEqual(payload["unowned_paths"], ["other/new.py"])
        self.assertEqual(payload["ambiguous_paths"], ["src/conflict.py"])
        self.assertEqual(payload["status"], "WARN")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["anchor"], "src/conflict.py")
        self.assertEqual(set(conflicts[0]["scopes"]), {"conflict_a", "conflict_b"})

    def test_ownership_real_map_has_unique_primary_routes(self) -> None:
        self.assertEqual(agent.ownership_conflicts(ROOT), [])
        payload = agent.ownership_payload(
            ROOT,
            [
                "app/quest_catalog.py",
                "app/cartography/scan_status_service.py",
                "app/modules/encyclopedia/constants.py",
                "unmapped/new_module.py",
            ],
        )
        self.assertEqual(payload["paths"]["app/quest_catalog.py"]["primary_scope"], "dofus_data")
        self.assertEqual(
            payload["paths"]["app/cartography/scan_status_service.py"]["primary_scope"],
            "world_scan",
        )
        shell = payload["paths"]["app/modules/encyclopedia/constants.py"]
        self.assertEqual(shell["primary_scope"], "encyclopedia_shell")
        self.assertIn("encyclopedia_bestiary", shell["placeholder_scopes"])
        self.assertEqual(payload["paths"]["unmapped/new_module.py"]["status"], "UNOWNED")

        quests = agent.inspect_scope(ROOT, "encyclopedia_quests")
        self.assertNotIn("app/quest_catalog.py", quests["working_set"])
        self.assertIn("app/quest_catalog.py", quests["context_entries"])
        self.assertIn(
            "app/quest_catalog.py",
            agent.symbols_payload(ROOT, "encyclopedia_quests")["files"],
        )

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

    def test_imports_enriches_working_set_without_recursive_scan(self) -> None:
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
    canonical_entries: []
""",
                encoding="utf-8",
            )
            (root / ".ai/scopes/demo.yaml").write_text(
                """schema_version: 1
scope: demo
kind: feature
working_set:
  - src/pkg/main.py
shared_dependencies: []
context_entries: []
""",
                encoding="utf-8",
            )
            (root / "src/__init__.py").write_text("", encoding="utf-8")
            (root / "src/pkg/__init__.py").write_text("", encoding="utf-8")
            (root / "src/pkg/main.py").write_text(
                """import json
from src.shared import helper
from . import sibling
from .nested import thing

def lazy_dependency():
    from src.deep import value
    return value
""",
                encoding="utf-8",
            )
            (root / "src/shared.py").write_text(
                "from src.transitive import value\n",
                encoding="utf-8",
            )
            (root / "src/pkg/sibling.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "src/pkg/nested.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "src/deep.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "src/transitive.py").write_text("VALUE = 1\n", encoding="utf-8")

            payload = agent.imports_payload(root, "demo")

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["source"], "scope-working-set-python-imports")
        self.assertEqual(payload["scope"], "demo")
        self.assertEqual(payload["file_count"], 1)
        self.assertEqual(
            set(payload["files"]["src/pkg/main.py"]),
            {"src/shared.py", "src/pkg/sibling.py", "src/pkg/nested.py", "src/deep.py"},
        )
        self.assertEqual(
            set(payload["import_dependencies"]),
            {"src/shared.py", "src/pkg/sibling.py", "src/pkg/nested.py", "src/deep.py"},
        )
        self.assertNotIn("src/transitive.py", payload["import_dependencies"])
        self.assertEqual(payload["enriched_working_set"][0], "src/pkg/main.py")
        self.assertNotIn("src/transitive.py", payload["enriched_working_set"])

    def test_imports_real_scope_resolves_internal_dependencies(self) -> None:
        payload = agent.imports_payload(ROOT, "encyclopedia_guide")
        self.assertGreater(payload["file_count"], 0)
        self.assertGreater(payload["edge_count"], 0)
        guide_view = "app/modules/encyclopedia/views/guides_view.py"
        self.assertIn(guide_view, payload["files"])
        self.assertIn("app/quest_catalog.py", payload["files"][guide_view])
        self.assertIn("app/quest_catalog.py", payload["import_dependencies"])
        self.assertIn("app/quest_catalog.py", payload["enriched_working_set"])
        self.assertTrue(all(path.endswith(".py") for path in payload["import_dependencies"]))

    def test_imports_rejects_unknown_scope(self) -> None:
        with self.assertRaisesRegex(agent.AgentConfigError, "unknown scope"):
            agent.imports_payload(ROOT, "missing_scope")

    def test_validate_delegates_directly_to_atlas_integrity(self) -> None:
        arguments = ["critical", "--base-ref", "origin/main", "--json"]
        with mock.patch.object(agent.atlas_integrity, "main", return_value=7) as delegated:
            exit_code = agent.main(["validate", *arguments])
        self.assertEqual(exit_code, 7)
        delegated.assert_called_once_with(arguments)


if __name__ == "__main__":
    unittest.main()
