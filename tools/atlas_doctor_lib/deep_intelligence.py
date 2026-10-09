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


def _missing_internal_imports(root: Path, source: str, tree: ast.AST) -> list[dict[str, Any]]:
    """Bounded static candidates, never claim missing attributes are modules."""
    prefixes = {"app", "tools", "tests", "local_dofus_data"}
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for module in names:
            parts = module.split(".")
            if len(parts) < 2 or parts[0] not in prefixes:
                continue
            if not all(part.isidentifier() for part in parts):
                continue
            candidate = root.joinpath(*parts)
            if candidate.with_suffix(".py").is_file() or candidate.is_dir():
                continue
            findings.append({
                "path": source, "line": node.lineno, "module": module,
                "kind": "MISSING_LOCAL_MODULE_CANDIDATE",
                "confidence": "STATIC_ABSOLUTE_MODULE_RESOLUTION",
                "review_only": True,
            })
    return findings


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
    missing_imports: list[dict[str, Any]] = []
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
        missing_imports.extend(_missing_internal_imports(root, path, tree))
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
                 or len(missing_imports) > MAX_FINDINGS
                 or len(silent) > MAX_FINDINGS or len(lineage) > MAX_FINDINGS)
    return {
        "status": "REVIEW" if truncated or missing_imports else "PASS",
        "paths_inspected": inspected, "requested_count": len(requested),
        "parse_errors": errors[:MAX_FINDINGS], "duplicate_bodies": duplicates[:MAX_FINDINGS],
        "near_duplicate_candidates": near[:MAX_FINDINGS],
        "missing_internal_import_candidates": missing_imports[:MAX_FINDINGS],
        "silent_exceptions": silent[:MAX_FINDINGS],
        "data_lineage_candidates": lineage[:MAX_FINDINGS],
        "counts": {"functions": function_count,
                   "duplicate_groups": len(duplicates), "near_duplicate_groups": len(near),
                   "missing_internal_import_candidates": len(missing_imports),
                   "silent_exceptions": len(silent),
                   "literal_json_references": len(lineage)},
        "truncated": truncated,
        "budgets": {"max_files": MAX_FILES, "max_source_bytes": MAX_SOURCE_BYTES,
                    "max_function_bodies": MAX_FUNCTIONS, "function_limit_reached": function_cap_reached},
        "limits": "Bounded AST only; missing local imports and near duplicates are source-review leads, never automatic deletions.",
    }


