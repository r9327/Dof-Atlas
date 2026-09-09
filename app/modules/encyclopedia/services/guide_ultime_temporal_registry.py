from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Objet JSON attendu: {path}")
    return payload


def _merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_temporal_registry(path: Path, *, _seen: set[Path] | None = None) -> dict[str, Any]:
    """Resolve a versioned manual temporal registry.

    Later versions may keep the previous audited registry immutable, patch existing
    entries and append explicitly versioned entries. Patches are keyed by the stable
    ``id`` field and are deep merged. Insertions require a fresh id; duplicate ids
    are rejected so a new timer can never shadow an older one silently.
    """

    path = Path(path).resolve()
    seen = set(_seen or ())
    if path in seen:
        raise ValueError(f"Cycle de registre temporel détecté: {path}")
    seen.add(path)

    source = _read(path)
    base_name = str(source.get("base_file") or "").strip()
    if not base_name:
        result = copy.deepcopy(source)
        result["_resolved_from"] = [path.name]
        return result

    base_path = path.parent / base_name
    if not base_path.is_file():
        raise FileNotFoundError(f"Base temporelle absente: {base_path}")
    result = load_temporal_registry(base_path, _seen=seen)

    reserved = {"base_file", "entry_patches", "entry_insertions"}
    for key, value in source.items():
        if key not in reserved:
            result[key] = copy.deepcopy(value)

    entries = [copy.deepcopy(row) for row in result.get("entries", []) if isinstance(row, dict)]
    by_id = {str(row.get("id") or ""): i for i, row in enumerate(entries)}
    if not by_id or len(by_id) != len(entries) or any(not key for key in by_id):
        raise ValueError(f"Ids temporels invalides dans la base de {path.name}")

    for entry_id, patch in (source.get("entry_patches") or {}).items():
        if entry_id not in by_id:
            raise KeyError(f"Timer patché absent: {entry_id!r} dans {path.name}")
        if not isinstance(patch, dict):
            raise ValueError(f"Patch temporel invalide: {entry_id!r}")
        entries[by_id[entry_id]] = _merge_dict(entries[by_id[entry_id]], patch)

    for row in source.get("entry_insertions", []) or []:
        if not isinstance(row, dict):
            raise ValueError(f"Insertion temporelle invalide dans {path.name}: {row!r}")
        entry_id = str(row.get("id") or "").strip()
        if not entry_id:
            raise ValueError(f"Insertion temporelle sans id dans {path.name}")
        if entry_id in by_id:
            raise ValueError(f"Timer inséré déjà existant: {entry_id!r} dans {path.name}")
        by_id[entry_id] = len(entries)
        entries.append(copy.deepcopy(row))

    if len({str(row.get("id") or "") for row in entries}) != len(entries):
        raise ValueError(f"Ids temporels dupliqués après composition: {path.name}")

    result["entries"] = entries
    resolved = list(result.get("_resolved_from", []) or [])
    resolved.append(path.name)
    result["_resolved_from"] = resolved
    return result
