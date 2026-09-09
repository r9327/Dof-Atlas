from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import RAW_QUEST_DATA_DIR
from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.quest_catalog import normalize_text

BASE = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = BASE / "manifest_v1.json"
EXPECTED_ORDER_KEYS = {"coeur vaillant", "oeil attentif", "esprit salvateur"}
EXPECTED_EARLY_OCRE = {
    "Shin Larve", "Rakoopeur", "Scarabosse Doré", "Bworkette",
    "Craqueleur Légendaire", "Corailleur Magistral",
}


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Objet JSON attendu: {path}")
    return payload


def catalog_index() -> dict[str, list[int]]:
    catalog = QuestProvider(data_dir=RAW_QUEST_DATA_DIR).get_catalog()
    result: dict[str, list[int]] = {}
    for quest in catalog.quests:
        result.setdefault(normalize_text(quest.name), []).append(int(quest.id))
    return result


def first_rank_order(stages: list[dict[str, Any]]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for stage in stages:
        for raw in stage.get("ranks", []) or []:
            if isinstance(raw, int) and raw not in seen:
                seen.add(raw)
                result.append(raw)
    return result


def explicit_quest_names(payload: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for row in payload.get("rank_contract", []) or []:
        if isinstance(row, dict):
            name = str(row.get("quest") or "").strip()
            if name:
                names.add(name)
    for stage in payload.get("stages", []) or []:
        if not isinstance(stage, dict):
            continue
        for raw in stage.get("quests", []) or []:
            name = str(raw or "").strip()
            if name and not name.startswith("conditional:"):
                names.add(name)
    return names


def validate_order_route(
    hard: list[dict[str, Any]],
    conditional_rows: list[dict[str, Any]],
    route_id: str,
    expected_next_rank: int,
    *,
    must_keep_order: bool,
) -> tuple[dict[str, Any], set[str]]:
    row = next((item for item in conditional_rows if item.get("id") == route_id), None)
    if row is None:
        hard.append({"code": "order_route_missing_from_manifest", "route": route_id})
        return {}, set()
    path = BASE / str(row.get("file") or "")
    if not path.is_file():
        hard.append({"code": "order_file_missing", "route": route_id, "file": path.name})
        return {}, set()
    payload = load(path)
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    if set(options) != EXPECTED_ORDER_KEYS:
        hard.append({"code": "order_options_invalid", "route": route_id, "actual": sorted(options)})
    selection = payload.get("selection_policy") if isinstance(payload.get("selection_policy"), dict) else {}
    if selection.get("exactly_one") is not True:
        hard.append({"code": "order_exactly_one_not_locked", "route": route_id})
    if must_keep_order and selection.get("order_change_forbidden") is not True:
        hard.append({"code": "order_change_not_forbidden", "route": route_id})
    names: set[str] = set()
    for order_name, option in options.items():
        if not isinstance(option, dict):
            hard.append({"code": "order_option_invalid", "route": route_id, "order": order_name})
            continue
        quest = str(option.get("quest") or "").strip()
        if not quest:
            hard.append({"code": "order_quest_missing", "route": route_id, "order": order_name})
        else:
            names.add(quest)
        if not isinstance(option.get("route"), list) or not option.get("route"):
            hard.append({"code": "order_route_empty", "route": route_id, "order": order_name})
        gate = option.get("next_order_gate") if isinstance(option.get("next_order_gate"), dict) else {}
        if gate.get("alignment_rank") != expected_next_rank:
            hard.append({"code": "order_next_gate_invalid", "route": route_id, "order": order_name, "gate": gate})
    return payload, names


def main() -> None:
    parser = argparse.ArgumentParser(description="Valide Bonta/Ordres/Ocre et les gros hooks du Guide Ultime manuel.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    warn: list[dict[str, Any]] = []
    manifest = load(MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}

    transversal_rows = [row for row in canonical.get("transversal_routes", []) or [] if isinstance(row, dict)]
    bonta_row = next((row for row in transversal_rows if row.get("id") == "bonta_1_40"), None)
    bonta: dict[str, Any] = {}
    if bonta_row is None:
        hard.append({"code": "bonta_1_40_missing_from_manifest"})
    else:
        path = BASE / str(bonta_row.get("file") or "")
        if not path.is_file():
            hard.append({"code": "bonta_file_missing", "file": path.name})
        else:
            bonta = load_manual_chapter(path)

    if bonta:
        if bonta.get("quest_range") != [1, 40]:
            hard.append({"code": "bonta_range_invalid", "expected": [1, 40], "actual": bonta.get("quest_range")})
        stages = [row for row in bonta.get("stages", []) or [] if isinstance(row, dict)]
        expected = list(range(1, 41))
        actual = first_rank_order(stages)
        if actual != expected:
            hard.append({"code": "bonta_rank_first_appearance_invalid", "expected": expected, "actual": actual})
        covered = {rank for stage in stages for rank in (stage.get("ranks", []) or []) if isinstance(rank, int)}
        if covered != set(expected):
            hard.append({"code": "bonta_rank_coverage_invalid", "missing": sorted(set(expected)-covered), "extra": sorted(covered-set(expected))})
        ids = [str(stage.get("id") or "").strip() for stage in stages]
        if len(ids) != len(set(ids)) or any(not value for value in ids):
            hard.append({"code": "bonta_stage_ids_invalid"})
        for required in ("BNT-07", "BNT-15"):
            if required not in ids:
                hard.append({"code": "bonta_order_gate_stage_missing", "stage": required})

    conditional_rows = [row for row in canonical.get("conditional_routes", []) or [] if isinstance(row, dict)]
    order20, names20 = validate_order_route(hard, conditional_rows, "bonta_order_rank20", 40, must_keep_order=False)
    order40, names40 = validate_order_route(hard, conditional_rows, "bonta_order_rank40", 60, must_keep_order=True)
    if order20 and order40:
        if set(order20.get("options", {})) != set(order40.get("options", {})):
            hard.append({"code": "order_keys_changed_between_20_and_40"})
        rank40_manifest = next((row for row in conditional_rows if row.get("id") == "bonta_order_rank40"), {})
        if rank40_manifest.get("same_order_as_rank20") is not True:
            hard.append({"code": "manifest_does_not_lock_same_order_at_40"})

    ocre_name = str(canonical.get("ocre_capture_registry") or "").strip()
    ocre_path = BASE / ocre_name
    ocre: dict[str, Any] = {}
    if not ocre_name or not ocre_path.is_file():
        hard.append({"code": "ocre_registry_missing", "file": ocre_name})
    else:
        ocre = load(ocre_path)
        rules = ocre.get("rules") if isinstance(ocre.get("rules"), dict) else {}
        if rules.get("classic_monsters_required") is not False:
            hard.append({"code": "ocre_classic_monster_policy_stale"})
        if rules.get("bosses_required") is not True or rules.get("archimonsters_required") is not True:
            hard.append({"code": "ocre_required_sections_invalid"})
        steps = ocre.get("boss_steps") if isinstance(ocre.get("boss_steps"), dict) else {}
        if set(steps) != {"1", "2", "3"}:
            hard.append({"code": "ocre_boss_steps_invalid", "actual": sorted(steps)})
        flattened = [str(name) for key in ("1", "2", "3") for name in steps.get(key, []) or []]
        if len([normalize_text(x) for x in flattened]) != len(set(normalize_text(x) for x in flattened)):
            hard.append({"code": "ocre_boss_duplicate"})
        missing = sorted(EXPECTED_EARLY_OCRE - set(flattened))
        if missing:
            hard.append({"code": "ocre_early_boss_missing", "bosses": missing})

    chapter_rows = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    l70_row = next((row for row in chapter_rows if row.get("id") == "level_70_100"), None)
    l70: dict[str, Any] = {}
    if l70_row is None:
        hard.append({"code": "level_70_100_missing_from_manifest"})
    else:
        path = BASE / str(l70_row.get("file") or "")
        if not path.is_file():
            hard.append({"code": "level_70_100_file_missing", "file": path.name})
        else:
            l70 = load_manual_chapter(path)
            stages = [row for row in l70.get("stages", []) or [] if isinstance(row, dict)]
            if len(stages) != 16:
                hard.append({"code": "level_70_100_stage_count_invalid", "expected": 16, "actual": len(stages)})
            by_id = {str(row.get("id") or ""): row for row in stages}
            prep = by_id.get("L70-10H")
            chap = by_id.get("L70-11")
            if not prep:
                hard.append({"code": "hurlements_pre_chapiteau_stage_missing"})
            if not chap:
                hard.append({"code": "chapiteau_stage_missing"})
            else:
                quests = {normalize_text(str(q)) for q in chap.get("quests", []) or []}
                for name in ("Le spectacle vivant", "La lettre anonyme", "La grande parade"):
                    if normalize_text(name) not in quests:
                        hard.append({"code": "chapiteau_shared_quest_missing", "quest": name})

    if not args.skip_catalog:
        try:
            index = catalog_index()
        except Exception as exc:
            hard.append({"code": "local_catalog_unavailable", "error": repr(exc)})
            index = {}
        if index:
            names = explicit_quest_names(bonta) | names20 | names40
            if l70:
                names |= explicit_quest_names(l70)
            for name in sorted(names, key=normalize_text):
                matches = index.get(normalize_text(name), [])
                if not matches:
                    hard.append({"code": "transversal_quest_not_in_local_catalog", "quest": name})
                elif len(matches) > 1:
                    warn.append({"code": "transversal_quest_name_ambiguous", "quest": name, "ids": matches})

    result = {
        "ok": not hard,
        "bonta_rank_first_appearance": first_rank_order([row for row in bonta.get("stages", []) or [] if isinstance(row, dict)]) if bonta else [],
        "order20_options": sorted((order20.get("options") or {}).keys()) if order20 else [],
        "order40_options": sorted((order40.get("options") or {}).keys()) if order40 else [],
        "level_70_100_stage_count": len(l70.get("stages", []) or []) if l70 else 0,
        "ocre_boss_count": sum(len(ocre.get("boss_steps", {}).get(key, []) or []) for key in ("1", "2", "3")) if ocre else 0,
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
