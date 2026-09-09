from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = BASE / "manifest_v1.json"
CANONICAL_BONTA_FILE = "bonta_1_100_v17.json"
OCRE_COMPLETION_FILE = "ocre_completion_route_v2.json"
EXPECTED_KRALAMOURE_HOOK = "kralamoure_server_opening"
EXPECTED_CANONICAL_SUPPORT_FILES = {
    "astrub_class_branches": "astrub_class_branches_v1.json",
    "bonta_order_rank20": "bonta_order_rank20_v1.json",
    "bonta_order_rank40": "bonta_order_rank40_v1.json",
    "bonta_order_rank60": "bonta_order_rank60_v1.json",
    "bonta_order_rank80": "bonta_order_rank80_v1.json",
    "bonta_order_rank100": "bonta_order_rank100_v1.json",
    "bonta_1_100": CANONICAL_BONTA_FILE,
    "temporal_registry": "temporal_registry_v15.json",
    "ocre_capture_registry": "ocre_capture_registry_v1.json",
    "ocre_final_route": "ocre_final_route_v2.json",
    "success_contracts": "success_contracts_v2.json",
}

BONTA_DEPENDENT_CHAPTERS = {
    "level_51_70",
    "level_70_100",
    "level_100_120",
    "level_120_150",
    "level_150_170",
    "level_171_180",
    "level_181_190",
    "level_191_200",
    "level_200_plus",
}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Objet JSON attendu: {path}")
    return payload


def _dependency_files(payload: dict[str, Any], *, chapter_id: str, errors: list[dict[str, Any]]) -> list[str]:
    dependencies: list[str] = []
    for field in ("depends_on", "transversal_routes"):
        raw = payload.get(field, []) or []
        if not isinstance(raw, list):
            errors.append({"code": "dependency_field_not_list", "chapter": chapter_id, "field": field})
            continue
        for value in raw:
            if not isinstance(value, str):
                continue
            filename = value.strip()
            if filename.endswith(".json") and filename not in dependencies:
                dependencies.append(filename)
    return dependencies


def _manifest_support_files(canonical: dict[str, Any]) -> dict[str, str]:
    files: dict[str, str] = {}
    for section in ("conditional_routes", "transversal_routes"):
        for row in canonical.get(section, []) or []:
            if not isinstance(row, dict):
                continue
            item_id = str(row.get("id") or "").strip()
            filename = str(row.get("file") or "").strip()
            if item_id:
                files[item_id] = filename
    for key in ("temporal_registry", "ocre_capture_registry", "ocre_final_route", "success_contracts"):
        files[key] = str(canonical.get(key) or "").strip()
    return files


