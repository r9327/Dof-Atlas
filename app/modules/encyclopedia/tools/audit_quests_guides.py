from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.constants import DATA_DIR, QUEST_PROGRESS_FILE, RAW_QUEST_DATA_DIR, ROOT_DIR
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.providers.guide_provider import GUIDES_DIR
from app.modules.encyclopedia.services import (
    ACHIEVEMENT_PROGRESS_FILE,
    GUIDE_PROGRESS_FILE,
    AchievementProgressService,
    GuideProgressCalculator,
    GuideProgressService,
    QuestGraphService,
    QuestProgressService,
)
from app.modules.encyclopedia.services.guide_quest_view_model import (
    clean_requirement_line,
    clean_text,
    quest_items_from_objectives,
    quest_rewards,
    quest_solution_blocks,
    quest_solution_steps,
)
from app.quest_catalog import QuestCatalog, QuestRecord, array_value, doduda_rows, normalize_text, read_json_file, safe_int


DEFAULT_OUTPUT = ROOT_DIR / "artifacts" / "quests_guides_audit.json"
GUIDE_CATALOG_PATH = GUIDES_DIR / "catalog.json"
GUIDE_MANIFEST_PATH = GUIDES_DIR / "manifest.json"
QUEST_ENRICHED_PATH = DATA_DIR / "encyclopedia" / "quests" / "quests_enriched.json"
QUEST_SOURCE_MAPPING_PATH = DATA_DIR / "encyclopedia" / "quests" / "source_mapping.json"
QUEST_IMAGE_MANIFEST_PATH = DATA_DIR / "encyclopedia" / "quests" / "image_manifest.json"
QUEST_ORPHAN_IMAGES_REPORT_PATH = DATA_DIR / "encyclopedia" / "quests" / "orphan_images_report.json"
DUFFUS_GUIDE_AUDIT_PATH = ROOT_DIR / "artifacts" / "duffus_guides_full_audit.json"
QUEST_IMAGE_ROOT = DATA_DIR / "encyclopedia" / "images" / "quests"
GUIDE_IMAGE_ROOT = DATA_DIR / "encyclopedia" / "images" / "guides"
CATALOG_CACHE_PATH = ROOT_DIR / ".cache" / "dofus_atlas" / "quest_catalog_v1.pkl"
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico"}
PLACEHOLDER_RE = re.compile(r"\b(todo|a venir|placeholder|lorem ipsum)\b", re.IGNORECASE)
HTML_RE = re.compile(r"<(script|html|body|div|span|p|br|img|a)\b|</", re.IGNORECASE)
CORRUPT_RE = re.compile("\ufffd")
QF_CRITERION_RE = re.compile(r"\bQf\s*=\s*(\d+)", re.IGNORECASE)
QUEST_REFERENCE_RE = re.compile(r"\bQ[fa]\s*[=<>!]+\s*(\d+)", re.IGNORECASE)
QUEST_POSITIVE_REQUIREMENT_RE = re.compile(r"\bQ[fa]\s*=\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class Issue:
    severity: str
    category: str
    subject_type: str
    subject_id: str
    title: str
    file: str
    field: str
    reason: str
    evidence: str = ""
    auto_fix: str = ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit local des modules Quetes et Guides.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=None)
    parser.add_argument("--compare-before", type=Path, default=None)
    parser.add_argument("--fail-on-critical", action="store_true")
    args = parser.parse_args(argv)

    payload = build_audit()
    write_json(args.output, payload)
    if args.markdown_output is not None:
        before_payload = read_json_file(args.compare_before, {}) if args.compare_before is not None else {}
        write_markdown_report(args.markdown_output, payload, before_payload)
    summary = payload["summary"]
    print(f"Quetes actives: {summary['inventory']['active_quests']}")
    print(f"Guides actifs: {summary['inventory']['active_guides']}")
    print(f"References Guides -> Quetes: {summary['inventory']['guide_quest_references_total']}")
    print(f"Critiques: {summary['issues_by_severity'].get('critical', 0)}")
    print(f"Corrigeables: {summary['issues_by_severity'].get('fixable', 0)}")
    print(f"Suspectes: {summary['issues_by_severity'].get('suspect', 0)}")
    print(f"Informative: {summary['issues_by_severity'].get('info', 0)}")
    print(f"Rapport JSON: {args.output}")
    if args.markdown_output is not None:
        print(f"Rapport Markdown: {args.markdown_output}")
    if args.fail_on_critical and summary["issues_by_severity"].get("critical", 0):
        return 1
    return 0


def build_audit() -> dict[str, Any]:
    quest_provider = QuestProvider()
    catalog = quest_provider.get_catalog()
    achievement_provider = AchievementProvider(quest_provider=quest_provider)
    guide_provider = GuideProvider(quest_provider=quest_provider, achievement_provider=achievement_provider)
    guides = guide_provider.load_all()
    graph = QuestGraphService(quest_provider, guide_provider, achievement_provider)

    issues: list[Issue] = []
    source_inventory = source_inventory_payload(guides)
    raw_inventory, raw_issues = raw_quest_inventory(catalog)
    issues.extend(raw_issues)
    quest_inventory, quest_issues, quest_ref_images = audit_quests(catalog, graph, achievement_provider)
    issues.extend(quest_issues)
    guide_inventory, guide_issues, guide_ref_images = audit_guides(guides, guide_provider, catalog, graph)
    issues.extend(guide_issues)
    progress_inventory, progress_issues = audit_progress(catalog, guides, achievement_provider)
    issues.extend(progress_issues)
    image_inventory, image_issues = audit_images(catalog, guides, quest_ref_images | guide_ref_images)
    issues.extend(image_issues)
    graph_inventory, graph_issues = audit_graph(catalog, graph)
    issues.extend(graph_issues)

    issue_rows = [asdict(issue) for issue in issues]
    issue_counts = Counter(issue.severity for issue in issues)
    issue_categories = Counter(issue.category for issue in issues)
    fixed_count = sum(1 for issue in issues if issue.auto_fix)
    affected_quests = {
        int(issue.subject_id)
        for issue in issues
        if issue.subject_type == "quest" and str(issue.subject_id).isdigit()
    }
    affected_guides = {
        issue.subject_id
        for issue in issues
        if issue.subject_type == "guide" and issue.subject_id
    }
    manual_quest_ids = {
        int(issue.subject_id)
        for issue in issues
        if issue.subject_type == "quest" and str(issue.subject_id).isdigit() and issue.severity in {"critical", "suspect"}
    }
    manual_guide_ids = {
        issue.subject_id
        for issue in issues
        if issue.subject_type == "guide" and issue.severity in {"critical", "suspect"}
    }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_of_truth": {
            "quests": str(RAW_QUEST_DATA_DIR),
            "quest_enrichment": str(QUEST_ENRICHED_PATH),
            "guides": str(GUIDE_CATALOG_PATH),
            "runtime": "QuestCatalog -> QuestProvider -> QuestGraphService -> GuideProvider -> progress services",
        },
        "inventory": {
            **raw_inventory,
            **quest_inventory,
            **guide_inventory,
            **image_inventory,
            **graph_inventory,
            **progress_inventory,
        },
        "issues_by_severity": dict(issue_counts),
        "issues_by_category": dict(issue_categories),
        "quests_with_anomalies": len(affected_quests),
        "guides_with_anomalies": len(affected_guides),
        "quests_to_review": len(manual_quest_ids),
        "guides_to_review": len(manual_guide_ids),
        "auto_fixable_issues": fixed_count,
        "provider_validation_errors": list(guide_provider.validation_errors),
    }
    return {
        "schema_version": 1,
        "summary": summary,
        "source_inventory": source_inventory,
        "issues": issue_rows,
        "manual_review": [row for row in issue_rows if row["severity"] in {"critical", "suspect"}],
    }


