from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = BASE / "manifest_v1.json"
LOCK = BASE / "canonical_lock_v1.json"
MANIFEST_SUPPORT_KEYS = ("temporal_registry", "ocre_capture_registry", "ocre_final_route", "success_contracts")
EXPECTED_LOCK_SCHEMA_VERSION = 4
EXPECTED_LOCK_ID = "guide_ultime_manual_pre_network_v1"
EXPECTED_ACTIVE_SOURCE_BASELINE_COMMIT = "618b66e679d478ee0885e9234dc3a17f0e90b74d"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Objet JSON attendu: {path}")
    return payload


def _raw_git_blob_sha(path: Path) -> str:
    content = path.read_bytes()
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def _git_blob_sha(path: Path) -> str:
    """Hash working-tree content as Git would store it for this repository path.

    `Path.read_bytes()` is not portable for a Git fingerprint on Windows because a
    clean checkout may expose CRLF while Git stores LF. `git hash-object --path`
    applies the same clean/text filters that Git uses for the tracked path, while
    still hashing the current working-tree content, so real edits continue to be
    detected.
    """
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return _raw_git_blob_sha(resolved)

    try:
        process = subprocess.run(
            ["git", "hash-object", f"--path={relative}", str(resolved)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        return _raw_git_blob_sha(resolved)

    sha = process.stdout.strip().lower()
    if process.returncode == 0 and len(sha) == 40 and all(char in "0123456789abcdef" for char in sha):
        return sha
    return _raw_git_blob_sha(resolved)


def _json_filename(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    filename = value.strip()
    if not filename.endswith(".json") or Path(filename).name != filename:
        return None
    return filename


def _local_json_file(value: Any) -> str | None:
    filename = _json_filename(value)
    if not filename:
        return None
    return filename if (BASE / filename).is_file() else None


def _locked_file(*, row: dict[str, Any], errors: list[dict[str, Any]], error_prefix: str) -> dict[str, Any] | None:
    item_id = str(row.get("id") or "").strip()
    filename = str(row.get("file") or "").strip()
    expected_sha = str(row.get("git_blob_sha") or "").strip()
    path = BASE / filename
    if not filename or not path.is_file():
        errors.append({"code": f"{error_prefix}_file_missing", "id": item_id, "file": filename})
        return None
    actual_sha = _git_blob_sha(path)
    if actual_sha != expected_sha:
        errors.append({
            "code": f"{error_prefix}_content_drift",
            "id": item_id,
            "file": filename,
            "expected": expected_sha,
            "actual": actual_sha,
        })
    return {"id": item_id, "file": filename, "git_blob_sha": actual_sha, "locked": actual_sha == expected_sha}


def _manifest_support_file(canonical: dict[str, Any], row: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    expected_file = str(row.get("file") or "").strip()
    item_id = str(row.get("id") or "").strip()
    manifest_key = str(row.get("manifest_key") or "").strip()
    if manifest_key:
        actual = str(canonical.get(manifest_key) or "").strip()
        if actual != expected_file:
            errors.append({
                "code": "support_manifest_key_drift",
                "id": item_id,
                "manifest_key": manifest_key,
                "expected": expected_file,
                "actual": actual,
            })
        return

    manifest_section = str(row.get("manifest_section") or "").strip()
    if manifest_section:
        values = [value for value in canonical.get(manifest_section, []) or [] if isinstance(value, dict)]
        match = next((value for value in values if str(value.get("id") or "") == item_id), None)
        if match is None:
            errors.append({"code": "support_manifest_entry_missing", "id": item_id, "manifest_section": manifest_section})
            return
        actual = str(match.get("file") or "").strip()
        if actual != expected_file:
            errors.append({
                "code": "support_manifest_entry_drift",
                "id": item_id,
                "manifest_section": manifest_section,
                "expected": expected_file,
                "actual": actual,
            })
        return

    referenced_by = str(row.get("referenced_by") or "").strip()
    if referenced_by:
        source_file, separator, field = referenced_by.partition("#")
        if separator != "#" or not source_file or not field:
            errors.append({"code": "support_reference_contract_invalid", "id": item_id, "referenced_by": referenced_by})
            return
        source_path = BASE / source_file
        if not source_path.is_file():
            errors.append({"code": "support_reference_source_missing", "id": item_id, "source": source_file})
            return
        actual = str(_load(source_path).get(field) or "").strip()
        if actual != expected_file:
            errors.append({
                "code": "support_reference_drift",
                "id": item_id,
                "source": source_file,
                "field": field,
                "expected": expected_file,
                "actual": actual,
            })


def _manifest_support_entries(canonical: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for section in ("conditional_routes", "transversal_routes"):
        for row in canonical.get(section, []) or []:
            if not isinstance(row, dict):
                continue
            entries.append({
                "id": str(row.get("id") or "").strip(),
                "file": str(row.get("file") or "").strip(),
                "binding": section,
                "binding_kind": "manifest_section",
            })
    for key in MANIFEST_SUPPORT_KEYS:
        entries.append({
            "id": key,
            "file": str(canonical.get(key) or "").strip(),
            "binding": key,
            "binding_kind": "manifest_key",
        })
    return entries


def _validate_manifest_support_lock(
    canonical: dict[str, Any],
    support_rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> list[dict[str, str]]:
    entries = _manifest_support_entries(canonical)
    support_by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    for row in support_rows:
        item_id = str(row.get("id") or "").strip()
        if not item_id:
            errors.append({"code": "support_lock_id_missing", "row": row})
            continue
        if item_id in support_by_id:
            duplicate_ids.add(item_id)
            continue
        support_by_id[item_id] = row
    if duplicate_ids:
        errors.append({"code": "support_lock_duplicate_ids", "ids": sorted(duplicate_ids)})

    for entry in entries:
        item_id = entry["id"]
        filename = entry["file"]
        if not item_id or not filename:
            errors.append({"code": "manifest_support_contract_invalid", "entry": entry})
            continue
        locked = support_by_id.get(item_id)
        if locked is None:
            errors.append({
                "code": "support_lock_missing_for_manifest_route",
                "id": item_id,
                "file": filename,
                "binding": entry["binding"],
            })
            continue
        actual_file = str(locked.get("file") or "").strip()
        if actual_file != filename:
            errors.append({
                "code": "support_lock_manifest_file_mismatch",
                "id": item_id,
                "expected": filename,
                "actual": actual_file,
            })
        binding_kind = entry["binding_kind"]
        actual_binding = str(locked.get(binding_kind) or "").strip()
        if actual_binding != entry["binding"]:
            errors.append({
                "code": "support_lock_binding_drift",
                "id": item_id,
                "binding_kind": binding_kind,
                "expected": entry["binding"],
                "actual": actual_binding,
            })
    return entries


def _effective_dependency_files(payload: dict[str, Any]) -> set[str]:
    dependencies: set[str] = set()
    for field in ("depends_on", "transversal_routes"):
        raw = payload.get(field) or []
        if not isinstance(raw, list):
            continue
        for value in raw:
            filename = _local_json_file(value)
            if filename:
                dependencies.add(filename)
    return dependencies


def _composition_source_files(
    path: Path,
    errors: list[dict[str, Any]],
    *,
    _seen: set[Path] | None = None,
) -> tuple[set[str], set[str]]:
    path = Path(path).resolve()
    seen = set(_seen or ())
    if path in seen:
        errors.append({"code": "active_composition_cycle", "file": path.name})
        return set(), set()
    seen.add(path)
    if not path.is_file():
        errors.append({"code": "active_source_missing", "file": path.name})
        return set(), set()
    try:
        source = _load(path)
    except Exception as exc:
        errors.append({"code": "active_source_raw_read_failed", "file": path.name, "error": str(exc)})
        return {path.name}, set()

    sources: set[str] = {path.name}
    import_roots: set[str] = set()
    base_name = str(source.get("base_file") or "").strip()
    if base_name:
        filename = _json_filename(base_name)
        if filename is None:
            errors.append({"code": "active_base_file_invalid", "file": path.name, "base_file": base_name})
        else:
            base_path = path.parent / filename
            if not base_path.is_file():
                errors.append({"code": "active_base_file_missing", "file": path.name, "base_file": filename})
            else:
                base_sources, base_imports = _composition_source_files(base_path, errors, _seen=seen)
                sources.update(base_sources)
                import_roots.update(base_imports)

    imports = source.get("stage_imports", []) or []
    if not isinstance(imports, list):
        errors.append({"code": "active_stage_imports_invalid", "file": path.name})
        return sources, import_roots
    for entry in imports:
        if not isinstance(entry, dict):
            errors.append({"code": "active_stage_import_invalid", "file": path.name, "entry": repr(entry)})
            continue
        filename = _json_filename(entry.get("file"))
        stage_id = str(entry.get("stage_id") or "").strip()
        if not filename or not stage_id:
            errors.append({"code": "active_stage_import_incomplete", "file": path.name, "entry": entry})
            continue
        import_path = path.parent / filename
        if not import_path.is_file():
            errors.append({
                "code": "active_stage_import_file_missing",
                "file": path.name,
                "import_file": filename,
                "stage_id": stage_id,
            })
            continue
        import_roots.add(filename)
        import_sources, nested_imports = _composition_source_files(import_path, errors, _seen=seen)
        sources.update(import_sources)
        import_roots.update(nested_imports)
    return sources, import_roots


def _route_level_hook_files(payload: dict[str, Any]) -> set[str]:
    files: set[str] = set()
    for stage in payload.get("stages", []) or []:
        if not isinstance(stage, dict):
            continue
        raw = stage.get("route_hooks")
        hooks = raw if isinstance(raw, list) else [raw] if raw else []
        for value in hooks:
            hook = str(value or "").strip()
            if not hook:
                continue
            filename = hook if hook.endswith(".json") else f"{hook}.json"
            local = _local_json_file(filename)
            if local:
                files.add(local)
    return files


def _active_source_files(canonical: dict[str, Any], lock: dict[str, Any], errors: list[dict[str, Any]]) -> list[str]:
    active: set[str] = {MANIFEST.name}
    processed: set[str] = set()
    queue: list[str] = []

    for row in canonical.get("chapters", []) or []:
        if isinstance(row, dict):
            filename = _json_filename(row.get("file"))
            if filename:
                queue.append(filename)
    for entry in _manifest_support_entries(canonical):
        filename = _json_filename(entry.get("file"))
        if filename:
            queue.append(filename)
    for row in lock.get("supporting_routes", []) or []:
        if isinstance(row, dict):
            filename = _json_filename(row.get("file"))
            if filename:
                queue.append(filename)

    while queue:
        filename = queue.pop()
        if filename in processed:
            continue
        processed.add(filename)
        path = BASE / filename
        if not path.is_file():
            errors.append({"code": "active_source_missing", "file": filename})
            continue
        try:
            payload = load_manual_chapter(path, _expand_hooks=False)
        except Exception as exc:
            errors.append({"code": "active_source_resolution_failed", "file": filename, "error": str(exc)})
            continue

        composition_sources, import_roots = _composition_source_files(path, errors)
        active.update(composition_sources)
        active.add(filename)
        for dependency in sorted(_effective_dependency_files(payload)):
            if dependency not in processed:
                queue.append(dependency)
        for import_root in sorted(import_roots):
            if import_root not in processed:
                queue.append(import_root)
        for hook_file in sorted(_route_level_hook_files(payload)):
            if hook_file not in processed:
                queue.append(hook_file)

    overlays = {
        str(row.get("file") or "").strip()
        for row in lock.get("noncanonical_overlays", []) or []
        if isinstance(row, dict) and str(row.get("file") or "").strip()
    }
    leaked = sorted(overlays.intersection(active))
    if leaked:
        errors.append({"code": "noncanonical_overlay_became_active", "files": leaked})
    return sorted(active)


def _git_baseline_blobs(baseline: str, errors: list[dict[str, Any]]) -> dict[str, str]:
    baseline = baseline.strip()
    if len(baseline) != 40 or any(char not in "0123456789abcdef" for char in baseline.lower()):
        errors.append({"code": "active_source_baseline_invalid", "baseline": baseline})
        return {}
    try:
        probe = subprocess.run(
            ["git", "cat-file", "-e", f"{baseline}^{{commit}}"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as exc:
        errors.append({"code": "git_unavailable_for_active_source_lock", "error": str(exc)})
        return {}
    if probe.returncode != 0:
        errors.append({
            "code": "active_source_baseline_unavailable",
            "baseline": baseline,
            "stderr": probe.stderr.strip(),
        })
        return {}

    tree = subprocess.run(
        ["git", "ls-tree", "-r", baseline, "--", "data/routes/guide_ultime_manual"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if tree.returncode != 0:
        errors.append({"code": "active_source_git_tree_failed", "stderr": tree.stderr.strip()})
        return {}

    blobs: dict[str, str] = {}
    for line in tree.stdout.splitlines():
        metadata, separator, repo_path = line.partition("\t")
        if not separator:
            continue
        parts = metadata.split()
        if len(parts) != 3 or parts[1] != "blob":
            continue
        filename = Path(repo_path.strip()).name
        sha = parts[2].strip()
        if filename in blobs and blobs[filename] != sha:
            errors.append({
                "code": "active_source_basename_collision",
                "file": filename,
                "first": blobs[filename],
                "second": sha,
            })
            continue
        blobs[filename] = sha
    return blobs


def _active_source_fingerprints(
    baseline: str,
    active_files: list[str],
    errors: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    baseline_blobs = _git_baseline_blobs(baseline, errors)
    rows: list[dict[str, Any]] = []
    drift: list[str] = []
    for filename in active_files:
        path = BASE / filename
        expected_sha = baseline_blobs.get(filename)
        if not path.is_file():
            errors.append({"code": "active_source_missing", "file": filename})
            rows.append({
                "file": filename,
                "expected_git_blob_sha": expected_sha or "",
                "actual_git_blob_sha": "",
                "locked": False,
            })
            drift.append(filename)
            continue
        actual_sha = _git_blob_sha(path)
        if not expected_sha:
            errors.append({
                "code": "active_source_not_in_baseline",
                "baseline": baseline,
                "file": filename,
                "actual": actual_sha,
            })
            locked = False
        else:
            locked = actual_sha == expected_sha
            if not locked:
                errors.append({
                    "code": "active_source_content_drift",
                    "baseline": baseline,
                    "file": filename,
                    "expected": expected_sha,
                    "actual": actual_sha,
                })
        if not locked:
            drift.append(filename)
        rows.append({
            "file": filename,
            "expected_git_blob_sha": expected_sha or "",
            "actual_git_blob_sha": actual_sha,
            "locked": locked,
        })
    return rows, sorted(set(drift))


def audit() -> dict[str, Any]:
    manifest = _load(MANIFEST)
    lock = _load(LOCK)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    manifest_rows = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    lock_rows = [row for row in lock.get("chapters", []) or [] if isinstance(row, dict)]
    support_rows = [row for row in lock.get("supporting_routes", []) or [] if isinstance(row, dict)]
    manifest_rows.sort(key=lambda row: int(row.get("order") or 0))
    lock_rows.sort(key=lambda row: int(row.get("order") or 0))

    errors: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []
    supporting_routes: list[dict[str, Any]] = []

    declared_schema = int(lock.get("schema_version") or 0)
    if declared_schema != EXPECTED_LOCK_SCHEMA_VERSION:
        errors.append({"code": "lock_schema_version_drift", "expected": EXPECTED_LOCK_SCHEMA_VERSION, "actual": declared_schema})
    declared_lock_id = str(lock.get("lock_id") or "").strip()
    if declared_lock_id != EXPECTED_LOCK_ID:
        errors.append({"code": "lock_id_drift", "expected": EXPECTED_LOCK_ID, "actual": declared_lock_id})
    declared_baseline = str(lock.get("active_source_baseline_commit") or "").strip()
    if declared_baseline != EXPECTED_ACTIVE_SOURCE_BASELINE_COMMIT:
        errors.append({
            "code": "active_source_baseline_drift",
            "expected": EXPECTED_ACTIVE_SOURCE_BASELINE_COMMIT,
            "actual": declared_baseline,
        })

    manifest_support_entries = _validate_manifest_support_lock(canonical, support_rows, errors)
    if len(manifest_rows) != len(lock_rows):
        errors.append({"code": "chapter_count_drift", "manifest": len(manifest_rows), "lock": len(lock_rows)})

    manifest_by_id = {str(row.get("id") or ""): row for row in manifest_rows}
    lock_by_id = {str(row.get("id") or ""): row for row in lock_rows}
    if set(manifest_by_id) != set(lock_by_id):
        errors.append({
            "code": "chapter_id_set_drift",
            "manifest_only": sorted(set(manifest_by_id) - set(lock_by_id)),
            "lock_only": sorted(set(lock_by_id) - set(manifest_by_id)),
        })

    total_resolved = 0
    for lock_row in lock_rows:
        chapter_id = str(lock_row.get("id") or "").strip()
        expected_file = str(lock_row.get("file") or "").strip()
        expected_count = int(lock_row.get("stage_count") or 0)
        expected_sha = str(lock_row.get("git_blob_sha") or "").strip()
        manifest_row = manifest_by_id.get(chapter_id)
        if manifest_row is None:
            continue

        actual_file = str(manifest_row.get("file") or "").strip()
        declared_count = int(manifest_row.get("stage_count") or 0)
        if actual_file != expected_file:
            errors.append({"code": "canonical_file_drift", "chapter": chapter_id, "expected": expected_file, "actual": actual_file})
        if declared_count != expected_count:
            errors.append({"code": "manifest_stage_count_drift", "chapter": chapter_id, "expected": expected_count, "actual": declared_count})

        path = BASE / expected_file
        if not path.is_file():
            errors.append({"code": "locked_file_missing", "chapter": chapter_id, "file": expected_file})
            continue
        actual_sha = _git_blob_sha(path)
        if actual_sha != expected_sha:
            errors.append({
                "code": "locked_content_drift",
                "chapter": chapter_id,
                "file": expected_file,
                "expected": expected_sha,
                "actual": actual_sha,
            })
        try:
            payload = load_manual_chapter(path)
        except Exception as exc:
            errors.append({
                "code": "locked_chapter_resolution_failed",
                "chapter": chapter_id,
                "file": expected_file,
                "error": str(exc),
            })
            continue

        stages = [stage for stage in payload.get("stages", []) or [] if isinstance(stage, dict)]
        resolved_count = len(stages)
        total_resolved += resolved_count
        if resolved_count != expected_count:
            errors.append({"code": "resolved_stage_count_drift", "chapter": chapter_id, "expected": expected_count, "actual": resolved_count})
        ids = [str(stage.get("id") or "").strip() for stage in stages]
        missing_ids = [index for index, stage_id in enumerate(ids) if not stage_id]
        if missing_ids:
            errors.append({"code": "missing_stage_id", "chapter": chapter_id, "indexes": missing_ids})
        duplicates = sorted({stage_id for stage_id in ids if stage_id and ids.count(stage_id) > 1})
        if duplicates:
            errors.append({"code": "duplicate_stage_id_in_chapter", "chapter": chapter_id, "stage_ids": duplicates})
        chapters.append({
            "id": chapter_id,
            "file": expected_file,
            "stage_count": resolved_count,
            "git_blob_sha": actual_sha,
            "resolved_from": [str(value) for value in payload.get("_resolved_from", []) or []],
            "locked": actual_sha == expected_sha and resolved_count == expected_count,
        })

    expected_total = int(lock.get("locked_stage_count") or 0)
    if total_resolved != expected_total:
        errors.append({"code": "locked_total_stage_count_drift", "expected": expected_total, "actual": total_resolved})

    for support_row in support_rows:
        _manifest_support_file(canonical, support_row, errors)
        locked = _locked_file(row=support_row, errors=errors, error_prefix="support")
        if locked is not None:
            supporting_routes.append(locked)

    active_source_files = _active_source_files(canonical, lock, errors)
    baseline = EXPECTED_ACTIVE_SOURCE_BASELINE_COMMIT
    active_sources, active_source_drift = _active_source_fingerprints(baseline, active_source_files, errors)

    return {
        "lock_id": declared_lock_id,
        "status": "PASS" if not errors else "FAIL",
        "chapter_count": len(lock_rows),
        "supporting_route_count": len(support_rows),
        "manifest_support_count": len(manifest_support_entries),
        "locked_stage_count": expected_total,
        "resolved_stage_count": total_resolved,
        "active_source_lock_mode": str(lock.get("active_source_lock_mode") or ""),
        "active_source_declared_baseline_commit": declared_baseline,
        "active_source_baseline_commit": baseline,
        "active_source_count": len(active_source_files),
        "active_source_files": active_source_files,
        "active_sources": active_sources,
        "active_source_drift": active_source_drift,
        "chapters": chapters,
        "supporting_routes": supporting_routes,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Vérifie le verrou canonique des données du Guide Ultime avant réseau.")
    parser.add_argument("--strict", action="store_true", help="Retourne 1 si le verrou a dérivé.")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = audit()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 1 if args.strict and report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