def _audit_critical_supports(canonical: dict[str, Any], errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actual = _manifest_support_files(canonical)
    expected_ids = set(EXPECTED_CANONICAL_SUPPORT_FILES)
    actual_ids = set(actual)
    if actual_ids != expected_ids:
        errors.append({
            "code": "canonical_support_id_set_drift",
            "expected_only": sorted(expected_ids - actual_ids),
            "actual_only": sorted(actual_ids - expected_ids),
        })

    checked: list[dict[str, Any]] = []
    for item_id, expected_file in EXPECTED_CANONICAL_SUPPORT_FILES.items():
        actual_file = actual.get(item_id, "")
        if actual_file != expected_file:
            errors.append({"code": "canonical_support_file_drift", "id": item_id, "expected": expected_file, "actual": actual_file})
        exists = bool(actual_file) and (BASE / actual_file).is_file()
        if actual_file and not exists:
            errors.append({"code": "canonical_support_file_missing", "id": item_id, "file": actual_file})
        checked.append({"id": item_id, "file": actual_file, "exists": exists})

    conditional = {
        str(row.get("id") or "").strip(): row
        for row in canonical.get("conditional_routes", []) or []
        if isinstance(row, dict)
    }
    class_branch = conditional.get("astrub_class_branches", {})
    if str(class_branch.get("selector") or "") != "actual_character_class" or class_branch.get("manual_selection_forbidden") is not True:
        errors.append({"code": "class_branch_selector_contract_drift", "actual": class_branch})

    for rank in (20, 40, 60, 80, 100):
        item_id = f"bonta_order_rank{rank}"
        row = conditional.get(item_id, {})
        if str(row.get("selector") or "") != "persisted_bonta_order" or row.get("exactly_one") is not True or row.get("unselected_hidden") is not True:
            errors.append({"code": "bonta_order_selector_contract_drift", "id": item_id, "actual": row})

    final_file = EXPECTED_CANONICAL_SUPPORT_FILES["ocre_final_route"]
    if (BASE / final_file).is_file():
        final_route = _load(BASE / final_file)
        actual_base = str(final_route.get("base_file") or "").strip()
        if actual_base != OCRE_COMPLETION_FILE:
            errors.append({"code": "ocre_final_base_drift", "expected": OCRE_COMPLETION_FILE, "actual": actual_base})

    completion_path = BASE / OCRE_COMPLETION_FILE
    if not completion_path.is_file():
        errors.append({"code": "ocre_completion_file_missing", "file": OCRE_COMPLETION_FILE})
    else:
        completion = load_manual_chapter(completion_path, _expand_hooks=False)
        dependencies = set(_dependency_files(completion, chapter_id="ocre_completion_route", errors=errors))
        expected_dependencies = {
            EXPECTED_CANONICAL_SUPPORT_FILES["ocre_capture_registry"],
            EXPECTED_CANONICAL_SUPPORT_FILES["temporal_registry"],
        }
        if dependencies != expected_dependencies:
            errors.append({"code": "ocre_completion_dependency_drift", "expected": sorted(expected_dependencies), "actual": sorted(dependencies)})
        kral = next(
            (row for row in completion.get("stages", []) or [] if isinstance(row, dict) and str(row.get("id") or "") == "OCRE-F4"),
            None,
        )
        actual_hook = str((kral or {}).get("temporal_hook") or "").strip()
        if actual_hook != EXPECTED_KRALAMOURE_HOOK:
            errors.append({"code": "ocre_kralamoure_temporal_hook_drift", "expected": EXPECTED_KRALAMOURE_HOOK, "actual": actual_hook})
        checked.append({
            "id": "ocre_completion_route",
            "file": OCRE_COMPLETION_FILE,
            "exists": True,
            "dependencies": sorted(dependencies),
            "kralamoure_temporal_hook": actual_hook,
        })

    return checked


def audit() -> dict[str, Any]:
    manifest = _load(MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    rows = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    rows.sort(key=lambda row: int(row.get("order") or 0))

    errors: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []
    critical_supports = _audit_critical_supports(canonical, errors)

    for meta in rows:
        chapter_id = str(meta.get("id") or "").strip()
        filename = str(meta.get("file") or "").strip()
        path = BASE / filename
        if not path.is_file():
            errors.append({"code": "canonical_file_missing", "chapter": chapter_id, "file": filename})
            continue

        try:
            composed = load_manual_chapter(path, _expand_hooks=False)
        except Exception as exc:
            errors.append({"code": "canonical_dependency_resolution_failed", "chapter": chapter_id, "file": filename, "error": str(exc)})
            continue

        dependencies = _dependency_files(composed, chapter_id=chapter_id, errors=errors)
        missing_files = sorted(dependency for dependency in dependencies if not (BASE / dependency).is_file())
        if missing_files:
            errors.append({"code": "dependency_file_missing", "chapter": chapter_id, "dependencies": missing_files})

        bonta_dependencies = sorted(dependency for dependency in dependencies if dependency.startswith("bonta_1_"))
        stale_bonta = [dependency for dependency in bonta_dependencies if dependency != CANONICAL_BONTA_FILE]
        if stale_bonta:
            errors.append({"code": "legacy_bonta_dependency", "chapter": chapter_id, "expected": CANONICAL_BONTA_FILE, "actual": stale_bonta})

        if chapter_id in BONTA_DEPENDENT_CHAPTERS and CANONICAL_BONTA_FILE not in dependencies:
            errors.append({"code": "canonical_bonta_dependency_missing", "chapter": chapter_id, "expected": CANONICAL_BONTA_FILE, "dependencies": dependencies})

        chapters.append({
            "id": chapter_id,
            "file": filename,
            "dependencies": dependencies,
            "bonta_dependencies": bonta_dependencies,
            "resolved_from": [str(value) for value in composed.get("_resolved_from", []) or []],
        })

    return {
        "status": "PASS" if not errors else "FAIL",
        "chapter_count": len(rows),
        "critical_dependency_count": len(critical_supports),
        "canonical_bonta_file": CANONICAL_BONTA_FILE,
        "bonta_dependent_chapters": sorted(BONTA_DEPENDENT_CHAPTERS),
        "critical_supports": critical_supports,
        "chapters": chapters,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit des dépendances canoniques du Guide Ultime manuel.")
    parser.add_argument("--strict", action="store_true")
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