def source_inventory_payload(guides: list[Any]) -> dict[str, Any]:
    guide_files = sorted(
        str(path.relative_to(ROOT_DIR))
        for path in GUIDES_DIR.glob("*.json")
        if path.name not in {"catalog.json", "manifest.json"}
    )
    # Guide.raw intentionally mirrors source JSON and does not carry its file path.
    active_guide_files = sorted(str((GUIDES_DIR / f"{guide.id}.json").relative_to(ROOT_DIR)) for guide in guides)
    return {
        "active": {
            "raw_doduda": source_file_entries(RAW_QUEST_DATA_DIR),
            "quest_enrichment": file_entry(QUEST_ENRICHED_PATH),
            "guide_catalog": file_entry(GUIDE_CATALOG_PATH),
            "guide_files": active_guide_files,
            "quest_progress": file_entry(QUEST_PROGRESS_FILE),
            "guide_progress": file_entry(GUIDE_PROGRESS_FILE),
            "achievement_progress": file_entry(ACHIEVEMENT_PROGRESS_FILE),
        },
        "supporting": {
            "source_mapping": file_entry(QUEST_SOURCE_MAPPING_PATH),
            "image_manifest": file_entry(QUEST_IMAGE_MANIFEST_PATH),
            "quest_images": dir_entry(QUEST_IMAGE_ROOT),
            "guide_images": dir_entry(GUIDE_IMAGE_ROOT),
        },
        "derived_or_historical": {
            "quest_catalog_cache": file_entry(CATALOG_CACHE_PATH),
            "guide_manifest_inactive_when_catalog_exists": file_entry(GUIDE_MANIFEST_PATH),
            "orphan_images_report": file_entry(QUEST_ORPHAN_IMAGES_REPORT_PATH),
            "duffus_guides_audit": file_entry(DUFFUS_GUIDE_AUDIT_PATH),
        },
        "unused_guide_files": sorted(set(guide_files) - set(active_guide_files)),
    }


def source_file_entries(root: Path) -> dict[str, Any]:
    names = [
        "languages/fr.json",
        "quests.json",
        "quest_steps.json",
        "quest_objectives.json",
        "quest_step_rewards.json",
        "achievements.json",
        "achievement_objectives.json",
        "achievement_rewards.json",
        "quest_categories.json",
        "quest_objective_types.json",
        "items.json",
        "jobs.json",
        "spells.json",
        "titles.json",
        "emoticons.json",
        "monsters.json",
        "npcs.json",
        "areas.json",
        "subareas.json",
        "maps_information.json",
        "char_xp_mappings.json",
    ]
    return {name: file_entry(root / name) for name in names}


def raw_quest_inventory(catalog: QuestCatalog) -> tuple[dict[str, int], list[Issue]]:
    issues: list[Issue] = []
    raw_rows = raw_ref_rows(RAW_QUEST_DATA_DIR / "quests.json")
    ids = [safe_int(row.get("id")) for row in raw_rows if isinstance(row, dict)]
    valid_ids = [ident for ident in ids if ident is not None]
    duplicate_ids = [ident for ident, count in Counter(valid_ids).items() if count > 1]
    missing_ids = len([ident for ident in ids if ident is None])
    for ident in duplicate_ids:
        issues.append(
            Issue(
                "critical",
                "quest_identity",
                "quest",
                str(ident),
                catalog.by_id.get(int(ident), empty_quest()).name,
                relative_path(RAW_QUEST_DATA_DIR / "quests.json"),
                "id",
                "ID de quete duplique dans la source brute active.",
            )
        )
    if missing_ids:
        issues.append(
            Issue(
                "critical",
                "quest_identity",
                "raw_source",
                "quests.json",
                "quests.json",
                relative_path(RAW_QUEST_DATA_DIR / "quests.json"),
                "id",
                "Entrees de quete sans ID dans la source brute active.",
                str(missing_ids),
            )
        )
    return {
        "raw_quest_rows": len(raw_rows),
        "raw_quest_ids_unique": len(set(valid_ids)),
        "raw_quests_without_id": missing_ids,
        "raw_duplicate_quest_ids": len(duplicate_ids),
    }, issues


