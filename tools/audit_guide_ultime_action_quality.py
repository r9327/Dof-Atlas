from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    MANUAL_DIR,
    GuideUltimeManualRuntimeService,
)
from app.quest_catalog import normalize_text


MANIFEST = MANUAL_DIR / "manifest_v1.json"

_PLACEHOLDER_TOKENS = (
    "todo",
    "tbd",
    "placeholder",
    "???",
    "a verifier",
    "a confirmer",
    "non verifie",
    "inconnu",
)

_AUTHORING_TOKENS = (
    "questprovider",
    "runtime",
    "compteur local",
    "ne simule",
    "ne jamais simuler",
    "ne jamais pretendre",
    "fictif",
    "fiche de fermeture",
    "route principale",
    "stage_id",
    "merge hook",
    "merge_hook",
    "chapitre canonique",
    "blocker",
    "rerun",
    "cleanup",
    "startcriterion",
    "walkthrough local",
    "temporal_registry",
    "pending",
    "handoff",
    "capture_allowed=false",
)

_VAGUE_TOKENS = (
    "si besoin",
    "si necessaire",
    "si possible",
    "au besoin",
    "eventuellement",
    "etc.",
)

_TRAVEL_ACTION_RE = re.compile(
    r"^(?:va\b|rends[- ]?toi\b|retourne\b|reviens\b|parle\b|prends\b|lance\b|entre\b|rejoins\b|teleporte\b|utilise\s+(?:le\s+)?zaap\b)",
    flags=re.IGNORECASE,
)
_BRACKET_COORD_RE = re.compile(r"\[[^\]]*,[^\]]*\]")
_INTERNAL_FILE_RE = re.compile(r"\b[\w.-]+\.json\b", flags=re.IGNORECASE)
_INTERNAL_STAGE_ID_RE = re.compile(
    r"\b(?:INC|AST|PAD|AMK|BNT|OCRE|P200|L\d{2,3})-[A-Z0-9][A-Z0-9-]*\b",
    flags=re.IGNORECASE,
)


def _contains_token(raw_value: str, normalized_value: str, token: str) -> bool:
    normalized_token = normalize_text(token)
    if normalized_token:
        return normalized_token in normalized_value
    return bool(token) and token.casefold() in raw_value.casefold()


def _issue(
    *,
    severity: str,
    code: str,
    chapter: str,
    stage: str,
    line_index: int,
    kind: str,
    position: str,
    text: str,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "chapter": chapter,
        "stage": stage,
        "line_index": line_index,
        "kind": kind,
        "position": position,
        "text": text,
    }


def _line_issues(
    *,
    chapter_id: str,
    stage_id: str,
    line_index: int,
    line: dict[str, Any],
) -> list[dict[str, Any]]:
    kind = str(line.get("kind") or "").strip()
    position = str(line.get("position") or "").strip()
    text = " ".join(str(line.get("text") or "").split()).strip()
    normalized_text = normalize_text(text)
    normalized_position = normalize_text(position)
    issues: list[dict[str, Any]] = []

    for token in _PLACEHOLDER_TOKENS:
        if _contains_token(text, normalized_text, token) or _contains_token(position, normalized_position, token):
            issues.append(
                _issue(
                    severity="hard",
                    code="placeholder_or_unverified_instruction",
                    chapter=chapter_id,
                    stage=stage_id,
                    line_index=line_index,
                    kind=kind,
                    position=position,
                    text=text,
                )
            )
            break

    authoring_language = any(_contains_token(text, normalized_text, token) for token in _AUTHORING_TOKENS)
    internal_reference = bool(
        _INTERNAL_FILE_RE.search(text)
        or _INTERNAL_FILE_RE.search(position)
        or _INTERNAL_STAGE_ID_RE.search(text)
        or _INTERNAL_STAGE_ID_RE.search(position)
    )
    if authoring_language or internal_reference:
        issues.append(
            _issue(
                severity="review",
                code="authoring_language_visible_to_player",
                chapter=chapter_id,
                stage=stage_id,
                line_index=line_index,
                kind=kind,
                position=position,
                text=text,
            )
        )

    if kind == "action":
        for token in _VAGUE_TOKENS:
            if _contains_token(text, normalized_text, token):
                issues.append(
                    _issue(
                        severity="review",
                        code="vague_action_condition",
                        chapter=chapter_id,
                        stage=stage_id,
                        line_index=line_index,
                        kind=kind,
                        position=position,
                        text=text,
                    )
                )
                break

        if not position and _TRAVEL_ACTION_RE.search(text):
            if GuideUltimeManualRuntimeService._coords_from_text(text) is None:
                issues.append(
                    _issue(
                        severity="review",
                        code="travel_action_without_position",
                        chapter=chapter_id,
                        stage=stage_id,
                        line_index=line_index,
                        kind=kind,
                        position=position,
                        text=text,
                    )
                )

    if position and _BRACKET_COORD_RE.search(position):
        if GuideUltimeManualRuntimeService._coords_from_text(position) is None:
            issues.append(
                _issue(
                    severity="hard",
                    code="malformed_bracket_coordinate",
                    chapter=chapter_id,
                    stage=stage_id,
                    line_index=line_index,
                    kind=kind,
                    position=position,
                    text=text,
                )
            )

    return issues


