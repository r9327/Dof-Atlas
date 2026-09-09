from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from app.modules.encyclopedia.providers.quest_provider import QuestProvider
from app.modules.encyclopedia.services.guide_quest_view_model import quest_solution_steps
from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    MANUAL_DIR,
    GuideUltimeManualRuntimeService,
)
from app.modules.encyclopedia.services.guide_ultime_temporal_registry import load_temporal_registry
from app.quest_catalog import normalize_text

MANIFEST = MANUAL_DIR / "manifest_v1.json"

_AUTHORING_TOKENS = (
    "questprovider", "runtime", "route principale", "walkthrough", "rerun",
    "blocker", "cleanup", "pending", "handoff", "merge hook", "merge_hook",
    "persisted_bonta_order", "exactly_one:", "startcriterion", "temporal_registry",
)
_INTERNAL_REF_RE = re.compile(
    r"(?:\b(?:AST|AMK|BNT|PAD|L\d{2})-[A-Z0-9]+\b|\b[a-z0-9_./-]+\.json\b)",
    flags=re.IGNORECASE,
)


def _issue(issues: list[dict[str, Any]], counts: Counter[str], *, severity: str, code: str, source: str, target: str, text: str) -> None:
    issues.append({
        "severity": severity,
        "code": code,
        "source": source,
        "target": target,
        "text": " ".join(str(text or "").split()).strip(),
    })
    counts[code] += 1


def _audit_player_text(issues: list[dict[str, Any]], counts: Counter[str], *, source: str, target: str, text: Any) -> None:
    raw = " ".join(str(text or "").split()).strip()
    if not raw:
        return
    normalized = normalize_text(raw)
    for token in _AUTHORING_TOKENS:
        if normalize_text(token) in normalized:
            _issue(issues, counts, severity="review", code="authoring_language_visible_to_player", source=source, target=target, text=raw)
            break
    if _INTERNAL_REF_RE.search(raw):
        _issue(issues, counts, severity="review", code="internal_reference_visible_to_player", source=source, target=target, text=raw)


def _quest_name_index(provider: QuestProvider) -> tuple[dict[str, int], dict[int, Any]]:
    by_name: dict[str, int] = {}
    by_id: dict[int, Any] = {}
    for quest in provider.list_quests():
        try:
            qid = int(quest.id)
        except (TypeError, ValueError):
            continue
        by_id[qid] = quest
        key = normalize_text(quest.name)
        if key and key not in by_name:
            by_name[key] = qid
    return by_name, by_id


def _canonical_temporal_hooks(manifest: dict[str, Any]) -> dict[str, list[str]]:
    hooks: dict[str, list[str]] = {}
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    for meta in [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]:
        chapter_id = str(meta.get("id") or "").strip()
        filename = str(meta.get("file") or "").strip()
        if not chapter_id or not filename:
            continue
        chapter = load_manual_chapter(MANUAL_DIR / filename)
        for stage in chapter.get("stages", []) or []:
            if not isinstance(stage, dict):
                continue
            stage_id = str(stage.get("id") or "").strip()
            values: list[Any] = []
            if stage.get("temporal_hook") not in (None, "", []):
                values.append(stage.get("temporal_hook"))
            raw_hooks = stage.get("temporal_hooks")
            if isinstance(raw_hooks, list):
                values.extend(raw_hooks)
            elif raw_hooks not in (None, ""):
                values.append(raw_hooks)
            for raw in values:
                hook = str(raw or "").strip()
                if hook:
                    hooks.setdefault(hook, []).append(f"{chapter_id}:{stage_id}")
    return hooks


