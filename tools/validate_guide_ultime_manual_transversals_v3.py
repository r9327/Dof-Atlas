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


def quest_names(stage: dict[str, Any]) -> set[str]:
    return {normalize_text(str(raw)) for raw in stage.get("quests", []) or [] if str(raw).strip()}


def explicit_quest_names(payload: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for row in payload.get("rank_contract", []) or []:
        if isinstance(row, dict):
            value = str(row.get("quest") or "").strip()
            if value:
                names.add(value)
    for stage in payload.get("stages", []) or []:
        if isinstance(stage, dict):
            for raw in stage.get("quests", []) or []:
                value = str(raw or "").strip()
                if value and not value.startswith("conditional:"):
                    names.add(value)
    return names


def require_quests(hard: list[dict[str, Any]], stage: dict[str, Any] | None, stage_id: str, required: set[str]) -> None:
    if not stage:
        hard.append({"code": "required_stage_missing", "stage": stage_id})
        return
    actual = quest_names(stage)
    for name in sorted(required, key=normalize_text):
        if normalize_text(name) not in actual:
            hard.append({"code": "required_quest_missing_from_stage", "stage": stage_id, "quest": name})


def route_text(stage: dict[str, Any] | None) -> str:
    if not stage:
        return ""
    chunks: list[str] = []
    for key in ("route", "hard_exit", "pause", "preparation", "hard_gates"):
        chunks.append(json.dumps(stage.get(key, []), ensure_ascii=False))
    return normalize_text(" ".join(chunks))


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


def chapter_payload(hard: list[dict[str, Any]], rows: list[dict[str, Any]], chapter_id: str) -> dict[str, Any]:
    row = next((item for item in rows if item.get("id") == chapter_id), None)
    if row is None:
        hard.append({"code": "chapter_missing_from_manifest", "chapter": chapter_id})
        return {}
    path = BASE / str(row.get("file") or "")
    if not path.is_file():
        hard.append({"code": "chapter_file_missing", "chapter": chapter_id, "file": path.name})
        return {}
    try:
        payload = load_manual_chapter(path)
    except Exception as exc:
        hard.append({"code": "chapter_composition_failed", "chapter": chapter_id, "error": repr(exc)})
        return {}
    declared = row.get("stage_count")
    actual = len(payload.get("stages", []) or [])
    if isinstance(declared, int) and declared != actual:
        hard.append({"code": "chapter_stage_count_mismatch", "chapter": chapter_id, "manifest": declared, "actual": actual})
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Valide Bonta/Ordres/Ocre/Émeraude et les gros hooks 70-120.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    warn: list[dict[str, Any]] = []
    manifest = load(MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}

    transversal_rows = [row for row in canonical.get("transversal_routes", []) or [] if isinstance(row, dict)]
    bonta_row = next((row for row in transversal_rows if row.get("id") == "bonta_1_50"), None)
    bonta: dict[str, Any] = {}
    if bonta_row is None:
        hard.append({"code": "bonta_1_50_missing_from_manifest"})
    else:
        path = BASE / str(bonta_row.get("file") or "")
        if not path.is_file():
            hard.append({"code": "bonta_file_missing", "file": path.name})
        else:
            bonta = load_manual_chapter(path)

    if bonta:
        if bonta.get("quest_range") != [1, 50]:
            hard.append({"code": "bonta_range_invalid", "expected": [1, 50], "actual": bonta.get("quest_range")})
        stages = [row for row in bonta.get("stages", []) or [] if isinstance(row, dict)]
        expected = list(range(1, 51))
        actual = first_rank_order(stages)
        if actual != expected:
            hard.append({"code": "bonta_rank_first_appearance_invalid", "expected": expected, "actual": actual})
        covered = {rank for stage in stages for rank in (stage.get("ranks", []) or []) if isinstance(rank, int)}
        if covered != set(expected):
            hard.append({"code": "bonta_rank_coverage_invalid", "missing": sorted(set(expected)-covered), "extra": sorted(covered-set(expected))})
        ids = [str(stage.get("id") or "").strip() for stage in stages]
        if len(ids) != len(set(ids)) or any(not value for value in ids):
            hard.append({"code": "bonta_stage_ids_invalid"})
        for required in ("BNT-07", "BNT-15", "BNT-19", "BNT-21"):
            if required not in ids:
                hard.append({"code": "bonta_required_stage_missing", "stage": required})

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
        normalized = [normalize_text(name) for name in flattened]
        if len(normalized) != len(set(normalized)):
            hard.append({"code": "ocre_boss_duplicate"})
        missing = sorted(EXPECTED_EARLY_OCRE - set(flattened))
        if missing:
            hard.append({"code": "ocre_early_boss_missing", "bosses": missing})

    chapter_rows = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    l70 = chapter_payload(hard, chapter_rows, "level_70_100")
    l100 = chapter_payload(hard, chapter_rows, "level_100_120")

    if l70:
        stages = [row for row in l70.get("stages", []) or [] if isinstance(row, dict)]
        if len(stages) != 17:
            hard.append({"code": "level_70_100_stage_count_invalid", "expected": 17, "actual": len(stages)})
        ids = [str(row.get("id") or "") for row in stages]
        by_id = {str(row.get("id") or ""): row for row in stages}
        if "L70-00E" not in by_id:
            hard.append({"code": "emerald_prerequisite_stage_missing"})
        elif ids.index("L70-00E") > ids.index("L70-01"):
            hard.append({"code": "emerald_prerequisite_stage_too_late"})
        require_quests(hard, by_id.get("L70-00E"), "L70-00E", {"Un sage parmi les sages", "La magicienne des marécages", "Le voleur d'âmes"})
        for stage_id in ("L70-01", "L70-05", "L70-06", "L70-09"):
            require_quests(hard, by_id.get(stage_id), stage_id, {"Le voleur d'âmes"})
        require_quests(hard, by_id.get("L70-11"), "L70-11", {"Le spectacle vivant", "La lettre anonyme", "La grande parade"})
        if "l amour perdu de nabur" not in route_text(by_id.get("L70-09")):
            hard.append({"code": "emerald_next_quest_not_started_after_soul_thief"})

    if l100:
        stages = [row for row in l100.get("stages", []) or [] if isinstance(row, dict)]
        if len(stages) != 16:
            hard.append({"code": "level_100_120_stage_count_invalid", "expected": 16, "actual": len(stages)})
        by_id = {str(row.get("id") or ""): row for row in stages}
        require_quests(hard, by_id.get("L100-00"), "L100-00", {"À la croisée des mondes", "Les voies du Pandawushu", "Rokwa : Voie du poing"})
        require_quests(hard, by_id.get("L100-01"), "L100-01", {"L'amour perdu de Nabur", "Naissance d'une vocation", "Les bandits de Cania", "Draconanthropie"})
        require_quests(hard, by_id.get("L100-03"), "L100-03", {"Allumer le feu", "Un juge hystérique", "Draconanthropie"})
        meulou_text = route_text(by_id.get("L100-03"))
        if "meulou" not in meulou_text or "ocre" not in meulou_text:
            hard.append({"code": "meulou_shared_contract_incomplete"})
        require_quests(hard, by_id.get("L100-09"), "L100-09", {"Vin diou", "Un juge hystérique", "La Geste de Ratagnan"})
        require_quests(hard, by_id.get("L100-12"), "L100-12", {"Un juge hystérique", "Fait comme un rat"})
        require_quests(hard, by_id.get("L100-14"), "L100-14", {"Le livre des Taures", "Des donjons, encore des donjons"})
        if "maitre corbac" not in route_text(by_id.get("L100-14")) and "maître corbac" not in route_text(by_id.get("L100-14")):
            hard.append({"code": "master_corbac_shared_contract_missing"})
        temporal_hooks = [row for row in l100.get("temporal_hooks", []) or [] if isinstance(row, dict)]
        gokuwa = next((row for row in temporal_hooks if row.get("id") == "gokwa_after_rokwa"), None)
        if not gokuwa or "24" not in str(gokuwa.get("condition") or ""):
            hard.append({"code": "gokwa_24h_hook_missing"})
        birth = by_id.get("L100-01") or {}
        gate_text = route_text(birth)
        for token in ("eleveur", "niveau 20", "dragodinde rousse", "dragodinde amande", "dragodinde doree"):
            if token not in gate_text:
                hard.append({"code": "emerald_breeding_gate_missing", "token": token})

    if not args.skip_catalog:
        try:
            index = catalog_index()
        except Exception as exc:
            hard.append({"code": "local_catalog_unavailable", "error": repr(exc)})
            index = {}
        if index:
            names = explicit_quest_names(bonta) | names20 | names40 | explicit_quest_names(l70) | explicit_quest_names(l100)
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
        "level_100_120_stage_count": len(l100.get("stages", []) or []) if l100 else 0,
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
