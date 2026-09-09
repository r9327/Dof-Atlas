from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import RAW_QUEST_DATA_DIR
from app.modules.encyclopedia.providers import QuestProvider
from app.quest_catalog import normalize_text


MANUAL_ROUTE_DIR = ROOT / "data" / "routes" / "guide_ultime_manual"
SENTINEL_COORD = -2147483648


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Objet JSON attendu: {path}")
    return payload


def _safe_coord(value: Any) -> int | None:
    try:
        coord = int(value)
    except (TypeError, ValueError):
        return None
    if coord == SENTINEL_COORD or abs(coord) > 10000:
        return None
    return coord


def _iter_quest_names(stage: dict[str, Any]) -> Iterable[tuple[str, str]]:
    for name in stage.get("quest_sequence", []) or []:
        if str(name or "").strip():
            yield "quest_sequence", str(name).strip()
    for name in stage.get("parallel_quests", []) or []:
        if str(name or "").strip():
            yield "parallel_quests", str(name).strip()
    for waypoint in stage.get("waypoints", []) or []:
        if not isinstance(waypoint, dict):
            continue
        for name in waypoint.get("quests", []) or []:
            if str(name or "").strip():
                yield "waypoints", str(name).strip()


def _iter_locations(stage: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for key in ("start", "end"):
        row = stage.get(key)
        if isinstance(row, dict):
            yield key, row
    for index, row in enumerate(stage.get("waypoints", []) or []):
        if isinstance(row, dict):
            yield f"waypoints[{index}]", row


def validate_route(path: Path, *, strict: bool) -> dict[str, Any]:
    payload = _read_json(path)
    catalog = QuestProvider(data_dir=RAW_QUEST_DATA_DIR).get_catalog()
    names: dict[str, list[int]] = {}
    for quest in catalog.quests:
        key = normalize_text(quest.name)
        names.setdefault(key, []).append(int(quest.id))

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    stages = [row for row in payload.get("stages", []) or [] if isinstance(row, dict)]
    seen_stage_ids: set[str] = set()
    referenced_names: set[str] = set()

    for stage_index, stage in enumerate(stages):
        stage_id = str(stage.get("id") or "").strip()
        if not stage_id:
            errors.append({"code": "stage_id_missing", "stage_index": stage_index})
        elif stage_id in seen_stage_ids:
            errors.append({"code": "stage_id_duplicate", "stage_id": stage_id})
        else:
            seen_stage_ids.add(stage_id)

        checkpoint = stage.get("pause_checkpoint")
        if not isinstance(checkpoint, dict) or checkpoint.get("safe") is not True:
            errors.append({"code": "pause_checkpoint_missing", "stage_id": stage_id})

        for source, quest_name in _iter_quest_names(stage):
            key = normalize_text(quest_name)
            referenced_names.add(key)
            matches = names.get(key, [])
            if not matches:
                errors.append({
                    "code": "quest_name_not_in_local_catalog",
                    "stage_id": stage_id,
                    "source": source,
                    "quest_name": quest_name,
                })
            elif len(matches) > 1:
                warnings.append({
                    "code": "quest_name_ambiguous",
                    "stage_id": stage_id,
                    "quest_name": quest_name,
                    "quest_ids": matches,
                })

        for location_key, location in _iter_locations(stage):
            has_x = "x" in location and location.get("x") is not None
            has_y = "y" in location and location.get("y") is not None
            if has_x != has_y:
                errors.append({
                    "code": "coordinate_pair_incomplete",
                    "stage_id": stage_id,
                    "location": location_key,
                    "x": location.get("x"),
                    "y": location.get("y"),
                })
            if has_x and has_y:
                x = _safe_coord(location.get("x"))
                y = _safe_coord(location.get("y"))
                if x is None or y is None:
                    errors.append({
                        "code": "invalid_coordinate",
                        "stage_id": stage_id,
                        "location": location_key,
                        "x": location.get("x"),
                        "y": location.get("y"),
                    })

    resource_plan = payload.get("resource_plan") if isinstance(payload.get("resource_plan"), dict) else {}
    for row in resource_plan.get("collect_before_leaving_incarnam", []) or []:
        if not isinstance(row, dict):
            continue
        quantity = row.get("quantity")
        if not isinstance(quantity, int) or quantity <= 0:
            errors.append({"code": "invalid_resource_quantity", "row": row})

    summary = {
        "route": path.name,
        "stage_count": len(stages),
        "unique_quest_name_count": len(referenced_names),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if strict and errors:
        raise SystemExit(1)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Valide les routes Guide Ultime manuelles contre le catalogue local.")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    paths = args.paths or sorted(MANUAL_ROUTE_DIR.glob("*.json"))
    if not paths:
        raise SystemExit("Aucune route manuelle trouvée.")
    failed = False
    for path in paths:
        try:
            validate_route(path, strict=args.strict)
        except SystemExit as exc:
            if int(exc.code or 0) != 0:
                failed = True
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
