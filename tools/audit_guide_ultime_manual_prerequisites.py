from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.encyclopedia.providers.quest_provider import QuestProvider
from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.quest_catalog import normalize_text


MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = MANUAL / "manifest_v1.json"


def quest_key(value: Any) -> str:
    """Normalize only typographic ligature variants before exact quest matching.

    Route authors and the local catalogue legitimately alternate between ``œ``
    and ``oe`` (and, more rarely, ``æ``/``ae``). Treating those spellings as
    different quests creates false hard errors, but broader fuzzy matching would
    hide real title mistakes. Keep the audit exact apart from these ligatures.
    """

    text = str(value or "")
    text = text.replace("Œ", "OE").replace("œ", "oe")
    text = text.replace("Æ", "AE").replace("æ", "ae")
    return normalize_text(text)


# QuestProvider exposes each member of some game-side OR prerequisites as a
# separate prerequisite line. The manual route deliberately follows one
# alignment, so requiring every mutually-exclusive member would invent quests
# the character cannot/should not do. Keep this map tiny and explicit: it is not
# a general fuzzy/OR escape hatch.
COMPLETED_ALTERNATIVE_GROUPS: dict[str, tuple[frozenset[str], ...]] = {
    quest_key("Malédiction !"): (
        frozenset({
            quest_key("La destinée"),
            quest_key("La fatalité"),
            quest_key("La rivalité"),
        }),
    ),
}


def completed_alternative_satisfied(
    dependent_name: str,
    target_key: str,
    positions: dict[str, list[int]],
    current: int,
) -> bool:
    for group in COMPLETED_ALTERNATIVE_GROUPS.get(quest_key(dependent_name), ()):
        if target_key not in group:
            continue
        return any(
            position < current
            for alternative in group
            for position in positions.get(alternative, [])
        )
    return False


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Objet JSON attendu: {path}")
    return payload


def quest_names_from_stage(stage: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for field in ("quest_sequence", "parallel_quests", "quests"):
        raw = stage.get(field)
        rows = raw if isinstance(raw, list) else [raw] if raw else []
        for value in rows:
            if not isinstance(value, str):
                continue
            value = value.strip()
            if not value or value.startswith("conditional:"):
                continue
            key = quest_key(value)
            if key and key not in seen:
                seen.add(key)
                result.append(value)
    return result


def all_named_quests(value: Any, result: set[str]) -> None:
    if isinstance(value, dict):
        for key in ("quest", "quests", "required_quest", "after_quest"):
            child = value.get(key)
            if isinstance(child, str) and child.strip() and not child.startswith("conditional:"):
                result.add(quest_key(child))
            elif isinstance(child, list):
                for row in child:
                    if isinstance(row, str) and row.strip() and not row.startswith("conditional:"):
                        result.add(quest_key(row))
        for child in value.values():
            all_named_quests(child, result)
    elif isinstance(value, list):
        for child in value:
            all_named_quests(child, result)


def prerequisite_target(line: str, prefix: str) -> str:
    text = str(line or "").strip()
    normalized = quest_key(text)
    normalized_prefix = quest_key(prefix)
    if not normalized.startswith(normalized_prefix):
        return ""
    if ":" in text:
        return text.split(":", 1)[1].strip()
    remainder = normalized.removeprefix(normalized_prefix).strip("_")
    return remainder.replace("_", " ").strip()


def _flatten_strings(value: Any, result: list[str]) -> None:
    if isinstance(value, str):
        if value.strip():
            result.append(value.strip())
        return
    if isinstance(value, list):
        for child in value:
            _flatten_strings(child, result)
        return
    if isinstance(value, dict):
        for child in value.values():
            _flatten_strings(child, result)


def stage_order_evidence(stage: dict[str, Any], prerequisite: str, dependent: str) -> dict[str, Any]:
    """Return conservative textual evidence for ordering inside one macro-stage."""

    ordered_fields = (
        "entry",
        "activation",
        "preparation",
        "take",
        "route",
        "instructions",
        "progress_also",
        "before_leaving",
        "hard_exit",
    )
    lines: list[str] = []
    for field in ordered_fields:
        _flatten_strings(stage.get(field), lines)

    pre_key = quest_key(prerequisite)
    dep_key = quest_key(dependent)
    pre_index: int | None = None
    dep_index: int | None = None
    for index, line in enumerate(lines):
        key = quest_key(line)
        if pre_index is None and pre_key and pre_key in key:
            pre_index = index
        if dep_index is None and dep_key and dep_key in key:
            dep_index = index

    demonstrated = pre_index is not None and dep_index is not None and pre_index < dep_index
    return {
        "demonstrated": demonstrated,
        "prerequisite_line_index": pre_index,
        "dependent_line_index": dep_index,
        "ordered_line_count": len(lines),
    }


def build_route(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[int]], set[str]]:
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    chapters = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    chapters.sort(key=lambda row: int(row.get("order") or 0))

    timeline: list[dict[str, Any]] = []
    positions: dict[str, list[int]] = defaultdict(list)
    cursor = 0
    for chapter_meta in chapters:
        filename = str(chapter_meta.get("file") or "").strip()
        chapter_id = str(chapter_meta.get("id") or filename).strip()
        if not filename:
            continue
        chapter = load_manual_chapter(MANUAL / filename)
        for stage in chapter.get("stages", []) or []:
            if not isinstance(stage, dict):
                continue
            names = quest_names_from_stage(stage)
            row = {
                "position": cursor,
                "chapter": chapter_id,
                "stage": str(stage.get("id") or ""),
                "quests": names,
                "stage_payload": stage,
            }
            timeline.append(row)
            for name in names:
                positions[quest_key(name)].append(cursor)
            cursor += 1

    conditional_names: set[str] = set()
    for field in ("conditional_routes", "transversal_routes"):
        for meta in canonical.get(field, []) or []:
            if not isinstance(meta, dict):
                continue
            filename = str(meta.get("file") or "").strip()
            if not filename:
                continue
            try:
                payload = load_manual_chapter(MANUAL / filename)
            except Exception:
                payload = load_json(MANUAL / filename)
            all_named_quests(payload, conditional_names)

    return timeline, positions, conditional_names


