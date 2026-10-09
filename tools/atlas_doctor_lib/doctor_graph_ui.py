from __future__ import annotations

"""Doctor overlay on the *existing* exact-SHA Graphify export.

An independent local HTML viewer; no server, CDN, Qt runtime or graph rebuild.
"""
from collections import defaultdict
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

MAX_NODES = 15000
MAX_LINKS = 50000
MAX_SOURCE_INSPECTION_FILES = 16
MAX_SOURCE_SIGNALS_PER_FILE = 6


def _domain(path: str) -> str:
    parts = path.split("/")
    if len(parts) > 3 and parts[:2] == ["app", "modules"]:
        return "/".join(parts[:3])
    return "/".join(parts[:2]) if len(parts) > 1 else path


def compact_graph(graph: dict[str, Any], audit: dict[str, Any],
                  trace: dict[str, Any] | None = None,
                  inspection: dict[str, Any] | None = None,
                  lineage: dict[str, Any] | None = None,
                  comparison: dict[str, Any] | None = None,
                  historical_trend: dict[str, Any] | None = None,
                  focused_impact: dict[str, Any] | None = None) -> dict[str, Any]:
    nodes = graph.get("nodes", [])[:MAX_NODES]
    indexed = {item["id"]: number for number, item in enumerate(nodes)}
    # Stable source-file comparisons, never match ephemeral Leiden community IDs.
    source_changes: dict[str, dict[str, Any]] = {}
    if comparison is not None:
        if comparison.get("candidate_sha") != graph.get("built_at_commit"):
            raise ValueError("Baseline comparison does not match graph SHA")
        def change(path: str) -> dict[str, Any]:
            return source_changes.setdefault(path, {
                "added_imports": [], "removed_imports": [],
                "new_orphan": False, "new_weak": False,
            })
        for field, kind in (("new_import_file_pairs", "added_imports"),
                            ("removed_import_file_pairs", "removed_imports")):
            for pair in comparison.get(field, [])[:80]:
                if isinstance(pair, (list, tuple)) and len(pair) == 2 and all(
                    isinstance(value, str) for value in pair
                ):
                    change(pair[0])[kind].append(pair[1])
        for field, kind in (("new_orphan_symbols", "new_orphan"),
                            ("new_weak_symbols", "new_weak")):
            for item in comparison.get(field, [])[:80]:
                if isinstance(item, dict) and isinstance(item.get("path"), str):
                    change(item["path"])[kind] = True
    file_reasons: dict[str, list[str]] = {}
    review_by_file: dict[str, set[str]] = {}
    if isinstance(historical_trend, dict):
        # These are historical observations from the same scenario, NOT proof
        # of a regression in the current Git tree.
        for finding in historical_trend.get("candidates", [])[:80]:
            if not isinstance(finding, dict):
                continue
            for path in (finding.get("source"), finding.get("target")):
                if not isinstance(path, str) or not path.endswith(".py"):
                    continue
                reason = ("Repeated historical absence; scenario review needed"
                          if finding.get("classification") == "REPEATED_ABSENCE_REVIEW"
                          else "Historical observation difference; not proven regression")
                reasons = file_reasons.setdefault(path, [])
                if reason not in reasons:
                    reasons.append(reason)
                review_by_file.setdefault(path, set()).add("history")
    for field, reason, category in (

        ("orphan_nodes", "Isolated Graphify node; not proof of dead code", "orphan"),
        ("weak_production_candidates", "Weakly connected candidate", "weak"),
        ("high_fanout_files", "High fanout coupling candidate", "fanout"),
        ("blocking_findings", "Doctor source-confirmed forbidden dependency", "forbidden"),
    ):
        for item in audit.get(field, []):
            path = item.get("file") or item.get("path") or item.get("source")
            if isinstance(path, str):
                values = file_reasons.setdefault(path, [])
                if reason not in values:
                    values.append(reason)
                review_by_file.setdefault(path, set()).add(category)
    for community in audit.get("isolated_communities", []):
        # A disconnected community does not imply its containing Python file
        # lacks imports/calls from other communities. Make this explicit.
        linked = set(community.get("sample_linked_production_files", []))
        for path in community.get("sample_source_files", [])[:8]:
            if not isinstance(path, str) or not path.startswith("app/"):
                continue
            reason = ("Graphify subcommunity isolated; file linked elsewhere"
                      if path in linked else
                      "Graphify subcommunity isolated; file reachability unproven")
            values = file_reasons.setdefault(path, [])
            if reason not in values:
                values.append(reason)
            review_by_file.setdefault(path, set()).add("island")
    # Show exact source-file consumers only when a developer explicitly
    # requests focused analysis. Runtime imports remain review leads.
    focus_consumers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if isinstance(focused_impact, dict):
        for target in focused_impact.get("changed_files", [])[:8]:
            review_by_file.setdefault(target, set()).add("focus")
            reasons = file_reasons.setdefault(target, [])
            reasons.append("Explicit source impact investigation (not proof of dead code)")
        for edge in focused_impact.get("import_evidence", [])[:160]:
            if not isinstance(edge, dict):
                continue
            target, importer = edge.get("imported"), edge.get("importer")
            if isinstance(target, str) and isinstance(importer, str):
                review_by_file.setdefault(importer, set()).add("consumer")
                focus_consumers[target].append({
                    "path": importer, "line": edge.get("line"),
                    "depth": edge.get("depth"), "kind": "SOURCE_STATIC_IMPORT",
                })
        for edge in focused_impact.get("literal_dynamic_import_candidates", [])[:160]:
            if not isinstance(edge, dict):
                continue
            target, importer = edge.get("imported"), edge.get("importer")
            if isinstance(target, str) and isinstance(importer, str):
                review_by_file.setdefault(importer, set()).add("dynamic")
                focus_consumers[target].append({
                    "path": importer, "line": edge.get("line"),
                    "depth": 1, "kind": "LITERAL_IMPORT_CALL_UNEXECUTED",
                })
    # Expose Doctor's existing prioritized remediation plan in the graph
    # inspector, without promoting speculative candidate findings to P0.
    priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    file_actions: dict[str, dict[str, str]] = {}
    for task in (audit.get("remediation_plan") or {}).get("tasks", []):
        level = task.get("priority")
        if level not in priority_rank:
            continue
        for source_path in task.get("paths", [])[:20]:
            if not isinstance(source_path, str):
                continue
            before = file_actions.get(source_path)
            if before is None or priority_rank[level] < priority_rank[before["priority"]]:
                file_actions[source_path] = {
                    "priority": level, "kind": str(task.get("kind") or ""),
                    "action": str(task.get("action") or ""),
                }
    # Read-only AST source evidence is separate from Graphify predictions and
    # runtime observations. Only explicitly scanned files can show findings.
    source_evidence: dict[str, list[dict[str, Any]]] = {}
    if isinstance(inspection, dict):
        def add(path: Any, line: Any, kind: str, subject: Any) -> None:
            if not isinstance(path, str):
                return
            bucket = source_evidence.setdefault(path, [])
            if len(bucket) < MAX_SOURCE_SIGNALS_PER_FILE:
                bucket.append({"line": str(line or ""), "kind": kind,
                               "subject": str(subject or "")[:180],
                               "confidence": "STATIC_SOURCE_REVIEW_ONLY"})
        # Show bounded Doctor resource/caching hints in the existing inspector.
        resource_scan = inspection.get("resource_lifecycle") or {}
        for item in resource_scan.get("findings", [])[:80]:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if not isinstance(path, str):
                continue
            is_cache = item.get("kind") == "UNBOUNDED_CACHE_CANDIDATE"
            category = "cache" if is_cache else "resource"
            reason = ("Potentially unbounded cache, source review only" if is_cache
                      else "Qt/WebEngine resource, native lifetime unproven")
            review_by_file.setdefault(path, set()).add(category)
            reasons = file_reasons.setdefault(path, [])
            if reason not in reasons:
                reasons.append(reason)
            add(path, item.get("line"), reason,
                item.get("symbol") if is_cache else item.get("qt_type"))
        for key, kind in (
            ("missing_internal_import_candidates", "Missing internal import candidate"),
            ("silent_exceptions", "Swallowed exception pattern"),
            ("data_lineage_candidates", "Literal JSON string reference"),
        ):
            for item in inspection.get(key, [])[:80]:
                if isinstance(item, dict):
                    add(item.get("path"), item.get("line"), kind,
                        item.get("module") or item.get("data_reference") or "")
        for group in inspection.get("near_duplicate_candidates", [])[:80]:
            if isinstance(group, dict):
                for item in group.get("occurrences", [])[:16]:
                    if isinstance(item, dict):
                        add(item.get("path"), item.get("line"),
                            "Similar AST shape (not semantic equality)", item.get("symbol"))
    if isinstance(lineage, dict):
        for entry in lineage.get("references", [])[:80]:
            if not isinstance(entry, dict):
                continue
            path = entry.get("source")
            label = entry.get("data_reference")
            for ui in entry.get("possible_ui_importers", [])[:8]:
                if not isinstance(ui, dict):
                    continue
                ui_path = ui.get("path")
                if not isinstance(ui_path, str):
                    continue
                existing = source_evidence.setdefault(ui_path, [])
                if len(existing) >= MAX_SOURCE_SIGNALS_PER_FILE:
                    continue
                existing.append({
                    "line": "", "kind": "Possible JSON reference via import chain",
                    "subject": f"{path} : {label}"[:180],
                    "confidence": "STATIC_IMPORT_PATH_NOT_RUNTIME_FLOW",
                })
    trace_status = "NOT_PROVIDED"
    runtime_pairs: set[tuple[str, str]] = set()
    observed_lifecycle: dict[str, Any] = {"status": "NOT_TRUSTED"}
    observed_performance: dict[str, Any] = {"status": "NOT_PROVIDED", "samples": [],
                                            "comparisons": [], "peak_rss_proven": False}
    trace_events = trace.get("events") if isinstance(trace, dict) else None
    if isinstance(trace, dict):
        trace_sha = trace.get("candidate_sha")
        graph_sha = graph.get("built_at_commit")
        if (isinstance(trace_sha, str) and isinstance(graph_sha, str)
                and len(graph_sha) == 40 and trace_sha == graph_sha
                and trace.get("worktree_clean") is True
                and not trace.get("truncated")
                and isinstance(trace_events, list) and len(trace_events) <= 50000
                and all(isinstance(row, dict) for row in trace_events)):
            trace_status = "MATCHED"
            from .runtime_observation import summarize_runtime_lifecycle
            observed_lifecycle = summarize_runtime_lifecycle(trace)
            from .runtime_observation import summarize_process_checkpoints
            observed_performance = summarize_process_checkpoints(trace)
            runtime_pairs = {
                (row["source"], row["target"])
                for row in trace.get("events", [])
                if row.get("type") == "python_call_edge"
                and isinstance(row.get("source"), str)
                and isinstance(row.get("target"), str)
            }
        else:
            trace_status = "STALE_OR_INCOMPLETE"
    elif trace is not None:
        trace_status = "STALE_OR_INCOMPLETE"
    qt_pairs: set[tuple[str, str]] = set()
    if trace_status == "MATCHED" and trace is not None:
        qt_pairs = {
            (row["source"], row["target"])
            for row in trace.get("events", [])
            if row.get("type") == "qt_signal_connect_returned"
            and isinstance(row.get("source"), str)
            and isinstance(row.get("target"), str)
        }
    invoked_qt_pairs: set[tuple[str, str]] = set()
    if trace_status == "MATCHED" and trace is not None:
        invoked_qt_pairs = {
            (row["source"], row["target"])
            for row in trace.get("events", [])
            if row.get("type") == "qt_callback_invoked"
            and row.get("confidence") == "WRAPPED_PYTHON_CALLBACK_ENTERED"
            and isinstance(row.get("source"), str)
            and isinstance(row.get("target"), str)
        }
    # Dynamic module import attempts are scenario observations, not successful imports.
    runtime_import_pairs: set[tuple[str, str]] = set()
    runtime_imports_truncated = False
    if trace_status == "MATCHED" and trace is not None:
        represented_files = {row.get("source_file") for row in nodes}
        for event in trace.get("events", []):
            if event.get("type") != "import_attempt":
                continue
            source, module = event.get("source"), event.get("module")
            if not isinstance(source, str) or source not in represented_files or not isinstance(module, str):
                continue
            if not module or not all(part.isidentifier() for part in module.split(".")):
                continue
            relative = module.replace(".", "/")
            target = next((path for path in (relative + ".py", relative + "/__init__.py")
                           if path in represented_files and path != source), None)
            if target:
                if len(runtime_import_pairs) >= 256:
                    runtime_imports_truncated = True
                    continue
                runtime_import_pairs.add((source, target))
    # A genuine return from explicit importlib.import_module is stronger
    # evidence than an attempted import, but not proof of fresh execution.
    returned_import_pairs: set[tuple[str, str]] = set()
    if trace_status == "MATCHED" and trace is not None:
        represented = {row.get("source_file") for row in nodes}
        returned_import_pairs = {
            (row["source"], row["target"])
            for row in trace.get("events", [])[:50000]
            if row.get("type") == "module_import_returned"
            and row.get("confidence") == "IMPORTLIB_RETURNED_REPOSITORY_MODULE"
            and isinstance(row.get("source"), str)
            and isinstance(row.get("target"), str)
            and row["source"] in represented and row["target"] in represented
            and row["source"] != row["target"]
        }
    symbol_calls: list[dict[str, Any]] = []
    if trace_status == "MATCHED" and trace is not None:
        symbol_calls = [
            {field: row[field] for field in (
                "source", "target", "caller_symbol", "callee_symbol",
                "caller_line", "callee_line", "confidence",
            ) if field in row}
            for row in trace.get("events", [])
            if row.get("type") == "python_symbol_call"
            and isinstance(row.get("source"), str)
            and isinstance(row.get("target"), str)
        ][:384]
    open_worker_files = {row["source"] for row in observed_lifecycle.get("worker_starts_unpaired", [])}
    open_qt_worker_files = {row["source"] for row in observed_lifecycle.get("qt_worker_unpaired", [])}
    cache_released_files = set(observed_lifecycle.get("cache_release_sources", []))
    qt_destroyed_files = set(observed_lifecycle.get("qt_destroyed_sources", []))
    qt_pending_destroy_files = {row["source"] for row in observed_lifecycle.get("qt_destroy_watches_pending", [])}
    runtime_scenarios_by_file: dict[str, set[str]] = defaultdict(set)
    scenario_names: list[str] = []
    if trace_status == "MATCHED" and isinstance(trace, dict):
        raw_names = trace.get("scenario_modules")
        if isinstance(raw_names, list):
            scenario_names = [name for name in raw_names if isinstance(name, str) and len(name) <= 120][:8]
        if not scenario_names:
            single = trace.get("scenario_module")
            scenario_names = [single] if isinstance(single, str) and len(single) <= 120 else ["Trace 1"]
        # Every emitted event keeps its originating scenario. Do not assign a
        # JSON decode to another scenario sharing the same token.
        for row in trace.get("events", []):
            group = row.get("_trace_group", 0)
            if not isinstance(group, int) or isinstance(group, bool) or not 0 <= group < 8:
                continue
            label = f"Scénario {group + 1}"
            from .scenario_coverage import observed_executing_python_files
            for file in observed_executing_python_files(row):
                runtime_scenarios_by_file[file].add(label)
    native_invalid_by_file: dict[str, int] = {}
    if trace_status == "MATCHED" and trace is not None:
        for event in trace.get("events", []):
            count = event.get("native_invalid_wrappers")
            source = event.get("source")
            if (event.get("type") == "qt_native_snapshot"
                    and event.get("status") == "OBSERVED"
                    and isinstance(source, str)
                    and isinstance(count, int) and not isinstance(count, bool)
                    and 0 < count <= 128):
                native_invalid_by_file[source] = max(native_invalid_by_file.get(source, 0), count)
    observed_files = {file for pair in runtime_pairs for file in pair}
    qt_files = {file for pair in qt_pairs for file in pair}
    qt_invoked_files = {file for pair in invoked_qt_pairs for file in pair}
    dynamic_import_files = {file for pair in runtime_import_pairs for file in pair}
    returned_import_files = {file for pair in returned_import_pairs for file in pair}
    qt_sites: set[str] = set()
    if trace_status == "MATCHED" and trace is not None:
        qt_sites = {row["source"] for row in trace.get("events", [])
                    if row.get("type") == "qt_c_call_site"
                    and isinstance(row.get("source"), str)}
    # Runtime JSON opens plus observed caller paths are not proof of data flow.
    json_runtime_by_file: dict[str, list[dict[str, str]]] = {}
    json_runtime_summary: dict[str, Any] = {"status": "NOT_TRUSTED", "json_opens_observed": 0}
    if trace_status == "MATCHED" and trace is not None:
        from .deep_intelligence import trace_observed_json_to_ui
        json_runtime_summary = trace_observed_json_to_ui(graph, trace)
        for entry in json_runtime_summary.get("references", []):
            source, json_path = entry.get("opening_source"), entry.get("json_path")
            if not isinstance(source, str) or not isinstance(json_path, str):
                continue
            sources = [(source, "JSON_OPEN_OBSERVED")]
            sources.extend((row["path"], "CO_OBSERVED_PYTHON_CALL_CHAIN")
                           for row in entry.get("ui_callers_in_same_trace", [])
                           if isinstance(row, dict) and isinstance(row.get("path"), str))
            for path, kind in sources:
                bucket = json_runtime_by_file.setdefault(path, [])
                if len(bucket) < 6:
                    bucket.append({"json_path": json_path, "opening_source": source,
                                   "kind": kind, "confidence": "OBSERVATION_NOT_DATA_FLOW"})
    # Exact-SHA opt-in decoded JSON -> explicit Python UI-binding evidence.
    json_bindings_by_file: dict[str, list[dict[str, Any]]] = {}
    bindings_summary: dict[str, Any] = {"status": "NOT_TRUSTED", "bound_to_ui": 0}
    if trace_status == "MATCHED" and trace is not None:
        from .deep_intelligence import trace_explicit_json_bindings
        bindings_summary = trace_explicit_json_bindings(graph, trace)
        for row in bindings_summary.get("bindings", []):
            for path in (row["reader"], row["ui_file"]):
                selected_rows = json_bindings_by_file.setdefault(path, [])
                if len(selected_rows) < 6:
                    selected_rows.append(row)
    # Existing source-backed community cohesion audit is advisory. Store it
    # once per community, never duplicate the same row for every symbol node.
    cohesion = audit.get("community_cohesion") or {}
    boundary_rows = cohesion.get("candidates", []) if isinstance(cohesion, dict) else []
    community_reviews = [
        {key: row[key] for key in (
            "community", "production_files", "internal_extracted_edges",
            "external_extracted_edges", "classification", "automatic_merge"
        ) if key in row}
        for row in boundary_rows[:80] if isinstance(row, dict)
    ]
    selected = []
    for item in nodes:
        file = item.get("source_file") or ""
        selected.append({
            "id": str(item["id"]), "label": str(item.get("label") or ""),
            "file": file, "domain": _domain(file), "community": item.get("community"),
            "line": str(item.get("source_location") or ""),
            "reasons": file_reasons.get(file, []),
            "review_categories": sorted(
                review_by_file.get(file, set())
                | ({"ast"} if source_evidence.get(file) else set())
                | ({"doctor"} if file_actions.get(file) else set())
                | ({"worker"} if file in open_worker_files or file in open_qt_worker_files else set())
                | ({"lifecycle"} if file in qt_pending_destroy_files else set())
            ),
            "source_evidence": source_evidence.get(file, []),
            "snapshot_changes": source_changes.get(file),
            "doctor_task": file_actions.get(file),
            "focused_source_consumers": focus_consumers.get(file, [])[:80],
            "runtime_observed": file in observed_files,
            "qt_call_site_observed": file in qt_sites,
            "qt_connection_observed": file in qt_files,
            "qt_callback_invoked_observed": file in qt_invoked_files,
            "runtime_import_attempt_observed": file in dynamic_import_files,
            "dynamic_module_import_returned": file in returned_import_files,
            "json_runtime_evidence": json_runtime_by_file.get(file, []),
            "json_verified_binding_evidence": json_bindings_by_file.get(file, []),
            "worker_start_unpaired_at_trace_end": file in open_worker_files,
            "qt_worker_unpaired_at_trace_end": file in open_qt_worker_files,
            "cache_release_observed": file in cache_released_files,
            "qt_destroyed_observed": file in qt_destroyed_files,
            "qt_destroy_pending_at_trace_end": file in qt_pending_destroy_files,
            "runtime_scenarios": sorted(runtime_scenarios_by_file.get(file, set())),
            "qt_native_invalid_wrappers_observed": native_invalid_by_file.get(file, 0),
        })
    edges = []
    for link in graph.get("links", []):
        if len(edges) >= MAX_LINKS:
            break
        a, b = indexed.get(link.get("source")), indexed.get(link.get("target"))
        if a is not None and b is not None:
            edges.append({"a": a, "b": b, "relation": str(link.get("relation") or "")})
    # Runtime calls are separate edges; they do not fabricate static imports.
    first_by_file: dict[str, int] = {}
    for number, row in enumerate(selected):
        first_by_file.setdefault(row["file"], number)
    for a, b in sorted(runtime_pairs):
        if len(edges) >= MAX_LINKS:
            break
        if a in first_by_file and b in first_by_file:
            edges.append({"a": first_by_file[a], "b": first_by_file[b],
                          "relation": "OBSERVED_PYTHON_CALL", "observed": True})
    for a, b in sorted(qt_pairs):
        if len(edges) >= MAX_LINKS:
            break
        if a in first_by_file and b in first_by_file:
            edges.append({"a": first_by_file[a], "b": first_by_file[b],
                          "relation": "QT_CONNECT_RETURNED", "observed": True})
    for a, b in sorted(invoked_qt_pairs):
        if len(edges) >= MAX_LINKS:
            break
        if a in first_by_file and b in first_by_file:
            edges.append({"a": first_by_file[a], "b": first_by_file[b],
                          "relation": "QT_CALLBACK_INVOKED", "observed": True})
    for a, b in sorted(returned_import_pairs):
        if len(edges) >= MAX_LINKS:
            break
        if a in first_by_file and b in first_by_file:
            edges.append({"a": first_by_file[a], "b": first_by_file[b],
                          "relation": "RUNTIME_IMPORT_RETURNED", "observed": True})
    for a, b in sorted(runtime_import_pairs):
        if len(edges) >= MAX_LINKS:
            break
        if a in first_by_file and b in first_by_file:
            edges.append({"a": first_by_file[a], "b": first_by_file[b],
                          "relation": "RUNTIME_IMPORT_ATTEMPT", "observed": True})
    return {
        "nodes": selected, "edges": edges, "candidate_sha": graph.get("built_at_commit"),
        "snapshot_diff": comparison,
        "historical_scenario_trend": historical_trend,
        "focused_source_impact": focused_impact,
        "community_review_candidates": community_reviews,
        "community_review_total": int(cohesion.get("candidate_count") or 0)
        if isinstance(cohesion, dict) else 0,
        "trace_status": trace_status, "observed_runtime_file_pairs": len(runtime_pairs),
        "scenarios_merged": (trace.get("scenarios_merged", 1) if trace_status == "MATCHED" and isinstance(trace, dict) else 0),
        "scenario_modules": scenario_names,
        "observed_qt_callback_file_pairs": len(invoked_qt_pairs),
        "observed_runtime_import_attempt_pairs": len(runtime_import_pairs),
        "observed_module_import_returned_pairs": len(returned_import_pairs),
        "runtime_import_attempts_truncated": runtime_imports_truncated,
        "observed_json_opens": json_runtime_summary.get("json_opens_observed", 0),
        "observed_json_ui_bindings": bindings_summary.get("bound_to_ui", 0),
        "observed_json_truncated": json_runtime_summary.get("truncated", False),
        "observed_lifecycle": observed_lifecycle,
        "observed_performance": observed_performance,
        "observed_symbol_calls": symbol_calls,
        "source_inspection_status": (inspection or {}).get("status", "NOT_RUN"),
        "json_lineage_review_leads": (lineage or {}).get("references_with_ui_importers", 0),
        "json_lineage_runtime_proven": False,
        "source_inspection_files": len((inspection or {}).get("paths_inspected", [])),
        "source_inspection_truncated": bool((inspection or {}).get("truncated")),
        "symbol_calls_bounded": bool(isinstance(trace, dict) and trace.get("symbol_edges_truncated")),
        "qt_call_site_files": len(qt_sites),
        "raw_nodes": len(graph.get("nodes", [])), "raw_links": len(graph.get("links", [])),
        "truncated": len(graph.get("nodes", [])) > MAX_NODES or len(graph.get("links", [])) > MAX_LINKS,
        "disclaimer": "A flagged node is not proof of dead code; native runtime connections require trace evidence.",
    }


