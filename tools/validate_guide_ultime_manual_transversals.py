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
    "Shin Larve",
    "Rakoopeur",
    "Scarabosse Doré",
    "Bworkette",
    "Craqueleur Légendaire",
    "Corailleur Magistral",
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
            if not isinstance(raw, int):
                continue
            if raw not in seen:
                seen.add(raw)
                result.append(raw)
    return result


def explicit_bonta_names(payload: dict[str, Any]) -> set[str]:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Valide les fils transversaux du Guide Ultime manuel.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    warn: list[dict[str, Any]] = []
    manifest = load(MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}

    transversal_rows = [row for row in canonical.get("transversal_routes", []) or [] if isinstance(row, dict)]
    bonta_row = next((row for row in transversal_rows if str(row.get("id") or "").startswith("bonta_")), None)
    if bonta_row is None:
        hard.append({"code": "bonta_transversal_missing"})
        bonta: dict[str, Any] = {}
    else:
        bonta_path = BASE / str(bonta_row.get("file") or "")
        if not bonta_path.is_file():
            hard.append({"code": "bonta_file_missing", "file": bonta_path.name})
            bonta = {}
        else:
            bonta = load_manual_chapter(bonta_path)

    if bonta:
        quest_range = bonta.get("quest_range")
        if quest_range != [1, 22]:
            hard.append({"code": "bonta_range_invalid", "expected": [1, 22], "actual": quest_range})
        stages = [row for row in bonta.get("stages", []) or [] if isinstance(row, dict)]
        rank_order = first_rank_order(stages)
        expected = list(range(1, 23))
        if rank_order != expected:
            hard.append({"code": "bonta_rank_first_appearance_invalid", "expected": expected, "actual": rank_order})
        rank_values = {
            raw
            for stage in stages
            for raw in (stage.get("ranks", []) or [])
            if isinstance(raw, int)
        }
        if rank_values != set(expected):
            hard.append({"code": "bonta_rank_coverage_invalid", "missing": sorted(set(expected) - rank_values), "extra": sorted(rank_values - set(expected))})
        ids = [str(stage.get("id") or "").strip() for stage in stages]
        if len(ids) != len(set(ids)) or any(not value for value in ids):
            hard.append({"code": "bonta_stage_ids_invalid", "ids": ids})
        if not any("BNT-07" == value for value in ids):
            hard.append({"code": "bonta_order_gate_stage_missing"})
        if not any("BNT-08" == value for value in ids):
            hard.append({"code": "bonta_21_22_stage_missing"})

    conditional_rows = [row for row in canonical.get("conditional_routes", []) or [] if isinstance(row, dict)]
    order_row = next((row for row in conditional_rows if row.get("id") == "bonta_order_rank20"), None)
    if order_row is None:
        hard.append({"code": "bonta_order_route_missing_from_manifest"})
        order_payload: dict[str, Any] = {}
    else:
        order_path = BASE / str(order_row.get("file") or "")
        if not order_path.is_file():
            hard.append({"code": "bonta_order_file_missing", "file": order_path.name})
            order_payload = {}
        else:
            order_payload = load(order_path)

    order_names: set[str] = set()
    if order_payload:
        options = order_payload.get("options") if isinstance(order_payload.get("options"), dict) else {}
        if set(options) != EXPECTED_ORDER_KEYS:
            hard.append({"code": "bonta_order_options_invalid", "expected": sorted(EXPECTED_ORDER_KEYS), "actual": sorted(options)})
        quest_keys: set[str] = set()
        for order_name, option in options.items():
            if not isinstance(option, dict):
                hard.append({"code": "bonta_order_option_invalid", "order": order_name})
                continue
            quest = str(option.get("quest") or "").strip()
            if not quest:
                hard.append({"code": "bonta_order_quest_missing", "order": order_name})
            else:
                key = normalize_text(quest)
                if key in quest_keys:
                    hard.append({"code": "bonta_order_quest_duplicate", "quest": quest})
                quest_keys.add(key)
                order_names.add(quest)
            route = option.get("route") if isinstance(option.get("route"), list) else []
            if not route:
                hard.append({"code": "bonta_order_route_empty", "order": order_name})
            gate = option.get("next_order_gate") if isinstance(option.get("next_order_gate"), dict) else {}
            if gate.get("alignment_rank") != 40:
                hard.append({"code": "bonta_next_order_gate_invalid", "order": order_name, "gate": gate})
        selection = order_payload.get("selection_policy") if isinstance(order_payload.get("selection_policy"), dict) else {}
        if selection.get("exactly_one") is not True:
            hard.append({"code": "bonta_order_exactly_one_not_locked"})

    ocre_name = str(canonical.get("ocre_capture_registry") or "").strip()
    ocre_path = BASE / ocre_name
    if not ocre_name or not ocre_path.is_file():
        hard.append({"code": "ocre_registry_missing", "file": ocre_name})
        ocre: dict[str, Any] = {}
    else:
        ocre = load(ocre_path)

    if ocre:
        rules = ocre.get("rules") if isinstance(ocre.get("rules"), dict) else {}
        if rules.get("classic_monsters_required") is not False:
            hard.append({"code": "ocre_classic_monster_policy_stale"})
        if rules.get("bosses_required") is not True or rules.get("archimonsters_required") is not True:
            hard.append({"code": "ocre_required_sections_invalid"})
        boss_steps = ocre.get("boss_steps") if isinstance(ocre.get("boss_steps"), dict) else {}
        if set(boss_steps) != {"1", "2", "3"}:
            hard.append({"code": "ocre_boss_steps_invalid", "actual": sorted(boss_steps)})
        flattened: list[str] = [str(name) for key in ("1", "2", "3") for name in boss_steps.get(key, []) or []]
        normalized = [normalize_text(name) for name in flattened]
        if len(normalized) != len(set(normalized)):
            hard.append({"code": "ocre_boss_duplicate"})
        missing_early = sorted(EXPECTED_EARLY_OCRE - set(flattened))
        if missing_early:
            hard.append({"code": "ocre_early_boss_missing", "bosses": missing_early})
        early_rows = [row for row in ocre.get("early_route_state", []) or [] if isinstance(row, dict)]
        early_named = {str(row.get("boss") or "") for row in early_rows}
        for required in EXPECTED_EARLY_OCRE:
            if required not in early_named:
                hard.append({"code": "ocre_early_route_state_missing", "boss": required})

    if not args.skip_catalog:
        try:
            index = catalog_index()
        except Exception as exc:
            hard.append({"code": "local_catalog_unavailable", "error": repr(exc)})
            index = {}
        if index:
            names = explicit_bonta_names(bonta) | order_names
            for name in sorted(names, key=normalize_text):
                matches = index.get(normalize_text(name), [])
                if not matches:
                    hard.append({"code": "transversal_quest_not_in_local_catalog", "quest": name})
                elif len(matches) > 1:
                    warn.append({"code": "transversal_quest_name_ambiguous", "quest": name, "ids": matches})

    result = {
        "ok": not hard,
        "bonta_rank_first_appearance": first_rank_order([row for row in bonta.get("stages", []) or [] if isinstance(row, dict)]) if bonta else [],
        "bonta_order_options": sorted((order_payload.get("options") or {}).keys()) if order_payload else [],
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
