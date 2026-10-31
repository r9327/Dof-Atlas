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
        self.unresolved_all: list[dict[str, Any]] = []
        self.ambiguous_all: list[dict[str, Any]] = []
        self.errors: list[dict[str, str]] = []
        self.counts = {
            "python_files_scanned": 0,
            "json_files_scanned": 0,
            "literals_checked": 0,
            "resolved_edges": 0,
            "possible_edges": 0,
            "unresolved_literals": 0,
            "unsafe_literals": 0,
            "skipped_overlength_literals": 0,
            "skipped_uri_literals": 0,
            "skipped_multiline_literals": 0,
        }

    @staticmethod
    def _example(rows: list[dict[str, Any]], entry: dict[str, Any]) -> None:
        if len(rows) < _EXAMPLE_LIMIT:
            rows.append(entry)

    @staticmethod
    def _pointer_part(value: object) -> str:
        return str(value).replace("~", "~0").replace("/", "~1")

    def inspect_literal(self, origin: str, value: str, line: int | None = None,
                        *, json_pointer: str | None = None,
                        json_role: str | None = None) -> None:
        if not value:
            return
        if len(value) > 320:
            self.counts["skipped_overlength_literals"] += 1
            return
        literal = value.strip().replace("\\", "/")
        if "\n" in literal or "\r" in literal:
            self.counts["skipped_multiline_literals"] += 1
            return
        if "://" in literal:
            self.counts["skipped_uri_literals"] += 1
            return
        if PurePosixPath(literal).suffix.lower() not in _RESOURCE_SUFFIXES:
            return
        self.counts["literals_checked"] += 1
        parts = PurePosixPath(literal).parts
        row: dict[str, Any] = {"source": origin, "literal": value}
        if line is not None:
            row["line"] = line
        if json_pointer is not None:
            row["json_pointer"] = json_pointer
            row["json_role"] = json_role or "value"
        if (literal.startswith("/") or ":" in literal or
                any(part in {"..", "."} for part in parts)):
            self.counts["unsafe_literals"] += 1
            entry = {**row, "kind": "UNSAFE_RESOURCE_LITERAL_REVIEW"}
            self.unresolved_all.append(entry)
            self._example(self.unresolved, entry)
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
            entry = {**row, "kind": "BASENAME_ONLY_REVIEW",
                     "candidate_count": len(matches), "candidates": list(matches)}
            self.ambiguous_all.append(entry)
            self._example(self.ambiguous, {**entry, "candidates": list(matches[:5])})
            return
        self.counts["unresolved_literals"] += 1
        entry = {**row, "kind": "UNRESOLVED_RESOURCE_LITERAL_REVIEW"}
        self.unresolved_all.append(entry)
        self._example(self.unresolved, entry)

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
        # Iterator frames keep the traversal bounded by JSON nesting depth,
        # rather than storing pointers for every large Quest JSON sibling.
        stack: list[tuple[Any, str]] = [(iter([(None, payload)]), "")]
        while stack:
            iterator, parent = stack[-1]
            try:
                segment, value = next(iterator)
            except StopIteration:
                stack.pop()
                continue
            pointer = parent if segment is None else parent + "/" + self._pointer_part(segment)
            if isinstance(value, dict):
                for key in value:
                    self.inspect_literal(name, key, json_pointer=pointer + "/" + self._pointer_part(key),
                                         json_role="key")
                stack.append((iter(value.items()), pointer))
            elif isinstance(value, list):
                stack.append((enumerate(value), pointer))
            elif isinstance(value, str):
                self.inspect_literal(name, value, json_pointer=pointer, json_role="value")

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
            report["unresolved_literal_all_candidates"] = self.unresolved_all
            report["ambiguous_literal_all_candidates"] = self.ambiguous_all
            report["all_candidates_exported"] = True
            report["all_link_candidates_exported"] = (
                len(self.unresolved_all) == self.counts["unresolved_literals"] + self.counts["unsafe_literals"]
                and len(self.ambiguous_all) == self.counts["possible_edges"]
                and all(len(item["candidates"]) == item["candidate_count"] for item in self.ambiguous_all)
            )
        return report


def inspect_resource_links(root: Path, tracked: list[str], python_files: list[str],
                           json_files: list[str], *, offset: int = 0) -> dict[str, Any]:
    """Standalone compatibility path for fixtures and callers outside full-scope."""
    root = root.resolve()
    collector = ResourceLinkCollector(tracked, offset=offset)
    for name in python_files:
        if not name.startswith(("app/", "scripts/windows/", "tools/")):
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
