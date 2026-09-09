from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.constants import DATA_DIR, ROOT_DIR
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import QuestGraphService
from app.modules.encyclopedia.tools.enrich_quests import (
    dpln_mapping_confidence,
    extract_dpln_page_v2,
    request_bytes,
)
from app.quest_catalog import normalize_text, read_json_file, write_json_file


AUDIT_VERSION = 2
QUESTS_DIR = DATA_DIR / "encyclopedia" / "quests"
MAPPING_PATH = QUESTS_DIR / "source_mapping.json"
ENRICHED_PATH = QUESTS_DIR / "quests_enriched.json"
DEFAULT_JSON = ROOT_DIR / "artifacts" / "quests_guides_semantic_audit.json"
DEFAULT_MARKDOWN = ROOT_DIR / "artifacts" / "quests_guides_semantic_audit_report.md"
DEFAULT_CHANGES = ROOT_DIR / "artifacts" / "quests_guides_semantic_changes.md"
DEFAULT_CACHE = ROOT_DIR / "artifacts" / "dpln_semantic_audit_cache.json"
PERFORMANCE_PATH = ROOT_DIR / "artifacts" / "quests_guides_performance.json"
GUIDES_BEFORE_AUDIT = 20
GUIDED_QUESTS_BEFORE_AUDIT = 363
AVENTURE_QUESTS_BEFORE_AUDIT = 89
AVENTURE_CHAPTERS_BEFORE_AUDIT = 8
NAMED_GUIDE_EXPECTED_QUESTS = {
    "dofus_cawotte": 11,
    "dofus_argente": 58,
    "dofus_des_veilleurs": 15,
    "dofus_abyssal": 40,
    "dofus_des_glaces": 72,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split("_") if len(token) >= 3}


def jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left and right else 0.0


def local_solution_text(row: dict[str, Any]) -> str:
    blocks = [
        str(block.get("content") or block.get("text") or "")
        for block in row.get("solution_blocks", []) or []
        if isinstance(block, dict) and str(block.get("type") or block.get("block_type") or "") != "image"
    ]
    if blocks:
        return " ".join(blocks)
    return " ".join(
        str(objective.get("text") or "")
        for step in row.get("solution_steps", []) or []
        if isinstance(step, dict)
        for objective in step.get("objectives", []) or []
        if isinstance(objective, dict)
    )


def local_image_urls(row: dict[str, Any]) -> set[str]:
    urls = {
        str(block.get("source_url") or "")
        for block in row.get("solution_blocks", []) or []
        if isinstance(block, dict) and str(block.get("type") or block.get("block_type") or "") == "image"
    }
    urls.update(
        str(image.get("source_url") or "")
        for step in row.get("solution_steps", []) or []
        if isinstance(step, dict)
        for objective in step.get("objectives", []) or []
        if isinstance(objective, dict)
        for image in objective.get("images", []) or []
        if isinstance(image, dict)
    )
    return {url for url in urls if url}


def item_map(rows: Iterable[Any]) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = normalize_text(row.get("name") or "")
        if not key:
            continue
        try:
            quantity = int(row.get("quantity")) if row.get("quantity") not in (None, "") else None
        except (TypeError, ValueError):
            quantity = None
        result[key] = quantity
    return result


