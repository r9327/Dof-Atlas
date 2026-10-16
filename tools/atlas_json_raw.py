"""Read-only evidence for the public Doduda inputs owned by the build locks.

Never discover arbitrary cache files or read character/profile state. A dataset
fingerprint identifies bytes, independently of the code SHA that consumed them.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from scripts.windows.quest_assets import RELATIVE_ROOT, read_lock


def _fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _array(value: object) -> list:
    if isinstance(value, dict):
        value = value.get("Array")
    if not isinstance(value, list):
        raise ValueError("Expected a Doduda array")
    return value


def _public_path(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Unsafe source path in build lock")
    path = root / RELATIVE_ROOT / relative
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != root):
        raise ValueError("Symlink source refused")
    if not path.resolve().is_relative_to((root / RELATIVE_ROOT).resolve()):
        raise ValueError("Source outside public raw directory")
    return path


def _relations(tables: dict[str, list[dict]]) -> list[dict]:
    specs = (
        ("quests", "categoryId", "quest_categories", False),
        ("quests", "stepIds", "quest_steps", True),
        ("quest_steps", "questId", "quests", False),
        ("quest_steps", "objectiveIds", "quest_objectives", True),
        ("quest_objectives", "stepId", "quest_steps", False),
        ("achievements", "categoryId", "achievement_categories", False),
        ("achievements", "objectiveIds", "achievement_objectives", True),
        ("achievement_objectives", "achievementId", "achievements", False),
        ("recipes", "resultId", "items", False),
        ("recipes", "jobId", "jobs", False),
        ("recipes", "ingredientIds", "items", True),
    )
    results = []
    for source, field, target, multiple in specs:
        if source not in tables or target not in tables:
            results.append({"relation": f"{source}.{field}", "status": "BLOCKED"})
            continue
        ids = {row["id"] for row in tables[target] if type(row.get("id")) is int}
        missing, checked = [], 0
        for row in tables[source]:
            values = _array(row.get(field)) if multiple else [row.get(field)]
            for ident in values:
                checked += 1
                if type(ident) is not int or ident not in ids:
                    missing.append({"source_id": row.get("id", row.get("resultId")),
                                    "target_id": ident})
        results.append({"relation": f"{source}.{field}", "target": target,
                        "checked": checked, "missing_count": len(missing),
                        "missing": missing, "status": "REVIEW" if missing else "PASS"})
    if "recipes" in tables:
        invalid = []
        for row in tables["recipes"]:
            ids, quantities = _array(row.get("ingredientIds")), _array(row.get("quantities"))
            if (not ids or len(ids) != len(quantities) or len(ids) != len(set(ids))
                    or any(type(qty) is not int or qty <= 0 for qty in quantities)):
                invalid.append(row.get("resultId"))
        results.append({"relation": "recipes.quantities", "checked": len(tables["recipes"]),
                        "invalid_result_ids": invalid, "status": "REVIEW" if invalid else "PASS"})
    return results


def audit_raw_inputs(root: Path, candidate_sha: str) -> dict:
    """Snapshot only locked public inputs; unresolved source links stay REVIEW."""
    if not re.fullmatch(r"[0-9a-f]{40}", candidate_sha):
        raise ValueError("An exact code SHA is required")
    root = root.resolve()
    errors, records, tables, duplicates = [], [], {}, []
    try:
        quest = read_lock(root)
        craft = json.loads((root / "scripts/windows/craft_assets_lock.json").read_text())
        if (craft.get("schema_version") != 1 or set(craft.get("assets", {})) != {"recipes.json"}
                or craft.get("source_repo") != quest["source_repo"]
                or craft.get("tag") != quest["tag"]):
            raise ValueError("Craft and Quest locks must identify the same public release")
        pins = dict(quest["assets"])
        for name, pin in craft["assets"].items():
            if name in pins and pins[name] != pin:
                raise ValueError("Conflicting public source pins")
            pins[name] = pin
        identity = {"repository": quest["source_repo"], "tag": quest["tag"]}
        for name, pin in sorted(pins.items()):
            try:
                path = _public_path(root, name)
                size = path.stat().st_size
                if not 0 < size <= 128 * 1024 * 1024:
                    raise ValueError("Source size outside audit bounds")
                content = path.read_bytes()
                digest = hashlib.sha256(content).hexdigest()
                if size != pin["size"] or digest != pin["sha256"]:
                    raise ValueError("Source differs from the reviewed release pin")
                payload = json.loads(content)
                del content
                if name == "languages/fr.json":
                    values = payload["entries"]
                    if not isinstance(values, dict) or not values:
                        raise ValueError("Empty or malformed French dictionary")
                    row = {"entries": len(values), "schema": "entries"}
                else:
                    refs = payload["references"]["RefIds"]
                    if not isinstance(refs, list) or not refs:
                        raise ValueError("Empty or malformed Doduda references")
                    values = [ref["data"] for ref in refs if isinstance(ref, dict)
                              and isinstance(ref.get("data"), dict)]
                    if len(values) != len(refs):
                        raise ValueError("Malformed Doduda reference row")
                    # Nested effect instances have no entity id and are counted
                    # separately rather than misreported as duplicate items.
                    ids = [value["id"] for value in values if type(value.get("id")) is int]
                    repeated = sorted(key for key, count in Counter(ids).items() if count > 1)
                    if repeated:
                        duplicates.append({"source": name, "ids": repeated})
                    row = {"references": len(refs), "entity_ids": len(ids),
                           "classes": dict(Counter(ref.get("type", {}).get("class", "unknown")
                                                   for ref in refs)), "schema": "references.RefIds"}
                    tables[Path(name).stem] = values
                records.append({"path": name, "bytes": size, "sha256": digest, **row})
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append({"source": name, "error": type(exc).__name__, "reason": str(exc)})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        identity = None
        errors.append({"source": "build_locks", "error": type(exc).__name__, "reason": str(exc)})
    try:
        relations = _relations(tables)
    except (TypeError, ValueError) as exc:
        relations = []
        errors.append({"source": "relations", "error": type(exc).__name__, "reason": str(exc)})
    content_identity = {"source": identity,
                        "files": [{k: row[k] for k in ("path", "bytes", "sha256")} for row in records]}
    return {"schema_version": 1, "kind": "public_raw_inputs", "candidate_sha": candidate_sha,
            "status": "BLOCKED" if errors else "PASS", "source": identity,
            "dataset_fingerprint": _fingerprint(content_identity), "files": records,
            "errors": errors, "duplicate_entity_ids": duplicates, "relations": relations,
            "relation_status": "REVIEW" if duplicates or any(r["status"] != "PASS" for r in relations) else "PASS",
            "limitations": ["Only public sources explicitly owned by Quest/Craft build locks are read.",
                            "Missing raw links are observations, not proof of a player-visible defect.",
                            "Private progression/configuration is neither read nor fingerprinted."]}


def verify_raw_inputs(before: dict, after: dict) -> None:
    """No PASS across an unavailable source, another code SHA or changed bytes."""
    for report in (before, after):
        if (not isinstance(report, dict)
                or report.get("schema_version") != 1 or report.get("kind") != "public_raw_inputs"
                or report.get("status") != "PASS" or report.get("errors")):
            raise ValueError("Incomplete public input evidence")
        if not re.fullmatch(r"[0-9a-f]{40}", str(report.get("candidate_sha", ""))):
            raise ValueError("Invalid code SHA in public input evidence")
        identity = {"source": report["source"],
                    "files": [{k: row[k] for k in ("path", "bytes", "sha256")} for row in report["files"]]}
        if not report["files"] or _fingerprint(identity) != report["dataset_fingerprint"]:
            raise ValueError("Invalid public input fingerprint")
    if (before["candidate_sha"] != after["candidate_sha"]
            or before["dataset_fingerprint"] != after["dataset_fingerprint"]):
        raise ValueError("Code SHA or public dataset changed during validation")
