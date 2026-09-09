from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.validate_guide_ultime_manual_transversals_v9 as v9

v9.EXPECTED_CHAPTERS["level_171_180"] = ("level_171_180_v2.json", 27)


def validate_level171_v2(hard: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    ids, by_id = v9.stage_index(payload)
    v9.need_quests(hard, by_id, "L171-00", {"Trou de mémoire"})
    v9.before(hard, ids, "L171-00", "L180-09")

    for sid, wanted in {
        "L171-01": ("BNT-30", "BNT-31"),
        "L171-05": ("BNT-32", "BNT-33"),
        "L171-06": ("BNT-34", "BNT-35"),
        "L180-00": ("BNT-36", "bonta_order_rank80_v1"),
    }.items():
        v9.need_tokens(hard, by_id, sid, wanted)

    v9.need_quests(hard, by_id, "L171-02", {
        "Le disparu de Sufokia",
        "Rendez-vous avec la mort",
        "Secret de fabrication",
        "S'emparer des commandes",
        "C'est dans la boîte",
        "Crise d'identité",
    })
    v9.need_tokens(hard, by_id, "L171-02", ("Par-delà les apparences", "Veilleurs"))
    v9.need_quests(hard, by_id, "L171-03", {
        "Elle va finir par se faire coffrer",
        "Pompe à fric",
        "Koffrologie",
        "Trésorphelinat",
        "Malladie",
    })
    v9.need_quests(hard, by_id, "L171-04", {"La pelle de la phorrée"})
    v9.before(hard, ids, "L171-04", "L180-02")

    v9.need_quests(hard, by_id, "L180-01", {"Il était une foi dans l'Ouest", "La bénédiction de Foluk"})
    v9.need_tokens(hard, by_id, "L180-01", ("Idole de Foluk Dorée", "Idole de Foluk Griffée", "Idole de Foluk Féérique"))

    phossile = v9.need_stage(hard, by_id, "L180-02")
    if phossile:
        dungeon = phossile.get("dungeon") if isinstance(phossile.get("dungeon"), dict) else {}
        if dungeon.get("name") != "Galerie du Phossile" or dungeon.get("capture_allowed") is not False:
            hard.append({"code": "phossile_capture_contract_invalid"})
    v9.need_quests(hard, by_id, "L180-02", {"La pelle de la phorrée", "La bénédiction de Foluk"})
    v9.need_tokens(hard, by_id, "L180-04", ("rerun causal", "Idole de Foluk Griffée"))

    korriandre: list[str] = []
    ougah: list[str] = []
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

    v9.need_quests(hard, by_id, "L180-05", {"Sans ma barbe, quelle barbe", "Les derniers d'entre nous", "La bénédiction de Foluk"})
    v9.need_tokens(hard, by_id, "L180-05", ("Kroa", "Idole de Foluk Féérique", "190"))
    v9.need_quests(hard, by_id, "L180-07", {"Porte, Korriandre, trésor", "Donjon sans dragon", "Une âme en colère"})
    v9.need_tokens(hard, by_id, "L180-07", ("deux passages", "aucun troisième"))
    v9.before(hard, ids, "L180-05", "L180-07")

    v9.need_quests(hard, by_id, "L180-08", {"Une âme en colère"})
    v9.need_tokens(hard, by_id, "L180-08", ("Dofus Turquoise", "Bleu turquoise"))
    v9.need_quests(hard, by_id, "L180-09", {"Champallucination", "Le baptême du feu", "Passe le fungus autour de toi", "Appui sur le champignon"})
    v9.need_tokens(hard, by_id, "L180-09", ("Trou de mémoire", "Ougah pas encore", "La prolifération a crû"))
    v9.need_quests(hard, by_id, "L180-12", {"La prolifération a crû"})
    if v9.norm("La prolifération à crû") in v9.text(by_id.get("L180-12", {})):
        hard.append({"code": "obsolete_fungus_quest_spelling"})

    v9.need_tokens(hard, by_id, "L180-10", ("Tour de force", "Appui sur le champignon", "exactly_one:persisted_bonta_order_rank80", "Ougah"))
    v9.need_tokens(hard, by_id, "L180-11", ("Tour de force", "Appui", "Ordre80", "Ocre", "190"))
    v9.need_quests(hard, by_id, "L180-13", {"Le serment de l'ambre"})
    v9.need_tokens(hard, by_id, "L180-13", ("Anneau Ocre", "Au-delà des apparences", "aucun rerun Demeure"))

    tox = v9.need_stage(hard, by_id, "L180-15")
    if tox:
        dungeon = tox.get("dungeon") if isinstance(tox.get("dungeon"), dict) else {}
        if dungeon.get("name") != "Cave du Toxoliath" or dungeon.get("capture_allowed") is not False:
            hard.append({"code": "toxoliath_capture_contract_invalid"})

    v9.need_tokens(hard, by_id, "L180-16", ("Frappez, ami, et entrez", "startCriterion", "aucun gate200 forcé"))
    v9.need_tokens(hard, by_id, "L180-17", ("osavora_gargandyas_weekend", "capture_allowed=false", "pas de faux Dofoozbz"))

    ebony = v9.need_stage(hard, by_id, "L180-18")
    if ebony:
        value = v9.text(ebony)
        if v9.norm("Dofus Ébène obtenu") in value or v9.norm("Dofus Ébène terminé") in value:
            hard.append({"code": "false_ebony_completion_claim"})
        for token in ("Jusqu'au bout du rêve", "compteur", "aucune rencontre inventée"):
            if v9.norm(token) not in value:
                hard.append({"code": "ebony_async_contract_missing", "token": token})


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit transversal V10 du Guide Ultime manuel jusqu'au niveau180.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    manifest = v9.load(v9.MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    resolved = v9.resolve_canonical(hard, canonical)
    if "level_150_170" in resolved:
        v9.validate_level150(hard, resolved["level_150_170"])
    if "level_171_180" in resolved:
        validate_level171_v2(hard, resolved["level_171_180"])
    v9.validate_bonta(hard, canonical)
    v9.validate_orders(hard, canonical)
    v9.validate_temporal(hard, canonical)
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
        "schema_version": 10,
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
