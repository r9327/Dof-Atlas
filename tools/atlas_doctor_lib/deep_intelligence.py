from __future__ import annotations

"""Small, read-only source intelligence; findings are evidence, not deletions."""
import ast
import hashlib
import json
import re
import subprocess
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

MAX_FILES = 150
MAX_SOURCE_BYTES = 512 * 1024
MAX_FUNCTIONS = 4000
MAX_FINDINGS = 80


def _shape(node: Any) -> Any:
    """Similar syntax is a review lead, never equivalent behavior."""
    if isinstance(node, ast.Name):
        return ("Name", type(node.ctx).__name__)
    if isinstance(node, ast.arg):
        return ("arg",)
    if isinstance(node, ast.Constant):
        return ("Constant", type(node.value).__name__)
    if isinstance(node, ast.AST):
        return (type(node).__name__, tuple(
            (field, _shape(value)) for field, value in ast.iter_fields(node)
        ))
    if isinstance(node, list):
        return tuple(_shape(item) for item in node)
    return node



def _relative(root: Path, value: str) -> str | None:
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return None
    try:
        requested = root / path
        if requested.is_symlink():
            return None
        resolved = requested.resolve()
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
    similar: dict[str, list[dict[str, Any]]] = defaultdict(list)
    function_count = 0
    function_cap_reached = False
    for path in selected[:MAX_FILES]:
        try:
            candidate = root / path
            if candidate.stat().st_size > MAX_SOURCE_BYTES:
                errors.append({"path": path, "reason": "SOURCE_SIZE_BUDGET_EXCEEDED"})
                continue
            tree = ast.parse(candidate.read_text(encoding="utf-8-sig"), filename=path)
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append({"path": path, "reason": type(exc).__name__})
            continue
        inspected.append(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if function_count >= MAX_FUNCTIONS:
                    function_cap_reached = True
                    continue
                function_count += 1
                # Canonical AST ignores local variable spelling/formatting only where
                # syntax itself is identical. Near-duplicates need human review.
                body = ast.Module(body=node.body, type_ignores=[])
                fingerprint = hashlib.sha256(ast.dump(body, include_attributes=False).encode()).hexdigest()
                item = {"path": path, "line": node.lineno, "symbol": node.name}
                functions[fingerprint].append(item)
                if len(node.body) >= 3 and sum(1 for _ in ast.walk(body)) >= 18:
                    shape_key = hashlib.sha256(repr(_shape(body)).encode()).hexdigest()
                    similar[shape_key].append({**item, "exact": fingerprint})
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
    near = [
        {"kind": "SIMILAR_AST_SHAPE", "occurrences": [
            {k: row[k] for k in ("path", "line", "symbol")} for row in rows
        ], "review_only": True, "semantic_equivalence_proven": False}
        for rows in similar.values() if len(rows) > 1
        and len({row["exact"] for row in rows}) > 1
    ]
    near.sort(key=lambda x: (-len(x["occurrences"]), x["occurrences"][0]["path"]))
    truncated = (len(selected) > MAX_FILES or function_cap_reached or bool(errors)
                 or len(duplicates) > MAX_FINDINGS or len(near) > MAX_FINDINGS
                 or len(silent) > MAX_FINDINGS or len(lineage) > MAX_FINDINGS)
    return {
        "status": "REVIEW" if truncated else "PASS",
        "paths_inspected": inspected, "requested_count": len(requested),
        "parse_errors": errors[:MAX_FINDINGS], "duplicate_bodies": duplicates[:MAX_FINDINGS],
        "near_duplicate_candidates": near[:MAX_FINDINGS],
        "silent_exceptions": silent[:MAX_FINDINGS],
        "data_lineage_candidates": lineage[:MAX_FINDINGS],
        "counts": {"functions": function_count,
                   "duplicate_groups": len(duplicates), "near_duplicate_groups": len(near),
                   "silent_exceptions": len(silent),
                   "literal_json_references": len(lineage)},
        "truncated": truncated,
        "budgets": {"max_files": MAX_FILES, "max_source_bytes": MAX_SOURCE_BYTES,
                    "max_function_bodies": MAX_FUNCTIONS, "function_limit_reached": function_cap_reached},
        "limits": "Bounded AST only; oversized sources are REVIEW; near duplicates are review leads, not safe automatic edits.",
    }


def launcher_entrypoints(root: Path) -> dict[str, Any]:
    """Read only literal DOFUS.bat startup declarations (never execute BAT)."""
    launcher = root / "DOFUS.bat"
    if launcher.is_symlink() or not launcher.is_file():
        return {"status": "REVIEW", "entrypoints": ["main.py"],
                "source": "DOFUS.bat", "reason": "Launcher unavailable"}
    try:
        if launcher.stat().st_size > 65536:
            raise ValueError("Batch launcher exceeds 64 KiB")
        lines = launcher.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError, ValueError) as exc:
        return {"status": "REVIEW", "entrypoints": ["main.py"],
                "source": "DOFUS.bat", "reason": type(exc).__name__}
    declared: set[str] = set()
    for line in lines:
        line = line.strip()
        if not line or line.lower().startswith(("rem ", "::")):
            continue
        match = re.fullmatch(
            r'set\s+"APP_SCRIPT=%ROOT%([a-zA-Z0-9_./\\-]+\.py)"',
            line, flags=re.IGNORECASE,
        )
        if match:
            declared.add(match.group(1).replace("\\", "/"))
        for module in re.findall(r'(?:^|\s)-m\s+([a-zA-Z_][a-zA-Z0-9_.]*)', line):
            declared.add(module.replace(".", "/") + ".py")
    found = sorted(path for path in declared if _relative(root, path) is not None)
    missing = sorted(declared.difference(found))
    return {
        "status": "PASS" if found and not missing else "REVIEW",
        "entrypoints": found or ["main.py"], "source": "DOFUS.bat",
        "unresolved_declarations": missing[:10],
        "execution_proven": False,
        "scope": "Static launcher declarations only, no process was launched.",
    }


