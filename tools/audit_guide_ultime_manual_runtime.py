from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.encyclopedia.services.guide_auto_validation_contract import (
    build_card_auto_validation_contract,
)
from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    MANUAL_DIR,
    _SUPPORTED_STAGE_FIELDS,
    GuideUltimeManualRuntimeService,
)


MANIFEST = MANUAL_DIR / "manifest_v1.json"
_TARGET_KEYS = (
    "quests",
    "successes",
    "dungeons",
    "monsters",
    "items",
    "reserved_items",
    "bank_reservations",
    "capture_requirements",
)


def audit() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    rows = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    rows.sort(key=lambda row: int(row.get("order") or 0))

    service = object.__new__(GuideUltimeManualRuntimeService)
    service.quest_provider = None
    service._quest_name_to_id = {}

    empty_cards: list[str] = []
    count_mismatches: list[dict] = []
    unsupported: dict[str, set[str]] = defaultdict(set)
    field_usage: Counter[str] = Counter()
    stage_count_by_chapter: dict[str, int] = {}
    line_count_by_chapter: dict[str, int] = {}
    resolved_from: dict[str, list[str]] = {}
    auto_validation_counts: Counter[str] = Counter()
    auto_validation_gap_counts: Counter[str] = Counter()
    auto_validation_gaps: list[dict] = []
    chapter_target_counts: dict[str, Counter[str]] = defaultdict(Counter)
    chapter_gap_counts: dict[str, Counter[str]] = defaultdict(Counter)
    chapter_gap_stages: dict[str, list[str]] = defaultdict(list)
    chapter_structured_stages: Counter[str] = Counter()
    chapter_positioned_stages: Counter[str] = Counter()
    chapter_positioned_lines: Counter[str] = Counter()
    global_index = 1

    for meta in rows:
        chapter_id = str(meta.get("id") or "").strip()
        filename = str(meta.get("file") or "").strip()
        chapter = load_manual_chapter(MANUAL_DIR / filename)
        stages = [stage for stage in chapter.get("stages", []) or [] if isinstance(stage, dict)]
        stage_count_by_chapter[chapter_id] = len(stages)
        line_total = 0
        resolved_from[chapter_id] = [str(value) for value in chapter.get("_resolved_from", []) or []]
        preparation_schedule = service._chapter_preparation_schedule(chapter, stages)

        declared = meta.get("stage_count")
        if declared is not None and int(declared) != len(stages):
            count_mismatches.append(
                {"chapter": chapter_id, "declared": int(declared), "resolved": len(stages)}
            )

        for stage_position, stage in enumerate(stages):
            stage_id = str(stage.get("id") or "").strip() or "<sans-id>"
            field_usage.update(str(key) for key in stage)
            unsupported[chapter_id].update(
                str(key) for key in stage if str(key) not in _SUPPORTED_STAGE_FIELDS
            )
            quest_names = service._stage_quest_names(stage)
            lines = service._stage_lines(
                stage,
                quest_names,
                chapter_preparation=preparation_schedule.get(stage_position, []),
            )
            line_total += len(lines)
            positioned = [
                row
                for row in lines
                if isinstance(row, dict) and str(row.get("position") or "").strip()
            ]
            if positioned:
                chapter_positioned_stages[chapter_id] += 1
                chapter_positioned_lines[chapter_id] += len(positioned)
            if not lines:
                empty_cards.append(f"{chapter_id}:{stage_id}")

            card = service._stage_to_card(
                chapter_id,
                meta,
                chapter,
                stage,
                global_index,
                chapter_preparation=preparation_schedule.get(stage_position, []),
            )
            contract = build_card_auto_validation_contract(card)
            has_structured_target = False
            for key in _TARGET_KEYS:
                count = len(contract.get(key, []) or [])
                auto_validation_counts[key] += count
                chapter_target_counts[chapter_id][key] += count
                has_structured_target = has_structured_target or count > 0
            if has_structured_target:
                chapter_structured_stages[chapter_id] += 1

            missing = list(contract.get("missing_structured_categories", []) or [])
            if missing:
                auto_validation_gap_counts.update(missing)
                chapter_gap_counts[chapter_id].update(missing)
                chapter_gap_stages[chapter_id].append(stage_id)
                auto_validation_gaps.append(
                    {
                        "chapter": chapter_id,
                        "stage": stage_id,
                        "missing": missing,
                        "hints": {
                            key: list(values or [])
                            for key, values in (contract.get("prose_hints") or {}).items()
                            if values
                        },
                    }
                )
            global_index += 1
        line_count_by_chapter[chapter_id] = line_total

    unsupported_clean = {
        chapter: sorted(fields)
        for chapter, fields in unsupported.items()
        if fields
    }
    action_review_by_chapter: dict[str, dict] = {}
    for row in rows:
        chapter_id = str(row.get("id") or "")
        stage_count = int(stage_count_by_chapter.get(chapter_id, 0))
        gaps = list(dict.fromkeys(chapter_gap_stages.get(chapter_id, [])))
        empty = [
            value.split(":", 1)[1]
            for value in empty_cards
            if value.startswith(f"{chapter_id}:")
        ]
        unsupported_fields = unsupported_clean.get(chapter_id, [])
        if empty or unsupported_fields:
            status = "STRUCTURE_BLOCKED"
        elif gaps:
            status = "ACTION_REVIEW_WITH_STRUCTURING_GAPS"
        else:
            status = "ACTION_REVIEW_READY"
        action_review_by_chapter[chapter_id] = {
            "file": str(row.get("file") or ""),
            "stage_count": stage_count,
            "instruction_line_count": int(line_count_by_chapter.get(chapter_id, 0)),
            "positioned_stage_count": int(chapter_positioned_stages.get(chapter_id, 0)),
            "positioned_instruction_count": int(chapter_positioned_lines.get(chapter_id, 0)),
            "structured_target_stage_count": int(chapter_structured_stages.get(chapter_id, 0)),
            "target_counts": dict(sorted(chapter_target_counts.get(chapter_id, Counter()).items())),
            "gap_stage_count": len(gaps),
            "gap_counts": dict(sorted(chapter_gap_counts.get(chapter_id, Counter()).items())),
            "gap_stage_ids": gaps,
            "empty_stage_ids": empty,
            "unsupported_stage_fields": unsupported_fields,
            "status": status,
        }

    return {
        "manifest_status": str(manifest.get("status") or ""),
        "chapter_count": len(rows),
        "card_count": sum(stage_count_by_chapter.values()),
        "chapter_ids": [str(row.get("id") or "") for row in rows],
        "stage_count_by_chapter": stage_count_by_chapter,
        "instruction_line_count_by_chapter": line_count_by_chapter,
        "empty_cards": empty_cards,
        "unsupported_stage_fields": unsupported_clean,
        "field_usage": dict(sorted(field_usage.items())),
        "resolved_from": resolved_from,
        "count_mismatches": count_mismatches,
        "action_review": {
            "schema_version": 1,
            "chapters": action_review_by_chapter,
            "note": "Inventaire de préparation pour la passe finale des actions. Un statut READY signifie uniquement que la structure est exploitable pour relire les actions; il ne valide pas le gameplay ni les coordonnées.",
        },
        "auto_validation": {
            "schema_version": 1,
            "target_counts": dict(sorted(auto_validation_counts.items())),
            "gap_count": len(auto_validation_gaps),
            "gap_counts": dict(sorted(auto_validation_gap_counts.items())),
            "gaps": auto_validation_gaps,
            "strict": False,
            "note": "Les gaps sont informatifs tant que les farms/items/réserves/banque/captures textuels n'ont pas tous été convertis en objectifs structurés. Le futur lecteur réseau ne devra jamais deviner un compteur depuis du texte libre, ni confondre conserver sur soi avec mettre en banque.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit du runtime canonique Guide Ultime manuel")
    parser.add_argument(
        "--strict-fields",
        action="store_true",
        help="Échoue aussi si un champ de stage canonique n'est pas encore déclaré supporté.",
    )
    parser.add_argument(
        "--strict-auto-validation",
        action="store_true",
        help="Échoue si un objectif quantifié auto-validable reste uniquement en texte libre. À activer une fois le nettoyage terminé.",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = audit()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    # PowerShell 5.1 can expose cp1252 stdout; keep console output ASCII-safe
    # while preserving the UTF-8 report file exactly.
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    failed = bool(report["empty_cards"] or report["count_mismatches"])
    if args.strict_fields and report["unsupported_stage_fields"]:
        failed = True
    if args.strict_auto_validation and report["auto_validation"]["gap_count"]:
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