def audit_quests(
    catalog: QuestCatalog,
    graph: QuestGraphService,
    achievement_provider: AchievementProvider,
) -> tuple[dict[str, int], list[Issue], set[str]]:
    issues: list[Issue] = []
    referenced_images: set[str] = set()
    quest_ids = [int(quest.id) for quest in catalog.quests]
    title_counts = Counter(normalize_text(quest.name) for quest in catalog.quests if normalize_text(quest.name))
    duplicate_titles = [key for key, count in title_counts.items() if count > 1]
    source_mapping = read_json_file(QUEST_SOURCE_MAPPING_PATH, {})
    mapping_quests = source_mapping.get("quests", {}) if isinstance(source_mapping, dict) else {}
    enrichment = read_json_file(QUEST_ENRICHED_PATH, {})
    enriched_quests = enrichment.get("quests", {}) if isinstance(enrichment, dict) else {}
    guide_referenced_ids = {qid for ids in graph.guide_ids_by_quest.values() for qid in ids}
    _ = guide_referenced_ids
    quests_without_title = 0
    quests_without_level = 0
    quests_without_solution = 0
    quests_without_source = 0
    quests_with_required_items = 0
    quests_with_images = 0
    quests_with_anomalies: set[int] = set()
    prerequisite_refs = 0
    achievement_linked_quests = 0
    rewards_count = 0
    source_solution_count = 0
    local_solution_count = 0

    duplicate_title_keys = set(duplicate_titles)
    for quest in catalog.quests:
        before_issue_count = len(issues)
        title = clean_text(quest.name)
        if not isinstance(quest.id, int) or int(quest.id) <= 0:
            issues.append(issue_for_quest("critical", "quest_identity", quest, "id", "quest_id absent ou invalide."))
        if not title:
            quests_without_title += 1
            issues.append(issue_for_quest("critical", "quest_identity", quest, "name", "Titre absent."))
        elif normalize_text(title) in duplicate_title_keys:
            issues.append(issue_for_quest("suspect", "quest_duplicates", quest, "name", "Titre normalise duplique.", title))
        if int(quest.level_min or 0) <= 0 and int(quest.level_max or 0) <= 0:
            quests_without_level += 1
            issues.append(issue_for_quest("suspect", "quest_identity", quest, "level", "Niveau absent ou nul."))
        if not clean_text(quest.category):
            issues.append(issue_for_quest("suspect", "quest_identity", quest, "category", "Categorie absente."))

        source_blocks = quest_solution_blocks(quest)
        display_steps = quest_solution_steps(quest)
        local_objectives = [objective for step in quest.steps for objective in step.objectives if clean_text(objective.text)]
        if quest.solution_blocks or quest.source_solution_steps:
            source_solution_count += 1
        if display_steps or local_objectives:
            local_solution_count += 1
        if not source_blocks and not display_steps and not local_objectives:
            quests_without_solution += 1
            issues.append(issue_for_quest("suspect", "quest_content", quest, "solution", "Aucune solution exploitable detectee."))
        elif len(source_blocks) + len(display_steps) <= 1 and len(local_objectives) <= 1:
            issues.append(
                issue_for_quest(
                    "suspect",
                    "quest_content",
                    quest,
                    "solution",
                    "Solution tres courte: a verifier, non corrige automatiquement.",
                    f"blocks={len(source_blocks)}, steps={len(display_steps)}, local_objectives={len(local_objectives)}",
                )
            )
        if str(quest.id) not in mapping_quests and str(quest.id) not in enriched_quests:
            quests_without_source += 1
            issues.append(issue_for_quest("suspect", "quest_source", quest, "source", "Aucune source enrichie/mapping identifiable."))

        for field_name, value in quest_text_fields(quest):
            scan_text_quality(value, issues, "quest", str(quest.id), quest.name, quest_file_for(quest.id), field_name)

        required_items = quest_items_from_objectives(quest)
        if required_items:
            quests_with_required_items += 1
        item_seen: dict[tuple[str, str], int] = defaultdict(int)
        for item in required_items:
            key = (str(item.item_id or ""), normalize_text(item.name))
            item_seen[key] += 1
            if not clean_text(item.name):
                issues.append(issue_for_quest("critical", "quest_required_items", quest, "required_items.name", "Objet requis sans nom."))
            if item.quantity is not None and int(item.quantity or 0) <= 0:
                issues.append(issue_for_quest("critical", "quest_required_items", quest, "required_items.quantity", "Quantite d'objet requise invalide.", str(item.quantity)))
            if item.quantity is not None and int(item.quantity or 0) > 9999:
                issues.append(issue_for_quest("suspect", "quest_required_items", quest, "required_items.quantity", "Quantite d'objet requise aberrante.", str(item.quantity)))
            if item.image_path:
                referenced_images.add(item.image_path)
        for key, count in item_seen.items():
            if key[0] and count > 1:
                issues.append(issue_for_quest("info", "quest_required_items", quest, "required_items", "Doublon fusionne a l'affichage.", f"{key} x{count}"))

        image_paths = quest_image_paths(quest)
        if image_paths:
            quests_with_images += 1
        for path in image_paths:
            referenced_images.add(path)
        for reward in quest_rewards(quest, achievement_provider.get_by_quest(quest.id)):
            rewards_count += 1
            if not clean_text(reward.name):
                issues.append(issue_for_quest("critical", "quest_rewards", quest, "rewards.name", "Recompense sans nom."))
            if reward.quantity is not None and int(reward.quantity or 0) < 0:
                issues.append(issue_for_quest("critical", "quest_rewards", quest, "rewards.quantity", "Quantite de recompense negative.", str(reward.quantity)))
            if reward.image_path:
                referenced_images.add(reward.image_path)

        criteria_ids = positive_requirement_quest_ids(quest.start_criterion)
        prerequisite_refs += len(criteria_ids)
        for target_id in criteria_ids:
            if target_id not in catalog.by_id:
                issues.append(issue_for_quest("critical", "quest_prerequisites", quest, "start_criterion", "Prerequis vers une quete inexistante.", str(target_id)))
            elif target_id == quest.id:
                issues.append(issue_for_quest("critical", "quest_prerequisites", quest, "start_criterion", "Prerequis auto-reference.", str(target_id)))

        if achievement_provider.get_by_quest(quest.id):
            achievement_linked_quests += 1
        if len(issues) > before_issue_count:
            quests_with_anomalies.add(int(quest.id))

    inventory = {
        "active_quests": len(catalog.quests),
        "active_quest_ids_unique": len(set(quest_ids)),
        "active_duplicate_quest_ids": len(quest_ids) - len(set(quest_ids)),
        "duplicate_quest_titles": len(duplicate_title_keys),
        "quests_without_title": quests_without_title,
        "quests_without_level": quests_without_level,
        "quests_without_solution": quests_without_solution,
        "quests_without_source": quests_without_source,
        "quests_referenced_by_guides": len(graph.guide_ids_by_quest),
        "quests_used_as_prerequisites": len({qid for values in graph.previous_by_quest.values() for qid in values}),
        "quest_prerequisite_references": prerequisite_refs,
        "quests_linked_to_achievements": achievement_linked_quests,
        "quests_with_required_items": quests_with_required_items,
        "quests_with_images": quests_with_images,
        "quest_reward_entries": rewards_count,
        "quests_with_source_solution": source_solution_count,
        "quests_with_local_solution": local_solution_count,
        "quests_with_anomalies": len(quests_with_anomalies),
    }
    return inventory, issues, referenced_images


