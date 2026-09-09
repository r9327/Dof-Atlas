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
SENTINEL = -2147483648
ORDER_KEYS = {"coeur vaillant", "oeil attentif", "esprit salvateur"}
EXPECTED_CHAPTERS = {
    "amakna_40_60": ("amakna_40_60_v4.json", 10),
    "level_51_70": ("level_51_70_v2.json", 7),
    "level_70_100": ("level_70_100_v5.json", 17),
    "level_100_120": ("level_100_120_v3.json", 16),
    "level_120_150": ("level_120_150_v4.json", 31),
    "level_150_170": ("level_150_170_v5.json", 20),
    "level_171_180": ("level_171_180_v1.json", 27),
}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Objet JSON attendu: {path}")
    return value


def norm(value: Any) -> str:
    return normalize_text(str(value or ""))


def text(value: Any) -> str:
    return norm(json.dumps(value, ensure_ascii=False))


def stage_index(payload: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    stages = [x for x in payload.get("stages", []) or [] if isinstance(x, dict)]
    ids = [str(x.get("id") or "").strip() for x in stages]
    return ids, {str(x.get("id") or "").strip(): x for x in stages}


def quests(stage: dict[str, Any] | None) -> set[str]:
    if not stage:
        return set()
    return {
        norm(q)
        for q in stage.get("quests", []) or []
        if str(q).strip() and not str(q).startswith("conditional:")
    }


def need_stage(hard: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], sid: str) -> dict[str, Any] | None:
    stage = by_id.get(sid)
    if stage is None:
        hard.append({"code": "required_stage_missing", "stage": sid})
    return stage


def need_quests(hard: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], sid: str, wanted: set[str]) -> None:
    stage = need_stage(hard, by_id, sid)
    if not stage:
        return
    actual = quests(stage)
    for name in wanted:
        if norm(name) not in actual:
            hard.append({"code": "required_quest_missing", "stage": sid, "quest": name})


def need_tokens(hard: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], sid: str, wanted: tuple[str, ...]) -> None:
    stage = need_stage(hard, by_id, sid)
    if not stage:
        return
    value = text(stage)
    for token in wanted:
        if norm(token) not in value:
            hard.append({"code": "required_contract_token_missing", "stage": sid, "token": token})


def before(hard: list[dict[str, Any]], ids: list[str], left: str, right: str) -> None:
    if left not in ids or right not in ids:
        hard.append({"code": "order_stage_missing", "left": left, "right": right})
    elif ids.index(left) >= ids.index(right):
        hard.append({"code": "causal_order_invalid", "left": left, "right": right})


def scan_destinations(hard: list[dict[str, Any]], source: str, value: Any, path: str = "") -> None:
    if value == SENTINEL or (isinstance(value, str) and str(SENTINEL) in value):
        hard.append({"code": "sentinel_coordinate_found", "source": source, "path": path})
        return
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if str(key).lower().replace("_", "") == "mapid" and child == 0:
                hard.append({"code": "map_id_zero_found", "source": source, "path": child_path})
            scan_destinations(hard, source, child, child_path)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            scan_destinations(hard, source, child, f"{path}[{i}]")


