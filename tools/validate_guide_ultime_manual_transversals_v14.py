from __future__ import annotations

import argparse
import json
from typing import Any

import tools.validate_guide_ultime_manual_transversals_v13 as v13

v12 = v13.v12
v9 = v13.v9

v9.EXPECTED_CHAPTERS.update({
    "astrub": ("astrub_v4.json", 16),
    "level_100_120": ("level_100_120_v6.json", 16),
    "level_181_190": ("level_181_190_v4.json", 21),
    "level_191_200": ("level_191_200_v6.json", 36),
    "level_200_plus": ("level_200_plus_v4.json", 26),
})


def check_astrub_v4(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    _, by = v9.stage_index(payload)
    v9.need_quests(hard, by, "AST-05", {"Bûcherons en détresse"})
    v9.need_tokens(hard, by, "AST-05", ("La fin... ou le commencement", "aucun retour Astrub post-200"))


def check_level100_v6(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    _, by = v9.stage_index(payload)
    v9.need_quests(hard, by, "L100-15", {
        "À la croisée des mondes",
        "Sous le bois de sa colère",
        "Infâme pourriture",
        "Le Saule du Promeneur",
        "Dites-le avec des fleurs",
    })
    v9.need_tokens(hard, by, "L100-15", ("Damadrya", "aucun nouveau passage", "sigil de Rosal"))


def check_level181_v4(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    v12.v11.check_level181(hard, payload)
    _, by = v9.stage_index(payload)
    v9.need_tokens(hard, by, "L181-00", ("métier de récolte niveau200", "Vulbis", "Six sur six", "Alchimiste", "Paysan"))


def check_level191_v6(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    v12.check_level200(hard, payload)
    ids, by = v9.stage_index(payload)
    v9.need_quests(hard, by, "L200-VUL0", {
        "Barnabé dans l'espace", "Chaque chose en son temps", "Aux frontières du réel",
        "Ce sera mieux avant", "Amaknanomalie", "La mère des Dragoeufs",
    })
    v9.need_tokens(hard, by, "L200-VUL0", ("0,7%", "jamais en arène", "Parangon_drop_enabled=true"))
    v9.need_quests(hard, by, "L200-VUL1", {"Perdu dans le temps", "Plongée dans un bain de sang", "Le sens du sacrifice"})
    torke = v9.need_stage(hard, by, "L200-VUL1")
    if torke:
        dungeon = torke.get("dungeon") if isinstance(torke.get("dungeon"), dict) else {}
        if dungeon.get("name") != "Sanctuaire de Torkélonia" or dungeon.get("parangon_attempt") is not True:
            hard.append({"code":"vulbis_torkelonia_contract_invalid","dungeon":dungeon})
    v9.need_quests(hard, by, "L200-VUL2", {"Cauchemar infini", "La Nuit-qui-rugit", "Les raisons de la colère", "Le temps des secrets"})
    v9.need_tokens(hard, by, "L200-VUL2", ("Dofus Vulbis obtenu si et seulement si runtime confirmé", "500", "Reflet onirique"))
    v9.before(hard, ids, "L200-VUL0", "L200-DDG1")
    v9.before(hard, ids, "L200-VUL1", "L200-DDG1")
    v9.before(hard, ids, "L200-VUL2", "L200-16")


def check_post200_v4(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    ids, by = v9.stage_index(payload)
    stages = [x for x in payload.get("stages", []) or [] if isinstance(x, dict)]
    if len(stages) != 26:
        hard.append({"code":"post200_stage_count_invalid","actual":len(stages)})
    missing_pause = [str(x.get("id") or "") for x in stages if not (x.get("pause") or isinstance(x.get("pause_checkpoint"), dict))]
    if missing_pause:
        hard.append({"code":"post200_pause_missing","stages":missing_pause})

    v9.need_quests(hard, by, "P200-00", {"L'éternelle moisson", "Le tour est joué"})
    v9.need_tokens(hard, by, "P200-00", ("ocre_final_route_v1", "Kralamoure"))

    for sid, quests in {
        "P200-01": {"La dernière pierre"},
        "P200-02": {"Les coûts du sort"},
        "P200-03": {"Une ombre au tableau", "Un remède draconien"},
        "P200-05": {"Mississitudes", "Le destin de Kalisthe"},
        "P200-06": {"Dans la gueule du dragon", "Le silence est d'Aure"},
        "P200-07": {"S'armer contre le destin"},
        "P200-08": {"La fin... ou le commencement"},
    }.items():
        v9.need_quests(hard, by, sid, quests)
    v9.need_tokens(hard, by, "P200-07", ("RERUN CAUSAL Six sur six", "Œil de Vortex", "Comte Harebourg"))
    v9.need_tokens(hard, by, "P200-08", ("choisir explicitement", "Aucune voie auto-sélectionnée"))

    v9.need_quests(hard, by, "P200-09", {"Rêves translucides", "La source de tous les maux"})
    v9.need_quests(hard, by, "P200-10", {"Les quatre volontés", "Mort et renouveau", "Prise de conscience"})
    v9.need_quests(hard, by, "P200-11", {"Main dans la main", "Deux souffles, une inspiration", "En ce jardin qui nous unit"})
    v9.need_quests(hard, by, "P200-12", {"Quand l'éveil n'est qu'un songe", "Par ce serment s'écrit le monde", "Une bien étrange prophétie"})
    v9.need_quests(hard, by, "P200-13", {"Au détour d'un rêve perdu", "Le chant du Pandamonium", "Le début de la fin"})
    v9.need_quests(hard, by, "P200-14", {"La danse de la dissonance", "Descendre aux cendres"})
    v9.need_quests(hard, by, "P200-15", {"Un héritage tourmenté", "Les totems de Maïmane"})
    v9.need_quests(hard, by, "P200-16", {"Entretemps, une renaissance", "La bête au bois dormant"})
    v9.need_tokens(hard, by, "P200-15", ("éviter Roi Nidas", "éviter Ilyzaelle", "éviter Solar"))

    for sid, quests in {
        "P200-17": {"Dis, scierie ?", "Association de fureteurs", "La complote des P.O.M.S."},
        "P200-18": {"Un événement inattendu", "L'île maudite", "La fin des maningances"},
        "P200-19": {"La graine de la révolte", "Par l'héritage qui vous lie", "Une dernière volonté"},
        "P200-20": {"Les risques du métier", "La sorcière exilée", "Pour que la flamme vacille", "L'heure des adieux"},
    }.items():
        v9.need_quests(hard, by, sid, quests)
    v9.need_tokens(hard, by, "P200-20", ("16/16", "L'héritage de l'île brisée"))
    v9.need_tokens(hard, by, "P200-21", ("Grunob", "Gobalden", "Dom de Pin réellement obtenu"))

    v9.need_quests(hard, by, "P200-22", {"Cultures et turpitudes"})
    v9.need_tokens(hard, by, "P200-22", ("Gobstination d'un Grobelin", "Par ce serment s'écrit le monde"))
    v9.need_quests(hard, by, "P200-23", {"Qui nous protège du Protecteur ?"})
    v9.need_tokens(hard, by, "P200-23", (
        "12 sigils", "Palais du Roi Nidas", "Bataille de l'Aurore Pourpre", "Tour de Solar",
        "100 Âmes de Possédé", "La Griffe des Démons", "Ménologium béni", "Elya Wood",
    ))
    v9.need_quests(hard, by, "P200-24", {"Flovoraison", "Qui nous protège du Protecteur ?"})
    flovo = v9.need_stage(hard, by, "P200-24")
    if flovo:
        dungeon = flovo.get("dungeon") if isinstance(flovo.get("dungeon"), dict) else {}
        if dungeon.get("boss") != "Belladone" or dungeon.get("pass") != "flovoraison_causal":
            hard.append({"code":"flovoraison_belladone_contract_invalid","dungeon":dungeon})
        value = v9.text(flovo)
        for token in ("final_dofus_sylvestre=false", "quest_receptacle_sylvestre=true", "PAS comme récompense finale"):
            if v9.norm(token) not in value:
                hard.append({"code":"sylvestre_receptacle_guard_missing","token":token})

    v9.need_quests(hard, by, "P200-25", {"Qui nous protège du Protecteur ?", "Flovoraison"})
    v9.need_tokens(hard, by, "P200-25", ("200000", "SOIGNER Silvosse", "Vrai Dofus Sylvestre reçu", "final_dofus_sylvestre=true only_if_runtime_confirmed"))

    for left, right in zip([f"P200-{i:02d}" for i in range(0, 25)], [f"P200-{i:02d}" for i in range(1, 26)]):
        v9.before(hard, ids, left, right)
    v9.scan_destinations(hard, "level_200_plus_v4", payload)


def check_ocre_final_manifest(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> None:
    if canonical.get("ocre_final_route") != "ocre_final_route_v1.json":
        hard.append({"code":"ocre_final_manifest_missing","actual":canonical.get("ocre_final_route")})
        return
    payload = v9.load(v9.BASE / "ocre_final_route_v1.json")
    value = v9.text(payload)
    for token in ("19", "boss", "archimonstres", "Kralamoure", "Le tour est joué"):
        if v9.norm(token) not in value:
            hard.append({"code":"ocre_final_contract_missing","token":token})


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit transversal V14 du Guide Ultime manuel jusqu'au post-200 Sylvestre.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    manifest = v9.load(v9.MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    resolved = v9.resolve_canonical(hard, canonical)

    checks = {
        "astrub": check_astrub_v4,
        "level_70_100": v12.v11.check_level70,
        "level_100_120": check_level100_v6,
        "level_120_150": v12.check_level120_v7,
        "level_150_170": v12.v11.check_level150,
        "level_171_180": v12.v11.check_level171,
        "level_181_190": check_level181_v4,
        "level_191_200": check_level191_v6,
        "level_200_plus": check_post200_v4,
    }
    for chapter_id, check in checks.items():
        if chapter_id in resolved:
            check(hard, resolved[chapter_id])

    v12.check_bonta100(hard, canonical)
    v9.validate_orders(hard, canonical)
    v12.check_order100(hard, canonical)
    v12.v11.check_temporal11(hard, canonical)
    v9.validate_ocre(hard, canonical)
    check_ocre_final_manifest(hard, canonical)

    if not args.skip_catalog:
        try:
            catalog = v9.catalog_names()
        except Exception as exc:
            hard.append({"code":"quest_catalog_load_failed","error":repr(exc)})
        else:
            for chapter_id, payload in resolved.items():
                v9.validate_catalog(hard, catalog, chapter_id, payload)

    result = {
        "schema_version":14,
        "status":"STRICT_PASS" if not hard else "STRICT_FAIL",
        "hard_error_count":len(hard),
        "hard_errors":hard,
        "canonical_chapters_checked":sorted(resolved),
        "catalog_skipped":bool(args.skip_catalog),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and hard:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
