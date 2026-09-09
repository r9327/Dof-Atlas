from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.modules.encyclopedia.providers.quest_provider import QuestProvider
from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import GuideUltimeManualRuntimeService
from app.modules.encyclopedia.services.guide_ultime_temporal_registry import load_temporal_registry
from app.quest_catalog import normalize_text


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = BASE / "manifest_v1.json"

EXPECTED_CHAPTERS: tuple[tuple[str, str, int], ...] = (
    ("incarnam", "incarnam_v2.json", 9),
    ("astrub", "astrub_v5.json", 16),
    ("pandala_access", "pandala_access_v1.json", 2),
    ("amakna_40_60", "amakna_40_60_v5.json", 10),
    ("level_51_70", "level_51_70_v4.json", 7),
    ("level_70_100", "level_70_100_v10.json", 17),
    ("level_100_120", "level_100_120_v9.json", 17),
    ("level_120_150", "level_120_150_v21.json", 37),
    ("level_150_170", "level_150_170_v21.json", 24),
    ("level_171_180", "level_171_180_v13.json", 30),
    ("level_181_190", "level_181_190_v15.json", 24),
    ("level_191_200", "level_191_200_v22.json", 62),
    ("level_200_plus", "level_200_plus_v11.json", 12),
)
EXPECTED_STAGE_COUNT = 267
EXPECTED_BONTA_FILE = "bonta_1_100_v17.json"
EXPECTED_TEMPORAL_FILE = "temporal_registry_v15.json"
EXPECTED_OCRE_CAPTURE_FILE = "ocre_capture_registry_v1.json"
EXPECTED_OCRE_FINAL_FILE = "ocre_final_route_v2.json"
EXPECTED_OCRE_COMPLETION_FILE = "ocre_completion_route_v2.json"
EXPECTED_SUCCESS_CONTRACTS_FILE = "success_contracts_v2.json"
EXPECTED_ORDER_FILES = {
    20: "bonta_order_rank20_v1.json",
    40: "bonta_order_rank40_v1.json",
    60: "bonta_order_rank60_v1.json",
    80: "bonta_order_rank80_v1.json",
    100: "bonta_order_rank100_v1.json",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _error(hard: list[dict[str, Any]], code: str, **details: Any) -> None:
    hard.append({"code": code, **details})


def _quest_values(stage: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("quests", "quest_sequence", "parallel_quests"):
        raw = stage.get(field)
        rows = raw if isinstance(raw, list) else [raw] if raw else []
        for value in rows:
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
    return values


def _stage_index(payload: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    stages = [row for row in payload.get("stages", []) or [] if isinstance(row, dict)]
    ids = [str(row.get("id") or "").strip() for row in stages]
    return ids, {stage_id: stage for stage_id, stage in zip(ids, stages) if stage_id}


def _need_stage(hard: list[dict[str, Any]], by: dict[str, dict[str, Any]], stage_id: str) -> dict[str, Any] | None:
    stage = by.get(stage_id)
    if stage is None:
        _error(hard, "required_stage_missing", stage=stage_id)
    return stage


def _need_quests(
    hard: list[dict[str, Any]],
    by: dict[str, dict[str, Any]],
    stage_id: str,
    wanted: set[str],
) -> None:
    stage = _need_stage(hard, by, stage_id)
    if stage is None:
        return
    actual = set(_quest_values(stage))
    missing = sorted(wanted - actual)
    if missing:
        _error(hard, "required_quests_missing", stage=stage_id, missing=missing)


def _before(hard: list[dict[str, Any]], ids: list[str], left: str, right: str) -> None:
    if left not in ids or right not in ids:
        _error(hard, "ordering_stage_missing", left=left, right=right)
        return
    if ids.index(left) >= ids.index(right):
        _error(hard, "causal_order_invalid", left=left, right=right)


def _forbid_unconditional(
    hard: list[dict[str, Any]],
    by: dict[str, dict[str, Any]],
    stage_id: str,
    forbidden: set[str],
) -> None:
    stage = _need_stage(hard, by, stage_id)
    if stage is None:
        return
    actual = {value for value in _quest_values(stage) if not value.startswith("conditional:")}
    leaked = sorted(forbidden & actual)
    if leaked:
        _error(hard, "conditional_quest_leaked_to_common_route", stage=stage_id, quests=leaked)


def _canonical_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    rows = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    rows.sort(key=lambda row: int(row.get("order") or 0))
    return rows


def _validate_chapters(
    hard: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    rows = _canonical_rows(manifest)
    expected_ids = [chapter_id for chapter_id, _, _ in EXPECTED_CHAPTERS]
    actual_ids = [str(row.get("id") or "").strip() for row in rows]
    if actual_ids != expected_ids:
        _error(hard, "canonical_chapter_order_invalid", expected=expected_ids, actual=actual_ids)

    resolved: dict[str, dict[str, Any]] = {}
    total = 0
    by_id = {str(row.get("id") or "").strip(): row for row in rows}
    for chapter_id, filename, stage_count in EXPECTED_CHAPTERS:
        row = by_id.get(chapter_id)
        if row is None:
            _error(hard, "canonical_chapter_missing", chapter=chapter_id)
            continue
        if row.get("file") != filename:
            _error(hard, "canonical_chapter_file_stale", chapter=chapter_id, expected=filename, actual=row.get("file"))
            continue
        if int(row.get("stage_count") or -1) != stage_count:
            _error(hard, "canonical_manifest_stage_count_invalid", chapter=chapter_id, expected=stage_count, actual=row.get("stage_count"))
        try:
            payload = load_manual_chapter(BASE / filename)
        except Exception as exc:
            _error(hard, "canonical_chapter_resolution_failed", chapter=chapter_id, file=filename, error=f"{type(exc).__name__}: {exc}")
            continue
        stages = [stage for stage in payload.get("stages", []) or [] if isinstance(stage, dict)]
        total += len(stages)
        if len(stages) != stage_count:
            _error(hard, "canonical_resolved_stage_count_invalid", chapter=chapter_id, expected=stage_count, actual=len(stages))
        ids = [str(stage.get("id") or "").strip() for stage in stages]
        missing_ids = [index for index, stage_id in enumerate(ids) if not stage_id]
        if missing_ids:
            _error(hard, "canonical_stage_id_missing", chapter=chapter_id, indexes=missing_ids)
        duplicates = sorted({stage_id for stage_id in ids if stage_id and ids.count(stage_id) > 1})
        if duplicates:
            _error(hard, "canonical_stage_id_duplicate", chapter=chapter_id, ids=duplicates)
        resolved[chapter_id] = payload

    if total != EXPECTED_STAGE_COUNT:
        _error(hard, "canonical_total_stage_count_invalid", expected=EXPECTED_STAGE_COUNT, actual=total)
    return resolved


def _validate_bonta(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> None:
    rows = [row for row in canonical.get("transversal_routes", []) or [] if isinstance(row, dict)]
    row = next((item for item in rows if item.get("id") == "bonta_1_100"), None)
    if row is None or row.get("file") != EXPECTED_BONTA_FILE:
        _error(hard, "bonta100_manifest_invalid", expected=EXPECTED_BONTA_FILE, actual=row)
        return
    if row.get("alignment") != "Bonta" or row.get("mandatory") is not True or row.get("alignment_complete") is not True:
        _error(hard, "bonta100_manifest_contract_invalid", row=row)

    payload = load_manual_chapter(BASE / EXPECTED_BONTA_FILE)
    stages = [stage for stage in payload.get("stages", []) or [] if isinstance(stage, dict)]
    if len(stages) != 49 or int(payload.get("macro_stage_count") or -1) != 49:
        _error(hard, "bonta100_macro_count_invalid", resolved=len(stages), declared=payload.get("macro_stage_count"))
    if payload.get("quest_range") != [1, 100]:
        _error(hard, "bonta100_range_invalid", actual=payload.get("quest_range"))
    _, by = _stage_index(payload)
    _need_quests(hard, by, "BNT-46", {"À glacer le sang"})
    _need_quests(hard, by, "BNT-48", {"Fée d'hiver", "L'exorciste"})


def _validate_orders(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> None:
    rows = [row for row in canonical.get("conditional_routes", []) or [] if isinstance(row, dict)]
    class_row = next((row for row in rows if row.get("id") == "astrub_class_branches"), None)
    if class_row is None or class_row.get("file") != "astrub_class_branches_v1.json":
        _error(hard, "class_branch_manifest_invalid", row=class_row)
    elif class_row.get("selector") != "actual_character_class" or class_row.get("manual_selection_forbidden") is not True or int(class_row.get("option_count") or 0) != 19:
        _error(hard, "class_branch_selector_contract_invalid", row=class_row)

    for rank, filename in EXPECTED_ORDER_FILES.items():
        route_id = f"bonta_order_rank{rank}"
        row = next((item for item in rows if item.get("id") == route_id), None)
        if row is None or row.get("file") != filename:
            _error(hard, "order_manifest_invalid", rank=rank, expected=filename, actual=row)
            continue
        if row.get("selector") != "persisted_bonta_order" or row.get("exactly_one") is not True or row.get("unselected_hidden") is not True or int(row.get("option_count") or 0) != 3:
            _error(hard, "order_selector_contract_invalid", rank=rank, row=row)
        for previous_rank in (20, 40, 60, 80):
            if previous_rank >= rank:
                break
            field = f"same_order_as_rank{previous_rank}"
            if row.get(field) is not True:
                _error(hard, "order_continuity_not_locked", rank=rank, field=field)
        payload = _load(BASE / filename)
        options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
        if set(options) != {"coeur vaillant", "oeil attentif", "esprit salvateur"}:
            _error(hard, "order_options_invalid", rank=rank, actual=sorted(options))
        policy = payload.get("selection_policy") if isinstance(payload.get("selection_policy"), dict) else {}
        if policy.get("exactly_one") is not True or policy.get("unselected_hidden") is not True:
            _error(hard, "order_payload_policy_invalid", rank=rank, policy=policy)
        if rank > 20 and policy.get("order_change_forbidden") is not True:
            _error(hard, "order_change_not_forbidden", rank=rank)


def _temporal_hooks(resolved: dict[str, dict[str, Any]]) -> set[str]:
    hooks: set[str] = set()
    for payload in resolved.values():
        for stage in payload.get("stages", []) or []:
            if not isinstance(stage, dict):
                continue
            raw_values: list[Any] = []
            if stage.get("temporal_hook") not in (None, "", []):
                raw_values.append(stage.get("temporal_hook"))
            raw = stage.get("temporal_hooks")
            if isinstance(raw, list):
                raw_values.extend(raw)
            elif raw not in (None, ""):
                raw_values.append(raw)
            hooks.update(str(value).strip() for value in raw_values if str(value or "").strip())
    return hooks


def _validate_temporal(
    hard: list[dict[str, Any]], canonical: dict[str, Any], resolved: dict[str, dict[str, Any]]
) -> None:
    if canonical.get("temporal_registry") != EXPECTED_TEMPORAL_FILE:
        _error(hard, "temporal_registry_manifest_stale", expected=EXPECTED_TEMPORAL_FILE, actual=canonical.get("temporal_registry"))
        return
    payload = load_temporal_registry(BASE / EXPECTED_TEMPORAL_FILE)
    rows = [row for row in payload.get("entries", []) or [] if isinstance(row, dict)]
    entries = {str(row.get("id") or "").strip(): row for row in rows if str(row.get("id") or "").strip()}
    if len(entries) != len(rows):
        _error(hard, "temporal_duplicate_ids")

    service = object.__new__(GuideUltimeManualRuntimeService)
    for hook in sorted(_temporal_hooks(resolved)):
        entry = entries.get(hook)
        if entry is None:
            _error(hard, "temporal_hook_missing", hook=hook)
            continue
        if not service._temporal_player_instruction(entry):
            _error(hard, "temporal_hook_without_player_instruction", hook=hook)

    for hook in ("frigost_hunter_blessure_to_chasse", "frigost_hunter_chasse_to_brocouille"):
        text = str(entries.get(hook, {}).get("route_policy") or "")
        if "13 h" not in text:
            _error(hard, "frigost_13h_delay_missing", hook=hook)
    bonmonstres = str(entries.get("frigost_bonmonstres_attempt_window", {}).get("route_policy") or "")
    if "5 minutes" not in bonmonstres or "1 h" not in bonmonstres:
        _error(hard, "bonmonstres_retry_contract_invalid")


def _validate_ocre(hard: list[dict[str, Any]], canonical: dict[str, Any]) -> None:
    if canonical.get("ocre_capture_registry") != EXPECTED_OCRE_CAPTURE_FILE:
        _error(hard, "ocre_capture_manifest_stale", expected=EXPECTED_OCRE_CAPTURE_FILE, actual=canonical.get("ocre_capture_registry"))
    if canonical.get("ocre_final_route") != EXPECTED_OCRE_FINAL_FILE:
        _error(hard, "ocre_final_manifest_stale", expected=EXPECTED_OCRE_FINAL_FILE, actual=canonical.get("ocre_final_route"))
        return
    if canonical.get("success_contracts") != EXPECTED_SUCCESS_CONTRACTS_FILE:
        _error(hard, "success_contracts_manifest_stale", expected=EXPECTED_SUCCESS_CONTRACTS_FILE, actual=canonical.get("success_contracts"))

    alias = _load(BASE / EXPECTED_OCRE_FINAL_FILE)
    if alias.get("base_file") != EXPECTED_OCRE_COMPLETION_FILE:
        _error(hard, "ocre_final_base_invalid", expected=EXPECTED_OCRE_COMPLETION_FILE, actual=alias.get("base_file"))
    completion = _load(BASE / EXPECTED_OCRE_COMPLETION_FILE)
    expected_deps = {EXPECTED_OCRE_CAPTURE_FILE, EXPECTED_TEMPORAL_FILE}
    actual_deps = {str(value) for value in completion.get("depends_on", []) or []}
    if actual_deps != expected_deps:
        _error(hard, "ocre_completion_dependencies_invalid", expected=sorted(expected_deps), actual=sorted(actual_deps))

    resolved = load_manual_chapter(BASE / EXPECTED_OCRE_FINAL_FILE)
    stages = [stage for stage in resolved.get("stages", []) or [] if isinstance(stage, dict)]
    if len(stages) != 5:
        _error(hard, "ocre_final_stage_count_invalid", expected=5, actual=len(stages))
    _, by = _stage_index(resolved)
    kral = _need_stage(hard, by, "OCRE-F4")
    if kral is not None and kral.get("temporal_hook") != "kralamoure_server_opening":
        _error(hard, "ocre_kralamoure_temporal_hook_invalid", actual=kral.get("temporal_hook"))


def _validate_key_causality(hard: list[dict[str, Any]], resolved: dict[str, dict[str, Any]]) -> None:
    astrub_ids, astrub = _stage_index(resolved.get("astrub", {}))
    del astrub_ids
    for stage_id in ("AST-06", "AST-08", "AST-09"):
        _need_quests(hard, astrub, stage_id, {"Le tour du monde"})
    _need_quests(hard, astrub, "AST-14", {"L'invasion des profanateurs de sépultures"})

    _, level100 = _stage_index(resolved.get("level_100_120", {}))
    _need_quests(hard, level100, "L100-15", {
        "À la croisée des mondes", "Sous le bois de sa colère", "Infâme pourriture",
        "Le Saule du Promeneur", "Dites-le avec des fleurs",
    })

    _, level120 = _stage_index(resolved.get("level_120_150", {}))
    _need_quests(hard, level120, "L120-00", {"La terre banquise", "La maire de glace", "Full Contact", "Bienvenue à Frigost"})
    _need_quests(hard, level120, "L120-21", {"Qu'est-ce qu'on a fait des tuyaux ?", "Lâcher les gaz"})

    ids150, level150 = _stage_index(resolved.get("level_150_170", {}))
    _need_quests(hard, level150, "L150-13", {"Si loin, si proches", "Où est mon samouraï ?", "Sombre mystère", "Sécurité routière", "Gobstination d'un Grobelin"})
    _need_quests(hard, level150, "L150-15", {"Anomalies temporelles", "C'est ton destin", "Retour vers le présent", "Prisonniers du temps"})
    _before(hard, ids150, "L150-15", "L150-17")
    for stage_id in ("L150-07", "L150-08"):
        _forbid_unconditional(hard, level150, stage_id, {"Complètement givré", "L'appel de la forêt", "Crocs en jambes", "Ourse molle"})

    _, level190 = _stage_index(resolved.get("level_181_190", {}))
    _need_quests(hard, level190, "L190-00", {"Développement durable", "Le champ des héros", "La transe du crystal"})
    _need_quests(hard, level190, "L190-04", {"Porte, Kolosso, trésor", "C'est Rébro", "Le champ des héros", "La transe du crystal"})
    _need_quests(hard, level190, "L190-05", {"Le pic qui glace", "Mission Solution"})
    _need_quests(hard, level190, "L190-06", {"Porte, Glourséleste, trésor", "Glourson et lumière", "L'arène et le roi"})
    for stage_id in ("L190-00", "L190-04"):
        _forbid_unconditional(hard, level190, stage_id, {"Crocs en jambes"})
    for stage_id in ("L190-05", "L190-06"):
        _forbid_unconditional(hard, level190, stage_id, {"Ourse molle"})

    ids200, level200 = _stage_index(resolved.get("level_191_200", {}))
    _need_quests(hard, level200, "P200-07-PREP", {"S'armer contre le destin"})
    _need_quests(hard, level200, "P200-14", {"La loi du plus faible", "Leçon d'histoire"})
    _need_quests(hard, level200, "L200-ENUT-PREP", {"Reconnaissance de dettes"})
    _need_quests(hard, level200, "L200-ENUT-CLOSE", {"Le roi et moi"})
    _before(hard, ids200, "P200-06", "P200-07-PREP")
    _before(hard, ids200, "P200-13", "P200-14")

    ids_post, post = _stage_index(resolved.get("level_200_plus", {}))
    required_post = [
        "P200-08", "P200-AU-DETOUR", "P200-16", "P200-17", "P200-18", "P200-20",
        "P200-19", "P200-21", "P200-22", "P200-23", "P200-24", "P200-25",
    ]
    for stage_id in required_post:
        _need_stage(hard, post, stage_id)
    for left, right in zip(required_post, required_post[1:]):
        _before(hard, ids_post, left, right)
    _need_quests(hard, post, "P200-AU-DETOUR", {"Au détour d'un rêve perdu"})
    _need_quests(hard, post, "P200-19", {"La graine de la révolte", "Par l'héritage qui vous lie", "Une dernière volonté"})
    _need_quests(hard, post, "P200-24", {"Flovoraison", "Qui nous protège du Protecteur ?"})


def _catalog_names() -> set[str]:
    provider = QuestProvider()
    return {
        normalize_text(getattr(quest, "name", ""))
        for quest in provider.list_quests()
        if normalize_text(getattr(quest, "name", ""))
    }


def _validate_catalog(hard: list[dict[str, Any]], resolved: dict[str, dict[str, Any]]) -> None:
    try:
        catalog = _catalog_names()
    except Exception as exc:
        _error(hard, "quest_catalog_load_failed", error=f"{type(exc).__name__}: {exc}")
        return
    for chapter_id, payload in resolved.items():
        for stage in payload.get("stages", []) or []:
            if not isinstance(stage, dict):
                continue
            for raw in _quest_values(stage):
                name = raw.split(":", 1)[1].strip() if raw.startswith("conditional:") else raw
                if normalize_text(name) not in catalog:
                    _error(hard, "quest_missing_from_catalog", chapter=chapter_id, stage=stage.get("id"), quest=name)


def audit(*, skip_catalog: bool = False) -> dict[str, Any]:
    manifest = _load(MANIFEST)
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    hard: list[dict[str, Any]] = []

    resolved = _validate_chapters(hard, manifest)
    _validate_bonta(hard, canonical)
    _validate_orders(hard, canonical)
    _validate_temporal(hard, canonical, resolved)
    _validate_ocre(hard, canonical)
    _validate_key_causality(hard, resolved)
    if not skip_catalog:
        _validate_catalog(hard, resolved)

    return {
        "schema_version": 16,
        "status": "STRICT_PASS" if not hard else "STRICT_FAIL",
        "hard_error_count": len(hard),
        "hard_errors": hard,
        "canonical_chapter_count": len(resolved),
        "canonical_stage_count": sum(len(payload.get("stages", []) or []) for payload in resolved.values()),
        "canonical_chapters_checked": [chapter_id for chapter_id, _, _ in EXPECTED_CHAPTERS if chapter_id in resolved],
        "bonta_file": EXPECTED_BONTA_FILE,
        "temporal_file": EXPECTED_TEMPORAL_FILE,
        "ocre_final_file": EXPECTED_OCRE_FINAL_FILE,
        "catalog_skipped": bool(skip_catalog),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit transversal final du Guide Ultime manuel canonique.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    result = audit(skip_catalog=args.skip_catalog)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and result["hard_error_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
