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


def capability_inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    library = root / "tools" / "atlas_doctor_lib"
    symbols: dict[str, set[str] | None] = {}
    rows: list[dict[str, Any]] = []
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
        rows.append({
            "id": ident, "engine": engine, "name": name,
            "source_anchor": "PRESENT" if present else "MISSING",
            "source_path": "tools/atlas_doctor_lib/" + file,
            "callable": symbol, "behavior_certified": False,
        })
    missing = sum(row["source_anchor"] == "MISSING" for row in rows)
    return {
        "kind": "doctor_capabilities", "count": len(rows),
        "source_present": len(rows) - missing, "source_missing": missing,
        "status": "BLOCKED" if missing else "REVIEW_PENDING_FINAL_CERTIFICATION",
        "capabilities": rows, "certified_count": 0,
        "tests_executed": False, "graph_rebuilt": False,
        "limits": "AST presence is not functionality. Every capability still requires exact-SHA behavioral, Qt, Graphify and applicable RAM/CI proof.",
    }
