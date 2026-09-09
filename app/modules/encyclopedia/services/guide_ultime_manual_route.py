from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from threading import RLock
from typing import Any


_CACHE_LOCK = RLock()
_CHAPTER_CACHE: dict[tuple[object, ...], dict[str, Any]] = {}
_MAX_CHAPTER_CACHE_ENTRIES = 96


def _manual_tree_signature(directory: Path) -> tuple[tuple[str, int, int], ...]:
    rows: list[tuple[str, int, int]] = []
    try:
        files = sorted(Path(directory).glob("*.json"), key=lambda path: path.name.casefold())
    except OSError:
        return ()
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue
        rows.append((path.name, int(stat.st_mtime_ns), int(stat.st_size)))
    return tuple(rows)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Objet JSON attendu: {path}")
    return payload


def _apply_stage_patch(row: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(row)
    for key, value in (patch.get("replace") or {}).items():
        result[key] = copy.deepcopy(value)
    for key, values in (patch.get("append") or {}).items():
        current = list(result.get(key, []) or [])
        current.extend(copy.deepcopy(list(values or [])))
        result[key] = current
    for key, values in (patch.get("prepend") or {}).items():
        current = list(result.get(key, []) or [])
        result[key] = copy.deepcopy(list(values or [])) + current
    return result


def _insert_anchored_stage(stages: list[dict[str, Any]], insertion: dict[str, Any], new_stage: dict[str, Any], *, source_name: str) -> None:
    new_id = str(new_stage.get("id") or "").strip()
    if not new_id:
        raise ValueError(f"Insertion sans id dans {source_name}")
    if any(str(row.get("id") or "") == new_id for row in stages):
        raise ValueError(f"Étape insérée déjà existante: {new_id}")
    after = str(insertion.get("after") or "").strip()
    before = str(insertion.get("before") or "").strip()
    if bool(after) == bool(before):
        raise ValueError(f"Insertion {new_id}: renseigner exactement un anchor after/before")
    anchor = after or before
    anchor_index = next((i for i, row in enumerate(stages) if str(row.get("id") or "") == anchor), None)
    if anchor_index is None:
        raise KeyError(f"Ancre d'insertion absente {anchor!r} pour {new_id}")
    stages.insert(anchor_index + 1 if after else anchor_index, copy.deepcopy(new_stage))


def _stable_key(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return repr(value)


def _merge_sequence(existing: Any, incoming: Any, *, prepend: bool = True) -> list[Any]:
    left = existing if isinstance(existing, list) else ([] if existing in (None, "") else [existing])
    right = incoming if isinstance(incoming, list) else ([] if incoming in (None, "") else [incoming])
    rows = (right + left) if prepend else (left + right)
    result: list[Any] = []
    seen: set[str] = set()
    for row in rows:
        key = _stable_key(row)
        if key in seen:
            continue
        seen.add(key)
        result.append(copy.deepcopy(row))
    return result


def _route_hook_ids(stage: dict[str, Any]) -> list[str]:
    values: list[str] = []
    raw = stage.get("route_hooks")
    rows = raw if isinstance(raw, list) else [raw] if raw else []
    for value in rows:
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text)

    transversal = str(stage.get("transversal") or "")
    for match in re.finditer(r"\b[A-Z][A-Z0-9_]*-\d+[A-Z0-9_-]*\b", transversal):
        value = match.group(0)
        if value not in values:
            values.append(value)
    return values


def _route_file_path(path: Path, hook_id: str) -> Path | None:
    """Return the declared route file represented by a route-level hook, if any.

    Some authored ``route_hooks`` are stage ids such as ``BNT-36`` and must be
    expanded into the canonical player card. Others are whole route/condition
    identifiers such as ``bonta_order_rank80_v1`` or ``ocre_final_route_v1``;
    those are consumed by their dedicated runtime logic and must not be mistaken
    for stage ids. A route-level hook is recognized only when a real sibling JSON
    file exists, so a typo in an explicit stage hook still fails loudly.
    """

    value = str(hook_id or "").strip()
    if not value:
        return None
    candidate = path.parent / (value if value.endswith(".json") else f"{value}.json")
    return candidate.resolve() if candidate.is_file() else None


def _expand_route_hooks(
    payload: dict[str, Any],
    path: Path,
    seen: set[Path],
) -> dict[str, Any]:
    """Expand authored transversal stage ids into the player-facing canonical stage.

    Manual chapters intentionally reference Bonta/transversal macro stages instead
    of copying them. A stage hook is not useful to the player unless its prerequisites,
    preparation and actions are present in the resolved chapter. Expansion happens
    at composition time so runtime, coverage and prerequisite audits all consume the
    same concrete route.

    Whole-route hooks (for example a persisted Bonta Order route or the Ocre final
    route) remain untouched for their dedicated runtime consumers. Stage sources may
    be declared either in ``depends_on`` or in the historical ``transversal_routes``
    field; both are explicit declarations and therefore safe to resolve.
    """

    stages = [copy.deepcopy(row) for row in payload.get("stages", []) if isinstance(row, dict)]
    referenced = {hook for stage in stages for hook in _route_hook_ids(stage)}
    if not referenced:
        result = copy.deepcopy(payload)
        result["stages"] = stages
        return result

    route_level_hooks = {hook for hook in referenced if _route_file_path(path, hook) is not None}
    stage_references = referenced - route_level_hooks
    if not stage_references:
        result = copy.deepcopy(payload)
        result["stages"] = stages
        return result

    dependencies: list[Any] = []
    dependencies.extend(payload.get("depends_on", []) or [])
    dependencies.extend(payload.get("transversal_routes", []) or [])
    dependency_rows: dict[str, list[dict[str, Any]]] = {}
    seen_dependency_files: set[Path] = set()
    for raw_name in dependencies:
        filename = str(raw_name or "").strip()
        if not filename.endswith(".json"):
            continue
        dependency_path = (path.parent / filename).resolve()
        if dependency_path in seen_dependency_files:
            continue
        seen_dependency_files.add(dependency_path)
        if not dependency_path.is_file() or dependency_path == path:
            continue
        try:
            dependency = load_manual_chapter(dependency_path, _seen=seen)
        except (FileNotFoundError, KeyError, ValueError):
            continue
        for row in dependency.get("stages", []) or []:
            if not isinstance(row, dict):
                continue
            stage_id = str(row.get("id") or "").strip()
            if stage_id in stage_references:
                dependency_rows.setdefault(stage_id, []).append(row)

    unresolved = sorted(stage_references - set(dependency_rows))
    if unresolved:
        raise KeyError(f"route_hooks non résolus dans {path.name}: {unresolved}")

    ambiguous = {
        stage_id: rows
        for stage_id, rows in dependency_rows.items()
        if len({_stable_key(row) for row in rows}) > 1
    }
    if ambiguous:
        raise ValueError(f"route_hooks ambigus dans {path.name}: {sorted(ambiguous)}")

    list_fields = (
        "quests",
        "quest_sequence",
        "parallel_quests",
        "preparation",
        "a_preparer",
        "resources",
        "required_items",
        "items_to_prepare",
        "manual_preparation",
        "keep_in_bank",
        "bank_items",
        "take",
        "waypoints",
        "route",
        "conditional_actions",
        "instructions",
        "opportunistic",
        "progress_also",
        "progress_alongside",
        "dungeons",
        "monsters",
        "successes",
        "before_leaving_area",
        "before_leaving",
        "before_leave",
        "avant_de_partir",
        "hard_exit",
        "hard_stop",
        "conditions",
        "runtime_conditions",
        "runtime_gates",
        "hard_runtime_gates",
        "temporal_hooks",
    )
    prerequisite_fields = (
        "entry",
        "activation",
        "prerequisite",
        "prerequisites",
        "requirements",
        "hard_gates",
    )

    for stage in stages:
        hook_ids = _route_hook_ids(stage)
        if not hook_ids:
            continue
        for hook_id in hook_ids:
            if hook_id in route_level_hooks:
                continue
            hook = copy.deepcopy(dependency_rows[hook_id][0])
            for field in prerequisite_fields:
                if hook.get(field) in (None, "", []):
                    continue
                if stage.get(field) in (None, "", []):
                    stage[field] = copy.deepcopy(hook[field])
                else:
                    stage[field] = _merge_sequence(stage[field], hook[field], prepend=True)
            for field in list_fields:
                if hook.get(field) in (None, "", []):
                    continue
                stage[field] = _merge_sequence(stage.get(field), hook[field], prepend=True)

            hook_dungeon = hook.get("dungeon")
            if hook_dungeon:
                if not stage.get("dungeon"):
                    stage["dungeon"] = copy.deepcopy(hook_dungeon)
                elif _stable_key(stage.get("dungeon")) != _stable_key(hook_dungeon):
                    stage["dungeons"] = _merge_sequence(
                        stage.get("dungeons"),
                        [hook_dungeon, stage.get("dungeon")],
                        prepend=True,
                    )

            for field in ("temporal_hook", "runtime_gate"):
                if hook.get(field) in (None, ""):
                    continue
                if stage.get(field) in (None, ""):
                    stage[field] = copy.deepcopy(hook[field])
                elif _stable_key(stage[field]) != _stable_key(hook[field]):
                    plural = f"{field}s"
                    stage[plural] = _merge_sequence(stage.get(plural), [hook[field], stage[field]], prepend=True)

    result = copy.deepcopy(payload)
    result["stages"] = stages
    return result


def _load_manual_chapter_uncached(
    path: Path,
    *,
    _seen: set[Path] | None = None,
    _expand_hooks: bool = True,
) -> dict[str, Any]:
    """Resolve a manual chapter, including versioned base/patch compositions.

    A composed chapter keeps the previous verified route immutable and stores only
    deliberate corrections. Resolution is deterministic and never invents data:
    stage patches can replace/append known fields, ``stage_removals`` can explicitly
    retire obsolete macro-stages after a causal reorder, ``stage_imports`` can move
    an already-authored stage from another manual file without copying its source
    text, insertions identify their exact anchor stage, and ``stage_order`` may
    reorder the final known stage ids without adding or duplicating any stage.
    Explicit ``route_hooks``/``transversal`` stage ids are finally expanded from
    declared dependency files so player-facing data and audits see the real route.
    """

    path = Path(path).resolve()
    seen = set(_seen or ())
    if path in seen:
        raise ValueError(f"Cycle de composition détecté: {path}")
    seen.add(path)

    source = _read_json(path)
    base_name = str(source.get("base_file") or "").strip()
    if not base_name:
        result = copy.deepcopy(source)
        result["_resolved_from"] = [path.name]
        return _expand_route_hooks(result, path, seen) if _expand_hooks else result

    base_path = path.parent / base_name
    if not base_path.is_file():
        raise FileNotFoundError(f"Base de route manuelle absente: {base_path}")
    result = load_manual_chapter(base_path, _seen=seen, _expand_hooks=False)
    result = copy.deepcopy(result)

    reserved = {
        "base_file",
        "stage_patches",
        "stage_removals",
        "stage_imports",
        "insertions",
        "stage_order",
    }
    for key, value in source.items():
        if key not in reserved:
            result[key] = copy.deepcopy(value)

    stages = [copy.deepcopy(row) for row in result.get("stages", []) if isinstance(row, dict)]
    by_id = {str(row.get("id") or ""): index for index, row in enumerate(stages)}

    for stage_id, patch in (source.get("stage_patches") or {}).items():
        if not isinstance(patch, dict):
            raise ValueError(f"Patch invalide pour {stage_id!r} dans {path.name}")
        if stage_id not in by_id:
            raise KeyError(f"Étape patchée absente: {stage_id!r} dans {path.name}")
        stages[by_id[stage_id]] = _apply_stage_patch(stages[by_id[stage_id]], patch)

    removals = source.get("stage_removals", []) or []
    if not isinstance(removals, list) or not all(isinstance(value, str) and value.strip() for value in removals):
        raise ValueError(f"stage_removals invalide dans {path.name}")
    removal_ids = [value.strip() for value in removals]
    if len(removal_ids) != len(set(removal_ids)):
        raise ValueError(f"stage_removals contient des doublons dans {path.name}: {removal_ids}")
    if removal_ids:
        current_ids = {str(row.get("id") or "").strip() for row in stages}
        unknown = sorted(set(removal_ids) - current_ids)
        if unknown:
            raise KeyError(f"Étapes à retirer absentes dans {path.name}: {unknown}")
        removal_set = set(removal_ids)
        stages = [row for row in stages if str(row.get("id") or "").strip() not in removal_set]

    imports = source.get("stage_imports", []) or []
    if not isinstance(imports, list):
        raise ValueError(f"stage_imports invalide dans {path.name}")

    # Imported stages and local insertions may deliberately anchor to another
    # operation declared later (cross-chapter causal moves). Resolve all source
    # rows first, then repeatedly insert every operation whose anchor is already
    # present. If a complete pass makes no progress, the remaining anchor graph
    # is invalid/cyclic and resolution fails loudly.
    structural_ops: list[tuple[str, dict[str, Any], dict[str, Any], str | None]] = []
    for entry in imports:
        if not isinstance(entry, dict):
            raise ValueError(f"stage_imports contient une entrée invalide dans {path.name}: {entry!r}")
        filename = str(entry.get("file") or "").strip()
        stage_id = str(entry.get("stage_id") or "").strip()
        if not filename or not stage_id:
            raise ValueError(f"Import de stage incomplet dans {path.name}: {entry!r}")
        import_path = (path.parent / filename).resolve()
        if not import_path.is_file():
            raise FileNotFoundError(f"Fichier de stage importé absent: {import_path}")
        imported = load_manual_chapter(import_path, _seen=seen)
        imported_stage = next(
            (row for row in imported.get("stages", []) or [] if isinstance(row, dict) and str(row.get("id") or "").strip() == stage_id),
            None,
        )
        if imported_stage is None:
            raise KeyError(f"Étape importée absente {stage_id!r} dans {filename}")
        new_stage = copy.deepcopy(imported_stage)
        new_id = str(entry.get("new_id") or "").strip()
        if new_id:
            new_stage["id"] = new_id
        new_stage = _apply_stage_patch(new_stage, entry)
        structural_ops.append(("import", entry, new_stage, f"{filename}#{stage_id}"))

    for insertion in source.get("insertions", []) or []:
        if not isinstance(insertion, dict) or not isinstance(insertion.get("stage"), dict):
            raise ValueError(f"Insertion invalide dans {path.name}: {insertion!r}")
        structural_ops.append(("insertion", insertion, copy.deepcopy(insertion["stage"]), None))

    imported_sources: list[str] = []
    pending = list(structural_ops)
    while pending:
        deferred: list[tuple[str, dict[str, Any], dict[str, Any], str | None]] = []
        progress = False
        for kind, entry, new_stage, import_ref in pending:
            try:
                _insert_anchored_stage(stages, entry, new_stage, source_name=path.name)
            except KeyError:
                deferred.append((kind, entry, new_stage, import_ref))
                continue
            progress = True
            if kind == "import" and import_ref:
                imported_sources.append(import_ref)
        if not deferred:
            break
        if not progress:
            unresolved = [
                {
                    "id": str(stage.get("id") or ""),
                    "after": str(entry.get("after") or ""),
                    "before": str(entry.get("before") or ""),
                }
                for _kind, entry, stage, _ref in deferred
            ]
            raise KeyError(f"Ancres structurelles non résolues dans {path.name}: {unresolved}")
        pending = deferred

    requested_order = source.get("stage_order")
    if requested_order is not None:
        if not isinstance(requested_order, list) or not all(isinstance(value, str) and value.strip() for value in requested_order):
            raise ValueError(f"stage_order invalide dans {path.name}")
        requested_ids = [value.strip() for value in requested_order]
        current_ids = [str(row.get("id") or "").strip() for row in stages]
        if len(requested_ids) != len(set(requested_ids)):
            raise ValueError(f"stage_order contient des doublons dans {path.name}: {requested_ids}")
        missing = sorted(set(current_ids) - set(requested_ids))
        unknown = sorted(set(requested_ids) - set(current_ids))
        if len(requested_ids) != len(current_ids) or missing or unknown:
            raise ValueError(
                f"stage_order doit contenir exactement toutes les étapes de {path.name}; "
                f"absentes={missing}, inconnues={unknown}"
            )
        rows_by_id = {str(row.get("id") or "").strip(): row for row in stages}
        stages = [rows_by_id[stage_id] for stage_id in requested_ids]

    result["stages"] = stages
    result["stage_count"] = len(stages)
    resolved_from = list(result.get("_resolved_from", []) or [])
    resolved_from.append(path.name)
    result["_resolved_from"] = resolved_from
    if imported_sources:
        result["_stage_imports_resolved"] = imported_sources
    return _expand_route_hooks(result, path, seen) if _expand_hooks else result


def load_manual_chapter(
    path: Path,
    *,
    _seen: set[Path] | None = None,
    _expand_hooks: bool = True,
) -> dict[str, Any]:
    """Resolve one chapter and cache only complete top-level compositions."""

    resolved = Path(path).resolve()
    if _seen is not None:
        return _load_manual_chapter_uncached(
            resolved,
            _seen=_seen,
            _expand_hooks=_expand_hooks,
        )
    key: tuple[object, ...] = (
        str(resolved),
        bool(_expand_hooks),
        _manual_tree_signature(resolved.parent),
    )
    with _CACHE_LOCK:
        cached = _CHAPTER_CACHE.get(key)
        if cached is not None:
            return copy.deepcopy(cached)
    result = _load_manual_chapter_uncached(resolved, _expand_hooks=_expand_hooks)
    frozen = copy.deepcopy(result)
    with _CACHE_LOCK:
        stale = [
            cached_key
            for cached_key in _CHAPTER_CACHE
            if cached_key[0] == str(resolved) and cached_key[1] == bool(_expand_hooks)
        ]
        for cached_key in stale:
            _CHAPTER_CACHE.pop(cached_key, None)
        _CHAPTER_CACHE[key] = frozen
        while len(_CHAPTER_CACHE) > _MAX_CHAPTER_CACHE_ENTRIES:
            _CHAPTER_CACHE.pop(next(iter(_CHAPTER_CACHE)))
    return copy.deepcopy(frozen)


def clear_manual_route_cache() -> None:
    with _CACHE_LOCK:
        _CHAPTER_CACHE.clear()
