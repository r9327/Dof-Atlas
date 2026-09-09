from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.validate_guide_ultime_manual_transversals_v11 as v11

v9 = v11.v9

v9.EXPECTED_CHAPTERS.update({
    "level_120_150": ("level_120_150_v7.json", 34),
    "level_191_200": ("level_191_200_v4.json", 33),
})


def check_level120_v7(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    v11.check_level120(hard, payload)
    ids, by = v9.stage_index(payload)
    v9.need_quests(hard, by, "L120-20G", {"L'ombre et la glace", "Lumière sur l'ombre"})
    v9.need_tokens(hard, by, "L120-20G", ("Le givre des révélations", "Aucun donjon supplémentaire"))
    v9.before(hard, ids, "L120-20F", "L120-20G")
    v9.before(hard, ids, "L120-20G", "L120-21")


def check_bonta100(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> None:
    rows = [x for x in canonical.get("transversal_routes", []) or [] if isinstance(x, dict)]
    row = next((x for x in rows if x.get("id") == "bonta_1_100"), None)
    if row is None or row.get("file") != "bonta_1_100_v11.json":
        hard.append({"code": "bonta100_manifest_invalid", "row": row})
        return
    payload = v9.load_manual_chapter(v9.BASE / "bonta_1_100_v11.json")
    ranks = v11.rank_order(payload)
    if ranks != list(range(1, 101)):
        hard.append({"code": "bonta100_rank_coverage_invalid", "actual": ranks})
    stages = [x for x in payload.get("stages", []) or [] if isinstance(x, dict)]
    if len(stages) != 49:
        hard.append({"code": "bonta100_macro_count_invalid", "actual": len(stages)})
    _, by = v9.stage_index(payload)
    v9.need_quests(hard, by, "BNT-46", {"À glacer le sang"})
    v9.need_tokens(hard, by, "BNT-46", ("Missiz Frizz", "merge_hook_main_route"))
    v9.need_quests(hard, by, "BNT-48", {"Fée d'hiver", "L'exorciste"})
    v9.need_tokens(hard, by, "BNT-48", ("bonta_order_rank100_v1.json", "persisted_bonta_order"))
    v9.scan_destinations(hard, "bonta_1_100_v11", payload)


def check_order100(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> None:
    rows = [x for x in canonical.get("conditional_routes", []) or [] if isinstance(x, dict)]
    row = next((x for x in rows if x.get("id") == "bonta_order_rank100"), None)
    if row is None or row.get("file") != "bonta_order_rank100_v1.json":
        hard.append({"code": "order100_manifest_invalid", "row": row})
        return
    if row.get("selector") != "persisted_bonta_order" or row.get("exactly_one") is not True or row.get("unselected_hidden") is not True:
        hard.append({"code": "order100_selector_contract_invalid", "row": row})
    for key in ("same_order_as_rank20", "same_order_as_rank40", "same_order_as_rank60", "same_order_as_rank80"):
        if row.get(key) is not True:
            hard.append({"code": "order100_same_order_not_locked", "field": key})
    payload = v9.load(v9.BASE / "bonta_order_rank100_v1.json")
    policy = payload.get("selection_policy") if isinstance(payload.get("selection_policy"), dict) else {}
    if policy.get("exactly_one") is not True or policy.get("order_change_forbidden") is not True or policy.get("unselected_hidden") is not True:
        hard.append({"code": "order100_payload_policy_invalid"})
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    if set(options) != {"coeur vaillant", "oeil attentif", "esprit salvateur"}:
        hard.append({"code": "order100_options_invalid", "actual": sorted(options)})
    value = v9.text(payload)
    for token in ("Aquadôme de Merkator", "rerun", "Examen de passage"):
        if v9.norm(token) not in value:
            hard.append({"code": "order100_contract_missing", "token": token})


def check_level200(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    ids, by = v9.stage_index(payload)

    # Bonta100 / Order100.
    v9.need_tokens(hard, by, "L200-05", ("bonta_order_rank100_v1.json", "persisted_bonta_order", "Merkator"))
    v9.before(hard, ids, "L195-01", "L200-DDG1")
    v9.before(hard, ids, "L200-DDG1", "L197-02")
    v9.before(hard, ids, "L197-02", "L198-03")
    missiz = v9.need_stage(hard, by, "L197-02")
    if missiz:
        text = v9.text(missiz)
        for token in ("À glacer le sang", "La dernière carte", "Chaud et Froid", "Missiz passage unique"):
            if v9.norm(token) not in text:
                hard.append({"code": "missiz_triple_merge_missing", "token": token})

    # Ivoire.
    for sid, wanted in {
        "L200-06": {"Le dragon blanc"},
        "L200-07": {"Examen de passage"},
        "L200-08": {"Le pays gris", "Casse en Enutrosor"},
        "L200-09": {"Casse en Enutrosor", "Un morceau de roi", "Coiffeur de génie"},
        "L200-10": {"Nordalie", "Le bonheur est dans le spray", "Une voix de crystal", "Le mort dans l'âme", "Le guerrier noir"},
        "L200-12": {"Le mort dans l'âme"},
        "L200-13": {"Une voix de crystal", "Il faut mettre un terme aux maîtres"},
        "L200-15": {"Il est temps de mourir"},
    }.items():
        v9.need_quests(hard, by, sid, wanted)
    v9.need_tokens(hard, by, "L200-09", ("Un seul Nidas",))
    v9.need_tokens(hard, by, "L200-13", ("RERUN CAUSAL MENO", "Aucun troisième Meno"))
    v9.need_tokens(hard, by, "L200-15", ("Dofus Ivoire obtenu uniquement si le runtime le confirme",))

    # Dofus des Glaces.
    v9.need_quests(hard, by, "L200-DDG1", {"Les desseins de Sylargh", "Vous avez demandé la peau lisse ?", "Chaud et Froid", "Il faut mettre un terme aux maîtres"})
    v9.need_quests(hard, by, "L200-DDG2", {"Les derniers rescapés", "La machine à démonter le temps", "Le givre des révélations"})
    v9.need_quests(hard, by, "L200-DDG3", {"Le givre des révélations", "Un comte de faits divers", "Le Dofus des Glaces"})
    v9.need_tokens(hard, by, "L200-DDG2", ("RERUN CAUSAL GROLLOUM", "second passage causal"))
    v9.need_tokens(hard, by, "L200-DDG3", ("Comte Harebourg", "Dofus des Glaces obtenu uniquement si runtime confirme"))

    # Ebene: 12 Songes must remain a real gate, with causal Koutoulou.
    v9.need_quests(hard, by, "L200-15E1", {"Jusqu'au bout du rêve", "À la recherche de Crocoburio"})
    v9.need_tokens(hard, by, "L200-15E1", ("12/12", "SUSPENDRE"))
    v9.need_quests(hard, by, "L200-15E2", {"Le creuset de Mériana"})
    v9.need_tokens(hard, by, "L200-15E2", ("RERUN CAUSAL", "Koutoulou"))
    v9.need_quests(hard, by, "L200-15E6", {"Un nouvel héritier"})
    v9.need_tokens(hard, by, "L200-15E6", ("Dofus Ébène obtenu seulement si runtime confirme",))

    # Nebuleux: shared Nidas, conditional Reine, one Vortex, four-player final.
    v9.need_quests(hard, by, "L200-NEB1", {"Espionnage industriel", "Un morceau de roi", "Coiffeur de génie"})
    v9.need_tokens(hard, by, "L200-NEB1", ("Aucun Nidas isolé",))
    v9.need_quests(hard, by, "L200-NEB3", {"La cour des miracles", "La grosse commission"})
    v9.need_quests(hard, by, "L200-NEB5", {"La vérité est au fond du puits", "Les sables du temps", "Demain ne meurt jamais"})
    vortex = v9.need_stage(hard, by, "L200-NEB5")
    if vortex:
        dungeon = vortex.get("dungeon") if isinstance(vortex.get("dungeon"), dict) else {}
        if dungeon.get("name") != "Œil de Vortex" or dungeon.get("pass") != "unique_for_two_nebuleux_quests":
            hard.append({"code": "nebuleux_vortex_contract_invalid", "dungeon": dungeon})
    v9.need_quests(hard, by, "L200-NEB6", {"La quête de l'oiseau du temps"})
    v9.need_tokens(hard, by, "L200-NEB6", ("4 personnages", "Dofus Nébuleux obtenu uniquement si runtime confirme"))

    # Final synthetic-completion guard.
    audit = v9.need_stage(hard, by, "L200-16")
    if audit and v9.norm("Aucun compteur synthétique") not in v9.text(audit):
        hard.append({"code": "level200_synthetic_completion_guard_missing"})

    # Causal ordering of the main 200 blocks.
    for left, right in (
        ("L200-NEB1", "L200-09"),
        ("L200-09", "L200-NEB2"),
        ("L200-15E4", "L200-NEB3"),
        ("L200-NEB3", "L200-15E5"),
        ("L200-15E5", "L200-NEB4"),
        ("L200-NEB4", "L200-NEB5"),
        ("L200-NEB5", "L200-NEB6"),
    ):
        v9.before(hard, ids, left, right)

    v9.scan_destinations(hard, "level_191_200_v4", payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit transversal V12 du Guide Ultime manuel jusqu'au niveau200.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    manifest = v9.load(v9.MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    resolved = v9.resolve_canonical(hard, canonical)

    checks = {
        "level_70_100": v11.check_level70,
        "level_120_150": check_level120_v7,
        "level_150_170": v11.check_level150,
        "level_171_180": v11.check_level171,
        "level_181_190": v11.check_level181,
        "level_191_200": check_level200,
    }
    for chapter_id, check in checks.items():
        if chapter_id in resolved:
            check(hard, resolved[chapter_id])

    check_bonta100(hard, canonical)
    v9.validate_orders(hard, canonical)
    check_order100(hard, canonical)
    v11.check_temporal11(hard, canonical)
    v9.validate_ocre(hard, canonical)

    if not args.skip_catalog:
        try:
            catalog = v9.catalog_names()
        except Exception as exc:
            hard.append({"code": "quest_catalog_load_failed", "error": repr(exc)})
        else:
            for chapter_id, payload in resolved.items():
                v9.validate_catalog(hard, catalog, chapter_id, payload)

    result = {
        "schema_version": 12,
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
