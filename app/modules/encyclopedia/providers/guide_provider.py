from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.constants import DATA_DIR
from app.modules.encyclopedia.models import (
    GUIDE_ACTIVITY_TYPES,
    GUIDE_STEP_TYPES,
    EntityRef,
    Guide,
    GuideActivity,
    GuideChapter,
    GuideObjective,
    GuidePart,
    GuideRequiredItem,
    GuideSection,
    GuideSeries,
    GuideStep,
)
from app.modules.encyclopedia.providers.achievement_provider import AchievementProvider, safe_int
from app.modules.encyclopedia.providers.dofus_item_provider import DOFUS_UNKNOWN_ICON, DofusItemProvider
from app.modules.encyclopedia.providers.quest_provider import QuestProvider
from app.quest_catalog import normalize_text

LOGGER = logging.getLogger(__name__)
GUIDES_DIR = DATA_DIR / "encyclopedia" / "guides"
GUIDE_IMAGES_DIR = DATA_DIR / "encyclopedia" / "images" / "guides"
GUIDE_CATALOG_FILE = "catalog.json"
GUIDE_MANIFEST_FILE = "manifest.json"
GUIDE_ALLOWED_CATEGORIES = ("aventure", "dofus", "alignements")
GUIDE_CATEGORY_LABELS = {
    "aventure": "Aventure",
    "dofus": "Dofus",
    "alignements": "Alignements",
}
GUIDE_COMPLETENESS_STATUSES = frozenset({"complete", "partial", "draft"})
FUTURE_ENTITY_LABELS = {
    "dungeon": "Donjon",
    "monster": "Monstre",
    "wanted": "Avis de recherche",
    "archmonster": "Archimonstre",
}


