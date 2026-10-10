from __future__ import annotations

"""Runtime-only, file-level Graphify focus with explicit evidence boundaries.

Graphify's AST symbol graph is kept intact. This is a *projection*, not code
deletion or a claim about runtime performance, dead code, or community validity.
Only EXTRACTED AST Python imports between app files enter the dependency graph.
"""
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

_IMPORTS = frozenset({"imports", "imports_from"})
_MAX_EXAMPLES = 8


def _app_file(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    path = value.replace("\\", "/")
    if not path.startswith("app/") or not path.endswith(".py"):
        return None
    if path.startswith("/") or ":" in path or any(
        part in {"", ".", ".."} for part in path.split("/")
    ):
        return None
    return path


def _domain(path: str) -> str:
    parts = path.split("/")
    if len(parts) >= 4 and parts[1:3] == ["modules", "encyclopedia"]:
        return "/".join(parts[:5]) if len(parts) >= 5 else "/".join(parts[:4])
    if len(parts) >= 3:
        return "/".join(parts[:2]) if len(parts) > 3 else path
    return path


def runtime_file_focus(graph: dict[str, Any]) -> dict[str, Any]:
    """Provide useful app-only coupling and isolated-file evidence in O(V+E)."""
    by_id = {row["id"]: row for row in graph["nodes"]}
    files = sorted({
        path for row in graph["nodes"]
        if (path := _app_file(row.get("source_file"))) is not None
    })
    caller_imports: dict[str, set[str]] = defaultdict(set)
    imported_by: dict[str, set[str]] = defaultdict(set)
    pairs: set[tuple[str, str]] = set()
    ignored_inferred = ignored_nonimports = 0
    for edge in graph["links"]:
        source = _app_file(by_id[edge["source"]].get("source_file"))
        target = _app_file(by_id[edge["target"]].get("source_file"))
        if not source or not target or source == target:
            continue
        if edge.get("relation") not in _IMPORTS:
            ignored_nonimports += 1
            continue
        if edge.get("confidence") != "EXTRACTED" or edge.get("_origin") != "ast":
            ignored_inferred += 1
            continue
        pairs.add((source, target))
    for source, target in pairs:
        caller_imports[source].add(target)
        imported_by[target].add(source)

    rows = []
    for path in files:
        consumers = imported_by[path]
        dependencies = caller_imports[path]
        in_count, out_count = len(consumers), len(dependencies)
        boundary = path.endswith("/__init__.py")
        if in_count == 0 and out_count == 0:
            classification = "NO_STATIC_IMPORT_EDGES_REVIEW"
            next_check = "Check launcher, dynamic imports, Qt callbacks and external entrypoints; never delete from isolation alone."
        elif boundary:
            classification = "PACKAGE_FACADE_OR_BOUNDARY"
            next_check = "Verify __init__ re-exports and lazy import contracts; preserve public import compatibility."
        elif in_count >= 12 and out_count <= 2:
            classification = "SHARED_LEAF_EXPECTED"
            next_check = "Keep stable shared APIs unless benchmark or source contracts show a regression."
        elif out_count >= 10:
            classification = "MANY_DEPENDENCIES_REVIEW"
            next_check = "Inspect responsibilities and lazy-loading constraints; profile before extracting a module."
        elif in_count >= 12 and out_count >= 3:
            classification = "MANY_CONSUMERS_REVIEW"
            next_check = "Review API ownership and downstream impact; do not split on graph degree alone."
        else:
            classification = "NORMAL_STATIC_DEPENDENCY"
            next_check = "No action from import topology alone."
        rows.append({
            "file": path, "domain": _domain(path),
            "consumer_files": in_count, "dependency_files": out_count,
            "consumer_domains": len({_domain(x) for x in consumers}),
            "dependency_domains": len({_domain(x) for x in dependencies}),
            "classification": classification, "next_check": next_check,
            "sample_consumers": sorted(consumers)[:_MAX_EXAMPLES],
            "sample_dependencies": sorted(dependencies)[:_MAX_EXAMPLES],
            "proof_of_dead_code": False, "proof_of_runtime_bottleneck": False,
        })
    ranked = sorted(
        [r for r in rows if r["classification"] in
         {"MANY_CONSUMERS_REVIEW", "MANY_DEPENDENCIES_REVIEW"}],
        key=lambda r: (-r["dependency_files"], -r["consumer_files"], r["file"]),
    )
    shared = sorted(
        [r for r in rows if r["classification"] == "SHARED_LEAF_EXPECTED"],
        key=lambda r: (-r["consumer_files"], r["file"]),
    )
    isolates = [r for r in rows if r["classification"] == "NO_STATIC_IMPORT_EDGES_REVIEW"]
    # Deterministic domain groupings make community triage stable across Leiden
    # community-ID changes. The original graph's communities remain unchanged.
    groups: dict[str, set[str]] = defaultdict(set)
    for path in files:
        groups[_domain(path)].add(path)
    bridges: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for source, target in pairs:
        sd, td = _domain(source), _domain(target)
        if sd != td:
            bridges[(sd, td)].add((source, target))
    return {
        "schema_version": 1, "status": "REVIEW" if ranked or isolates else "PASS",
        "kind": "runtime_static_import_projection",
        "source_sha": graph.get("built_at_commit"),
        "raw_graph_node_count": len(graph["nodes"]),
        "file_nodes": len(files), "confirmed_ast_import_file_pairs": len(pairs),
        "files_without_static_import_edges": len(isolates),
        "source_domains": len(groups), "cross_domain_import_pairs": sum(map(len, bridges.values())),
        "structural_hotspot_count": len(ranked),
        "ignored_nonimport_app_relations": ignored_nonimports,
        "ignored_inferred_app_import_edges": ignored_inferred,
        "hotspots": ranked[:30], "shared_leaf_apis": shared[:20],
        "isolate_candidates": isolates[:30],
        "domain_groups": [
            {"domain": key, "files": len(values)}
            for key, values in sorted(groups.items(), key=lambda row: (-len(row[1]), row[0]))
        ],
        "cross_domain_bridges": [
            {"source_domain": a, "target_domain": b, "distinct_imports": len(edges),
             "example_files": [list(e) for e in sorted(edges)[:_MAX_EXAMPLES]],
             "automatic_merge": False}
            for (a, b), edges in sorted(bridges.items(),
                key=lambda row: (-len(row[1]), row[0]))
        ][:30],
        "limits": {
            "projection_not_deletion": True, "graph_communities_unchanged": True,
            "dynamic_imports_and_reflection_not_exhaustive": True,
            "static_coupling_not_a_cpu_ram_bottleneck": True,
            "no_automatic_refactor": True,
            "truncated": len(ranked) > 30 or len(isolates) > 30 or len(bridges) > 30,
        },
    }
