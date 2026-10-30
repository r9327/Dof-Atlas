"""Exact-Git-inventory JSON syntax and ID-collision triage for Atlas Doctor.

Read-only and opt-in: payloads are discarded file by file. This is not a
runtime-consumer, schema, image-reference, or native Windows verification.
"""
from __future__ import annotations

import json
import math
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


def _id_collision_candidates(payload: Any) -> tuple[list[dict[str, Any]], int]:
    """Inspect ID collisions in every nested JSON list, not just root children.

    Use a depth-first iterator stack instead of materializing a second copy of
    large nested quest/guide catalogues. Locations are JSON-pointer-like paths;
    they identify candidate containers, not evidence that IDs must be unique
    across different lists or entity types.
    """
    def children(path: str, value: list[Any] | dict[str, Any]):
        # Own function frame pins path/value for each active iterator; an
        # inline generator would capture the outer loop's changing locals.
        if isinstance(value, list):
            for index, child in enumerate(value):
                if isinstance(child, (dict, list)):
                    yield f"{path}/{index}", child
        else:
            for key, child in value.items():
                if isinstance(child, (dict, list)):
                    escaped = str(key).replace("~", "~0").replace("/", "~1")
                    yield f"{path}/{escaped}", child

    collisions: list[dict[str, Any]] = []
    lists_inspected = 0
    stack = [iter([("$root", payload)])]
    while stack:
        try:
            path, value = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if isinstance(value, list):
            lists_inspected += 1
            ids = _duplicate_ids(value)
            if ids:
                collisions.append({
                    "collection": path, "ids": ids, "kind": "DUPLICATE_ID_REVIEW",
                })
            stack.append(children(path, value))
        elif isinstance(value, dict):
            stack.append(children(path, value))
    return collisions, lists_inspected



_GUIDE_DIR = "data/encyclopedia/guides/"
_GUIDE_CATALOG = _GUIDE_DIR + "catalog.json"


def _verify_guide_catalog(catalog: Any, guide_headers: dict[str, dict[str, Any]],
                          tracked_paths: list[str]) -> dict[str, Any]:
    """Verify only manifest->Guide static links, never Quest, UI or runtime links."""
    if catalog is None:
        present = _GUIDE_CATALOG in tracked_paths
        return {
            "status": "REVIEW" if present else "NOT_RUN",
            "reason": "Canonical Guide catalog has no parsed object" if present
                      else "Canonical Guide catalog not tracked",
            "checked": 0, "issues": [],
        }
    issues: list[dict[str, Any]] = []
    if (not isinstance(catalog, dict)
            or not isinstance(catalog.get("categories"), list)
            or not isinstance(catalog.get("guides"), list)):
        return {"status": "REVIEW", "checked": 0,
                "issues": [{"kind": "INVALID_CATALOG_SHAPE"}]}
    categories: set[str] = set()
    for index, row in enumerate(catalog["categories"]):
        value = row.get("id") if isinstance(row, dict) else None
        if not isinstance(value, str) or not value or value in categories:
            issues.append({"kind": "INVALID_OR_DUPLICATE_CATEGORY", "index": index})
        else:
            categories.add(value)
    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    tracked = set(tracked_paths)
    for index, row in enumerate(catalog["guides"]):
        if not isinstance(row, dict):
            issues.append({"kind": "INVALID_GUIDE_ENTRY", "index": index})
            continue
        gid, filename, category = row.get("id"), row.get("file"), row.get("category")
        if not isinstance(gid, str) or not gid or gid in seen_ids:
            issues.append({"kind": "INVALID_OR_DUPLICATE_GUIDE_ID", "index": index})
        else:
            seen_ids.add(gid)
        if not isinstance(category, str) or category not in categories:
            issues.append({"kind": "UNKNOWN_GUIDE_CATEGORY", "index": index, "id": gid})
        # Do not resolve paths, follow symlinks, or accept untrusted subpaths.
        if (not isinstance(filename, str) or not filename.endswith(".json")
                or "/" in filename or "\\" in filename or ":" in filename
                or filename.startswith(".") or filename == ".json"):
            issues.append({"kind": "UNSAFE_GUIDE_FILENAME", "index": index, "id": gid})
            continue
        target = _GUIDE_DIR + filename
        if target in seen_files:
            issues.append({"kind": "DUPLICATE_GUIDE_FILE", "index": index, "file": target})
        seen_files.add(target)
        if target not in tracked:
            issues.append({"kind": "MISSING_TRACKED_GUIDE", "index": index, "file": target})
        elif target not in guide_headers:
            issues.append({"kind": "UNREADABLE_GUIDE_HEADER", "index": index, "file": target})
        else:
            header = guide_headers[target]
            if header["id"] != gid:
                issues.append({"kind": "GUIDE_ID_MISMATCH", "index": index, "file": target})
            if header["category"] != category:
                issues.append({"kind": "GUIDE_CATEGORY_MISMATCH", "index": index, "file": target})
    return {
        "status": "STATIC_PASS" if not issues and catalog["guides"] and categories else "REVIEW",
        "checked": len(catalog["guides"]), "category_count": len(categories),
        "issues": issues, "runtime_routes_verified": False,
    }


