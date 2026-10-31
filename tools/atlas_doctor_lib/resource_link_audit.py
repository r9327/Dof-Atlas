"""Advisory, non-destructive Doctor triage of static JSON/asset consumers.

Reuse Python AST and JSON payloads already traversed by full-scope where possible.
Do not claim runtime reachability, bundle completeness, or deletability.
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


class ResourceLinkCollector:
    """One per Doctor audit; retains only references and filenames, not payloads."""

    def __init__(self, tracked: list[str], *, offset: int = 0):
        if offset < 0:
            raise ValueError("Link candidate page offset must be >= 0")
        self.offset = offset
        self.resources = sorted(path for path in set(tracked)
                                if path.startswith(_PRODUCTION_PREFIXES)
                                and PurePosixPath(path).suffix.lower() in _RESOURCE_SUFFIXES)
        self.resource_set = set(self.resources)
        self.by_name: dict[str, list[str]] = defaultdict(list)
        for path in self.resources:
            self.by_name[PurePosixPath(path).name].append(path)
        self.definite: set[str] = set()
        self.possible: set[str] = set()
        self.unresolved: list[dict[str, Any]] = []
        self.ambiguous: list[dict[str, Any]] = []
        self.errors: list[dict[str, str]] = []
        self.counts = {
            "python_files_scanned": 0,
            "json_files_scanned": 0,
            "literals_checked": 0,
            "resolved_edges": 0,
            "possible_edges": 0,
            "unresolved_literals": 0,
            "unsafe_literals": 0,
        }

    @staticmethod
    def _example(rows: list[dict[str, Any]], entry: dict[str, Any]) -> None:
        if len(rows) < _EXAMPLE_LIMIT:
            rows.append(entry)

    def inspect_literal(self, origin: str, value: str, line: int | None = None) -> None:
        if not (0 < len(value) <= 320):
            return
        literal = value.strip().replace("\\", "/")
        if PurePosixPath(literal).suffix.lower() not in _RESOURCE_SUFFIXES:
            return
        if "\n" in literal or "\r" in literal or "://" in literal:
            return
        self.counts["literals_checked"] += 1
        parts = PurePosixPath(literal).parts
        row: dict[str, Any] = {"source": origin, "literal": value}
        if line is not None:
            row["line"] = line
        if (literal.startswith("/") or ":" in literal or
                any(part in {"..", "."} for part in parts)):
            self.counts["unsafe_literals"] += 1
            self._example(self.unresolved, {**row, "kind": "UNSAFE_RESOURCE_LITERAL_REVIEW"})
            return
        direct = literal if literal in self.resource_set else None
        relative = str(PurePosixPath(origin).parent / literal)
        target = direct or (relative if relative in self.resource_set else None)
        if target is not None:
            self.definite.add(target)
            self.counts["resolved_edges"] += 1
            return
        matches = self.by_name.get(PurePosixPath(literal).name, ())
        if matches:
            self.possible.update(matches)
            self.counts["possible_edges"] += 1
            self._example(self.ambiguous, {
                **row, "kind": "BASENAME_ONLY_REVIEW",
                "candidate_count": len(matches), "candidates": matches[:5],
            })
            return
        self.counts["unresolved_literals"] += 1
        self._example(self.unresolved, {**row, "kind": "UNRESOLVED_RESOURCE_LITERAL_REVIEW"})

    def inspect_python_node(self, name: str, node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            self.inspect_literal(name, node.value, getattr(node, "lineno", None))

    def inspect_python_tree(self, name: str, tree: ast.AST) -> None:
        self.counts["python_files_scanned"] += 1
        for node in ast.walk(tree):
            self.inspect_python_node(name, node)

    def observe_json(self, name: str, payload: Any) -> None:
        if not name.startswith(_PRODUCTION_PREFIXES):
            return
        self.counts["json_files_scanned"] += 1
        pending = [payload]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
            elif isinstance(value, str):
                self.inspect_literal(name, value)

    def inspect_json_files(self, root: Path, paths: list[str]) -> None:
        """Only when --with-json was not requested. Never import the Atlas runtime."""
        for name in paths:
            if not name.startswith(_PRODUCTION_PREFIXES):
                continue
            file = root / name
            try:
                if file.is_symlink() or not file.is_file():
                    raise OSError("Missing or symlinked JSON")
                file.resolve().relative_to(root)
                with file.open(encoding="utf-8-sig") as stream:
                    payload = json.load(stream)
                self.observe_json(name, payload)
                del payload
            except (OSError, UnicodeError, ValueError, RecursionError) as exc:
                self.errors.append({"file": name, "error": type(exc).__name__})

    def finish(self, *, include_all: bool = False) -> dict[str, Any]:
        absent = [name for name in self.resources
                  if name not in self.definite and name not in self.possible]
        next_offset = self.offset + _EXAMPLE_LIMIT
        report = {
            "status": "BLOCKED" if self.errors else "REVIEW",
            "kind": "resource_consumer_static_triage",
            "counts": {**self.counts, "production_resources": len(self.resources),
                       "static_resolved_resources": len(self.definite),
                       "basename_possible_resources": len(self.possible - self.definite),
                       "no_static_consumer_candidates": len(absent)},
            "unresolved_literal_examples": self.unresolved,
            "unresolved_literal_examples_limited":
                self.counts["unresolved_literals"] + self.counts["unsafe_literals"] > _EXAMPLE_LIMIT,
            "ambiguous_literal_examples": self.ambiguous,
            "ambiguous_literal_examples_limited": self.counts["possible_edges"] > _EXAMPLE_LIMIT,
            "no_static_consumer_examples": absent[self.offset:next_offset],
            "no_static_consumer_examples_limited": next_offset < len(absent),
            "no_static_consumer_total": len(absent),
            "no_static_consumer_offset": self.offset,
            "no_static_consumer_next_offset": next_offset if next_offset < len(absent) else None,
            "scan_errors": self.errors,
            "semantic_links_verified": False,
            "runtime_consumers_verified": False,
            "assets_contents_verified": False,
            "automatic_deletion_authorized": False,
            "note": "Only literal paths and basenames: dynamic paths, Qt resources, packagers and external consumers remain unverified.",
        }
        if include_all:
            report["no_static_consumer_all_candidates"] = absent
            report["all_candidates_exported"] = True
        return report


def inspect_resource_links(root: Path, tracked: list[str], python_files: list[str],
                           json_files: list[str], *, offset: int = 0) -> dict[str, Any]:
    """Standalone compatibility path for fixtures and callers outside full-scope."""
    root = root.resolve()
    collector = ResourceLinkCollector(tracked, offset=offset)
    for name in python_files:
        if not name.startswith("app/"):
            continue
        file = root / name
        try:
            if file.is_symlink() or not file.is_file():
                raise OSError("Missing or symlinked source")
            file.resolve().relative_to(root)
            tree = ast.parse(file.read_text(encoding="utf-8-sig"), filename=name)
            collector.inspect_python_tree(name, tree)
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            collector.errors.append({"file": name, "error": type(exc).__name__})
    collector.inspect_json_files(root, json_files)
    return collector.finish()
