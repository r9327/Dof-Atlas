from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def text(stage: dict[str, Any] | None) -> str:
    return normalize_text(json.dumps(stage or {}, ensure_ascii=False))


def require_stage(hard: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], stage_id: str) -> dict[str, Any] | None:
    stage = by_id.get(stage_id)
    if stage is None:
        hard.append({"code": "required_stage_missing", "stage": stage_id})
    return stage


def require_quests(hard: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], stage_id: str, required: set[str]) -> None:
    stage = require_stage(hard, by_id, stage_id)
    if stage is None:
        return
    actual = quest_names(stage)
    for name in sorted(required, key=normalize_text):
        if normalize_text(name) not in actual:
            hard.append({"code": "required_quest_missing", "stage": stage_id, "quest": name})


def require_tokens(hard: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], stage_id: str, required: tuple[str, ...]) -> None:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit transversal manuel V7 jusqu'au niveau170.")
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
            hard.append({"code": "canonical_file_stale", "chapter": chapter_id, "expected": expected_file, "actual": row.get("file")})
            continue
        path = BASE / expected_file
        try:
            payload = load_manual_chapter(path)
        except Exception as exc:
            hard.append({"code": "chapter_composition_failed", "chapter": chapter_id, "error": repr(exc)})
            continue
        resolved[chapter_id] = payload
        actual = len(payload.get("stages", []) or [])
        if row.get("stage_count") != expected_count or actual != expected_count:
            hard.append({"code": "stage_count_invalid", "chapter": chapter_id, "expected": expected_count, "manifest": row.get("stage_count"), "actual": actual})

    # Ocre d'Ambre must be opened before every historical dungeon, not repaired at 170.
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

    # Saharach: Mantiscore at 80, El Piko at 130, Père Ver at 170.
    _, l70 = stages_by_id(resolved.get("level_70_100", {}))
    require_quests(hard, l70, "L70-08", {"L'Épice rit", "Le roi scorpion", "Le fossile et le marteau"})
    require_tokens(hard, l70, "L70-08", ("Mantiscore", "gants", "même"))

    ids120, l120 = stages_by_id(resolved.get("level_120_150", {}))
    require_quests(hard, l120, "L120-08S", {
        "L'Étoile de la Mer", "La barrière des langues", "Ne pas payer de mine", "Le monde entier est un cactus"
    })
    require_tokens(hard, l120, "L120-08S", ("El Piko", "deux", "une seule fois"))
    assert_before(hard, ids120, "L120-08S", "L120-14T")

    ids150, l150 = stages_by_id(resolved.get("level_150_170", {}))
    require_quests(hard, l150, "L150-14", {"Un ver, ça va, trop de vers, bonjour les dégâts", "Le mystère des vers"})
    require_tokens(hard, l150, "L150-14", ("Père Ver", "ne peut pas être capturé"))

    # Forest/Ocre d'Ambre and Demeure shared contract.
    require_quests(hard, l150, "L150-00", {"Pas de fumée sans feu", "Arrête-la si tu peux", "Quand les esprits s'échauffent"})
    require_tokens(hard, l150, "L150-00", ("Tertre du long sommeil", "un seul"))
    require_quests(hard, l150, "L150-11", {"Requiem pour un Yokai", "Quand les esprits s'échauffent"})
    require_tokens(hard, l150, "L150-11", ("Demeure des Esprits", "UNE Demeure", "Jusqu'à leur dernier soupir"))
    require_quests(hard, l150, "L150-12", {"Jusqu'à leur dernier soupir", "Sécurité routière", "Requiem pour un Yokai"})
    require_tokens(hard, l150, "L150-12", ("UN Élixir", "44 combats", "16 Bakazako"))

    # Thomahon / Frigost causal reruns.
    require_quests(hard, l150, "L150-01", {"Porte, Ben le Ripate, trésor", "Piwates des sept mers et demies", "La bénédiction de Thomahon"})
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

    # Ebène/Xelorium must distinguish non-capturable bosses and causal returns.
    require_quests(hard, l150, "L150-15", {"Prisonniers du temps", "L'épée du rocher"})
    require_tokens(hard, l150, "L150-15", ("Skeunk", "causal", "Poudre scintillante", "Fraktale", "n'est pas capturable"))
    require_quests(hard, l150, "L150-16", {"Le forgeur de légende", "Jusqu'au bout du rêve"})
    require_tokens(hard, l150, "L150-16", ("Crocabulia", "causal", "Songes", "12"))
    require_quests(hard, l150, "L150-17", {"La Vie, l'Hormonde et le Reste"})
    require_tokens(hard, l150, "L150-17", ("XLII", "ne peut pas être capturé", "Carpe Diem"))
    assert_before(hard, ids150, "L150-15", "L150-16")

    # Alignment still intentionally stops at 70.
    transversals = [row for row in canonical.get("transversal_routes", []) or [] if isinstance(row, dict)]
    bonta = next((row for row in transversals if row.get("id") == "bonta_1_70"), None)
    if bonta is None or bonta.get("file") != "bonta_1_70_v6.json" or bonta.get("next_rank") != 71:
        hard.append({"code": "bonta70_contract_invalid", "row": bonta})
    if "bonta_1_80" in {str(row.get("id") or "") for row in transversals}:
        hard.append({"code": "bonta71_80_injected_too_early"})

    # Temporal V7 contracts.
    temporal_name = str(canonical.get("temporal_registry") or "")
    if temporal_name != "temporal_registry_v7.json":
        hard.append({"code": "temporal_registry_stale", "actual": temporal_name})
    else:
        try:
            temporal = load_temporal_registry(BASE / temporal_name)
        except Exception as exc:
            hard.append({"code": "temporal_registry_composition_failed", "error": repr(exc)})
            temporal = {}
        entries = {str(row.get("id") or ""): row for row in temporal.get("entries", []) or [] if isinstance(row, dict)}
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
        if entries.get("pandala_selenite_fight_respawn", {}).get("approx_respawn_minutes") != 60:
            hard.append({"code": "selenite_respawn_invalid"})
        if entries.get("pandala_yokaiku_itinerant_respawn", {}).get("approx_respawn_minutes") != 120:
            hard.append({"code": "yokaiku_respawn_invalid"})

    # User-facing route count remains macro, not action count.
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
