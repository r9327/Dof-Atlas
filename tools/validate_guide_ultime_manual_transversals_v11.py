from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.validate_guide_ultime_manual_transversals_v10 as v10

v9 = v10.v9
v9.EXPECTED_CHAPTERS.update({
    "level_70_100": ("level_70_100_v6.json", 17),
    "level_120_150": ("level_120_150_v6.json", 33),
    "level_150_170": ("level_150_170_v8.json", 24),
    "level_171_180": ("level_171_180_v4.json", 30),
    "level_181_190": ("level_181_190_v3.json", 21),
})


def dungeon_ids(payload: dict[str, Any], name: str) -> list[str]:
    result: list[str] = []
    for stage in payload.get("stages", []) or []:
        if not isinstance(stage, dict):
            continue
        dungeon = stage.get("dungeon") if isinstance(stage.get("dungeon"), dict) else {}
        if dungeon.get("name") == name:
            result.append(str(stage.get("id") or ""))
    return result


def rank_order(payload: dict[str, Any]) -> list[int]:
    result: list[int] = []
    for stage in payload.get("stages", []) or []:
        if not isinstance(stage, dict):
            continue
        for rank in stage.get("ranks", []) or []:
            if isinstance(rank, int) and rank not in result:
                result.append(rank)
    return result