_MANUAL_MANIFEST = "data/routes/guide_ultime_manual/manifest_v1.json"
_MANUAL_DIR = "data/routes/guide_ultime_manual/"


def _manual_manifest_chapter_refs(
    payload: Any, tracked_json: set[str],
) -> tuple[list[dict[str, Any]], int, int]:
    """Triage tracked canonical Guide Ultime chapter, branch and registry references.

    Chapter imports, option branches and resolved stage totals are deliberately
    outside this static check. A tracked file is not proof of runtime validity.
    """
    candidates: list[dict[str, Any]] = []
    canonical = payload.get("canonical") if isinstance(payload, dict) else None
    chapters = canonical.get("chapters") if isinstance(canonical, dict) else None
    if not isinstance(chapters, list) or not chapters:
        return ([{"kind": "CANONICAL_CHAPTERS_MISSING_REVIEW"}], 0, 0)
    inspected = 0
    references_inspected = 0
    for index, row in enumerate(chapters):
        inspected += 1
        references_inspected += 1
        filename = row.get("file") if isinstance(row, dict) else None
        if not isinstance(filename, str) or not filename:
            candidates.append({
                "kind": "MANIFEST_CHAPTER_FILE_MISSING_REVIEW", "chapter_index": index,
            })
            continue
        # The actual runtime joins filenames with MANUAL_DIR. Do not follow
        # absolute/parent-relative paths even in read-only audit logic.
        if (
            "/" in filename or "\\" in filename or ":" in filename
            or filename in {".", ".."} or not filename.lower().endswith(".json")
        ):
            candidates.append({
                "kind": "MANIFEST_CHAPTER_PATH_UNSAFE_REVIEW",
                "chapter_index": index, "file": filename,
            })
        elif _MANUAL_DIR + filename not in tracked_json:
            candidates.append({
                "kind": "MANIFEST_CHAPTER_NOT_TRACKED_REVIEW",
                "chapter_index": index, "file": filename,
            })
    # The runtime also uses named registries and conditionally resolved routes
    # from the same canonical manifest. They are distinct from chapter cards;
    # missing references must still be visible in the Git-wide audit.
    for family in ("conditional_routes", "transversal_routes"):
        rows = canonical.get(family) if isinstance(canonical, dict) else None
        if rows is None:
            continue
        if not isinstance(rows, list):
            candidates.append({
                "kind": "MANIFEST_COLLECTION_INVALID_REVIEW", "collection": family,
            })
            continue
        for index, row in enumerate(rows):
            references_inspected += 1
            filename = row.get("file") if isinstance(row, dict) else None
            if not isinstance(filename, str) or not filename:
                candidates.append({
                    "kind": "MANIFEST_REFERENCE_MISSING_REVIEW",
                    "collection": family, "index": index,
                })
                continue
            if (
                "/" in filename or "\\" in filename or ":" in filename
                or filename in {".", ".."} or not filename.lower().endswith(".json")
            ):
                candidates.append({
                    "kind": "MANIFEST_REFERENCE_UNSAFE_REVIEW",
                    "collection": family, "index": index, "file": filename,
                })
            elif _MANUAL_DIR + filename not in tracked_json:
                candidates.append({
                    "kind": "MANIFEST_REFERENCE_NOT_TRACKED_REVIEW",
                    "collection": family, "index": index, "file": filename,
                })
    for key in (
        "temporal_registry", "ocre_capture_registry", "ocre_final_route",
        "success_contracts",
    ):
        if not isinstance(canonical, dict) or key not in canonical:
            # Do not invent a requirement for optional historical manifests.
            continue
        references_inspected += 1
        filename = canonical[key]
        if not isinstance(filename, str) or not filename:
            candidates.append({
                "kind": "MANIFEST_REFERENCE_MISSING_REVIEW", "collection": key,
            })
        elif (
            "/" in filename or "\\" in filename or ":" in filename
            or filename in {".", ".."} or not filename.lower().endswith(".json")
        ):
            candidates.append({
                "kind": "MANIFEST_REFERENCE_UNSAFE_REVIEW",
                "collection": key, "file": filename,
            })
        elif _MANUAL_DIR + filename not in tracked_json:
            candidates.append({
                "kind": "MANIFEST_REFERENCE_NOT_TRACKED_REVIEW",
                "collection": key, "file": filename,
            })
    return candidates, inspected, references_inspected


