from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib.deep_intelligence import (
    scan_sources, graph_reachability, architectural_guardrails, inspect_code,
)


class DeepIntelligenceTests(unittest.TestCase):
    def test_exact_ast_duplicates_json_and_silent_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in {
                "app/a.py": "def first():\n    return 123\ntry:\n    x = 1\nexcept Exception:\n    pass\n",
                "app/b.py": "def second():\n    return 123\nthing = 'data/catalog.json'\n",
            }.items():
                p = root / name
                p.parent.mkdir(exist_ok=True)
                p.write_text(content)
            report = scan_sources(root, ["app/a.py", "app/b.py"])
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["counts"]["duplicate_groups"], 1)
            self.assertEqual(report["counts"]["silent_exceptions"], 1)
            self.assertEqual(report["counts"]["literal_json_references"], 1)
            self.assertTrue(report["duplicate_bodies"][0]["review_only"])

    def test_symlink_and_traversal_are_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(scan_sources(root, ["../out.py"])["status"], "BLOCKED")

    def test_source_size_cap_is_explicit_not_a_false_pass(self):
        from tools.atlas_doctor_lib.deep_intelligence import MAX_SOURCE_BYTES
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "large.py"
            source.write_bytes(b"#" + b" " * MAX_SOURCE_BYTES)
            report = scan_sources(root, ["large.py"])
            self.assertEqual(report["status"], "REVIEW")
            self.assertTrue(report["truncated"])
            self.assertEqual(report["paths_inspected"], [])
            self.assertEqual(report["parse_errors"][0]["reason"], "SOURCE_SIZE_BUDGET_EXCEEDED")
            self.assertEqual(report["budgets"]["max_source_bytes"], MAX_SOURCE_BYTES)

    def test_result_cap_does_not_report_pass_on_incomplete_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "catalog.py"
            source.write_text("\n".join(
                f"item_{i} = 'data/{i}.json'" for i in range(95)
            ) + "\n")
            report = scan_sources(root, ["catalog.py"])
            self.assertEqual(report["status"], "REVIEW")
            self.assertTrue(report["truncated"])
            self.assertEqual(report["counts"]["literal_json_references"], 95)
            self.assertEqual(len(report["data_lineage_candidates"]), 80)

    def test_symlink_sources_are_rejected_before_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "real.py").write_text("pass\n")
            try:
                (root / "alias.py").symlink_to(root / "real.py")
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks not supported on this test platform")
            report = scan_sources(root, ["alias.py"])
            self.assertEqual(report["status"], "BLOCKED")

    def test_reachability_labels_unobserved_not_dead(self):
        graph = {"nodes": [
            {"id": "a", "source_file": "main.py"},
            {"id": "b", "source_file": "app/b.py"},
            {"id": "c", "source_file": "app/c.py"},
        ], "links": [
            {"source": "a", "target": "b", "relation": "imports",
             "confidence": "EXTRACTED", "_origin": "ast"},
        ]}
        report = graph_reachability(graph, ["main.py", "missing.py"])
        self.assertEqual(report["unreached_candidates"], ["app/c.py"])
        self.assertFalse(report["proof_of_dead_code"])
        self.assertEqual(report["status"], "REVIEW")

    def test_near_duplicates_are_not_semantically_proven(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text(
                "def price(items):\n    subtotal = 0\n"
                "    for item in items:\n        subtotal += item\n    return subtotal\n")
            (root / "b.py").write_text(
                "def total(values):\n    amount = 0\n"
                "    for value in values:\n        amount += value\n    return amount\n")
            report = scan_sources(root, ["a.py", "b.py"])
            self.assertEqual(report["counts"]["duplicate_groups"], 0)
            self.assertEqual(report["counts"]["near_duplicate_groups"], 1)
            self.assertTrue(report["near_duplicate_candidates"][0]["review_only"])
            self.assertFalse(report["near_duplicate_candidates"][0]["semantic_equivalence_proven"])

    def test_runtime_reachability_requires_valid_provenance(self):
        sha = "a" * 40
        graph = {"built_at_commit": sha,
                 "nodes": [{"id": 1, "source_file": "main.py"},
                           {"id": 2, "source_file": "app/first.py"},
                           {"id": 3, "source_file": "app/dynamic.py"}],
                 "links": [{"source": 1, "target": 2, "relation": "imports",
                            "confidence": "EXTRACTED", "_origin": "ast"}]}
        trace = {"candidate_sha": sha, "worktree_clean": True, "truncated": False,
                 "events": [{"type": "python_call_edge", "source": "app/first.py",
                             "target": "app/dynamic.py"}]}
        actual = graph_reachability(graph, ["main.py"], trace=trace)
        self.assertEqual(actual["runtime_trace_status"], "MATCHED")
        self.assertEqual(actual["observed_python_call_edges"], 1)
        self.assertEqual(actual["unreached_total"], 0)
        trace["worktree_clean"] = False
        stale = graph_reachability(graph, ["main.py"], trace=trace)
        self.assertEqual(stale["status"], "REVIEW")
        self.assertEqual(stale["unreached_candidates"], ["app/dynamic.py"])
        self.assertFalse(stale["proof_of_dead_code"])

    def test_qt_connect_is_not_callback_execution(self):
        sha = "b" * 40
        graph = {"built_at_commit": sha,
                 "nodes": [{"id": 1, "source_file": "main.py"},
                           {"id": 2, "source_file": "app/slot.py"}], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "truncated": False,
                 "events": [{"type": "qt_signal_connect_returned", "source": "main.py",
                             "target": "app/slot.py"}]}
        result = graph_reachability(graph, ["main.py"], trace=trace)
        self.assertEqual(result["unreached_candidates"], ["app/slot.py"])
        self.assertEqual(result["qt_registered_but_not_invoked_candidates"], ["app/slot.py"])

    def test_launcher_entrypoints_include_worker_and_preflight(self):
        from tools.atlas_doctor_lib.deep_intelligence import launcher_entrypoints
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app").mkdir()
            for name in ("launch.py", "app/startup_preflight.py",
                         "app/startup_cache_warmup.py"):
                (root / name).write_text("pass\n")
            (root / "DOFUS.bat").write_text(
                'set "APP_SCRIPT=%ROOT%launch.py"\n'
                '"%PYTHON_EXE%" -m app.startup_preflight "%APP_SCRIPT%"\n'
                'start "" /b "%PYTHONW_EXE%" -m app.startup_cache_warmup\n'
            )
            report = launcher_entrypoints(root)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["entrypoints"], [
                "app/startup_cache_warmup.py", "app/startup_preflight.py",
                "launch.py",
            ])
            self.assertFalse(report["execution_proven"])

    def test_launcher_entrypoints_accept_a_symlinked_repo_root(self):
        from tools.atlas_doctor_lib.deep_intelligence import launcher_entrypoints
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "real_repo"
            root.mkdir()
            (root / "launch.py").write_text("pass\n")
            (root / "DOFUS.bat").write_text('set "APP_SCRIPT=%ROOT%launch.py"\n')
            alias = base / "alias_repo"
            try:
                alias.symlink_to(root, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Directory symlinks not available")
            result = launcher_entrypoints(alias)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["entrypoints"], ["launch.py"])
            self.assertFalse(result["execution_proven"])

    def test_undocumented_or_missing_launcher_cannot_prove_accessibility(self):
        from tools.atlas_doctor_lib.deep_intelligence import launcher_entrypoints
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(launcher_entrypoints(root)["status"], "REVIEW")
            (root / "DOFUS.bat").write_text(
                'set "APP_SCRIPT=%ROOT%missing.py"\n'
            )
            report = launcher_entrypoints(root)
            self.assertEqual(report["status"], "REVIEW")
            self.assertEqual(report["unresolved_declarations"], ["missing.py"])

    def test_missing_internal_import_is_flagged_without_code_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app/core").mkdir(parents=True)
            (root / "app/core/existing.py").write_text("pass\n")
            (root / "caller.py").write_text(
                "import app.core.existing\n"
                "from app.core.missing import coordinator_for\n"
                "from pathlib import Path\n"
            )
            result = scan_sources(root, ["caller.py"])
            self.assertEqual(result["status"], "REVIEW")
            self.assertEqual(result["counts"]["missing_internal_import_candidates"], 1)
            finding = result["missing_internal_import_candidates"][0]
            self.assertEqual((finding["module"], finding["line"]), ("app.core.missing", 2))
            self.assertTrue(finding["review_only"])

    def test_imported_package_attribute_is_not_called_a_missing_module(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app/core").mkdir(parents=True)
            (root / "app/core/__init__.py").write_text("name = 1\n")
            (root / "consumer.py").write_text("from app.core import name\n")
            result = scan_sources(root, ["consumer.py"])
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["missing_internal_import_candidates"], [])

    def test_json_lineage_to_ui_uses_only_source_confirmed_import_edges(self):
        from tools.atlas_doctor_lib.deep_intelligence import trace_literal_json_to_ui
        graph = {"nodes": [
            {"id": 1, "source_file": "app/core/catalog.py"},
            {"id": 2, "source_file": "app/modules/encyclopedia/services/catalog_service.py"},
            {"id": 3, "source_file": "app/modules/encyclopedia/views/catalog_view.py"},
            {"id": 4, "source_file": "app/ui/decoy.py"},
        ], "links": [
            {"source": 2, "target": 1, "relation": "imports_from",
             "confidence": "EXTRACTED", "_origin": "ast"},
            {"source": 3, "target": 2, "relation": "imports",
             "confidence": "EXTRACTED", "_origin": "ast"},
            {"source": 4, "target": 1, "relation": "imports",
             "confidence": "INFERRED", "_origin": "generated"},
        ]}
        evidence = trace_literal_json_to_ui(graph, [{
            "path": "app/core/catalog.py", "line": 11,
            "data_reference": "data/catalog.json",
        }])
        self.assertEqual(evidence["status"], "REVIEW")
        self.assertEqual(evidence["references_with_ui_importers"], 1)
        self.assertEqual(evidence["references"][0]["possible_ui_importers"], [
            {"path": "app/modules/encyclopedia/views/catalog_view.py", "import_hops": 2}
        ])
        self.assertFalse(evidence["runtime_data_flow_proven"])
        self.assertFalse(evidence["references"][0]["data_read_proven"])

    def test_json_lineage_cycles_and_unproven_links_never_claim_ui(self):
        from tools.atlas_doctor_lib.deep_intelligence import trace_literal_json_to_ui
        graph = {"nodes": [
            {"id": "a", "source_file": "app/core/catalog.py"},
            {"id": "b", "source_file": "app/core/loader.py"},
            {"id": "c", "source_file": "app/pages/catalog_page.py"},
        ], "links": [
            {"source": "a", "target": "b", "relation": "imports",
             "confidence": "EXTRACTED", "_origin": "ast"},
            {"source": "b", "target": "a", "relation": "imports",
             "confidence": "EXTRACTED", "_origin": "ast"},
            {"source": "c", "target": "a", "relation": "imports",
             "confidence": "INFERRED", "_origin": "generated"},
        ]}
        data = trace_literal_json_to_ui(graph, [{"path": "app/core/catalog.py",
                                                "data_reference": "data/items.json"}])
        self.assertEqual(data["references"][0]["possible_ui_importers"], [])
        self.assertFalse(data["truncated"])

    def test_json_lineage_budgets_never_report_complete_when_graph_oversized(self):
        from tools.atlas_doctor_lib.deep_intelligence import trace_literal_json_to_ui
        graph = {"nodes": [{"id": n, "source_file": "app/core/item.py"}
                           for n in range(15001)], "links": []}
        data = trace_literal_json_to_ui(graph, [{"path": "app/core/item.py",
                                                "data_reference": "x.json"}])
        self.assertEqual(data["status"], "REVIEW")
        self.assertTrue(data["truncated"])
        self.assertFalse(data["runtime_data_flow_proven"])

    def test_old_architecture_debt_is_separate(self):
        g = {"nodes": [
            {"id": "a", "source_file": "app/a.py"},
            {"id": "b", "source_file": "tools/b.py"},
        ], "links": [
            {"source": "a", "target": "b", "relation": "imports",
             "confidence": "EXTRACTED"},
        ]}
        self.assertEqual(architectural_guardrails(g, g)["historical_candidates"], 1)
        self.assertEqual(architectural_guardrails(g, g)["new_candidate_violations"], [])
        self.assertEqual(architectural_guardrails(g)["status"], "REVIEW")

    def test_old_debt_does_not_block_when_exact_baseline_contains_it(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("pass\n")
            graph = {"nodes": [{"id": "a", "source_file": "main.py"},
                               {"id": "b", "source_file": "app/x.py"},
                               {"id": "c", "source_file": "tools/y.py"}],
                     "links": [{"source": "b", "target": "c", "relation": "imports",
                                "confidence": "EXTRACTED", "_origin": "ast"}]}
            baseline = root / "before.json"
            baseline.write_text(json.dumps(graph))
            evidence = {"status": "PASS", "graph": str(baseline)}
            confirmed = {"blocking_findings": [{"source": "app/x.py", "target": "tools/y.py"}]}
            with patch("tools.atlas_doctor_lib.architecture.graph_status", return_value=evidence), \
                 patch("tools.atlas_doctor_lib.graph_audit.inspect_graph", return_value=confirmed):
                report = inspect_code(root, paths=["main.py"], baseline=baseline)
            self.assertEqual(report["architectural_rules"]["confirmed_blockers"], [])
            self.assertEqual(report["architectural_rules"]["historical_candidates"], 1)

    def test_missing_graph_does_not_claim_reachability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root / "main.py"
            p.write_text("pass\n")
            with patch("tools.atlas_doctor_lib.architecture.graph_status", return_value={"status": "MISSING"}):
                report = inspect_code(root, paths=["main.py"])
            self.assertEqual(report["status"], "REVIEW")
            self.assertEqual(report["reachability"]["status"], "UNAVAILABLE")
            self.assertFalse(report["tests_executed"])


    def test_observed_json_open_and_python_ui_call_chain(self):
        from tools.atlas_doctor_lib.deep_intelligence import trace_observed_json_to_ui
        sha = "c" * 40
        graph = {"built_at_commit": sha, "nodes": [
            {"id": "a", "source_file": "app/core/reader.py"},
            {"id": "b", "source_file": "app/modules/encyclopedia/services/provider.py"},
            {"id": "c", "source_file": "app/modules/encyclopedia/views/catalog_view.py"},
        ], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "truncated": False,
                 "events": [
                     {"type": "file_open", "source": "app/core/reader.py",
                      "target": "data/catalog.json"},
                     {"type": "python_call_edge",
                      "source": "app/modules/encyclopedia/services/provider.py",
                      "target": "app/core/reader.py"},
                     {"type": "python_call_edge",
                      "source": "app/modules/encyclopedia/views/catalog_view.py",
                      "target": "app/modules/encyclopedia/services/provider.py"},
                 ]}
        result = trace_observed_json_to_ui(graph, trace)
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["json_opens_observed"], 1)
        self.assertEqual(result["references"][0]["ui_callers_in_same_trace"], [
            {"path": "app/modules/encyclopedia/views/catalog_view.py", "call_hops": 2}
        ])
        self.assertFalse(result["data_read_proven"])
        self.assertFalse(result["ui_render_proven"])
        self.assertFalse(result["references"][0]["data_read_proven"])

    def test_observed_json_lineage_rejects_stale_and_incomplete_traces(self):
        from tools.atlas_doctor_lib.deep_intelligence import trace_observed_json_to_ui
        graph = {"built_at_commit": "a" * 40, "nodes": [
            {"id": 1, "source_file": "app/core/reader.py"},
        ], "links": []}
        trace = {"candidate_sha": "b" * 40, "worktree_clean": True,
                 "truncated": False, "events": [
                     {"type": "file_open", "source": "app/core/reader.py",
                      "target": "data/items.json"},
                 ]}
        for change in ({"candidate_sha": "b" * 40},
                       {"candidate_sha": "a" * 40, "truncated": True},
                       {"candidate_sha": "a" * 40, "truncated": False, "events": ["invalid"]}):
            sample = {**trace, **change}
            actual = trace_observed_json_to_ui(graph, sample)
            self.assertEqual(actual["status"], "STALE_OR_INCOMPLETE")
            self.assertEqual(actual["json_opens_observed"], 0)
            self.assertEqual(actual["references"], [])

    def test_observed_json_lineage_ignores_untracked_data_and_outside_paths(self):
        from tools.atlas_doctor_lib.deep_intelligence import trace_observed_json_to_ui
        sha = "a" * 40
        graph = {"built_at_commit": sha, "nodes": [
            {"id": 1, "source_file": "app/core/reader.py"},
        ], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "truncated": False,
                 "events": [
                     {"type": "file_open", "source": "app/core/reader.py", "target": "../bad.json"},
                     {"type": "file_open", "source": "app/core/reader.py", "target": "/tmp/file.json"},
                     {"type": "file_open", "source": "missing.py", "target": "data/good.json"},
                 ]}
        result = trace_observed_json_to_ui(graph, trace)
        self.assertEqual(result["json_opens_observed"], 0)
        self.assertFalse(result["ui_render_proven"])
    def test_qt_callback_observation_is_distinct_from_registration(self):
        sha = "b" * 40
        graph = {"built_at_commit": sha,
                 "nodes": [{"id": 1, "source_file": "main.py"},
                           {"id": 2, "source_file": "app/slot.py"}], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "truncated": False,
                 "events": [
                     {"type": "qt_signal_connect_returned",
                      "source": "main.py", "target": "app/slot.py"},
                     {"type": "qt_callback_invoked", "source": "main.py",
                      "target": "app/slot.py", "confidence": "WRAPPED_PYTHON_CALLBACK_ENTERED"},
                 ]}
        report = graph_reachability(graph, ["main.py"], trace=trace)
        self.assertEqual(report["unreached_total"], 0)
        self.assertEqual(report["observed_qt_callback_targets"], ["app/slot.py"])
        self.assertEqual(report["qt_registered_but_not_invoked_candidates"], [])
        trace["worktree_clean"] = False
        self.assertEqual(graph_reachability(graph, ["main.py"], trace=trace)["unreached_total"], 1)

    def test_explicit_json_binding_confirms_decode_handoff_not_visual_render(self):
        from tools.atlas_doctor_lib.deep_intelligence import trace_explicit_json_bindings
        sha = "d" * 40
        graph = {"built_at_commit": sha, "nodes": [
            {"id": 1, "source_file": "app/core/data_reader.py"},
            {"id": 2, "source_file": "app/modules/encyclopedia/views/catalog_view.py"},
        ], "links": []}
        events = [
            {"type": "json_decoded", "source": "app/core/data_reader.py",
             "target": "data/catalog.json", "token": "json-1",
             "confidence": "JSON_DECODE_RETURNED"},
            {"type": "json_ui_bound", "source": "app/modules/encyclopedia/views/catalog_view.py",
             "token": "json-1", "confidence": "EXPLICIT_UI_BINDING_MARKER"},
        ]
        trace = {"candidate_sha": sha, "worktree_clean": True,
                 "truncated": False, "events": events}
        result = trace_explicit_json_bindings(graph, trace)
        self.assertEqual(result["status"], "OBSERVED_BINDING")
        self.assertEqual(result["json_decodes"], 1)
        self.assertEqual(result["bound_to_ui"], 1)
        self.assertEqual(result["bindings"][0]["ui_file"],
                         "app/modules/encyclopedia/views/catalog_view.py")
        self.assertFalse(result["ui_render_proven"])
        self.assertNotIn("token", result["bindings"][0])
        trace["candidate_sha"] = "b" * 40
        self.assertEqual(trace_explicit_json_bindings(graph, trace)["bound_to_ui"], 0)

    def test_unmatched_token_and_non_ui_marker_not_data_flow_proof(self):
        from tools.atlas_doctor_lib.deep_intelligence import trace_explicit_json_bindings
        sha = "f" * 40
        graph = {"built_at_commit": sha, "nodes": [
            {"id": 1, "source_file": "app/core/loader.py"},
            {"id": 2, "source_file": "app/services/service.py"}], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "truncated": False,
                 "events": [
                     {"type": "json_ui_bound", "source": "app/services/service.py",
                      "token": "json-1", "confidence": "EXPLICIT_UI_BINDING_MARKER"},
                     {"type": "json_decoded", "source": "app/core/loader.py",
                      "target": "data/a.json", "token": "json-1",
                      "confidence": "JSON_DECODE_RETURNED"},
                     {"type": "json_ui_bound", "source": "app/services/service.py",
                      "token": "json-1", "confidence": "EXPLICIT_UI_BINDING_MARKER"},
                 ]}
        result = trace_explicit_json_bindings(graph, trace)
        self.assertEqual(result["json_decodes"], 1)
        self.assertEqual(result["bound_to_ui"], 0)
        self.assertEqual(result["status"], "REVIEW")

    def test_qt_label_binding_evidence_is_positive_and_never_visual_proof(self):
        from tools.atlas_doctor_lib.deep_intelligence import trace_explicit_json_bindings
        sha = "9" * 40
        graph = {"built_at_commit": sha, "nodes": [
            {"id": 1, "source_file": "tools/atlas_doctor_lib/app_ui_smoke_scenario.py"},
            {"id": 2, "source_file": "app/pages/equipment_page.py"}], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "truncated": False,
                 "events": [
                     {"type": "json_decoded",
                      "source": "tools/atlas_doctor_lib/app_ui_smoke_scenario.py",
                      "target": ".ai/runtime/doctor_sample.json", "token": "json-1",
                      "confidence": "JSON_DECODE_RETURNED"},
                     {"type": "json_ui_bound", "source": "app/pages/equipment_page.py",
                      "token": "json-1", "confidence": "EXPLICIT_QT_LABEL_SETTEXT_RETURNED"},
                 ]}
        result = trace_explicit_json_bindings(graph, trace)
        self.assertEqual(result["bound_to_ui"], 1)
        self.assertEqual(result["bindings"][0]["confidence"], "QT_TEXT_BINDING_RETURNED")
        self.assertFalse(result["ui_render_proven"])
    def test_multi_trace_call_chains_do_not_cross_independent_scenarios(self):
        from tools.atlas_doctor_lib.deep_intelligence import trace_observed_json_to_ui
        sha = "c" * 40
        graph = {"built_at_commit": sha, "nodes": [
            {"id": 1, "source_file": "app/core/reader.py"},
            {"id": 2, "source_file": "app/pages/home.py"}], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "truncated": False,
                 "events": [
                    {"type": "file_open", "source": "app/core/reader.py",
                     "target": "data/config.json", "_trace_group": 0},
                    {"type": "python_call_edge", "source": "app/pages/home.py",
                     "target": "app/core/reader.py", "_trace_group": 1},
                 ]}
        result = trace_observed_json_to_ui(graph, trace)
        self.assertEqual(result["json_opens_observed"], 1)
        self.assertEqual(result["references"][0]["ui_callers_in_same_trace"], [])

    def test_import_attempt_does_not_promote_failed_import_to_reachable(self):
        graph = {"built_at_commit": "f" * 40,
                 "nodes": [{"id": 1, "source_file": "main.py"},
                           {"id": 2, "source_file": "app/features/lazy.py"}],
                 "links": []}
        trace = {"candidate_sha": "f" * 40, "worktree_clean": True,
                 "truncated": False, "events": [
                     {"type": "import_attempt", "source": "main.py",
                      "module": "app.features.lazy"},
                 ]}
        report = graph_reachability(graph, ["main.py"], trace=trace)
        self.assertEqual(report["unreached_total"], 1)
        self.assertEqual(report["runtime_import_attempt_pairs"], 1)
        self.assertEqual(report["unreached_with_runtime_import_attempt"],
                         ["app/features/lazy.py"])
        self.assertFalse(report["proof_of_dead_code"])
        trace["worktree_clean"] = False
        self.assertEqual(graph_reachability(graph, ["main.py"], trace=trace)
                         ["runtime_import_attempt_pairs"], 0)


if __name__ == "__main__":
    unittest.main()