class GuideProvider:
    def __init__(
        self,
        guides_dir: Path = GUIDES_DIR,
        quest_provider: QuestProvider | None = None,
        achievement_provider: AchievementProvider | None = None,
        dofus_item_provider: DofusItemProvider | None = None,
        include_drafts: bool = False,
    ) -> None:
        self.guides_dir = guides_dir
        self.quest_provider = quest_provider or QuestProvider()
        self.achievement_provider = achievement_provider or AchievementProvider(quest_provider=self.quest_provider)
        self.dofus_item_provider = dofus_item_provider or DofusItemProvider()
        self.include_drafts = include_drafts
        self._loaded = False
        self._guides: list[Guide] = []
        self._by_id: dict[str, Guide] = {}
        self._by_category: dict[str, list[Guide]] = defaultdict(list)
        self._by_entity: dict[tuple[str, int], list[Guide]] = defaultdict(list)
        self._category_labels: dict[str, str] = dict(GUIDE_CATEGORY_LABELS)
        self._category_orders: dict[str, int] = {category: index * 10 for index, category in enumerate(GUIDE_ALLOWED_CATEGORIES, 1)}
        self.validation_errors: list[str] = []

    def load_all(self) -> list[Guide]:
        self._ensure_loaded()
        return list(self._guides)

    def reload(self) -> list[Guide]:
        self._loaded = False
        self._guides = []
        self._by_id = {}
        self._by_category = defaultdict(list)
        self._by_entity = defaultdict(list)
        self.validation_errors = []
        return self.load_all()

    def get_by_id(self, guide_id: str) -> Guide | None:
        self._ensure_loaded()
        return self._by_id.get(str(guide_id))

    def search(self, query: str, limit: int | None = None) -> list[Guide]:
        self._ensure_loaded()
        needle = normalize_text(query)
        if not needle:
            results = list(self._guides)
        else:
            tokens = [token for token in needle.split("_") if token]
            results = [guide for guide in self._guides if all(token in guide.search_text for token in tokens)]
            results.sort(key=lambda guide: self._search_sort_key(guide, tokens))
        return results[:limit] if limit is not None else results

    def get_categories(self) -> list[str]:
        self._ensure_loaded()
        return sorted(self._by_category, key=self._category_sort_key)

    def get_category_label(self, category: str) -> str:
        category = self._canonical_category(category)
        return self._category_labels.get(category, category)

    def get_by_category(self, category: str) -> list[Guide]:
        self._ensure_loaded()
        return list(self._by_category.get(str(category), []))

    def validate_guide(self, guide: Guide) -> list[str]:
        errors = list(guide.validation_errors)
        for section in guide.sections:
            errors.extend(section.validation_errors)
            for step in section.steps:
                errors.extend(step.validation_errors)
        errors.extend(self._circular_prerequisite_errors(guide))
        return errors

    def resolve_step(self, step: GuideStep) -> GuideStep:
        return step

    def get_linked_entities(self, guide_id: str) -> list[EntityRef]:
        guide = self.get_by_id(guide_id)
        return list(guide.linked_entities) if guide is not None else []

    def get_guides_for_entity(self, entity_type: str, entity_id: int) -> list[Guide]:
        self._ensure_loaded()
        return list(self._by_entity.get((str(entity_type), int(entity_id)), []))

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load()
        self._loaded = True

    def _load(self) -> None:
        entries = self._guide_entries()
        guides: list[Guide] = []
        seen_ids: set[str] = set()
        for order, (path, catalog_entry) in enumerate(entries):
            guide = self._load_guide(path, order, catalog_entry)
            if guide is None:
                continue
            if guide.completeness_status == "draft" and not self.include_drafts:
                continue
            if guide.id in seen_ids:
                message = f"Guide duplique ignore: {guide.id} ({path})"
                self.validation_errors.append(message)
                LOGGER.warning(message)
                continue
            seen_ids.add(guide.id)
            errors = self.validate_guide(guide)
            if errors:
                self.validation_errors.extend(f"{guide.id}: {error}" for error in errors)
                for error in errors:
                    LOGGER.info("Guide %s: %s", guide.id, error)
            guides.append(guide)
        self._guides = sorted(guides, key=lambda guide: (self._category_sort_key(guide.category), guide.order, normalize_text(guide.title), guide.id))
        self._by_id = {guide.id: guide for guide in self._guides}
        by_category: dict[str, list[Guide]] = defaultdict(list)
        by_entity: dict[tuple[str, int], list[Guide]] = defaultdict(list)
        for guide in self._guides:
            by_category[guide.category].append(guide)
            for ref in guide.linked_entities:
                by_entity[(ref.entity_type, int(ref.entity_id))].append(guide)
        self._by_category = defaultdict(
            list,
            {category: sorted(values, key=lambda guide: (guide.order, normalize_text(guide.title), guide.id)) for category, values in by_category.items()},
        )
        self._by_entity = defaultdict(
            list,
            {key: sorted(values, key=lambda guide: (guide.order, normalize_text(guide.title), guide.id)) for key, values in by_entity.items()},
        )

    def _guide_entries(self) -> list[tuple[Path, dict[str, Any]]]:
        catalog_path = self.guides_dir / GUIDE_CATALOG_FILE
        if catalog_path.exists():
            return self._guide_entries_from_catalog(catalog_path)
        manifest_path = self.guides_dir / GUIDE_MANIFEST_FILE
        if manifest_path.exists():
            payload = self._read_json(manifest_path, {})
            guide_names = payload.get("guides", []) if isinstance(payload, dict) else []
            entries = []
            for name in guide_names if isinstance(guide_names, list) else []:
                path = self._safe_guide_path(str(name))
                if path is not None:
                    entries.append((path, {}))
            return entries
        if not self.guides_dir.exists():
            return []
        return [(path, {}) for path in sorted(path for path in self.guides_dir.glob("*.json") if path.name not in {GUIDE_CATALOG_FILE, GUIDE_MANIFEST_FILE})]

    def _guide_entries_from_catalog(self, catalog_path: Path) -> list[tuple[Path, dict[str, Any]]]:
        payload = self._read_json(catalog_path, {})
        if not isinstance(payload, dict):
            self.validation_errors.append("catalog.json invalide")
            return []
        if safe_int(payload.get("schema_version")) != 1:
            self.validation_errors.append("catalog.json: schema_version invalide ou absent")
        self._load_catalog_categories(payload.get("categories", []))
        guide_entries = payload.get("guides", [])
        if not isinstance(guide_entries, list):
            self.validation_errors.append("catalog.json: guides doit etre une liste")
            return []
        entries: list[tuple[Path, dict[str, Any]]] = []
        seen_files: set[str] = set()
        for index, row in enumerate(guide_entries):
            if not isinstance(row, dict):
                self.validation_errors.append(f"catalog.json: entree guide #{index + 1} invalide")
                continue
            if row.get("enabled") is False:
                continue
            file_name = str(row.get("file") or "").strip()
            if not file_name:
                self.validation_errors.append(f"catalog.json: fichier absent pour {row.get('id') or index + 1}")
                continue
            if file_name in seen_files:
                self.validation_errors.append(f"catalog.json: fichier duplique: {file_name}")
                continue
            seen_files.add(file_name)
            category = self._canonical_category(row.get("category"))
            if category not in GUIDE_ALLOWED_CATEGORIES:
                self.validation_errors.append(f"catalog.json: categorie non autorisee: {row.get('category')}")
            path = self._safe_guide_path(file_name)
            if path is not None:
                entries.append((path, dict(row)))
        return sorted(entries, key=lambda item: (self._category_sort_key(str(item[1].get("category") or "")), safe_int(item[1].get("order"), 9999) or 9999, item[0].name))

    def _load_catalog_categories(self, rows: Any) -> None:
        self._category_labels = dict(GUIDE_CATEGORY_LABELS)
        self._category_orders = {category: index * 10 for index, category in enumerate(GUIDE_ALLOWED_CATEGORIES, 1)}
        if not isinstance(rows, list):
            self.validation_errors.append("catalog.json: categories doit etre une liste")
            return
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            category = self._canonical_category(row.get("id"))
            if category not in GUIDE_ALLOWED_CATEGORIES:
                self.validation_errors.append(f"catalog.json: categorie non autorisee: {row.get('id')}")
                continue
            if category in seen:
                self.validation_errors.append(f"catalog.json: categorie dupliquee: {category}")
            seen.add(category)
            self._category_labels[category] = str(row.get("label") or GUIDE_CATEGORY_LABELS[category]).strip()
            self._category_orders[category] = safe_int(row.get("order"), self._category_orders[category]) or self._category_orders[category]

    def _load_guide(self, path: Path, order: int, catalog_entry: dict[str, Any] | None = None) -> Guide | None:
        catalog_entry = catalog_entry or {}
        payload = self._read_json(path, None)
        if not isinstance(payload, dict):
            message = f"Guide JSON invalide: {path}"
            self.validation_errors.append(message)
            LOGGER.warning(message)
            return None
        errors: list[str] = []
        if safe_int(payload.get("schema_version")) != 1:
            errors.append("schema_version invalide ou absent")
        guide_id = str(payload.get("id") or path.stem).strip()
        if not guide_id:
            errors.append("id de guide absent")
            guide_id = path.stem
        title = str(payload.get("title") or guide_id).strip()
        category = self._canonical_category(catalog_entry.get("category") or payload.get("category"))
        if category not in GUIDE_ALLOWED_CATEGORIES:
            errors.append(f"categorie non autorisee: {payload.get('category') or catalog_entry.get('category')}")
        payload_category = self._canonical_category(payload.get("category"))
        if catalog_entry.get("category") and payload_category and payload_category != category:
            errors.append(f"categorie du guide differente du catalogue: {payload_category} != {category}")
        category_label = self.get_category_label(category)
        completeness_status = str(payload.get("completeness_status") or "complete").strip().casefold()
        if completeness_status not in GUIDE_COMPLETENESS_STATUSES:
            errors.append(f"completeness_status non autorise: {payload.get('completeness_status')}")
            completeness_status = "draft"
        validation_warnings = tuple(str(value).strip() for value in payload.get("validation_warnings", []) if str(value).strip()) if isinstance(payload.get("validation_warnings", []), list) else ()
        sections = self._sections(payload, guide_id)
        parts = self._parts(payload, guide_id, sections)
        if not sections and parts:
            sections = self._sections_from_parts(parts)
        context_entities, context_errors = self._context_entities(payload, sections)
        errors.extend(context_errors)
        if not sections:
            errors.append("guide vide")
        reward_item_id = safe_int(payload.get("reward_item_id"))
        illustration_item_id = safe_int(payload.get("illustration_item_id"))
        reward_item = self.dofus_item_provider.get_by_id(reward_item_id)
        illustration_item = self.dofus_item_provider.get_by_id(illustration_item_id)
        if reward_item_id is not None and reward_item is None:
            errors.append(f"reward_item_id invalide: {reward_item_id}")
        if illustration_item_id is not None and illustration_item is None:
            errors.append(f"illustration_item_id invalide: {illustration_item_id}")
        image_path = self._resolve_image_path(payload.get("image"))
        if not image_path and illustration_item is not None:
            image_path = illustration_item.image_path
        if not image_path and DOFUS_UNKNOWN_ICON.exists():
            image_path = str(DOFUS_UNKNOWN_ICON)
        search_values = [
            title,
            str(payload.get("description") or ""),
            category,
            category_label,
            reward_item.name if reward_item is not None else "",
            illustration_item.name if illustration_item is not None else "",
            " ".join(validation_warnings),
            " ".join(section.title for section in sections),
            " ".join(section.description for section in sections),
            " ".join(part.title for part in parts),
            " ".join(chapter.title for part in parts for chapter in part.chapters),
            " ".join(series.title for part in parts for chapter in part.chapters for series in chapter.series),
            " ".join(ref.label for ref in context_entities),
            " ".join(step.display_title for section in sections for step in section.steps),
            " ".join(step.notes for section in sections for step in section.steps),
            " ".join(step.content for section in sections for step in section.steps),
        ]
        guide = Guide(
            id=guide_id,
            title=title,
            category=category,
            category_label=category_label,
            description=str(payload.get("description") or "").strip(),
            recommended_level_min=safe_int(payload.get("recommended_level_min")),
            recommended_level_max=safe_int(payload.get("recommended_level_max")),
            reward_item_id=reward_item_id,
            illustration_item_id=illustration_item_id,
            reward_item=reward_item,
            illustration_item=illustration_item,
            image_path=image_path,
            order=safe_int(catalog_entry.get("order"), safe_int(payload.get("order"), order)) or order,
            completeness_status=completeness_status,
            verified_steps=safe_int(payload.get("verified_steps")),
            total_steps=safe_int(payload.get("total_steps")),
            validation_warnings=validation_warnings,
            generation_source=str(payload.get("generation_source") or "").strip(),
            parts=parts,
            sections=sections,
            context_entities=context_entities,
            validation_errors=tuple(errors),
            search_text=normalize_text(" ".join(search_values)),
            raw=dict(payload),
        )
        circular_errors = self._circular_prerequisite_errors(guide)
        if circular_errors:
            guide = replace(guide, validation_errors=tuple([*guide.validation_errors, *circular_errors]))
        return guide

    def _parts(self, payload: dict[str, Any], guide_id: str, sections: tuple[GuideSection, ...]) -> tuple[GuidePart, ...]:
        part_rows = payload.get("parts", [])
        if isinstance(part_rows, list) and part_rows:
            return self._parts_from_rows(part_rows, guide_id)
        return self._parts_from_sections(sections)

    def _parts_from_rows(self, rows: list[Any], guide_id: str) -> tuple[GuidePart, ...]:
        parts: list[GuidePart] = []
        for part_order, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                continue
            part_id = str(row.get("id") or f"{guide_id}_part_{part_order}").strip()
            chapters = self._chapters_from_rows(row.get("chapters", []), guide_id, part_id)
            parts.append(
                GuidePart(
                    id=part_id,
                    title=str(row.get("title") or part_id).strip(),
                    order=safe_int(row.get("order"), part_order) or part_order,
                    part_type=str(row.get("type") or row.get("part_type") or "quest_category").strip(),
                    description=str(row.get("description") or "").strip(),
                    progress_mode=str(row.get("progress_mode") or "quests").strip(),
                    level_min=safe_int(row.get("level_min")),
                    level_max=safe_int(row.get("level_max")),
                    chapters=chapters,
                    activities=self._activities(row.get("activities", []), part_id),
                    required_items=self._required_items(row.get("required_items", []), part_id=part_id),
                    raw=dict(row),
                )
            )
        return tuple(sorted(parts, key=lambda part: (part.order, normalize_text(part.title), part.id)))

    def _chapters_from_rows(self, rows: Any, guide_id: str, part_id: str) -> tuple[GuideChapter, ...]:
        if not isinstance(rows, list):
            rows = []
        chapters: list[GuideChapter] = []
        for chapter_order, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                continue
            chapter_id = str(row.get("id") or f"{part_id}_chapter_{chapter_order}").strip()
            series = self._series_from_rows(row.get("series", []), guide_id, part_id, chapter_id)
            chapters.append(
                GuideChapter(
                    id=chapter_id,
                    title=str(row.get("title") or chapter_id).strip(),
                    order=safe_int(row.get("order"), chapter_order) or chapter_order,
                    description=str(row.get("description") or "").strip(),
                    level_min=safe_int(row.get("level_min")),
                    level_max=safe_int(row.get("level_max")),
                    series=series,
                    activities=self._activities(row.get("activities", []), chapter_id),
                    required_items=self._required_items(row.get("required_items", []), part_id=part_id, chapter_id=chapter_id),
                    raw=dict(row),
                )
            )
        return tuple(sorted(chapters, key=lambda chapter: (chapter.order, normalize_text(chapter.title), chapter.id)))

    def _series_from_rows(self, rows: Any, guide_id: str, part_id: str, chapter_id: str) -> tuple[GuideSeries, ...]:
        if not isinstance(rows, list):
            rows = []
        seen_steps: set[str] = set()
        series_rows: list[GuideSeries] = []
        for series_order, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                continue
            series_id = str(row.get("id") or f"{chapter_id}_series_{series_order}").strip()
            step_rows = row.get("steps")
            if not isinstance(step_rows, list):
                quest_ids = [safe_int(value) for value in row.get("quest_ids", [])] if isinstance(row.get("quest_ids", []), list) else []
                step_rows = [
                    {
                        "id": f"{series_id}_quest_{quest_id}",
                        "type": "quest",
                        "entity_id": quest_id,
                        "optional": False,
                        "prerequisites": [],
                    }
                    for quest_id in quest_ids
                    if quest_id is not None
                ]
            steps = self._steps({"steps": step_rows}, guide_id, series_id, seen_steps)
            series_rows.append(
                GuideSeries(
                    id=series_id,
                    title=str(row.get("title") or series_id).strip(),
                    order=safe_int(row.get("order"), series_order) or series_order,
                    achievement_id=safe_int(row.get("achievement_id")),
                    description=str(row.get("description") or "").strip(),
                    quest_ids=tuple(step.entity_id for step in steps if step.step_type == "quest" and step.entity_id is not None),
                    steps=steps,
                    objectives=self._objectives(row.get("objectives", []), series_id),
                    activities=self._activities(row.get("activities", []), series_id),
                    required_items=self._required_items(row.get("required_items", []), part_id=part_id, chapter_id=chapter_id),
                    chapter_info=tuple(str(value).strip() for value in row.get("chapter_info", []) if str(value).strip()) if isinstance(row.get("chapter_info", []), list) else (),
                    source_reference=str(row.get("source_reference") or "").strip(),
                    local_resolution_status=str(row.get("local_resolution_status") or "resolved").strip(),
                    raw=dict(row),
                )
            )
        return tuple(sorted(series_rows, key=lambda series: (series.order, normalize_text(series.title), series.id)))

    @staticmethod
    def _parts_from_sections(sections: tuple[GuideSection, ...]) -> tuple[GuidePart, ...]:
        parts: list[GuidePart] = []
        for section in sections:
            series = GuideSeries(
                id=f"{section.id}_series",
                title=section.title,
                order=section.order,
                achievement_id=_first_int(section.raw.get("linked_achievement_ids", [])) if isinstance(section.raw, dict) else None,
                description=section.description,
                quest_ids=tuple(step.entity_id for step in section.steps if step.step_type == "quest" and step.entity_id is not None),
                steps=section.steps,
                raw=dict(section.raw) if isinstance(section.raw, dict) else {},
            )
            chapter = GuideChapter(
                id=f"{section.id}_chapter",
                title=section.title,
                order=section.order,
                description=section.description,
                series=(series,),
                raw=dict(section.raw) if isinstance(section.raw, dict) else {},
            )
            parts.append(
                GuidePart(
                    id=section.id,
                    title=section.title,
                    order=section.order,
                    description=section.description,
                    chapters=(chapter,),
                    raw=dict(section.raw) if isinstance(section.raw, dict) else {},
                )
            )
        return tuple(parts)

    @staticmethod
    def _sections_from_parts(parts: tuple[GuidePart, ...]) -> tuple[GuideSection, ...]:
        sections: list[GuideSection] = []
        for part in parts:
            sections.append(
                GuideSection(
                    id=part.id,
                    title=part.title,
                    description=part.description,
                    order=part.order,
                    steps=part.steps,
                    raw=dict(part.raw) if isinstance(part.raw, dict) else {},
                )
            )
        return tuple(sections)

    def _activities(self, rows: Any, prefix: str) -> tuple[GuideActivity, ...]:
        if not isinstance(rows, list):
            return ()
        result: list[GuideActivity] = []
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                continue
            activity_type = str(row.get("type") or row.get("activity_type") or "other").strip()
            if activity_type not in GUIDE_ACTIVITY_TYPES:
                activity_type = "other"
            result.append(
                GuideActivity(
                    activity_id=str(row.get("activity_id") or f"{prefix}_activity_{index}").strip(),
                    activity_type=activity_type,
                    quest_id=safe_int(row.get("quest_id")),
                    objective_id=safe_int(row.get("objective_id")),
                    quantity=safe_int(row.get("quantity"), 1) or 1,
                    monster_ids=tuple(int(value) for value in row.get("monster_ids", []) if safe_int(value) is not None) if isinstance(row.get("monster_ids", []), list) else (),
                    dungeon_id=safe_int(row.get("dungeon_id")),
                    boss_id=safe_int(row.get("boss_id")),
                    item_ids=tuple(int(value) for value in row.get("item_ids", []) if safe_int(value) is not None) if isinstance(row.get("item_ids", []), list) else (),
                    map_id=safe_int(row.get("map_id")),
                    mandatory=bool(row.get("mandatory", True)),
                    label=str(row.get("label") or "").strip(),
                    raw=dict(row),
                )
            )
        return tuple(result)

    def _required_items(self, rows: Any, part_id: str = "", chapter_id: str = "") -> tuple[GuideRequiredItem, ...]:
        if not isinstance(rows, list):
            return ()
        result: list[GuideRequiredItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item_id = safe_int(row.get("item_id"))
            item = self.dofus_item_provider.get_by_id(item_id) if item_id is not None else None
            result.append(
                GuideRequiredItem(
                    item_id=item_id,
                    name=str(row.get("name") or (item.name if item else "")).strip(),
                    quantity=safe_int(row.get("quantity"), 1) or 1,
                    item_type=str(row.get("type") or row.get("item_type") or "").strip(),
                    image_path=str(row.get("image_path") or (item.image_path if item else "")).strip(),
                    mandatory=bool(row.get("mandatory", True)),
                    consumed=bool(row.get("consumed", True)),
                    quest_id=safe_int(row.get("quest_id")),
                    chapter_id=chapter_id,
                    part_id=part_id,
                    raw=dict(row),
                )
            )
        return tuple(result)

    def _objectives(self, rows: Any, prefix: str) -> tuple[GuideObjective, ...]:
        if not isinstance(rows, list):
            return ()
        result: list[GuideObjective] = []
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                continue
            entity_ref = None
            entity_type = str(row.get("entity_type") or "").strip()
            entity_id = safe_int(row.get("entity_id"))
            if entity_type and entity_id is not None:
                entity_ref, _available, _errors = self._resolve_entity(entity_type, entity_id, row)
            result.append(
                GuideObjective(
                    id=str(row.get("id") or f"{prefix}_objective_{index}").strip(),
                    title=str(row.get("title") or row.get("text") or "").strip(),
                    objective_type=str(row.get("type") or row.get("objective_type") or "info").strip(),
                    entity_ref=entity_ref,
                    quantity_current=safe_int(row.get("quantity_current")),
                    quantity_required=safe_int(row.get("quantity_required")),
                    optional=bool(row.get("optional", False)),
                    raw=dict(row),
                )
            )
        return tuple(result)

    def _sections(self, payload: dict[str, Any], guide_id: str) -> tuple[GuideSection, ...]:
        section_rows = payload.get("sections", [])
        if not isinstance(section_rows, list):
            section_rows = []
        sections: list[GuideSection] = []
        seen_sections: set[str] = set()
        seen_steps: set[str] = set()
        for section_order, section_row in enumerate(section_rows, 1):
            if not isinstance(section_row, dict):
                continue
            section_id = str(section_row.get("id") or f"{guide_id}_section_{section_order}").strip()
            errors = []
            if section_id in seen_sections:
                errors.append(f"section dupliquee: {section_id}")
            seen_sections.add(section_id)
            sections.append(
                GuideSection(
                    id=section_id,
                    title=str(section_row.get("title") or section_id).strip(),
                    description=str(section_row.get("description") or "").strip(),
                    order=section_order,
                    steps=self._steps(section_row, guide_id, section_id, seen_steps),
                    validation_errors=tuple(errors),
                    raw=dict(section_row),
                )
            )
        return tuple(sections)

    def _context_entities(self, payload: dict[str, Any], sections: tuple[GuideSection, ...]) -> tuple[tuple[EntityRef, ...], list[str]]:
        refs: dict[tuple[str, int], EntityRef] = {}
        errors: list[str] = []

        def add_achievement(raw_id: Any) -> None:
            achievement_id = safe_int(raw_id)
            if achievement_id is None:
                return
            achievement = self.achievement_provider.get_by_id(achievement_id)
            if achievement is None:
                errors.append(f"succes contextuel inexistant: {achievement_id}")
                return
            refs.setdefault(("achievement", achievement.id), EntityRef("achievement", achievement.id, achievement.name))

        root_ids = payload.get("linked_achievement_ids", [])
        if isinstance(root_ids, list):
            for achievement_id in root_ids:
                add_achievement(achievement_id)
        for section in sections:
            section_ids = section.raw.get("linked_achievement_ids", []) if isinstance(section.raw, dict) else []
            if isinstance(section_ids, list):
                for achievement_id in section_ids:
                    add_achievement(achievement_id)
        return tuple(refs.values()), errors

    def _steps(
        self,
        section_row: dict[str, Any],
        guide_id: str,
        section_id: str,
        seen_steps: set[str],
    ) -> tuple[GuideStep, ...]:
        step_rows = section_row.get("steps", [])
        if not isinstance(step_rows, list):
            step_rows = []
        steps: list[GuideStep] = []
        for step_order, step_row in enumerate(step_rows, 1):
            if not isinstance(step_row, dict):
                continue
            step_id = str(step_row.get("id") or f"{section_id}_step_{step_order}").strip()
            errors: list[str] = []
            if step_id in seen_steps:
                errors.append(f"etape dupliquee: {step_id}")
            seen_steps.add(step_id)
            step_type = str(step_row.get("type") or "info").strip()
            if step_type not in GUIDE_STEP_TYPES:
                errors.append(f"type d'etape non autorise: {step_type}")
            entity_id = safe_int(step_row.get("entity_id"))
            entity_ref, available, entity_errors = self._resolve_entity(step_type, entity_id, step_row)
            errors.extend(entity_errors)
            prerequisites = tuple(self._prerequisites(step_row.get("prerequisites", [])))
            steps.append(
                GuideStep(
                    id=step_id,
                    step_type=step_type,
                    order=step_order,
                    title=str(step_row.get("title") or "").strip(),
                    content=str(step_row.get("content") or "").strip(),
                    entity_id=entity_id,
                    optional=bool(step_row.get("optional", False)),
                    notes=str(step_row.get("notes") or "").strip(),
                    prerequisites=prerequisites,
                    entity_ref=entity_ref,
                    available=available,
                    validation_errors=tuple(errors),
                    raw=dict(step_row),
                )
            )
        return tuple(steps)

    def _resolve_entity(
        self,
        step_type: str,
        entity_id: int | None,
        step_row: dict[str, Any],
    ) -> tuple[EntityRef | None, bool, list[str]]:
        if step_type == "info":
            return None, True, []
        title = str(step_row.get("title") or "").strip()
        if entity_id is None:
            return None, False, [f"entity_id absent pour {step_type}"]
        if step_type == "quest":
            quest = self.quest_provider.get_quest(entity_id)
            if quest is None:
                return EntityRef("quest", entity_id, title or f"Quete {entity_id}"), False, [f"quete inexistante: {entity_id}"]
            return EntityRef("quest", entity_id, quest.name), True, []
        if step_type == "achievement":
            achievement = self.achievement_provider.get_by_id(entity_id)
            if achievement is None:
                return EntityRef("achievement", entity_id, title or f"Succes {entity_id}"), False, [f"succes inexistant: {entity_id}"]
            return EntityRef("achievement", entity_id, achievement.name), True, []
        if step_type in FUTURE_ENTITY_LABELS:
            label = title or f"{FUTURE_ENTITY_LABELS[step_type]} {entity_id}"
            return EntityRef(step_type, entity_id, label), False, [f"module non encore disponible: {step_type}"]
        return None, False, [f"type d'etape non autorise: {step_type}"]

    def _prerequisites(self, rows: Any) -> list[EntityRef]:
        if not isinstance(rows, list):
            return []
        refs: list[EntityRef] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            entity_type = str(row.get("type") or "").strip()
            entity_id = safe_int(row.get("entity_id"))
            if entity_type not in GUIDE_STEP_TYPES or entity_id is None:
                continue
            entity_ref, _available, _errors = self._resolve_entity(entity_type, entity_id, row)
            if entity_ref is not None:
                refs.append(entity_ref)
        return refs

    def _circular_prerequisite_errors(self, guide: Guide) -> list[str]:
        steps_by_entity = {
            (step.step_type, step.entity_id): step.id
            for step in guide.steps
            if step.entity_id is not None
        }
        graph: dict[str, list[str]] = defaultdict(list)
        for step in guide.steps:
            for ref in step.prerequisites:
                target = steps_by_entity.get((ref.entity_type, ref.entity_id))
                if target:
                    graph[step.id].append(target)
        visiting: set[str] = set()
        visited: set[str] = set()
        errors: list[str] = []

        def visit(step_id: str) -> None:
            if step_id in visiting:
                errors.append(f"prerequis circulaire detecte autour de {step_id}")
                return
            if step_id in visited:
                return
            visiting.add(step_id)
            for target_id in graph.get(step_id, []):
                visit(target_id)
            visiting.discard(step_id)
            visited.add(step_id)

        for step in guide.steps:
            visit(step.id)
        return errors

    def _safe_guide_path(self, name: str) -> Path | None:
        candidate = (self.guides_dir / name).resolve()
        try:
            candidate.relative_to(self.guides_dir.resolve())
        except ValueError:
            LOGGER.warning("Guide ignore hors dossier: %s", name)
            return None
        return candidate

    def _resolve_image_path(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if "://" in text:
            LOGGER.warning("Image distante ignoree dans un guide: %s", text)
            return ""
        candidate = (GUIDE_IMAGES_DIR / text).resolve()
        try:
            candidate.relative_to(GUIDE_IMAGES_DIR.resolve())
        except ValueError:
            return ""
        return str(candidate) if candidate.exists() else ""

    def _category_sort_key(self, category: str) -> tuple[int, str]:
        canonical = self._canonical_category(category)
        return self._category_orders.get(canonical, 9999), normalize_text(canonical)

    def _search_sort_key(self, guide: Guide, tokens: list[str]) -> tuple[int, int, int, str]:
        def matches(value: str) -> bool:
            text = normalize_text(value)
            return all(token in text for token in tokens)

        reward_name = guide.reward_item.name if guide.reward_item is not None else ""
        context_labels = " ".join(ref.label for ref in guide.context_entities)
        step_titles = " ".join(step.display_title for step in guide.steps)
        if matches(guide.title) or matches(reward_name):
            bucket = 0
        elif matches(context_labels):
            bucket = 1
        elif matches(step_titles):
            bucket = 2
        else:
            bucket = 3
        broad_penalty = 1 if guide.category == "aventure" and bucket else 0
        return bucket, broad_penalty, guide.order, normalize_text(guide.title)

    @staticmethod
    def _canonical_category(value: Any) -> str:
        text = str(value or "").strip()
        key = normalize_text(text)
        aliases = {
            "aventure": "aventure",
            "guide_complet": "aventure",
            "dofus": "dofus",
            "alignement": "alignements",
            "alignements": "alignements",
            "alignement_bonta": "alignements",
            "alignement_brakmar": "alignements",
        }
        return aliases.get(key, key)

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("JSON guide illisible %s: %s", path, exc)
            return default


def _first_int(values: Any) -> int | None:
    if not isinstance(values, list):
        return None
    for value in values:
        ident = safe_int(value)
        if ident is not None:
            return ident
    return None