def audit() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    chapter_rows = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    chapter_rows.sort(key=lambda row: int(row.get("order") or 0))

    service = object.__new__(GuideUltimeManualRuntimeService)
    service.quest_provider = None
    service._quest_name_to_id = {}

    issues: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    chapter_stats: dict[str, dict[str, Any]] = {}
    stage_issue_codes: dict[str, set[str]] = defaultdict(set)
    global_stage_count = 0
    global_line_count = 0
    global_action_line_count = 0
    global_warning_line_count = 0
    global_positioned_action_count = 0

    for meta in chapter_rows:
        chapter_id = str(meta.get("id") or "").strip()
        filename = str(meta.get("file") or "").strip()
        chapter = load_manual_chapter(MANUAL_DIR / filename)
        stages = [stage for stage in chapter.get("stages", []) or [] if isinstance(stage, dict)]
        preparation_schedule = service._chapter_preparation_schedule(chapter, stages)

        chapter_line_count = 0
        chapter_action_count = 0
        chapter_warning_count = 0
        chapter_positioned_actions = 0
        chapter_issue_start = len(issues)

        for stage_position, stage in enumerate(stages):
            global_stage_count += 1
            stage_id = str(stage.get("id") or "").strip() or "<sans-id>"
            quest_names = service._stage_quest_names(stage)
            lines = service._stage_lines(
                stage,
                quest_names,
                chapter_preparation=preparation_schedule.get(stage_position, []),
            )
            for line_index, line in enumerate(lines):
                if not isinstance(line, dict):
                    continue
                chapter_line_count += 1
                global_line_count += 1
                kind = str(line.get("kind") or "").strip()
                if kind == "action":
                    chapter_action_count += 1
                    global_action_line_count += 1
                    if str(line.get("position") or "").strip():
                        chapter_positioned_actions += 1
                        global_positioned_action_count += 1
                elif kind == "warning":
                    chapter_warning_count += 1
                    global_warning_line_count += 1

                found = _line_issues(
                    chapter_id=chapter_id,
                    stage_id=stage_id,
                    line_index=line_index,
                    line=line,
                )
                for row in found:
                    issues.append(row)
                    counts[row["code"]] += 1
                    severity_counts[row["severity"]] += 1
                    stage_issue_codes[f"{chapter_id}:{stage_id}"].add(str(row["code"]))

        chapter_issues = issues[chapter_issue_start:]
        hard_count = sum(1 for row in chapter_issues if row["severity"] == "hard")
        review_count = sum(1 for row in chapter_issues if row["severity"] == "review")
        if hard_count:
            status = "ACTION_REVIEW_BLOCKED"
        elif review_count:
            status = "ACTION_REVIEW_NEEDED"
        else:
            status = "ACTION_TEXT_HEURISTICALLY_CLEAN"
        chapter_stats[chapter_id] = {
            "file": filename,
            "stage_count": len(stages),
            "instruction_line_count": chapter_line_count,
            "action_line_count": chapter_action_count,
            "warning_line_count": chapter_warning_count,
            "positioned_action_line_count": chapter_positioned_actions,
            "hard_issue_count": hard_count,
            "review_issue_count": review_count,
            "status": status,
        }

    return {
        "schema_version": 1,
        "status": "BLOCKED" if severity_counts["hard"] else "REVIEW_REQUIRED" if severity_counts["review"] else "HEURISTICALLY_CLEAN",
        "manifest_status": str(manifest.get("status") or ""),
        "chapter_count": len(chapter_rows),
        "stage_count": global_stage_count,
        "instruction_line_count": global_line_count,
        "action_line_count": global_action_line_count,
        "warning_line_count": global_warning_line_count,
        "positioned_action_line_count": global_positioned_action_count,
        "hard_issue_count": int(severity_counts["hard"]),
        "review_issue_count": int(severity_counts["review"]),
        "issue_counts": dict(sorted(counts.items())),
        "stage_with_issue_count": len(stage_issue_codes),
        "chapters": chapter_stats,
        "issues": issues,
        "note": (
            "Inventaire heuristique de la passe Actions. Les erreurs hard indiquent des marqueurs inachevés ou des coordonnées malformées. "
            "Les éléments review doivent être relus/corrigés, mais leur absence ne prouve pas la justesse gameplay ou GPS."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit qualité des consignes joueur du Guide Ultime manuel.")
    parser.add_argument("--strict-hard", action="store_true", help="Échoue sur les problèmes durs uniquement.")
    parser.add_argument("--strict-review", action="store_true", help="Échoue tant qu'une consigne reste à relire.")
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

    if args.strict_review and (report["hard_issue_count"] or report["review_issue_count"]):
        return 1
    if args.strict_hard and report["hard_issue_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
