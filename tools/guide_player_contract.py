from __future__ import annotations

"""Phase 7E player-facing Guide contract audit.

The canonical route remains the source of truth. This audit evaluates the
instructions rendered from that route and focuses on UX/content rules that are
not covered by the historical causal/coverage audits.
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    MANUAL_DIR,
    GuideUltimeManualRuntimeService,
)
from app.quest_catalog import normalize_text


MANIFEST = MANUAL_DIR / "manifest_v1.json"

_MULTI_ACTION_RE = re.compile(
    r"(?:\b(?:puis|ensuite|et)\b|[;,])\s*"
    r"(?:va\b|rends[- ]?toi\b|retourne\b|reviens\b|parle\b|prends\b|lance\b|"
    r"entre\b|rejoins\b|t[ée]l[ée]porte\b|utilise\b|ach[èe]te\b|drop\w*\b|"
    r"tue\b|fais\b|bats\b|ramasse\b|donne\b|clique\b|ouvre\b|termine\b|valide\b)",
    flags=re.IGNORECASE,
)
_TALK_TARGET_RE = re.compile(
    r"^(?:parle(?:r)?|discute(?:r)?)\s+"
    r"(?:(?:à|a)\s+(?:la\s+|le\s+|l['’]\s*)?|au\s+|aux\s+|avec\s+)"
    r"(?P<target>.+?)"
    r"(?=\s+(?:pour|afin(?:\s+de)?|et)\b|[.,;:]|$)",
    flags=re.IGNORECASE,
)
_DROP_RE = re.compile(r"\bdrop\w*\b", flags=re.IGNORECASE)
_PURCHASE_RE = re.compile(r"\b(?:achet\w*|ach[èe]t\w*|hdv|h[ôo]tel de vente)\b", flags=re.IGNORECASE)
_DESTINATION_NEXT_RE = re.compile(r"\bdestination\s+suivante\b", flags=re.IGNORECASE)


def _issue(
    severity: str,
    code: str,
    chapter: str,
    stage: str,
    **details: Any,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "chapter": chapter,
        "stage": stage,
        **details,
    }


def _talk_target(text: str) -> str:
    """Return a conservative normalized interlocutor for an explicit talk action."""
    value = " ".join(str(text or "").split()).strip()
    match = _TALK_TARGET_RE.search(value)
    if match is None:
        return ""
    return normalize_text(match.group("target"))


def line_contract_issues(
    *,
    chapter_id: str,
    stage_id: str,
    line_index: int,
    line: dict[str, Any],
) -> list[dict[str, Any]]:
    kind = str(line.get("kind") or "").strip()
    position = " ".join(str(line.get("position") or "").split()).strip()
    text = " ".join(str(line.get("text") or "").split()).strip()
    issues: list[dict[str, Any]] = []

    if _DESTINATION_NEXT_RE.search(text) or _DESTINATION_NEXT_RE.search(position):
        issues.append(
            _issue(
                "hard",
                "destination_suivante_visible",
                chapter_id,
                stage_id,
                line_index=line_index,
                kind=kind,
                position=position,
                text=text,
            )
        )

    if kind == "action" and _MULTI_ACTION_RE.search(text):
        issues.append(
            _issue(
                "review",
                "multiple_real_actions_in_one_line",
                chapter_id,
                stage_id,
                line_index=line_index,
                kind=kind,
                position=position,
                text=text,
            )
        )

    if kind == "action" and _DROP_RE.search(text) and not _PURCHASE_RE.search(text):
        issues.append(
            _issue(
                "review",
                "drop_without_purchase_alternative",
                chapter_id,
                stage_id,
                line_index=line_index,
                kind=kind,
                position=position,
                text=text,
            )
        )

    return issues


def stage_contract_issues(
    *,
    chapter_id: str,
    stage_id: str,
    lines: list[dict[str, Any]],
    resource_names: list[str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    fingerprints: dict[str, list[int]] = defaultdict(list)
    talk_by_position_target: dict[tuple[str, str], list[int]] = defaultdict(list)

    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            continue
        kind = str(line.get("kind") or "").strip()
        position = " ".join(str(line.get("position") or "").split()).strip()
        text = " ".join(str(line.get("text") or "").split()).strip()
        fingerprint = normalize_text(f"{kind} {position} {text}")
        if fingerprint:
            fingerprints[fingerprint].append(index)
        target = _talk_target(text) if kind == "action" and position else ""
        if target:
            talk_by_position_target[(normalize_text(position), target)].append(index)

    for indexes in fingerprints.values():
        if len(indexes) > 1:
            first = lines[indexes[0]]
            issues.append(
                _issue(
                    "review",
                    "duplicate_rendered_instruction",
                    chapter_id,
                    stage_id,
                    line_indexes=indexes,
                    position=str(first.get("position") or ""),
                    text=str(first.get("text") or ""),
                )
            )

    for (position_key, target), indexes in talk_by_position_target.items():
        if len(indexes) > 1:
            issues.append(
                _issue(
                    "review",
                    "repeated_talk_same_position",
                    chapter_id,
                    stage_id,
                    line_indexes=indexes,
                    position=position_key,
                    target=target,
                    texts=[str(lines[index].get("text") or "") for index in indexes],
                )
            )

    normalized_resources = [(name, normalize_text(name)) for name in resource_names]
    for resource_name, resource_key in normalized_resources:
        if not resource_key:
            continue
        preparation_indexes: list[int] = []
        action_indexes: list[int] = []
        for index, line in enumerate(lines):
            if not isinstance(line, dict):
                continue
            text_key = normalize_text(line.get("text"))
            if resource_key not in text_key:
                continue
            kind = str(line.get("kind") or "").strip()
            if kind == "warning" and text_key.startswith("prepare_"):
                preparation_indexes.append(index)
            elif kind == "action":
                action_indexes.append(index)
        if preparation_indexes and action_indexes:
            issues.append(
                _issue(
                    "review",
                    "preparation_repeated_in_now",
                    chapter_id,
                    stage_id,
                    resource=resource_name,
                    preparation_line_indexes=preparation_indexes,
                    action_line_indexes=action_indexes,
                )
            )

    return issues


def audit() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    chapters = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    chapters.sort(key=lambda row: int(row.get("order") or 0))

    service = object.__new__(GuideUltimeManualRuntimeService)
    service.quest_provider = None
    service._quest_name_to_id = {}

    issues: list[dict[str, Any]] = []
    issue_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    stage_count = 0
    line_count = 0

    for meta in chapters:
        chapter_id = str(meta.get("id") or "").strip()
        filename = str(meta.get("file") or "").strip()
        chapter = load_manual_chapter(MANUAL_DIR / filename)
        stages = [stage for stage in chapter.get("stages", []) or [] if isinstance(stage, dict)]
        preparation_schedule = service._chapter_preparation_schedule(chapter, stages)

        for stage_position, stage in enumerate(stages):
            stage_count += 1
            stage_id = str(stage.get("id") or "").strip() or "<sans-id>"
            quest_names = service._stage_quest_names(stage)
            lines = service._stage_lines(
                stage,
                quest_names,
                chapter_preparation=preparation_schedule.get(stage_position, []),
            )
            line_count += len(lines)

            found: list[dict[str, Any]] = []
            for line_index, line in enumerate(lines):
                if isinstance(line, dict):
                    found.extend(
                        line_contract_issues(
                            chapter_id=chapter_id,
                            stage_id=stage_id,
                            line_index=line_index,
                            line=line,
                        )
                    )
            found.extend(
                stage_contract_issues(
                    chapter_id=chapter_id,
                    stage_id=stage_id,
                    lines=lines,
                    resource_names=service._stage_resource_names(chapter, stage),
                )
            )

            for row in found:
                issues.append(row)
                issue_counts[str(row["code"])] += 1
                severity_counts[str(row["severity"])] += 1

    return {
        "schema_version": 1,
        "contract": "phase7e_player_guide",
        "status": "BLOCKED" if severity_counts["hard"] else "REVIEW_REQUIRED" if severity_counts["review"] else "PASS",
        "chapter_count": len(chapters),
        "stage_count": stage_count,
        "line_count": line_count,
        "hard_issue_count": int(severity_counts["hard"]),
        "review_issue_count": int(severity_counts["review"]),
        "issue_counts": dict(sorted(issue_counts.items())),
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Phase 7E du contrat joueur du Guide Ultime.")
    parser.add_argument("--strict-hard", action="store_true")
    parser.add_argument("--strict-review", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    report = audit()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
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
