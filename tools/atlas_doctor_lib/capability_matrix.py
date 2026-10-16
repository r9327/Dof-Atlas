from __future__ import annotations

"""Read-only source ledger of Doctor's 18 capabilities, never a PASS gate."""
import ast
from pathlib import Path
from typing import Any

# 4 Graph, 5 Runtime, 4 Change, 3 Test, 2 UI = 18.
CAPABILITIES = (
    ("G01", "Graph", "File map coverage", "file_coverage.py", "file_coverage"),
    ("G02", "Graph", "Confirmed import cycles", "graph_intelligence.py", "inspect_import_cycles"),
    ("G03", "Graph", "Community cohesion", "graph_intelligence.py", "analyze_community_boundaries"),
    ("G04", "Graph", "Reachability and lineage", "deep_intelligence.py", "graph_reachability"),
    ("R05", "Runtime", "Opt-in Python calls", "runtime_observation.py", "RuntimeObserver._profile"),
    ("R06", "Runtime", "Import and filesystem attempts", "runtime_observation.py", "RuntimeObserver._audit_event"),
    ("R07", "Runtime", "Qt callback proof", "runtime_observation.py", "RuntimeObserver.wrap_qt_slot"),
    ("R08", "Runtime", "Qt worker lifecycle", "runtime_observation.py", "RuntimeObserver.watch_qt_thread"),
    ("R09", "Runtime", "Qt native and WebEngine snapshots", "runtime_observation.py", "RuntimeObserver.snapshot_qt_objects"),
    ("C10", "Change", "Git diff/rename planning", "change_intelligence.py", "build_change_plan"),
    ("C11", "Change", "Source-confirmed consumers", "source_impact.py", "source_reverse_impact"),
    ("C12", "Change", "Refactor preview", "refactor_simulation.py", "simulate_refactor"),
    ("C13", "Change", "Historical scenario regressions", "scenario_trends.py", "summarize_scenario_trend"),
    ("T14", "Test", "Targeted suite planning", "test_intelligence.py", "suggest_targeted_test_order"),
    ("T15", "Test", "Historical test costs", "test_intelligence.py", "test_cost_report"),
    ("T16", "Test", "Scenario execution coverage", "scenario_coverage.py", "summarize_scenarios"),
    ("U17", "UI", "Interactive Graphify view", "doctor_graph_ui.py", "render_html"),
    ("U18", "UI", "Live Graphify dev view", "live_graph.py", "serve_graph_live"),
)


# Explicit read-only call-site contracts. A matching AST call does not
# certify that the call succeeds, only that its source-level wiring exists.
WIRED_AT = {
    "G01": ("tools/atlas_doctor.py", "file_coverage"),
    "G02": ("tools/atlas_doctor_lib/graph_audit.py", "inspect_import_cycles"),
    "G03": ("tools/atlas_doctor_lib/graph_audit.py", "analyze_community_boundaries"),
    "G04": ("tools/atlas_doctor.py", "inspect_code"),
    "R05": ("tools/atlas_doctor.py", "run_traced_module"),
    "R06": ("tools/atlas_doctor.py", "run_traced_module"),
    "R07": ("tools/atlas_doctor_lib/qt_smoke_scenario.py", "wrap_qt_slot"),
    "R08": ("tools/atlas_doctor_lib/qt_smoke_scenario.py", "watch_qt_thread"),
    "R09": ("tools/atlas_doctor_lib/webengine_lifecycle_scenario.py", "snapshot_qt_objects"),
    "C10": ("tools/atlas_doctor.py", "build_change_plan"),
    "C11": ("tools/atlas_doctor_lib/integrated_investigation.py", "source_reverse_impact"),
    "C12": ("tools/atlas_doctor.py", "simulate_refactor"),
    "C13": ("tools/atlas_doctor_lib/doctor_graph_ui.py", "load_scenario_trend"),
    "T14": ("tools/atlas_doctor_lib/integrated_investigation.py", "suggest_targeted_test_order"),
    "T15": ("tools/atlas_doctor_lib/integrated_investigation.py", "test_cost_report"),
    "T16": ("tools/atlas_doctor_lib/integrated_investigation.py", "summarize_scenarios"),
    "U17": ("tools/atlas_doctor_lib/doctor_graph_ui.py", "render_html"),
    "U18": ("tools/atlas_doctor.py", "serve_graph_live"),
}


