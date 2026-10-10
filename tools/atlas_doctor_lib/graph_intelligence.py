from __future__ import annotations

"""Read-only graph forensics: imports, cycles, source consumers and safe plans.

A Graphify edge or missing static reference is never proof of dead code.
Only current-source import checks are labeled confirmed. Graph comparisons
preserve commit identities and compare stable file/symbol labels rather than
unstable clustering IDs.
"""
import ast
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .architecture import summarize_graph

IMPORT_KINDS = frozenset({"imports", "imports_from"})
RELEVANT_KINDS = frozenset({"imports", "imports_from", "re_exports"})
MAX_REVIEW = 30


def _path(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    value = value.replace("\\", "/")
    parts = value.split("/")
    if value.startswith("/") or ":" in value or any(part in ("", ".", "..") for part in parts):
        return None
    return value


def _production(path: str | None) -> bool:
    return bool(path and (path.startswith("app/") or path == "main.py") and path.endswith(".py"))


def _module(path: str) -> str:
    return path.removesuffix("/__init__.py").removesuffix(".py").replace("/", ".")


def _imports_from_current_source(root: Path, path: str, cache: dict[str, set[str] | None]) -> set[str] | None:
    if path in cache:
        return cache[path]
    relative = _path(path)
    if not relative or not relative.endswith(".py"):
        cache[path] = None
        return None
    try:
        original = root / relative
        if original.is_symlink() or not original.is_file():
            raise ValueError("Missing or symlinked source")
        resolved = original.resolve()
        resolved.relative_to(root.resolve())
        if original.stat().st_size > 512 * 1024:
            raise ValueError("Source size budget exceeded")
        tree = ast.parse(resolved.read_text(encoding="utf-8-sig"), filename=path)
    except (OSError, UnicodeError, SyntaxError, ValueError):
        cache[path] = None
        return None
    imports: set[str] = set()
    package = _module(path).rsplit(".", 1)[0] if not path.endswith("/__init__.py") else _module(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = node.module or ""
            if node.level:
                parts = package.split(".") if package else []
                if node.level > len(parts):
                    # Import climbs above the containing package: never
                    # reinterpret it as an absolute module dependency.
                    continue
                parts = parts[:len(parts) - node.level + 1]
                prefix = ".".join(filter(None, (".".join(parts), prefix)))
            if prefix:
                imports.add(prefix)
                imports.update(prefix + "." + name.name for name in node.names if name.name != "*")
    cache[path] = imports
    return imports


def _source_proves_import(root: Path, source: str, target: str, cache: dict[str, set[str] | None]) -> bool:
    imported = _imports_from_current_source(root, source, cache)
    if imported is None:
        return False
    module = _module(target)
    return module in imported or any(name.startswith(module + ".") for name in imported)


def _import_pairs(graph: dict[str, Any]) -> set[tuple[str, str]]:
    by_id = {node["id"]: node for node in graph["nodes"]}
    pairs: set[tuple[str, str]] = set()
    for edge in graph["links"]:
        if (
            edge.get("relation") not in IMPORT_KINDS
            or edge.get("confidence") != "EXTRACTED"
            or edge.get("_origin") != "ast"
        ):
            continue
        left = _path(by_id[edge["source"]].get("source_file"))
        right = _path(by_id[edge["target"]].get("source_file"))
        if _production(left) and _production(right) and left != right:
            pairs.add((left, right))
    return pairs


def _components(adjacency: dict[str, set[str]]) -> list[list[str]]:
    """Iterative Kosaraju: never hit Python recursion limits on large repos."""
    visited: set[str] = set()
    order: list[str] = []
    for first in sorted(adjacency):
        if first in visited:
            continue
        visited.add(first)
        stack: list[tuple[str, Any]] = [(first, iter(sorted(adjacency[first])))]
        while stack:
            node, iterator = stack[-1]
            following = next(iterator, None)
            if following is None:
                order.append(node)
                stack.pop()
            elif following not in visited:
                visited.add(following)
                stack.append((following, iter(sorted(adjacency.get(following, ())))))
    reverse: dict[str, set[str]] = defaultdict(set)
    for source, targets in adjacency.items():
        reverse.setdefault(source, set())
        for target in targets:
            reverse[target].add(source)
    found: set[str] = set()
    result: list[list[str]] = []
    for first in reversed(order):
        if first in found:
            continue
        found.add(first)
        stack = [first]
        group = []
        while stack:
            node = stack.pop()
            group.append(node)
            for other in reverse.get(node, ()):
                if other not in found:
                    found.add(other)
                    stack.append(other)
        if len(group) > 1:
            result.append(sorted(group))
    return sorted(result, key=lambda group: (-len(group), group))


def inspect_import_cycles(graph: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    """Potential cycles from directed extracted file imports, source checked."""
    summarize_graph(graph)
    pairs = _import_pairs(graph)
    adjacency: dict[str, set[str]] = defaultdict(set)
    for source, target in pairs:
        adjacency[source].add(target)
        adjacency.setdefault(target, set())
    components = _components(adjacency)
    cache: dict[str, set[str] | None] = {}
    source_confirmed_pairs: set[tuple[str, str]] = set()
    cycles = []
    for members in components:
        group = set(members)
        edges = sorted((source, target) for source, target in pairs if source in group and target in group)
        checked = []
        for source, target in edges:
            proof = root is not None and _source_proves_import(root, source, target, cache)
            checked.append({"source": source, "target": target, "source_confirmed": proof})
            if proof:
                source_confirmed_pairs.add((source, target))
        cycles.append({
            "files": members, "import_file_edges": len(edges),
            "source_confirmed_edges": sum(x["source_confirmed"] for x in checked),
            "confidence": "GRAPH_CYCLE_NEEDS_SOURCE_REVIEW",
            "blocking": False, "review_required": True,
            "reason": "A cycle in import dependencies does not prove a runtime error or a new regression.",
            "sample_edges": checked[:10],
        })
    # A source-confirmed cycle can survive even when *other* edges in the
    # same Graphify SCC are stale. Compute SCCs again using only proven edges.
    confirmed_adjacency: dict[str, set[str]] = defaultdict(set)
    for source, target in source_confirmed_pairs:
        confirmed_adjacency[source].add(target)
        confirmed_adjacency.setdefault(target, set())
    confirmed_components = _components(confirmed_adjacency)
    for candidate in cycles:
        members = set(candidate["files"])
        confirmed_inside = [c for c in confirmed_components if set(c) <= members]
        if confirmed_inside:
            candidate["confidence"] = "CURRENT_SOURCE_IMPORT_CYCLE"
        candidate["source_confirmed_subcycles"] = len(confirmed_inside)
        candidate["confirmed_cycle_samples"] = confirmed_inside[:3]
    return {
        "status": "REVIEW" if cycles else "PASS",
        "directed_extracted_import_pairs": len(pairs),
        "suspected_cycles": len(cycles),
        "source_confirmed_cycles": len(confirmed_components),
        "cycles": cycles[:MAX_REVIEW],
        "truncated": len(cycles) > MAX_REVIEW,
        "scope": "Extracted directed runtime Python file imports only; dynamic imports can be missed.",
    }


def _stable_nodes(graph: dict[str, Any]) -> dict[tuple[str, str, str], int]:
    values: dict[tuple[str, str, str], int] = {}
    adjacency: Counter[Any] = Counter()
    for edge in graph["links"]:
        adjacency[edge["source"]] += 1
        adjacency[edge["target"]] += 1
    for node in graph["nodes"]:
        path = _path(node.get("source_file"))
        if not _production(path) or node.get("file_type") != "code":
            continue
        label = str(node.get("label") or "")
        if not label or label.endswith(".py"):
            continue
        key = (path, label, str(node.get("_origin") or ""))
        values[key] = min(values.get(key, 2**31), adjacency[node["id"]])
    return values


def compare_graphs(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare structural signals by stable file/label, never Leiden community IDs."""
    old = summarize_graph(before)
    now = summarize_graph(after)
    ids = [graph.get("built_at_commit") for graph in (before, after)]
    if not all(isinstance(sha, str) and re.fullmatch(r"[0-9a-fA-F]{40}", sha) for sha in ids):
        raise ValueError("Exact 40-digit source commit identity required for both graphs.")
    if ids[0] == ids[1]:
        raise ValueError("Baseline and candidate must identify different commits.")
    old_nodes, new_nodes = _stable_nodes(before), _stable_nodes(after)
    old_links, new_links = _import_pairs(before), _import_pairs(after)
    new_orphans = sorted(k for k, value in new_nodes.items() if value == 0 and old_nodes.get(k, -1) > 0)
    new_weak = sorted(k for k, value in new_nodes.items() if value == 1 and old_nodes.get(k, -1) > 1)
    removed_imports = sorted(old_links - new_links)
    added_imports = sorted(new_links - old_links)
    # Compare *all* cycles. The display report caps at MAX_REVIEW entries,
    # which must never hide regression number 31 and later.
    def complete_cycles(graph: dict[str, Any]) -> set[tuple[str, ...]]:
        adjacency: dict[str, set[str]] = defaultdict(set)
        for source, target in _import_pairs(graph):
            adjacency[source].add(target)
            adjacency.setdefault(target, set())
        return {tuple(group) for group in _components(adjacency)}
    old_cycles = complete_cycles(before)
    new_cycles = complete_cycles(after)
    return {
        "schema_version": 1, "kind": "graph_architecture_comparison",
        "status": "REVIEW" if new_orphans or new_weak or new_cycles - old_cycles or added_imports else "PASS",
        "baseline_sha": ids[0], "candidate_sha": ids[1],
        "node_delta": now["node_count"] - old["node_count"],
        "relationship_delta": now["link_count"] - old["link_count"],
        "new_orphan_symbols": [{"path": p, "symbol": s, "origin": o} for p, s, o in new_orphans[:MAX_REVIEW]],
        "new_weak_symbols": [{"path": p, "symbol": s, "origin": o} for p, s, o in new_weak[:MAX_REVIEW]],
        "new_import_file_pairs": [list(item) for item in added_imports[:MAX_REVIEW]],
        "removed_import_file_pairs": [list(item) for item in removed_imports[:MAX_REVIEW]],
        "new_candidate_import_cycles": [list(c) for c in sorted(new_cycles - old_cycles)[:MAX_REVIEW]],
        "limits": {
            "stable_symbol_key": "file+label+origin",
            "community_ids_not_comparable": True,
            "differences_are_not_proof_of_regressions": True,
            "candidate_limits": MAX_REVIEW,
            "truncated": any(len(x) > MAX_REVIEW for x in (new_orphans, new_weak, added_imports, removed_imports, new_cycles - old_cycles)),
        },
    }


def _candidate_symbol(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    # Graphify emits Python method labels as ".publish_status()" rather than
    # identifiers. Use only names for searching; a name match is not binding proof.
    token = value.strip().removeprefix(".").removesuffix("()")
    generic = {"init", "__init__", "run", "start", "end", "wait", "ok", "open", "close", "get", "set"}
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{3,}", token) or token in generic:
        return None
    return token



def _local_symbol_references(root: Path, path: str, symbol: str) -> list[dict[str, Any]]:
    """Recognize local AST *uses*, not just external text matches.

    A callback passed as self.method or a ctypes type referenced within its
    defining file must not become an 'unused' removal lead. Local AST names
    alone still do not prove that any execution path was reached.
    """
    safe = _path(path)
    if not safe or not safe.endswith(".py"):
        return []
    try:
        candidate = root / safe
        if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size > 512 * 1024:
            return []
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
        tree = ast.parse(candidate.read_text(encoding="utf-8-sig"), filename=safe)
    except (OSError, ValueError, UnicodeError, SyntaxError):
        return []
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == symbol:
            lines.add(node.lineno)
        elif isinstance(node, ast.Name) and node.id == symbol and isinstance(node.ctx, ast.Load):
            lines.add(node.lineno)
    return [
        {"file": safe, "line": line, "kind": "LOCAL_AST_REFERENCE_UNVERIFIED_BINDING"}
        for line in sorted(lines)[:8]
    ]


def inspect_consumers(root: Path, candidates: list[dict[str, Any]], *, limit: int = 20) -> dict[str, Any]:
    """Bounded full tracked-source name sweep; no negative proof of dead code."""
    subset = [
        (row, _candidate_symbol(row.get("symbol"))) for row in candidates
        if _production(_path(row.get("file"))) and _candidate_symbol(row.get("symbol"))
    ][:limit]
    if not subset:
        return {"status": "PASS", "reviewed": [], "files_checked": 0, "scan_complete": True}
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.py", "*.ps1", "*.bat"],
            cwd=root, capture_output=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "BLOCKED", "reason": str(exc), "reviewed": [], "scan_complete": False}
    if completed.returncode != 0:
        return {"status": "BLOCKED", "reason": completed.stderr.decode(errors="replace")[-500:], "reviewed": [], "scan_complete": False}
    tracked = sorted(p.decode("utf-8", errors="replace") for p in completed.stdout.split(b"\0") if p)
    names = sorted({name for _, name in subset}, key=len, reverse=True)
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(name) for name in names) + r")\b")
    findings: dict[str, list[dict[str, Any]]] = {name: [] for name in names}
    errors = []
    count = 0
    for path in tracked:
        safe = _path(path)
        if not safe or Path(safe).suffix not in {".py", ".ps1", ".bat"}:
            continue
        target = (root / safe).resolve()
        try:
            target.relative_to(root.resolve())
            if target.stat().st_size > 2_000_000:
                errors.append({"path": safe, "reason": "file exceeds 2MB scan cap"})
                continue
            source = target.read_text(encoding="utf-8-sig", errors="replace")
        except (OSError, ValueError):
            errors.append({"path": safe, "reason": "file unreadable"})
            continue
        count += 1
        if not pattern.search(source):
            continue
        found = set(pattern.findall(source))
        for name in found:
            if len(findings[name]) >= 8:
                continue
            rows = [
                index for index, line in enumerate(source.splitlines(), 1)
                if re.search(r"\b" + re.escape(name) + r"\b", line)
            ]
            for line in rows[:max(0, 8 - len(findings[name]))]:
                findings[name].append({
                    "file": safe, "line": line,
                    "kind": "SOURCE_TEXT_MATCH_UNVERIFIED_BINDING",
                })
    reviewed = []
    for row, name in subset:
        references = [item for item in findings[name] if item["file"] != row["file"]]
        local_references = _local_symbol_references(root, row["file"], name)
        classification = ("POSSIBLE_EXTERNAL_CONSUMER" if references
                          else "LOCAL_SOURCE_REFERENCE_REVIEW" if local_references
                          else "NO_EXTERNAL_TEXT_MATCH_UNPROVEN")
        reviewed.append({
            "file": row["file"], "symbol": row["symbol"], "normalized_symbol": name,
            "classification": classification,
            "references": references[:8], "local_references": local_references,
            "confirmed_dead_code": False,
            "next_action": (
                "Keep as source-used pending binding/runtime verification; do not propose removal."
                if local_references else
                "Verify dynamic Qt callbacks, entry points, native code and external consumers before removal."
            ),
        })
    return {
        "status": "REVIEW" if reviewed else "PASS",
        "reviewed": reviewed, "files_checked": count,
        "candidate_limit": limit, "eligible_candidates": len(subset),
        "scan_complete": not errors,
        "unreadable_or_skipped": errors[:10],
        "scope": "Tracked Python, PowerShell and batch source text. Text matches do not prove symbol binding; absence never proves dead code.",
    }


def analyze_community_boundaries(graph: dict[str, Any]) -> dict[str, Any]:
    """Advisory cohesion signals only; never force merges based on IDs."""
    summarize_graph(graph)
    nodes = {n["id"]: n for n in graph["nodes"]}
    internal: Counter[Any] = Counter()
    external: Counter[Any] = Counter()
    files: dict[Any, set[str]] = defaultdict(set)
    for node in nodes.values():
        path = _path(node.get("source_file"))
        if _production(path) and node.get("file_type") == "code" and node.get("community") is not None:
            files[node["community"]].add(path)
    for edge in graph["links"]:
        if edge.get("confidence") != "EXTRACTED" or edge.get("relation") not in RELEVANT_KINDS:
            continue
        left, right = nodes[edge["source"]], nodes[edge["target"]]
        lc, rc = left.get("community"), right.get("community")
        if lc not in files or rc not in files:
            continue
        if lc == rc:
            internal[lc] += 1
        else:
            external[lc] += 1
            external[rc] += 1
    rows = []
    for group, sources in files.items():
        if len(sources) < 2 or external[group] < 5:
            continue
        if external[group] <= 2 * max(1, internal[group]):
            continue
        rows.append({
            "community": group, "production_files": len(sources),
            "internal_extracted_edges": internal[group],
            "external_extracted_edges": external[group],
            "sample_files": sorted(sources)[:8],
            "classification": "LOW_INTERNAL_HIGH_EXTERNAL_GRAPH_COHESION_REVIEW",
            "automatic_merge": False,
        })
    rows.sort(key=lambda x: (-x["external_extracted_edges"], x["production_files"], str(x["community"])))
    return {"status": "REVIEW" if rows else "PASS", "candidate_count": len(rows),
            "candidates": rows[:MAX_REVIEW], "truncated": len(rows) > MAX_REVIEW,
            "limitation": "Leiden partitions are heuristics; domain ownership and runtime tests prevail."}


def remediation_plan(
    triage: dict[str, Any], cycles: dict[str, Any], cohesion: dict[str, Any],
    *, source_review: dict[str, Any] | None = None, performance: dict[str, Any] | None = None
) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for row in triage.get("blocking_findings", [])[:MAX_REVIEW]:
        tasks.append({
            "priority": "P0", "kind": "PROVEN_IMPORT_INVERSION",
            "paths": [row["source"], row["target"]],
            "evidence": "Current Python source import", "action": "Move shared pure code to app/core or correct import owner.",
            "require_tests": ["targeted functional contracts", "Graphify exact SHA", "Doctor FAST"],
            "automatic_edit": False,
        })
    for cycle in cycles.get("cycles", [])[:MAX_REVIEW]:
        tasks.append({
            "priority": "P1" if cycle["confidence"] == "CURRENT_SOURCE_IMPORT_CYCLE" else "P2", "kind": "IMPORT_CYCLE",
            "paths": cycle["files"], "evidence": cycle["confidence"],
            "action": "Review dependency direction and relocate shared interfaces only if source and tests confirm.",
            "require_tests": ["affected unit tests", "Graphify exact SHA", "Doctor FAST"],
            "automatic_edit": False,
        })
    for row in (source_review or {}).get("reviewed", [])[:10]:
        if row["classification"] != "NO_EXTERNAL_TEXT_MATCH_UNPROVEN":
            continue
        tasks.append({
            "priority": "P3", "kind": "UNPROVEN_UNUSED_SYMBOL",
            "paths": [row["file"]], "symbol": row["symbol"],
            "evidence": "No external text match in scanned tracked source; not proof of dead code",
            "action": "Verify dynamic Qt signals/callbacks, native imports and external entry points; only then decide keep/remove.",
            "require_tests": ["current owner tests", "Graphify exact SHA"],
            "automatic_edit": False,
        })
    for row in cohesion.get("candidates", [])[:8]:
        tasks.append({
            "priority": "P3", "kind": "FRAGMENTED_COMMUNITY_REVIEW",
            "paths": row["sample_files"], "community": row["community"],
            "evidence": f"{row['external_extracted_edges']} external, {row['internal_extracted_edges']} internal extracted graph edges",
            "action": "Inspect responsibilities and real runtime consumers; do not merge by community count.",
            "require_tests": ["affected unit tests", "Graphify exact SHA"],
            "automatic_edit": False,
        })
    for row in triage.get("high_fanout_files", [])[:5]:
        tasks.append({
            "priority": "P3", "kind": "HIGH_FANOUT_REVIEW",
            "paths": [row["file"]], "evidence": f"{row.get('runtime_neighbor_files', 0)} neighboring runtime files",
            "action": "Review responsibilities; keep intentional core utilities and public APIs.",
            "require_tests": ["affected unit tests", "Graphify exact SHA"],
            "automatic_edit": False,
        })
    for task in tasks:
        if any(path.startswith("app/") or path == "main.py" for path in task["paths"]):
            task["require_tests"].extend(["Phase 8 RAM benchmark", "Phase 8 comparable preload"])
            task["memory_risk"] = "UNMEASURED_REQUIRES_BENCHMARK"
        else:
            task["memory_risk"] = "NO_DIRECT_RUNTIME_SCOPE_IDENTIFIED"
    # Explicitly separate an actionable, proven contract violation from a
    # graph lead. Source-confirmed import cycles are still not proven runtime
    # failures, and weak communities are never automatic refactor commands.
    next_proofs = {
        "PROVEN_IMPORT_INVERSION": "Confirm imports in current source and run affected contracts.",
        "IMPORT_CYCLE": "Identify eager runtime imports versus TYPE_CHECKING/lazy imports, then exercise both import orders.",
        "UNPROVEN_UNUSED_SYMBOL": "Check callbacks, ctypes/FFI, same-file references and entrypoints before any deletion.",
        "FRAGMENTED_COMMUNITY_REVIEW": "Inspect domain ownership and runtime consumers; merge only for a proven duplication.",
        "HIGH_FANOUT_REVIEW": "Profile import and runtime cost before splitting a heavily used API.",
    }
    for task in tasks:
        task["decision"] = ("FIX_CONFIRMED_CONTRACT_VIOLATION"
                            if task["kind"] == "PROVEN_IMPORT_INVERSION"
                            else "INVESTIGATE_NO_CODE_CHANGE_YET")
        task["next_proof"] = next_proofs[task["kind"]]
        task["code_change_authorized"] = False
    priority = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    tasks.sort(key=lambda task: (priority[task["priority"]], task["kind"], str(task["paths"])))
    return {
        "schema_version": 1, "status": "REVIEW" if tasks else "PASS",
        "tasks": tasks[:MAX_REVIEW], "task_count": len(tasks),
        "truncated": len(tasks) > MAX_REVIEW,
        "actionability": {
            "confirmed_fix_candidates": sum(t["decision"] == "FIX_CONFIRMED_CONTRACT_VIOLATION" for t in tasks),
            "investigation_candidates": sum(t["decision"] == "INVESTIGATE_NO_CODE_CHANGE_YET" for t in tasks),
            "local_source_used_symbols": [
                {"file": row["file"], "symbol": row["symbol"],
                 "references": row.get("local_references", [])[:8]}
                for row in (source_review or {}).get("reviewed", [])
                if row.get("classification") == "LOCAL_SOURCE_REFERENCE_REVIEW"
            ],
            "unproven_is_not_safe_to_delete": True,
            "next_action": "Investigate individual source/runtime leads; no automatic app refactor on graph counts alone.",
        },
        "performance_evidence": performance or {
            "status": "UNAVAILABLE", "reason": "No exact-SHA runtime benchmark joined."
        },
        "policy": {
            "no_automatic_deletion": True, "no_automatic_merge": True,
            "single_domain_bounded_lots": True, "source_confirmation_required": True,
            "benchmark_before_claiming_RAM_improvement": True,
        },
    }


def correlate_performance(root: Path, candidate_sha: str) -> dict[str, Any]:
    """Never attach stale benchmark measurements to a current candidate."""
    from .core import load_json
    perf = load_json(root, "latest_perf")
    if not isinstance(perf, dict) or (perf.get("git") or {}).get("head") != candidate_sha:
        return {
            "status": "UNAVAILABLE",
            "reason": "Doctor latest_perf missing or does not match exact graph SHA.",
            "candidate_sha": candidate_sha,
        }
    runtime = perf.get("runtime") or {}
    measured = (runtime.get("benchmark") or {}).get("after") or {}
    if not isinstance(measured, dict):
        return {"status": "UNAVAILABLE", "reason": "Runtime benchmark lacks after measurements."}
    return {
        "status": "MEASURED" if measured else "UNAVAILABLE",
        "candidate_sha": candidate_sha, "runtime_status": runtime.get("status"),
        "measurements": measured if measured else {},
        "limitation": "Whole-application benchmarks do not attribute memory to individual graph nodes.",
    }
