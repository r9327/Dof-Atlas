"""Exact-Git-inventory JSON syntax and ID-collision triage for Atlas Doctor.

Read-only and opt-in: payloads are discarded file by file. This is not a
runtime-consumer, schema, image-reference, or native Windows verification.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _duplicate_ids(rows: list[Any]) -> list[str]:
    """Report same-list ID collisions as REVIEW leads, never delete data."""
    seen: set[tuple[type, str]] = set()
    duplicates: set[str] = set()
    for value in rows:
        if not isinstance(value, dict):
            continue
        raw = value.get("id")
        if isinstance(raw, bool) or not isinstance(raw, (str, int)):
            continue
        key = (type(raw), str(raw))
        if key in seen:
            duplicates.add(str(raw))
        else:
            seen.add(key)
    return sorted(duplicates)



def _children(path: str, node: Any):
    """Yield child containers lazily so large JSON arrays do not create a second heap."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                yield (escaped if path == "$root" else f"{path}/{escaped}"), value
    elif isinstance(node, list):
        for index, value in enumerate(node):
            if isinstance(value, (dict, list)):
                yield f"{path}/{index}", value


def _nested_duplicate_ids(payload: Any) -> tuple[list[dict[str, Any]], int]:
    """Find review-only ID collisions in every nested list without recursive calls."""
    candidates: list[dict[str, Any]] = []
    lists_scanned = 0
    frames = [iter([("$root", payload)])]
    while frames:
        try:
            path, node = next(frames[-1])
        except StopIteration:
            frames.pop()
            continue
        if isinstance(node, list):
            lists_scanned += 1
            ids = _duplicate_ids(node)
            if ids:
                candidates.append({
                    "collection": path, "ids": ids, "kind": "DUPLICATE_ID_REVIEW",
                })
        if isinstance(node, (dict, list)):
            frames.append(_children(path, node))
    return sorted(candidates, key=lambda item: item["collection"]), lists_scanned


def _reject_non_finite(value: str) -> None:
    raise ValueError("Non-standard JSON number: " + value)


def inspect_tracked_json(root: Path, paths: list[str], *, sha: str, clean: bool) -> dict[str, Any]:
    """Inspect every tracked JSON; a skipped/broken file blocks completeness."""
    files: list[dict[str, Any]] = []
    counts = {
        "tracked": len(paths), "valid_syntax": 0, "invalid_syntax": 0,
        "unavailable": 0, "duplicate_id_review_files": 0,
        "duplicate_member_review_files": 0, "nested_lists_scanned": 0,
        "bytes_parsed": 0,
    }
    for relative in paths:
        file = root / relative
        entry: dict[str, Any] = {"file": relative}
        try:
            if file.is_symlink() or not file.is_file():
                raise OSError("Missing or symlinked tracked JSON")
            file.resolve().relative_to(root)
            entry["bytes"] = file.stat().st_size
            # Loading one file at a time avoids accidentally retaining the
            # 70 MiB Quest index alongside the 28 MiB image manifest.
            duplicate_members: set[str] = set()

            def observe_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                result: dict[str, Any] = {}
                for key, value in pairs:
                    if key in result:
                        duplicate_members.add(key)
                    result[key] = value
                return result

            with file.open("r", encoding="utf-8-sig") as stream:
                prefix = stream.read(80)
                if prefix.startswith("version https://git-lfs.github.com/spec/v1"):
                    raise OSError("Tracked JSON is a Git LFS pointer, not materialized data")
                stream.seek(0)
                payload = json.load(stream, parse_constant=_reject_non_finite,
                                    object_pairs_hook=observe_object)
            entry["top_level_type"] = type(payload).__name__
            collisions, lists_scanned = _nested_duplicate_ids(payload)
            entry["duplicate_id_candidates"] = collisions
            # json.load accepts repeated object member keys by default: do not
            # silently treat a value overwritten by the decoder as sound data.
            entry["duplicate_member_candidates"] = sorted(duplicate_members)
            entry["status"] = (
                "VALID_SYNTAX_REVIEW" if collisions or duplicate_members else "VALID_SYNTAX"
            )
            counts["valid_syntax"] += 1
            counts["bytes_parsed"] += entry["bytes"]
            counts["nested_lists_scanned"] += lists_scanned
            if collisions:
                counts["duplicate_id_review_files"] += 1
            if duplicate_members:
                counts["duplicate_member_review_files"] += 1
            del payload
        except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
            entry["status"] = "INVALID"
            entry["error"] = type(exc).__name__
            counts["invalid_syntax"] += 1
        except OSError as exc:
            entry["status"] = "NOT_AVAILABLE"
            entry["error"] = type(exc).__name__
            counts["unavailable"] += 1
        files.append(entry)

    complete = (
        clean and counts["tracked"] > 0 and len(files) == counts["tracked"]
        and counts["valid_syntax"] == counts["tracked"]
        and not counts["invalid_syntax"] and not counts["unavailable"]
    )
    return {
        "candidate_sha": sha,
        "status": "REVIEW" if complete else "BLOCKED",
        "syntax_coverage": "PASS" if complete else "BLOCKED",
        "semantic_links_verified": False,
        "consumers_verified": False,
        "assets_verified": False,
        "worktree_clean": clean,
        "counts": counts,
        "files": files,
        "truncated": False,
        "automatic_deletion_authorized": False,
        "limits": [
            "Syntax PASS does not prove domain ID references, schema, active packaging or assets",
            "Nested ID and repeated object-key candidates require source semantics before cleanup",
            "Repeated object-key names are counted per file; exact object paths are not recovered",
            "Git-tracked inventory excludes generated and user-local files",
        ],
    }
