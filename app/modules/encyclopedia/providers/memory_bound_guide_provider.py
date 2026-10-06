from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from app.constants import ROOT_DIR
from app.modules.encyclopedia.models import EntityRef, Guide, GuideSection, GuideStep
from app.modules.encyclopedia.providers.achievement_provider import safe_int
from app.modules.encyclopedia.providers.guide_provider import (
    DOFUS_UNKNOWN_ICON,
    GUIDE_COMPLETENESS_STATUSES,
    GUIDES_DIR,
)
from app.modules.encyclopedia.providers.indexed_guide_provider import (
    IndexedGuideProvider,
    _drop_nested_raw,
)
from app.quest_catalog import normalize_text


_DUMP_COMPACT_FLAG = "--dump-compact"
_INDEXED_ENTITY_TYPES = frozenset(
    {"quest", "achievement", "dungeon", "monster", "wanted", "archmonster"}
)
_PROGRESS_STEP_TYPES = frozenset({"quest", "achievement", "info"})
_SEARCH_KEYS = frozenset({"title", "description", "notes", "content", "label", "source_reference"})


def _walk_dicts(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _entity_ref_payload(ref: EntityRef) -> dict[str, object]:
    return {
        "entity_type": ref.entity_type,
        "entity_id": ref.entity_id,
        "label": ref.label,
    }


def _summary_payload(guide: Guide, entity_keys: set[tuple[str, int]]) -> dict[str, object]:
    return {
        "id": guide.id,
        "title": guide.title,
        "category": guide.category,
        "category_label": guide.category_label,
        "description": guide.description,
        "recommended_level_min": guide.recommended_level_min,
        "recommended_level_max": guide.recommended_level_max,
        "reward_item_id": guide.reward_item_id,
        "illustration_item_id": guide.illustration_item_id,
        "image_path": guide.image_path,
        "order": guide.order,
        "completeness_status": guide.completeness_status,
        "verified_steps": guide.verified_steps,
        "total_steps": guide.total_steps,
        "validation_warnings": list(guide.validation_warnings),
        "generation_source": guide.generation_source,
        "steps": [
            {
                "id": step.id,
                "step_type": step.step_type,
                "order": step.order,
                "title": step.title,
                "entity_id": step.entity_id,
                "optional": step.optional,
            }
            for step in guide.steps
        ],
        "context_entities": [_entity_ref_payload(ref) for ref in guide.context_entities],
        "search_text": guide.search_text,
        "source_file": str(guide.raw.get("source_file") or ""),
        "entity_keys": [[entity_type, entity_id] for entity_type, entity_id in sorted(entity_keys)],
    }


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

    def release_catalogue(self) -> None:
        """Drop reconstructible Guide summaries/details while keeping the provider reusable."""

        self.release_detail_cache()
        self._loaded = False
        self._guides = []
        self._by_id = {}
        self._by_category = defaultdict(list)
        self._by_entity = defaultdict(list)
        self._detail_entries = {}
        self.validation_errors = []

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
        default_guides_dir = Path(GUIDES_DIR).resolve(strict=False)
        current_guides_dir = Path(self.guides_dir).resolve(strict=False)
        if bool(getattr(sys, "frozen", False)) or current_guides_dir != default_guides_dir:
            self._load_in_process()
            return
        self._load_from_compact_subprocess()

    def _load_from_compact_subprocess(self) -> None:
        # Reading guide_complet.json in Atlas temporarily creates a very large
        # Python object graph. Windows' allocator keeps many of those arenas
        # reserved after json.loads() returns. Build summaries in a disposable
        # process so only the compact rows ever enter Atlas' long-lived heap.
        entries = self._guide_entries()
        entry_by_file = {
            path.name: (path, order, dict(catalog_entry))
            for order, (path, catalog_entry) in enumerate(entries)
        }
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.modules.encyclopedia.providers.memory_bound_guide_provider",
                _DUMP_COMPACT_FLAG,
            ],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=True,
        )
        summaries: list[Guide] = []
        by_entity_ids: dict[tuple[str, int], set[str]] = defaultdict(set)
        self._detail_entries = {}
        for raw_line in completed.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                continue
            guide = self._summary_from_compact_row(row)
            source_file = str(row.get("source_file") or "")
            entry = entry_by_file.get(source_file)
            if entry is None:
                continue
            summaries.append(guide)
            self._detail_entries[guide.id] = entry
            raw_entity_keys = row.get("entity_keys")
            if isinstance(raw_entity_keys, list):
                for raw_key in raw_entity_keys:
                    if not isinstance(raw_key, list) or len(raw_key) != 2:
                        continue
                    entity_type = str(raw_key[0] or "")
                    entity_id = safe_int(raw_key[1])
                    if entity_type and entity_id is not None:
                        by_entity_ids[(entity_type, entity_id)].add(guide.id)
        if not summaries:
            raise RuntimeError("L'extraction compacte des Guides n'a produit aucun résultat")
        self._install_summaries(summaries, by_entity_ids)

    def _load_in_process(self) -> None:
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

        self._install_summaries(summaries, by_entity_ids)

    def _install_summaries(
        self,
        summaries: list[Guide],
        by_entity_ids: dict[tuple[str, int], set[str]],
    ) -> None:
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
                category: sorted(
                    values,
                    key=lambda guide: (guide.order, normalize_text(guide.title), guide.id),
                )
                for category, values in by_category.items()
            },
        )
        self._by_entity = defaultdict(
            list,
            {
                entity_key: [
                    self._by_id[guide_id]
                    for guide_id in sorted(guide_ids)
                    if guide_id in self._by_id
                ]
                for entity_key, guide_ids in by_entity_ids.items()
            },
        )

    def _summary_from_compact_row(self, row: dict[str, Any]) -> Guide:
        reward_item_id = safe_int(row.get("reward_item_id"))
        illustration_item_id = safe_int(row.get("illustration_item_id"))
        reward_item = self.dofus_item_provider.get_by_id(reward_item_id)
        illustration_item = self.dofus_item_provider.get_by_id(illustration_item_id)

        steps: list[GuideStep] = []
        raw_steps = row.get("steps")
        if isinstance(raw_steps, list):
            for raw_step in raw_steps:
                if not isinstance(raw_step, dict):
                    continue
                steps.append(
                    GuideStep(
                        id=str(raw_step.get("id") or ""),
                        step_type=str(raw_step.get("step_type") or "info"),
                        order=int(raw_step.get("order") or len(steps) + 1),
                        title=str(raw_step.get("title") or ""),
                        entity_id=safe_int(raw_step.get("entity_id")),
                        optional=bool(raw_step.get("optional", False)),
                    )
                )
        refs: list[EntityRef] = []
        raw_refs = row.get("context_entities")
        if isinstance(raw_refs, list):
            for raw_ref in raw_refs:
                if not isinstance(raw_ref, dict):
                    continue
                entity_id = raw_ref.get("entity_id")
                if entity_id is None:
                    continue
                refs.append(
                    EntityRef(
                        str(raw_ref.get("entity_type") or ""),
                        entity_id,
                        str(raw_ref.get("label") or ""),
                    )
                )
        sections = (
            GuideSection(
                id=f"{row.get('id')}__summary",
                title="",
                order=0,
                steps=tuple(steps),
            ),
        ) if steps else ()
        return Guide(
            id=str(row.get("id") or ""),
            title=str(row.get("title") or ""),
            category=str(row.get("category") or ""),
            category_label=str(row.get("category_label") or ""),
            description=str(row.get("description") or ""),
            recommended_level_min=safe_int(row.get("recommended_level_min")),
            recommended_level_max=safe_int(row.get("recommended_level_max")),
            reward_item_id=reward_item_id,
            illustration_item_id=illustration_item_id,
            reward_item=reward_item,
            illustration_item=illustration_item,
            image_path=str(row.get("image_path") or ""),
            order=int(row.get("order") or 0),
            completeness_status=str(row.get("completeness_status") or "complete"),
            verified_steps=safe_int(row.get("verified_steps")),
            total_steps=safe_int(row.get("total_steps")),
            validation_warnings=tuple(str(value) for value in row.get("validation_warnings", [])),
            generation_source=str(row.get("generation_source") or ""),
            sections=sections,
            context_entities=tuple(refs),
            search_text=str(row.get("search_text") or ""),
            raw={"source_file": str(row.get("source_file") or "")},
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

        entity_keys: set[tuple[str, int]] = set()
        achievement_ids: set[int] = set()
        progress_steps: list[GuideStep] = []
        progress_step_keys: set[tuple[str, object]] = set()
        search_chunks: set[str] = {
            normalize_text(str(payload.get("title") or guide_id)),
            normalize_text(str(payload.get("description") or "")),
            normalize_text(category),
            normalize_text(category_label),
        }
        catalog = self.quest_provider.get_catalog()

        for node in _walk_dicts(payload):
            for key in _SEARCH_KEYS:
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    normalized = normalize_text(value)
                    if normalized:
                        search_chunks.add(normalized)

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

            if step_type in _PROGRESS_STEP_TYPES:
                raw_step_id = str(node.get("id") or "").strip()
                identity: tuple[str, object]
                if raw_step_id:
                    identity = (step_type, raw_step_id)
                elif entity_id is not None:
                    identity = (step_type, entity_id)
                else:
                    identity = (step_type, len(progress_steps))
                if identity not in progress_step_keys:
                    progress_step_keys.add(identity)
                    title = str(node.get("title") or "").strip()
                    if step_type == "quest" and entity_id is not None:
                        quest = catalog.by_id.get(entity_id)
                        if quest is not None:
                            title = quest.name
                            search_chunks.add(normalize_text(quest.name))
                    elif step_type == "achievement" and entity_id is not None:
                        name = self._achievement_name(entity_id)
                        if name:
                            title = name
                            search_chunks.add(normalize_text(name))
                    progress_steps.append(
                        GuideStep(
                            id=raw_step_id or f"{guide_id}__summary_{step_type}_{entity_id if entity_id is not None else len(progress_steps)}",
                            step_type=step_type,
                            order=safe_int(node.get("order"), len(progress_steps) + 1) or len(progress_steps) + 1,
                            title=title,
                            entity_id=entity_id,
                            optional=bool(node.get("optional", False)),
                        )
                    )

            raw_ids = node.get("quest_ids")
            if isinstance(raw_ids, list):
                for raw_id in raw_ids:
                    quest_id = safe_int(raw_id)
                    if quest_id is None:
                        continue
                    entity_keys.add(("quest", quest_id))
                    identity = ("quest", quest_id)
                    if identity in progress_step_keys:
                        continue
                    progress_step_keys.add(identity)
                    quest = catalog.by_id.get(quest_id)
                    title = quest.name if quest is not None else f"Quête {quest_id}"
                    search_chunks.add(normalize_text(title))
                    progress_steps.append(
                        GuideStep(
                            id=f"{guide_id}__summary_quest_{quest_id}",
                            step_type="quest",
                            order=len(progress_steps) + 1,
                            title=title,
                            entity_id=quest_id,
                        )
                    )

        context_entities: list[EntityRef] = []
        for achievement_id in sorted(achievement_ids):
            name = self._achievement_name(achievement_id) or f"Succès {achievement_id}"
            search_chunks.add(normalize_text(name))
            context_entities.append(EntityRef("achievement", achievement_id, name))

        sections = (
            GuideSection(
                id=f"{guide_id}__summary",
                title="",
                order=0,
                steps=tuple(progress_steps),
            ),
        ) if progress_steps else ()

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
            search_text="_".join(sorted(chunk for chunk in search_chunks if chunk)),
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


def _dump_compact_default_guides() -> int:
    provider = MemoryBoundGuideProvider(guides_dir=GUIDES_DIR)
    provider._load_in_process()
    for guide in provider._guides:
        entity_keys = {
            entity_key
            for entity_key, guides in provider._by_entity.items()
            if any(candidate.id == guide.id for candidate in guides)
        }
        print(
            json.dumps(
                _summary_payload(guide, entity_keys),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    return 0


if __name__ == "__main__" and _DUMP_COMPACT_FLAG in sys.argv:
    raise SystemExit(_dump_compact_default_guides())


__all__ = ["MemoryBoundGuideProvider"]
