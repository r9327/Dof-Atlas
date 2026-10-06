from __future__ import annotations

from typing import Any

from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    ACHIEVEMENT_PROGRESS_FILE,
    AchievementProgressService as SerializedAchievementProgressService,
)


class AchievementProgressService(SerializedAchievementProgressService):
    """Serialized progress service that consumes compact Guide summaries when available."""

    @staticmethod
    def _alignment_main_quest_ids(guide_provider: Any) -> dict[str, tuple[int, ...]]:
        if guide_provider is None:
            return {}
        try:
            from app.modules.encyclopedia.achievement_catalog_policy import ALIGNMENT_GUIDE_IDS
        except Exception:
            return {}

        summary_getter = getattr(guide_provider, "get_summary_by_id", None)
        detail_getter = getattr(guide_provider, "get_by_id", None)
        getter = summary_getter if callable(summary_getter) else detail_getter
        if not callable(getter):
            return {}

        result: dict[str, tuple[int, ...]] = {}
        for side, guide_id in ALIGNMENT_GUIDE_IDS.items():
            try:
                guide = getter(guide_id)
            except Exception:
                guide = None
            if guide is None:
                continue
            quest_ids: list[int] = []
            for step in tuple(getattr(guide, "required_steps", ()) or ()):
                if str(getattr(step, "step_type", "")) != "quest":
                    continue
                entity_id = getattr(step, "entity_id", None)
                try:
                    quest_id = int(entity_id)
                except (TypeError, ValueError):
                    continue
                if quest_id not in quest_ids:
                    quest_ids.append(quest_id)
            result[str(side)] = tuple(quest_ids)
        return result


__all__ = ["ACHIEVEMENT_PROGRESS_FILE", "AchievementProgressService"]
