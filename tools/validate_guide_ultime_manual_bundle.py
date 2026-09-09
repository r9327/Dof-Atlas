from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import RAW_QUEST_DATA_DIR
from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.modules.encyclopedia.services.guide_ultime_temporal_registry import load_temporal_registry
from app.quest_catalog import normalize_text


BASE = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = BASE / "manifest_v1.json"
COVERAGE = BASE / "dofus_argente_coverage_v1.json"
SENTINEL = "-2147483648"
COORD_RE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")
THREAD_LABELS = {normalize_text("Tour du Monde")}
ASTRUB_EXTRA_REQUIRED = {
    "Scène de ménage",
    "Shushu et Lulu",
    "Bien velu, c'est Kerubim",
    "Donjon en lambeaux",
    "Le Maître des clefs",
    "Le réceptacle des Dofus",
}


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Objet JSON attendu: {path}")
    return payload


def walk(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]")


def route_quest_names(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for stage in payload.get("stages", []) or []:
        if not isinstance(stage, dict):
            continue
        for field in ("quests", "quest_sequence", "parallel_quests"):
            for raw in stage.get(field, []) or []:
                name = str(raw or "").strip()
                if name and not name.startswith("conditional:"):
                    names.append(name)
        for waypoint_field in ("waypoints",):
            for waypoint in stage.get(waypoint_field, []) or []:
                if not isinstance(waypoint, dict):
                    continue
                for raw in waypoint.get("quests", []) or []:
                    name = str(raw or "").strip()
                    if name and not name.startswith("conditional:"):
                        names.append(name)
    return names


def coverage_names(payload: dict[str, Any], area: str) -> list[str]:
    block = payload.get(area) if isinstance(payload.get(area), dict) else {}
    successes = block.get("successes") if isinstance(block.get("successes"), dict) else {}
    result: list[str] = []
    for rows in successes.values():
        for raw in rows or []:
            name = str(raw or "").strip()
            if name and not name.startswith("conditional:"):
                result.append(name)
    return result


def catalog_index() -> dict[str, list[int]]:
    catalog = QuestProvider(data_dir=RAW_QUEST_DATA_DIR).get_catalog()
    result: dict[str, list[int]] = {}
    for quest in catalog.quests:
        result.setdefault(normalize_text(quest.name), []).append(int(quest.id))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Valide le bundle canonique Guide Ultime manuel.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    warn: list[dict[str, Any]] = []
    manifest = load(MANIFEST)
    coverage = load(COVERAGE)

    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    chapter_rows = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    chapter_payloads: dict[str, dict[str, Any]] = {}

    for row in chapter_rows:
        chapter_id = str(row.get("id") or "").strip()
        filename = str(row.get("file") or "").strip()
        path = BASE / filename
        if not filename or not path.is_file():
            hard.append({"code": "canonical_file_missing", "chapter": chapter_id, "file": filename})
            continue
        try:
            payload = load_manual_chapter(path)
        except Exception as exc:
            hard.append({"code": "canonical_composition_failed", "chapter": chapter_id, "file": filename, "error": repr(exc)})
            continue
        chapter_payloads[chapter_id] = payload
        stages = [stage for stage in payload.get("stages", []) or [] if isinstance(stage, dict)]
        declared = row.get("stage_count")
        if isinstance(declared, int) and declared != len(stages):
            hard.append({"code": "stage_count_mismatch", "chapter": chapter_id, "manifest": declared, "actual": len(stages)})
        payload_declared = payload.get("stage_count")
        if isinstance(payload_declared, int) and payload_declared != len(stages):
            hard.append({"code": "resolved_stage_count_mismatch", "chapter": chapter_id, "payload": payload_declared, "actual": len(stages)})
        ids = [str(stage.get("id") or "").strip() for stage in stages]
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            hard.append({"code": "stage_ids_invalid", "chapter": chapter_id, "ids": ids})
        for stage in stages:
            stage_id = str(stage.get("id") or "")
            checkpoint = stage.get("pause_checkpoint") if isinstance(stage.get("pause_checkpoint"), dict) else None
            compact_pause = stage.get("pause") if isinstance(stage.get("pause"), list) else None
            if checkpoint is None and not compact_pause:
                hard.append({"code": "pause_checkpoint_missing", "chapter": chapter_id, "stage": stage_id})

    # Never allow the historical Dofus INT32_MIN sentinel back into manual sources,
    # including superseded files: they remain useful audit history.
    for path in BASE.glob("*.json"):
        payload = load(path)
        for json_path, value in walk(payload):
            if value == -2147483648 or (isinstance(value, str) and SENTINEL in value):
                hard.append({"code": "sentinel_present", "file": path.name, "path": json_path})
            if isinstance(value, str):
                for match in COORD_RE.finditer(value):
                    x, y = int(match.group(1)), int(match.group(2))
                    if abs(x) > 10000 or abs(y) > 10000:
                        hard.append({"code": "invalid_coordinate_text", "file": path.name, "path": json_path, "value": match.group(0)})

    branch_file = BASE / "astrub_class_branches_v1.json"
    if not branch_file.is_file():
        hard.append({"code": "class_branch_file_missing"})
        branches: dict[str, Any] = {}
    else:
        branch_payload = load(branch_file)
        branches = branch_payload.get("branches") if isinstance(branch_payload.get("branches"), dict) else {}
        if len(branches) != 19:
            hard.append({"code": "class_branch_count", "expected": 19, "actual": len(branches)})
        class_quests = [str(row.get("quest") or "").strip() for row in branches.values() if isinstance(row, dict)]
        if len(class_quests) != len(set(normalize_text(v) for v in class_quests if v)):
            hard.append({"code": "class_quest_duplicate"})
        for klass, row in branches.items():
            if not isinstance(row, dict):
                hard.append({"code": "class_branch_invalid", "class": klass})
                continue
            points = row.get("route_points") or []
            if not points:
                hard.append({"code": "class_route_empty", "class": klass})
            for point in points:
                if not isinstance(point, list) or len(point) != 2 or not all(isinstance(v, int) and abs(v) <= 10000 for v in point):
                    hard.append({"code": "class_route_point_invalid", "class": klass, "point": point})
            for prep in row.get("preparation", []) or []:
                if isinstance(prep, dict) and prep.get("conditional") is not True:
                    hard.append({"code": "class_preparation_not_conditional", "class": klass, "row": prep})

    # Coverage accounting: 26 current Incarnam + 32 Astrub = 58.
    inc_cov = coverage_names(coverage, "incarnam")
    ast_cov = coverage_names(coverage, "astrub")
    if len(inc_cov) != 26:
        hard.append({"code": "incarnam_coverage_count", "expected": 26, "actual": len(inc_cov)})
    if len(ast_cov) != 31:
        hard.append({"code": "astrub_fixed_coverage_count", "expected": 31, "actual": len(ast_cov)})
    if len(inc_cov) + len(ast_cov) + 1 != 58:
        hard.append({"code": "dofus_argente_58_invariant_failed"})

    inc_route = {normalize_text(name) for name in route_quest_names(chapter_payloads.get("incarnam", {}))}
    ast_route = {normalize_text(name) for name in route_quest_names(chapter_payloads.get("astrub", {}))}
    for name in inc_cov:
        if normalize_text(name) not in inc_route:
            hard.append({"code": "incarnam_coverage_missing_from_route", "quest": name})
    for name in ast_cov:
        if normalize_text(name) not in ast_route:
            hard.append({"code": "astrub_coverage_missing_from_route", "quest": name})
    for name in sorted(ASTRUB_EXTRA_REQUIRED, key=normalize_text):
        if normalize_text(name) not in ast_route:
            hard.append({"code": "astrub_global_thread_missing_from_route", "quest": name})

    temporal_name = str(canonical.get("temporal_registry") or "").strip()
    temporal_path = BASE / temporal_name
    temporal: dict[str, Any] = {}
    if not temporal_name or not temporal_path.is_file():
        hard.append({"code": "temporal_registry_missing", "file": temporal_name})
    else:
        try:
            temporal = load_temporal_registry(temporal_path)
        except Exception as exc:
            hard.append({"code": "temporal_registry_composition_failed", "file": temporal_name, "error": repr(exc)})
        if temporal:
            entries = [row for row in temporal.get("entries", []) or [] if isinstance(row, dict)]
            ids = [str(row.get("id") or "") for row in entries]
            if len(ids) != len(set(ids)) or any(not value for value in ids):
                hard.append({"code": "temporal_entry_ids_invalid", "ids": ids})
            pandawushu = next((row for row in entries if row.get("id") == "pandawushu_grade_chain"), None)
            if not isinstance(pandawushu, dict):
                hard.append({"code": "pandawushu_timer_missing"})
            else:
                intro = pandawushu.get("intro_wait_policy") if isinstance(pandawushu.get("intro_wait_policy"), dict) else {}
                choices = intro.get("attestation_choices") if isinstance(intro.get("attestation_choices"), list) else []
                actual_choices = {(row.get("cost_kamas"), row.get("delay_hours")) for row in choices if isinstance(row, dict)}
                expected_choices = {(50000, 0), (10000, 2), (1000, 24), (0, 48)}
                if actual_choices != expected_choices:
                    hard.append({"code": "pandawushu_attestation_waits_invalid", "expected": sorted(expected_choices), "actual": sorted(actual_choices)})
                if intro.get("bad_quiz_answer_delay_hours") != 24:
                    hard.append({"code": "pandawushu_bad_quiz_delay_invalid", "actual": intro.get("bad_quiz_answer_delay_hours")})
                grade_delay = pandawushu.get("delay_policy") if isinstance(pandawushu.get("delay_policy"), dict) else {}
                if grade_delay.get("first_24h_timer_starts_after") != "Rokwa : Voie du poing" or grade_delay.get("delay_hours_between_following_grades") != 24:
                    hard.append({"code": "pandawushu_grade_delay_invalid", "delay_policy": grade_delay})

    if not args.skip_catalog:
        try:
            index = catalog_index()
        except Exception as exc:
            hard.append({"code": "local_catalog_unavailable", "error": repr(exc)})
            index = {}
        if index:
            explicit_names = set(inc_cov + ast_cov + list(ASTRUB_EXTRA_REQUIRED))
            explicit_names.update(str(row.get("quest") or "").strip() for row in branches.values() if isinstance(row, dict))
            explicit_names.update(
                name for payload in chapter_payloads.values() for name in route_quest_names(payload)
                if normalize_text(name) not in THREAD_LABELS
            )
            for name in sorted(explicit_names, key=normalize_text):
                if not name or name.startswith("conditional:"):
                    continue
                matches = index.get(normalize_text(name), [])
                if not matches:
                    hard.append({"code": "quest_not_in_local_catalog", "quest": name})
                elif len(matches) > 1:
                    warn.append({"code": "quest_name_ambiguous_in_catalog", "quest": name, "ids": matches})

    result = {
        "ok": not hard,
        "canonical_chapter_count": len(chapter_payloads),
        "canonical_stage_count": sum(len(payload.get("stages", []) or []) for payload in chapter_payloads.values()),
        "dofus_argente_target_count": 58,
        "class_branch_count": len(branches),
        "temporal_entry_count": len(temporal.get("entries", []) or []) if temporal else 0,
        "hard_error_count": len(hard),
        "warning_count": len(warn),
        "hard_errors": hard,
        "warnings": warn,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and hard:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