def check_level70(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    _, by = v9.stage_index(payload)
    v9.need_quests(hard, by, "L70-05", {
        "Le Gardien du Pont de la Mort", "La vengeance du Kito",
        "La vengeance de Peggy la Porkass", "Le Chevalier Noir et Rose",
        "C'est radical ici", "Chéri fais-moi peur",
    })
    v9.need_tokens(hard, by, "L70-05", ("Gourlo", "aucun passage Arche supplémentaire", "Tourbière nauséabonde", "Le tour est joué"))
    gourlo = [str(s.get("id") or "") for s in payload.get("stages", []) or [] if isinstance(s, dict) and v9.norm("Gourlo") in v9.text(s)]
    if gourlo != ["L70-05"]:
        hard.append({"code": "gourlo_stage_count_invalid", "actual": gourlo})


def check_level120(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    ids, by = v9.stage_index(payload)
    v9.need_quests(hard, by, "L120-00", {"La destinée"})
    v9.need_quests(hard, by, "L120-20F", {
        "Bricole Girl", "Promenons-nous dans les bois", "Pêche en eaux gelées",
        "L'essentiel est dans Lac Gelé", "Les chasseurs", "Hôtel de glace", "La fonte des glaces",
    })
    v9.need_quests(hard, by, "L120-21M", {"Malédiction !"})
    v9.need_tokens(hard, by, "L120-20F", ("HDV", "pods", "Mansot"))
    v9.before(hard, ids, "L120-20F", "L120-21")
    v9.before(hard, ids, "L120-21", "L120-21M")


def check_level150(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    v9.validate_level150(hard, payload)
    ids, by = v9.stage_index(payload)
    v9.need_quests(hard, by, "L150-01F", {"Il préfère la mort en mer", "Chauffage à moindre frais", "À la recherche de Dan Lavy", "La marche de l'impératrice"})
    v9.need_quests(hard, by, "L150-03", {"À la recherche de Dan Lavy"})
    v9.need_tokens(hard, by, "L150-03", ("salles1 à4", "sans Obsidiantre supplémentaire"))
    v9.need_quests(hard, by, "L150-02T", {"La voie du guerrier"})
    v9.need_tokens(hard, by, "L150-02T", ("Minotot", "190", "Bworker"))
    v9.need_quests(hard, by, "L150-07D", {"Convoi humanitaire", "Sang dessus-dessous", "Un remède à tous les maux"})
    v9.need_tokens(hard, by, "L150-07D", ("RERUN CAUSAL", "Chêne Mou", "Patte de Korriandre", "Aucun nouveau Korriandre"))
    v9.need_quests(hard, by, "L150-08R", {"À qui profite le boufmouth", "Les rescapés de Frigost"})
    v9.before(hard, ids, "L150-01F", "L150-03")
    v9.before(hard, ids, "L150-07", "L150-07D")
    v9.before(hard, ids, "L150-07D", "L150-08")


def check_level171(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    v10.validate_level171_v2(hard, payload)
    ids, by = v9.stage_index(payload)
    v9.need_quests(hard, by, "L180-13B", {"La voie du guerrier", "Le tracas du guerrier"})
    v9.need_tokens(hard, by, "L180-13B", ("Bworker", "190", "La dernière pierre", "Tour du Monde complet"))
    v9.need_quests(hard, by, "L180-13S", {"Tour nage", "Pollution, je dis non", "Prise de notes", "Le tour est joué"})
    merkator = v9.need_stage(hard, by, "L180-13S")
    if merkator:
        dungeon = merkator.get("dungeon") if isinstance(merkator.get("dungeon"), dict) else {}
        if dungeon.get("name") != "Aquadôme de Merkator" or dungeon.get("capture_allowed") is not False:
            hard.append({"code": "merkator_contract_invalid"})
    v9.need_tokens(hard, by, "L180-13S", ("Kralamoure", "étape19", "aucune pierre standard"))
    v9.need_quests(hard, by, "L180-13F", {"Dépôt de ravitaillement", "Chaud du S.L.I.P.", "Mission Solution"})
    v9.need_tokens(hard, by, "L180-13F", ("frigost_depot_lulu_day_window", "frigost_chaud_slip_night_window", "RERUN CAUSAL S.L.I.P.", "STOP AVANT ENTRÉE"))
    v9.before(hard, ids, "L180-13B", "L180-13S")
    v9.before(hard, ids, "L180-13S", "L180-13F")


def check_level181(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    ids, by = v9.stage_index(payload)
    for sid, tokens in {
        "L181-00": ("BNT-37",), "L183-01": ("BNT-38",),
        "L185-02": ("BNT-39", "Korriandre"), "L186-03": ("BNT-40",),
        "L187-04": ("BNT-41",), "L190-08": ("BNT-42", "Grolloum"),
    }.items():
        v9.need_tokens(hard, by, sid, tokens)

    expected_dungeons = {
        "Antre du Korriandre": ["L185-02"],
        "Cavernes du Kolosso": ["L190-02", "L190-04"],
        "Antichambre des Gloursons": ["L190-05", "L190-06"],
        "Vaisseau du Capitaine Meno": ["L190-10B"],
        "Palais de Dantinéa": ["L190-10C"],
        "Temple de Koutoulou": ["L190-10E"],
    }
    for name, expected in expected_dungeons.items():
        actual = dungeon_ids(payload, name)
        if actual != expected:
            hard.append({"code": "dungeon_pass_count_invalid", "dungeon": name, "expected": expected, "actual": actual})

    v9.need_quests(hard, by, "L190-01", {"Un remède à tous les maux", "Un ami qui ne vous veut pas que du bien", "Là-haut sur la montagne"})
    v9.need_quests(hard, by, "L190-02", {"Là-haut sur la montagne", "Un remède à tous les maux", "Un ami qui ne vous veut pas que du bien"})
    v9.need_quests(hard, by, "L190-04", {"Porte, Kolosso, trésor", "C'est Rébro"})
    v9.need_quests(hard, by, "L190-05", {"Le pic qui glace", "Mission Solution"})
    v9.need_quests(hard, by, "L190-06", {"Porte, Glourséleste, trésor", "Glourson et lumière", "L'arène et le roi"})
    v9.need_quests(hard, by, "L190-07", {"Frigost, une île pas comme les autres", "Donjons et trouffions", "Au fion du trou"})
    v9.need_tokens(hard, by, "L190-07", ("rétroactivement", "Ne refaire aucun boss"))
    v9.need_quests(hard, by, "L190-08", {"Ça fait froid dans le dos", "Au fion du trou"})
    v9.need_tokens(hard, by, "L190-08", ("La machine à démonter le temps", "futur retour Grolloum", "causal"))
    v9.need_tokens(hard, by, "L190-09", ("La maire dénie", "blocker200", "Pas de faux DDG190"))

    neb = v9.need_stage(hard, by, "L190-10")
    if neb:
        if neb.get("quests") not in ([], None):
            hard.append({"code": "synthetic_nebuleux_quest_leaked_into_catalog", "quests": neb.get("quests")})
        v9.need_tokens(hard, by, "L190-10", ("Nébuleux", "zones200", "Aucune fausse validation"))

    for sid, required in {
        "L190-10A": {"La pêche aux infos", "Il y a de l'électricité dans l'eau", "Reine de beauté", "Celle qui glougloutait dans les ténèbres"},
        "L190-10B": {"Piège de crystal", "Une porte vers le passé", "Le vieux gob et la mer", "Nos chairs voisines"},
        "L190-10C": {"Reine de beauté", "Rançon nage", "La gueule de l'enfer"},
        "L190-10D": {"Demain, j'arête", "Fhtagn !", "Les sept Mercemers", "Aux grands mots les grands remèdes"},
        "L190-10E": {"Celle qui glougloutait dans les ténèbres", "De mal en impie"},
        "L190-10F": {"Le héros de Sufokia"},
    }.items():
        v9.need_quests(hard, by, sid, required)
    v9.need_tokens(hard, by, "L190-10F", ("Si le runtime", "OU unique gate final", "Aucun faux Abyssal"))

    for left, right in (
        ("L190-01", "L190-02"), ("L190-02", "L190-04"), ("L190-04", "L190-05"),
        ("L190-05", "L190-06"), ("L190-07", "L190-08"),
        ("L190-10A", "L190-10B"), ("L190-10B", "L190-10C"),
        ("L190-10C", "L190-10D"), ("L190-10D", "L190-10E"), ("L190-10E", "L190-10F"),
    ):
        v9.before(hard, ids, left, right)


def check_bonta90(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> None:
    rows = [x for x in canonical.get("transversal_routes", []) or [] if isinstance(x, dict)]
    row = next((x for x in rows if x.get("id") == "bonta_1_90"), None)
    if row is None or row.get("file") != "bonta_1_90_v10.json" or row.get("next_rank") != 91:
        hard.append({"code": "bonta90_manifest_invalid", "row": row})
        return
    payload = v9.load_manual_chapter(v9.BASE / "bonta_1_90_v10.json")
    ranks = rank_order(payload)
    if ranks != list(range(1, 91)):
        hard.append({"code": "bonta90_rank_coverage_invalid", "actual": ranks})
    stages = [x for x in payload.get("stages", []) or [] if isinstance(x, dict)]
    if len(stages) != 43:
        hard.append({"code": "bonta90_macro_count_invalid", "actual": len(stages)})
    if 91 in ranks:
        hard.append({"code": "bonta91_injected_too_early"})
    _, by = v9.stage_index(payload)
    v9.need_quests(hard, by, "BNT-39", {"Gelé à pierre fendre"})
    v9.need_tokens(hard, by, "BNT-39", ("PASS3 GLOBAL CAUSAL", "Aucune capture Ocre"))
    v9.need_quests(hard, by, "BNT-42", {"Ça fait froid dans le dos"})
    v9.need_tokens(hard, by, "BNT-42", ("Grolloum", "Gobiling"))
    v9.scan_destinations(hard, "bonta_1_90_v10", payload)


def check_temporal11(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> None:
    if canonical.get("temporal_registry") != "temporal_registry_v11.json":
        hard.append({"code": "temporal_registry_manifest_stale", "actual": canonical.get("temporal_registry")})
        return
    payload = v9.load_temporal_registry(v9.BASE / "temporal_registry_v11.json")
    rows = [x for x in payload.get("entries", []) or [] if isinstance(x, dict)]
    entries = {str(x.get("id") or ""): x for x in rows}
    if len(entries) != len(rows):
        hard.append({"code": "temporal_duplicate_ids"})
    required = {
        "bonta73_gambling_den_access", "fungus_agrypnite_grilled_respawn", "fungus_sword_fishing_spot_respawn",
        "osavora_season_cycle", "osavora_a_la_petite_semaine", "osavora_gargandyas_weekend",
        "kralamoure_server_opening", "frigost_depot_lulu_day_window", "frigost_chaud_slip_night_window",
    }
    missing = sorted(required - set(entries))
    if missing:
        hard.append({"code": "temporal_entries_missing", "entries": missing})
    lulu = entries.get("frigost_depot_lulu_day_window", {})
    if (lulu.get("open_local_time"), lulu.get("close_local_time"), lulu.get("hard_wait_forbidden")) != ("08:00", "20:00", True):
        hard.append({"code": "depot_lulu_window_invalid"})
    slip = entries.get("frigost_chaud_slip_night_window", {})
    if (slip.get("open_local_time"), slip.get("close_local_time"), slip.get("wraps_midnight"), slip.get("hard_wait_forbidden")) != ("20:00", "08:00", True, True):
        hard.append({"code": "slip_night_window_invalid"})
    kral = entries.get("kralamoure_server_opening", {})
    if kral.get("minimum_people_to_open") != 49 or kral.get("hard_wait_forbidden") is not True or "étape19" not in str(kral.get("preferred_merge_condition") or ""):
        hard.append({"code": "kralamoure_merge_contract_invalid"})


def check_global(hard: list[dict[str, Any]], resolved: dict[str, dict[str, Any]]) -> None:
    korriandre = dungeon_ids(resolved.get("level_171_180", {}), "Antre du Korriandre") + dungeon_ids(resolved.get("level_181_190", {}), "Antre du Korriandre")
    if korriandre != ["L180-05", "L180-07", "L185-02"]:
        hard.append({"code": "global_korriandre_passes_invalid", "actual": korriandre})
    for payload in resolved.values():
        for stage in payload.get("stages", []) or []:
            if not isinstance(stage, dict):
                continue
            dungeon = stage.get("dungeon") if isinstance(stage.get("dungeon"), dict) else {}
            if "Kralamoure" in str(dungeon.get("name") or ""):
                hard.append({"code": "isolated_kralamoure_dungeon_planned", "stage": stage.get("id")})


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit transversal V11 du Guide Ultime manuel jusqu'au niveau190.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    manifest = v9.load(v9.MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    resolved = v9.resolve_canonical(hard, canonical)

    checks = {
        "level_70_100": check_level70,
        "level_120_150": check_level120,
        "level_150_170": check_level150,
        "level_171_180": check_level171,
        "level_181_190": check_level181,
    }
    for chapter_id, check in checks.items():
        if chapter_id in resolved:
            check(hard, resolved[chapter_id])

    check_bonta90(hard, canonical)
    v9.validate_orders(hard, canonical)
    check_temporal11(hard, canonical)
    v9.validate_ocre(hard, canonical)
    check_global(hard, resolved)

    if not args.skip_catalog:
        try:
            catalog = v9.catalog_names()
        except Exception as exc:
            hard.append({"code": "quest_catalog_load_failed", "error": repr(exc)})
        else:
            for chapter_id, payload in resolved.items():
                v9.validate_catalog(hard, catalog, chapter_id, payload)

    result = {
        "schema_version": 11,
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