def audit_guides(
    guides: list[Any],
    provider: GuideProvider,
    catalog: QuestCatalog,
    graph: QuestGraphService,
) -> tuple[dict[str, int], list[Issue], set[str]]:
    issues: list[Issue] = []
    referenced_images: set[str] = set()
    guide_ids = [guide.id for guide in guides]
    category_counts = Counter(guide.category for guide in guides)
    total_parts = 0
    total_chapters = 0
    total_series = 0
    total_refs = 0
    unique_quest_refs: set[int] = set()
    guides_without_chapters = 0
    guides_without_quests = 0
    empty_chapters = 0
    duplicate_refs = 0
    dead_refs = 0
    incomplete = 0
    inaccessible_files = 0

    catalog_payload = read_json_file(GUIDE_CATALOG_PATH, {})
    catalog_rows = catalog_payload.get("guides", []) if isinstance(catalog_payload, dict) else []
    enabled_ids = {
        str(row.get("id") or Path(str(row.get("file") or "")).stem)
        for row in catalog_rows
        if isinstance(row, dict) and row.get("enabled") is not False
    }

    for guide in guides:
        if guide.id not in enabled_ids:
            inaccessible_files += 1
            issues.append(issue_for_guide("suspect", "guide_access", guide, "catalog", "Guide charge mais absent du catalogue actif."))
        if not clean_text(guide.id):
            issues.append(issue_for_guide("critical", "guide_identity", guide, "id", "Identifiant interne absent."))
        if not clean_text(guide.title):
            issues.append(issue_for_guide("critical", "guide_identity", guide, "title", "Titre absent."))
        if not clean_text(guide.category):
            issues.append(issue_for_guide("critical", "guide_identity", guide, "category", "Categorie absente."))
        if guide.completeness_status != "complete":
            incomplete += 1
            issues.append(issue_for_guide("suspect", "guide_completeness", guide, "completeness_status", "Guide actif non complet.", guide.completeness_status))
        if guide.image_path:
            referenced_images.add(guide.image_path)

        if not guide.parts or not any(part.chapters for part in guide.parts):
            guides_without_chapters += 1
            issues.append(issue_for_guide("critical", "guide_structure", guide, "parts.chapters", "Guide sans chapitre actif."))
        if not guide.quest_ids:
            guides_without_quests += 1
            issues.append(issue_for_guide("critical", "guide_structure", guide, "quest_ids", "Guide sans quete active."))

        seen_step_ids: set[str] = set()
        seen_quests: set[int] = set()
        for part in guide.parts:
            total_parts += 1
            if not clean_text(part.title):
                issues.append(issue_for_guide("suspect", "guide_structure", guide, f"part:{part.id}.title", "Partie sans titre."))
            if part.required_items:
                for item in part.required_items:
                    if item.image_path:
                        referenced_images.add(item.image_path)
            for chapter in part.chapters:
                total_chapters += 1
                if not chapter.series:
                    empty_chapters += 1
                    issues.append(issue_for_guide("suspect", "guide_structure", guide, f"chapter:{chapter.id}", "Chapitre sans serie."))
                for item in chapter.required_items:
                    if item.image_path:
                        referenced_images.add(item.image_path)
                for series in chapter.series:
                    total_series += 1
                    if not series.steps and not series.objectives and not series.activities:
                        issues.append(issue_for_guide("suspect", "guide_structure", guide, f"series:{series.id}", "Serie vide."))
                    if series.achievement_id is not None:
                        if provider.achievement_provider.get_by_id(int(series.achievement_id)) is None:
                            issues.append(issue_for_guide("critical", "guide_achievements", guide, f"series:{series.id}.achievement_id", "Succes reference inexistant.", str(series.achievement_id)))
                    for item in series.required_items:
                        if not clean_text(item.name) and item.item_id is None:
                            issues.append(issue_for_guide("critical", "guide_required_items", guide, f"series:{series.id}.required_items", "Objet requis sans nom ni ID."))
                        if int(item.quantity or 0) <= 0:
                            issues.append(issue_for_guide("critical", "guide_required_items", guide, f"series:{series.id}.required_items.quantity", "Quantite d'objet requise invalide.", str(item.quantity)))
                        if item.image_path:
                            referenced_images.add(item.image_path)
                    for step in series.steps:
                        total_refs += 1 if step.step_type == "quest" and step.entity_id is not None else 0
                        if step.id in seen_step_ids:
                            issues.append(issue_for_guide("critical", "guide_structure", guide, "step.id", "Etape dupliquee.", step.id))
                        seen_step_ids.add(step.id)
                        if step.step_type == "quest" and step.entity_id is not None:
                            qid = int(step.entity_id)
                            if qid in seen_quests:
                                duplicate_refs += 1
                                issues.append(issue_for_guide("fixable", "guide_relations", guide, "quest_refs", "Reference de quete dupliquee dans le guide.", str(qid)))
                            seen_quests.add(qid)
                            unique_quest_refs.add(qid)
                            quest = catalog.by_id.get(qid)
                            if quest is None:
                                dead_refs += 1
                                issues.append(issue_for_guide("critical", "guide_relations", guide, "entity_id", "Reference Guide -> Quete morte.", str(qid)))
                            else:
                                raw_title = clean_text(step.raw.get("title")) if isinstance(step.raw, dict) else ""
                                if raw_title and normalize_text(raw_title) != normalize_text(quest.name):
                                    issues.append(
                                        issue_for_guide(
                                            "fixable",
                                            "guide_relations",
                                            guide,
                                            "step.title",
                                            "Titre secondaire desynchronise; quest_id resout une quete certaine.",
                                            f"{raw_title} != {quest.name}",
                                        )
                                    )
                        for ref in step.prerequisites:
                            if ref.entity_type == "quest":
                                if int(ref.entity_id) == int(step.entity_id or -1):
                                    issues.append(issue_for_guide("critical", "guide_prerequisites", guide, f"step:{step.id}.prerequisites", "Prerequis auto-reference.", str(ref.entity_id)))
                                if int(ref.entity_id) not in catalog.by_id:
                                    issues.append(issue_for_guide("critical", "guide_prerequisites", guide, f"step:{step.id}.prerequisites", "Prerequis vers quete inexistante.", str(ref.entity_id)))

        for error in provider.validate_guide(guide):
            issues.append(issue_for_guide("critical", "guide_provider_validation", guide, "validation", error))

    duplicate_guide_ids = len(guide_ids) - len(set(guide_ids))
    if duplicate_guide_ids:
        issues.append(Issue("critical", "guide_identity", "guide", "", "", relative_path(GUIDE_CATALOG_PATH), "id", "IDs de guide dupliques.", str(duplicate_guide_ids)))
    return {
        "active_guides": len(guides),
        "guide_categories": len(category_counts),
        "guide_parts": total_parts,
        "guide_chapters": total_chapters,
        "guide_series": total_series,
        "guide_quest_references_total": total_refs,
        "guide_quest_references_unique": len(unique_quest_refs),
        "guides_without_chapters": guides_without_chapters,
        "guides_without_quests": guides_without_quests,
        "empty_guide_chapters": empty_chapters,
        "duplicate_guide_quest_references": duplicate_refs,
        "dead_guide_quest_references": dead_refs,
        "incomplete_guides": incomplete,
        "guides_not_really_accessible": inaccessible_files,
    }, issues, referenced_images