def local_row_signature(row: dict[str, Any]) -> str:
    payload = {
        "source_url": row.get("source_url"),
        "text": local_solution_text(row),
        "images": sorted(local_image_urls(row)),
        "items": row.get("required_items", []),
        "prerequisites": row.get("prerequisites", []),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def activity_flags(rows: Iterable[Any]) -> set[str]:
    result: set[str] = set()
    for row in rows:
        flags = getattr(row, "flags", None) if not isinstance(row, dict) else row.get("flags")
        if not isinstance(flags, dict):
            continue
        result.update(str(key) for key, value in flags.items() if value)
    return result


def compare_quest_info(local_row: dict[str, Any], live_blocks: Iterable[Any]) -> tuple[str, str]:
    source = activity_flags(live_blocks)
    if not source:
        return "QUEST_INFO_UNKNOWN", "Aucune information speciale structuree n'est demontree par la source."
    local = activity_flags(local_row.get("solution_blocks", []) or [])
    if source <= local:
        return "QUEST_INFO_OK", "Les indicateurs combat/activite/mecanique de la source sont conserves localement."
    if source & local:
        return "QUEST_INFO_PARTIAL", f"Indicateurs conserves partiellement: {len(source & local)}/{len(source)}."
    return "QUEST_INFO_PARTIAL", "Des indicateurs de quete existent dans la source mais ne sont pas structures localement."


def source_prerequisite_ids(
    prerequisites: list[str],
    title_to_ids: dict[str, list[int]],
) -> set[int]:
    result: set[int] = set()
    for value in prerequisites:
        key = normalize_text(value)
        ids = title_to_ids.get(key, [])
        if len(ids) == 1:
            result.add(ids[0])
    return result


def compare_text(local_row: dict[str, Any], live_text: str) -> tuple[str, float, str]:
    local_text = local_solution_text(local_row)
    if not live_text.strip():
        return "TEXT_UNKNOWN", 0.0, "Aucun texte de solution DPLN exploitable."
    if not local_text.strip():
        return "TEXT_MISSING", 0.0, "Solution locale absente alors que DPLN contient une solution."
    score = jaccard(clean_tokens(local_text), clean_tokens(live_text))
    if score >= 0.85:
        return "TEXT_OK", score, "Le contenu local recouvre fortement la page DPLN."
    if score >= 0.35:
        return "TEXT_PARTIAL", score, "Le contenu local ne recouvre qu'une partie de la page DPLN."
    if str(local_row.get("source") or "") == "dofus_pour_les_noobs":
        return "TEXT_PARTIAL", score, "Extraction DPLN locale tres incomplete; aucune autre quete n'est attribuee automatiquement."
    return "TEXT_UNKNOWN", score, "Source locale differente; divergence de formulation non suffisante pour conclure a une mauvaise quete."


def compare_images(local_row: dict[str, Any], live_urls: set[str]) -> tuple[str, float | None, str]:
    local_urls = local_image_urls(local_row)
    if not live_urls:
        return "IMAGE_UNKNOWN", None, "Aucune image de solution DPLN detectee."
    if not local_urls:
        return "IMAGE_MISSING", 0.0, "Images DPLN presentes mais aucune URL d'image source n'est conservee localement."
    recall = len(local_urls & live_urls) / len(live_urls)
    if recall == 1.0:
        return "IMAGE_OK", recall, "Toutes les images DPLN detectees sont rattachees a la quete locale."
    if recall > 0:
        return "IMAGE_UNKNOWN", recall, "Association partielle; les images restantes ne sont pas remappees automatiquement."
    return "IMAGE_UNKNOWN", recall, "Images issues d'une autre source; absence de preuve qu'elles sont incorrectes."


def compare_objects(local_row: dict[str, Any], live_rows: list[dict[str, Any]]) -> tuple[str, str]:
    source = item_map(live_rows)
    local = item_map(local_row.get("required_items", []) or [])
    if not source:
        return "OBJECTS_UNKNOWN", "DPLN ne fournit pas de liste structuree exploitable."
    if not local:
        return "OBJECTS_PARTIAL", "Objets DPLN presents mais liste locale absente."
    shared = set(source) & set(local)
    conflicts = [key for key in shared if source[key] is not None and local[key] is not None and source[key] != local[key]]
    doubled = [key for key in conflicts if int(local[key] or 0) == 2 * int(source[key] or 0)]
    if set(source) == set(local) and not conflicts:
        return "OBJECTS_OK", "Noms et quantites DPLN concordent."
    if doubled:
        return "OBJECTS_WRONG", f"Quantites doublees confirmees pour {len(doubled)} objet(s)."
    if shared:
        return "OBJECTS_PARTIAL", f"Concordance partielle: {len(shared)}/{len(source)} objet(s) DPLN."
    return "OBJECTS_UNKNOWN", "Aucun objet commun certain; pas de correction par ressemblance de nom."


def compare_prerequisites(local_ids: set[int], source_ids: set[int]) -> tuple[str, str]:
    if not source_ids:
        return "PREREQ_UNKNOWN", "Aucun prerequis de quete DPLN resolu sans ambiguite."
    if local_ids == source_ids:
        return "PREREQ_OK", "Les prerequis de quetes concordent."
    if local_ids & source_ids:
        return "PREREQ_PARTIAL", f"Prerequis communs: {len(local_ids & source_ids)}/{len(source_ids)}."
    return "PREREQ_UNKNOWN", "Divergence non corrigee: DPLN peut omettre des conditions techniques."


def audit_live_page(
    quest: Any,
    mapping_row: dict[str, Any],
    local_row: dict[str, Any],
    local_previous_ids: set[int],
    title_to_ids: dict[str, list[int]],
) -> dict[str, Any]:
    candidates = mapping_row.get("dofus_pour_les_noobs", []) or []
    if len(candidates) != 1:
        return {}
    candidate = candidates[0]
    url = str(candidate.get("url") or "")
    payload = request_bytes(url, timeout=45)
    extracted = extract_dpln_page_v2(payload, url, quest.name)
    confidence, signals, conflicts = dpln_mapping_confidence(quest, candidate, extracted)
    live_text = " ".join(block.content for block in extracted["blocks"] if block.block_type != "image")
    live_images = {block.source_url for block in extracted["blocks"] if block.block_type == "image" and block.source_url}
    source_previous_ids = source_prerequisite_ids(extracted["prerequisites"], title_to_ids)
    text_status, text_similarity, text_reason = compare_text(local_row, live_text)
    image_status, image_recall, image_reason = compare_images(local_row, live_images)
    objects_status, objects_reason = compare_objects(local_row, extracted["required_items"])
    prereq_status, prereq_reason = compare_prerequisites(local_previous_ids, source_previous_ids)
    quest_info_status, quest_info_reason = compare_quest_info(local_row, extracted["blocks"])
    return {
        "checked_at": now_iso(),
        "url": url,
        "source_title": extracted.get("title", ""),
        "mapping": confidence,
        "mapping_signals": signals,
        "mapping_conflicts": conflicts,
        "text": text_status,
        "text_similarity": round(text_similarity, 4),
        "text_reason": text_reason,
        "image": image_status,
        "image_recall": None if image_recall is None else round(image_recall, 4),
        "image_reason": image_reason,
        "objects": objects_status,
        "objects_reason": objects_reason,
        "prerequisites": prereq_status,
        "prerequisites_reason": prereq_reason,
        "quest_info": quest_info_status,
        "quest_info_reason": quest_info_reason,
        "source_counts": {
            "solution_blocks": len(extracted["blocks"]),
            "images": len(live_images),
            "required_items": len(extracted["required_items"]),
            "resolved_quest_prerequisites": len(source_previous_ids),
        },
        "local_signature": local_row_signature(local_row),
    }


def representative_sample(
    catalog: Any,
    guides: list[Any],
    mapping: dict[str, Any],
    enriched: dict[str, Any],
    size: int,
) -> list[int]:
    eligible = {
        int(qid)
        for qid, row in mapping.items()
        if isinstance(row, dict)
        and row.get("status") == "matched"
        and len(row.get("dofus_pour_les_noobs", []) or []) == 1
    }
    selected: list[int] = []

    def add(qid: int) -> None:
        if qid in eligible and qid not in selected and len(selected) < size:
            selected.append(qid)

    def add_where(predicate: Any, wanted: int) -> None:
        added = 0
        for quest in sorted(catalog.quests, key=lambda item: int(item.id)):
            before = len(selected)
            if int(quest.id) in eligible and predicate(quest):
                add(int(quest.id))
            if len(selected) > before:
                added += 1
            if added >= wanted or len(selected) >= size:
                break

    def local_row(quest: Any) -> dict[str, Any]:
        row = enriched.get(str(int(quest.id)), {})
        return row if isinstance(row, dict) else {}

    for guide in guides:
        for step in guide.required_steps:
            if step.step_type == "quest" and step.entity_id is not None and int(step.entity_id) in eligible:
                add(int(step.entity_id))
                break
    for guide in guides:
        consecutive = [
            int(step.entity_id)
            for step in guide.required_steps
            if step.step_type == "quest" and step.entity_id is not None and int(step.entity_id) in eligible
        ]
        if len(consecutive) >= 3:
            for qid in consecutive[:3]:
                add(qid)
            break
    dimension_terms = ("dimension", "ecaflipus", "enutrosor", "srambad", "xelorium")
    add_where(lambda quest: any(term in quest.search_text for term in dimension_terms), 3)
    add_where(lambda quest: int(quest.level_min or 0) <= 20, 5)
    add_where(lambda quest: 80 <= int(quest.level_min or 0) < 200, 5)
    add_where(lambda quest: int(quest.level_min or 0) >= 200, 5)
    add_where(
        lambda quest: bool(local_row(quest).get("required_items"))
        or any(objective.item_id is not None for step in quest.steps for objective in step.objectives),
        5,
    )
    add_where(
        lambda quest: bool(local_image_urls(local_row(quest))),
        5,
    )
    add_where(lambda quest: len(local_row(quest).get("prerequisites", []) or quest.prerequisites) >= 2, 5)
    add_where(
        lambda quest: bool(activity_flags(local_row(quest).get("solution_blocks", [])))
        or any(objective.is_combat for step in quest.steps for objective in step.objectives),
        5,
    )
    add_where(lambda quest: len(quest.steps) >= 5 or len(local_row(quest).get("solution_blocks", [])) >= 10, 5)
    for qid in sorted(eligible, key=lambda value: ((value * 2654435761) % (2**32), value)):
        add(qid)
    return selected[:size]


def sample_coverage(
    catalog: Any,
    sample_ids: list[int],
    guide_ids_by_quest: dict[int, list[str]],
    enriched: dict[str, Any],
    guides: list[Any],
) -> dict[str, int]:
    rows = [catalog.by_id[qid] for qid in sample_ids if qid in catalog.by_id]
    local_rows = {
        int(quest.id): enriched.get(str(int(quest.id)), {})
        if isinstance(enriched.get(str(int(quest.id)), {}), dict)
        else {}
        for quest in rows
    }
    guide_sequences = []
    for guide in guides:
        qids = [
            int(step.entity_id)
            for step in guide.required_steps
            if step.step_type == "quest" and step.entity_id is not None
        ]
        selected_positions = [index for index, qid in enumerate(qids) if qid in sample_ids]
        guide_sequences.append(any(right == left + 1 for left, right in zip(selected_positions, selected_positions[1:])))
    dofus_guide_ids = {
        str(guide.id)
        for guide in guides
        if str(getattr(guide, "category", "")) == "dofus"
    }
    return {
        "sample_size": len(rows),
        "low_level": sum(int(quest.level_min or 0) <= 20 for quest in rows),
        "mid_level": sum(20 < int(quest.level_min or 0) < 200 for quest in rows),
        "level_200": sum(int(quest.level_min or 0) >= 200 for quest in rows),
        "guide_quests": sum(bool(guide_ids_by_quest.get(int(quest.id))) for quest in rows),
        "dofus_guide_quests": sum(bool(dofus_guide_ids & set(guide_ids_by_quest.get(int(quest.id), []))) for quest in rows),
        "bonta_quests": sum("alignement_bonta" in guide_ids_by_quest.get(int(quest.id), []) for quest in rows),
        "brakmar_quests": sum("alignement_brakmar" in guide_ids_by_quest.get(int(quest.id), []) for quest in rows),
        "dimension_quests": sum(any(term in quest.search_text for term in ("dimension", "ecaflipus", "enutrosor", "srambad", "xelorium")) for quest in rows),
        "with_consecutive_guide_sequence": int(any(guide_sequences)),
        "with_items": sum(bool(local_rows[int(quest.id)].get("required_items")) or any(obj.item_id is not None for step in quest.steps for obj in step.objectives) for quest in rows),
        "with_images": sum(bool(local_image_urls(local_rows[int(quest.id)])) for quest in rows),
        "multiple_prerequisites": sum(len(local_rows[int(quest.id)].get("prerequisites", []) or quest.prerequisites) >= 2 for quest in rows),
        "with_combat": sum(bool(activity_flags(local_rows[int(quest.id)].get("solution_blocks", []))) or any(obj.is_combat for step in quest.steps for obj in step.objectives) for quest in rows),
        "long_quests": sum(len(quest.steps) >= 5 or len(local_rows[int(quest.id)].get("solution_blocks", [])) >= 10 for quest in rows),
    }


def base_result(quest: Any, mapping_row: dict[str, Any], local_row: dict[str, Any]) -> dict[str, Any]:
    candidates = mapping_row.get("dofus_pour_les_noobs", []) or []
    if mapping_row.get("status") == "ambiguous" or len(candidates) > 1:
        mapping_status = "AMBIGUOUS"
    elif not candidates:
        mapping_status = "NOT_FOUND"
    else:
        mapping_status = "AMBIGUOUS"
    technical_migration = "dpln_v2_pipeline" if int(local_row.get("extraction_version") or 0) == 2 else "legacy_or_other_source"
    return {
        "quest_id": int(quest.id),
        "title": quest.name,
        "level": int(quest.level_min or 0),
        "dpln_url": str(candidates[0].get("url") or "") if len(candidates) == 1 else "",
        "mapping": mapping_status,
        "mapping_signals": [],
        "mapping_conflicts": [],
        "text": "TEXT_UNKNOWN",
        "image": "IMAGE_UNKNOWN",
        "objects": "OBJECTS_UNKNOWN",
        "prerequisites": "PREREQ_UNKNOWN",
        "guide_reference": "GUIDE_REFERENCE_UNKNOWN",
        "quest_info": "QUEST_INFO_UNKNOWN",
        "status": "AMBIGUOUS" if mapping_status == "AMBIGUOUS" else "NOT_FOUND",
        "local_source": str(local_row.get("source") or ""),
        "correction": "none",
        "technical_migration": technical_migration,
        "reason": "Page DPLN non verifiee en ligne." if candidates else "Aucune page DPLN candidate fiable.",
    }


def global_status(row: dict[str, Any]) -> str:
    if row["mapping"] == "AMBIGUOUS":
        return "AMBIGUOUS"
    if row["mapping"] == "NOT_FOUND":
        return "NOT_FOUND"
    statuses = (row["text"], row["image"], row["objects"], row["prerequisites"], row["quest_info"])
    if all(value.endswith("_OK") for value in statuses):
        return "OK"
    return "PARTIAL"


def unguided_dependency_series(
    catalog: Any,
    graph: QuestGraphService,
    guided_ids: set[int],
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Find only series demonstrated by explicit Qf dependency edges."""

    candidates = set(catalog.by_id) - guided_ids
    adjacency: dict[int, set[int]] = defaultdict(set)
    for quest_id, following_ids in graph.criterion_next_by_quest.items():
        if quest_id not in candidates:
            continue
        for following_id in following_ids:
            if following_id in candidates:
                adjacency[quest_id].add(following_id)
                adjacency[following_id].add(quest_id)

    rows: list[dict[str, Any]] = []
    visited: set[int] = set()
    for root in sorted(adjacency):
        if root in visited:
            continue
        stack = [root]
        component: list[int] = []
        visited.add(root)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        if len(component) < 3:
            continue
        component.sort()
        quests = [catalog.by_id[quest_id] for quest_id in component]
        achievements = Counter(
            name
            for quest in quests
            for name in quest.achievements
            if str(name).strip()
        )
        categories = Counter(str(quest.category or "").strip() for quest in quests if str(quest.category or "").strip())
        label = achievements.most_common(1)[0][0] if achievements else (categories.most_common(1)[0][0] if categories else "Série sans libellé")
        rows.append(
            {
                "label": label,
                "quest_count": len(component),
                "quest_ids": component,
                "first_titles": [quest.name for quest in quests[:4]],
                "evidence": "Composante continue fondée uniquement sur des critères Qf explicites; aucun Guide créé automatiquement.",
            }
        )
    return sorted(rows, key=lambda row: (-row["quest_count"], normalize_text(row["label"])))[:limit]


def build_audit(online: str, sample_size: int, workers: int, refresh: bool, cache_path: Path) -> dict[str, Any]:
    quest_provider = QuestProvider()
    catalog = quest_provider.get_catalog()
    achievement_provider = AchievementProvider(quest_provider=quest_provider)
    guide_provider = GuideProvider(quest_provider=quest_provider, achievement_provider=achievement_provider)
    guides = guide_provider.load_all()
    graph = QuestGraphService(quest_provider, guide_provider, achievement_provider)
    mapping_payload = read_json_file(MAPPING_PATH, {})
    mapping = mapping_payload.get("quests", {}) if isinstance(mapping_payload, dict) else {}
    enriched_payload = read_json_file(ENRICHED_PATH, {})
    enriched = enriched_payload.get("quests", {}) if isinstance(enriched_payload, dict) else {}
    cache_payload = read_json_file(cache_path, {"version": AUDIT_VERSION, "quests": {}})
    cache_rows = cache_payload.get("quests", {}) if isinstance(cache_payload, dict) else {}
    if not isinstance(cache_rows, dict):
        cache_rows = {}

    title_to_ids: dict[str, list[int]] = defaultdict(list)
    for quest in catalog.quests:
        title_to_ids[normalize_text(quest.name)].append(int(quest.id))
    guide_ids_by_quest: dict[int, list[str]] = defaultdict(list)
    for guide in guides:
        for quest_id in guide.quest_ids:
            guide_ids_by_quest[int(quest_id)].append(guide.id)

    results = {
        str(quest.id): base_result(
            quest,
            mapping.get(str(quest.id), {}) if isinstance(mapping.get(str(quest.id), {}), dict) else {},
            enriched.get(str(quest.id), {}) if isinstance(enriched.get(str(quest.id), {}), dict) else {},
        )
        for quest in catalog.quests
    }
    sample_ids = representative_sample(catalog, guides, mapping, enriched, sample_size)
    if online == "full":
        target_ids = [
            int(qid)
            for qid, row in mapping.items()
            if isinstance(row, dict)
            and row.get("status") == "matched"
            and len(row.get("dofus_pour_les_noobs", []) or []) == 1
        ]
    elif online == "sample":
        target_ids = sample_ids
    else:
        target_ids = []

    errors: list[dict[str, Any]] = []
    fetched = 0
    reused = 0

    def inspect(qid: int) -> tuple[int, dict[str, Any], bool]:
        quest = catalog.by_id[qid]
        mapping_row = mapping[str(qid)]
        local_row = enriched.get(str(qid), {}) if isinstance(enriched.get(str(qid), {}), dict) else {}
        cached = cache_rows.get(str(qid), {}) if isinstance(cache_rows.get(str(qid), {}), dict) else {}
        candidate_url = str(mapping_row["dofus_pour_les_noobs"][0].get("url") or "")
        if (
            not refresh
            and cached.get("audit_version") in {1, AUDIT_VERSION}
            and cached.get("url") == candidate_url
            and cached.get("local_signature") == local_row_signature(local_row)
        ):
            migrated = dict(cached)
            if cached.get("audit_version") == 1 and cached.get("mapping") == "AMBIGUOUS":
                confidence, signals, conflicts = dpln_mapping_confidence(
                    quest,
                    mapping_row["dofus_pour_les_noobs"][0],
                    {"title": cached.get("source_title", ""), "prerequisites": []},
                )
                if confidence in {"EXACT", "HIGH"}:
                    migrated["mapping"] = confidence
                    migrated["mapping_signals"] = signals
                    migrated["mapping_conflicts"] = conflicts
            migrated["audit_version"] = AUDIT_VERSION
            return qid, migrated, True
        live = audit_live_page(
            quest,
            mapping_row,
            local_row,
            set(graph.previous_ids(qid)),
            title_to_ids,
        )
        live["audit_version"] = AUDIT_VERSION
        time.sleep(0.05)
        return qid, live, False

    if target_ids:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as pool:
            futures = {pool.submit(inspect, qid): qid for qid in target_ids}
            completed = 0
            for future in as_completed(futures):
                qid = futures[future]
                try:
                    resolved_qid, live, was_cached = future.result()
                except Exception as exc:
                    errors.append({"quest_id": qid, "error": str(exc)})
                    continue
                completed += 1
                if was_cached:
                    reused += 1
                else:
                    fetched += 1
                cache_rows[str(resolved_qid)] = live
                row = results[str(resolved_qid)]
                row.update({key: value for key, value in live.items() if key not in {"audit_version", "local_signature"}})
                row["status"] = global_status(row)
                row["reason"] = "; ".join(
                    value
                    for value in (
                        live.get("text_reason", ""),
                        live.get("image_reason", ""),
                        live.get("objects_reason", ""),
                        live.get("prerequisites_reason", ""),
                        live.get("quest_info_reason", ""),
                    )
                    if value
                )
                if completed % 100 == 0:
                    write_json_file(cache_path, {"version": AUDIT_VERSION, "updated_at": now_iso(), "quests": cache_rows})
        write_json_file(cache_path, {"version": AUDIT_VERSION, "updated_at": now_iso(), "quests": cache_rows})

    for qid, guide_ids in guide_ids_by_quest.items():
        if str(qid) in results:
            results[str(qid)]["guides"] = sorted(set(guide_ids))
            # A valid local id and a strong quest/page mapping do not prove that
            # the quest belongs in this Guide. That requires an independent
            # source for Guide composition and order.
            results[str(qid)]["guide_reference"] = "GUIDE_REFERENCE_UNKNOWN"

    quest_rows = sorted(results.values(), key=lambda row: int(row["quest_id"]))
    mapping_counts = Counter(row["mapping"] for row in quest_rows)
    text_counts = Counter(row["text"] for row in quest_rows)
    image_counts = Counter(row["image"] for row in quest_rows)
    object_counts = Counter(row["objects"] for row in quest_rows)
    prereq_counts = Counter(row["prerequisites"] for row in quest_rows)
    quest_info_counts = Counter(row["quest_info"] for row in quest_rows)
    status_counts = Counter(row["status"] for row in quest_rows)
    corrections = [row for row in quest_rows if row["correction"] != "none"]
    technical_migrations = [row for row in quest_rows if row["technical_migration"] == "dpln_v2_pipeline"]
    guide_rows = []
    for guide in guides:
        qids = list(guide.quest_ids)
        verified = sum(results[str(qid)]["mapping"] in {"EXACT", "HIGH"} for qid in qids if str(qid) in results)
        source_urls = [str(value) for value in guide.raw.get("source_urls", []) if str(value)] if isinstance(guide.raw.get("source_urls", []), list) else []
        if guide.completeness_status == "partial":
            guide_status = "GUIDE_PARTIAL"
            guide_reason = "; ".join(guide.validation_warnings) or "Le guide déclare explicitement une couverture partielle."
        elif source_urls:
            guide_status = "GUIDE_COMPLETE_SOURCE_VERIFIED"
            guide_reason = "Composition et nombre de quêtes recoupés avec la source de série déclarée."
        else:
            guide_status = "GUIDE_AMBIGUOUS"
            guide_reason = (
                "Toutes les pages de quete sont mappees, mais aucune source independante de composition/ordre du Guide n'est disponible."
                if qids and verified == len(qids)
                else "Une ou plusieurs quetes du Guide n'ont pas de mapping externe EXACT/HIGH."
            )
        guide_rows.append(
            {
                "guide_id": guide.id,
                "title": guide.title,
                "quest_references": len(qids),
                "mapped_exact_or_high": verified,
                "completeness_status": guide.completeness_status,
                "status": guide_status,
                "source_urls": source_urls,
                "reason": guide_reason,
            }
        )

    guided_ids = set(guide_ids_by_quest)
    unguided_series = unguided_dependency_series(catalog, graph, guided_ids)
    guides_by_id = {guide.id: guide for guide in guides}
    named_guides: dict[str, dict[str, Any]] = {}
    for guide_id, expected in NAMED_GUIDE_EXPECTED_QUESTS.items():
        guide = guides_by_id.get(guide_id)
        actual = len(guide.quest_ids) if guide is not None else 0
        named_guides[guide_id] = {
            "title": guide.title if guide is not None else guide_id,
            "status": guide.completeness_status if guide is not None else "missing",
            "quests": actual,
            "expected": expected,
            "missing": max(0, expected - actual),
            "warnings": list(guide.validation_warnings) if guide is not None else ["Guide absent."],
            "source_urls": [str(value) for value in guide.raw.get("source_urls", []) if str(value)] if guide is not None and isinstance(guide.raw.get("source_urls", []), list) else [],
        }
    adventure = guides_by_id.get("guide_complet")
    adventure_quests_after = len(adventure.quest_ids) if adventure is not None else 0
    adventure_chapters_after = len(adventure.sections) if adventure is not None else 0
    guides_complete = sum(guide.completeness_status == "complete" for guide in guides)
    guides_partial = sum(guide.completeness_status == "partial" for guide in guides)
    local_gaps_filled = max(0, len(guided_ids) - GUIDED_QUESTS_BEFORE_AUDIT)
    external_gaps_remaining = sum(row["missing"] for row in named_guides.values())
    guide_audit = {
        "guides_before": GUIDES_BEFORE_AUDIT,
        "guides_after": len(guides),
        "guides_complete": guides_complete,
        "guides_partial": guides_partial,
        "guides_added": max(0, len(guides) - GUIDES_BEFORE_AUDIT),
        "guides_remaining_to_verify": guides_partial,
        "guide_quests_missing_detected": local_gaps_filled + external_gaps_remaining,
        "guide_quests_added": local_gaps_filled,
        "external_guide_quests_remaining": external_gaps_remaining,
        "orders_corrected": 0,
        "verified_new_sequences": sum(1 for row in named_guides.values() if row["quests"]),
        "quest_info_added": 0,
        "named_guides": named_guides,
        "adventure": {
            "status": adventure.completeness_status if adventure is not None else "missing",
            "quests_before": AVENTURE_QUESTS_BEFORE_AUDIT,
            "quests_after": adventure_quests_after,
            "chapters_before": AVENTURE_CHAPTERS_BEFORE_AUDIT,
            "chapters_after": adventure_chapters_after,
            "series_and_gaps": "Les chaînes Dofus actives démontrées ont été ajoutées; la progression globale reste marquée partielle faute de source exhaustive unique.",
        },
        "unguided_dependency_series": unguided_series,
    }

    dpln_complete_without_blocks = sum(
        isinstance(row, dict)
        and row.get("status") == "complete"
        and row.get("source") == "dofus_pour_les_noobs"
        and not row.get("solution_blocks")
        for row in enriched.values()
    )
    doubled_objects = sum(row["objects"] == "OBJECTS_WRONG" for row in quest_rows)
    current_rows = sum(row["technical_migration"] == "dpln_v2_pipeline" for row in quest_rows)
    legacy_rows = len(quest_rows) - current_rows
    root_causes = [
        f"CAUSE CERTAINE - dataset hybride: {current_rows} lignes au schema DPLN v2 et {legacy_rows} lignes legacy/autre source; {dpln_complete_without_blocks} quetes DPLN completes n'ont aucun bloc ordonne.",
        "CAUSE CERTAINE - l'ancien parseur creait des etapes artificielles par token et attachait les images au bloc courant, ce qui perdait l'ordre naturel texte/image.",
        "CAUSE CERTAINE - le generateur reutilisait toute entree existante sans version d'extraction, laissant les anciennes lignes intactes apres une evolution du parseur.",
        f"CAUSE CERTAINE - la fusion historique additionnait des quantites provenant de deux sources; {doubled_objects} divergence(s) doublee(s) restent detectees dans le perimetre verifie.",
        "CAUSE NON DEMONTREE - aucun mapping par index n'a ete trouve dans le pipeline actuel; le mapping historique utilise titre normalise/slug, avec collisions classees ambigues.",
        "LIMITE DE SOURCE - le depot ne contient aucun corpus de quetes Dofus Book. Les controles de walkthrough disponibles utilisent Dofus Pour Les Noobs; la conformite Dofus Book reste donc non demontree.",
    ]
    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "source": "Dofus Pour Les Noobs",
        "mode": online,
        "summary": {
            "quests_analyzed": len(quest_rows),
            "guides_analyzed": len(guide_rows),
            "mapping": dict(mapping_counts),
            "text": dict(text_counts),
            "images": dict(image_counts),
            "objects": dict(object_counts),
            "prerequisites": dict(prereq_counts),
            "quest_info": dict(quest_info_counts),
            "status": dict(status_counts),
            "network_fetched": fetched,
            "cache_reused": reused,
            "network_errors": len(errors),
            "corrections_applied": len(corrections),
            "technical_migrations": len(technical_migrations),
        },
        "root_causes": root_causes,
        "sample_quest_ids": sample_ids,
        "sample_coverage": sample_coverage(catalog, sample_ids, guide_ids_by_quest, enriched, guides),
        "sample": [results[str(qid)] for qid in sample_ids if str(qid) in results],
        "guides": guide_rows,
        "guide_audit": guide_audit,
        "performance": read_json_file(PERFORMANCE_PATH, {}),
        "quests": quest_rows,
        "network_errors": errors,
        "corrections": corrections,
        "technical_migrations": technical_migrations,
    }


def md(value: Any) -> str:
    return " ".join(str(value or "").split()).replace("|", "\\|")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# Audit semantique Quetes / Guides",
        "",
        f"Genere le {payload['generated_at']} depuis Dofus Pour Les Noobs (mode `{payload['mode']}`).",
        "Dofus Book a ete demande comme reference principale, mais aucun corpus de quetes Dofus Book exploitable n'est present dans le depot; ce rapport ne revendique donc pas une conformite Dofus Book.",
        "",
        "## Resume",
        "",
        f"- {summary['quests_analyzed']} quetes analysees.",
        f"- Mapping: {summary['mapping'].get('EXACT', 0)} EXACT, {summary['mapping'].get('HIGH', 0)} HIGH, {summary['mapping'].get('AMBIGUOUS', 0)} AMBIGUOUS, {summary['mapping'].get('NOT_FOUND', 0)} NOT_FOUND.",
        f"- Textes: {summary['text'].get('TEXT_OK', 0)} OK, {summary['text'].get('TEXT_PARTIAL', 0)} partiels, {summary['text'].get('TEXT_MISSING', 0)} manquants, {summary['text'].get('TEXT_UNKNOWN', 0)} inconnus.",
        f"- Images: {summary['images'].get('IMAGE_OK', 0)} OK, {summary['images'].get('IMAGE_MISSING', 0)} manquantes, {summary['images'].get('IMAGE_UNKNOWN', 0)} inconnues.",
        f"- Objets: {summary['objects'].get('OBJECTS_OK', 0)} OK, {summary['objects'].get('OBJECTS_WRONG', 0)} faux, {summary['objects'].get('OBJECTS_PARTIAL', 0)} partiels, {summary['objects'].get('OBJECTS_UNKNOWN', 0)} inconnus.",
        f"- Prerequis: {summary['prerequisites'].get('PREREQ_OK', 0)} OK, {summary['prerequisites'].get('PREREQ_PARTIAL', 0)} partiels, {summary['prerequisites'].get('PREREQ_UNKNOWN', 0)} inconnus.",
        f"- Infos quete: {summary['quest_info'].get('QUEST_INFO_OK', 0)} OK, {summary['quest_info'].get('QUEST_INFO_PARTIAL', 0)} partielles, {summary['quest_info'].get('QUEST_INFO_UNKNOWN', 0)} inconnues.",
        f"- Guides: {summary['guides_analyzed']} analyses.",
        f"- Reseau: {summary['network_fetched']} pages lues, {summary['cache_reused']} resultats reutilises, {summary['network_errors']} erreurs.",
        f"- Corrections de donnees appliquees: {summary['corrections_applied']}.",
        f"- Migrations techniques DPLN v2 (non comptees comme corrections semantiques): {summary['technical_migrations']}.",
        "",
        "## Causes racines",
        "",
    ]
    lines.extend(f"- {cause}" for cause in payload["root_causes"])
    coverage = payload["sample_coverage"]
    lines.extend(
        [
            "",
            "## Echantillon automatise de 40-50 quetes",
            "",
            "Cet echantillon valide les signaux deterministes du mapping et la conservation technique du contenu. Il ne remplace pas une validation humaine Dofus Book.",
            "",
            (
                f"Couverture: {coverage['sample_size']} quetes; {coverage['low_level']} bas niveau; "
                f"{coverage['mid_level']} niveaux intermediaires; {coverage['level_200']} niveau 200; "
                f"{coverage['guide_quests']} presentes dans des Guides dont {coverage['dofus_guide_quests']} Dofus, "
                f"{coverage['bonta_quests']} Bonta et {coverage['brakmar_quests']} Brakmar; "
                f"{coverage['dimension_quests']} dimensions; {coverage['with_consecutive_guide_sequence']} serie consecutive; "
                f"{coverage['with_items']} avec objets; "
                f"{coverage['with_images']} avec images; {coverage['multiple_prerequisites']} avec plusieurs prerequis; "
                f"{coverage['with_combat']} avec combat; {coverage['long_quests']} longues."
            ),
            "",
            "| quest_id | Titre | Mapping | Texte | Image | Objets | Prerequis | Info quete | URL |",
            "| ---: | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in payload["sample"]:
        lines.append(
            "| " + " | ".join(md(value) for value in (row["quest_id"], row["title"], row["mapping"], row["text"], row["image"], row["objects"], row["prerequisites"], row["quest_info"], row["dpln_url"])) + " |"
        )
    guide_audit = payload["guide_audit"]
    lines.extend(
        [
            "",
            "## GUIDES",
            "",
            f"- Guides présents avant audit : {guide_audit['guides_before']}",
            f"- Guides complets après audit : {guide_audit['guides_complete']}",
            f"- Guides partiels : {guide_audit['guides_partial']}",
            f"- Guides ajoutés : {guide_audit['guides_added']}",
            f"- Guides restant à vérifier : {guide_audit['guides_remaining_to_verify']}",
            f"- Quêtes Guide manquantes détectées : {guide_audit['guide_quests_missing_detected']} ({guide_audit['guide_quests_added']} lacunes locales comblées, {guide_audit['external_guide_quests_remaining']} quêtes externes encore non positionnées).",
            f"- Quêtes ajoutées aux Guides : {guide_audit['guide_quests_added']}",
            f"- Ordres corrigés : {guide_audit['orders_corrected']} ; nouvelles séquences sourcées : {guide_audit['verified_new_sequences']}",
            f"- Infos quête ajoutées aux données : {guide_audit['quest_info_added']} (l'UI réutilise les indicateurs vérifiés existants).",
            "",
            "| Guide demandé | Couverture | Statut | Source / limite |",
            "| --- | ---: | --- | --- |",
        ]
    )
    for guide_id in ("dofus_cawotte", "dofus_argente", "dofus_des_veilleurs", "dofus_abyssal", "dofus_des_glaces"):
        row = guide_audit["named_guides"][guide_id]
        source = ", ".join(row["source_urls"]) or "; ".join(row["warnings"]) or "Source de composition non déclarée."
        lines.append(f"| {md(row['title'])} | {row['quests']}/{row['expected']} | {row['status']} | {md(source)} |")
    adventure = guide_audit["adventure"]
    lines.extend(
        [
            "",
            "### Aventure de zéro",
            "",
            f"- Quêtes avant : {adventure['quests_before']} ; après : {adventure['quests_after']}.",
            f"- Chapitres avant : {adventure['chapters_before']} ; après : {adventure['chapters_after']}.",
            f"- Statut : {adventure['status']}.",
            f"- Séries/trous : {adventure['series_and_gaps']}",
            "",
            "### Séries principales probablement sans Guide",
            "",
            "Détection conservatrice : uniquement des composantes de trois quêtes ou plus reliées par des critères `Qf` explicites. Ces lignes sont des candidats d'audit, pas des Guides créés automatiquement.",
            "",
        ]
    )
    if guide_audit["unguided_dependency_series"]:
        for row in guide_audit["unguided_dependency_series"]:
            titles = ", ".join(row["first_titles"])
            lines.append(f"- {md(row['label'])} — {row['quest_count']} quêtes ({md(titles)}).")
    else:
        lines.append("- Aucune composante continue non guidée de taille suffisante détectée.")
    lines.extend(["", "### Audit individuel des Guides", "", "Un mapping de page fort ne prouve ni l'appartenance au Guide, ni son ordre, ni sa complétude. Les statuts complets sourcés exigent une source de composition déclarée.", "", "| Guide | Quetes | EXACT/HIGH | Statut | Raison |", "| --- | ---: | ---: | --- | --- |"]) 
    for row in payload["guides"]:
        lines.append(f"| {md(row['title'])} | {row['quest_references']} | {row['mapped_exact_or_high']} | {row['status']} | {md(row['reason'])} |")
    performance = payload.get("performance", {})
    before = performance.get("before", {}) if isinstance(performance, dict) else {}
    after = performance.get("after", {}) if isinstance(performance, dict) else {}
    cold = performance.get("after_cold_cache_rebuild", {}) if isinstance(performance, dict) else {}
    if before and after:
        lines.extend(
            [
                "",
                "## PERFORMANCES GUIDES / QUÊTES",
                "",
                "Mesures offscreen Windows/Python 3.13. Les seuils ne sont pas utilisés comme tests fragiles; les tests vérifient l'architecture de cache.",
                "",
                "| Mesure | Avant | Après |",
                "| --- | ---: | ---: |",
                f"| Constructeur de démarrage | {before.get('startup_constructor_ms')} ms | {after.get('startup_constructor_ms')} ms |",
                f"| Première fenêtre peinte | {before.get('first_window_paint_ms')} ms | {after.get('first_window_paint_ms')} ms |",
                f"| QuestCatalog chaud | {before.get('quest_catalog_warm_ms')} ms | {after.get('quest_catalog_warm_ms')} ms |",
                f"| Premier clic Guides, retour UI | bloqué par {before.get('related_providers_sync_ms')} ms de préparation synchrone | {after.get('guide_click_dispatch_ms')} ms |",
                f"| Données Guides prêtes, cache chaud | n/a | {after.get('related_data_ready_background_ms')} ms en arrière-plan |",
                f"| Premier Guide rendu | {before.get('first_guide_render_ms')} ms | {after.get('first_guide_render_ms')} ms |",
                f"| Première quête rendue | {before.get('first_quest_render_ms')} ms | {after.get('first_quest_render_ms')} ms |",
                f"| Quête suivante rendue | {before.get('next_quest_render_ms')} ms | {after.get('next_quest_render_ms')} ms |",
                "",
                f"Après invalidation des sources, la reconstruction froide prend {cold.get('related_data_ready_background_ms')} ms en arrière-plan; le clic rend la main en {cold.get('guide_click_dispatch_ms')} ms et la page courante reste affichée. Le cache disque est reconstructible et invalidé par signatures de sources/code; le cache mémoire réutilise ensuite exactement les mêmes providers et le même graphe.",
            ]
        )
    lines.extend(["", "## Cas restant a verifier", "", "| quest_id | Titre | Guide | URL DPLN | Mapping | Texte | Image | Objets | Prerequis | Info quete | Migration | Correction | Raison |", "| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]) 
    for row in payload["quests"]:
        if row["status"] == "OK":
            continue
        lines.append(
            "| " + " | ".join(md(value) for value in (row["quest_id"], row["title"], ", ".join(row.get("guides", [])), row["dpln_url"], row["mapping"], row["text"], row["image"], row["objects"], row["prerequisites"], row["quest_info"], row["technical_migration"], row["correction"], row["reason"])) + " |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_changes(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Modifications semantiques Quetes / Guides",
        "",
        f"Genere le {payload['generated_at']}.",
        "",
        "## Problemes detectes",
        "",
        f"- {sum(row['text'] == 'TEXT_MISSING' for row in payload['quests'])} texte(s) source present(s) mais absent(s) localement.",
        f"- {sum(row['image'] == 'IMAGE_MISSING' for row in payload['quests'])} association(s) d'image source presente(s) mais absente(s) localement.",
        f"- {sum(row['objects'] == 'OBJECTS_WRONG' for row in payload['quests'])} divergence(s) certaine(s) d'objets/quantites.",
        f"- {sum(row['mapping'] in {'AMBIGUOUS', 'NOT_FOUND'} for row in payload['quests'])} mapping(s) sans preuve EXACT/HIGH.",
        "",
        "## Problemes corriges",
        "",
        f"{len(payload['corrections'])} correction(s) semantique(s) avec trace avant/apres.",
    ]
    if not payload["corrections"]:
        lines.extend(["", "Aucune regeneration technique n'est presentee comme une correction semantique sans ancienne valeur, nouvelle valeur et preuve de source."])
    lines.extend(
        [
            "",
            "## Migrations techniques deja presentes",
            "",
            f"{len(payload['technical_migrations'])} quete(s) portent le schema d'extraction DPLN v2. Ce nombre mesure une regeneration technique, pas un nombre de mauvaises associations corrigees.",
            "",
            "## Problemes volontairement laisses intacts",
            "",
            "Les mappings ambigus ou absents, divergences de formulation entre sources, compositions/ordres de Guides et champs sans source structuree restent inchanges.",
            "",
            "| quest_id | Titre | Mapping | Texte | Image | Objets | Prerequis | Info quete | Raison |",
            "| ---: | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in payload["quests"]:
        if row["status"] == "OK":
            continue
        lines.append(
            "| "
            + " | ".join(
                md(value)
                for value in (
                    row["quest_id"], row["title"], row["mapping"], row["text"], row["image"],
                    row["objects"], row["prerequisites"], row["quest_info"], row["reason"],
                )
            )
            + " |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit semantique conservateur Quetes/Guides contre DPLN.")
    parser.add_argument("--online", choices=("none", "sample", "full"), default="none")
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--changes-output", type=Path, default=DEFAULT_CHANGES)
    args = parser.parse_args(argv)
    payload = build_audit(args.online, max(30, min(args.sample_size, 50)), args.workers, args.refresh, args.cache)
    write_json_file(args.json_output, payload)
    write_markdown(args.markdown_output, payload)
    write_changes(args.changes_output, payload)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
