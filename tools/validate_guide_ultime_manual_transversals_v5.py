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
from app.modules.encyclopedia.services.guide_ultime_temporal_registry import load_temporal_registry
from app.quest_catalog import normalize_text

BASE = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = BASE / "manifest_v1.json"
EXPECTED_ORDER_KEYS = {"coeur vaillant", "oeil attentif", "esprit salvateur"}
EXPECTED_FRIGOST_TIMER_IDS = {
    "frigost_vaccine_appointment",
    "frigost_vaccine_duration",
    "frigost_vaccine_expiry_gate",
    "frigost_no_vaccine_weekly",
    "frigost_hiques_respawn",
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


def quest_names(stage: dict[str, Any] | None) -> set[str]:
    if not stage:
        return set()
    names: set[str] = set()
    for raw in stage.get("quests", []) or []:
        value = str(raw or "").strip()
        if value and not value.startswith("conditional:"):
            names.add(normalize_text(value))
    return names


def stage_text(stage: dict[str, Any] | None) -> str:
    if not stage:
        return ""
    return normalize_text(json.dumps(stage, ensure_ascii=False))


def require_quests(
    hard: list[dict[str, Any]],
    stage: dict[str, Any] | None,
    stage_id: str,
    required: set[str],
) -> None:
    if stage is None:
        hard.append({"code": "required_stage_missing", "stage": stage_id})
        return
    actual = quest_names(stage)
    for name in sorted(required, key=normalize_text):
        if normalize_text(name) not in actual:
            hard.append({"code": "required_quest_missing_from_stage", "stage": stage_id, "quest": name})


def require_text(
    hard: list[dict[str, Any]],
    stage: dict[str, Any] | None,
    stage_id: str,
    tokens: tuple[str, ...],
) -> None:
    text = stage_text(stage)
    for token in tokens:
        if normalize_text(token) not in text:
            hard.append({"code": "required_stage_contract_text_missing", "stage": stage_id, "token": token})


def chapter_payload(
    hard: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    chapter_id: str,
) -> dict[str, Any]:
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


def validate_order_route(
    hard: list[dict[str, Any]],
    conditional_rows: list[dict[str, Any]],
    route_id: str,
    expected_next_rank: int,
    *,
    keep_order: bool,
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
    if keep_order and selection.get("order_change_forbidden") is not True:
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
    parser = argparse.ArgumentParser(description="Valide Bonta1-70, Ordres20/40/60, timers et contrats partagés jusqu'au niveau150.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    warn: list[dict[str, Any]] = []
    manifest = load(MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}

    transversal_rows = [row for row in canonical.get("transversal_routes", []) or [] if isinstance(row, dict)]
    bonta_row = next((row for row in transversal_rows if row.get("id") == "bonta_1_70"), None)
    bonta: dict[str, Any] = {}
    if bonta_row is None:
        hard.append({"code": "bonta_1_70_missing_from_manifest"})
    else:
        path = BASE / str(bonta_row.get("file") or "")
        if not path.is_file():
            hard.append({"code": "bonta_file_missing", "file": path.name})
        else:
            try:
                bonta = load_manual_chapter(path)
            except Exception as exc:
                hard.append({"code": "bonta_composition_failed", "error": repr(exc)})

    bonta_names: set[str] = set()
    if bonta:
        if bonta.get("quest_range") != [1, 70]:
            hard.append({"code": "bonta_range_invalid", "expected": [1, 70], "actual": bonta.get("quest_range")})
        stages = [row for row in bonta.get("stages", []) or [] if isinstance(row, dict)]
        expected = list(range(1, 71))
        actual = first_rank_order(stages)
        if actual != expected:
            hard.append({"code": "bonta_rank_first_appearance_invalid", "expected": expected, "actual": actual})
        covered = {rank for stage in stages for rank in (stage.get("ranks", []) or []) if isinstance(rank, int)}
        if covered != set(expected):
            hard.append({"code": "bonta_rank_coverage_invalid", "missing": sorted(set(expected)-covered), "extra": sorted(covered-set(expected))})
        by_id = {str(stage.get("id") or ""): stage for stage in stages}
        ids = list(by_id)
        if len(ids) != len(stages) or any(not value for value in ids):
            hard.append({"code": "bonta_stage_ids_invalid"})
        for required in ("BNT-07", "BNT-15", "BNT-19", "BNT-21", "BNT-23", "BNT-25", "BNT-26", "BNT-27", "BNT-28", "BNT-29"):
            if required not in by_id:
                hard.append({"code": "bonta_required_stage_missing", "stage": required})
        require_quests(hard, by_id.get("BNT-23"), "BNT-23", {"La tactique des gens d'armes", "Au nom de l'Art", "La voie du guerrier"})
        require_quests(hard, by_id.get("BNT-27"), "BNT-27", {"Bandanarthrie", "Tour de rein"})
        require_quests(hard, by_id.get("BNT-29"), "BNT-29", {"Le subterfuge de la corne", "Chachyène de vie"})
        require_text(hard, by_id.get("BNT-27"), "BNT-27", ("Sphincter Cell", "Ocre", "causal"))
        require_text(hard, by_id.get("BNT-29"), "BNT-29", ("Kanigroula", "pas", "Ocre"))
        for stage in stages:
            for raw in stage.get("quests", []) or []:
                value = str(raw or "").strip()
                if value and not value.startswith("conditional:"):
                    bonta_names.add(value)

    conditional_rows = [row for row in canonical.get("conditional_routes", []) or [] if isinstance(row, dict)]
    order20, names20 = validate_order_route(hard, conditional_rows, "bonta_order_rank20", 40, keep_order=False)
    order40, names40 = validate_order_route(hard, conditional_rows, "bonta_order_rank40", 60, keep_order=True)
    order60, names60 = validate_order_route(hard, conditional_rows, "bonta_order_rank60", 80, keep_order=True)
    if order20 and order40 and order60:
        if set(order20.get("options", {})) != set(order40.get("options", {})) or set(order20.get("options", {})) != set(order60.get("options", {})):
            hard.append({"code": "order_keys_changed_across_paliers"})
        row60 = next((row for row in conditional_rows if row.get("id") == "bonta_order_rank60"), {})
        if row60.get("same_order_as_rank20") is not True or row60.get("same_order_as_rank40") is not True:
            hard.append({"code": "manifest_does_not_lock_same_order_at_60"})
        spirit = (order60.get("options") or {}).get("esprit salvateur") or {}
        if "chene mou" not in normalize_text(json.dumps(spirit, ensure_ascii=False)):
            hard.append({"code": "order60_esprit_chene_mou_contract_missing"})

    temporal_name = str(canonical.get("temporal_registry") or "").strip()
    temporal: dict[str, Any] = {}
    if not temporal_name or not (BASE / temporal_name).is_file():
        hard.append({"code": "temporal_registry_missing", "file": temporal_name})
    else:
        try:
            temporal = load_temporal_registry(BASE / temporal_name)
        except Exception as exc:
            hard.append({"code": "temporal_registry_composition_failed", "error": repr(exc)})
    if temporal:
        entries = [row for row in temporal.get("entries", []) or [] if isinstance(row, dict)]
        ids = [str(row.get("id") or "") for row in entries]
        if len(ids) != len(set(ids)) or any(not value for value in ids):
            hard.append({"code": "temporal_entry_ids_invalid"})
        missing = sorted(EXPECTED_FRIGOST_TIMER_IDS - set(ids))
        if missing:
            hard.append({"code": "frigost_temporal_entries_missing", "ids": missing})
        expiry = next((row for row in entries if row.get("id") == "frigost_vaccine_expiry_gate"), {})
        if expiry.get("delay_days") != 7:
            hard.append({"code": "frigost_vaccine_expiry_invalid", "actual": expiry.get("delay_days")})
        appointment = next((row for row in entries if row.get("id") == "frigost_vaccine_appointment"), {})
        if appointment.get("reschedule_lock_hours") != 24:
            hard.append({"code": "frigost_appointment_lock_invalid", "actual": appointment.get("reschedule_lock_hours")})

    ocre_name = str(canonical.get("ocre_capture_registry") or "").strip()
    ocre: dict[str, Any] = {}
    if not ocre_name or not (BASE / ocre_name).is_file():
        hard.append({"code": "ocre_registry_missing", "file": ocre_name})
    else:
        ocre = load(BASE / ocre_name)
    if ocre:
        rules = ocre.get("rules") if isinstance(ocre.get("rules"), dict) else {}
        if rules.get("classic_monsters_required") is not False:
            hard.append({"code": "ocre_classic_monster_policy_stale"})
        flattened = {
            str(name)
            for key in ("1", "2", "3")
            for name in ((ocre.get("boss_steps") or {}).get(key, []) or [])
        }
        for required in ("Minotoror", "Tofu Royal", "Crocabulia", "Skeunk", "Tanukouï San", "Founoroshi", "Chêne Mou", "Sphincter Cell"):
            if required not in flattened:
                hard.append({"code": "ocre_route_boss_missing", "boss": required})
        if "Kanigroula" in flattened:
            hard.append({"code": "kanigroula_should_not_be_ocre_target"})

    chapter_rows = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    l120 = chapter_payload(hard, chapter_rows, "level_120_150")
    chapter_names: set[str] = set()
    if l120:
        stages = [row for row in l120.get("stages", []) or [] if isinstance(row, dict)]
        if len(stages) != 22:
            hard.append({"code": "level_120_150_stage_count_invalid", "expected": 22, "actual": len(stages)})
        ids = [str(row.get("id") or "") for row in stages]
        by_id = {str(row.get("id") or ""): row for row in stages}
        expected_ids = [f"L120-{n:02d}" for n in range(22)]
        if ids != expected_ids:
            hard.append({"code": "level_120_150_stage_order_invalid", "expected": expected_ids, "actual": ids})

        require_quests(hard, by_id.get("L120-02"), "L120-02", {"Antiroyaliste", "Des donjons, encore des donjons"})
        require_quests(hard, by_id.get("L120-03"), "L120-03", {"Taures et détours", "Des donjons, encore des donjons"})
        require_text(hard, by_id.get("L120-03"), "L120-03", ("Minotoror", "Ocre", "trone", "Minotot"))
        require_quests(hard, by_id.get("L120-05"), "L120-05", {"L'anneau de Tot", "Un ring pour les gouverner tous"})
        require_quests(hard, by_id.get("L120-07"), "L120-07", {"Des donjons, encore des donjons", "Comment perdre ses plumes"})
        require_text(hard, by_id.get("L120-08"), "L120-08", ("Crocabulia", "Le forgeur de legende", "causal"))
        require_quests(hard, by_id.get("L120-09"), "L120-09", {"La voie du guerrier", "L'épée du rocher"})
        require_quests(hard, by_id.get("L120-11"), "L120-11", {"La tactique des gens d'armes", "Au nom de l'Art", "La voie du guerrier"})
        require_quests(hard, by_id.get("L120-13"), "L120-13", {"La voie du guerrier", "Le festival de la lanterne"})
        require_quests(hard, by_id.get("L120-14"), "L120-14", {"La voie du guerrier", "L'art de la langue de bois"})
        require_text(hard, by_id.get("L120-14"), "L120-14", ("Adepte des Ecrits", "conditionnel", "Convoi humanitaire", "pas"))
        require_quests(hard, by_id.get("L120-15"), "L120-15", {"Tour de passe-passe"})
        require_quests(hard, by_id.get("L120-17"), "L120-17", {"Bandanarthrie", "Tour de rein"})
        require_quests(hard, by_id.get("L120-19"), "L120-19", {"Chachyène de vie", "Le subterfuge de la corne"})
        require_quests(hard, by_id.get("L120-20"), "L120-20", {"Porte, Royalmouth, trésor", "Monarchie absolue", "Le pouvoir derrière le trône", "Le mal a dit"})
        require_text(hard, by_id.get("L120-20"), "L120-20", ("7 jours", "vaccin", "quatre"))
        require_quests(hard, by_id.get("L120-21"), "L120-21", {"Les joyeux de la couronne", "Les chasseurs", "Pêche en eaux gelées"})

        if ids.index("L120-15") > ids.index("L120-17"):
            hard.append({"code": "tynril_must_precede_bonta65_sphincter"})
        if ids.index("L120-18") > ids.index("L120-19"):
            hard.append({"code": "bonta66_69_must_precede_bonta70"})

        first_rm = stage_text(by_id.get("L120-02"))
        second_rm = stage_text(by_id.get("L120-20"))
        if "porte royalmouth" in first_rm or "monarchie absolue" in first_rm and "prendre" not in first_rm:
            warn.append({"code": "review_first_royalmouth_post_unlock_wording"})
        for token in ("porte royalmouth", "monarchie absolue", "pouvoir derriere le trone", "le mal a dit"):
            if token not in second_rm:
                hard.append({"code": "second_royalmouth_contract_incomplete", "token": token})

        for stage in stages:
            for raw in stage.get("quests", []) or []:
                value = str(raw or "").strip()
                if value and not value.startswith("conditional:"):
                    chapter_names.add(value)

    if not args.skip_catalog:
        try:
            index = catalog_index()
        except Exception as exc:
            hard.append({"code": "local_catalog_unavailable", "error": repr(exc)})
            index = {}
        if index:
            names = bonta_names | names20 | names40 | names60 | chapter_names
            for name in sorted(names, key=normalize_text):
                matches = index.get(normalize_text(name), [])
                if not matches:
                    hard.append({"code": "transversal_quest_not_in_local_catalog", "quest": name})
                elif len(matches) > 1:
                    warn.append({"code": "transversal_quest_name_ambiguous", "quest": name, "ids": matches})

    result = {
        "ok": not hard,
        "bonta_rank_first_appearance": first_rank_order([row for row in bonta.get("stages", []) or [] if isinstance(row, dict)]) if bonta else [],
        "temporal_registry": temporal_name,
        "level_120_150_stage_count": len(l120.get("stages", []) or []) if l120 else 0,
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
