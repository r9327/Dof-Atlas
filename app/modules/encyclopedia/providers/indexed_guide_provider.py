from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from app.constants import ROOT_DIR
from app.modules.encyclopedia.models import EntityRef, GuideSection
from app.modules.encyclopedia.providers.achievement_provider import safe_int
from app.modules.encyclopedia.providers.guide_provider import GuideProvider


_ACHIEVEMENT_NAME_CACHE: dict[str, dict[int, str]] = {}
_ACHIEVEMENT_NAME_LOCK = Lock()
_ACHIEVEMENT_NAMES_FILE = (
    ROOT_DIR / ".cache" / "dofus_atlas" / "achievement_sources_v1" / "achievement_names.json"
)



def _achievement_name_index(data_dir: Path) -> dict[int, str]:
    """Read the compact name index prepared by preload; never start a runtime worker."""

    from app.constants import RAW_QUEST_DATA_DIR

    root = Path(data_dir)
    key = str(root.resolve(strict=False))
    cached = _ACHIEVEMENT_NAME_CACHE.get(key)
    if cached is not None:
        return cached

    with _ACHIEVEMENT_NAME_LOCK:
        cached = _ACHIEVEMENT_NAME_CACHE.get(key)
        if cached is not None:
            return cached
        if root.resolve(strict=False) != Path(RAW_QUEST_DATA_DIR).resolve(strict=False):
            return {}
        try:
            payload = json.loads(_ACHIEVEMENT_NAMES_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        names = {
            int(achievement_id): str(name)
            for achievement_id, name in payload.items()
            if str(achievement_id).lstrip("-").isdigit()
        }
        _ACHIEVEMENT_NAME_CACHE[key] = names
        return names

def _drop_nested_raw(value: object, *keys: str) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    excluded = set(keys)
    return {key: item for key, item in value.items() if key not in excluded}


class IndexedGuideProvider(GuideProvider):
    """Guide provider with compact link indexes and non-duplicated raw trees."""

    def _load(self) -> None:
        super()._load()
        # Guide JSON already has typed models for every structural child. Keeping
        # those same child arrays inside each parent's raw dict pins the original
        # parsed JSON tree in memory a second time. Preserve scalar/metadata raw
        # fields used by compatibility code, but cut only structural duplicates.
        for guide in self._guides:
            object.__setattr__(guide, "raw", _drop_nested_raw(guide.raw, "sections", "parts"))
            for section in guide.sections:
                object.__setattr__(section, "raw", _drop_nested_raw(section.raw, "steps"))
            for part in guide.parts:
                object.__setattr__(part, "raw", _drop_nested_raw(part.raw, "chapters"))
                for chapter in part.chapters:
                    object.__setattr__(chapter, "raw", _drop_nested_raw(chapter.raw, "series"))
                    for series in chapter.series:
                        object.__setattr__(series, "raw", _drop_nested_raw(series.raw, "steps"))

    def _achievement_name(self, achievement_id: int) -> str | None:
        provider = self.achievement_provider
        if getattr(provider, "_loaded", False):
            achievement = provider.get_by_id(int(achievement_id))
            if achievement is not None:
                return achievement.name
        return _achievement_name_index(provider.data_dir).get(int(achievement_id))

    def _context_entities(
        self,
        payload: dict[str, Any],
        sections: tuple[GuideSection, ...],
    ) -> tuple[tuple[EntityRef, ...], list[str]]:
        refs: dict[tuple[str, int], EntityRef] = {}
        errors: list[str] = []

        def add_achievement(raw_id: Any) -> None:
            achievement_id = safe_int(raw_id)
            if achievement_id is None:
                return
            name = self._achievement_name(achievement_id)
            if name is None:
                errors.append(f"succes contextuel inexistant: {achievement_id}")
                return
            refs.setdefault(
                ("achievement", achievement_id),
                EntityRef("achievement", achievement_id, name),
            )

        root_ids = payload.get("linked_achievement_ids", [])
        if isinstance(root_ids, list):
            for achievement_id in root_ids:
                add_achievement(achievement_id)
        for section in sections:
            section_ids = (
                section.raw.get("linked_achievement_ids", [])
                if isinstance(section.raw, dict)
                else []
            )
            if isinstance(section_ids, list):
                for achievement_id in section_ids:
                    add_achievement(achievement_id)
        return tuple(refs.values()), errors

    def _resolve_entity(
        self,
        step_type: str,
        entity_id: int | None,
        step_row: dict[str, Any],
    ) -> tuple[EntityRef | None, bool, list[str]]:
        if step_type != "achievement":
            return super()._resolve_entity(step_type, entity_id, step_row)

        title = str(step_row.get("title") or "").strip()
        if entity_id is None:
            return None, False, ["entity_id absent pour achievement"]
        name = self._achievement_name(entity_id)
        if name is None:
            return (
                EntityRef("achievement", entity_id, title or f"Succes {entity_id}"),
                False,
                [f"succes inexistant: {entity_id}"],
            )
        return EntityRef("achievement", entity_id, name), True, []


__all__ = ["IndexedGuideProvider"]
