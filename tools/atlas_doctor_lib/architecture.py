from __future__ import annotations

"""Doctor orchestration and a compact view of the actual Graphify 0.9.72 format."""
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tools import graphify
from .core import cache_matches_git, git_state, load_json, run_git, utc_now, write_json


def summarize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("links"), list):
        raise ValueError("Expected Graphify nodes and links arrays.")
    nodes, links = graph["nodes"], graph["links"]
    if not nodes:
        raise ValueError("Graphify graph is empty.")
    by_id = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), (str, int)):
            raise ValueError("Invalid Graphify node id.")
        if node["id"] in by_id:
            raise ValueError("Duplicate Graphify node id.")
        by_id[node["id"]] = node
    adjacency = {key: set() for key in by_id}
    neighbors = defaultdict(set)
    relations = Counter()
    confidence = Counter()
    for link in links:
        if not isinstance(link, dict):
            raise ValueError("Invalid Graphify relationship.")
        source, target = link.get("source"), link.get("target")
        if not isinstance(source, (str, int)) or not isinstance(target, (str, int)) or source not in by_id or target not in by_id:
            raise ValueError("Graphify relationship references an absent node.")
        adjacency[source].add(target)
        adjacency[target].add(source)
        relation = link.get("relation")
        if isinstance(relation, str):
            relations[relation] += 1
        if isinstance(link.get("confidence"), str):
            confidence[link["confidence"]] += 1
        first, second = by_id[source].get("source_file"), by_id[target].get("source_file")
        if isinstance(first, str) and isinstance(second, str) and first and second and first != second:
            neighbors[first].add(second)
            neighbors[second].add(first)
    remaining = set(by_id)
    components = 0
    while remaining:
        components += 1
        stack = [remaining.pop()]
        while stack:
            for neighbor in adjacency[stack.pop()]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
    return {
        "node_count": len(nodes), "link_count": len(links),
        "community_count": len({node["community"] for node in nodes if isinstance(node.get("community"), (str, int))}),
        "relation_counts": dict(sorted(relations.items())),
        "confidence_counts": dict(sorted(confidence.items())),
        "isolated_node_count": sum(not values for values in adjacency.values()),
        "connected_component_count": components,
        "most_connected_files": [
            {"path": path, "neighbor_file_count": len(values)}
            for path, values in sorted(neighbors.items(), key=lambda item: (-len(item[1]), item[0]))[:15]
        ],
        "cycle_analysis": {"status": "NOT_COMPUTED", "reason": "The exported graph is undirected; consult Graphify GRAPH_REPORT.md for import cycles."},
        "interpretation": "Connections are diagnostic evidence, not proof that dependencies or files are obsolete.",
    }


def _signature(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def graph_status(root: Path, *, state: dict[str, Any] | None = None) -> dict[str, Any]:
    root = root.resolve()
    current = state or git_state(root)
    payload: dict[str, Any] = {
        "schema_version": 1, "kind": "architecture", "git": current,
        "tool": graphify.detect(root), "status": "MISSING",
        "graph": str(root / graphify.OUTPUT / "graph.json"),
        "html": str(root / graphify.OUTPUT / "graph.html"),
        "report": str(root / graphify.OUTPUT / "GRAPH_REPORT.md"),
        "rebuild_command": "py -3.13 -m tools.atlas_doctor graph --rebuild",
    }
    graph_path = Path(payload["graph"])
    if not graph_path.is_file():
        payload["reason"] = "Graph absent. Reconstruction explicite requise."
        return payload
    try:
        raw = json.loads(graph_path.read_text(encoding="utf-8"))
        summary = summarize_graph(raw)
        for path in (Path(payload["html"]), Path(payload["report"])):
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(f"Missing or empty Graphify output: {path}")
        if "<html" not in Path(payload["html"]).read_text(encoding="utf-8").lower():
            raise ValueError("Graphify HTML visualization is invalid.")
        signature = _signature(graph_path)
    except (OSError, UnicodeError, ValueError) as exc:
        payload.update(status="INVALID", reason=str(exc))
        return payload
    payload["summary"] = summary
    payload["graph_signature"] = signature
    cached = load_json(root, "latest_graph")
    if not isinstance(cached, dict):
        cached = None
    matches = (
        cache_matches_git(cached, current)
        and cached.get("graph_signature") == signature
        and cached.get("version") == graphify.PINNED_VERSION
    )
    graph_head = raw.get("built_at_commit")
    if graph_head:
        resolved = run_git(root, "rev-parse", "--verify", graph_head + "^{commit}", check=False) if isinstance(graph_head, str) and re.fullmatch(r"[0-9a-fA-F]{7,40}", graph_head) else ""
        if resolved != current["head"]:
            matches = False
    payload["status"] = "PASS" if matches else "STALE"
    payload["reason"] = "Graph current for HEAD/worktree." if matches else "Graph perime ou sans provenance Doctor HEAD/worktree. Utiliser --rebuild."
    return payload


def architecture(root: Path, *, rebuild: bool = False) -> dict[str, Any]:
    root = root.resolve()
    before = git_state(root)
    if not rebuild:
        return graph_status(root, state=before)
    previous = load_json(root, "latest_graph")
    result = graphify.build_graph(root)
    if result["status"] != "PASS":
        return {"schema_version": 1, "kind": "architecture", "status": result["status"],
                "git": before, "generation": result, "reason": result.get("reason")}
    after = git_state(root)
    if not cache_matches_git({"git": before}, after):
        return {"schema_version": 1, "kind": "architecture", "status": "STALE",
                "git": after, "reason": "Worktree changed during Graphify generation; rebuild required."}
    status = graph_status(root, state=after)
    if status["status"] == "INVALID":
        return status
    if "summary" not in status:
        return status
    snapshot = {
        "schema_version": 1, "git": after, "generated_at": utc_now(),
        "version": graphify.PINNED_VERSION,
        "graph_signature": _signature(Path(status["graph"])), "summary": status["summary"],
    }
    write_json(root, "latest_graph", snapshot, rotate=True)
    status = graph_status(root, state=after)
    if isinstance(previous, dict) and previous.get("version") == graphify.PINNED_VERSION:
        old = previous.get("summary") or {}
        status["count_delta"] = {key: snapshot["summary"][key] - old[key]
                                 for key in ("node_count", "link_count")
                                 if isinstance(old.get(key), int)}
    status["generation"] = result
    return status