HTML = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Doctor Atlas — Graphify interactif</title>
<style>
:root{font:14px system-ui,sans-serif;color-scheme:dark;background:#0d1420;color:#ecf1fc}
*{box-sizing:border-box}body{margin:0}header{display:flex;flex-wrap:wrap;gap:12px;align-items:center;padding:12px 18px;border-bottom:1px solid #29354c}
h1{font-size:17px;margin:0 20px 0 0}input,select,button{background:#172437;color:#fff;border:1px solid #41526f;border-radius:6px;padding:7px}
main{display:grid;grid-template-columns:minmax(0,1fr) 330px;height:calc(100vh - 64px)}
canvas{width:100%;height:100%;touch-action:none;cursor:grab}
aside{border-left:1px solid #29354c;padding:16px;overflow:auto;overflow-wrap:anywhere}
small{color:#9baec9}a{color:#8dc9ff}li{margin-bottom:8px} .warning{color:#ffbd6b}
@media(max-width:850px){main{grid-template-columns:1fr;height:auto}canvas{height:65vh}aside{border-left:none;border-top:1px solid #29354c}}
</style></head><body>
<header><h1>Doctor Atlas × Graphify</h1>
<input id="search" type="search" placeholder="Chercher symbole ou fichier" aria-label="Rechercher">
<select id="domain" aria-label="Domaine"><option value="">Tous les domaines</option></select>
<select id="scenario" aria-label="Scénario runtime"><option value="">Tous les scénarios</option></select>
<select id="community" aria-label="Communauté Graphify"><option value="">Toutes les communautés</option></select>
<select id="relation" aria-label="Relation du graphe"><option value="">Toutes les relations</option></select>
<select id="priority" aria-label="Priorité Doctor"><option value="">Toutes priorités</option><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select>
<select id="reviewKind" aria-label="Catégorie de diagnostic Doctor"><option value="">Tous les diagnostics</option></select>
<label><input id="flagged" type="checkbox"> À examiner uniquement</label>
<label><input id="snapshotOnly" type="checkbox"> Changements depuis référence</label>
<button id="reset">Recentrer</button><button id="refreshGit">Actualiser Git</button>
<button id="graphPrev" type="button" aria-label="Page précédente du graphe">◀</button>
<small id="graphPage" aria-live="polite">Page 1</small>
<button id="graphNext" type="button" aria-label="Page suivante du graphe">▶</button>
<small id="summary"></small><small id="liveStatus">Graphe statique</small></header>
<main><canvas id="map" aria-label="Graphe interactif, zoom molette, déplacement souris"></canvas>
<aside><h2>Inspection du code</h2><div id="snapshotDetails"></div><div id="coverageDetails"></div><div id="nodeDetails">Clique sur un nœud pour voir les dépendances, les preuves et les raisons d'examen.</div>
<hr><small id="limits"></small></aside></main>
<script id="doctor-data" type="application/json">__GRAPH_DATA__</script>
<script>
(()=>{'use strict';
const data=JSON.parse(document.getElementById('doctor-data').textContent);
const canvas=document.getElementById('map'),ctx=canvas.getContext('2d');
const search=document.getElementById('search'),domain=document.getElementById('domain');
const community=document.getElementById('community');
const scenario=document.getElementById('scenario');
const relation=document.getElementById('relation');
const flagged=document.getElementById('flagged'),details=document.getElementById('nodeDetails');
const snapshotOnly=document.getElementById('snapshotOnly');
const priority=document.getElementById('priority');
const reviewKind=document.getElementById('reviewKind');
const inventory=data.file_coverage;
const snapshot=data.snapshot_diff;
snapshotOnly.disabled=!snapshot;
if(snapshot){
 const section=document.getElementById('snapshotDetails');
 const heading=document.createElement('h3');heading.textContent='Changements depuis le graphe de référence';
 section.appendChild(heading);
 const summary=document.createElement('p');
 summary.textContent='Référence '+snapshot.baseline_sha.slice(0,9)+' → '+snapshot.candidate_sha.slice(0,9)+
  ' · '+snapshot.new_import_file_pairs.length+' imports ajoutés · '+
  snapshot.removed_import_file_pairs.length+' imports retirés · '+
  snapshot.new_orphan_symbols.length+' nouveaux orphelins candidats';
 section.appendChild(summary);
 const caveat=document.createElement('small');
 caveat.textContent='Diff statique consultatif ; aucune preuve de régression ou de code mort. Les listes peuvent être tronquées.';
 section.appendChild(caveat);
 section.appendChild(document.createElement('hr'));
}
if(inventory){
 const section=document.getElementById('coverageDetails');
 const heading=document.createElement('h3');heading.textContent='Fichiers Python couverts';section.appendChild(heading);
 const count=document.createElement('p');
 count.textContent=inventory.represented+'/'+inventory.tracked+' représentés dans le graphe';
 section.appendChild(count);
 const status=document.createElement('small');
 status.textContent=inventory.status+' · Pas une preuve de code utilisé ou mort';
 section.appendChild(status);
 if(inventory.missing_total){
  const details=document.createElement('details');
  const summary=document.createElement('summary');
  summary.textContent=inventory.missing_total+' fichiers absents du graphe';
  details.appendChild(summary);
  inventory.missing_examples.forEach(path=>{
   const p=document.createElement('p');p.textContent=path;details.appendChild(p);
  });
  section.appendChild(details);
 }
 section.appendChild(document.createElement('hr'));
}
const perf=data.observed_performance;
if(perf && perf.samples && perf.samples.length){
 const section=document.getElementById('coverageDetails');
 const h=document.createElement('h3');h.textContent='Checkpoints CPU/RAM du scénario';section.appendChild(h);
 perf.samples.slice(0,12).forEach(sample=>{
  const line=document.createElement('p');
  line.textContent=sample.label+' : '+(sample.rss_tree_bytes==null?'indisponible':
    (sample.rss_tree_bytes/1048576).toFixed(2)+' Mio RSS observés')+
    (sample.cpu_time_cumulative_seconds==null?'':' · '+sample.cpu_time_cumulative_seconds+' s CPU cumulé');
  section.appendChild(line);
 });
 perf.comparisons.slice(0,10).forEach(delta=>{
  const p=document.createElement('p');
  p.textContent=delta.from+' → '+delta.to+' : '+
   (delta.same_sampled_process_set ?
     (delta.rss_delta_bytes/1048576).toFixed(2)+' Mio RSS (différence)' +
     (delta.cpu_time_delta_seconds==null?'':' · '+delta.cpu_time_delta_seconds+' s CPU (différence)') :
     'ensemble de processus modifié, comparaison refusée');
  section.appendChild(p);
 });
 const limits=document.createElement('small');
 limits.textContent='Instantanés opt-in, pas le pic RAM ni un benchmark certifié ; aucun ownership WebEngine prouvé.';
 section.appendChild(limits);section.appendChild(document.createElement('hr'));
}
// Native Qt parent relationship is visible only for explicitly watched
// wrappers in exact-SHA opt-in traces. Do not infer native WebEngine memory.
const qtSnapshots=(data.observed_lifecycle||{}).qt_parent_snapshots||[];
if(qtSnapshots.length){
 const section=document.getElementById('coverageDetails');
 const title=document.createElement('h3');
 title.textContent='Qt natif · relations parent (scénarios)';section.appendChild(title);
 qtSnapshots.slice(0,16).forEach(sample=>{
  const p=document.createElement('p');
  const number=v=>Number.isInteger(v)&&v>=0?String(v):'?';
  p.textContent=String(sample.label||'snapshot')+' : '+
   number(sample.parent_present_native_valid)+' avec parent Qt · '+
   number(sample.parent_absent_at_snapshot)+' sans parent Qt · '+
   number(sample.native_invalid_wrappers)+' wrappers natifs invalides · '+
   number(sample.webengine_wrappers_sampled)+' wrappers WebEngine';
  section.appendChild(p);
 });
 const caveat=document.createElement('small');
 caveat.textContent='Observation QObject.parent()/shiboken, sans preuve de fuite, de propriété Chromium ni de couverture complète.';
 section.appendChild(caveat);section.appendChild(document.createElement('hr'));
}
const qtLifetime=data.observed_lifecycle;
if(qtLifetime&&qtLifetime.qt_destroy_watches_registered>0){
 const section=document.getElementById('coverageDetails');
 const title=document.createElement('h3');title.textContent='Destruction Qt dans les scénarios';section.appendChild(title);
 const p=document.createElement('p');
 p.textContent=qtLifetime.qt_destroy_watches_delivered+' signaux reçus / '+
 qtLifetime.qt_destroy_watches_registered+' connexions enregistrées ; '+
 qtLifetime.qt_destroy_watches_pending_count+' sans destruction observée';
 section.appendChild(p);
 const note=document.createElement('small');
 note.textContent='Une destruction non observée peut être différée, et ne prouve pas une fuite native.';
 section.appendChild(note);section.appendChild(document.createElement('hr'));
}
const historicalTrend=data.historical_scenario_trend;
if(historicalTrend && historicalTrend.status!=='UNAVAILABLE'){
 const section=document.getElementById('coverageDetails');
 const title=document.createElement('h3');title.textContent='Historique du scénario';section.appendChild(title);
 const p=document.createElement('p');
 p.textContent=String(historicalTrend.scenario_module||'')+' · '+
  String(historicalTrend.run_count||0)+' traces · '+
  String(historicalTrend.repeated_absence_candidates||0)+' absences répétées candidates';
 section.appendChild(p);
 const note=document.createElement('small');
 note.textContent='Différences historiques, non preuve de régression ni de code mort. Vérifier les scénarios réels.';
 section.appendChild(note);section.appendChild(document.createElement('hr'));
}
const focusImpact=data.focused_source_impact;
if(focusImpact){
 const section=document.getElementById('coverageDetails');
 const heading=document.createElement('h3');heading.textContent='Impact source ciblé';
 section.appendChild(heading);
 const paragraph=document.createElement('p');
 paragraph.textContent=(focusImpact.changed_files||[]).join(', ')+
  ' · '+String(focusImpact.direct_consumers||0)+' directs · '+
  String(focusImpact.indirect_consumers||0)+' indirects';
 section.appendChild(paragraph);
 const note=document.createElement('small');
 note.textContent=(focusImpact.truncated?'Inspection incomplète · ':'')+
  'Import AST confirmé ≠ usage runtime; piste d’import dynamique ≠ exécution.';
 section.appendChild(note);section.appendChild(document.createElement('hr'));
}
const neighbors=new Map(), nodes=data.nodes;
const relationCounts=new Map();
// File-level import consumers are derived once from the existing static graph.
// Runtime call and Qt connection edges must never be treated as imports.
const firstNodeByFile=new Map(), staticImporters=new Map();
nodes.forEach((node,i)=>{if(node.file&&!firstNodeByFile.has(node.file))firstNodeByFile.set(node.file,i)});
for(const edge of data.edges){
 if(!['imports','imports_from'].includes(edge.relation)||edge.observed===true)continue;
 const importer=nodes[edge.a]?.file, imported=nodes[edge.b]?.file;
 if(!importer||!imported||importer===imported)continue;
 if(!staticImporters.has(imported))staticImporters.set(imported,new Set());
 staticImporters.get(imported).add(importer);
}
data.edges.forEach(e=>{
  const kind=String(e.relation||'non typée');
  relationCounts.set(kind,(relationCounts.get(kind)||0)+1);
  if(!neighbors.has(e.a))neighbors.set(e.a,[]);
  if(!neighbors.has(e.b))neighbors.set(e.b,[]);
  neighbors.get(e.a).push({n:e.b,relation:e.relation,direction:'out'});
  neighbors.get(e.b).push({n:e.a,relation:e.relation,direction:'in'});
});
[...relationCounts].sort((a,b)=>a[0].localeCompare(b[0])).forEach(([kind,count])=>{
 const option=document.createElement('option');option.value=kind;
 option.textContent=kind+' ('+count+')';relation.appendChild(option);
});
const groups=[...new Set(nodes.map(n=>n.domain))].sort();
groups.forEach(g=>{let opt=document.createElement('option');opt.value=g;opt.textContent=g;domain.appendChild(opt)});
(data.scenario_modules||[]).forEach((name,index)=>{
 const opt=document.createElement('option');opt.value='Scénario '+(index+1);
 opt.textContent='Scénario '+(index+1)+' · '+name;scenario.appendChild(opt);
});
scenario.disabled=!(data.scenarios_merged>0);
const communityReview=new Map((data.community_review_candidates||[]).map(row=>[String(row.community),row]));
// All counts are bounded by the already-loaded Graphify node payload.
const reviewLabels={focus:'Fichier ciblé',consumer:'Consommateur AST',dynamic:'Import dynamique candidat',orphan:'Nœuds isolés',weak:'Connexions faibles',fanout:'Couplage élevé',
 forbidden:'Imports interdits confirmés',island:'Communautés isolées',lifecycle:'Destruction Qt non observée',history:'Écarts historiques à examiner',
 ast:'Indices AST / JSON',doctor:'Actions Doctor',worker:'Workers à vérifier'};
const reviewCounts=new Map();
nodes.forEach(n=>(n.review_categories||[]).forEach(kind=>
 reviewCounts.set(kind,(reviewCounts.get(kind)||0)+1)));
[...reviewCounts].sort((a,b)=>a[0].localeCompare(b[0])).forEach(([kind,count])=>{
 const option=document.createElement('option');option.value=kind;
 option.textContent=(reviewLabels[kind]||kind)+' ('+count+' nœuds)';
 reviewKind.appendChild(option);
});
const communityCounts=new Map();
nodes.forEach(n=>{
 if(n.community===null||n.community===undefined)return;
 const id=String(n.community);
 communityCounts.set(id,(communityCounts.get(id)||0)+1);
});
[...communityCounts].sort((a,b)=>a[0].localeCompare(b[0],undefined,{numeric:true})).forEach(([id,count])=>{
 const option=document.createElement('option');option.value=id;
 option.textContent='Communauté '+id+' ('+count+' nœuds)'+(communityReview.has(id)?' · cohésion à examiner':'');
 community.appendChild(option);
});
function hash(s){let n=2166136261;for(let i=0;i<s.length;i++)n=Math.imul(n^s.charCodeAt(i),16777619);return n>>>0}
const offsets=new Map(groups.map((g,i)=>[g,i]));
const positions=nodes.map(n=>{
  const seed=hash(n.file+'|'+n.id),angle=(seed%65521)/65521*Math.PI*2;
  const group=offsets.get(n.domain)||0,outer=360+125*Math.sqrt(group);
  const groupAngle=group*2.39996323,small=12+Math.sqrt((seed>>>9)%2400)*1.8;
  return {x:Math.cos(groupAngle)*outer+Math.cos(angle)*small,
          y:Math.sin(groupAngle)*outer+Math.sin(angle)*small};
});
const PAGE_SIZE=1200;
let scale=.36,panX=0,panY=0,drag=null,selected=-1,visible=[],matches=[],pageIndex=0,pathStart=-1;
let changedFiles=new Set();
let importChanges=new Map(),importErrors=new Map(),importStatus='UNKNOWN';
let lastRefresh=0,refreshInFlight=false,lastLabel='';
function fit(){const rect=canvas.getBoundingClientRect();canvas.width=Math.max(1,Math.round(rect.width*devicePixelRatio));canvas.height=Math.max(1,Math.round(rect.height*devicePixelRatio));render()}
function filter(resetPage=true){const needle=search.value.toLowerCase().trim(),group=domain.value,level=priority.value,cluster=community.value,kind=reviewKind.value,scenarioName=scenario.value;
matches=nodes.map((n,i)=>i).filter(i=>{const n=nodes[i];return (!group||n.domain===group)&&
 (!cluster||String(n.community)===cluster)&&
 (!scenarioName||(n.runtime_scenarios||[]).includes(scenarioName))&&
 (!kind||(n.review_categories||[]).includes(kind))&&
 (!snapshotOnly.checked||!!n.snapshot_changes)&&
 (!level||(n.doctor_task&&n.doctor_task.priority===level))&&
 (!flagged.checked||n.reasons.length||n.doctor_task||n.source_evidence.length||n.worker_start_unpaired_at_trace_end)&&
 (!needle||(n.file+' '+n.label).toLowerCase().includes(needle))});
const pages=Math.max(1,Math.ceil(matches.length/PAGE_SIZE));
if(resetPage)pageIndex=0;
pageIndex=Math.max(0,Math.min(pageIndex,pages-1));
visible=matches.slice(pageIndex*PAGE_SIZE,(pageIndex+1)*PAGE_SIZE);
document.getElementById('graphPrev').disabled=pageIndex===0;
document.getElementById('graphNext').disabled=pageIndex>=pages-1;
document.getElementById('graphPage').textContent='Page '+(pageIndex+1)+' / '+pages;
document.getElementById('summary').textContent=visible.length+' affichés · '+matches.length+' filtrés / '+nodes.length+' nœuds · relations de la page uniquement';
render()}
function screen(p){return {x:canvas.width/2+(p.x+panX)*scale*devicePixelRatio,
y:canvas.height/2+(p.y+panY)*scale*devicePixelRatio}}
let drawScheduled=false;
function render(){
 if(drawScheduled)return;
 drawScheduled=true;
 requestAnimationFrame(()=>{drawScheduled=false;paint()});
}
function paint(){
 if(!ctx)return;
 ctx.fillStyle='#0d1420';ctx.fillRect(0,0,canvas.width,canvas.height);
 const subset=new Set(visible);ctx.strokeStyle='#2b4259';ctx.lineWidth=1;
 if(visible.length<=3500){for(const e of data.edges){
 if(!subset.has(e.a)||!subset.has(e.b))continue;
 if(relation.value && e.relation!==relation.value)continue;
 let a=screen(positions[e.a]),b=screen(positions[e.b]);
 ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();
 }}
 for(const i of visible){const p=screen(positions[i]),n=nodes[i];
 if(p.x < -10||p.x>canvas.width+10||p.y < -10||p.y>canvas.height+10)continue;
 ctx.beginPath();ctx.arc(p.x,p.y,i===selected?6:3,0,2*Math.PI);
 ctx.fillStyle=i===selected?'#ffdf86':changedFiles.has(n.file)?'#f9b454':n.snapshot_changes?'#9bdf8b':(n.reasons.length||n.source_evidence.length)?'#ff8d7d':(n.runtime_observed||n.qt_call_site_observed)?'#b39cf5':'#70b9e9';ctx.fill()}
}
function pick(x,y){let best=-1,distance=100;for(const i of visible){
 const p=screen(positions[i]),d=(p.x-x)**2+(p.y-y)**2;
 if(d<distance){distance=d;best=i}}return best}
function show(i){selected=i;const n=nodes[i];details.replaceChildren();
function line(tag,text){const el=document.createElement(tag);el.textContent=text;details.appendChild(el);return el}
line('h3',n.label||n.file);line('p',n.file+(n.line?' · '+n.line:''));
if(changedFiles.has(n.file))line('p','Fichier modifié depuis le graphe : dépendances statiques potentiellement périmées.');
if(importChanges.has(n.file)){
 const delta=importChanges.get(n.file);
 line('h4','Imports Python modifiés (AST courant versus commit du graphe)');
 delta.added_imports.forEach(x=>line('p','+ L'+x.line+' '+x.statement));
 delta.removed_imports.forEach(x=>line('p','− ancienne L'+x.baseline_line+' '+x.statement));
 if(delta.imports_truncated)line('p','Détails tronqués : analyse ciblée nécessaire.');
}
if(importErrors.has(n.file))line('p','Inspection AST incomplète : '+importErrors.get(n.file));
line('p','Communauté Graphify : '+String(n.community??'non déterminée'));
if(n.snapshot_changes){
 const changes=n.snapshot_changes;
 line('h4','Différences Graphify depuis la référence');
 changes.added_imports.forEach(path=>line('p','+ import vers '+path));
 changes.removed_imports.forEach(path=>line('p','− import vers '+path));
 if(changes.new_orphan)line('p','Nouveau symbole orphelin candidat : vérifier ses consommateurs.');
 if(changes.new_weak)line('p','Symbole nouvellement peu connecté : examen nécessaire.');
}
if(n.review_categories.length){
 line('p','Catégories de diagnostic à vérifier : '+n.review_categories.map(kind=>reviewLabels[kind]||kind).join(', '));
}
const boundary=communityReview.get(String(n.community));
if(boundary){
 line('h4','Frontières de communauté à examiner');
 line('p',boundary.production_files+' fichiers de production · '+boundary.internal_extracted_edges+
 ' liens internes extraits · '+boundary.external_extracted_edges+' liens externes extraits.');
 line('p','Cohésion faible selon le graphe statique : ni fusion ni suppression automatique. Vérifier responsabilités, imports et appels réels.');
}
if((n.focused_source_consumers||[]).length){
 line('h4','Consommateurs confirmés dans la source et pistes dynamiques');
 n.focused_source_consumers.slice(0,32).forEach(lead=>{
  const text=lead.path+' · profondeur '+lead.depth+' · '+lead.kind+
   (lead.line?' (ligne '+lead.line+')':'');
  const index=firstNodeByFile.get(lead.path);
  if(index==null){line('p',text+' · fichier non représenté dans ce graphe');return}
  const button=line('button',text+' · ouvrir');
  button.type='button';button.addEventListener('click',()=>revealNode(index));
 });
 if(n.focused_source_consumers.length>32)line('p','Résultats paginés/tronqués; inspecter les sources pour la suite.');
}
if(n.runtime_observed)line('p','Appel Python observé dans une trace opt-in correspondant au SHA.');
if((n.runtime_scenarios||[]).length)line('p','Scénarios observés : '+n.runtime_scenarios.join(', '));
const symbolCalls=(data.observed_symbol_calls||[]).filter(e=>e.source===n.file||e.target===n.file);
if(symbolCalls.length){
 line('h4','Appels de fonctions observés (scénario opt-in)');
 symbolCalls.slice(0,20).forEach(e=>line('p',
  e.source+':'+e.caller_line+' '+e.caller_symbol+' → '+e.target+':'+e.callee_line+' '+e.callee_symbol));
 if(symbolCalls.length>20||data.symbol_calls_bounded)line('p','Observations partielles : aucune conclusion sur les fonctions non vues.');
}
if(n.qt_destroy_pending_at_trace_end)line('p',
 'Signal de destruction Qt connecté mais non reçu pendant la trace. À examiner, pas une preuve de fuite.');
if(n.qt_call_site_observed)line('p','Appel PySide observé au site d’appel ; récepteur non prouvé.');
if(n.qt_connection_observed)line('p','Connexion Qt explicitement instrumentée ; exécution du récepteur non prouvée.');
 if(n.qt_callback_invoked_observed)line('p','Callback Python Qt entré pendant ce scénario opt-in ; ownership natif non prouvé.');
 if(n.runtime_import_attempt_observed)line('p','Tentative d’import Python observée dans ce scénario ; réussite de l’import non attestée.');
 if(n.dynamic_module_import_returned)line('p','Import dynamique retourné par importlib dans ce scénario ; succès de résolution attesté, pas de nouvelle exécution prouvée.');
 if((n.json_verified_binding_evidence||[]).length){
  line('h4','JSON décodé et transmis à la vue (scénario opt-in)');
  n.json_verified_binding_evidence.forEach(e=>line('p',e.json_path+' · '+e.reader+' → '+e.ui_file));
  line('p','Liaison Python explicitement marquée : ni affichage d’une image ni rendu QWebEngine prouvés.');
 }
 if((n.json_runtime_evidence||[]).length){
  line('h4','JSON : observations du scénario');
  n.json_runtime_evidence.forEach(e=>line('p',e.kind+' · '+e.json_path+' · ouverture dans '+e.opening_source));
  line('p','Ouverture et appels co-observés : ni lecture des données ni rendu UI prouvés.');
 }
if(n.worker_start_unpaired_at_trace_end)line('p','Worker démarré sans arrêt observé avant la fin de cette trace ; une activité en cours est possible, ce n’est pas une fuite mémoire prouvée.');
if(n.qt_worker_unpaired_at_trace_end)line('p','QThread.started observé sans QThread.finished correspondant dans le même scénario ; ce n’est ni preuve de fuite ni ownership.');
if(n.cache_release_observed)line('p','Libération de cache explicitement marquée dans le scénario runtime.');
 if(n.qt_destroyed_observed)line('p','Signal QObject.destroyed reçu sous observation explicite ; ownership C++ et mémoire libérée non prouvés.');
 if(n.qt_native_invalid_wrappers_observed)line('p',n.qt_native_invalid_wrappers_observed+' wrapper(s) Python Qt avec objet C++ invalidé ; ce n’est pas une fuite prouvée.');
if(n.doctor_task){
 line('h4','Priorité Doctor : '+n.doctor_task.priority);
 line('p',n.doctor_task.kind+' · '+n.doctor_task.action);
 line('p','Proposition à vérifier dans le code et les tests, jamais correction automatique.');
}
if(n.source_evidence.length){
 line('h4','Indices AST du fichier (examen nécessaire)');
 n.source_evidence.forEach(e=>line('p',e.kind+(e.line?' · L'+e.line:'')+(e.subject?' · '+e.subject:'')));
}
if(n.reasons.length){line('h4','Pourquoi Doctor signale ce nœud');n.reasons.forEach(v=>line('p','• '+v))}
else line('p','Aucun signal prioritaire dans cet extrait de diagnostic.');
const link=document.createElement('a');
const locationMatch=String(n.line||'').match(/(?:^|:)([0-9]+)(?::[0-9]+)?$/);
const lineAnchor=locationMatch?'#L'+locationMatch[1]:'';
link.href='https://github.com/r9327/Dof-Atlas/blob/'+encodeURIComponent(data.candidate_sha||'main')+'/'+n.file.split('/').map(encodeURIComponent).join('/')+lineAnchor;
link.target='_blank';link.rel='noopener noreferrer';link.textContent='Voir le code sur GitHub';details.appendChild(link);
if(data.local_ide_root && n.file && !n.file.startsWith('/') &&
  n.file.endsWith('.py') && n.file.split('/').every(p=>p && p!=='.' && p!=='..')){
 const filePath=data.local_ide_root.replace(/\\/g,'/')+'/'+n.file;
 const ideLink=document.createElement('a');
 ideLink.href='vscode://file/'+encodeURI(filePath)+(locationMatch?':'+locationMatch[1]:'');
 ideLink.textContent='Ouvrir le fichier dans VS Code';
 details.appendChild(ideLink);
}
const adj=neighbors.get(i)||[];
const shownAdj=adj.filter(e=>!relation.value||e.relation===relation.value);
line('h4','Voisins du graphe ('+shownAdj.length+' / '+adj.length+' avec ce filtre)');
shownAdj.slice(0,40).forEach(e=>{
 const button=document.createElement('button');button.type='button';
 button.textContent=(e.direction==='out'?'→ ':'← ')+nodes[e.n].file+' · '+e.relation;
 button.addEventListener('click',()=>revealNode(e.n));
 details.appendChild(button);
});
if(shownAdj.length>40)line('small','Liste limitée à 40 voisins, sans supprimer les relations du graphe.');
const startButton=document.createElement('button');startButton.type='button';
startButton.textContent=pathStart===i?'Départ sélectionné':'Définir comme départ du chemin';
startButton.addEventListener('click',()=>{pathStart=i;show(i)});
details.appendChild(startButton);
if(pathStart>=0&&pathStart!==i){
 const pathButton=document.createElement('button');pathButton.type='button';
 pathButton.textContent='Chercher les dépendances depuis '+nodes[pathStart].file;
 pathButton.addEventListener('click',()=>showGraphPath(pathStart,i));
 details.appendChild(pathButton);
}
if(pathStart===i)line('p','Choisis un autre nœud puis cherche son chemin de dépendances.');
const impactButton=document.createElement('button');impactButton.type='button';
impactButton.textContent='Explorer les consommateurs (imports inverses)';
impactButton.addEventListener('click',()=>showReverseImpact(i));
details.appendChild(impactButton);
const previewButton=document.createElement('button');previewButton.type='button';
previewButton.textContent='Simuler l’impact du retrait de ce fichier (sans modification)';
previewButton.addEventListener('click',()=>showFileRemovalPreview(n.file));
details.appendChild(previewButton);
const evidenceButton=document.createElement('button');evidenceButton.type='button';
evidenceButton.textContent='Exporter les preuves Doctor de ce nœud (JSON)';
evidenceButton.addEventListener('click',()=>downloadNodeEvidence(i));
details.appendChild(evidenceButton);
render()}
function buildNodeEvidence(i){
 const n=nodes[i];
 const direct=(neighbors.get(i)||[]).slice(0,80).map(edge=>({
  direction:edge.direction,relation:edge.relation,
  file:nodes[edge.n].file,source_location:nodes[edge.n].line,
 }));
 const calls=(data.observed_symbol_calls||[])
  .filter(e=>e.source===n.file||e.target===n.file).slice(0,20);
 return {
  schema_version:1,kind:'doctor_graph_node_evidence',
  candidate_sha:data.candidate_sha,
  static_graph_truncated:!!data.truncated,
  runtime_trace_status:data.trace_status,
  runtime_scenarios:(n.runtime_scenarios||[]).slice(0,8),
  source_inspection_status:data.source_inspection_status,
  source:{file:n.file,symbol:n.label,line:n.line,community:n.community},
  review:{categories:n.review_categories||[],reasons:n.reasons||[],
   doctor_task:n.doctor_task||null,source_evidence:(n.source_evidence||[]).slice(0,20),
   snapshot_changes:n.snapshot_changes||null},
  runtime:{python_call_observed:!!n.runtime_observed,
   qt_connection_observed:!!n.qt_connection_observed,
   qt_callback_invoked_observed:!!n.qt_callback_invoked_observed,
    json_verified_binding_evidence:(n.json_verified_binding_evidence||[]).slice(0,6),
    runtime_import_attempt_observed:!!n.runtime_import_attempt_observed,
    json_runtime_evidence:(n.json_runtime_evidence||[]).slice(0,6),
   qt_call_site_observed:!!n.qt_call_site_observed,
   unpaired_worker_at_trace_end:!!n.worker_start_unpaired_at_trace_end,
   qt_worker_unpaired_at_trace_end:!!n.qt_worker_unpaired_at_trace_end,
   cache_release_marked:!!n.cache_release_observed,
    qt_destroyed_observed:!!n.qt_destroyed_observed,
    qt_native_invalid_wrappers_observed:n.qt_native_invalid_wrappers_observed||0,
   symbol_calls:calls,partial_symbol_calls:!!data.symbol_calls_bounded},
  relationships:{shown:direct,total:(neighbors.get(i)||[]).length,
   truncated:(neighbors.get(i)||[]).length>80},
  limitations:[
   'Review evidence only; not proof of dead code or safe deletion.',
   'Static relations do not prove runtime calls.',
   'An unobserved Qt callback is not proof that it never executes.',
   'The exported subset and current Graphify snapshot may be incomplete.',
  ],
  code_changed_since_graph:changedFiles.has(n.file),
 };
}
function downloadNodeEvidence(i){
 const report=buildNodeEvidence(i);
 const blob=new Blob([JSON.stringify(report,null,2)+'\n'],{type:'application/json'});
 const url=URL.createObjectURL(blob);
 const element=document.createElement('a');
 const safe=String(report.source.file||'node').replace(/[^a-zA-Z0-9_.-]/g,'_').slice(0,72);
 element.download='doctor-evidence-'+safe+'-'+String(report.candidate_sha||'unknown').slice(0,9)+'.json';
 element.href=url;document.body.appendChild(element);
 element.click();element.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function focusNode(i){
 const loc=positions[i];
 if(!loc)return;
 panX=-loc.x;panY=-loc.y;
 scale=Math.max(scale,.55);
 show(i);
}
function revealNode(i){
 let offset=matches.indexOf(i);
 if(offset<0){
  search.value='';domain.value='';community.value='';reviewKind.value='';priority.value='';flagged.checked=false;snapshotOnly.checked=false;
  filter(true);offset=matches.indexOf(i);
 }
 if(offset>=0){pageIndex=Math.floor(offset/PAGE_SIZE);filter(false);focusNode(i)}
}
function showReverseImpact(source){
 // Imported-by is static structural review, never observed behavior or deadness.
 const queue=[{node:source,depth:0}],seen=new Set([source]),candidates=[];
 let cursor=0,truncated=false;
 while(cursor<queue.length){
  const current=queue[cursor++];
  if(current.depth>=2)continue;
  for(const edge of neighbors.get(current.node)||[]){
   if(edge.direction!=='in'||!['imports','imports_from'].includes(edge.relation))continue;
   if(seen.has(edge.n))continue;
   if(seen.size>=2000){truncated=true;break}
   seen.add(edge.n);queue.push({node:edge.n,depth:current.depth+1});
   if(candidates.length<30)candidates.push({node:edge.n,depth:current.depth+1,relation:edge.relation});
  }
  if(truncated)break;
 }
 const section=document.createElement('section');
 const header=document.createElement('h4');
 header.textContent='Consommateurs possibles (imports inverses, 2 sauts maximum)';
 section.appendChild(header);
 const status=document.createElement('p');
 status.textContent=(seen.size-1)+' nœuds atteints dans ce budget ; '+(truncated?'revue partielle. ':'30 résultats affichés maximum. ')+
  'Relations structurales uniquement : valider les fichiers avant tout refactor.';
 section.appendChild(status);
 candidates.forEach(row=>{
  const button=document.createElement('button');button.type='button';
  button.textContent='Niveau '+row.depth+' : '+nodes[row.node].file+' ('+row.relation+')';
  button.addEventListener('click',()=>revealNode(row.node));
  section.appendChild(button);
 });
 details.appendChild(section);
}
function showFileRemovalPreview(file){
 // Static file-import review only. Never edit files or claim an absence of consumers.
 const visited=new Set([file]), queue=[{file,depth:0}], direct=[], indirect=[];
 let cursor=0,complete=true, examinedEdges=0;
 while(cursor<queue.length){
  const current=queue[cursor++];
  if(current.depth>=2)continue;
  const incoming=staticImporters.get(current.file)||new Set();
  for(const importer of incoming){
   examinedEdges++;
   if(examinedEdges>4000||visited.size>=2000){complete=false;break}
   if(visited.has(importer))continue;
   visited.add(importer);
   const entry={file:importer,depth:current.depth+1};
   if(entry.depth===1)direct.push(entry);else indirect.push(entry);
   queue.push(entry);
  }
  if(!complete)break;
 }
 const section=document.createElement('section');
 const heading=document.createElement('h4');
 heading.textContent='Aperçu de retrait (imports par fichier, sans édition)';
 section.appendChild(heading);
 const note=document.createElement('p');
 note.textContent=direct.length+' consommateurs directs, '+indirect.length+
  ' indirects (2 niveaux). '+(complete?'Analyse bornée terminée. ':'Résultats incomplets (budget atteint). ')+
  'Ce sont des imports statiques extraits, pas une preuve d’exécution ou de sécurité de suppression.';
 section.appendChild(note);
 const rowList=[...direct,...indirect];
 rowList.sort((a,b)=>a.depth-b.depth||a.file.localeCompare(b.file));
 for(const row of rowList.slice(0,40)){
  const index=firstNodeByFile.get(row.file);
  if(index===undefined)continue;
  const button=document.createElement('button');button.type='button';
  button.textContent=(row.depth===1?'Direct : ':'Indirect : ')+row.file;
  button.addEventListener('click',()=>revealNode(index));
  section.appendChild(button);
 }
 if(rowList.length>40){
  const warning=document.createElement('small');
  warning.textContent='Affichage limité à 40 fichiers ; le total reste calculé séparément.';
  section.appendChild(warning);
 }
 const provenance=document.createElement('small');
 provenance.textContent='Scénario hypothétique, lecture seule. Vérifier les imports dynamiques, Qt et tests avant tout changement.';
 section.appendChild(provenance);
 details.appendChild(section);
}
function showGraphPath(from,to){
 // On-demand, directional Graphify relationships only; never a runtime proof.
 const queue=[from], depth=new Map([[from,0]]), previous=new Map();
 let cursor=0,complete=true,found=from===to;
 while(cursor<queue.length&&!found){
  const here=queue[cursor++],distance=depth.get(here);
  if(distance>=8){complete=false;continue}
  for(const edge of neighbors.get(here)||[]){
   if(edge.direction!=='out'||(relation.value&&edge.relation!==relation.value))continue;
   if(depth.has(edge.n))continue;
   if(depth.size>=4000){complete=false;break}
   depth.set(edge.n,distance+1);previous.set(edge.n,{from:here,relation:edge.relation});
   queue.push(edge.n);
   if(edge.n===to){found=true;break}
  }
  if(depth.size>=4000&&!found)break;
 }
 const section=document.createElement('section');
 const heading=document.createElement('h4');heading.textContent='Chemin de relations Graphify';section.appendChild(heading);
 if(!found){
  const note=document.createElement('p');
  note.textContent=(complete?'Aucun chemin orienté trouvé dans ce graphe extrait.':'Recherche partielle (8 sauts ou 4 000 nœuds). Chemin non établi.')+' Ce résultat ne prouve jamais du code mort.';
  section.appendChild(note);
 }else{
  const chain=[to];let next=to;
  while(next!==from){next=previous.get(next).from;chain.unshift(next)}
  const note=document.createElement('small');
  note.textContent=(chain.length-1)+' relation(s) extraites/observées ; ce chemin ne prouve pas une exécution.';
  section.appendChild(note);
  chain.forEach((nodeIndex,index)=>{
   const button=document.createElement('button');button.type='button';
   const parent=index?previous.get(nodeIndex):null;
   button.textContent=(parent?'→ '+parent.relation+' → ':'Départ : ')+nodes[nodeIndex].file;
   button.addEventListener('click',()=>revealNode(nodeIndex));
   section.appendChild(button);
  });
 }
 details.appendChild(section);
}
canvas.addEventListener('pointerdown',e=>{canvas.setPointerCapture(e.pointerId);drag={x:e.clientX,y:e.clientY,px:panX,py:panY,moved:false}});
canvas.addEventListener('pointermove',e=>{if(!drag)return;const dx=(e.clientX-drag.x)/scale,dy=(e.clientY-drag.y)/scale;
if(Math.abs(dx)+Math.abs(dy)>5)drag.moved=true;panX=drag.px+dx;panY=drag.py+dy;render()});
canvas.addEventListener('pointerup',e=>{if(!drag)return;const moved=drag.moved;drag=null;
if(!moved){const r=canvas.getBoundingClientRect();const found=pick((e.clientX-r.left)*devicePixelRatio,(e.clientY-r.top)*devicePixelRatio);if(found>=0)show(found)}});
canvas.addEventListener('wheel',e=>{e.preventDefault();scale=Math.max(.025,Math.min(3,scale*(e.deltaY>0?.84:1.16)));render()},{passive:false});
[search,domain,scenario,community,reviewKind,priority,flagged,snapshotOnly].forEach(el=>el.addEventListener('input',()=>filter(true)));
relation.addEventListener('change',()=>{if(selected>=0)show(selected);else render()});
document.getElementById('graphPrev').addEventListener('click',()=>{pageIndex--;filter(false)});
document.getElementById('graphNext').addEventListener('click',()=>{pageIndex++;filter(false)});
search.addEventListener('keydown',event=>{
 if(event.key==='Enter'&&matches.length){event.preventDefault();pageIndex=0;filter(false);focusNode(matches[0])}
});
document.getElementById('reset').addEventListener('click',()=>{scale=.36;panX=0;panY=0;render()});
document.getElementById('limits').textContent='Trace: '+data.trace_status+' · '+data.observed_runtime_file_pairs+' relations de fichiers observées, '+(data.observed_qt_callback_file_pairs||0)+' callbacks Qt exécutés · '+(data.scenarios_merged||0)+' scénario(s). '+data.disclaimer+(data.truncated?' Attention : graphe tronqué pour une visualisation fluide.':'');
async function refreshLive(force=false){
 if(document.hidden||refreshInFlight||(!force&&Date.now()-lastRefresh<1500))return;
 lastRefresh=Date.now();
 refreshInFlight=true;
 const label=document.getElementById('liveStatus');
 try{
  const response=await fetch('/api/live',{cache:'no-store'});
  if(!response.ok)throw new Error('status '+response.status);
  const live=await response.json();
  const next=new Set(live.changed_files||[]);
  const importData=live.source_import_delta||{};
  const nextImportChanges=new Map((importData.changes||[]).map(row=>[row.path,row]));
  const nextImportErrors=new Map((importData.errors||[]).map(row=>[row.path,row.reason]));
  const before=JSON.stringify([...importChanges,...importErrors]);
  const after=JSON.stringify([...nextImportChanges,...nextImportErrors]);
  const changed=next.size!==changedFiles.size||[...next].some(path=>!changedFiles.has(path))||before!==after;
  changedFiles=next;
  importChanges=nextImportChanges;
  importErrors=nextImportErrors;
  importStatus=importData.status||'UNKNOWN';
  const filesShown=new Set(nodes.map(n=>n.file));
  const unknown=[...changedFiles].filter(path=>!filesShown.has(path)).length;
  let caption=live.graph_stale?'Graphe figé · '+live.changed_count+' fichiers modifiés · '+unknown+' hors graphe':'Graphe inchangé · suivi à la demande';
  if(live.truncated)caption+=' (liste partielle)';
  label.textContent=caption+' · imports '+importStatus;
  if(changed){if(selected>=0)show(selected);else render();}
 }catch(error){label.textContent='Suivi Git indisponible · graphe figé';}
 finally{refreshInFlight=false;}
}
if(location.hostname==='127.0.0.1'||location.hostname==='localhost'){
 document.getElementById('refreshGit').addEventListener('click',()=>refreshLive(true));
 window.addEventListener('focus',()=>refreshLive());
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshLive()});
 // Heartbeat keeps the *local* viewer alive while visible; it never invokes Git.
 setInterval(()=>{if(!document.hidden)fetch('/api/ping',{cache:'no-store'}).catch(()=>{})},60000);
 refreshLive(true);
}
// Populate the initial node set before the first canvas render.
window.addEventListener('resize',fit);filter();fit();
})();
</script></body></html>"""


def render_html(payload: dict[str, Any]) -> str:
    # An untrusted symbol/file label cannot close the JSON script or inject HTML.
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return HTML.replace("__GRAPH_DATA__", encoded)


def save_graph_snapshot(root: Path, graph_path: Path, sha: str) -> str:
    """Opt-in immutable snapshot. Never rebuild or overwrite an existing SHA."""
    root = root.resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Full commit SHA required for snapshot")
    expected = root / "graphify-out" / "graph.json"
    source = Path(graph_path)
    if source.is_symlink() or not source.is_file() or source.resolve() != expected.resolve():
        raise ValueError("Only the canonical Graphify export can be snapshotted")
    if source.stat().st_size > 25_000_000:
        raise ValueError("Graphify snapshot exceeds 25 MB")
    history = root / "graphify-out" / "history"
    if history.is_symlink():
        raise ValueError("Snapshot history cannot be a symlink")
    history.mkdir(parents=True, exist_ok=True)
    target = history / (sha + ".json")
    if target.is_symlink():
        raise ValueError("Historical snapshot cannot be a symlink")
    if target.exists():
        with source.open("rb") as left, target.open("rb") as right:
            if hashlib.file_digest(left, "sha256").digest() != hashlib.file_digest(right, "sha256").digest():
                raise ValueError("Existing snapshot SHA has different contents")
        return str(target)
    with source.open("rb") as left, target.open("xb") as right:
        try:
            shutil.copyfileobj(left, right, 1024 * 1024)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    return str(target)


def load_snapshot_comparison(
    root: Path, graph: dict[str, Any], baseline_path: Path
) -> dict[str, Any]:
    """Compare an explicitly supplied snapshot inside graphify-out, read-only."""
    from .graph_intelligence import compare_graphs

    root = root.resolve()
    allowed = root / "graphify-out"
    if baseline_path.is_symlink():
        raise ValueError("Symlink baseline snapshots are not allowed")
    selected = baseline_path.resolve()
    if not selected.is_relative_to(allowed) or not selected.is_file():
        raise ValueError("Baseline graph must be a regular file under graphify-out")
    if selected.stat().st_size > 25_000_000:
        raise ValueError("Baseline graph exceeds 25 MB")
    baseline = json.loads(selected.read_text(encoding="utf-8"))
    if not isinstance(baseline, dict):
        raise ValueError("Baseline graph JSON must be an object")
    return compare_graphs(baseline, graph)


def merge_runtime_traces(traces: list[dict[str, Any]], *, graph_sha: str) -> dict[str, Any]:
    """Combine positive observations of 2..8 complete traces from one SHA.

    Reject all evidence on a mismatch rather than partially trusting a mixed
    batch. Never infer negative coverage or restart an application.
    """
    if not re.fullmatch(r"[a-f0-9]{40}", graph_sha) or not 2 <= len(traces) <= 8:
        raise ValueError("Expected 2..8 trace objects and full Graphify SHA")
    combined: list[dict[str, Any]] = []
    modules: list[str] = []
    for index, trace in enumerate(traces):
        if not isinstance(trace, dict):
            raise ValueError(f"Malformed trace {index}")
        events = trace.get("events")
        if (trace.get("kind") != "doctor_runtime_observation"
                or trace.get("candidate_sha") != graph_sha
                or trace.get("worktree_clean") is not True
                or trace.get("truncated") is not False
                or not isinstance(events, list) or len(events) > 50000
                or any(not isinstance(row, dict) for row in events)
                or len(combined) + len(events) > 50000):
            raise ValueError(f"Trace {index} is incomplete, stale or exceeds 50k combined events")
        # Preserve scenario identity: identical json-1 tokens and unrelated
        # Python call paths from two runs must never combine into fake proof.
        combined.extend({**event, "_trace_group": index} for event in events)
        module = trace.get("scenario_module")
        modules.append(module if isinstance(module, str) and len(module) <= 120
                       else f"Trace {index + 1}")
    return {
        "kind": "doctor_runtime_observation", "candidate_sha": graph_sha,
        "worktree_clean": True, "truncated": False,
        "events": combined, "events_captured": len(combined),
        "symbol_edges_truncated": any(bool(t.get("symbol_edges_truncated")) for t in traces),
        "scenarios_merged": len(traces), "scenario_modules": modules,
        "limits": "Merged complete exact-SHA positive observations only; absence does not imply dead code.",
    }


def export_interactive_graph(root: Path, *, trace_path: Path | None = None,
                             allow_stale: bool = False,
                             baseline_path: Path | None = None,
                             save_snapshot: bool = False,
                             ide_links: bool = False,
                             extra_trace_paths: list[Path] | None = None,
                             scenario_trend_paths: list[Path] | None = None,
                             inspect_files: list[str] | None = None) -> dict[str, Any]:
    from .architecture import graph_status
    from .graph_audit import audit_current_graph, inspect_graph
    root = root.resolve()
    status = graph_status(root)
    stale = status.get("status") == "STALE"
    if status.get("status") != "PASS" and not (allow_stale and stale):
        return {"status": "BLOCKED", "reason": status.get("reason"), "graph_status": status.get("status")}
    try:
        graph = json.loads(Path(status["graph"]).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        return {"status": "BLOCKED", "reason": str(exc)}
    built_at = graph.get("built_at_commit")
    if not isinstance(built_at, str) or not re.fullmatch(r"[0-9a-fA-F]{7,40}", built_at):
        return {"status": "BLOCKED", "reason": "Graphify source commit provenance missing."}
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", built_at + "^{commit}"],
        cwd=root, text=True, capture_output=True, timeout=10, check=False,
    )
    if resolved.returncode != 0 or len(resolved.stdout.strip()) != 40:
        return {"status": "BLOCKED", "reason": "Graphify source commit could not be resolved."}
    snapshot_commit = resolved.stdout.strip()
    if not stale and status["git"]["head"] != snapshot_commit:
        return {"status": "BLOCKED", "reason": "Graphify source commit disagrees with current HEAD."}
    if stale:
        # Never validate a historical graph against today's changed source.
        # Show structural candidates only; no historical graph == current proof.
        audit = inspect_graph(graph, root=None)
    else:
        audit = audit_current_graph(root, graph_evidence=status)
        if audit["status"] not in {"PASS", "REVIEW"}:
            return {"status": "BLOCKED", "reason": "Doctor graph audit is not valid."}
    graph["built_at_commit"] = snapshot_commit
    focused = list(dict.fromkeys(inspect_files or []))
    if len(focused) > 8:
        return {"status": "BLOCKED", "reason": "No more than eight focused Python files."}
    if focused and stale:
        return {"status": "BLOCKED", "reason": "Focused source impact requires a current exact-SHA Graphify graph."}
    if focused:
        inventory_files = {row.get("source_file") for row in graph.get("nodes", [])
                           if isinstance(row, dict)}
        for value in focused:
            relative = Path(value)
            target = root / relative
            if (relative.is_absolute() or ".." in relative.parts or
                    "\\" in value or relative.suffix != ".py" or
                    not str(value).startswith(("app/", "tools/")) or
                    target.is_symlink() or not target.is_file() or
                    not target.resolve().is_relative_to(root) or value not in inventory_files):
                return {"status": "BLOCKED",
                        "reason": "Focused file must be a represented, existing app/tools Python source."}
    trace = None
    trace_files = ([trace_path] if trace_path is not None else []) + list(extra_trace_paths or [])
    if len(trace_files) > 8 or (extra_trace_paths and trace_path is None):
        return {"status": "BLOCKED", "reason": "Provide --trace first, at most 8 sources."}
    if trace_files:
        loaded_traces: list[dict[str, Any]] = []
        for original in trace_files:
            path = Path(original)
            selected_path = path.resolve()
            boundary = root / ".ai" / "runtime"
            if (path.is_symlink() or not selected_path.is_relative_to(boundary)
                    or not selected_path.is_file()):
                return {"status": "BLOCKED", "reason": "Trace must exist in .ai/runtime without symlinks."}
            if selected_path.stat().st_size > 10_000_000:
                return {"status": "BLOCKED", "reason": "Trace larger than 10 MB."}
            try:
                parsed = json.loads(selected_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError) as exc:
                return {"status": "BLOCKED", "reason": str(exc)}
            if not isinstance(parsed, dict):
                return {"status": "BLOCKED", "reason": "Malformed trace JSON payload."}
            loaded_traces.append(parsed)
        if len(loaded_traces) == 1:
            trace = loaded_traces[0]  # Retain existing single-trace behavior.
        else:
            try:
                trace = merge_runtime_traces(loaded_traces, graph_sha=snapshot_commit)
            except ValueError as exc:
                return {"status": "BLOCKED", "reason": str(exc)}
    # Explicit graph-ui action only: inspect at most 16 flagged Python files.
    # Never scan the repository periodically or certify historical graph data.
    inspection: dict[str, Any] | None = None
    source_scan_truncated = False
    if not stale:
        selected: list[str] = list(focused)
        seen: set[str] = set(focused)
        for kind in ("blocking_findings", "orphan_nodes",
                     "weak_production_candidates", "high_fanout_files"):
            for row in audit.get(kind, []):
                if not isinstance(row, dict):
                    continue
                path = row.get("file") or row.get("path") or row.get("source")
                if (isinstance(path, str) and path.startswith(("app/", "tools/"))
                        and path.endswith(".py") and path not in seen):
                    seen.add(path)
                    selected.append(path)
        source_scan_truncated = len(selected) > MAX_SOURCE_INSPECTION_FILES
        source_paths = [x for x in selected[:MAX_SOURCE_INSPECTION_FILES] if
                        (root / x).is_file() and not (root / x).is_symlink()]
        if source_paths:
            from .deep_intelligence import scan_sources
            inspection = scan_sources(root, source_paths)
            from .resource_lifecycle import inspect_resource_lifecycle
            inspection["resource_lifecycle"] = inspect_resource_lifecycle(root, source_paths)
    lineage = None
    if inspection is not None and inspection.get("data_lineage_candidates"):
        from .deep_intelligence import trace_literal_json_to_ui
        lineage = trace_literal_json_to_ui(graph, inspection["data_lineage_candidates"])
    comparison = None
    if baseline_path is not None:
        try:
            comparison = load_snapshot_comparison(root, graph, baseline_path)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            return {"status": "BLOCKED", "reason": f"Baseline graph: {exc}"}
    historical_trend = None
    if scenario_trend_paths:
        from .scenario_trends import load_scenario_trend
        try:
            historical_trend = load_scenario_trend(root, scenario_trend_paths)
        except (OSError, UnicodeError, ValueError) as exc:
            return {"status": "BLOCKED", "reason": f"Historical scenario: {exc}"}
        if historical_trend["status"] == "UNAVAILABLE":
            return {"status": "BLOCKED", "reason": historical_trend["reason"]}
    focused_impact = None
    if focused:
        from .source_impact import source_reverse_impact
        try:
            focused_impact = source_reverse_impact(root, focused, depth=2)
        except (OSError, RuntimeError, ValueError) as exc:
            return {"status": "BLOCKED", "reason": f"Focused AST impact: {type(exc).__name__}"}
        if focused_impact.get("status") not in {"SOURCE_CONFIRMED", "REVIEW"}:
            return {"status": "BLOCKED", "reason": focused_impact.get("reason", "Source impact unavailable.")}
    payload = compact_graph(graph, audit, trace=trace, inspection=inspection,
                            lineage=lineage, comparison=comparison,
                            historical_trend=historical_trend,
                            focused_impact=focused_impact)
    payload["source_scan_selection_truncated"] = source_scan_truncated
    if ide_links:
        payload["local_ide_root"] = root.as_posix()
    from .file_coverage import tracked_python
    inventory = tracked_python(root)
    graph_files = {row.get("source_file") for row in graph["nodes"]
                   if isinstance(row.get("source_file"), str)}
    missing = sorted(set(inventory) - graph_files)
    payload["file_coverage"] = {
        "tracked": len(inventory), "represented": len(inventory) - len(missing),
        "missing_total": len(missing), "missing_examples": missing[:60],
        "truncated": len(missing) > 60,
        "status": "HISTORICAL" if stale else "CURRENT_SNAPSHOT",
        "runtime_proof": False,
    }
    saved_snapshot = None
    if save_snapshot:
        if stale:
            return {"status": "BLOCKED", "reason": "Cannot snapshot a stale graph as current."}
        try:
            saved_snapshot = save_graph_snapshot(root, Path(status["graph"]), snapshot_commit)
        except (OSError, ValueError) as exc:
            return {"status": "BLOCKED", "reason": str(exc)}
    destination = root / "graphify-out" / "doctor_graph.html"
    destination.write_text(render_html(payload), encoding="utf-8")
    return {
        "status": "REVIEW" if stale else "PASS",
        "candidate_sha": snapshot_commit, "graph_status": status["status"],
        "path": str(destination), "trace_status": payload["trace_status"],
        "runtime_trace_sources": len(trace_files),
        "nodes_shown": len(payload["nodes"]),
        "links_shown": len(payload["edges"]), "truncated": payload["truncated"],
        "source_inspection": payload["source_inspection_status"],
        "source_scan_files": payload["source_inspection_files"],
        "focused_impact_status": focused_impact["status"] if focused_impact else "NOT_REQUESTED",
        "focused_consumer_count": focused_impact["direct_consumers"] + focused_impact["indirect_consumers"] if focused_impact else 0,
        "json_lineage_review_leads": payload["json_lineage_review_leads"],
        "baseline_sha": comparison["baseline_sha"] if comparison else None,
        "snapshot_comparison_status": comparison["status"] if comparison else "NOT_PROVIDED",
        "saved_snapshot": saved_snapshot,
        "historical_trend_status": historical_trend["status"] if historical_trend else "NOT_PROVIDED",
        "source_scan_truncated": source_scan_truncated or payload["source_inspection_truncated"],
        "tests_executed": False, "graph_rebuilt": False,
    }