# Real behavioral regression witnesses already included in Graphify Focused.
# Source anchors are not a PASS claim or a substitute for exact-SHA job logs.
BEHAVIOR_ANCHORS = {
    "G01": ("test_atlas_doctor_file_coverage.py", "test_gaps_are_reported_without_claiming_dead_code"),
    "G02": ("test_atlas_doctor_graph_intelligence.py", "test_type_checking_and_lazy_cycles_are_not_import_time_cycles"),
    "G03": ("test_atlas_doctor_graph_intelligence.py", "test_community_review_never_forces_merges"),
    "G04": ("test_atlas_doctor_deep_intelligence.py", "test_reachability_labels_unobserved_not_dead"),
    "R05": ("test_atlas_doctor_runtime_observation.py", "test_python_calls_are_observed_only_while_active"),
    "R06": ("test_atlas_doctor_runtime_observation.py", "test_real_source_file_open_is_attributed_to_test_script"),
    "R07": ("test_atlas_doctor_runtime_observation.py", "test_qt_connection_unwraps_instrumentation_to_real_callback_file"),
    "R08": ("test_atlas_doctor_runtime_observation.py", "test_qt_worker_started_finished_signals_observed_without_strong_ownership"),
    "R09": ("test_atlas_doctor_runtime_observation.py", "test_weak_watch_snapshot_is_observational_not_leak_evidence"),
    "C10": ("test_atlas_doctor_change_intelligence.py", "test_relative_and_dynamic_literals_are_detected"),
    "C11": ("test_atlas_doctor_source_impact.py", "test_static_relative_import_and_literal_dynamic_lead_are_separate"),
    "C12": ("test_atlas_doctor_refactor_simulation.py", "test_simulation_preserves_hard_validation_and_never_edits"),
    "C13": ("test_atlas_doctor_scenario_trends.py", "test_repeated_absence_is_review_not_functional_regression"),
    "T14": ("test_atlas_doctor_test_intelligence.py", "test_advisory_order_keeps_all_required_groups_and_full_suite"),
    "T15": ("test_atlas_doctor_test_intelligence.py", "test_real_successful_costs_exclude_reused_full_and_failures"),
    "T16": ("test_atlas_doctor_scenario_coverage.py", "test_multiple_scenarios_accumulate_only_positive_exact_sha_coverage"),
    "U17": ("test_atlas_doctor_graph_ui.py", "test_generated_interactive_javascript_passes_node_syntax_check"),
    "U18": ("test_atlas_doctor_live_graph.py", "test_live_graph_adds_actual_local_import_edges_without_graph_rebuild"),
}


def _test_case_defined(root: Path, file: str, name: str) -> bool:
    """Find an actual test method without importing or executing any code."""
    # Windows temporary roots can be junctions/aliases. Resolve both sides
    # before testing confinement, while still rejecting source symlinks.
    root = root.resolve()
    source = root / "tests" / file
    try:
        if (source.is_symlink() or not source.is_file()
                or not source.resolve().is_relative_to(root)
                or source.stat().st_size > 512 * 1024):
            return False
        tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=file)
    except (OSError, ValueError, SyntaxError, UnicodeError):
        return False
    return any(
        isinstance(cls, ast.ClassDef)
        and any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name for node in cls.body)
        for cls in tree.body
    )


