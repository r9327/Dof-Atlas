from __future__ import annotations

"""Bounded, source-only method inventory compared with opt-in function entries.

No import of application modules and no negative "dead code" inference.
The caller must pass an exact-SHA, clean, complete runtime scenario.
"""
import ast
from pathlib import Path
from typing import Any

from .scenario_coverage import observed_entered_symbols

MAX_FILES = 8
MAX_BYTES = 512 * 1024
MAX_SOURCE_SYMBOLS = 320
MAX_PER_FILE = 80
MAX_EVENTS = 50000


def _functions(tree: ast.Module) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []

    def visit(body: list[ast.stmt], scope: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                qualified = f"{scope}.{node.name}" if scope else node.name
                visit(node.body, qualified)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{scope}.{node.name}" if scope else node.name
                rows.append((node.lineno, qualified))
                # Python runtime qualnames put <locals> before nested functions.
                visit(node.body, qualified + ".<locals>")
    visit(tree.body, "")
    return rows


def compare_source_functions(root: Path, paths: list[str],
                             trace: dict[str, Any], *, expected_sha: str) -> dict[str, Any]:
    root = root.resolve()
    if not 1 <= len(paths) <= MAX_FILES:
        raise ValueError("Expected 1..8 focused source files")
    events = trace.get("events") if isinstance(trace, dict) else None
    if (not isinstance(trace, dict)
            or trace.get("kind") != "doctor_runtime_observation"
            or trace.get("candidate_sha") != expected_sha
            or len(expected_sha) != 40
            or trace.get("worktree_clean") is not True
            or trace.get("truncated") is not False
            or not isinstance(events, list) or len(events) > MAX_EVENTS
            or not all(isinstance(row, dict) for row in events)):
        return {
            "status": "UNAVAILABLE", "reason": "Complete clean exact-SHA runtime trace required",
            "files": [], "dead_code_proven": False, "tests_executed": False,
        }
    observed: set[str] = set()
    for event in events:
        observed.update(observed_entered_symbols(event))
    result_files: list[dict[str, Any]] = []
    total_defined = total_observed = 0
    truncated = False
    for name in list(dict.fromkeys(paths)):
        relative = Path(name)
        selected = root / relative
        if (relative.is_absolute() or relative.suffix != ".py"
                or "\\" in name or any(part in {"", ".", ".."} for part in relative.parts)
                or selected.is_symlink() or not selected.is_file()
                or not selected.resolve().is_relative_to(root)):
            return {"status": "UNAVAILABLE", "reason": "Unsafe or missing focused Python file",
                    "files": [], "dead_code_proven": False, "tests_executed": False}
        try:
            if selected.stat().st_size > MAX_BYTES:
                return {"status": "UNAVAILABLE", "reason": "Focused source over 512 KiB",
                        "files": [], "dead_code_proven": False, "tests_executed": False}
            tree = ast.parse(selected.read_text(encoding="utf-8-sig"), filename=name)
        except (OSError, UnicodeError, SyntaxError, ValueError):
            return {"status": "UNAVAILABLE", "reason": "Failed to parse focused Python file",
                    "files": [], "dead_code_proven": False, "tests_executed": False}
        functions = _functions(tree)
        total_defined += len(functions)
        if (len(functions) > MAX_PER_FILE or total_defined > MAX_SOURCE_SYMBOLS):
            truncated = True
        displayed = []
        observed_here = 0
        for lineno, symbol in functions:
            positive = f"{name}::{symbol}" in observed
            observed_here += bool(positive)
            if len(displayed) < MAX_PER_FILE and sum(len(f["symbols"]) for f in result_files) + len(displayed) < MAX_SOURCE_SYMBOLS:
                displayed.append({
                    "line": lineno, "symbol": symbol,
                    "entry_observed": positive,
                    "unobserved_is_not_dead": True,
                })
        total_observed += observed_here
        result_files.append({
            "path": name, "defined": len(functions), "entered": observed_here,
            "not_observed": len(functions) - observed_here,
            "symbols": displayed,
            "truncated": len(displayed) != len(functions),
        })
    return {
        "kind": "doctor_source_function_scenario_review",
        "status": "REVIEW" if truncated else "SCENARIO_EVIDENCE_ONLY",
        "candidate_sha": expected_sha, "files": result_files,
        "defined_total": total_defined, "entered_total": total_observed,
        "not_observed_total": total_defined - total_observed,
        "truncated": truncated, "dead_code_proven": False,
        "safe_to_delete": False, "tests_executed": False,
        "limits": "Only Python source definitions and positive opt-in exact-SHA entries. Decorator wrappers, dynamic attribute dispatch and unvisited scenarios may hide valid use. Missing an entry is not dead code.",
    }