def graph_reachability(graph: dict[str, Any], entrypoints: list[str],
                       trace: dict[str, Any] | None = None) -> dict[str, Any]:
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
    trace_sha, graph_sha = ((trace or {}).get("candidate_sha"),
                            graph.get("built_at_commit"))
    events = (trace or {}).get("events", [])
    valid_trace = (trace is not None and isinstance(graph_sha, str)
                   and len(graph_sha) == 40 and trace_sha == graph_sha
                   and trace.get("worktree_clean") is True
                   and trace.get("truncated") is False
                   and isinstance(events, list) and len(events) <= 50000)
    runtime_pairs: set[tuple[str, str]] = set()
    qt_registered: set[str] = set()
    if valid_trace:
        for item in events:
            if not isinstance(item, dict):
                continue
            source, target = item.get("source"), item.get("target")
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            if source not in files or target not in files or source == target:
                continue
            if item.get("type") == "python_call_edge":
                adjacency[source].add(target)
                runtime_pairs.add((source, target))
            elif item.get("type") == "qt_signal_connect_returned":
                qt_registered.add(target)
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
        "status": "REVIEW" if missing or (trace is not None and not valid_trace) else "PASS",
        "entrypoints_found": known, "entrypoints_missing_from_graph": missing,
        "reachable_files": len(visited), "graph_files": len(files),
        "unreached_candidates": sorted(files - visited)[:MAX_FINDINGS],
        "unreached_total": len(files - visited),
        "runtime_trace_status": ("NOT_PROVIDED" if trace is None else
                                 "MATCHED" if valid_trace else "STALE_OR_INCOMPLETE"),
        "observed_python_call_edges": len(runtime_pairs),
        "qt_registered_but_not_invoked_candidates": sorted(qt_registered)[:MAX_FINDINGS],
        "proof_of_dead_code": False,
        "coverage": "Static imports and opt-in exact-SHA observed Python calls; Qt registration is not invocation. Unobserved never means dead.",
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
                 baseline: Path | None = None,
                 trace_path: Path | None = None) -> dict[str, Any]:
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
            trace = None
            if trace_path is not None:
                selected = trace_path.resolve()
                if not selected.is_relative_to(root / ".ai" / "runtime"):
                    raise ValueError("Runtime trace must stay in .ai/runtime")
                if not selected.is_file() or selected.stat().st_size > 10_000_000:
                    raise ValueError("Runtime trace missing or exceeds 10 MB")
                trace = json.loads(selected.read_text(encoding="utf-8"))
                if not isinstance(trace, dict):
                    raise ValueError("Invalid runtime trace JSON")
            launcher = (
                {"status": "PASS", "source": "explicit CLI", "entrypoints": list(entrypoints)}
                if entrypoints else launcher_entrypoints(root)
            )
            reach = graph_reachability(graph, launcher["entrypoints"], trace=trace)
            reach["entrypoint_discovery"] = launcher
            if launcher["status"] != "PASS":
                reach["status"] = "REVIEW"
            rules = architectural_guardrails(graph, old)
            # Source confirmation already exists in graph_audit, do not duplicate it.
            from .graph_audit import inspect_graph
            findings = inspect_graph(graph, root=root)
            confirmed = findings.get("blocking_findings", [])
            new_edges = {
                (row["source"], row["target"])
                for row in rules.get("new_candidate_violations", [])
            }
            # Without a baseline, a source-confirmed forbidden edge is real
            # but its introduction date is unknown: REVIEW rather than CI FAIL.
            rules["confirmed_blockers"] = [
                row for row in confirmed
                if old is not None and (row.get("source"), row.get("target")) in new_edges
            ]
            rules["historical_or_unbased_confirmed"] = [
                row for row in confirmed if row not in rules["confirmed_blockers"]
            ][:MAX_FINDINGS]
            if rules["confirmed_blockers"]:
                rules["status"] = "BLOCKED"
            elif rules["historical_or_unbased_confirmed"] and old is None:
                rules["status"] = "REVIEW"
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
