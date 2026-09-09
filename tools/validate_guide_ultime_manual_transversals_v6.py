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


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def qnames(stage: dict[str, Any] | None) -> set[str]:
    if not stage:
        return set()
    return {
        normalize_text(str(value))
        for value in stage.get("quests", []) or []
        if str(value).strip() and not str(value).startswith("conditional:")
    }


def stage_text(stage: dict[str, Any] | None) -> str:
    return normalize_text(json.dumps(stage or {}, ensure_ascii=False))


def require_quests(hard: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], stage_id: str, names: set[str]) -> None:
    stage = by_id.get(stage_id)
    if stage is None:
        hard.append({"code": "stage_missing", "stage": stage_id})
        return
    actual = qnames(stage)
    for name in sorted(names, key=normalize_text):
        if normalize_text(name) not in actual:
            hard.append({"code": "quest_missing", "stage": stage_id, "quest": name})


def require_tokens(hard: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], stage_id: str, tokens: tuple[str, ...]) -> None:
    value = stage_text(by_id.get(stage_id))
    if not value:
        hard.append({"code": "stage_missing", "stage": stage_id})
        return
    for token in tokens:
        if normalize_text(token) not in value:
            hard.append({"code": "contract_token_missing", "stage": stage_id, "token": token})


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit transversal manuel V6: Bonta70, Turquoise et timers Frigost.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    hard: list[dict[str, Any]] = []
    manifest = load(MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    chapters = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]

    expected_files = {
        "level_70_100": ("level_70_100_v4.json", 17),
        "level_120_150": ("level_120_150_v3.json", 30),
    }
    resolved: dict[str, dict[str, Any]] = {}
    for chapter_id, (filename, count) in expected_files.items():
        row = next((item for item in chapters if item.get("id") == chapter_id), None)
        if row is None:
            hard.append({"code": "canonical_chapter_missing", "chapter": chapter_id})
            continue
        if row.get("file") != filename:
            hard.append({"code": "canonical_file_stale", "chapter": chapter_id, "expected": filename, "actual": row.get("file")})
            continue
        try:
            payload = load_manual_chapter(BASE / filename)
        except Exception as exc:
            hard.append({"code": "chapter_resolve_failed", "chapter": chapter_id, "error": repr(exc)})
            continue
        resolved[chapter_id] = payload
        actual_count = len(payload.get("stages", []) or [])
        if actual_count != count or row.get("stage_count") != count:
            hard.append({"code": "chapter_stage_count", "chapter": chapter_id, "expected": count, "manifest": row.get("stage_count"), "actual": actual_count})

    l70 = resolved.get("level_70_100", {})
    l70_stages = [row for row in l70.get("stages", []) or [] if isinstance(row, dict)]
    l70_by_id = {str(row.get("id") or ""): row for row in l70_stages}
    require_quests(hard, l70_by_id, "L70-00E", {"La magicienne des marécages", "Plongeon et dragon"})
    require_quests(hard, l70_by_id, "L70-07", {"Un juge hystérique", "Plongeon et dragon"})
    require_tokens(hard, l70_by_id, "L70-07", ("clef dentee", "dragon cochon", "ocre"))
    ids70 = [str(row.get("id") or "") for row in l70_stages]
    if "L70-00E" in ids70 and "L70-07" in ids70 and ids70.index("L70-00E") >= ids70.index("L70-07"):
        hard.append({"code": "turquoise_started_after_dragon_cochon"})

    l120 = resolved.get("level_120_150", {})
    l120_stages = [row for row in l120.get("stages", []) or [] if isinstance(row, dict)]
    l120_by_id = {str(row.get("id") or ""): row for row in l120_stages}
    ids120 = [str(row.get("id") or "") for row in l120_stages]
    required_order = ["L120-14T", "L120-21", "L120-20B", "L120-14E", "L120-14F", "L120-15", "L120-20", "L120-20M", "L120-20T", "L120-17"]
    missing_order = [stage_id for stage_id in required_order if stage_id not in ids120]
    if missing_order:
        hard.append({"code": "turquoise_stage_missing", "stages": missing_order})
    elif [ids120.index(stage_id) for stage_id in required_order] != sorted(ids120.index(stage_id) for stage_id in required_order):
        hard.append({"code": "turquoise_causal_order_invalid", "order": required_order})

    require_quests(hard, l120_by_id, "L120-14T", {"Plongeon et dragon", "Extinction des feux", "On dirait le Sud", "La méchante sorcière de l'Est"})
    require_quests(hard, l120_by_id, "L120-20B", {"Fais dodo, t'auras du gâteau", "La méchante sorcière de l'Est"})
    if normalize_text("La bénédiction de Thomahon") in qnames(l120_by_id.get("L120-20B")):
        hard.append({"code": "thomahon_illegally_active_on_ben_pass1"})
    require_quests(hard, l120_by_id, "L120-14E", {"La bénédiction de Viti"})
    require_quests(hard, l120_by_id, "L120-14F", {"La bénédiction de Viti"})
    require_tokens(hard, l120_by_id, "L120-15", ("tynril", "viti", "idole"))
    require_quests(hard, l120_by_id, "L120-20M", {"La bénédiction de Viti", "Porte, Mansot Royal, trésor", "Monarchie parlementaire"})
    require_quests(hard, l120_by_id, "L120-20T", {"La bénédiction de Viti", "Autel du Nord", "La bénédiction de Thomahon"})
    require_tokens(hard, l120_by_id, "L120-17", ("sphincter cell", "thomahon", "ocre"))

    transversals = [row for row in canonical.get("transversal_routes", []) or [] if isinstance(row, dict)]
    bonta_row = next((row for row in transversals if row.get("id") == "bonta_1_70"), None)
    if bonta_row is None or bonta_row.get("file") != "bonta_1_70_v6.json":
        hard.append({"code": "bonta70_canonical_missing"})
    else:
        bonta = load_manual_chapter(BASE / "bonta_1_70_v6.json")
        if bonta.get("quest_range") != [1, 70]:
            hard.append({"code": "bonta_range_invalid", "actual": bonta.get("quest_range")})
        ranks: list[int] = []
        seen: set[int] = set()
        for stage in bonta.get("stages", []) or []:
            if not isinstance(stage, dict):
                continue
            for rank in stage.get("ranks", []) or []:
                if isinstance(rank, int) and rank not in seen:
                    ranks.append(rank)
                    seen.add(rank)
        if ranks != list(range(1, 71)):
            hard.append({"code": "bonta_rank_order_invalid", "actual": ranks})
        if bonta_row.get("next_rank") != 71:
            hard.append({"code": "bonta_next_rank_invalid", "actual": bonta_row.get("next_rank")})

    temporal_name = str(canonical.get("temporal_registry") or "")
    if temporal_name != "temporal_registry_v6.json":
        hard.append({"code": "temporal_registry_stale", "actual": temporal_name})
    else:
        try:
            temporal = load_temporal_registry(BASE / temporal_name)
        except Exception as exc:
            hard.append({"code": "temporal_resolve_failed", "error": repr(exc)})
            temporal = {}
        entries = {str(row.get("id") or ""): row for row in temporal.get("entries", []) or [] if isinstance(row, dict)}
        expected = {
            "frigost_hunter_blessure_to_chasse",
            "frigost_hunter_chasse_to_brocouille",
            "frigost_bonmonstres_attempt_window",
            "pandala_presence_esprits_transcription_cap",
        }
        missing = sorted(expected - set(entries))
        if missing:
            hard.append({"code": "temporal_contract_missing", "ids": missing})
        if entries.get("frigost_hunter_blessure_to_chasse", {}).get("delay_hours") != 13:
            hard.append({"code": "hunter_delay_1_invalid"})
        if entries.get("frigost_hunter_chasse_to_brocouille", {}).get("delay_hours") != 13:
            hard.append({"code": "hunter_delay_2_invalid"})
        bon = entries.get("frigost_bonmonstres_attempt_window", {})
        if bon.get("attempt_window_minutes") != 5 or bon.get("failure_cooldown_hours") != 1:
            hard.append({"code": "bonmonstres_window_invalid", "value": bon})
        for timer_id in ("frigost_hunter_blessure_to_chasse", "frigost_hunter_chasse_to_brocouille"):
            row = entries.get(timer_id, {})
            positions = row.get("weekday_start_positions") if isinstance(row.get("weekday_start_positions"), dict) else {}
            if len(positions) != 7 or row.get("position_policy") != "weekday_variable":
                hard.append({"code": "hunter_weekday_positions_invalid", "id": timer_id})

    result = {"ok": not hard, "hard_error_count": len(hard), "hard_errors": hard}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and hard:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