def _reject_non_finite(value: str) -> None:
    raise ValueError("Non-standard JSON number: " + value)


def _parse_finite_float(value: str) -> float:
    # A valid JSON exponent such as 1e10000 overflows float() to infinity.
    # parse_constant alone only rejects explicit NaN/Infinity literals.
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number: " + value)
    return number


def inspect_tracked_json(root: Path, paths: list[str], *, sha: str, clean: bool) -> dict[str, Any]:
    """Inspect every tracked JSON; a skipped/broken file blocks completeness."""
    files: list[dict[str, Any]] = []
    guide_catalog: Any = None
    guide_headers: dict[str, dict[str, Any]] = {}
    counts = {
        "tracked": len(paths), "valid_syntax": 0, "invalid_syntax": 0,
        "unavailable": 0, "duplicate_id_review_files": 0,
        "duplicate_key_review_files": 0, "id_lists_inspected": 0,
        # Compatible aliases retained from the five current-PR commits.
        "duplicate_member_review_files": 0, "nested_lists_scanned": 0,
        "manifest_chapter_refs_inspected": 0,
        "manifest_refs_inspected": 0,
        "manifest_reference_review_files": 0, "manual_base_refs_inspected": 0,
        "manual_base_reference_review_files": 0, "bytes_parsed": 0,
    }
    tracked_json = set(paths)
    manual_base_edges: dict[str, str] = {}
    for relative in paths:
        file = root / relative
        entry: dict[str, Any] = {"file": relative}
        duplicate_keys: dict[str, int] = {}

        def record_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            # json.load normally silently keeps the last value for repeated
            # object keys. Retain the same decoded object for further triage,
            # but report every collision (including nested JSON objects).
            result = dict(pairs)
            if len(result) != len(pairs):
                seen: set[str] = set()
                for key, _ in pairs:
                    if key in seen:
                        duplicate_keys[key] = duplicate_keys.get(key, 0) + 1
                    else:
                        seen.add(key)
            return result

        try:
            if file.is_symlink() or not file.is_file():
                raise OSError("Missing or symlinked tracked JSON")
            file.resolve().relative_to(root)
            entry["bytes"] = file.stat().st_size
            # Loading one file at a time avoids accidentally retaining the
            # 70 MiB Quest index alongside the 28 MiB image manifest.
            with file.open("r", encoding="utf-8-sig") as stream:
                prefix = stream.read(80)
                if prefix.startswith("version https://git-lfs.github.com/spec/v1"):
                    raise OSError("Tracked JSON is a Git LFS pointer, not materialized data")
                stream.seek(0)
                payload = json.load(
                    stream, parse_constant=_reject_non_finite,
                    parse_float=_parse_finite_float,
                    object_pairs_hook=record_object_keys,
                )
            entry["top_level_type"] = type(payload).__name__
            if relative == _GUIDE_CATALOG:
                guide_catalog = payload
            elif relative.startswith(_GUIDE_DIR) and isinstance(payload, dict):
                guide_headers[relative] = {
                    "id": payload.get("id"), "category": payload.get("category"),
                }
            collisions, lists_inspected = _id_collision_candidates(payload)
            counts["id_lists_inspected"] += lists_inspected
            counts["nested_lists_scanned"] += lists_inspected
            entry["id_lists_inspected"] = lists_inspected
            entry["duplicate_id_candidates"] = collisions
            if relative == _MANUAL_MANIFEST:
                manifest_findings, chapter_refs, total_refs = _manual_manifest_chapter_refs(
                    payload, tracked_json,
                )
                entry["manual_manifest_reference_candidates"] = manifest_findings
                entry["manifest_chapter_refs_inspected"] = chapter_refs
                entry["manifest_refs_inspected"] = total_refs
                counts["manifest_chapter_refs_inspected"] += chapter_refs
                counts["manifest_refs_inspected"] += total_refs
                if manifest_findings:
                    counts["manifest_reference_review_files"] += 1
            else:
                manifest_findings = []
            # Canonical chapter layers are frequently patch-only JSON. The
            # manifest can point at a valid v2 file whose base_file v1 is
            # missing, so validate each declared predecessor separately.
            # This is reference triage, not stage-merging or route validation.
            base_findings: list[dict[str, str]] = []
            if relative.startswith(_MANUAL_DIR) and isinstance(payload, dict) and "base_file" in payload:
                counts["manual_base_refs_inspected"] += 1
                filename = payload["base_file"]
                if not isinstance(filename, str) or not filename:
                    base_findings.append({"kind": "MANUAL_BASE_MISSING_REVIEW"})
                elif (
                    "/" in filename or "\\" in filename or ":" in filename
                    or filename in {".", ".."} or not filename.lower().endswith(".json")
                ):
                    base_findings.append({
                        "kind": "MANUAL_BASE_UNSAFE_REVIEW", "file": filename,
                    })
                elif _MANUAL_DIR + filename == relative:
                    base_findings.append({
                        "kind": "MANUAL_BASE_SELF_REFERENCE_REVIEW", "file": filename,
                    })
                elif _MANUAL_DIR + filename not in tracked_json:
                    base_findings.append({
                        "kind": "MANUAL_BASE_NOT_TRACKED_REVIEW", "file": filename,
                    })
                else:
                    manual_base_edges[relative] = _MANUAL_DIR + filename
                entry["manual_base_reference_candidates"] = base_findings
                if base_findings:
                    counts["manual_base_reference_review_files"] += 1
            # A duplicate member name can silently change the interpreted
            # source even if JSON syntax and list-level IDs are otherwise OK.
            # The decoder hook has no parent path: never invent one.
            entry["duplicate_key_candidates"] = [
                {"key": key, "occurrences": number, "kind": "DUPLICATE_KEY_REVIEW",
                 "json_path": None}
                for key, number in sorted(duplicate_keys.items())
            ]
            entry["duplicate_member_candidates"] = sorted(duplicate_keys)
            entry["status"] = (
                "VALID_SYNTAX_REVIEW" if collisions or duplicate_keys or manifest_findings or base_findings
                else "VALID_SYNTAX"
            )
            counts["valid_syntax"] += 1
            counts["bytes_parsed"] += entry["bytes"]
            if collisions:
                counts["duplicate_id_review_files"] += 1
            if duplicate_keys:
                counts["duplicate_key_review_files"] += 1
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

    # A pair of individually tracked patch layers can still refer to one
    # another. Detect cycles in the tiny filename graph after decoding, not
    # by recursively loading the underlying JSON routes.
    cyclic_layers: set[str] = set()
    for origin in manual_base_edges:
        positions: dict[str, int] = {}
        chain: list[str] = []
        node = origin
        while node in manual_base_edges and node not in positions:
            positions[node] = len(chain)
            chain.append(node)
            node = manual_base_edges[node]
        if node in positions:
            cyclic_layers.update(chain[positions[node]:])
    if cyclic_layers:
        for entry in files:
            if entry["file"] not in cyclic_layers or entry.get("status") not in {
                "VALID_SYNTAX", "VALID_SYNTAX_REVIEW",
            }:
                continue
            findings = entry.setdefault("manual_base_reference_candidates", [])
            if not findings:
                counts["manual_base_reference_review_files"] += 1
            findings.append({"kind": "MANUAL_BASE_CYCLE_REVIEW"})
            entry["status"] = "VALID_SYNTAX_REVIEW"
    counts["manual_base_cycle_files"] = len(cyclic_layers)

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
        "guide_catalog_static_links": _verify_guide_catalog(
            guide_catalog, guide_headers, paths,
        ),
        "consumers_verified": False,
        "assets_verified": False,
        "worktree_clean": clean,
        "counts": counts,
        "files": files,
        "truncated": False,
        "automatic_deletion_authorized": False,
        "limits": [
            "Syntax PASS does not prove domain ID references, schema, active packaging or assets",
            "Duplicate ID/key candidates require source semantics before any cleanup",
            "Duplicate object keys are counted without invented JSON paths",
            "Guide Ultime manifest check covers declared chapter, branch and registry filenames only",
            "Guide catalog static links cover only names, IDs, categories and tracked filenames",
            "Git-tracked inventory excludes generated and user-local files",
        ],
    }
