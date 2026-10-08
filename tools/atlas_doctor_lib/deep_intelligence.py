from __future__ import annotations

"""Small, read-only source intelligence; findings are evidence, not deletions."""
import ast
import hashlib
import json
import subprocess
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

MAX_FILES = 150
MAX_FUNCTIONS = 4000
MAX_FINDINGS = 80


def _relative(root: Path, value: str) -> str | None:
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return None
    try:
        resolved = (root / path).resolve()
        relative = resolved.relative_to(root).as_posix()
    except (OSError, ValueError):
        return None
    if resolved.is_symlink() or not resolved.is_file() or not relative.endswith(".py"):
        return None
    return relative


def scan_sources(root: Path, paths: list[str]) -> dict[str, Any]:
    """AST evidence, bounded by requested files; never imports project code."""
    root = root.resolve()
    requested = sorted(set(paths))
    selected = [_relative(root, path) for path in requested]
    invalid = [path for path, result in zip(requested, selected) if result is None]
    if invalid:
        return {"status": "BLOCKED", "reason": "Invalid or missing Python paths", "paths": invalid[:10]}
    selected = [path for path in selected if path is not None]
    inspected, errors, functions, silent, lineage = [], [], defaultdict(list), [], []
    for path in selected[:MAX_FILES]:
        try:
            tree = ast.parse((root / path).read_text(encoding="utf-8-sig"), filename=path)
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append({"path": path, "reason": str(exc)})
            continue
        inspected.append(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Canonical AST ignores local variable spelling/formatting only where
                # syntax itself is identical. Near-duplicates need human review.
                body = ast.Module(body=node.body, type_ignores=[])
                fingerprint = hashlib.sha256(ast.dump(body, include_attributes=False).encode()).hexdigest()
                functions[fingerprint].append({"path": path, "line": node.lineno, "symbol": node.name})
            if isinstance(node, ast.ExceptHandler):
                content = [item for item in node.body if not (
                    isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant)
                    and isinstance(item.value.value, str)
                )]
                if len(content) == 1 and (
                    isinstance(content[0], ast.Pass)
                    or (isinstance(content[0], ast.Return) and (
                        content[0].value is None or isinstance(content[0].value, ast.Constant)
                    ))
                ):
                    silent.append({"path": path, "line": node.lineno,
                                   "kind": "SWALLOWED_EXCEPTION_CANDIDATE",
                                   "confidence": "SOURCE_PATTERN_REVIEW"})
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value.replace("\\", "/")
                if value.endswith(".json") and len(value) <= 240 and "\n" not in value:
                    lineage.append({"path": path, "line": node.lineno,
                                    "data_reference": value, "confidence": "LITERAL_ONLY"})
    duplicates = [
        {"kind": "EXACT_AST_BODY", "occurrences": rows, "review_only": True}
        for rows in functions.values() if len(rows) > 1
        and len({(x["path"], x["line"]) for x in rows}) > 1
    ]
    duplicates.sort(key=lambda item: (-len(item["occurrences"]), item["occurrences"][0]["path"]))
    truncated = len(selected) > MAX_FILES or len(functions) > MAX_FUNCTIONS
    return {
        "status": "REVIEW" if truncated or errors else "PASS",
        "paths_inspected": inspected, "requested_count": len(requested),
        "parse_errors": errors[:MAX_FINDINGS], "duplicate_bodies": duplicates[:MAX_FINDINGS],
        "silent_exceptions": silent[:MAX_FINDINGS],
        "data_lineage_candidates": lineage[:MAX_FINDINGS],
        "counts": {"functions": sum(len(x) for x in functions.values()),
                   "duplicate_groups": len(duplicates), "silent_exceptions": len(silent),
                   "literal_json_references": len(lineage)},
        "truncated": truncated or len(duplicates) > MAX_FINDINGS
        or len(silent) > MAX_FINDINGS or len(lineage) > MAX_FINDINGS,
        "limits": "AST-only, literal JSON strings are leads not confirmed data flows; no automatic edits.",
    }