def resolve_canonical(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = [x for x in canonical.get("chapters", []) or [] if isinstance(x, dict)]
    result: dict[str, dict[str, Any]] = {}
    for chapter_id, (filename, expected_count) in EXPECTED_CHAPTERS.items():
        row = next((x for x in rows if x.get("id") == chapter_id), None)
        if row is None:
            hard.append({"code": "canonical_chapter_missing", "chapter": chapter_id})
            continue
        if row.get("file") != filename:
            hard.append({"code": "canonical_file_stale", "chapter": chapter_id, "expected": filename, "actual": row.get("file")})
            continue
        try:
            payload = load_manual_chapter(BASE / filename)
        except Exception as exc:
            hard.append({"code": "chapter_composition_failed", "chapter": chapter_id, "error": repr(exc)})
            continue
        result[chapter_id] = payload
        ids, _ = stage_index(payload)
        if len(ids) != expected_count or row.get("stage_count") != expected_count:
            hard.append({"code": "stage_count_invalid", "chapter": chapter_id, "expected": expected_count, "actual": len(ids), "manifest": row.get("stage_count")})
        if any(not x for x in ids) or len(ids) != len(set(ids)):
            hard.append({"code": "stage_ids_invalid", "chapter": chapter_id})
        scan_destinations(hard, chapter_id, payload)
    return result


def validate_level150(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    ids, by_id = stage_index(payload)
    need_quests(hard, by_id, "L150-16O", {"Ça barde là-haut", "Un problème de taille", "Le vol des bourdons", "Têtes de ponte", "Dérive insectaire"})
    need_tokens(hard, by_id, "L150-16O", ("On se fait la bzzzbz", "La proie des vérités", "180"))
    need_quests(hard, by_id, "L150-16V", {"Voyage, voyage", "La porte d'Enutrosor", "Orichomania", "La cité de l'indicible mal", "Le maître des zaaps"})
    need_quests(hard, by_id, "L150-17", {"Le disparu de Sufokia", "Carpe Diem"})
    need_tokens(hard, by_id, "L150-17", ("XLII", "Diamant Dimensionnel"))
    before(hard, ids, "L150-16O", "L150-16V")
    before(hard, ids, "L150-16V", "L150-17")


def validate_level171(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    ids, by_id = stage_index(payload)
    need_quests(hard, by_id, "L171-00", {"Trou de mémoire"})
    before(hard, ids, "L171-00", "L180-09")

    for sid, wanted in {
        "L171-01": ("BNT-30", "BNT-31"),
        "L171-05": ("BNT-32", "BNT-33"),
        "L171-06": ("BNT-34", "BNT-35"),
        "L180-00": ("BNT-36", "bonta_order_rank80_v1"),
    }.items():
        need_tokens(hard, by_id, sid, wanted)

    need_quests(hard, by_id, "L171-02", {"Le disparu de Sufokia", "Rendez-vous avec la mort", "Secret de fabrication", "S'emparer des commandes", "C'est dans la boîte", "Crise d'identité"})
    need_tokens(hard, by_id, "L171-02", ("Par-delà les apparences", "Veilleurs"))
    need_quests(hard, by_id, "L171-03", {"Elle va finir par se faire coffrer", "Pompe à fric", "Koffrologie", "Trésorphelinat", "Malladie"})
    need_quests(hard, by_id, "L171-04", {"La pelle de la phorrée"})
    before(hard, ids, "L171-04", "L180-02")

    need_quests(hard, by_id, "L180-01", {"Il était une foi dans l'Ouest", "La bénédiction de Foluk"})
    need_tokens(hard, by_id, "L180-01", ("Idole de Foluk Dorée", "Idole de Foluk Griffée", "Idole de Foluk Féérique"))

    phossile = need_stage(hard, by_id, "L180-02")
    if phossile:
        dungeon = phossile.get("dungeon") if isinstance(phossile.get("dungeon"), dict) else {}
        if dungeon.get("name") != "Galerie du Phossile" or dungeon.get("capture_allowed") is not False:
            hard.append({"code": "phossile_capture_contract_invalid"})
    need_quests(hard, by_id, "L180-02", {"La pelle de la phorrée", "La bénédiction de Foluk"})
    need_tokens(hard, by_id, "L180-04", ("rerun causal", "Idole de Foluk Griffée"))

    korriandre = []
    ougah = []
    for stage in payload.get("stages", []) or []:
        if not isinstance(stage, dict):
            continue
        dungeon = stage.get("dungeon") if isinstance(stage.get("dungeon"), dict) else {}
        if dungeon.get("name") == "Antre du Korriandre":
            korriandre.append(str(stage.get("id") or ""))
        if dungeon.get("name") == "Temple du Grand Ougah":
            ougah.append(str(stage.get("id") or ""))
    if korriandre != ["L180-05", "L180-07"]:
        hard.append({"code": "korriandre_pass_count_or_order_invalid", "actual": korriandre})
    if ougah != ["L180-11"]:
        hard.append({"code": "ougah_unique_pass_invalid", "actual": ougah})

    need_quests(hard, by_id, "L180-05", {"Sans ma barbe, quelle barbe", "Les derniers d'entre nous", "La bénédiction de Foluk"})
    need_tokens(hard, by_id, "L180-05", ("Kroa", "Idole de Foluk Féérique", "190"))
    need_quests(hard, by_id, "L180-07", {"Porte, Korriandre, trésor", "Donjon sans dragon", "Une âme en colère"})
    need_tokens(hard, by_id, "L180-07", ("deux passages", "aucun troisième"))
    before(hard, ids, "L180-05", "L180-07")

    need_quests(hard, by_id, "L180-08", {"Une âme en colère"})
    need_tokens(hard, by_id, "L180-08", ("Dofus Turquoise", "Bleu turquoise"))
    need_quests(hard, by_id, "L180-09", {"Champallucination", "Le baptême du feu", "Passe le fungus autour de toi", "Appui sur le champignon"})
    need_tokens(hard, by_id, "L180-09", ("Trou de mémoire", "Ougah pas encore"))
    need_tokens(hard, by_id, "L180-10", ("Tour de force", "Appui sur le champignon", "exactly_one:persisted_bonta_order_rank80", "Ougah"))
    need_tokens(hard, by_id, "L180-11", ("Tour de force", "Appui", "Ordre80", "Ocre", "190"))
    need_quests(hard, by_id, "L180-12", {"La prolifération à crû"})
    need_quests(hard, by_id, "L180-13", {"Le serment de l'ambre"})
    need_tokens(hard, by_id, "L180-13", ("Anneau Ocre", "Au-delà des apparences", "aucun rerun Demeure"))

    tox = need_stage(hard, by_id, "L180-15")
    if tox:
        dungeon = tox.get("dungeon") if isinstance(tox.get("dungeon"), dict) else {}
        if dungeon.get("name") != "Cave du Toxoliath" or dungeon.get("capture_allowed") is not False:
            hard.append({"code": "toxoliath_capture_contract_invalid"})

    need_tokens(hard, by_id, "L180-16", ("Frappez, ami, et entrez", "startCriterion", "aucun gate200 forcé"))
    need_tokens(hard, by_id, "L180-17", ("osavora_gargandyas_weekend", "capture_allowed=false", "pas de faux Dofoozbz"))

    ebony = need_stage(hard, by_id, "L180-18")
    if ebony:
        value = text(ebony)
        if norm("Dofus Ébène obtenu") in value or norm("Dofus Ébène terminé") in value:
            hard.append({"code": "false_ebony_completion_claim"})
        for token in ("Jusqu'au bout du rêve", "compteur", "aucune rencontre inventée"):
            if norm(token) not in value:
                hard.append({"code": "ebony_async_contract_missing", "token": token})


def validate_bonta(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> None:
    rows = [x for x in canonical.get("transversal_routes", []) or [] if isinstance(x, dict)]
    row = next((x for x in rows if x.get("id") == "bonta_1_80"), None)
    if row is None or row.get("file") != "bonta_1_80_v9.json" or row.get("next_rank") != 81:
        hard.append({"code": "bonta_manifest_invalid", "row": row})
        return
    payload = load_manual_chapter(BASE / "bonta_1_80_v9.json")
    seen: list[int] = []
    for stage in payload.get("stages", []) or []:
        if isinstance(stage, dict):
            for rank in stage.get("ranks", []) or []:
                if isinstance(rank, int) and rank not in seen:
                    seen.append(rank)
    if seen != list(range(1, 81)):
        hard.append({"code": "bonta_rank_coverage_invalid", "actual": seen})
    if len([x for x in payload.get("stages", []) or [] if isinstance(x, dict)]) != 37:
        hard.append({"code": "bonta_macro_count_invalid"})
    scan_destinations(hard, "bonta_1_80_v9", payload)


def validate_orders(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> None:
    rows = [x for x in canonical.get("conditional_routes", []) or [] if isinstance(x, dict)]
    specs = [
        ("bonta_order_rank20", "bonta_order_rank20_v1.json", 40),
        ("bonta_order_rank40", "bonta_order_rank40_v1.json", 60),
        ("bonta_order_rank60", "bonta_order_rank60_v1.json", 80),
        ("bonta_order_rank80", "bonta_order_rank80_v1.json", 100),
    ]
    key_sets: list[set[str]] = []
    for route_id, filename, next_rank in specs:
        row = next((x for x in rows if x.get("id") == route_id), None)
        if row is None or row.get("file") != filename or row.get("selector") != "persisted_bonta_order" or row.get("exactly_one") is not True or row.get("unselected_hidden") is not True:
            hard.append({"code": "order_manifest_invalid", "route": route_id, "row": row})
            continue
        payload = load(BASE / filename)
        options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
        keys = set(options)
        key_sets.append(keys)
        if keys != ORDER_KEYS:
            hard.append({"code": "order_options_invalid", "route": route_id, "actual": sorted(keys)})
        selection = payload.get("selection_policy") if isinstance(payload.get("selection_policy"), dict) else {}
        if selection.get("exactly_one") is not True:
            hard.append({"code": "order_exactly_one_not_locked", "route": route_id})
        if route_id != "bonta_order_rank20" and selection.get("order_change_forbidden") is not True:
            hard.append({"code": "order_change_not_forbidden", "route": route_id})
        for key, option in options.items():
            gate = option.get("next_order_gate") if isinstance(option, dict) and isinstance(option.get("next_order_gate"), dict) else {}
            if gate.get("alignment_rank") != next_rank:
                hard.append({"code": "order_next_gate_invalid", "route": route_id, "order": key, "expected": next_rank, "actual": gate.get("alignment_rank")})
    if len(key_sets) == 4 and len({frozenset(x) for x in key_sets}) != 1:
        hard.append({"code": "order_keys_changed_across_paliers"})
    rank80 = next((x for x in rows if x.get("id") == "bonta_order_rank80"), {})
    for key in ("same_order_as_rank20", "same_order_as_rank40", "same_order_as_rank60"):
        if rank80.get(key) is not True:
            hard.append({"code": "manifest_rank80_same_order_not_locked", "field": key})


def validate_temporal(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> None:
    if canonical.get("temporal_registry") != "temporal_registry_v9.json":
        hard.append({"code": "temporal_registry_manifest_stale", "actual": canonical.get("temporal_registry")})
        return
    payload = load_temporal_registry(BASE / "temporal_registry_v9.json")
    rows = [x for x in payload.get("entries", []) or [] if isinstance(x, dict)]
    entries = {str(x.get("id") or ""): x for x in rows}
    if len(entries) != len(rows):
        hard.append({"code": "temporal_duplicate_ids"})
    for entry_id in (
        "bonta73_gambling_den_access",
        "fungus_agrypnite_grilled_respawn",
        "fungus_sword_fishing_spot_respawn",
        "osavora_season_cycle",
        "osavora_a_la_petite_semaine",
        "osavora_gargandyas_weekend",
    ):
        if entry_id not in entries:
            hard.append({"code": "temporal_entry_missing", "entry": entry_id})
    season = entries.get("osavora_season_cycle", {})
    if season.get("rotation_order") != ["Naissance", "Chasse", "Repos"] or season.get("change_weekday") != "MO" or season.get("change_local_time") != "08:00":
        hard.append({"code": "osavora_season_contract_invalid"})
    titan = entries.get("osavora_gargandyas_weekend", {})
    if (titan.get("open_weekday"), titan.get("open_local_time"), titan.get("close_weekday"), titan.get("close_local_time"), titan.get("capture_allowed")) != ("FR", "19:00", "MO", "08:00", False):
        hard.append({"code": "gargandyas_window_contract_invalid"})


def validate_ocre(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> None:
    if canonical.get("ocre_capture_registry") != "ocre_capture_registry_v1.json":
        hard.append({"code": "ocre_registry_manifest_invalid", "actual": canonical.get("ocre_capture_registry")})
        return
    payload = load(BASE / "ocre_capture_registry_v1.json")
    value = text(payload)
    for token in ("classic_monsters", "boss", "archimonsters"):
        if norm(token) not in value:
            hard.append({"code": "ocre_policy_token_missing", "token": token})
    scan_destinations(hard, "ocre_capture_registry", payload)


def catalog_names() -> set[str]:
    return {norm(q.name) for q in QuestProvider(data_dir=RAW_QUEST_DATA_DIR).get_catalog().quests}


def validate_catalog(hard: list[dict[str, Any]], catalog: set[str], label: str, payload: dict[str, Any]) -> None:
    seen: set[str] = set()
    for stage in payload.get("stages", []) or []:
        if not isinstance(stage, dict):
            continue
        for raw in stage.get("quests", []) or []:
            name = str(raw).strip()
            if not name or name.startswith("conditional:") or name in seen:
                continue
            seen.add(name)
            if norm(name) not in catalog:
                hard.append({"code": "quest_name_absent_from_catalog", "source": label, "quest": name})


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit transversal V9 du Guide Ultime manuel jusqu'au niveau180.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    manifest = load(MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    resolved = resolve_canonical(hard, canonical)
    if "level_150_170" in resolved:
        validate_level150(hard, resolved["level_150_170"])
    if "level_171_180" in resolved:
        validate_level171(hard, resolved["level_171_180"])
    validate_bonta(hard, canonical)
    validate_orders(hard, canonical)
    validate_temporal(hard, canonical)
    validate_ocre(hard, canonical)

    if not args.skip_catalog:
        try:
            catalog = catalog_names()
        except Exception as exc:
            hard.append({"code": "quest_catalog_load_failed", "error": repr(exc)})
        else:
            for chapter_id, payload in resolved.items():
                validate_catalog(hard, catalog, chapter_id, payload)

    result = {
        "schema_version": 9,
        "status": "STRICT_PASS" if not hard else "STRICT_FAIL",
        "hard_error_count": len(hard),
        "hard_errors": hard,
        "canonical_chapters_checked": sorted(resolved),
        "catalog_skipped": bool(args.skip_catalog),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and hard:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