def trace_literal_json_to_ui(
    graph: dict[str, Any], references: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bounded reverse AST-import paths, not proof of a JSON read or UI render.

    A UI file importing a service that contains a JSON string is a useful
    investigation lead, but that string need not ever be opened at runtime.
    """
    if not references:
        return {"status": "NOT_REQUIRED", "references": [], "truncated": False,
                "runtime_data_flow_proven": False}
    raw_nodes, raw_links = graph.get("nodes", []), graph.get("links", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_links, list):
        return {"status": "UNAVAILABLE", "reason": "Invalid graph payload",
                "references": [], "runtime_data_flow_proven": False}
    if len(raw_nodes) > 15000 or len(raw_links) > 50000:
        return {"status": "REVIEW", "reason": "Graph traversal budget exceeded",
                "references": [], "truncated": True, "runtime_data_flow_proven": False}
    node_files = {
        node.get("id"): node.get("source_file")
        for node in raw_nodes if isinstance(node, dict)
        and isinstance(node.get("id"), (int, str))
        and isinstance(node.get("source_file"), str)
    }
    reverse: dict[str, set[str]] = defaultdict(set)
    for link in raw_links:
        if not isinstance(link, dict) or link.get("relation") not in {"imports", "imports_from"}:
            continue
        if link.get("confidence") != "EXTRACTED" or link.get("_origin") != "ast":
            continue
        source, target = node_files.get(link.get("source")), node_files.get(link.get("target"))
        if source and target and source != target:
            reverse[target].add(source)

    def is_ui(path: str) -> bool:
        return (path.startswith(("app/pages/", "app/ui/"))
                or path.startswith("app/modules/") and
                ("/views/" in path or "/widgets/" in path))

    entries: list[dict[str, Any]] = []
    truncated = len(references) > MAX_FINDINGS
    for candidate in references[:MAX_FINDINGS]:
        source = candidate.get("path")
        if not isinstance(source, str):
            continue
        found: list[dict[str, Any]] = []
        frontier = deque([(source, 0)])
        visited = {source}
        while frontier:
            current, hops = frontier.popleft()
            if hops >= 4:
                if reverse.get(current):
                    truncated = True
                continue
            for importer in sorted(reverse.get(current, ())):
                if importer in visited:
                    continue
                if len(visited) >= 512:
                    truncated = True
                    break
                visited.add(importer)
                if is_ui(importer):
                    if len(found) >= 8:
                        truncated = True
                        break
                    found.append({"path": importer, "import_hops": hops + 1})
                frontier.append((importer, hops + 1))
        entries.append({
            "source": source, "line": candidate.get("line"),
            "data_reference": candidate.get("data_reference"),
            "possible_ui_importers": found, "confidence": "STATIC_IMPORT_PATH_ONLY",
            "data_read_proven": False, "ui_render_proven": False,
        })
    return {
        "status": "REVIEW", "references": entries,
        "references_with_ui_importers": sum(bool(x["possible_ui_importers"]) for x in entries),
        "truncated": truncated, "runtime_data_flow_proven": False,
        "limits": "Literal JSON strings + AST import paths, four hops, 512 files/reference, eight UI leads; no runtime data flow proof.",
    }



def trace_observed_json_to_ui(
    graph: dict[str, Any], trace: dict[str, Any] | None,
) -> dict[str, Any]:
    """Join observed JSON open attempts with observed Python call paths.

    Opening a file is not necessarily reading it, and co-observation does not
    prove that data reached a widget or was rendered to the screen.
    """
    empty = {
        "status": "NOT_PROVIDED" if trace is None else "STALE_OR_INCOMPLETE",
        "references": [], "json_opens_observed": 0, "truncated": False,
        "data_read_proven": False, "ui_render_proven": False,
    }
    if trace is None:
        return empty
    events = trace.get("events")
    sha = graph.get("built_at_commit")
    if (not isinstance(sha, str) or len(sha) != 40
            or trace.get("candidate_sha") != sha
            or trace.get("worktree_clean") is not True
            or trace.get("truncated") is not False
            or not isinstance(events, list) or len(events) > 50000
            or any(not isinstance(e, dict) for e in events)):
        return {**empty, "reason": "Exact SHA, complete events and clean worktree required."}
    files = {node.get("source_file") for node in graph.get("nodes", [])
             if isinstance(node, dict) and isinstance(node.get("source_file"), str)}
    reverse: dict[tuple[int, str], set[str]] = defaultdict(set)
    opened: set[tuple[int, str, str]] = set()

    def valid(path: Any, *, suffix: str) -> bool:
        return (isinstance(path, str) and path.endswith(suffix)
                and not path.startswith("/") and "\\" not in path
                and all(part not in {"", ".", ".."} for part in path.split("/")))

    for event in events:
        kind = event.get("type")
        source, target = event.get("source"), event.get("target")
        group = event.get("_trace_group", 0)
        if not isinstance(group, int) or isinstance(group, bool) or not 0 <= group < 8:
            continue
        if not valid(source, suffix=".py") or source not in files:
            continue
        if kind == "file_open" and valid(target, suffix=".json"):
            opened.add((group, source, target))
        elif (kind == "python_call_edge" and valid(target, suffix=".py")
              and target in files and target != source):
            reverse[(group, target)].add(source)

    def is_ui(path: str) -> bool:
        return (path.startswith(("app/pages/", "app/ui/"))
                or (path.startswith("app/modules/")
                    and ("/views/" in path or "/widgets/" in path)))

    selected = sorted(opened)
    truncated = len(selected) > MAX_FINDINGS
    references: list[dict[str, Any]] = []
    for group, source, json_path in selected[:MAX_FINDINGS]:
        callers: list[dict[str, Any]] = []
        frontier = deque([(source, 0)])
        visited = {source}
        if is_ui(source):
            callers.append({"path": source, "call_hops": 0})
        while frontier:
            current, hops = frontier.popleft()
            if hops >= 4:
                if reverse.get((group, current)):
                    truncated = True
                continue
            for caller in sorted(reverse.get((group, current), ())):
                if caller in visited:
                    continue
                if len(visited) >= 512:
                    truncated = True
                    break
                visited.add(caller)
                if is_ui(caller):
                    if len(callers) < 8:
                        callers.append({"path": caller, "call_hops": hops + 1})
                    else:
                        truncated = True
                frontier.append((caller, hops + 1))
        references.append({
            "opening_source": source, "json_path": json_path,
            "ui_callers_in_same_trace": callers,
            "json_open_observed": True, "data_read_proven": False,
            "ui_render_proven": False,
            "confidence": "OPEN_AND_CALL_PATH_CO_OBSERVED_NOT_DATA_FLOW",
        })
    return {
        "status": "REVIEW", "references": references,
        "json_opens_observed": len(selected), "truncated": truncated,
        "data_read_proven": False, "ui_render_proven": False,
        "limits": "50k events, 80 JSON open sites, 4 call hops, 512 files and 8 UI leads/site; observed opens are not reads or widget rendering.",
    }


def trace_explicit_json_bindings(
    graph: dict[str, Any], trace: dict[str, Any] | None,
) -> dict[str, Any]:
    """Cross-check opt-in JSON decoding and explicit UI binding by opaque token.

    Proof is limited to a Python decode and scenario-supplied handoff marker;
    neither a rendered Qt frame nor data use inside QWebEngine is inferred.
    """
    empty = {"status": "NOT_PROVIDED" if trace is None else "STALE_OR_INCOMPLETE",
             "bindings": [], "json_decodes": 0, "bound_to_ui": 0,
             "data_decoded_proven": False, "ui_render_proven": False,
             "truncated": False}
    if not isinstance(trace, dict):
        return empty
    sha, events = graph.get("built_at_commit"), trace.get("events")
    if (not isinstance(sha, str) or len(sha) != 40 or trace.get("candidate_sha") != sha
            or trace.get("worktree_clean") is not True or trace.get("truncated") is not False
            or not isinstance(events, list) or len(events) > 50000
            or any(not isinstance(row, dict) for row in events)):
        return {**empty, "reason": "Exact SHA, complete events and clean worktree required."}
    known = {item.get("source_file") for item in graph.get("nodes", [])
             if isinstance(item, dict) and isinstance(item.get("source_file"), str)}
    reads: dict[tuple[int, str], tuple[str, str]] = {}
    bindings: list[dict[str, Any]] = []
    total_bound = 0

    def safe(path: Any, suffix: str) -> bool:
        return (isinstance(path, str) and path.endswith(suffix)
                and not path.startswith("/") and "\\" not in path
                and all(part not in {"", ".", ".."} for part in path.split("/")))

    def view(path: str) -> bool:
        return (path.startswith(("app/pages/", "app/ui/"))
                or (path.startswith("app/modules/") and
                    ("/views/" in path or "/widgets/" in path)))

    for row in events:
        kind, token = row.get("type"), row.get("token")
        group = row.get("_trace_group", 0)
        if (not isinstance(group, int) or isinstance(group, bool) or not 0 <= group < 8
                or not isinstance(token, str)
                or not re.fullmatch(r"json-[1-9][0-9]{0,8}", token)):
            continue
        key = (group, token)
        source = row.get("source")
        if kind == "json_decoded" and row.get("confidence") == "JSON_DECODE_RETURNED":
            target = row.get("target")
            if safe(source, ".py") and source in known and safe(target, ".json"):
                reads.setdefault(key, (source, target))
        elif (kind == "json_ui_bound"
              and row.get("confidence") in {"EXPLICIT_UI_BINDING_MARKER",
                                             "EXPLICIT_QT_LABEL_SETTEXT_RETURNED"}
              and safe(source, ".py") and source in known and view(source)
              and key in reads):
            total_bound += 1
            if len(bindings) < MAX_FINDINGS:
                decoder, json_path = reads[key]
                bindings.append({"reader": decoder, "json_path": json_path,
                                 "ui_file": source,
                                 "confidence": ("QT_TEXT_BINDING_RETURNED"
                                                if row.get("confidence") == "EXPLICIT_QT_LABEL_SETTEXT_RETURNED"
                                                else "EXPLICIT_JSON_DECODE_AND_UI_BINDING"),
                                 "json_decode_observed": True,
                                 "ui_binding_marked": True, "ui_render_proven": False})
    return {
        "status": "OBSERVED_BINDING" if total_bound else "REVIEW",
        "bindings": bindings, "json_decodes": len(reads),
        "bound_to_ui": total_bound,
        "data_decoded_proven": bool(reads), "ui_render_proven": False,
        "truncated": total_bound > MAX_FINDINGS or len(reads) > MAX_FINDINGS,
        "limits": "Up to 50k exact-SHA events; 80 binding rows; no payloads; explicit Python handoff is not visual rendering.",
    }


def launcher_entrypoints(root: Path) -> dict[str, Any]:
    """Read only literal DOFUS.bat startup declarations (never execute BAT)."""
    # Windows CI may supply an 8.3 short path or a symlinked checkout root.
    # _relative() checks resolved paths, so canonicalize both sides first.
    root = root.resolve()
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
                   and isinstance(events, list) and len(events) <= 50000
                   and all(isinstance(row, dict) for row in events))
    runtime_pairs: set[tuple[str, str]] = set()
    qt_registered: set[str] = set()
    qt_invoked: set[str] = set()
    import_attempts: set[tuple[str, str]] = set()
    if valid_trace:
        for item in events:
            if not isinstance(item, dict):
                continue
            source, target = item.get("source"), item.get("target")
            if item.get("type") == "import_attempt" and isinstance(source, str) and source in files:
                module = item.get("module")
                if (isinstance(module, str) and len(module) <= 240
                        and all(part.isidentifier() for part in module.split("."))):
                    stem = module.replace(".", "/")
                    # An audit-hook import event records an ATTEMPT, not
                    # successful module initialization or use by the caller.
                    resolved = next((p for p in (stem + ".py", stem + "/__init__.py")
                                     if p in files), None)
                    if resolved and source != resolved and len(import_attempts) < 256:
                        import_attempts.add((source, resolved))
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            if source not in files or target not in files or source == target:
                continue
            if item.get("type") == "python_call_edge":
                adjacency[source].add(target)
                runtime_pairs.add((source, target))
            elif item.get("type") == "qt_signal_connect_returned":
                qt_registered.add(target)
            elif item.get("type") == "qt_callback_invoked" and item.get("confidence") == "WRAPPED_PYTHON_CALLBACK_ENTERED":
                adjacency[source].add(target)
                qt_invoked.add(target)
    known = sorted(set(entrypoints) & files)
    visited = set(known)
    frontier = deque(known)
    while frontier:
        for target in adjacency.get(frontier.popleft(), ()):
            if target not in visited:
                visited.add(target)
                frontier.append(target)
    missing = sorted(set(entrypoints) - files)
    unreachable = files - visited
    attempted_only = sorted(unreachable & {target for _, target in import_attempts})
    return {
        "status": "REVIEW" if missing or (trace is not None and not valid_trace) else "PASS",
        "entrypoints_found": known, "entrypoints_missing_from_graph": missing,
        "reachable_files": len(visited), "graph_files": len(files),
        "unreached_candidates": sorted(unreachable)[:MAX_FINDINGS],
        "unreached_total": len(unreachable),
        "unreached_with_runtime_import_attempt": attempted_only[:MAX_FINDINGS],
        "runtime_import_attempt_pairs": len(import_attempts),
        "static_or_observed_reachable_files": len(visited),
        "runtime_trace_status": ("NOT_PROVIDED" if trace is None else
                                 "MATCHED" if valid_trace else "STALE_OR_INCOMPLETE"),
        "observed_python_call_edges": len(runtime_pairs),
        "qt_registered_but_not_invoked_candidates": sorted(qt_registered - qt_invoked)[:MAX_FINDINGS],
        "observed_qt_callback_targets": sorted(qt_invoked)[:MAX_FINDINGS],
        "observed_qt_callback_target_count": len(qt_invoked),
        "proof_of_dead_code": False,
        "coverage": "Static imports, observed Python calls and explicitly wrapped Python callback entries; import attempts reported separately. No native ownership or negative reachability proof.",
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
    from .boundary_intelligence import layer_boundary_review
    layer_boundaries = layer_boundary_review(root, source.get("paths_inspected", [])[:16])
    from .resource_lifecycle import inspect_resource_lifecycle
    resource_lifecycle = inspect_resource_lifecycle(root, source.get("paths_inspected", [])[:16])
    if len(source.get("paths_inspected", [])) > 16:
        layer_boundaries["truncated"] = True
        layer_boundaries["status"] = "REVIEW"
    graph_evidence = graph_status(root)
    reach: dict[str, Any] = {"status": "UNAVAILABLE", "reason": "Current exact-SHA graph required."}
    rules: dict[str, Any] = {"status": "UNAVAILABLE"}
    lineage: dict[str, Any] = {"status": "UNAVAILABLE", "references": [], "runtime_data_flow_proven": False}
    runtime_lineage: dict[str, Any] = {"status": "NOT_PROVIDED" if trace_path is None else "UNAVAILABLE", "references": [], "data_read_proven": False, "ui_render_proven": False}
    explicit_bindings: dict[str, Any] = {"status": "NOT_PROVIDED", "bindings": [], "ui_render_proven": False}
    performance_checkpoints: dict[str, Any] = {"status": "NOT_PROVIDED", "samples": [], "peak_rss_proven": False}
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
            lineage = trace_literal_json_to_ui(graph, source.get("data_lineage_candidates", []))
            runtime_lineage = trace_observed_json_to_ui(graph, trace)
            explicit_bindings = trace_explicit_json_bindings(graph, trace)
            if (trace is not None and trace.get("candidate_sha") == graph.get("built_at_commit")
                    and trace.get("worktree_clean") is True and trace.get("truncated") is False):
                from .runtime_observation import summarize_process_checkpoints
                performance_checkpoints = summarize_process_checkpoints(trace)
            elif trace is not None:
                performance_checkpoints = {"status": "STALE_OR_INCOMPLETE", "samples": [],
                                           "peak_rss_proven": False}
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
            lineage = {"status": "UNAVAILABLE", "reason": str(exc), "references": [], "runtime_data_flow_proven": False}
            runtime_lineage = {"status": "UNAVAILABLE", "reason": str(exc), "references": [], "data_read_proven": False, "ui_render_proven": False}
            explicit_bindings = {"status": "UNAVAILABLE", "reason": str(exc), "bindings": [], "ui_render_proven": False}
    return {
        "schema_version": 1, "kind": "doctor_code_inspection",
        "status": "BLOCKED" if source["status"] == "BLOCKED" or rules["status"] == "BLOCKED"
        else "REVIEW" if source["status"] != "PASS" or graph_evidence["status"] != "PASS"
        or reach["status"] != "PASS" or rules["status"] != "PASS" else "PASS",
        "source": source, "graph_status": graph_evidence["status"],
        "reachability": reach, "architectural_rules": rules,
        "layer_boundaries": layer_boundaries,
        "resource_lifecycle": resource_lifecycle,
        "data_lineage_to_ui": lineage,
        "observed_json_to_ui": runtime_lineage,
        "explicit_json_bindings": explicit_bindings,
        "performance_checkpoints": performance_checkpoints,
        "tests_executed": False, "graph_rebuilt": False,
    }
