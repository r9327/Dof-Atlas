from __future__ import annotations

"""Source-confirmed, bounded reverse dependency analysis for changed Python files.

This is a read-only on-demand Doctor operation. It never imports application
modules, builds Graphify, starts Qt or executes tests. Dynamic consumers are
not inferred to be absent merely because static imports have no matches.
"""
import ast
import subprocess
from collections import deque
from pathlib import Path
from typing import Any

MAX_SOURCE_FILES = 1600
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
MAX_CHANGED = 32
MAX_RESULTS = 160


def _tracked_python(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"], cwd=root,
        capture_output=True, timeout=15, check=False,
    )
    if result.returncode:
        raise RuntimeError("Could not enumerate Git-tracked Python sources")
    return sorted({row.decode("utf-8", "replace").replace("\\", "/")
                   for row in result.stdout.split(b"\0") if row})


def _safe_relative(root: Path, raw: str) -> str | None:
    if not isinstance(raw, str) or "\\" in raw or "\0" in raw:
        return None
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".py":
        return None
    selected = root / path
    if selected.is_symlink() or not selected.is_file():
        return None
    try:
        if not selected.resolve().is_relative_to(root):
            return None
    except (OSError, RuntimeError):
        return None
    return path.as_posix()


def _module_path(parts: list[str], available: set[str]) -> str | None:
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    stem = "/".join(parts)
    for path in (stem + ".py", stem + "/__init__.py"):
        if path in available:
            return path
    return None


def _imports(source: str, tree: ast.AST, available: set[str]) -> tuple[list[tuple[str, int]], int]:
    parent = source.removesuffix(".py").split("/")
    package = parent[:-1]  # Both foo/bar.py and foo/__init__.py live in foo
    found: set[tuple[str, int]] = set()
    unresolved = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _module_path(alias.name.split("."), available)
                if target and target != source:
                    found.add((target, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level > len(package):
                    unresolved += 1
                    continue
                origin = package[:len(package) - node.level + 1]
            else:
                origin = []
            if node.module:
                origin += node.module.split(".")
            matches = []
            target = _module_path(origin, available)
            if target:
                matches.append(target)
            for alias in node.names:
                if alias.name != "*":
                    submodule = _module_path(origin + alias.name.split("."), available)
                    if submodule:
                        matches.append(submodule)
            for dest in matches:
                if dest != source:
                    found.add((dest, node.lineno))
            if not matches and node.level:
                unresolved += 1
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else "")
            if name in {"import_module", "__import__", "getattr"}:
                unresolved += 1
    return sorted(found), unresolved


def source_reverse_impact(root: Path, changed_paths: list[str], *, depth: int = 2) -> dict[str, Any]:
    """Confirm static source imports by AST; return bounded reverse impact.

    No result can declare an unobserved module safe to delete. A graph from a
    previous SHA is not consulted, preventing misleading stale "PASS" results.
    """
    root = root.resolve()
    if depth not in {1, 2} or not 1 <= len(changed_paths) <= MAX_CHANGED:
        raise ValueError("Expected 1..32 paths and depth 1 or 2")
    requested = sorted(set(changed_paths))
    changed = [_safe_relative(root, raw) for raw in requested]
    invalid = [raw for raw, result in zip(requested, changed) if result is None]
    if invalid:
        return {
            "status": "BLOCKED", "reason": "Changed Python files are missing or unsafe",
            "invalid_paths": invalid[:MAX_CHANGED], "read_only": True,
            "tests_executed": False, "safe_to_delete": False,
        }
    changed = [path for path in changed if path is not None]
    tracked = _tracked_python(root)
    available = set(tracked)
    if any(path not in available for path in changed):
        return {
            "status": "REVIEW", "reason": "Untracked change paths require separate source review",
            "untracked": sorted(set(changed) - available),
            "read_only": True, "tests_executed": False, "safe_to_delete": False,
        }
    backwards: dict[str, list[tuple[str, int]]] = {}
    budget = 0
    errors: list[dict[str, str]] = []
    inspected = 0
    dynamic_sites = 0
    for path in tracked[:MAX_SOURCE_FILES]:
        selected = root / path
        try:
            if selected.is_symlink() or not selected.is_file() or not selected.resolve().is_relative_to(root):
                raise ValueError("UNSAFE_SOURCE")
            size = selected.stat().st_size
            if size > MAX_FILE_BYTES or budget + size > MAX_TOTAL_BYTES:
                raise ValueError("SOURCE_BUDGET_EXCEEDED")
            budget += size
            tree = ast.parse(selected.read_text(encoding="utf-8-sig"), filename=path)
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            errors.append({"path": path, "reason": type(exc).__name__})
            continue
        inspected += 1
        deps, unresolved = _imports(path, tree, available)
        dynamic_sites += unresolved
        for target, line in deps:
            backwards.setdefault(target, []).append((path, line))

    reached = {path: 0 for path in changed}
    chain = deque(changed)
    evidence: list[dict[str, Any]] = []
    while chain:
        imported = chain.popleft()
        level = reached[imported]
        if level >= depth:
            continue
        for importer, line in sorted(backwards.get(imported, [])):
            next_depth = level + 1
            if importer in changed:
                continue
            if importer not in reached or next_depth < reached[importer]:
                reached[importer] = next_depth
                chain.append(importer)
            if len(evidence) < MAX_RESULTS:
                evidence.append({
                    "importer": importer, "imported": imported,
                    "line": line, "depth": next_depth,
                    "confidence": "CURRENT_SOURCE_AST_STATIC_IMPORT",
                })
    consumers = sorted(({"path": path, "depth": level}
                        for path, level in reached.items() if path not in changed),
                       key=lambda item: (item["depth"], item["path"]))
    domains = sorted({"/".join(item["path"].split("/")[:3])
                      if item["path"].startswith("app/modules/")
                      else "/".join(item["path"].split("/")[:2])
                      for item in consumers})
    incomplete = (len(tracked) > MAX_SOURCE_FILES or bool(errors)
                  or len(evidence) >= MAX_RESULTS or len(consumers) > MAX_RESULTS)
    return {
        "schema_version": 1, "kind": "doctor_source_reverse_impact",
        "status": "REVIEW" if incomplete else "SOURCE_CONFIRMED",
        "changed_files": changed, "depth": depth,
        "inspected_files": inspected, "tracked_files": len(tracked),
        "direct_consumers": sum(row["depth"] == 1 for row in consumers),
        "indirect_consumers": sum(row["depth"] == 2 for row in consumers),
        "consumer_files": consumers[:MAX_RESULTS],
        "import_evidence": evidence[:MAX_RESULTS],
        "affected_domains": domains[:MAX_RESULTS],
        "potential_dynamic_import_sites": dynamic_sites,
        "source_errors": errors[:32], "truncated": incomplete,
        "read_only": True, "tests_executed": False, "graph_rebuilt": False,
        "safe_to_delete": False, "runtime_coverage_proven": False,
        "limits": "Source AST static imports only, 2 levels, bounded to 1600 tracked files/40 MiB. Dynamic imports, callbacks, Qt receivers, plugins and external consumers require separate evidence.",
    }