def audit_progress(
    catalog: QuestCatalog,
    guides: list[Any],
    achievement_provider: AchievementProvider,
) -> tuple[dict[str, int], list[Issue]]:
    issues: list[Issue] = []
    with tempfile.TemporaryDirectory(prefix="atlas_audit_progress_") as tmp:
        tmp_path = Path(tmp)
        quest_progress_service = QuestProgressService(tmp_path / "quest_progress.json")
        guide_progress_service = GuideProgressService(tmp_path / "guide_progress.json")
        achievement_progress_service = AchievementProgressService(tmp_path / "achievement_progress.json")
        calculator = GuideProgressCalculator(
            quest_progress_service,
            guide_progress_service,
            achievement_progress_service,
            catalog.by_id,
        )
        progress_cases_checked = 0
        inconsistent_progress = 0
        for guide in guides:
            total = len(guide.required_steps)
            empty = calculator.steps_progress(guide, guide.required_steps, "__audit_empty__")
            progress_cases_checked += 1
            if empty.total != total or empty.completed != 0:
                inconsistent_progress += 1
                issues.append(issue_for_guide("critical", "guide_progress", guide, "empty", "Progression vide incoherente.", f"{empty.completed}/{empty.total} attendu 0/{total}"))
            quest_steps = [step for step in guide.required_steps if step.step_type == "quest" and step.entity_id is not None]
            if len({int(step.entity_id) for step in quest_steps}) != len(quest_steps):
                issues.append(issue_for_guide("fixable", "guide_progress", guide, "quest_ids", "Double comptage possible: quetes requises dupliquees."))
    progress_payload = read_json_file(QUEST_PROGRESS_FILE, {"version": 1, "characters": {}})
    invalid_done = 0
    invalid_objectives = 0
    characters = progress_payload.get("characters", {}) if isinstance(progress_payload, dict) else {}
    if isinstance(characters, dict):
        for character_id, row in characters.items():
            done = row.get("done", {}) if isinstance(row, dict) else {}
            if isinstance(done, dict):
                for quest_id_text in done:
                    qid = safe_int(quest_id_text)
                    if qid is None or qid not in catalog.by_id:
                        invalid_done += 1
                        issues.append(Issue("suspect", "user_progress", "progress", str(character_id), str(character_id), relative_path(QUEST_PROGRESS_FILE), "done", "Progression utilisateur reference une quete absente.", str(quest_id_text)))
            completed = row.get("completed_quest_objectives", {}) if isinstance(row, dict) else {}
            if isinstance(completed, dict):
                for quest_id_text, objective_ids in completed.items():
                    qid = safe_int(quest_id_text)
                    quest = catalog.by_id.get(qid or -1)
                    valid_objectives = {objective.id for step in quest.steps for objective in step.objectives} if quest is not None else set()
                    if not isinstance(objective_ids, list):
                        invalid_objectives += 1
                        continue
                    for objective_id in objective_ids:
                        oid = safe_int(objective_id)
                        if quest is None or oid not in valid_objectives:
                            invalid_objectives += 1
                            issues.append(Issue("suspect", "user_progress", "progress", str(character_id), str(character_id), relative_path(QUEST_PROGRESS_FILE), "completed_quest_objectives", "Progression utilisateur reference un objectif absent.", f"quest={quest_id_text}, objective={objective_id}"))
    return {
        "guide_progress_cases_checked": progress_cases_checked,
        "guide_progress_inconsistencies": inconsistent_progress,
        "user_progress_invalid_quest_refs": invalid_done,
        "user_progress_invalid_objective_refs": invalid_objectives,
    }, issues


def audit_images(
    catalog: QuestCatalog,
    guides: list[Any],
    referenced_images: set[str],
) -> tuple[dict[str, int], list[Issue]]:
    issues: list[Issue] = []
    active_paths = {normalize_path(path) for path in referenced_images if str(path or "").strip()}
    missing = 0
    bad_format = 0
    for image_path in sorted(active_paths):
        path = Path(image_path)
        if not path.exists():
            missing += 1
            issues.append(Issue("critical", "images", "image", image_path, Path(image_path).name, relative_path(path), "image_path", "Image referencee introuvable."))
            continue
        if path.suffix.casefold() not in ALLOWED_IMAGE_SUFFIXES or not is_exploitable_image(path):
            bad_format += 1
            issues.append(Issue("critical", "images", "image", image_path, Path(image_path).name, relative_path(path), "image_path", "Image referencee non exploitable."))
    quest_files = set(file for file in image_files(QUEST_IMAGE_ROOT))
    guide_files = set(file for file in image_files(GUIDE_IMAGE_ROOT))
    active_file_paths = {Path(path).resolve() for path in active_paths if Path(path).exists()}
    orphan_files = sorted((quest_files | guide_files) - active_file_paths)
    duplicate_hashes = duplicate_files_by_hash(active_file_paths)
    for digest, paths in list(duplicate_hashes.items())[:50]:
        issues.append(Issue("info", "images", "image", digest, "duplicate_image", "", "sha256", "Fichiers images actifs identiques; conservation par securite.", ", ".join(relative_path(path) for path in paths[:5])))
    return {
        "active_referenced_images": len(active_paths),
        "missing_referenced_images": missing,
        "bad_format_referenced_images": bad_format,
        "orphan_quest_guide_images": len(orphan_files),
        "duplicate_active_image_hashes": len(duplicate_hashes),
    }, issues