def _call_names(root: Path, path: str) -> dict[str, list[int]] | None:
    root = root.resolve()
    source = root / path
    try:
        if (source.is_symlink() or not source.is_file()
                or not source.resolve().is_relative_to(root)
                or source.stat().st_size > 512 * 1024):
            return None
        tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=path)
    except (OSError, ValueError, SyntaxError, UnicodeError):
        return None
    found: dict[str, list[int]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = (node.func.id if isinstance(node.func, ast.Name)
                  else node.func.attr if isinstance(node.func, ast.Attribute)
                  else None)
        if called:
            found.setdefault(called, []).append(node.lineno)
    return {name: sorted(set(lines)) for name, lines in found.items()}


def capability_inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    library = root / "tools" / "atlas_doctor_lib"
    symbols: dict[str, dict[str, int] | None] = {}
    rows: list[dict[str, Any]] = []
    test_cache = {
        ident: _test_case_defined(root, *BEHAVIOR_ANCHORS[ident])
        for ident, *_ in CAPABILITIES
    }
    wiring_cache = {path: _call_names(root, path)
                    for path in {path for path, _ in WIRED_AT.values()}}
    for ident, engine, name, file, symbol in CAPABILITIES:
        if file not in symbols:
            candidate = library / file
            try:
                if (candidate.is_symlink() or not candidate.is_file()
                        or not candidate.resolve().is_relative_to(root)
                        or candidate.stat().st_size > 512 * 1024):
                    raise ValueError("Unsafe or unavailable source")
                tree = ast.parse(candidate.read_text(encoding="utf-8-sig"))
                declared: dict[str, int] = {}
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        declared[node.name] = node.lineno
                        if isinstance(node, ast.ClassDef):
                            for method in node.body:
                                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                    declared[node.name + "." + method.name] = method.lineno
                symbols[file] = declared
            except (OSError, ValueError, SyntaxError, UnicodeError):
                symbols[file] = None
        present = symbols[file] is not None and symbol in symbols[file]
        site, called = WIRED_AT[ident]
        calls = wiring_cache.get(site)
        callsite_lines = calls.get(called, [])[:20] if calls is not None else []
        wired = bool(callsite_lines)
        rows.append({
            "id": ident, "engine": engine, "name": name,
            "wiring_status": "AST_CALLSITE_PRESENT" if wired else "CALLSITE_NOT_FOUND",
            "wiring_source": site, "called_symbol": called,
            "source_anchor": "PRESENT" if present else "MISSING",
            "source_path": "tools/atlas_doctor_lib/" + file,
            "definition_line": symbols[file].get(symbol) if symbols[file] else None,
            "callsite_lines": callsite_lines,
            "callsite_resolution": "AST_NAME_ONLY_UNVERIFIED" if wired else "UNAVAILABLE",
            "proof_status": "UNVERIFIED", "proven_defect": False,
            "behavior_test": "tests/" + BEHAVIOR_ANCHORS[ident][0] + "::" + BEHAVIOR_ANCHORS[ident][1],
            "behavior_test_anchor": "DEFINED" if test_cache[ident] else "MISSING",
            "behavior_test_executed": False,
            "behavior_test_result": "UNVERIFIED",
            "callable": symbol, "behavior_certified": False,
        })
    missing = sum(row["source_anchor"] == "MISSING" for row in rows)
    unwired = sum(row["wiring_status"] != "AST_CALLSITE_PRESENT" for row in rows)
    missing_behavior_anchors = sum(row["behavior_test_anchor"] != "DEFINED" for row in rows)
    return {
        "kind": "doctor_capabilities", "count": len(rows),
        "source_present": len(rows) - missing, "source_missing": missing,
        "call_sites_wired": len(rows) - unwired, "call_sites_missing": unwired,
        "behavior_test_anchors_defined": len(rows) - missing_behavior_anchors,
        "behavior_test_anchors_missing": missing_behavior_anchors,
        "status": "BLOCKED" if missing or unwired or missing_behavior_anchors
                  else "REVIEW_PENDING_FINAL_CERTIFICATION",
        "capabilities": rows, "certified_count": 0,
        "tests_executed": False, "graph_rebuilt": False,
        "limits": "AST definitions, call-sites and test-case names are only source anchors. Run evidence must be checked separately on the same SHA. Simulated Qt tests do not prove live Windows behavior, and test presence cannot certify test results.",
    }