def graph_reachability(graph: dict[str, Any], entrypoints: list[str]) -> dict[str, Any]:
    """Conservative reachability over extracted import edges in Graphify data."""
    nodes = {item["id"]: item for item in graph.get("nodes", [])}
    files = {item.get("source_file") for item in nodes.values()
             if isinstance(item.get("source_file"), str)}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.get("links", []):
        if edge.get("relation") not in {"imports", "imports_from"}:
            continue
        if edge.get("confidence") != "EXTRACTED" or edge.get("_origin") != "ast":
            continue
        first, second = nodes.get(edge.get("source")), nodes.get(edge.get("target"))
        if first is None or second is None:
            continue
        source, target = first.get("source_file"), second.get("source_file")
        if isinstance(source, str) and isinstance(target, str) and source != target:
            adjacency[source].add(target)
    known = sorted(set(entrypoints) & files)
    visited = set(known)
    frontier = deque(known)
    while frontier:
        for target in adjacency.get(frontier.popleft(), ()):
            if target not in visited:
                visited.add(target)
                frontier.append(target)
    missing = sorted(set(entrypoints) - files)
    return {
        "status": "REVIEW" if missing else "PASS",
        "entrypoints_found": known, "entrypoints_missing_from_graph": missing,
        "reachable_files": len(visited), "graph_files": len(files),
        "unreached_candidates": sorted(files - visited)[:MAX_FINDINGS],
        "unreached_total": len(files - visited),
        "proof_of_dead_code": False,
        "coverage": "Extracted static imports only; dynamic imports, Qt callbacks and entrypoints not listed remain unknown.",
    }


def architectural_guardrails(
    current: dict[str, Any], baseline: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Compare forbidden app->tools edges. Old debt stays advisory, new debt blocks only if proven elsewhere."""
    def edges(graph: dict[str, Any]) -> set[tuple[str, str]]:
        nodes = {x["id"]: x for x in graph.get("nodes", [])}
        result = set()
        for item in graph.get("links", []):
            if item.get("relation") not in {"imports", "imports_from"} or item.get("confidence") != "EXTRACTED":
                continue
            first, second = nodes.get(item.get("source")), nodes.get(item.get("target"))
            if first and second:
                source, target = first.get("source_file"), second.get("source_file")
                if isinstance(source, str) and isinstance(target, str) and source.startswith("app/") and target.startswith("tools/"):
                    result.add((source, target))
        return result
    now = edges(current)
    before = edges(baseline) if baseline is not None else set()
    return {
        "status": "REVIEW" if now - before else "PASS",
        "new_candidate_violations": [{"source": a, "target": b} for a, b in sorted(now - before)[:MAX_FINDINGS]],
        "historical_candidates": len(now & before),
        "confirmed_blockers": [],
        "rule": "app/ must not import tools/",
        "limits": "Graph candidates alone cannot block CI; re-check AST source before hard failure.",
    }


def inspect_code(root: Path, *, paths: list[str],
                 entrypoints: list[str] | None = None,
                 baseline: Path | None = None) -> dict[str, Any]:
    from .architecture import graph_status
    root = root.resolve()
    source = scan_sources(root, paths)
    graph_evidence = graph_status(root)
    reach: dict[str, Any] = {"status": "UNAVAILABLE", "reason": "Current exact-SHA graph required."}
    rules: dict[str, Any] = {"status": "UNAVAILABLE"}
    if graph_evidence["status"] == "PASS":
        try:
            graph = json.loads(Path(graph_evidence["graph"]).read_text(encoding="utf-8"))
            old = json.loads(baseline.read_text(encoding="utf-8")) if baseline else None
            reach = graph_reachability(graph, entrypoints or ["main.py", "tools/atlas_doctor.py"])
            rules = architectural_guardrails(graph, old)
            # Source confirmation already exists in graph_audit, do not duplicate it.
            from .graph_audit import inspect_graph
            findings = inspect_graph(graph, root=root)
            rules["confirmed_blockers"] = findings.get("blocking_findings", [])
            if rules["confirmed_blockers"]:
                rules["status"] = "BLOCKED"
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            reach = {"status": "UNAVAILABLE", "reason": str(exc)}
            rules = {"status": "UNAVAILABLE", "reason": str(exc)}
    return {
        "schema_version": 1, "kind": "doctor_code_inspection",
        "status": "BLOCKED" if source["status"] == "BLOCKED" or rules["status"] == "BLOCKED"
        else "REVIEW" if source["status"] != "PASS" or graph_evidence["status"] != "PASS"
        or reach["status"] != "PASS" or rules["status"] != "PASS" else "PASS",
        "source": source, "graph_status": graph_evidence["status"],
        "reachability": reach, "architectural_rules": rules,
        "tests_executed": False, "graph_rebuilt": False,
    }
