from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from app.modules.encyclopedia.models import EntityRef, Guide, GuideSection, GuideStep
from app.modules.encyclopedia.providers.achievement_provider import safe_int
from app.modules.encyclopedia.providers.guide_provider import (
    DOFUS_UNKNOWN_ICON,
    GUIDE_COMPLETENESS_STATUSES,
)
from app.modules.encyclopedia.providers.indexed_guide_provider import (
    IndexedGuideProvider,
    _drop_nested_raw,
)
from app.quest_catalog import normalize_text


_INDEXED_ENTITY_TYPES = frozenset(
    {"quest", "achievement", "dungeon", "monster", "wanted", "archmonster"}
)
_SEARCH_KEYS = frozenset({"title", "description", "notes", "content", "label", "source_reference"})


def _walk_dicts(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


class MemoryBoundGuideProvider(IndexedGuideProvider):
    """Keep only Guide catalogue summaries resident; materialize one detail on demand."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._detail_entries: dict[str, tuple[Path, int, dict[str, Any]]] = {}
        self._detail_cache_id = ""
        self._detail_cache: Guide | None = None

    def release_detail_cache(self) -> None:
        self._detail_cache_id = ""
        self._detail_cache = None

    def reload(self) -> list[Guide]:
        self.release_detail_cache()
        self._detail_entries = {}
        return super().reload()

    def get_by_id(self, guide_id: str) -> Guide | None:
        self._ensure_loaded()
        key = str(guide_id)
        if self._detail_cache_id == key and self._detail_cache is not None:
            return self._detail_cache
        entry = self._detail_entries.get(key)
        if entry is None:
            return None
        path, order, catalog_entry = entry
        guide = super()._load_guide(path, order, catalog_entry)
        if guide is None:
            return None
        self._compact_detail_raw(guide)
        self._detail_cache_id = key
        self._detail_cache = guide
        return guide

    def get_summary_by_id(self, guide_id: str) -> Guide | None:
        self._ensure_loaded()
        return self._by_id.get(str(guide_id))

    def _load(self) -> None:
        entries = self._guide_entries()
        summaries: list[Guide] = []
        by_entity_ids: dict[tuple[str, int], set[str]] = defaultdict(set)
        seen_ids: set[str] = set()
        self._detail_entries = {}

        for order, (path, catalog_entry) in enumerate(entries):
            payload = self._read_json(path, None)
            if not isinstance(payload, dict):
                continue
            guide_id = str(payload.get("id") or catalog_entry.get("id") or path.stem).strip()
            if not guide_id or guide_id in seen_ids:
                continue
            completeness = str(payload.get("completeness_status") or "complete").strip().casefold()
            if completeness not in GUIDE_COMPLETENESS_STATUSES:
                completeness = "draft"
            if completeness == "draft" and not self.include_drafts:
                continue
            summary, entity_keys = self._summary_from_payload(
                payload,
                catalog_entry,
                guide_id=guide_id,
                order=order,
                source_file=path.name,
            )
            seen_ids.add(guide_id)
            summaries.append(summary)
            self._detail_entries[guide_id] = (path, order, dict(catalog_entry))
            for entity_key in entity_keys:
                by_entity_ids[entity_key].add(guide_id)

        self._guides = sorted(
            summaries,
            key=lambda guide: (
                self._category_sort_key(guide.category),
                guide.order,
                normalize_text(guide.title),
                guide.id,
            ),
        )
        self._by_id = {guide.id: guide for guide in self._guides}

        by_category: dict[str, list[Guide]] = defaultdict(list)
        for guide in self._guides:
            by_category[guide.category].append(guide)
        self._by_category = defaultdict(
            list,
            {
                category: sorted(values, key=lambda guide: (guide.order, normalize_text(guide.title), guide.id))
                for category, values in by_category.items()
            },
        )
        self._by_entity = defaultdict(
            list,
            {
                entity_key: [self._by_id[guide_id] for guide_id in sorted(guide_ids) if guide_id in self._by_id]
                for entity_key, guide_ids in by_entity_ids.items()
            },
        )

    def _summary_from_payload(
        self,
        payload: dict[str, Any],
        catalog_entry: dict[str, Any],
        *,
        guide_id: str,
        order: int,
        source_file: str,
    ) -> tuple[Guide, set[tuple[str, int]]]:
        category = self._canonical_category(catalog_entry.get("category") or payload.get("category"))
        category_label = self.get_category_label(category)
        reward_item_id = safe_int(payload.get("reward_item_id"))
        illustration_item_id = safe_int(payload.get("illustration_item_id"))
        reward_item = self.dofus_item_provider.get_by_id(reward_item_id)
        illustration_item = self.dofus_item_provider.get_by_id(illustration_item_id)
        image_path = self._resolve_image_path(payload.get("image"))
        if not image_path and illustration_item is not None:
            image_path = illustration_item.image_path
        if not image_path and DOFUS_UNKNOWN_ICON.exists():
            image_path = str(DOFUS_UNKNOWN_ICON)

        quest_order: list[int] = []
        quest_optional: dict[int, bool] = {}
        entity_keys: set[tuple[str, int]] = set()
        achievement_ids: set[int] = set()
        search_values: list[str] = [
            str(payload.get("title") or guide_id),
            str(payload.get("description") or ""),
            category,
            category_label,
        ]

        nodes = list(_walk_dicts(payload))
        for node in nodes:
            for key in _SEARCH_KEYS:
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    search_values.append(value.strip())

            linked = node.get("linked_achievement_ids")
            if isinstance(linked, list):
                for raw_id in linked:
                    achievement_id = safe_int(raw_id)
                    if achievement_id is not None:
                        achievement_ids.add(achievement_id)
                        entity_keys.add(("achievement", achievement_id))

            step_type = str(node.get("type") or node.get("step_type") or "").strip()
            entity_id = safe_int(node.get("entity_id"))
            if step_type in _INDEXED_ENTITY_TYPES and entity_id is not None:
                entity_keys.add((step_type, entity_id))
                if step_type == "achievement":
                    achievement_ids.add(entity_id)
                if step_type == "quest":
                    if entity_id not in quest_optional:
                        quest_order.append(entity_id)
                        quest_optional[entity_id] = bool(node.get("optional", False))
                    else:
                        quest_optional[entity_id] = quest_optional[entity_id] and bool(
                            node.get("optional", False)
                        )

        # Older series may expose quest_ids without explicit step rows.
        for node in nodes:
            raw_ids = node.get("quest_ids")
            if not isinstance(raw_ids, list):
                continue
            for raw_id in raw_ids:
                quest_id = safe_int(raw_id)
                if quest_id is None:
                    continue
                entity_keys.add(("quest", quest_id))
                if quest_id not in quest_optional:
                    quest_order.append(quest_id)
                    quest_optional[quest_id] = False

        catalog = self.quest_provider.get_catalog()
        summary_steps: list[GuideStep] = []
        for step_order, quest_id in enumerate(quest_order, 1):
            quest = catalog.by_id.get(quest_id)
            title = quest.name if quest is not None else f"Quête {quest_id}"
            search_values.append(title)
            summary_steps.append(
                GuideStep(
                    id=f"{guide_id}__summary_quest_{quest_id}",
                    step_type="quest",
                    order=step_order,
                    title=title,
                    entity_id=quest_id,
                    optional=quest_optional.get(quest_id, False),
                )
            )

        context_entities: list[EntityRef] = []
        for achievement_id in sorted(achievement_ids):
            name = self._achievement_name(achievement_id) or f"Succès {achievement_id}"
            search_values.append(name)
            context_entities.append(EntityRef("achievement", achievement_id, name))

        sections = (
            GuideSection(
                id=f"{guide_id}__summary",
                title="",
                order=0,
                steps=tuple(summary_steps),
            ),
        ) if summary_steps else ()

        completeness = str(payload.get("completeness_status") or "complete").strip().casefold()
        if completeness not in GUIDE_COMPLETENESS_STATUSES:
            completeness = "draft"
        summary = Guide(
            id=guide_id,
            title=str(payload.get("title") or guide_id).strip(),
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
            completeness_status=completeness,
            verified_steps=safe_int(payload.get("verified_steps")),
            total_steps=safe_int(payload.get("total_steps")),
            validation_warnings=tuple(
                str(value).strip()
                for value in payload.get("validation_warnings", [])
                if str(value).strip()
            ) if isinstance(payload.get("validation_warnings"), list) else (),
            generation_source=str(payload.get("generation_source") or "").strip(),
            sections=sections,
            context_entities=tuple(context_entities),
            search_text=normalize_text(" ".join(search_values)),
            raw={"source_file": source_file},
        )
        return summary, entity_keys

    @staticmethod
    def _compact_detail_raw(guide: Guide) -> None:
        object.__setattr__(guide, "raw", _drop_nested_raw(guide.raw, "sections", "parts"))
        for section in guide.sections:
            object.__setattr__(section, "raw", _drop_nested_raw(section.raw, "steps"))
        for part in guide.parts:
            object.__setattr__(part, "raw", _drop_nested_raw(part.raw, "chapters"))
            for chapter in part.chapters:
                object.__setattr__(chapter, "raw", _drop_nested_raw(chapter.raw, "series"))
                for series in chapter.series:
                    object.__setattr__(series, "raw", _drop_nested_raw(series.raw, "steps"))


__all__ = ["MemoryBoundGuideProvider"]