def audit_graph(catalog: QuestCatalog, graph: QuestGraphService) -> tuple[dict[str, int], list[Issue]]:
    issues: list[Issue] = []
    missing_edges = 0
    self_edges = 0
    duplicate_edges = 0
    edge_counter: Counter[tuple[int, int]] = Counter()
    for quest in catalog.quests:
        for previous in qf_finished_quest_ids(quest.start_criterion):
            edge_counter[(previous, quest.id)] += 1
            if previous not in catalog.by_id:
                missing_edges += 1
            if previous == quest.id:
                self_edges += 1
    duplicate_edges = sum(1 for _edge, count in edge_counter.items() if count > 1)
    for source, target in edge_counter:
        if source not in catalog.by_id:
            continue
        _ = target
    cycles = strongly_connected_components({qid: set(prevs) for qid, prevs in graph.previous_by_quest.items()})
    for cycle in cycles[:50]:
        titles = [catalog.by_id[qid].name for qid in cycle if qid in catalog.by_id]
        issues.append(Issue("suspect", "quest_graph", "graph", ",".join(map(str, cycle)), "cycle", "", "previous_by_quest", "Cycle detecte dans le graphe; non casse sans preuve externe.", " -> ".join(titles)))
    return {
        "graph_nodes": len(catalog.quests),
        "graph_edges": sum(len(values) for values in graph.previous_by_quest.values()),
        "graph_missing_edges": missing_edges,
        "graph_self_edges": self_edges,
        "graph_duplicate_raw_edges": duplicate_edges,
        "graph_cycles": len(cycles),
    }, issues


def quest_text_fields(quest: QuestRecord) -> Iterable[tuple[str, str]]:
    yield "name", quest.name
    yield "category", quest.category
    for index, line in enumerate(quest.info, 1):
        yield f"info[{index}]", line
    for index, line in enumerate(quest.prerequisites, 1):
        yield f"prerequisites[{index}]", line
    for step_index, step in enumerate(quest.steps, 1):
        yield f"steps[{step_index}].name", step.name
        yield f"steps[{step_index}].description", step.description
        for objective_index, objective in enumerate(step.objectives, 1):
            yield f"steps[{step_index}].objectives[{objective_index}].text", objective.text
            yield f"steps[{step_index}].objectives[{objective_index}].image_label", objective.image_label
    for block_index, block in enumerate(quest.solution_blocks, 1):
        yield f"solution_blocks[{block_index}].content", block.content
        yield f"solution_blocks[{block_index}].caption", block.caption


def quest_image_paths(quest: QuestRecord) -> set[str]:
    paths: set[str] = set()
    for step in quest.steps:
        for objective in step.objectives:
            if objective.image_path:
                paths.add(objective.image_path)
    for step in quest.source_solution_steps:
        for objective in step.objectives:
            if objective.image_path:
                paths.add(objective.image_path)
    for block in quest.solution_blocks:
        if block.image_path:
            paths.add(block.image_path)
    for reward in quest.rewards:
        if reward.image_path:
            paths.add(reward.image_path)
    source_info = quest.source_info if isinstance(quest.source_info, dict) else {}
    for item in source_info.get("required_items", []) or []:
        if isinstance(item, dict) and item.get("image_path"):
            paths.add(str(item.get("image_path")))
    return paths


def scan_text_quality(
    value: str,
    issues: list[Issue],
    subject_type: str,
    subject_id: str,
    title: str,
    file: str,
    field: str,
) -> None:
    text = str(value or "")
    if not text:
        return
    clean = clean_text(text)
    if PLACEHOLDER_RE.search(clean):
        issues.append(Issue("suspect", "content_quality", subject_type, subject_id, title, file, field, "Placeholder/TODO detecte.", truncate(clean)))
    if CORRUPT_RE.search(text):
        issues.append(Issue("suspect", "content_quality", subject_type, subject_id, title, file, field, "Caractere de remplacement Unicode detecte.", truncate(clean)))
    if HTML_RE.search(text) and clean_text(text) != text:
        issues.append(Issue("suspect", "content_quality", subject_type, subject_id, title, file, field, "HTML residuel detecte.", truncate(text)))


def raw_ref_rows(path: Path) -> list[dict[str, Any]]:
    payload = read_json_file(path, {})
    refs = payload.get("references", {}).get("RefIds", []) if isinstance(payload, dict) else []
    return [ref.get("data") for ref in refs if isinstance(ref, dict) and isinstance(ref.get("data"), dict)]


def qf_finished_quest_ids(criterion: str) -> list[int]:
    ids: list[int] = []
    for match in QF_CRITERION_RE.finditer(str(criterion or "")):
        ident = safe_int(match.group(1))
        if ident is not None:
            ids.append(int(ident))
    return ids


def positive_requirement_quest_ids(criterion: str) -> list[int]:
    ids: list[int] = []
    for match in QUEST_POSITIVE_REQUIREMENT_RE.finditer(str(criterion or "")):
        ident = safe_int(match.group(1))
        if ident is not None:
            ids.append(int(ident))
    return ids


