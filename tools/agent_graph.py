from __future__ import annotations

"""Bounded reverse impact over the canonical Doctor/Graphify cache.

Graph relationships are candidates, not evidence of runtime binding. Only
current Python imports confirm file dependencies; symbol precision stays
explicitly advisory. No graph generation or repository-wide source scan.
"""
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from tools.atlas_doctor_lib import architecture as graph_architecture

MAX_FILES = 100
RELATIONS = {"imports", "imports_from", "re_exports", "calls", "inherits", "references", "uses"}


def _source_path(root: Path, value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    try:
        resolved = (root / path).resolve()
        relative = resolved.relative_to(root).as_posix()
    except (OSError, ValueError):
        return None
    return relative if resolved.is_file() and resolved.suffix == ".py" else None


def reverse_impact(
    root: Path, paths: list[str], *,
    imports_resolver: Callable[[Path, str], list[str]],
    symbols_resolver: Callable[[Path, str], list[dict[str, Any]]],
    impact_resolver: Callable[[Path, list[str]], dict[str, Any]],
    symbol: str | None = None, depth: int = 1,
) -> dict[str, Any]:
    root = root.resolve()
    if depth not in (1, 2):
        raise ValueError("reverse impact depth must be 1 or 2")
    requested = sorted(set(paths))
    graph = graph_architecture.graph_status(root)
    payload: dict[str, Any] = {
        "schema_version": 1, "kind": "reverse_impact", "status": "REVIEW",
        "read_only": True, "paths": requested, "symbol": symbol, "depth": depth,
        "graph": graph, "direct_dependencies": {}, "reverse_dependencies": {},
        "impacted_files": [], "confirmed_relationships": [],
        "unconfirmed_relationships": [], "source_errors": [],
        "scopes": [], "recommended_tests": [],
        "source_files_parsed": 0, "truncated": False,
        "coverage": "Graph candidates confirmed against current Python imports; not a complete runtime consumer inventory.",
        "symbol_precision": "MODULE_DEPENDENCY_ONLY" if symbol else "FILE_IMPORTS",
        "next_action": "Confirm consumers, contracts and Atlas Integrity before structural edits.",
    }
    if graph["status"] != "PASS":
        payload["reason"] = graph.get("reason", "Current Graphify cache required.")
        return payload
    normalized = [_source_path(root, path) for path in requested]
    if None in normalized or len(requested) > MAX_FILES:
        payload["reason"] = "Expected at most 100 existing repository Python files."
        return payload
    requested = sorted(set(normalized))
    payload["paths"] = requested
    if symbol:
        if len(requested) != 1 or symbol not in {
            row["name"] for row in symbols_resolver(root, requested[0])
        }:
            payload["reason"] = "Symbol must identify a current top-level definition in one requested file."
            return payload
    # graph_status already validates actual nodes/links and HEAD/worktree provenance.
    content = Path(graph["graph"]).read_bytes()
    if hashlib.sha256(content).hexdigest() != graph["graph_signature"]:
        payload["reason"] = "Graph changed during impact inspection; retry with a current cache."
        return payload
    raw = json.loads(content.decode("utf-8"))
    nodes = {node["id"]: node for node in raw["nodes"]}
    candidate_edges: dict[str, list[tuple[str, dict[str, Any], dict[str, Any]]]] = {}
    source_paths: dict[str, str | None] = {}

    def node_path(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        if value not in source_paths:
            source_paths[value] = _source_path(root, value)
        return source_paths[value]
    for edge in raw["links"]:
        if edge.get("relation") not in RELATIONS:
            continue
        source, target = nodes[edge["source"]], nodes[edge["target"]]
        first = node_path(source.get("source_file"))
        second = node_path(target.get("source_file"))
        if first and second and first != second:
            candidate_edges.setdefault(second, []).append((first, edge, target))
    imports: dict[str, list[str]] = {}

    def current_imports(path: str) -> list[str]:
        if path not in imports:
            try:
                imports[path] = imports_resolver(root, path)
            except RuntimeError as exc:
                imports[path] = []
                payload["source_errors"].append({"path": path, "reason": str(exc)})
        return imports[path]

    for path in requested:
        payload["direct_dependencies"][path] = current_imports(path)
    impacted = set(requested)
    frontier = set(requested)
    examined = set(requested)
    seen_edges: set[tuple[str, str, str]] = set()
    for distance in range(1, depth + 1):
        following: set[str] = set()
        for target_file in sorted(frontier):
            for consumer, edge, target in sorted(candidate_edges.get(target_file, []), key=lambda row: row[0]):
                if symbol and distance == 1 and target.get("label", "").removesuffix("()") != symbol:
                    continue
                key = consumer, target_file, str(edge.get("relation"))
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                if consumer not in examined:
                    if len(examined) >= MAX_FILES:
                        payload["truncated"] = True
                        continue
                    examined.add(consumer)
                row = {"consumer": consumer, "dependency": target_file,
                       "relation": edge.get("relation"), "distance": distance,
                       "symbol_candidate": target.get("label"),
                       "consumer_symbol_candidate": nodes[edge["source"]].get("label"),
                       "source_location": edge.get("source_location")}
                extracted = edge.get("_origin") == "ast" and edge.get("confidence") == "EXTRACTED"
                if extracted and target_file in current_imports(consumer):
                    row["evidence"] = "CURRENT_PYTHON_IMPORT"
                    payload["confirmed_relationships"].append(row)
                    values = payload["reverse_dependencies"].setdefault(target_file, [])
                    if consumer not in values:
                        values.append(consumer)
                    if consumer not in impacted:
                        following.add(consumer)
                    impacted.add(consumer)
                else:
                    row["reason"] = "Graph binding not confirmed by a current Python import."
                    payload["unconfirmed_relationships"].append(row)
        frontier = following
    payload["impacted_files"] = sorted(impacted)
    impact = impact_resolver(root, payload["impacted_files"])
    payload["scopes"] = impact["scopes"]
    payload["recommended_tests"] = impact["recommended_tests"]
    payload["source_files_parsed"] = len(imports)
    payload["ownership_review_paths"] = sorted({
        path for path in [*impact["unowned_paths"], *impact["ambiguous_paths"]]
        if path in requested
    })
    payload["unowned_consumer_paths"] = sorted(set(impact["unowned_paths"]) - set(requested))
    payload["ambiguous_consumer_paths"] = sorted(set(impact["ambiguous_paths"]) - set(requested))
    review = bool(symbol or payload["unconfirmed_relationships"] or payload["source_errors"]
                  or payload["truncated"] or payload["ownership_review_paths"])
    payload["status"] = "REVIEW" if review else "PASS"
    payload["reason"] = "Bounded file import evidence collected; inspect limits and unconfirmed candidates."
    return payload
