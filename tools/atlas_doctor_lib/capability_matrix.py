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


def _call_names(root: Path, path: str) -> set[str] | None:
    source = root / path
    try:
        if (source.is_symlink() or not source.is_file()
                or not source.resolve().is_relative_to(root)
                or source.stat().st_size > 512 * 1024):
            return None
        tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=path)
    except (OSError, ValueError, SyntaxError, UnicodeError):
        return None
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            found.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            found.add(node.func.attr)
    return found


def capability_inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    library = root / "tools" / "atlas_doctor_lib"
    symbols: dict[str, set[str] | None] = {}
    rows: list[dict[str, Any]] = []
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
                declared = set()
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        declared.add(node.name)
                        if isinstance(node, ast.ClassDef):
                            for method in node.body:
                                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                    declared.add(node.name + "." + method.name)
                symbols[file] = declared
            except (OSError, ValueError, SyntaxError, UnicodeError):
                symbols[file] = None
        present = symbols[file] is not None and symbol in symbols[file]
        site, called = WIRED_AT[ident]
        calls = wiring_cache.get(site)
        wired = calls is not None and called in calls
        rows.append({
            "id": ident, "engine": engine, "name": name,
            "wiring_status": "AST_CALLSITE_PRESENT" if wired else "CALLSITE_NOT_FOUND",
            "wiring_source": site, "called_symbol": called,
            "source_anchor": "PRESENT" if present else "MISSING",
            "source_path": "tools/atlas_doctor_lib/" + file,
            "callable": symbol, "behavior_certified": False,
        })
    missing = sum(row["source_anchor"] == "MISSING" for row in rows)
    unwired = sum(row["wiring_status"] != "AST_CALLSITE_PRESENT" for row in rows)
    return {
        "kind": "doctor_capabilities", "count": len(rows),
        "source_present": len(rows) - missing, "source_missing": missing,
        "call_sites_wired": len(rows) - unwired, "call_sites_missing": unwired,
        "status": "BLOCKED" if missing or unwired else "REVIEW_PENDING_FINAL_CERTIFICATION",
        "capabilities": rows, "certified_count": 0,
        "tests_executed": False, "graph_rebuilt": False,
        "limits": "AST definitions and AST call-sites are integration evidence only, not proof of behavior. Every capability requires exact-SHA behavioral, Qt, Graphify and applicable RAM/CI certification.",
    }
