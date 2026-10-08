from __future__ import annotations

"""Evidence-aware, read-only Doctor triage of a current Graphify AST graph.

Graph nodes and Leiden communities are candidates, not proof of dead code.
Only a verified present-day Python import can become a blocking finding.
No implicit graph rebuild, imports of application modules, or source mutation.
"""
import ast
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .architecture import graph_status, summarize_graph

IMPORT_RELATIONS = {"imports", "imports_from"}
GRAPH_RELATIONS = {"imports", "imports_from", "calls", "inherits", "references", "uses", "re_exports"}
MAX_CANDIDATES = 30


def _path(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or ":" in normalized or ".." in Path(normalized).parts:
        return None
    return normalized


def _domain(path: str) -> str:
    parts = path.split("/")
    if parts[0] == "app" and len(parts) > 4 and parts[1] == "modules":
        return "/".join(parts[:4])
    return "/".join(parts[:2]) if len(parts) > 1 else parts[0]


def _confirm_import(root: Path, source: str, target: str) -> bool:
    """Prove a tools.* import using current code, never graph inference alone."""
    file = root / source
    if not source.startswith("app/") or not target.startswith("tools/"):
        return False
    if not file.is_file() or file.suffix != ".py":
        return False
    module = target.removesuffix(".py").removesuffix("/__init__").replace("/", ".")
    try:
        code = ast.parse(file.read_text(encoding="utf-8-sig"), filename=source)
    except (OSError, UnicodeError, SyntaxError):
        return False
    for node in ast.walk(code):
        if isinstance(node, ast.Import):
            if any(alias.name == module or alias.name.startswith(module + ".") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported = node.module or ""
            if imported == module or imported.startswith(module + "."):
                return True
            if target.endswith("/__init__.py") and imported.startswith(module + "."):
                return True
    return False


def inspect_graph(graph: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    """Bounded O(nodes + links) architectural diagnosis with explicit evidence."""
    basic = summarize_graph(graph)  # strict missing/duplicate nodes and dangling links
    nodes = {node["id"]: node for node in graph["nodes"]}
    degree: Counter[Any] = Counter()
    incoming: Counter[Any] = Counter()
    neighbors: dict[str, set[str]] = defaultdict(set)
    communities: Counter[Any] = Counter()
    cross_communities: Counter[tuple[Any, Any]] = Counter()
    community_file_pairs: dict[tuple[Any, Any], set[tuple[str, str]]] = defaultdict(set)
    community_neighbors: dict[Any, set[Any]] = defaultdict(set)
    community_files: dict[Any, set[str]] = defaultdict(set)
    edge_examples: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    inversions: dict[tuple[str, str], dict[str, Any]] = {}
    inferred: Counter[str] = Counter()
    for node in nodes.values():
        community = node.get("community")
        if isinstance(community, (int, str)) and not isinstance(community, bool):
            communities[community] += 1
            source_file = _path(node.get("source_file"))
            if source_file:
                community_files[community].add(source_file)

    for edge in graph["links"]:
        source = nodes[edge["source"]]
        target = nodes[edge["target"]]
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
        incoming[edge["target"]] += 1
        if len(edge_examples[edge["source"]]) < 2:
            edge_examples[edge["source"]].append({
                "direction": "outgoing", "relation": edge.get("relation"),
                "confidence": edge.get("confidence"), "neighbor": str(target.get("label") or ""),
                "neighbor_file": _path(target.get("source_file")),
            })
        if edge["source"] != edge["target"] and len(edge_examples[edge["target"]]) < 2:
            edge_examples[edge["target"]].append({
                "direction": "incoming", "relation": edge.get("relation"),
                "confidence": edge.get("confidence"), "neighbor": str(source.get("label") or ""),
                "neighbor_file": _path(source.get("source_file")),
            })
        sf, tf = _path(source.get("source_file")), _path(target.get("source_file"))
        relation = edge.get("relation")
        if edge.get("confidence") == "INFERRED":
            inferred[str(relation)] += 1
        if sf and tf and sf != tf:
            neighbors[sf].add(tf)
            neighbors[tf].add(sf)
            sc, tc = source.get("community"), target.get("community")
            if sc in communities and tc in communities and sc != tc:
                pair = tuple(sorted((sc, tc), key=lambda x: (type(x).__name__, str(x))))
                cross_communities[pair] += 1
                community_neighbors[sc].add(tc)
                community_neighbors[tc].add(sc)
                if edge.get("confidence") == "EXTRACTED" and relation in IMPORT_RELATIONS:
                    community_file_pairs[pair].add((sf, tf))
            if (sf.startswith("app/") and tf.startswith("tools/")
                    and relation in IMPORT_RELATIONS and edge.get("confidence") == "EXTRACTED"
                    and edge.get("_origin") == "ast"):
                key = sf, tf
                if key not in inversions:
                    inversions[key] = {
                        "rule": "RUNTIME_TO_TOOL_IMPORT", "source": sf, "target": tf,
                        "relation": relation, "graph_source_location": edge.get("source_location"),
                        "confidence": "GRAPH_EXTRACTED_UNCONFIRMED", "blocking": False,
                    }

    confirmed: list[dict[str, Any]] = []
    unconfirmed: list[dict[str, Any]] = []
    for (source, target), item in sorted(inversions.items()):
        if root is not None and _confirm_import(root, source, target):
            item = {**item, "confidence": "CURRENT_SOURCE_IMPORT", "blocking": True}
            confirmed.append(item)
        else:
            unconfirmed.append(item)

    orphan: list[dict[str, Any]] = []
    weak: list[dict[str, Any]] = []
    noncode_weak = 0
    for node_id, node in nodes.items():
        source = _path(node.get("source_file"))
        if not source or node.get("file_type") == "external":
            continue
        value = {
            "id": str(node_id), "symbol": str(node.get("label") or ""),
            "file": source, "location": node.get("source_location"),
            "community": node.get("community"), "degree": degree[node_id],
            "incoming_edges": incoming[node_id],
        }
        if degree[node_id] == 0:
            boundary = (
                source.endswith("/__init__.py") or source.endswith(".ps1")
                or source.startswith("tests/") or source.endswith(".bat")
            )
            orphan.append({**value, "classification": (
                "BOUNDARY_OR_EXTERNAL_ENTRY_CANDIDATE" if boundary
                else "UNPROVEN_ISOLATION_REVIEW"
            ), "proof_of_dead_code": False})
        elif degree[node_id] == 1 and source.startswith("app/") and source.endswith(".py"):
            # Graphify also emits docstring/rationale nodes. Those are NOT
            # runnable symbols and must never dominate dead-code candidates.
            if node.get("file_type") != "code":
                noncode_weak += 1
                continue
            priority = 2 if incoming[node_id] == 0 else 1
            weak.append({
                **value, "classification": "LOW_GRAPH_DEGREE_REVIEW",
                "review_priority": priority, "edge_evidence": edge_examples[node_id],
                "proof_of_dead_code": False,
            })

    orphan.sort(key=lambda x: (x["file"], x["symbol"]))
    weak.sort(key=lambda x: (-x["review_priority"], x["file"], x["symbol"]))
    hubs = []
    for file, others in neighbors.items():
        if not file.startswith("app/") or len(others) < 20:
            continue
        runtime = sorted(other for other in others if other.startswith("app/") or other == "main.py")
        test_neighbors = sorted(other for other in others if other.startswith("tests/"))
        domains = sorted({_domain(other) for other in runtime})
        hubs.append({
            "file": file, "neighbor_files": len(others),
            "runtime_neighbor_files": len(runtime), "test_neighbor_files": len(test_neighbors),
            "runtime_domains": domains[:10], "total_runtime_domains": len(domains),
            "sample_runtime_neighbors": runtime[:8], "sample_test_neighbors": test_neighbors[:3],
            "classification": "COUPLING_REVIEW_NOT_DEFECT",
        })
    hubs.sort(key=lambda x: (-x["runtime_neighbor_files"], -x["neighbor_files"], x["file"]))
    bridges = [
        {"communities": list(key), "graph_links": count,
         "distinct_extracted_import_file_pairs": len(community_file_pairs[key]),
         "sample_extracted_import_file_pairs": [list(value) for value in sorted(community_file_pairs[key])[:8]],
         "classification": "CROSS_COMMUNITY_COUPLING_REVIEW_NOT_MERGE_PROOF"}
        for key, count in cross_communities.items()
        if len(community_file_pairs[key]) >= 3
    ]
    bridges.sort(key=lambda x: (-x["distinct_extracted_import_file_pairs"], -x["graph_links"], str(x["communities"])))
    standalone = []
    for key, size in communities.items():
        if community_neighbors[key]:
            continue
        files = sorted(community_files[key])
        production = [
            path for path in files if path.startswith("app/")
            and path.endswith(".py") and not path.endswith("/__init__.py")
        ]
        standalone.append({
            "community": key, "raw_nodes": size,
            "production_source_files": len(production),
            "sample_source_files": files[:8],
            "classification": (
                "PRODUCTION_GRAPH_ISLAND_REVIEW" if production
                else "NON_RUNTIME_OR_PACKAGE_BOUNDARY_CANDIDATE"
            ),
        })
    standalone.sort(key=lambda x: (-int(x["production_source_files"] > 0), -x["raw_nodes"], str(x["community"])))
    return {
        "schema_version": 1, "kind": "graph_architecture_audit",
        "status": "FAIL" if confirmed else "REVIEW" if orphan or weak or hubs or bridges or unconfirmed else "PASS",
        "blocking_findings": confirmed, "unconfirmed_import_candidates": unconfirmed,
        "metrics": {
            "node_count": basic["node_count"], "link_count": basic["link_count"],
            "raw_community_count": len(communities),
            "raw_communities_lt3_nodes": sum(count < 3 for count in communities.values()),
            "isolated_communities": len(standalone),
            "isolated_communities_with_production_files": sum(x["production_source_files"] > 0 for x in standalone),
            "isolated_nodes": len(orphan), "weak_production_nodes_degree1": len(weak),
            "excluded_noncode_weak_nodes": noncode_weak,
            "inferred_edges": sum(inferred.values()), "inferred_relation_counts": dict(sorted(inferred.items())),
            "cross_community_pairs": len(cross_communities), "high_fanout_app_files": len(hubs),
            "confirmed_runtime_to_tools_imports": len(confirmed),
        },
        "orphan_nodes": orphan[:MAX_CANDIDATES], "isolated_communities": standalone[:MAX_CANDIDATES],
        "weak_production_candidates": weak[:MAX_CANDIDATES],
        "high_fanout_files": hubs[:MAX_CANDIDATES], "cross_community_bridges": bridges[:MAX_CANDIDATES],
        "limits": {
            "max_candidates_per_section": MAX_CANDIDATES,
            "unreported_weak_nodes": max(0, len(weak) - MAX_CANDIDATES),
            "no_automatic_deletion_or_merge": True,
            "undirected_graph_cycles": "NOT_COMPUTED",
            "community_report_omissions_are_not_raw_small_communities": True,
            "graph_absence_does_not_prove_no_consumers": True,
        },
    }


def audit_current_graph(
    root: Path, *, graph_evidence: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Refuse stale graphs; reuse a validated status to avoid repeat Git work."""
    root = root.resolve()
    status = graph_evidence if graph_evidence is not None else graph_status(root)
    if status["status"] != "PASS":
        return {"schema_version": 1, "kind": "graph_architecture_audit",
                "status": "BLOCKED", "graph_status": status["status"],
                "reason": status.get("reason", "A current Graphify graph is required."),
                "rebuild_command": "python -m tools.atlas_doctor graph --rebuild"}
    try:
        content = Path(status["graph"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != status["graph_signature"]:
            raise ValueError("Graph changed during audit; rebuild/retry required.")
        result = inspect_graph(json.loads(content), root=root)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return {"schema_version": 1, "kind": "graph_architecture_audit",
                "status": "BLOCKED", "reason": str(exc)}
    result["candidate_sha"] = status["git"]["head"]
    result["graph_signature"] = status["graph_signature"]
    result["graph_version"] = (status.get("tool") or {}).get("version")
    return result