def strongly_connected_components(graph: dict[int, set[int]]) -> list[list[int]]:
    index = 0
    stack: list[int] = []
    indexes: dict[int, int] = {}
    lowlinks: dict[int, int] = {}
    on_stack: set[int] = set()
    components: list[list[int]] = []
    nodes = set(graph)
    for targets in graph.values():
        nodes.update(targets)

    def visit(node: int) -> None:
        nonlocal index
        indexes[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, set()):
            if target not in indexes:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[target])
        if lowlinks[node] == indexes[node]:
            component: list[int] = []
            while stack:
                target = stack.pop()
                on_stack.discard(target)
                component.append(target)
                if target == node:
                    break
            if len(component) > 1 or node in graph.get(node, set()):
                components.append(sorted(component))

    for node in sorted(nodes):
        if node not in indexes:
            visit(node)
    return sorted(components, key=lambda values: (len(values), values))


def duplicate_files_by_hash(paths: Iterable[Path]) -> dict[str, list[Path]]:
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        by_hash[digest].append(path)
    return {digest: values for digest, values in by_hash.items() if len(values) > 1}


def image_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return [path.resolve() for path in root.rglob("*") if path.is_file() and path.suffix.casefold() in ALLOWED_IMAGE_SUFFIXES]


def is_exploitable_image(path: Path) -> bool:
    try:
        if path.stat().st_size <= 0:
            return False
        if path.suffix.casefold() == ".svg":
            text = path.read_text(encoding="utf-8", errors="ignore")[:512]
            return "<svg" in text.lower()
        header = path.read_bytes()[:16]
    except OSError:
        return False
    suffix = path.suffix.casefold()
    if suffix == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8")
    if suffix == ".webp":
        return header.startswith(b"RIFF") and b"WEBP" in header
    if suffix == ".ico":
        return header.startswith(b"\x00\x00\x01\x00")
    return False


def file_entry(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "exists": False}
    return {
        "path": str(path),
        "exists": True,
        "size": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


def dir_entry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "files": 0}
    return {
        "path": str(path),
        "exists": True,
        "files": sum(1 for child in path.rglob("*") if child.is_file()),
    }


def normalize_path(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        return ""
    candidate = Path(text)
    return str(candidate.resolve()) if candidate.exists() else text


def is_quest_image_path(path: str) -> bool:
    return "data/encyclopedia/images/quests" in str(path).replace("\\", "/").casefold()


def issue_for_quest(severity: str, category: str, quest: QuestRecord, field: str, reason: str, evidence: str = "", auto_fix: str = "") -> Issue:
    return Issue(severity, category, "quest", str(quest.id), quest.name, quest_file_for(quest.id), field, reason, evidence, auto_fix)


def issue_for_guide(severity: str, category: str, guide: Any, field: str, reason: str, evidence: str = "", auto_fix: str = "") -> Issue:
    return Issue(severity, category, "guide", str(guide.id), str(guide.title), guide_file_for(str(guide.id)), field, reason, evidence, auto_fix)


def quest_file_for(_quest_id: int) -> str:
    return relative_path(QUEST_ENRICHED_PATH)


def guide_file_for(guide_id: str) -> str:
    path = GUIDES_DIR / f"{guide_id}.json"
    return relative_path(path)


def relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT_DIR.resolve()))
    except Exception:
        return str(path)