def catalog_unavailable_report(manifest: dict[str, Any], timeline: list[dict[str, Any]]) -> dict[str, Any]:
    route_occurrences = sum(len(row.get("quests", [])) for row in timeline)
    warning = {
        "code": "quest_catalog_unavailable",
        "message": "QuestProvider n'a chargé aucune quête; l'ordre causal QuestProvider n'est pas auditable dans cet environnement.",
    }
    return {
        "schema_version": 3,
        "status": "CATALOG_UNAVAILABLE",
        "audit_complete": False,
        "catalog_available": False,
        "provider_quest_count": 0,
        "manifest_status": str(manifest.get("status") or ""),
        "route_stage_count": len(timeline),
        "route_quest_occurrence_count": route_occurrences,
        "route_quest_occurrences_checked": 0,
        "quest_dependency_count_checked": 0,
        "same_stage_dependency_count": 0,
        "same_stage_dependency_order_demonstrated_count": 0,
        "success_requirements_for_separate_audit": [],
        "hard_error_count": 0,
        "warning_count": 1,
        "hard_errors": [],
        "warnings": [warning],
        "interpretation": [
            "Aucune conclusion de couverture ou d'ordre QuestProvider n'est tirée quand le catalogue est absent.",
            "--strict échoue sur cet état sauf si --allow-missing-catalog est explicitement utilisé par un environnement CI sans données locales.",
            "Un run local de validation finale doit rester exécuté avec le vrai catalogue QuestProvider."
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit causal des prérequis QuestProvider du Guide Ultime manuel."
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--allow-missing-catalog",
        action="store_true",
        help="Autorise uniquement l'état CATALOG_UNAVAILABLE; ne transforme aucune erreur causale réelle en warning.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Écrit aussi le rapport JSON à cet emplacement.")
    args = parser.parse_args()

    manifest = load_json(MANIFEST)
    timeline, positions, conditional_names = build_route(manifest)

    provider = QuestProvider()
    quests = provider.list_quests()
    if not quests:
        result = catalog_unavailable_report(manifest, timeline)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.strict and not args.allow_missing_catalog:
            raise SystemExit(1)
        return

    grouped: dict[str, list[Any]] = defaultdict(list)
    for quest in quests:
        key = quest_key(getattr(quest, "name", ""))
        if key:
            grouped[key].append(quest)

    hard: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    checked_quests = 0
    checked_dependencies = 0
    same_stage_dependencies = 0
    same_stage_demonstrated = 0
    success_requirements: set[str] = set()

    for route_row in timeline:
        current = int(route_row["position"])
        stage_payload = route_row["stage_payload"]
        for authored_name in route_row["quests"]:
            records = grouped.get(quest_key(authored_name), [])
            if len(records) != 1:
                hard.append({
                    "code": "route_quest_catalog_resolution",
                    "chapter": route_row["chapter"],
                    "stage": route_row["stage"],
                    "quest": authored_name,
                    "catalog_matches": len(records),
                })
                continue
            quest = records[0]
            checked_quests += 1

            for raw_line in getattr(quest, "prerequisites", []) or []:
                line = str(raw_line or "").strip()
                if not line:
                    continue
                normalized = quest_key(line)

                completed_name = prerequisite_target(line, "Quete terminee")
                active_name = prerequisite_target(line, "Quete active")
                success_name = prerequisite_target(line, "Succes requis")

                if completed_name:
                    checked_dependencies += 1
                    target_key = quest_key(completed_name)
                    if completed_alternative_satisfied(authored_name, target_key, positions, current):
                        continue
                    target_positions = positions.get(target_key, [])
                    if any(pos < current for pos in target_positions):
                        continue
                    if current in target_positions:
                        same_stage_dependencies += 1
                        evidence = stage_order_evidence(stage_payload, completed_name, authored_name)
                        if evidence["demonstrated"]:
                            same_stage_demonstrated += 1
                        else:
                            warnings.append({
                                "code": "same_stage_completed_prerequisite_order_not_demonstrated",
                                "chapter": route_row["chapter"],
                                "stage": route_row["stage"],
                                "quest": authored_name,
                                "prerequisite": completed_name,
                                "evidence": evidence,
                            })
                        continue
                    if target_positions:
                        hard.append({
                            "code": "prerequisite_routed_after_dependent",
                            "chapter": route_row["chapter"],
                            "stage": route_row["stage"],
                            "quest": authored_name,
                            "prerequisite": completed_name,
                            "dependent_position": current,
                            "prerequisite_positions": target_positions,
                        })
                    elif target_key in conditional_names:
                        warnings.append({
                            "code": "prerequisite_only_in_conditional_or_transversal_route",
                            "chapter": route_row["chapter"],
                            "stage": route_row["stage"],
                            "quest": authored_name,
                            "prerequisite": completed_name,
                        })
                    else:
                        hard.append({
                            "code": "prerequisite_absent_from_manual_route",
                            "chapter": route_row["chapter"],
                            "stage": route_row["stage"],
                            "quest": authored_name,
                            "prerequisite": completed_name,
                        })
                    continue

                if active_name:
                    checked_dependencies += 1
                    target_key = quest_key(active_name)
                    target_positions = positions.get(target_key, [])
                    if any(pos < current for pos in target_positions):
                        continue
                    if current in target_positions:
                        evidence = stage_order_evidence(stage_payload, active_name, authored_name)
                        if not evidence["demonstrated"]:
                            warnings.append({
                                "code": "same_stage_active_prerequisite_order_not_demonstrated",
                                "chapter": route_row["chapter"],
                                "stage": route_row["stage"],
                                "quest": authored_name,
                                "required_active_quest": active_name,
                                "evidence": evidence,
                            })
                        continue
                    if target_positions:
                        hard.append({
                            "code": "required_active_quest_routed_too_late",
                            "chapter": route_row["chapter"],
                            "stage": route_row["stage"],
                            "quest": authored_name,
                            "required_active_quest": active_name,
                            "dependent_position": current,
                            "required_positions": target_positions,
                        })
                    elif target_key in conditional_names:
                        warnings.append({
                            "code": "required_active_quest_only_conditional_or_transversal",
                            "chapter": route_row["chapter"],
                            "stage": route_row["stage"],
                            "quest": authored_name,
                            "required_active_quest": active_name,
                        })
                    else:
                        hard.append({
                            "code": "required_active_quest_absent_from_manual_route",
                            "chapter": route_row["chapter"],
                            "stage": route_row["stage"],
                            "quest": authored_name,
                            "required_active_quest": active_name,
                        })
                    continue

                if success_name:
                    success_requirements.add(success_name)
                    continue

                if normalized.startswith("niveau_"):
                    continue

                warnings.append({
                    "code": "opaque_start_criterion_requires_manual_review",
                    "chapter": route_row["chapter"],
                    "stage": route_row["stage"],
                    "quest": authored_name,
                    "criterion": line,
                })

    result = {
        "schema_version": 3,
        "status": "COMPLETE_BY_PROVIDER_ORDER" if not hard else "GAPS_REMAIN",
        "audit_complete": True,
        "catalog_available": True,
        "provider_quest_count": len(quests),
        "manifest_status": str(manifest.get("status") or ""),
        "route_stage_count": len(timeline),
        "route_quest_occurrence_count": sum(len(row.get("quests", [])) for row in timeline),
        "route_quest_occurrences_checked": checked_quests,
        "quest_dependency_count_checked": checked_dependencies,
        "same_stage_dependency_count": same_stage_dependencies,
        "same_stage_dependency_order_demonstrated_count": same_stage_demonstrated,
        "success_requirements_for_separate_audit": sorted(success_requirements, key=quest_key),
        "hard_error_count": len(hard),
        "warning_count": len(warnings),
        "hard_errors": hard,
        "warnings": warnings,
        "interpretation": [
            "Un prérequis terminé placé dans une macro-fiche antérieure est considéré causalement sûr.",
            "Un prérequis dans la même macro-fiche n'est plus un PASS implicite: l'ordre textuel doit être démontré ou un warning est émis.",
            "Les variantes typographiques œ/oe et æ/ae sont équivalentes; aucun fuzzy matching sémantique n'est appliqué.",
            "Les groupes OR explicitement documentés (actuellement les variantes d'alignement de Malédiction !) sont satisfaits par une seule branche réellement routée.",
            "Les succès prérequis sont exportés pour l'audit de couverture séparé.",
            "Les critères opaques restent à revue manuelle; l'audit préfère un warning à une hypothèse silencieuse."
        ],
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and hard:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
