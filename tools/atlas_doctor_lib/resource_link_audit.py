"""Non-destructive static resource-consumer triage for Doctor full-scope.

A literal edge is evidence of a *possible* consumer, not runtime reachability.
Absence of an edge never authorizes cleanup (Qt, bundles and generated paths).
"""
from __future__ import annotations

import ast
from collections import defaultdict
import json
from pathlib import Path, PurePosixPath
from typing import Any

_RESOURCE_SUFFIXES = {".json", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".ttf", ".otf", ".qss"}
_PRODUCTION_PREFIXES = ("app/", "data/", "assets/", "resources/")
_EXAMPLE_LIMIT = 40


def inspect_resource_links(root: Path, tracked: list[str], python_files: list[str],
                           json_files: list[str]) -> dict[str, Any]:
    """Inventory all production resources and identify *static* candidate edges.

    Parse tracked app Python and production JSON, including dynamic-path caveats.
    This scan does not execute Python, open assets, or prove consumer absence.
    """
    root = root.resolve()
    tracked_set = set(tracked)
    resources = sorted(path for path in tracked_set
                       if path.startswith(_PRODUCTION_PREFIXES)
                       and PurePosixPath(path).suffix.lower() in _RESOURCE_SUFFIXES)
    resource_set = set(resources)
    by_name: dict[str, list[str]] = defaultdict(list)
    for path in resources:
        by_name[PurePosixPath(path).name].append(path)
    definite: set[str] = set()
    possible: set[str] = set()
    broken: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    counts = {"python_files_scanned": 0, "json_files_scanned": 0,
              "literals_checked": 0, "resolved_edges": 0,
              "possible_edges": 0, "unresolved_literals": 0,
              "unsafe_literals": 0}
    errors: list[dict[str, str]] = []

    def sample(destination: list[dict[str, Any]], row: dict[str, Any]) -> None:
        if len(destination) < _EXAMPLE_LIMIT:
            destination.append(row)

    def examine(origin: str, value: str, line: int | None = None) -> None:
        if not (0 < len(value) <= 320):
            return
        literal = value.strip().replace("\\", "/")
        if PurePosixPath(literal).suffix.lower() not in _RESOURCE_SUFFIXES:
            return
        if "\n" in literal or "\r" in literal or "://" in literal:
            return
        counts["literals_checked"] += 1
        parts = PurePosixPath(literal).parts
        row: dict[str, Any] = {"source": origin, "literal": value}
        if line is not None:
            row["line"] = line
        if (literal.startswith("/") or ":" in literal or
                any(part in {"..", "."} for part in parts)):
            counts["unsafe_literals"] += 1
            sample(broken, {**row, "kind": "UNSAFE_RESOURCE_LITERAL_REVIEW"})
            return
        direct = literal if literal in resource_set else None
        relative = str(PurePosixPath(origin).parent / literal)
        target = direct or (relative if relative in resource_set else None)
        if target is not None:
            definite.add(target)
            counts["resolved_edges"] += 1
            return
        matches = by_name.get(PurePosixPath(literal).name, ())
        if matches:
            possible.update(matches)
            counts["possible_edges"] += 1
            sample(ambiguous, {**row, "kind": "BASENAME_ONLY_REVIEW",
                               "candidate_count": len(matches),
                               "candidates": matches[:5]})
            return
        counts["unresolved_literals"] += 1
        sample(broken, {**row, "kind": "UNRESOLVED_RESOURCE_LITERAL_REVIEW"})

    for name in python_files:
        if not name.startswith("app/"):
            continue
        file = root / name
        try:
            if file.is_symlink() or not file.is_file():
                raise OSError("Missing or symlinked source")
            file.resolve().relative_to(root)
            tree = ast.parse(file.read_text(encoding="utf-8-sig"), filename=name)
            counts["python_files_scanned"] += 1
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    examine(name, node.value, node.lineno)
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            errors.append({"file": name, "error": type(exc).__name__})

    for name in json_files:
        if not name.startswith(_PRODUCTION_PREFIXES):
            continue
        file = root / name
        try:
            if file.is_symlink() or not file.is_file():
                raise OSError("Missing or symlinked JSON")
            file.resolve().relative_to(root)
            with file.open(encoding="utf-8-sig") as stream:
                data = json.load(stream)
            counts["json_files_scanned"] += 1
            pending = [data]
            while pending:
                value = pending.pop()
                if isinstance(value, dict):
                    pending.extend(value.values())
                elif isinstance(value, list):
                    pending.extend(value)
                elif isinstance(value, str):
                    examine(name, value)
            del data
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            errors.append({"file": name, "error": type(exc).__name__})

    absent = [name for name in resources if name not in definite and name not in possible]
    return {
        "status": "BLOCKED" if errors else "REVIEW",
        "kind": "resource_consumer_static_triage",
        "counts": {**counts, "production_resources": len(resources),
                   "static_resolved_resources": len(definite),
                   "basename_possible_resources": len(possible - definite),
                   "no_static_consumer_candidates": len(absent)},
        "unresolved_literal_examples": broken,
        "unresolved_literal_examples_limited": counts["unresolved_literals"] + counts["unsafe_literals"] > _EXAMPLE_LIMIT,
        "ambiguous_literal_examples": ambiguous,
        "ambiguous_literal_examples_limited": counts["possible_edges"] > _EXAMPLE_LIMIT,
        "no_static_consumer_examples": absent[:_EXAMPLE_LIMIT],
        "no_static_consumer_examples_limited": len(absent) > _EXAMPLE_LIMIT,
        "scan_errors": errors,
        "semantic_links_verified": False,
        "runtime_consumers_verified": False,
        "assets_contents_verified": False,
        "automatic_deletion_authorized": False,
        "note": "Static literal triage only; dynamically built paths, Qt resources, packagers and external consumers are not proven.",
    }
