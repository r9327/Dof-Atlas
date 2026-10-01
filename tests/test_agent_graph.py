from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import agent, agent_graph, atlas_doctor

ROOT = Path(__file__).resolve().parents[1]


class AgentGraphTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.write("tools/__init__.py", "")
        self.write("tools/target.py", "def work():\n    return 1\n")
        self.write("tools/consumer.py", "from tools.target import work\nwork()\n")
        self.write("tools/outer.py", "from tools import consumer\n")
        self.write("tools/unrelated.py", "def work():\n    return 2\n")
        self.raw = {"directed": False, "nodes": [
            {"id": "target", "label": "work()", "_origin": "ast", "file_type": "code",
             "source_file": "tools/target.py", "source_location": "L1"},
            {"id": "consumer", "label": "consumer.py", "_origin": "ast", "file_type": "code",
             "source_file": "tools/consumer.py", "source_location": "L1"},
            {"id": "outer", "label": "outer.py", "_origin": "ast", "file_type": "code",
             "source_file": "tools/outer.py", "source_location": "L1"},
            {"id": "unrelated", "label": "work()", "_origin": "ast", "file_type": "code",
             "source_file": "tools/unrelated.py", "source_location": "L1"},
        ], "links": [self.edge("consumer", "target"), self.edge("outer", "consumer")]}
        self.graph_path = self.root / "graphify-out/graph.json"
        self.graph_path.parent.mkdir()
        self.graph = {}
        self.refresh()
        patcher = mock.patch("tools.atlas_doctor_lib.architecture.graph_status", side_effect=lambda root: dict(self.graph))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch("tools.agent.impact_payload", return_value={
            "scopes": ["quality_ci"], "recommended_tests": ["tests.test_agent_graph"],
            "unowned_paths": [], "ambiguous_paths": [],
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, path, content):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")

    @staticmethod
    def edge(source, target):
        return {"source": source, "target": target, "relation": "imports",
                "_origin": "ast", "confidence": "EXTRACTED", "confidence_score": 1.0,
                "context": "import", "source_location": "L1", "weight": 1.0}

    def refresh(self):
        self.graph_path.write_text(json.dumps(self.raw), encoding="utf-8")
        self.graph = {"status": "PASS", "graph": str(self.graph_path),
                      "graph_signature": hashlib.sha256(self.graph_path.read_bytes()).hexdigest()}

    def query(self, **kwargs):
        return agent.reverse_impact_payload(self.root, ["tools/target.py"], **kwargs)

    def test_real_format_import_edge_confirms_current_consumer_only(self):
        result = self.query()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["impacted_files"], ["tools/consumer.py", "tools/target.py"])
        self.assertEqual(result["reverse_dependencies"], {"tools/target.py": ["tools/consumer.py"]})
        self.assertEqual(result["source_files_parsed"], 2)
        self.assertEqual(result["confirmed_relationships"][0]["evidence"], "CURRENT_PYTHON_IMPORT")
        self.assertEqual(result["recommended_tests"], ["tests.test_agent_graph"])
        self.assertTrue(result["read_only"])

    def test_current_graph_missing_a_requested_file_does_not_claim_zero_consumers(self):
        self.raw["nodes"] = [node for node in self.raw["nodes"] if node["id"] != "target"]
        self.raw["links"] = [self.edge("outer", "consumer")]
        self.refresh()
        result = self.query()
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["missing_graph_paths"], ["tools/target.py"])
        self.assertIn("coverage", result["reason"])
        self.assertEqual(result["confirmed_relationships"], [])
        self.assertEqual(result["source_files_parsed"], 1)

    def test_real_submodule_imports_from_format_finds_package_consumer(self):
        self.write("tools/consumer.py", "from tools import target as dependency\n")
        self.raw["nodes"][0].update(label="target.py", source_location="L1")
        self.raw["links"][0].update(relation="imports_from", context="submodule_import")
        self.refresh()
        result = self.query()
        self.assertEqual(result["status"], "PASS")
        self.assertIn("tools/consumer.py", result["impacted_files"])
        self.assertEqual(result["confirmed_relationships"][0]["relation"], "imports_from")

    def test_depth_two_is_explicit_and_bounded(self):
        result = self.query(depth=2)
        self.assertIn("tools/outer.py", result["impacted_files"])
        self.assertEqual(result["source_files_parsed"], 3)
        with self.assertRaises(agent.AgentConfigError):
            self.query(depth=3)

    def test_graph_misbinding_is_not_a_confirmed_consumer(self):
        self.raw["links"].append(self.edge("unrelated", "target"))
        self.refresh()
        result = self.query()
        self.assertEqual(result["status"], "REVIEW")
        self.assertNotIn("tools/unrelated.py", result["impacted_files"])
        self.assertEqual(result["unconfirmed_relationships"][0]["consumer"], "tools/unrelated.py")

    def test_inferred_edge_never_becomes_confirmed_import_evidence(self):
        self.raw["links"][0]["confidence"] = "INFERRED"
        self.refresh()
        result = self.query()
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["confirmed_relationships"], [])

    def test_symbol_selection_reports_module_level_precision(self):
        result = self.query(symbol="work")
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["symbol_precision"], "MODULE_DEPENDENCY_ONLY")
        self.assertEqual(result["confirmed_relationships"][0]["symbol_candidate"], "work()")
        self.assertEqual(self.query(symbol="absent")["confirmed_relationships"], [])

    def test_absent_stale_invalid_graph_never_triggers_generation(self):
        with mock.patch("tools.graphify.build_graph") as build:
            for status in ("MISSING", "STALE", "INVALID"):
                self.graph["status"] = status
                result = self.query()
                self.assertEqual(result["status"], "REVIEW")
                self.assertEqual(result["source_files_parsed"], 0)
            build.assert_not_called()

    def test_graph_changed_after_provenance_validation_requires_review(self):
        self.graph_path.write_text("{}", encoding="utf-8")
        self.assertIn("changed", self.query()["reason"])

    def test_invalid_paths_cannot_escape_the_repository(self):
        for path in ("../outside.py", str(self.root / "tools/target.py"), "tools/missing.py"):
            result = agent.reverse_impact_payload(self.root, [path])
            self.assertEqual(result["status"], "REVIEW")
            self.assertEqual(result["source_files_parsed"], 0)

    def test_file_budget_never_silently_expands_transitively(self):
        with mock.patch("tools.agent_graph.MAX_FILES", 1):
            result = self.query(depth=2)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["impacted_files"], ["tools/target.py"])

    def test_reciprocal_imports_terminate_without_global_closure(self):
        self.write("tools/target.py", "from tools.consumer import work\ndef work():\n    return 1\n")
        self.raw["links"].append(self.edge("target", "consumer"))
        self.refresh()
        result = self.query(depth=2)
        self.assertLessEqual(len(result["impacted_files"]), 3)
        self.assertLessEqual(result["source_files_parsed"], 3)

    def test_canonical_import_helper_resolves_existing_child_and_alias(self):
        self.write("tools/outer.py", "from tools import consumer as dependency\n")
        imports = agent._internal_imports(self.root, "tools/outer.py")
        self.assertIn("tools/consumer.py", imports)
        self.assertIn("tools/__init__.py", imports)
        self.assertNotIn("tools/work.py", agent._internal_imports(self.root, "tools/consumer.py"))

    def test_agent_cli_routes_read_only_engine_and_stable_json(self):
        with mock.patch.object(agent, "ROOT", self.root), contextlib.redirect_stdout(io.StringIO()) as output:
            code = agent.main(["reverse-impact", "tools/target.py", "--json"])
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["kind"], "reverse_impact")

    def test_doctor_reuses_agent_engine_without_implicit_build(self):
        args = argparse.Namespace(install=False, rebuild=False, open=False, json=True,
                                  impact=["tools/target.py"], symbol=None, depth=1)
        with mock.patch("tools.atlas_doctor_lib.architecture.architecture", return_value={"status": "PASS"}) as architecture:
            payload = atlas_doctor.command_graph(self.root, args)
        architecture.assert_called_once_with(self.root, rebuild=False)
        self.assertEqual(payload["impact"]["status"], "PASS")

    def test_structural_plan_consumes_graph_scopes_and_tests(self):
        graph_impact = {"status": "PASS", "graph": {"status": "PASS"},
                        "scopes": ["quality_ci"], "recommended_tests": ["tests.test_consumer"]}
        plan = {"status": "READY", "automation_safe": True}
        with mock.patch("tools.agent_graph.reverse_impact", return_value=graph_impact) as query, mock.patch.object(agent.agent_planner, "build_plan", return_value=plan) as planner, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(agent.main(["plan", "tools/agent.py", "--structural", "--json"]), 0)
        query.assert_called_once_with(
            agent.ROOT, ["tools/agent.py"], symbol=None, depth=1,
            imports_resolver=agent._internal_imports, symbols_resolver=agent._python_symbols,
            impact_resolver=agent.impact_payload,
        )
        impact = planner.call_args.args[2]
        self.assertIn("tests.test_consumer", impact["recommended_tests"])
        self.assertEqual(json.loads(output.getvalue())["architecture_preflight"]["impact"], graph_impact)

    def test_uncertain_structural_impact_blocks_automatic_editing(self):
        graph_impact = {"status": "REVIEW", "graph": {"status": "PASS"},
                        "scopes": [], "recommended_tests": []}
        with mock.patch("tools.agent_graph.reverse_impact", return_value=graph_impact), mock.patch.object(agent.agent_planner, "build_plan", return_value={"status": "READY", "automation_safe": True}), contextlib.redirect_stdout(io.StringIO()) as output:
            agent.main(["plan", "tools/agent.py", "--structural", "--json"])
        self.assertFalse(json.loads(output.getvalue())["automation_safe"])

    def test_local_plan_does_not_query_graph(self):
        with mock.patch("tools.agent_graph.reverse_impact", side_effect=AssertionError("Unexpected graph query")), mock.patch.object(agent.agent_planner, "build_plan", return_value={}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(agent.main(["plan", "tools/agent.py", "--json"]), 0)

    def test_consumer_ownership_is_advisory_but_change_ownership_requires_review(self):
        routing = {"scopes": ["quality_ci"], "recommended_tests": [],
                   "unowned_paths": ["tools/consumer.py"], "ambiguous_paths": []}
        with mock.patch("tools.agent.impact_payload", return_value=routing):
            result = self.query()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["unowned_consumer_paths"], ["tools/consumer.py"])
        routing["unowned_paths"].append("tools/target.py")
        with mock.patch("tools.agent.impact_payload", return_value=routing):
            result = self.query()
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["ownership_review_paths"], ["tools/target.py"])

    def test_graph_engine_does_not_import_the_agent_facade_reciprocally(self):
        self.assertNotIn("tools/agent.py", agent._internal_imports(ROOT, "tools/agent_graph.py"))

    def test_new_cli_help_exposes_bounded_cost(self):
        with contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as exit:
            agent.main(["reverse-impact", "--help"])
        self.assertEqual(exit.exception.code, 0)
        self.assertIn("--depth {1,2}", output.getvalue())


if __name__ == "__main__":
    unittest.main()