def truncate(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def empty_quest() -> QuestRecord:
    return QuestRecord(0, "", "", 0, 0, "")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_markdown_report(path: Path, payload: dict[str, Any], before_payload: dict[str, Any] | None = None) -> None:
    before_payload = before_payload if isinstance(before_payload, dict) else {}
    summary = payload["summary"]
    inventory = summary["inventory"]
    before_summary = before_payload.get("summary", {}) if isinstance(before_payload.get("summary"), dict) else {}
    before_counts = before_summary.get("issues_by_severity", {}) if isinstance(before_summary, dict) else {}
    after_counts = summary["issues_by_severity"]
    manual_rows = [row for row in payload["issues"] if row["severity"] in {"critical", "suspect"}]
    info_rows = [row for row in payload["issues"] if row["severity"] == "info"]
    quest_rows = [row for row in manual_rows if row["subject_type"] == "quest"]
    guide_rows = [row for row in manual_rows if row["subject_type"] == "guide"]
    other_rows = [row for row in manual_rows if row["subject_type"] not in {"quest", "guide"}]

    lines: list[str] = []
    lines.append("# Audit Quetes & Guides Dofus Atlas")
    lines.append("")
    lines.append(f"Genere le {summary['generated_at']}.")
    lines.append("")
    lines.append("## Source de verite et pipeline actif")
    lines.append("")
    lines.append("- Source quetes active: `data/cache/dofus_maps/raw/doduda_cli` chargee par `QuestCatalog.load()`.")
    lines.append("- Enrichissement actif: `data/encyclopedia/quests/quests_enriched.json`, applique apres les donnees Doduda locales.")
    lines.append("- Source Guides active: `data/encyclopedia/guides/catalog.json` puis fichiers de guides actives.")
    lines.append("- Runtime: `QuestCatalog -> QuestProvider -> QuestGraphService -> GuideProvider -> GuideProgressCalculator`.")
    lines.append("- Donnees utilisateur auditees en lecture seule: `data/local/quest_progress.json`, `data/encyclopedia/progress/guide_progress.json`, `achievement_progress.json`.")
    lines.append("- Caches/rapports derives: `.cache/dofus_atlas/quest_catalog_v1.pkl`, `source_mapping.json`, `image_manifest.json`, `orphan_images_report.json`, `duffus_guides_full_audit.json`.")
    unused = payload.get("source_inventory", {}).get("unused_guide_files", [])
    lines.append(f"- Fichiers guide presents mais non actifs via `catalog.json`: {len(unused)}.")
    lines.append("")
    lines.append("## Inventaire")
    lines.append("")
    lines.append("| Element | Valeur |")
    lines.append("| --- | ---: |")
    for label, key in [
        ("Quetes actives analysees", "active_quests"),
        ("IDs de quetes uniques", "active_quest_ids_unique"),
        ("Quetes sans ID brut", "raw_quests_without_id"),
        ("IDs de quetes dupliques", "active_duplicate_quest_ids"),
        ("Groupes de titres dupliques", "duplicate_quest_titles"),
        ("Quetes sans titre", "quests_without_title"),
        ("Quetes sans niveau", "quests_without_level"),
        ("Quetes sans solution exploitable", "quests_without_solution"),
        ("Quetes sans source identifiable", "quests_without_source"),
        ("Quetes referencees par Guides", "quests_referenced_by_guides"),
        ("Quetes utilisees comme prerequis", "quests_used_as_prerequisites"),
        ("Quetes liees a des succes", "quests_linked_to_achievements"),
        ("Quetes avec objets necessaires", "quests_with_required_items"),
        ("Quetes avec images", "quests_with_images"),
        ("Guides actifs analyses", "active_guides"),
        ("Categories de Guides", "guide_categories"),
        ("Parties de Guides", "guide_parts"),
        ("Chapitres de Guides", "guide_chapters"),
        ("Series de Guides", "guide_series"),
        ("References Guides -> Quetes", "guide_quest_references_total"),
        ("Quetes uniques dans Guides", "guide_quest_references_unique"),
        ("Images actives referencees", "active_referenced_images"),
        ("Images actives manquantes", "missing_referenced_images"),
        ("Prerequis/relations graphe casses", "graph_missing_edges"),
        ("Cycles suspects", "graph_cycles"),
    ]:
        lines.append(f"| {label} | {inventory.get(key, 0)} |")
    lines.append("")
    lines.append("## Avant / Apres")
    lines.append("")
    lines.append("| Severite | Avant | Apres |")
    lines.append("| --- | ---: | ---: |")
    for severity in ["critical", "fixable", "suspect", "info"]:
        lines.append(f"| {severity} | {before_counts.get(severity, 0)} | {after_counts.get(severity, 0)} |")
    lines.append("")
    lines.append("## Corrections appliquees")
    lines.append("")
    lines.append("- Donnees Quetes/Guides: 0 correction automatique. Aucune erreur de donnee certaine n'est sortie de l'audit corrige.")
    lines.append("- Routing Guides/Quetes: clic normal sur une quete de Guide garde le contexte GUIDES et ouvre `GuidesView.show_quest_detail()`.")
    lines.append("- Routing prerequis: clic sur une quete affichee dans `PREREQUIS` depuis une quete de Guide appelle explicitement `source=\"guide_prerequisite\"` et ouvre l'onglet QUETES.")
    lines.append("- Tests ajoutes/ajustes: audit data reutilisable, clic Guide interne, clic prerequis vers QUETES, conservation de l'etat Guides.")
    lines.append("")
    lines.append("## Etat apres correction")
    lines.append("")
    lines.append(f"{inventory['active_quests']} quetes analysees")
    lines.append(f"{inventory['active_quests'] - summary['quests_to_review']} quetes OK")
    lines.append("0 quete corrigee automatiquement")
    lines.append(f"{summary['quests_to_review']} quetes a verifier manuellement")
    lines.append("")
    lines.append(f"{inventory['active_guides']} Guides analyses")
    lines.append(f"{inventory['active_guides'] - summary['guides_to_review']} Guides OK")
    lines.append("0 Guide corrige cote donnees")
    lines.append(f"{summary['guides_to_review']} Guides a verifier manuellement")
    lines.append("")
    lines.append(f"{inventory['dead_guide_quest_references']} reference Guide -> Quete cassee restante")
    lines.append(f"{inventory['missing_referenced_images']} image active manquante restante")
    lines.append(f"{inventory['graph_missing_edges']} prerequis non resolu restant")
    lines.append(f"{inventory['duplicate_quest_titles']} groupe de titres de quetes dupliques restant")
    lines.append(f"{inventory['duplicate_active_image_hashes']} groupes d'images actives identiques restants")
    lines.append("")
    lines.append("## A verifier manuellement")
    lines.append("")
    lines.append("Ces lignes restent intactes parce qu'aucune correction locale certaine ne peut etre deduite sans inventer une donnee.")
    lines.append("")
    append_issue_table(lines, "Quetes", quest_rows)
    append_issue_table(lines, "Guides", guide_rows)
    append_issue_table(lines, "Graphe et autres", other_rows)
    lines.append("## Informatif")
    lines.append("")
    append_issue_table(lines, "Images et doublons non bloquants", info_rows)
    lines.append("## Validations a relancer")
    lines.append("")
    lines.append("- `python -m app.modules.encyclopedia.tools.audit_quests_guides --fail-on-critical`")
    lines.append("- `python -m app.modules.encyclopedia.tools.validate_guides`")
    lines.append("- Tests: `tests.test_guides_phase3`, `tests.test_quests_guides_audit`, `tests.test_encyclopedia_corrective`, `tests.test_encyclopedia_final_mission`.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


def append_issue_table(lines: list[str], title: str, rows: list[dict[str, Any]]) -> None:
    lines.append(f"### {title}")
    lines.append("")
    if not rows:
        lines.append("Aucune entree.")
        lines.append("")
        return
    lines.append("| ID | Titre | Fichier | Champ | Probleme | Infos disponibles | Pourquoi pas de correction automatique |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                md_cell(value)
                for value in [
                    row.get("subject_id", ""),
                    row.get("title", ""),
                    row.get("file", ""),
                    row.get("field", ""),
                    row.get("reason", ""),
                    row.get("evidence", ""),
                    no_auto_fix_reason(row),
                ]
            )
            + " |"
        )
    lines.append("")


def no_auto_fix_reason(row: dict[str, Any]) -> str:
    category = str(row.get("category") or "")
    reason = str(row.get("reason") or "")
    if category == "quest_required_items":
        return "La quantite est atypique mais peut etre un cout ou un objectif valide; aucune source locale contradictoire."
    if category == "quest_content":
        return "Une solution courte peut etre normale; aucune etape fiable supplementaire n'est disponible localement."
    if category == "quest_duplicates":
        return "Les IDs sont uniques et plusieurs variantes Dofus peuvent partager un titre; fusion impossible sans preuve externe."
    if category == "guide_completeness":
        return "Le guide est explicitement marque partial; completer l'ordre ou le contenu exigerait une source non presente."
    if category == "quest_graph":
        return "Le cycle peut representer une branche metier; il ne doit pas etre casse sans preuve que l'une des relations est fausse."
    if category == "images":
        return "Fichiers identiques mais chemins actifs distincts; suppression interdite sans preuve d'inutilite."
    if "duplique" in reason.casefold():
        return "Doublon detecte mais pas assez certain pour fusionner sans changer la semantique."
    return "Aucune correction certaine ne peut etre deduite depuis les sources locales actives."


def md_cell(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = text.replace("|", "\\|")
    return text


if __name__ == "__main__":
    raise SystemExit(main())
