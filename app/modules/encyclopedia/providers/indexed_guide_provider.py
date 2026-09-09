from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

from app.modules.encyclopedia.models import EntityRef, GuideSection
from app.modules.encyclopedia.providers.achievement_provider import safe_int
from app.modules.encyclopedia.providers.guide_provider import GuideProvider
from app.quest_catalog import doduda_rows, read_json_file, text_for


_ACHIEVEMENT_NAME_CACHE: dict[str, dict[int, str]] = {}
_ACHIEVEMENT_NAME_LOCK = Lock()


def _achievement_name_index(data_dir: Path) -> dict[int, str]:
    """Load only the two sources needed to resolve achievement labels in Guides.

    Guide parsing only needs achievement ids/names for links. Loading the complete
    AchievementProvider here would also parse objectives, rewards, monsters,
    dungeons, items, spells and other large sources before the Successes tab is
    requested.
    """

    root = Path(data_dir)
    key = str(root.resolve(strict=False))
    cached = _ACHIEVEMENT_NAME_CACHE.get(key)
    if cached is not None:
        return cached

    with _ACHIEVEMENT_NAME_LOCK:
        cached = _ACHIEVEMENT_NAME_CACHE.get(key)
        if cached is not None:
            return cached

        language = read_json_file(root / "languages" / "fr.json", {"entries": {}})
        entries = language.get("entries", {}) if isinstance(language, dict) else {}
        if not isinstance(entries, dict):
            entries = {}
        rows = doduda_rows(root / "achievements.json")
        names = {
            int(achievement_id): text_for(
                entries,
                row.get("nameId"),
                f"Succès {achievement_id}",
            )
            for achievement_id, row in rows.items()
        }
        _ACHIEVEMENT_NAME_CACHE[key] = names
        return names


class IndexedGuideProvider(GuideProvider):
    """Guide provider that does not force the rich Success catalogue to load.

    GuideProvider historically resolved achievement links through get_by_id(),
    which materializes the whole AchievementProvider. For Guide construction we
    only need a stable id and localized label, so this provider uses a small name
    index until the shared AchievementProvider has genuinely been loaded.
    """

    def _achievement_name(self, achievement_id: int) -> str | None:
        provider = self.achievement_provider
        if getattr(provider, "_loaded", False):
            achievement = provider.get_by_id(int(achievement_id))
            return achievement.name if achievement is not None else None
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
