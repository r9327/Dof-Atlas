from __future__ import annotations

import shutil
import subprocess
import unittest

from tools.atlas_doctor_lib.doctor_graph_ui import compact_graph, render_html


class DoctorGraphUiTests(unittest.TestCase):
    def test_history_overlay_marks_changed_imports_without_claiming_dead_code(self):
        graph = {
            "built_at_commit": "b" * 40,
            "nodes": [{"id": 1, "source_file": "app/a.py"},
                      {"id": 2, "source_file": "app/b.py"}],
            "links": [],
        }
        compare = {
            "baseline_sha": "a" * 40, "candidate_sha": "b" * 40,
            "status": "REVIEW",
            "new_import_file_pairs": [["app/a.py", "app/b.py"]],
            "removed_import_file_pairs": [["app/a.py", "app/old.py"]],
            "new_orphan_symbols": [{"path": "app/a.py", "symbol": "do", "origin": "ast"}],
            "new_weak_symbols": [],
        }
        output = compact_graph(graph, {}, comparison=compare)
        self.assertEqual(output["snapshot_diff"]["baseline_sha"], "a" * 40)
        self.assertEqual(output["nodes"][0]["snapshot_changes"]["added_imports"], ["app/b.py"])
        self.assertEqual(output["nodes"][0]["snapshot_changes"]["removed_imports"], ["app/old.py"])
        self.assertTrue(output["nodes"][0]["snapshot_changes"]["new_orphan"])
        self.assertIsNone(output["nodes"][1]["snapshot_changes"])
        html = render_html(output)
        self.assertIn("Changements depuis le graphe de référence", html)
        self.assertIn("Différences Graphify depuis la référence", html)
        self.assertIn("aucune preuve de régression ou de code mort", html)
        with self.assertRaisesRegex(ValueError, "does not match graph SHA"):
            compact_graph(graph, {}, comparison={**compare, "candidate_sha": "f" * 40})

    def test_snapshot_saves_exact_graph_without_rebuild_or_overwrite(self):
        import tempfile
        from pathlib import Path
        from tools.atlas_doctor_lib.doctor_graph_ui import save_graph_snapshot
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "graphify-out"
            output.mkdir()
            graph = output / "graph.json"
            graph.write_text('{"nodes":[{"id":1}],"links":[]}', encoding="utf-8")
            sha = "e" * 40
            saved = Path(save_graph_snapshot(root, graph, sha))
            self.assertEqual(saved.parent.name, "history")
            self.assertEqual(saved.name, sha + ".json")
            self.assertEqual(saved.read_bytes(), graph.read_bytes())
            self.assertEqual(save_graph_snapshot(root, graph, sha), str(saved))
            saved.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different contents"):
                save_graph_snapshot(root, graph, sha)
            with self.assertRaisesRegex(ValueError, "Full commit SHA"):
                save_graph_snapshot(root, graph, "short")

    def test_snapshot_baseline_is_bounded_to_graphify_out_and_read_only(self):
        import json
        import tempfile
        from pathlib import Path
        from tools.atlas_doctor_lib.doctor_graph_ui import load_snapshot_comparison
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "graphify-out"
            output.mkdir()
            prior = output / "previous.json"
            graph = {"built_at_commit": "b" * 40,
                     "nodes": [{"id": 1, "source_file": "app/main.py", "label": "main"}],
                     "links": []}
            prior.write_text(json.dumps({"built_at_commit": "a" * 40,
                                         "nodes": [{"id": 1, "source_file": "app/main.py",
                                                    "label": "main"}], "links": []}),
                             encoding="utf-8")
            report = load_snapshot_comparison(root, graph, prior)
            self.assertEqual(report["baseline_sha"], "a" * 40)
            self.assertEqual(report["candidate_sha"], "b" * 40)
            with self.assertRaisesRegex(ValueError, "under graphify-out"):
                load_snapshot_comparison(root, graph, root / "other.json")
            prior.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be an object"):
                load_snapshot_comparison(root, graph, prior)

    def test_snapshot_only_filter_is_opt_in_and_preserves_neighbor_discovery(self):
        graph = {
            "built_at_commit": "c" * 40,
            "nodes": [{"id": 1, "source_file": "app/a.py"},
                      {"id": 2, "source_file": "app/b.py"}],
            "links": [{"source": 1, "target": 2, "relation": "imports"}],
        }
        diff = {"baseline_sha": "b" * 40, "candidate_sha": "c" * 40,
                "new_import_file_pairs": [["app/a.py", "app/b.py"]],
                "removed_import_file_pairs": [],
                "new_orphan_symbols": [], "new_weak_symbols": []}
        report = compact_graph(graph, {}, comparison=diff)
        self.assertEqual(len(report["nodes"]), 2)
        self.assertEqual(len(report["edges"]), 1)
        page = render_html(report)
        for text in ('id="snapshotOnly"', "snapshotOnly.disabled=!snapshot",
                     "(!snapshotOnly.checked||!!n.snapshot_changes)",
                     "snapshotOnly.checked=false", "n.snapshot_changes?'#9bdf8b'"):
            self.assertIn(text, page)
        self.assertIsNone(compact_graph(graph, {})["snapshot_diff"])

    def test_interactive_view_has_real_navigation_and_filters(self):
        graph = {"nodes": [
            {"id": "a", "label": "guide", "source_file": "app/modules/encyclopedia/view.py", "community": 5},
            {"id": "b", "label": "db", "source_file": "app/core/db.py", "community": 5},
        ], "links": [{"source": "a", "target": "b", "relation": "imports"}],
                 "built_at_commit": "a" * 40}
        audit = {"orphan_nodes": [{"file": "app/core/db.py"}]}
        data = compact_graph(graph, audit)
        html = render_html(data)
        self.assertIn('id="search"', html)
        self.assertIn('id="domain"', html)
        self.assertIn("canvas.addEventListener('wheel'", html)
        self.assertIn("Doctor Atlas × Graphify", html)
        self.assertEqual(len(data["edges"]), 1)
        self.assertTrue(data["nodes"][1]["reasons"])
        self.assertFalse(data["truncated"])

    def test_pagination_retains_full_graph_and_global_neighbor_navigation(self):
        graph = {
            "nodes": [{"id": i, "source_file": f"app/{i}.py"} for i in range(2405)],
            "links": [{"source": 0, "target": 2404, "relation": "imports"}],
            "built_at_commit": "f" * 40,
        }
        data = compact_graph(graph, {})
        self.assertEqual(len(data["nodes"]), 2405)
        self.assertEqual(len(data["edges"]), 1)
        self.assertFalse(data["truncated"])
        html = render_html(data)
        for marker in (
            'id="graphPrev"', 'id="graphNext"', 'id="graphPage"',
            "const PAGE_SIZE=1200", "matches=nodes.map", "matches.slice(",
            "Math.floor(offset/PAGE_SIZE)", "button.addEventListener('click',()=>revealNode(e.n))",
            "button.addEventListener('click'", "relations de la page uniquement",
        ):
            self.assertTrue(marker in html, f"Expected Graphify UI marker: {marker}")
        self.assertIn("Page précédente du graphe", html)
        self.assertIn("Page suivante du graphe", html)

    def test_search_enter_and_neighbor_jump_center_the_real_selected_node(self):
        graph = {"built_at_commit": "a" * 40,
                 "nodes": [{"id": 1, "label": "node", "source_file": "app/a.py",
                            "source_location": "app/a.py:42:0"},
                           {"id": 2, "source_file": "app/b.py"}],
                 "links": [{"source": 1, "target": 2, "relation": "imports"}]}
        page = render_html(compact_graph(graph, {}))
        self.assertIn("function focusNode(i)", page)
        self.assertIn("panX=-loc.x;panY=-loc.y", page)
        self.assertIn("button.addEventListener('click',()=>revealNode(e.n))", page)
        self.assertIn("event.key==='Enter'", page)
        self.assertIn("focusNode(matches[0])", page)
        self.assertIn("const lineAnchor=locationMatch?'#L'", page)
        self.assertIn("app/a.py:42:0", page)

    def test_generated_interactive_javascript_passes_node_syntax_check(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js runtime unavailable for optional JS syntax validation")
        page = render_html(compact_graph({"nodes": [], "links": []}, {}))
        script = page.rsplit("<script>", 1)[1].split("</script>", 1)[0]
        result = subprocess.run(
            [node, "--check", "-"], input=script, text=True,
            capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_community_navigation_filters_global_nodes_without_deleting_them(self):
        graph = {
            "built_at_commit": "f" * 40,
            "nodes": [{"id": 1, "source_file": "app/a.py", "community": 2},
                      {"id": 2, "source_file": "app/b.py", "community": 200},
                      {"id": 3, "source_file": "app/c.py", "community": 2}],
            "links": [{"source": 1, "target": 2, "relation": "imports"}],
        }
        report = compact_graph(graph, {})
        page = render_html(report)
        self.assertEqual(len(report["nodes"]), 3)
        self.assertEqual(len(report["edges"]), 1)
        for fragment in ('id="community"', "communityCounts=new Map()",
                         "String(n.community)===cluster", "community.value=''",
                         "community.appendChild(option)", "numeric:true"):
            self.assertIn(fragment, page)
        self.assertNotIn('selectedCommunity = "', page)

    def test_cohesion_review_uses_existing_doctor_evidence_not_automatic_merges(self):
        graph = {
            "built_at_commit": "f" * 40,
            "nodes": [{"id": 1, "source_file": "app/a.py", "community": 9},
                      {"id": 2, "source_file": "app/b.py", "community": 9}],
            "links": [],
        }
        audit = {"community_cohesion": {"status": "REVIEW", "candidate_count": 1,
                 "candidates": [{"community": 9, "production_files": 2,
                                 "internal_extracted_edges": 1,
                                 "external_extracted_edges": 6,
                                 "classification": "LOW_INTERNAL_HIGH_EXTERNAL_GRAPH_COHESION_REVIEW",
                                 "automatic_merge": False}]}}
        data = compact_graph(graph, audit)
        self.assertEqual(data["community_review_total"], 1)
        self.assertEqual(len(data["community_review_candidates"]), 1)
        self.assertIs(data["community_review_candidates"][0]["automatic_merge"], False)
        self.assertNotIn("community_review", data["nodes"][0])
        page = render_html(data)
        self.assertIn("Frontières de communauté à examiner", page)
        self.assertIn("communityReview.has(id)", page)
        self.assertIn("ni fusion ni suppression automatique", page)

    def test_relation_filter_and_bounded_directed_dependency_path_are_interactive(self):
        graph = {"built_at_commit": "e" * 40,
                 "nodes": [{"id": "a", "source_file": "app/a.py"},
                           {"id": "b", "source_file": "app/b.py"},
                           {"id": "c", "source_file": "app/c.py"}],
                 "links": [{"source": "a", "target": "b", "relation": "imports"},
                           {"source": "b", "target": "c", "relation": "imports"}]}
        payload = compact_graph(graph, {})
        self.assertEqual(len(payload["nodes"]), 3)
        self.assertEqual(len(payload["edges"]), 2)
        html = render_html(payload)
        for marker in (
            'id="relation"', "const relationCounts=new Map()",
            "relation.value && e.relation!==relation.value",
            "edge.direction!=='out'", "function showGraphPath(from,to)",
            "depth.size>=4000", "distance>=8",
            "function revealNode(i)", "Définir comme départ du chemin",
            "Chercher les dépendances depuis", "Chemin de relations Graphify",
            "ce chemin ne prouve pas une exécution",
        ):
            self.assertIn(marker, html)

    def test_relation_filter_preserves_uncertainty_on_missing_paths(self):
        html = render_html(compact_graph({"nodes": [], "links": []}, {}))
        self.assertIn("Aucun chemin orienté trouvé dans ce graphe extrait", html)
        self.assertIn("Ce résultat ne prouve jamais du code mort", html)
        self.assertIn("Recherche partielle (8 sauts ou 4 000 nœuds)", html)
        self.assertIn("relation.addEventListener('change'", html)

    def test_reverse_consumer_inspection_is_bounded_and_advisory(self):
        graph = {
            "built_at_commit": "a" * 40,
            "nodes": [{"id": "core", "source_file": "app/core/a.py"},
                      {"id": "consumer", "source_file": "app/pages/b.py"}],
            "links": [{"source": "consumer", "target": "core", "relation": "imports"}],
        }
        html = render_html(compact_graph(graph, {}))
        for marker in (
            "Explorer les consommateurs (imports inverses)",
            "function showReverseImpact(source)",
            "edge.direction!=='in'",
            "['imports','imports_from'].includes(edge.relation)",
            "current.depth>=2",
            "seen.size>=2000",
            "Consommateurs possibles (imports inverses, 2 sauts maximum)",
            "Relations structurales uniquement",
            "button.addEventListener('click',()=>revealNode(row.node))",
        ):
            self.assertIn(marker, html)

    def test_review_category_filter_surfaces_isolates_hubs_workers_and_ast(self):
        graph = {"built_at_commit": "e" * 40,
                 "nodes": [{"id": 1, "source_file": "app/isolated.py"},
                           {"id": 2, "source_file": "app/hub.py"},
                           {"id": 3, "source_file": "app/ui.py"}], "links": []}
        audit = {
            "orphan_nodes": [{"file": "app/isolated.py"}],
            "high_fanout_files": [{"file": "app/hub.py"}],
            "isolated_communities": [{"sample_source_files": ["app/isolated.py"],
                                     "sample_linked_production_files": []}],
            "remediation_plan": {"tasks": [{"priority": "P2", "kind": "REVIEW",
                                           "action": "Inspect coupling",
                                           "paths": ["app/hub.py"]}]},
        }
        inspected = {"status": "REVIEW",
                     "paths_inspected": ["app/ui.py"],
                     "silent_exceptions": [{"path": "app/ui.py", "line": 7}],
                     "data_lineage_candidates": []}
        payload = compact_graph(graph, audit, inspection=inspected)
        self.assertEqual(payload["nodes"][0]["review_categories"], ["island", "orphan"])
        self.assertEqual(payload["nodes"][1]["review_categories"], ["doctor", "fanout"])
        self.assertEqual(payload["nodes"][2]["review_categories"], ["ast"])
        self.assertFalse(payload["truncated"])
        html = render_html(payload)
        for term in ('id="reviewKind"', "const reviewLabels=", "reviewCounts=new Map()",
                     "(n.review_categories||[]).includes(kind)", "reviewKind.value=''",
                     "Catégories de diagnostic à vérifier"):
            self.assertIn(term, html)
        self.assertIn("not proof of dead code", payload["disclaimer"])

    def test_file_removal_what_if_uses_static_file_imports_only(self):
        # Two importers of the same file, an indirect consumer and a runtime
        # edge. The interactive preview must keep all graph data read-only and
        # must not promote runtime events to import dependencies.
        graph = {"built_at_commit": "f" * 40,
                 "nodes": [
                     {"id": 1, "source_file": "app/source.py"},
                     {"id": 2, "source_file": "app/direct.py"},
                     {"id": 3, "source_file": "app/indirect.py"},
                     {"id": 4, "source_file": "app/runtime.py"},
                 ], "links": [
                     {"source": 2, "target": 1, "relation": "imports"},
                     {"source": 3, "target": 2, "relation": "imports_from"},
                 ]}
        data = compact_graph(graph, {})
        html = render_html(data)
        self.assertEqual(len(data["nodes"]), 4)
        self.assertEqual(len(data["edges"]), 2)
        for marker in (
            "const firstNodeByFile=new Map(), staticImporters=new Map()",
            "if(!['imports','imports_from'].includes(edge.relation)||edge.observed===true)",
            "function showFileRemovalPreview(file)",
            "showFileRemovalPreview(n.file)",
            "examinedEdges>4000||visited.size>=2000",
            "if(current.depth>=2)continue",
            "row.depth===1?'Direct : ':'Indirect : '",
            "button.addEventListener('click',()=>revealNode(index))",
            "Scénario hypothétique, lecture seule",
        ):
            self.assertIn(marker, html)
        self.assertIn("Simuler l’impact du retrait de ce fichier", html)
        self.assertNotIn("safe_to_delete", html)

    def test_node_evidence_can_be_downloaded_without_refactor_or_graph_rebuild(self):
        graph = {
            "built_at_commit": "d" * 40,
            "nodes": [{"id": 1, "label": "source", "source_file": "app/ui/source.py"},
                      {"id": 2, "label": "target", "source_file": "app/core/target.py"}],
            "links": [{"source": 1, "target": 2, "relation": "imports"}],
        }
        payload = compact_graph(graph, {})
        self.assertEqual(len(payload["edges"]), 1)
        html = render_html(payload)
        for snippet in (
            "Exporter les preuves Doctor de ce nœud (JSON)",
            "function buildNodeEvidence(i)", "function downloadNodeEvidence(i)",
            "schema_version:1,kind:'doctor_graph_node_evidence'",
            "relationships:{shown:direct,total:",
            "runtime_trace_status:data.trace_status",
            "limitations:[",
            "not proof of dead code or safe deletion",
            "const blob=new Blob([JSON.stringify(report,null,2)",
            "element.download='doctor-evidence-'",
            "URL.revokeObjectURL(url)",
        ):
            self.assertIn(snippet, html)
        self.assertNotIn("graph --rebuild", html)

    def test_prioritized_doctor_actions_are_actionable_but_review_only(self):
        graph = {"built_at_commit": "a" * 40,
                 "nodes": [{"id": 1, "source_file": "app/a.py"}], "links": []}
        audit = {"remediation_plan": {"tasks": [
            {"priority": "P3", "kind": "HIGH_FANOUT_REVIEW",
             "paths": ["app/a.py"], "action": "Review coupling"},
            {"priority": "P0", "kind": "PROVEN_IMPORT_INVERSION",
             "paths": ["app/a.py"], "action": "Fix verified inverted import"},
        ]}}
        report = compact_graph(graph, audit)
        self.assertEqual(report["nodes"][0]["doctor_task"]["priority"], "P0")
        self.assertIn("Fix verified inverted import", report["nodes"][0]["doctor_task"]["action"])
        html = render_html(report)
        self.assertIn('id="priority"', html)
        self.assertIn("correction automatique", html)

    def test_source_inspection_overlays_real_bounded_ast_findings(self):
        graph = {"nodes": [
            {"id": 1, "source_file": "app/core/catalog.py"},
            {"id": 2, "source_file": "app/pages/home.py"},
        ], "links": [], "built_at_commit": "a" * 40}
        inspection = {
            "status": "REVIEW", "paths_inspected": ["app/core/catalog.py"],
            "missing_internal_import_candidates": [
                {"path": "app/core/catalog.py", "line": 8,
                 "module": "app.core.progress_coordinator"},
            ],
            "data_lineage_candidates": [
                {"path": "app/core/catalog.py", "line": 10,
                 "data_reference": "data/catalog.json"},
            ],
            "silent_exceptions": [], "near_duplicate_candidates": [],
        }
        result = compact_graph(graph, {}, inspection=inspection)
        evidence = result["nodes"][0]["source_evidence"]
        self.assertEqual(len(evidence), 2)
        self.assertEqual(evidence[0]["subject"], "app.core.progress_coordinator")
        self.assertEqual(evidence[1]["kind"], "Literal JSON string reference")
        self.assertEqual(result["nodes"][1]["source_evidence"], [])
        self.assertEqual(result["source_inspection_status"], "REVIEW")
        self.assertEqual(result["source_inspection_files"], 1)
        self.assertIn("Indices AST du fichier", render_html(result))
        self.assertIn("n.source_evidence.length", render_html(result))

    def test_json_to_ui_review_evidence_is_visible_on_candidate_view_node(self):
        graph = {"nodes": [
            {"id": 1, "source_file": "app/core/catalog.py"},
            {"id": 2, "source_file": "app/pages/catalog_page.py"},
        ], "links": [], "built_at_commit": "a" * 40}
        lineage = {"references_with_ui_importers": 1, "references": [{
            "source": "app/core/catalog.py", "data_reference": "data/catalog.json",
            "possible_ui_importers": [{"path": "app/pages/catalog_page.py",
                                       "import_hops": 1}],
        }]}
        report = compact_graph(graph, {}, lineage=lineage)
        self.assertEqual(report["json_lineage_review_leads"], 1)
        self.assertFalse(report["json_lineage_runtime_proven"])
        self.assertEqual(report["nodes"][1]["source_evidence"][0]["kind"],
                         "Possible JSON reference via import chain")
        self.assertEqual(report["nodes"][0]["source_evidence"], [])

    def test_graph_is_populated_on_first_open_and_renders_only_per_frame(self):
        payload = compact_graph({"nodes": [{"id": 1, "source_file": "app/a.py"}],
                                 "links": []}, {})
        html = render_html(payload)
        self.assertIn("window.addEventListener('resize',fit);filter();fit();", html)
        self.assertIn("requestAnimationFrame(()=>{drawScheduled=false;paint()})", html)
        self.assertIn("if(drawScheduled)return", html)
        self.assertIn("n.source_evidence.length", html)
        self.assertNotIn("setInterval(refreshLive,2500)", html)

    def test_unscanned_graph_nodes_do_not_inherit_ast_findings(self):
        graph = {"nodes": [{"id": 1, "source_file": "app/a.py"}], "links": []}
        result = compact_graph(graph, {})
        self.assertEqual(result["source_inspection_status"], "NOT_RUN")
        self.assertEqual(result["nodes"][0]["source_evidence"], [])

    def test_matching_runtime_trace_adds_observed_calls_without_faking_imports(self):
        sha = "a" * 40
        graph = {"nodes": [{"id": 1, "source_file": "app/a.py"},
                           {"id": 2, "source_file": "app/b.py"}],
                 "links": [], "built_at_commit": sha}
        trace = {"candidate_sha": sha, "worktree_clean": True, "events": [
            {"type": "python_call_edge", "source": "app/a.py", "target": "app/b.py"}
        ]}
        payload = compact_graph(graph, {}, trace)
        self.assertEqual(payload["trace_status"], "MATCHED")
        self.assertEqual(payload["edges"][0]["relation"], "OBSERVED_PYTHON_CALL")
        self.assertTrue(payload["nodes"][0]["runtime_observed"])
        trace["worktree_clean"] = False
        self.assertEqual(compact_graph(graph, {}, trace)["trace_status"], "STALE_OR_INCOMPLETE")
        self.assertEqual(compact_graph(graph, {}, trace)["edges"], [])
        trace["worktree_clean"] = True
        trace["candidate_sha"] = "b" * 40
        self.assertEqual(compact_graph(graph, {}, trace)["trace_status"], "STALE_OR_INCOMPLETE")
        self.assertEqual(compact_graph(graph, {}, trace)["edges"], [])

    def test_lifecycle_ui_evidence_requires_same_complete_clean_sha(self):
        sha = "b" * 40
        graph = {"built_at_commit": sha, "nodes": [
            {"id": 1, "source_file": "app/worker.py"},
            {"id": 2, "source_file": "app/cache.py"},
        ], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "truncated": False,
                 "events": [
                     {"type": "worker_start", "source": "app/worker.py"},
                     {"type": "cache_release", "source": "app/cache.py"},
                 ]}
        data = compact_graph(graph, {}, trace)
        self.assertEqual(data["trace_status"], "MATCHED")
        self.assertTrue(data["nodes"][0]["worker_start_unpaired_at_trace_end"])
        self.assertTrue(data["nodes"][1]["cache_release_observed"])
        self.assertFalse(data["observed_lifecycle"]["proof_of_memory_leak"])
        trace["candidate_sha"] = "c" * 40
        stale = compact_graph(graph, {}, trace)
        self.assertEqual(stale["observed_lifecycle"]["status"], "NOT_TRUSTED")
        self.assertFalse(stale["nodes"][0]["worker_start_unpaired_at_trace_end"])

    def test_malformed_runtime_events_cannot_crash_graph_ui(self):
        sha = "d" * 40
        graph = {"built_at_commit": sha, "nodes": [], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True,
                 "truncated": False, "events": [None]}
        data = compact_graph(graph, {}, trace)
        self.assertEqual(data["trace_status"], "STALE_OR_INCOMPLETE")
        self.assertEqual(data["observed_lifecycle"]["status"], "NOT_TRUSTED")
        unexpected = compact_graph(graph, {}, trace=["not", "a", "trace"])
        self.assertEqual(unexpected["trace_status"], "STALE_OR_INCOMPLETE")
        self.assertEqual(unexpected["observed_lifecycle"]["status"], "NOT_TRUSTED")

    def test_legacy_runtime_trace_without_cleanliness_is_not_trusted(self):
        sha = "c" * 40
        graph = {"nodes": [{"id": 1, "source_file": "app/a.py"},
                           {"id": 2, "source_file": "app/b.py"}],
                 "links": [], "built_at_commit": sha}
        trace = {"candidate_sha": sha, "events": [
            {"type": "python_call_edge", "source": "app/a.py", "target": "app/b.py"}
        ]}
        result = compact_graph(graph, {}, trace)
        self.assertEqual(result["trace_status"], "STALE_OR_INCOMPLETE")
        self.assertEqual(result["observed_runtime_file_pairs"], 0)

    def test_instrumented_qt_connection_has_separate_non_invocation_edge(self):
        sha = "d" * 40
        graph = {"built_at_commit": sha,
                 "nodes": [{"id": 1, "source_file": "app/signal.py"},
                           {"id": 2, "source_file": "app/slot.py"}],
                 "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "events": [{
            "type": "qt_signal_connect_returned", "source": "app/signal.py",
            "target": "app/slot.py",
            "confidence": "CONNECT_RETURNED_NOT_CALLBACK_INVOKED",
        }]}
        payload = compact_graph(graph, {}, trace)
        self.assertEqual(payload["trace_status"], "MATCHED")
        self.assertEqual(payload["edges"][0]["relation"], "QT_CONNECT_RETURNED")
        self.assertTrue(payload["nodes"][1]["qt_connection_observed"])
        self.assertFalse(payload["nodes"][1]["runtime_observed"])
        trace["worktree_clean"] = False
        self.assertEqual(compact_graph(graph, {}, trace)["edges"], [])


    def test_qt_invocations_have_distinct_graph_edges_and_export_evidence(self):
        sha = "e" * 40
        graph = {"built_at_commit": sha,
                 "nodes": [{"id": 1, "source_file": "app/signal.py"},
                           {"id": 2, "source_file": "app/slot.py"}], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "truncated": False,
                 "events": [
                     {"type": "qt_signal_connect_returned",
                      "source": "app/signal.py", "target": "app/slot.py"},
                     {"type": "qt_callback_invoked", "source": "app/signal.py",
                      "target": "app/slot.py", "confidence": "WRAPPED_PYTHON_CALLBACK_ENTERED"},
                 ]}
        data = compact_graph(graph, {}, trace)
        self.assertEqual(data["observed_qt_callback_file_pairs"], 1)
        self.assertTrue(data["nodes"][1]["qt_callback_invoked_observed"])
        self.assertEqual([x["relation"] for x in data["edges"]],
                         ["QT_CONNECT_RETURNED", "QT_CALLBACK_INVOKED"])
        html = render_html(data)
        self.assertIn("Callback Python Qt entré", html)
        self.assertIn("qt_callback_invoked_observed:!!n.qt_callback_invoked_observed", html)
        trace["worktree_clean"] = False
        stale = compact_graph(graph, {}, trace)
        self.assertEqual(stale["observed_qt_callback_file_pairs"], 0)
        self.assertEqual(stale["edges"], [])

    def test_qt_callback_without_provenance_is_not_graph_evidence(self):
        sha = "f" * 40
        graph = {"built_at_commit": sha,
                 "nodes": [{"id": 1, "source_file": "app/a.py"},
                           {"id": 2, "source_file": "app/b.py"}], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "events": [
            {"type": "qt_callback_invoked", "source": "app/a.py",
             "target": "app/b.py", "confidence": "CALL_SITE_ONLY"}
        ]}
        data = compact_graph(graph, {}, trace)
        self.assertEqual(data["observed_qt_callback_file_pairs"], 0)
        self.assertEqual(data["edges"], [])

    def test_symbol_observations_are_opt_in_positive_evidence_only(self):
        sha = "f" * 40
        graph = {"built_at_commit": sha,
                 "nodes": [{"id": 1, "source_file": "app/a.py"},
                           {"id": 2, "source_file": "app/b.py"}], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "events": [{
            "type": "python_symbol_call", "source": "app/a.py",
            "target": "app/b.py", "caller_symbol": "send",
            "callee_symbol": "receive", "caller_line": 10, "callee_line": 30,
            "confidence": "OBSERVED_CALL_ENTRY",
        }]}
        result = compact_graph(graph, {}, trace)
        self.assertEqual(len(result["observed_symbol_calls"]), 1)
        self.assertEqual(result["observed_symbol_calls"][0]["callee_symbol"], "receive")
        self.assertIn("Appels de fonctions observés", render_html(result))
        trace["worktree_clean"] = False
        self.assertEqual(compact_graph(graph, {}, trace)["observed_symbol_calls"], [])

    def test_abbreviated_graph_sha_cannot_certify_runtime_edges(self):
        graph = {"nodes": [{"id": 1, "source_file": "app/a.py"},
                           {"id": 2, "source_file": "app/b.py"}],
                 "links": [], "built_at_commit": "a" * 7}
        trace = {"candidate_sha": "a" * 40, "worktree_clean": True, "events": [
            {"type": "python_call_edge", "source": "app/a.py", "target": "app/b.py"}
        ]}
        result = compact_graph(graph, {}, trace)
        self.assertEqual(result["trace_status"], "STALE_OR_INCOMPLETE")
        self.assertEqual(result["edges"], [])

    def test_live_uses_focus_events_not_periodic_git_polling(self):
        html = render_html(compact_graph({"nodes": [], "links": []}, {}))
        self.assertIn("addEventListener('focus'", html)
        self.assertIn("visibilitychange", html)
        self.assertIn('id="refreshGit"', html)
        self.assertNotIn("setInterval(refreshLive,2500)", html)
        self.assertIn("/api/ping", html)

    def test_can_open_historical_graph_read_only_without_source_confirmed_findings(self):
        import json
        import subprocess
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from tools.atlas_doctor_lib.doctor_graph_ui import export_interactive_graph
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Atlas"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "doctor@example.invalid"], cwd=root, check=True)
            (root / "main.py").write_text("pass\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            folder = root / "graphify-out"
            folder.mkdir()
            path = folder / "graph.json"
            path.write_text(json.dumps({
                "nodes": [{"id": "a", "source_file": "main.py", "label": "main", "community": 0}],
                "links": [], "built_at_commit": sha,
            }))
            evidence = {"status": "STALE", "graph": str(path), "git": {"head": sha}}
            with patch("tools.atlas_doctor_lib.architecture.graph_status", return_value=evidence):
                self.assertEqual(export_interactive_graph(root)["status"], "BLOCKED")
                result = export_interactive_graph(root, allow_stale=True)
            self.assertEqual(result["status"], "REVIEW")
            self.assertEqual(result["candidate_sha"], sha)
            self.assertEqual(result["graph_status"], "STALE")
            self.assertTrue((folder / "doctor_graph.html").is_file())

    def test_full_real_graph_budget_keeps_all_11366_nodes_and_33269_edges(self):
        from tools.atlas_doctor_lib.doctor_graph_ui import MAX_NODES, MAX_LINKS
        self.assertGreaterEqual(MAX_NODES, 11366)
        self.assertGreaterEqual(MAX_LINKS, 33269)
        nodes = [{"id": i, "source_file": "app/ui/sample.py"} for i in range(11366)]
        links = [{"source": i, "target": i+1, "relation": "uses"} for i in range(11365)]
        payload = compact_graph({"nodes": nodes, "links": links}, {})
        self.assertFalse(payload["truncated"])
        self.assertEqual(len(payload["nodes"]), 11366)
        self.assertEqual(len(payload["edges"]), 11365)

    def test_file_coverage_panel_is_read_only_and_escapes_file_names(self):
        from tools.atlas_doctor_lib.doctor_graph_ui import render_html
        graph = {"nodes": [], "edges": [], "candidate_sha": "a" * 40,
                 "file_coverage": {"tracked": 2, "represented": 1, "missing_total": 1,
                                   "missing_examples": ["app/<missing>.py"],
                                   "status": "HISTORICAL", "runtime_proof": False}}
        html = render_html(graph)
        self.assertIn("coverageDetails", html)
        self.assertIn("Fichiers Python couverts", html)
        self.assertIn("Pas une preuve de code utilisé ou mort", html)
        self.assertNotIn("app/<missing>.py", html)
        self.assertIn("app/\\u003cmissing\\u003e.py", html)

    def test_community_island_marks_files_without_claiming_dead_code(self):
        graph = {"nodes": [{"id": 1, "source_file": "app/widget.py", "label": "Widget"}],
                 "links": []}
        report = {"isolated_communities": [{
            "sample_source_files": ["app/widget.py"],
            "sample_linked_production_files": ["app/widget.py"],
        }]}
        data = compact_graph(graph, report)
        self.assertIn("file linked elsewhere", data["nodes"][0]["reasons"][0])
        self.assertIn("not proof of dead code", data["disclaimer"])

    def test_labels_cannot_escape_json_script(self):
        graph = {"nodes": [{"id": 1, "label": "</script><img src=x onerror=alert(1)>",
                            "source_file": "app/x.py"}], "links": []}
        html = render_html(compact_graph(graph, {}))
        self.assertNotIn("</script><img", html)
        self.assertIn("\\u003c", html)


if __name__ == "__main__":
    unittest.main()
