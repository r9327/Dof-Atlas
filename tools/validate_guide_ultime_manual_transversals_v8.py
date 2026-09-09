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

EXPECTED_CHAPTERS = {
    "amakna_40_60": ("amakna_40_60_v4.json", 10),
    "level_51_70": ("level_51_70_v2.json", 7),
    "level_70_100": ("level_70_100_v5.json", 17),
    "level_100_120": ("level_100_120_v3.json", 16),
    "level_120_150": ("level_120_150_v4.json", 31),
    "level_150_170": ("level_150_170_v2.json", 18),
}

EXPECTED_ORDER_KEYS = {"coeur vaillant", "oeil attentif", "esprit salvateur"}
SENTINEL = -2147483648


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Objet JSON attendu: {path}")
    return payload


def stages_by_id(payload: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    stages = [row for row in payload.get("stages", []) or [] if isinstance(row, dict)]
    ids = [str(row.get("id") or "").strip() for row in stages]
    return ids, {str(row.get("id") or "").strip(): row for row in stages}


def quest_names(stage: dict[str, Any] | None) -> set[str]:
    if not stage:
        return set()
    return {
        normalize_text(str(raw))
        for raw in stage.get("quests", []) or []
        if str(raw).strip() and not str(raw).startswith("conditional:")
    }


def raw_quest_names(stage: dict[str, Any] | None) -> set[str]:
    if not stage:
        return set()
    return {
        str(raw).strip()
        for raw in stage.get("quests", []) or []
        if str(raw).strip() and not str(raw).startswith("conditional:")
    }


def text(stage: dict[str, Any] | None) -> str:
    return normalize_text(json.dumps(stage or {}, ensure_ascii=False))


def require_stage(
    hard: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    stage_id: str,
) -> dict[str, Any] | None:
    stage = by_id.get(stage_id)
    if stage is None:
        hard.append({"code": "required_stage_missing", "stage": stage_id})
    return stage


def require_quests(
    hard: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    stage_id: str,
    required: set[str],
) -> None:
    stage = require_stage(hard, by_id, stage_id)
    if stage is None:
        return
    actual = quest_names(stage)
    for name in sorted(required, key=normalize_text):
        if normalize_text(name) not in actual:
            hard.append({"code": "required_quest_missing", "stage": stage_id, "quest": name})


def require_tokens(
    hard: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    stage_id: str,
    required: tuple[str, ...],
) -> None:
    stage = require_stage(hard, by_id, stage_id)
    if stage is None:
        return
    value = text(stage)
    for token in required:
        if normalize_text(token) not in value:
            hard.append({"code": "required_contract_token_missing", "stage": stage_id, "token": token})


def assert_before(hard: list[dict[str, Any]], ids: list[str], left: str, right: str) -> None:
    if left not in ids or right not in ids:
        hard.append({"code": "order_stage_missing", "left": left, "right": right})
        return
    if ids.index(left) >= ids.index(right):
        hard.append({"code": "causal_order_invalid", "left": left, "right": right})


def validate_unique_stage_ids(
    hard: list[dict[str, Any]],
    chapter_id: str,
    payload: dict[str, Any],
) -> None:
    ids = [
        str(row.get("id") or "").strip()
        for row in payload.get("stages", []) or []
        if isinstance(row, dict)
    ]
    if any(not stage_id for stage_id in ids):
        hard.append({"code": "empty_stage_id", "chapter": chapter_id})
    if len(ids) != len(set(ids)):
        hard.append({"code": "duplicate_stage_id", "chapter": chapter_id})


def scan_invalid_destinations(
    hard: list[dict[str, Any]],
    label: str,
    value: Any,
    path: str = "",
) -> None:
    if value == SENTINEL or (isinstance(value, str) and str(SENTINEL) in value):
        hard.append({"code": "sentinel_coordinate_found", "source": label, "path": path})
        return
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            key_norm = str(key).strip().lower().replace("_", "")
            if key_norm == "mapid" and child == 0:
                hard.append({"code": "map_id_zero_found", "source": label, "path": child_path})
            scan_invalid_destinations(hard, label, child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_invalid_destinations(hard, label, child, f"{path}[{index}]")


def first_rank_order(payload: dict[str, Any]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for stage in payload.get("stages", []) or []:
        if not isinstance(stage, dict):
            continue
        for rank in stage.get("ranks", []) or []:
            if isinstance(rank, int) and rank not in seen:
                result.append(rank)
                seen.add(rank)
    return result


def catalog_names() -> set[str]:
    catalog = QuestProvider(data_dir=RAW_QUEST_DATA_DIR).get_catalog()
    return {normalize_text(quest.name) for quest in catalog.quests}


def validate_catalog_names(
    hard: list[dict[str, Any]],
    catalog: set[str],
    label: str,
    payload: dict[str, Any],
) -> None:
    seen: set[str] = set()
    for stage in payload.get("stages", []) or []:
        if not isinstance(stage, dict):
            continue
        for name in raw_quest_names(stage):
            if name in seen:
                continue
            seen.add(name)
            if normalize_text(name) not in catalog:
                hard.append({"code": "quest_name_absent_from_catalog", "source": label, "quest": name})


def validate_order_contracts(
    hard: list[dict[str, Any]],
    canonical: dict[str, Any],
) -> None:
    rows = [row for row in canonical.get("conditional_routes", []) or [] if isinstance(row, dict)]
    expected = {
        "bonta_order_rank20": ("bonta_order_rank20_v1.json", 40, False),
        "bonta_order_rank40": ("bonta_order_rank40_v1.json", 60, True),
        "bonta_order_rank60": ("bonta_order_rank60_v1.json", 80, True),
    }
    option_keys: dict[str, set[str]] = {}
    for route_id, (filename, next_rank, must_lock_change) in expected.items():
        row = next((item for item in rows if item.get("id") == route_id), None)
        if row is None or row.get("file") != filename:
            hard.append({"code": "order_route_manifest_invalid", "route": route_id, "row": row})
            continue
        path = BASE / filename
        if not path.is_file():
            hard.append({"code": "order_route_file_missing", "route": route_id, "file": filename})
            continue
        payload = load(path)
        options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
        keys = set(options)
        option_keys[route_id] = keys
        if keys != EXPECTED_ORDER_KEYS:
            hard.append({"code": "order_options_invalid", "route": route_id, "actual": sorted(keys)})
        selection = payload.get("selection_policy") if isinstance(payload.get("selection_policy"), dict) else {}
        if selection.get("exactly_one") is not True:
            hard.append({"code": "order_exactly_one_not_locked", "route": route_id})
        if must_lock_change and selection.get("order_change_forbidden") is not True:
            hard.append({"code": "order_change_not_forbidden", "route": route_id})
        for key, option in options.items():
            if not isinstance(option, dict):
                hard.append({"code": "order_option_invalid", "route": route_id, "order": key})
                continue
            gate = option.get("next_order_gate") if isinstance(option.get("next_order_gate"), dict) else {}
            if gate.get("alignment_rank") != next_rank:
                hard.append({
                    "code": "order_next_gate_invalid",
                    "route": route_id,
                    "order": key,
                    "expected": next_rank,
                    "actual": gate.get("alignment_rank"),
                })
    if len(option_keys) == 3 and len({frozenset(keys) for keys in option_keys.values()}) != 1:
        hard.append({"code": "order_keys_changed_across_paliers"})
    row40 = next((item for item in rows if item.get("id") == "bonta_order_rank40"), {})
    row60 = next((item for item in rows if item.get("id") == "bonta_order_rank60"), {})
    if row40.get("same_order_as_rank20") is not True:
        hard.append({"code": "manifest_same_order_rank40_not_locked"})
    if row60.get("same_order_as_rank20") is not True or row60.get("same_order_as_rank40") is not True:
        hard.append({"code": "manifest_same_order_rank60_not_locked"})


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit transversal manuel V8: contrats Turquoise complets, Bonta65 corrigé et route jusqu'au niveau170."
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    manifest = load(MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    chapter_rows = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    resolved: dict[str, dict[str, Any]] = {}

    for chapter_id, (expected_file, expected_count) in EXPECTED_CHAPTERS.items():
        row = next((item for item in chapter_rows if item.get("id") == chapter_id), None)
        if row is None:
            hard.append({"code": "canonical_chapter_missing", "chapter": chapter_id})
            continue
        if row.get("file") != expected_file:
            hard.append({
                "code": "canonical_file_stale",
                "chapter": chapter_id,
                "expected": expected_file,
                "actual": row.get("file"),
            })
            continue
        path = BASE / expected_file
        if not path.is_file():
            hard.append({"code": "canonical_file_missing", "chapter": chapter_id, "file": expected_file})
            continue
        try:
            payload = load_manual_chapter(path)
        except Exception as exc:
            hard.append({"code": "chapter_composition_failed", "chapter": chapter_id, "error": repr(exc)})
            continue
        resolved[chapter_id] = payload
        actual = len(payload.get("stages", []) or [])
        if row.get("stage_count") != expected_count or actual != expected_count:
            hard.append({
                "code": "stage_count_invalid",
                "chapter": chapter_id,
                "expected": expected_count,
                "manifest": row.get("stage_count"),
                "actual": actual,
            })
        validate_unique_stage_ids(hard, chapter_id, payload)
        scan_invalid_destinations(hard, chapter_id, payload)

    _, amk = stages_by_id(resolved.get("amakna_40_60", {}))
    require_quests(hard, amk, "AMK-02O", {"Le Dofus et l'alchimiste", "L'éternelle moisson", "La raison du plus fort"})
    require_quests(hard, amk, "AMK-03", {"La raison du plus fort", "Après lui, le déluge"})
    require_tokens(hard, amk, "AMK-03", ("Akadémie des Gobs", "une seule fois"))

    _, l51 = stages_by_id(resolved.get("level_51_70", {}))
    require_quests(hard, l51, "L51-02", {"Donjon magistral", "Après lui, le déluge", "Comme un corbac sur sa branche"})
    require_tokens(hard, l51, "L51-02", ("Grotte Hesque", "corail", "Ocre"))

    _, l100 = stages_by_id(resolved.get("level_100_120", {}))
    require_quests(hard, l100, "L100-04", {"Comme un corbac sur sa branche", "Rester planté là"})
    require_tokens(hard, l100, "L100-04", ("Reine Nyée", "Ocre"))
    require_quests(hard, l100, "L100-15", {"Rester planté là", "Pas de fumée sans feu"})
    require_tokens(hard, l100, "L100-15", ("Damadrya", "aucun futur rerun"))

    ids70, l70 = stages_by_id(resolved.get("level_70_100", {}))
    require_quests(hard, l70, "L70-00E", {"La magicienne des marécages", "Plongeon et dragon"})
    require_quests(hard, l70, "L70-07", {"Un juge hystérique", "Plongeon et dragon"})
    require_tokens(hard, l70, "L70-07", ("Clef Dentée", "Dragon Cochon", "Ocre", "Aucun futur Dragon Cochon"))
    assert_before(hard, ids70, "L70-00E", "L70-07")

    require_quests(hard, l70, "L70-08", {"L'Épice rit", "Le roi scorpion", "Le fossile et le marteau"})
    require_tokens(hard, l70, "L70-08", ("Mantiscore", "gants", "même"))

    ids120, l120 = stages_by_id(resolved.get("level_120_150", {}))
    require_quests(hard, l120, "L120-14", {"Plongeon et dragon"})
    require_tokens(hard, l120, "L120-14", ("Clef Griffue", "Chêne Mou", "Clef Dentée"))
    require_quests(hard, l120, "L120-14T", {
        "Plongeon et dragon",
        "Extinction des feux",
        "On dirait le Sud",
        "La méchante sorcière de l'Est",
    })
    require_quests(hard, l120, "L120-14E", {"La bénédiction de Viti"})
    require_tokens(hard, l120, "L120-14E", ("Trois idoles Viti", "Founoroshi", "Tynril", "Mansot"))
    require_quests(hard, l120, "L120-14F", {"La bénédiction de Viti"})
    require_tokens(hard, l120, "L120-15", ("Tynril", "Viti", "Idole"))
    require_quests(hard, l120, "L120-20M", {
        "La bénédiction de Viti",
        "Porte, Mansot Royal, trésor",
        "Monarchie parlementaire",
    })
    require_tokens(hard, l120, "L120-20M", ("PASS 2", "Aucun troisième Mansot"))
    require_quests(hard, l120, "L120-20T", {
        "La bénédiction de Viti",
        "Autel du Nord",
        "La bénédiction de Thomahon",
    })
    require_tokens(hard, l120, "L120-20T", ("Thomahon active AVANT Sphincter", "quatre idoles Thomahon"))
    require_quests(hard, l120, "L120-17", {"La bénédiction de Thomahon"})
    require_tokens(hard, l120, "L120-17", ("Sphincter Cell", "Thomahon", "Ocre", "Nauséabonde"))
    for left, right in (
        ("L120-14E", "L120-15"),
        ("L120-15", "L120-20M"),
        ("L120-20M", "L120-20T"),
        ("L120-20T", "L120-17"),
    ):
        assert_before(hard, ids120, left, right)

    require_quests(hard, l120, "L120-08S", {
        "L'Étoile de la Mer",
        "La barrière des langues",
        "Ne pas payer de mine",
        "Le monde entier est un cactus",
    })
    require_tokens(hard, l120, "L120-08S", ("El Piko", "deux", "une seule fois"))

    ids150, l150 = stages_by_id(resolved.get("level_150_170", {}))
    require_quests(hard, l150, "L150-01", {
        "Porte, Ben le Ripate, trésor",
        "Piwates des sept mers et demies",
        "La bénédiction de Thomahon",
    })
    require_tokens(hard, l150, "L150-01", ("Marine", "PASS2", "Aucun objectif Ocre"))
    require_quests(hard, l150, "L150-02", {"Tour de main", "La bénédiction de Thomahon"})
    require_tokens(hard, l150, "L150-02", ("Kimbo", "Arboricole", "Ocre"))
    require_quests(hard, l150, "L150-03", {"Lavomatique", "La bénédiction de Thomahon"})
    require_tokens(hard, l150, "L150-03", ("Obsidiantre", "d'Obsidienne", "PASS1"))
    require_quests(hard, l150, "L150-05", {"Porte, Obsidiantre, trésor", "Pour qui sonne le glagla"})
    require_tokens(hard, l150, "L150-05", ("PASS2", "pas", "Ocre"))
    assert_before(hard, ids150, "L150-03", "L150-05")

    require_quests(hard, l150, "L150-07", {"C'est frais, mais c'est pas grave"})
    require_quests(hard, l150, "L150-08", {"Porte, Tengu Givrefoux, trésor", "Guerriers foux", "Les derniers d'entre nous"})
    require_tokens(hard, l150, "L150-08", ("PASS2", "Korriandre", "différé"))
    assert_before(hard, ids150, "L150-07", "L150-08")

    require_quests(hard, l150, "L150-14", {"Un ver, ça va, trop de vers, bonjour les dégâts", "Le mystère des vers"})
    require_tokens(hard, l150, "L150-14", ("Père Ver", "ne peut pas être capturé"))

    require_quests(hard, l150, "L150-00", {"Pas de fumée sans feu", "Arrête-la si tu peux", "Quand les esprits s'échauffent"})
    require_tokens(hard, l150, "L150-00", ("Tertre du long sommeil", "un seul"))
    require_quests(hard, l150, "L150-11", {"Requiem pour un Yokai", "Quand les esprits s'échauffent"})
    require_tokens(hard, l150, "L150-11", ("Demeure des Esprits", "UNE Demeure", "Jusqu'à leur dernier soupir"))
    require_quests(hard, l150, "L150-12", {"Jusqu'à leur dernier soupir", "Sécurité routière", "Requiem pour un Yokai"})
    require_tokens(hard, l150, "L150-12", ("UN Élixir", "44 combats", "16 Bakazako"))

    require_quests(hard, l150, "L150-15", {"Prisonniers du temps", "L'épée du rocher"})
    require_tokens(hard, l150, "L150-15", ("Skeunk", "causal", "Poudre scintillante", "Fraktale", "n'est pas capturable"))
    require_quests(hard, l150, "L150-16", {"Le forgeur de légende", "Jusqu'au bout du rêve"})
    require_tokens(hard, l150, "L150-16", ("Crocabulia", "causal", "Songes", "12"))
    require_quests(hard, l150, "L150-17", {"La Vie, l'Hormonde et le Reste"})
    require_tokens(hard, l150, "L150-17", ("XLII", "ne peut pas être capturé", "Carpe Diem"))
    assert_before(hard, ids150, "L150-15", "L150-16")

    transversals = [row for row in canonical.get("transversal_routes", []) or [] if isinstance(row, dict)]
    bonta_row = next((row for row in transversals if row.get("id") == "bonta_1_70"), None)
    bonta_payload: dict[str, Any] = {}
    if bonta_row is None or bonta_row.get("file") != "bonta_1_70_v7.json" or bonta_row.get("next_rank") != 71:
        hard.append({"code": "bonta70_contract_invalid", "row": bonta_row})
    else:
        try:
            bonta_payload = load_manual_chapter(BASE / "bonta_1_70_v7.json")
        except Exception as exc:
            hard.append({"code": "bonta_composition_failed", "error": repr(exc)})
        if bonta_payload:
            validate_unique_stage_ids(hard, "bonta_1_70", bonta_payload)
            scan_invalid_destinations(hard, "bonta_1_70", bonta_payload)
            ranks = first_rank_order(bonta_payload)
            if ranks != list(range(1, 71)):
                hard.append({"code": "bonta_rank_order_invalid", "actual": ranks})
            covered = {
                rank
                for stage in bonta_payload.get("stages", []) or []
                if isinstance(stage, dict)
                for rank in stage.get("ranks", []) or []
                if isinstance(rank, int)
            }
            if covered != set(range(1, 71)):
                hard.append({
                    "code": "bonta_rank_coverage_invalid",
                    "missing": sorted(set(range(1, 71)) - covered),
                    "extra": sorted(covered - set(range(1, 71))),
                })
            _, bonta_by_id = stages_by_id(bonta_payload)
            require_quests(hard, bonta_by_id, "BNT-27", {"Bandanarthrie", "Tour de rein", "La bénédiction de Thomahon"})
            require_tokens(
                hard,
                bonta_by_id,
                "BNT-27",
                ("Sphincter Cell", "Ocre", "Nauséabonde", "une seule fois", "Thomahon"),
            )
    if "bonta_1_80" in {str(row.get("id") or "") for row in transversals}:
        hard.append({"code": "bonta71_80_injected_too_early"})

    validate_order_contracts(hard, canonical)

    temporal_name = str(canonical.get("temporal_registry") or "")
    temporal: dict[str, Any] = {}
    if temporal_name != "temporal_registry_v7.json":
        hard.append({"code": "temporal_registry_stale", "actual": temporal_name})
    else:
        try:
            temporal = load_temporal_registry(BASE / temporal_name)
        except Exception as exc:
            hard.append({"code": "temporal_registry_composition_failed", "error": repr(exc)})
        if temporal:
            entries_list = [row for row in temporal.get("entries", []) or [] if isinstance(row, dict)]
            ids = [str(row.get("id") or "") for row in entries_list]
            if any(not entry_id for entry_id in ids) or len(ids) != len(set(ids)):
                hard.append({"code": "temporal_entry_ids_invalid"})
            entries = {str(row.get("id") or ""): row for row in entries_list}
            expected = {
                "frigost_hunter_blessure_to_chasse",
                "frigost_hunter_chasse_to_brocouille",
                "frigost_bonmonstres_attempt_window",
                "pandala_selenite_fight_respawn",
                "pandala_yokaiku_itinerant_respawn",
                "pandala_presence_esprits_transcription_cap",
            }
            missing = sorted(expected - set(entries))
            if missing:
                hard.append({"code": "temporal_entries_missing", "ids": missing})
            for timer_id in ("frigost_hunter_blessure_to_chasse", "frigost_hunter_chasse_to_brocouille"):
                row = entries.get(timer_id, {})
                if row.get("delay_hours") != 13:
                    hard.append({"code": "hunter_delay_invalid", "id": timer_id, "actual": row.get("delay_hours")})
                positions = row.get("weekday_start_positions") if isinstance(row.get("weekday_start_positions"), dict) else {}
                if row.get("position_policy") != "weekday_variable" or len(positions) != 7:
                    hard.append({"code": "hunter_weekday_positions_invalid", "id": timer_id})
            bon = entries.get("frigost_bonmonstres_attempt_window", {})
            if bon.get("attempt_window_minutes") != 5 or bon.get("failure_cooldown_hours") != 1:
                hard.append({"code": "bonmonstres_timing_invalid", "value": bon})
            if entries.get("pandala_selenite_fight_respawn", {}).get("approx_respawn_minutes") != 60:
                hard.append({"code": "selenite_respawn_invalid"})
            if entries.get("pandala_yokaiku_itinerant_respawn", {}).get("approx_respawn_minutes") != 120:
                hard.append({"code": "yokaiku_respawn_invalid"})
            scan_invalid_destinations(hard, "temporal_registry", temporal)

    ocre_name = str(canonical.get("ocre_capture_registry") or "")
    if ocre_name != "ocre_capture_registry_v1.json" or not (BASE / ocre_name).is_file():
        hard.append({"code": "ocre_registry_invalid", "file": ocre_name})
    else:
        ocre = load(BASE / ocre_name)
        rules = ocre.get("rules") if isinstance(ocre.get("rules"), dict) else {}
        if rules.get("classic_monsters_required") is not False or rules.get("bosses_required") is not True or rules.get("archimonsters_required") is not True:
            hard.append({"code": "ocre_35_policy_invalid", "rules": rules})
        flattened = {
            str(name)
            for step in ("1", "2", "3")
            for name in ((ocre.get("boss_steps") or {}).get(step, []) or [])
        }
        for required in ("Dragon Cochon", "Chêne Mou", "Sphincter Cell", "Kimbo", "Ougah"):
            if required not in flattened:
                hard.append({"code": "ocre_required_boss_missing", "boss": required})
        for forbidden in ("Kanigroula", "Fraktale", "Père Ver", "XLII"):
            if forbidden in flattened:
                hard.append({"code": "ocre_forbidden_boss_present", "boss": forbidden})
        scan_invalid_destinations(hard, "ocre_capture_registry", ocre)

    if not args.skip_catalog:
        try:
            catalog = catalog_names()
        except Exception as exc:
            hard.append({"code": "catalog_load_failed", "error": repr(exc)})
        else:
            for chapter_id, payload in resolved.items():
                validate_catalog_names(hard, catalog, chapter_id, payload)
            if bonta_payload:
                validate_catalog_names(hard, catalog, "bonta_1_70", bonta_payload)

    total_macro = sum(int(row.get("stage_count") or 0) for row in chapter_rows)
    if total_macro >= 1000:
        hard.append({"code": "macro_stage_explosion", "count": total_macro})

    result = {
        "ok": not hard,
        "canonical_chapter_count": len(chapter_rows),
        "canonical_macro_stage_count": total_macro,
        "level_150_170_stage_count": len(ids150),
        "hard_error_count": len(hard),
        "hard_errors": hard,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and hard:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