def audit() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    conditional = [row for row in canonical.get("conditional_routes", []) or [] if isinstance(row, dict)]
    transversal = [row for row in canonical.get("transversal_routes", []) or [] if isinstance(row, dict)]

    issues: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    stats: dict[str, Any] = {
        "conditional_route_count": len(conditional),
        "transversal_route_count": len(transversal),
        "transversal_stage_count": 0,
        "order_option_count": 0,
        "class_branch_count": 0,
        "class_branch_enriched_count": 0,
        "temporal_hook_count": 0,
    }

    provider = QuestProvider()
    by_name, by_id = _quest_name_index(provider)
    catalog_available = bool(by_id)
    service = object.__new__(GuideUltimeManualRuntimeService)
    service.manual_dir = MANUAL_DIR
    service.quest_provider = provider
    service._quest_name_to_id = by_name

    for meta in conditional:
        route_id = str(meta.get("id") or "").strip()
        filename = str(meta.get("file") or "").strip()
        if not route_id or not filename:
            _issue(issues, counts, severity="hard", code="invalid_conditional_route_manifest_entry", source="manifest_v1.json", target=route_id or filename or "<missing>", text=json.dumps(meta, ensure_ascii=False))
            continue

        if route_id == "astrub_class_branches":
            route = json.loads((MANUAL_DIR / filename).read_text(encoding="utf-8"))
            branches = route.get("branches") if isinstance(route.get("branches"), dict) else {}
            stats["class_branch_count"] = len(branches)
            expected = int(meta.get("option_count") or 0)
            if expected and len(branches) != expected:
                _issue(issues, counts, severity="hard", code="class_branch_count_mismatch", source=filename, target=route_id, text=f"expected={expected}, actual={len(branches)}")
            for class_key, branch in branches.items():
                if not isinstance(branch, dict):
                    _issue(issues, counts, severity="hard", code="class_branch_invalid", source=filename, target=str(class_key), text=repr(branch))
                    continue
                quest_name = str(branch.get("quest") or "").strip()
                if not quest_name:
                    _issue(issues, counts, severity="hard", code="class_branch_quest_missing", source=filename, target=str(class_key), text="")
                elif catalog_available:
                    qid = by_name.get(normalize_text(quest_name))
                    if qid is None or qid not in by_id:
                        _issue(issues, counts, severity="hard", code="class_quest_missing_from_catalog", source=filename, target=str(class_key), text=quest_name)
                    else:
                        detail_steps = quest_solution_steps(by_id[qid])
                        objective_count = sum(len(step.objectives) for step in detail_steps)
                        if objective_count:
                            stats["class_branch_enriched_count"] += 1
                        else:
                            _issue(issues, counts, severity="review", code="class_quest_without_enriched_actions", source=filename, target=str(class_key), text=quest_name)
                for prep in branch.get("preparation", []) or []:
                    if isinstance(prep, dict):
                        for value in prep.values():
                            _audit_player_text(issues, counts, source=filename, target=str(class_key), text=value)
            continue

        if route_id.startswith("bonta_order_rank"):
            route = load_manual_chapter(MANUAL_DIR / filename)
            options = route.get("options") if isinstance(route.get("options"), dict) else {}
            expected = int(meta.get("option_count") or 0)
            if expected and len(options) != expected:
                _issue(issues, counts, severity="hard", code="order_option_count_mismatch", source=filename, target=route_id, text=f"expected={expected}, actual={len(options)}")
            for option_key, option in options.items():
                if not isinstance(option, dict):
                    continue
                stats["order_option_count"] += 1
                stage = service._order_option_as_stage({"route": route}, option)
                quest_name = normalize_text(option.get("quest"))
                lines = service._stage_lines(stage, [quest_name] if quest_name else [])
                if not lines:
                    _issue(issues, counts, severity="hard", code="order_option_without_player_lines", source=filename, target=str(option_key), text=str(option.get("quest") or ""))
                for line in lines:
                    if isinstance(line, dict):
                        _audit_player_text(issues, counts, source=filename, target=str(option_key), text=line.get("text"))

    for meta in transversal:
        route_id = str(meta.get("id") or "").strip()
        filename = str(meta.get("file") or "").strip()
        if not route_id or not filename:
            _issue(issues, counts, severity="hard", code="invalid_transversal_route_manifest_entry", source="manifest_v1.json", target=route_id or filename or "<missing>", text=json.dumps(meta, ensure_ascii=False))
            continue
        route = load_manual_chapter(MANUAL_DIR / filename)
        stages = [stage for stage in route.get("stages", []) or [] if isinstance(stage, dict)]
        stats["transversal_stage_count"] += len(stages)
        declared = route.get("macro_stage_count")
        if declared is not None and int(declared) != len(stages):
            _issue(issues, counts, severity="hard", code="transversal_stage_count_mismatch", source=filename, target=route_id, text=f"declared={declared}, actual={len(stages)}")
        for stage in stages:
            stage_id = str(stage.get("id") or "").strip() or "<sans-id>"
            quest_names = service._stage_quest_names(stage)
            lines = service._stage_lines(stage, quest_names)
            if not lines:
                _issue(issues, counts, severity="hard", code="transversal_stage_without_player_lines", source=filename, target=stage_id, text=str(stage.get("title") or ""))
            for line in lines:
                if isinstance(line, dict):
                    _audit_player_text(issues, counts, source=filename, target=stage_id, text=line.get("text"))

    temporal_filename = str(canonical.get("temporal_registry") or "").strip()
    temporal_hooks = _canonical_temporal_hooks(manifest)
    stats["temporal_hook_count"] = len(temporal_hooks)
    temporal = load_temporal_registry(MANUAL_DIR / temporal_filename) if temporal_filename else {}
    temporal_entries = {
        str(row.get("id") or "").strip(): row
        for row in temporal.get("entries", []) or []
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    for hook, consumers in sorted(temporal_hooks.items()):
        entry = temporal_entries.get(hook)
        if entry is None:
            _issue(issues, counts, severity="hard", code="temporal_hook_missing", source=temporal_filename, target=hook, text=", ".join(consumers))
            continue
        rendered = service._temporal_player_instruction(entry)
        if not rendered:
            _issue(issues, counts, severity="hard", code="temporal_hook_without_player_instruction", source=temporal_filename, target=hook, text=", ".join(consumers))
            continue
        _audit_player_text(issues, counts, source=temporal_filename, target=hook, text=rendered)

    hard_count = sum(1 for row in issues if row["severity"] == "hard")
    review_count = sum(1 for row in issues if row["severity"] == "review")
    if hard_count:
        status = "BLOCKED"
    elif not catalog_available:
        status = "CATALOG_UNAVAILABLE"
    elif review_count:
        status = "REVIEW_REQUIRED"
    else:
        status = "CLEAN"
    return {
        "schema_version": 2,
        "status": status,
        "catalog_available": catalog_available,
        "catalog_enrichment_complete": catalog_available,
        **stats,
        "hard_issue_count": hard_count,
        "review_issue_count": review_count,
        "issue_counts": dict(sorted(counts.items())),
        "issues": issues,
        "note": "Audit des sources de support injectables dans le Guide Ultime : la structure reste strictement contrôlée même si le QuestProvider n'est pas matérialisé; l'enrichissement des 19 branches de classe n'est considéré complet que lorsque le catalogue est disponible.",
    }


def main() -> int:
    report = audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["hard_issue_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
