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

        # Compact Guide summaries deliberately have no required_steps. The
        # progress index is the authoritative lightweight quest-ID source.
        compact_ids = getattr(guide_provider, "progress_quest_ids_for", None)
        summary_getter = getattr(guide_provider, "get_summary_by_id", None)
        # Only detail-only legacy providers may use get_by_id. Never hydrate a
        # Guide when the production compact index is available.
        getter = (
            summary_getter
            if callable(summary_getter)
            else getattr(guide_provider, "get_by_id", None)
            if not callable(compact_ids)
            else None
        )
        if not callable(compact_ids) and not callable(getter):
            return {}

        result: dict[str, tuple[int, ...]] = {}
        for side, guide_id in ALIGNMENT_GUIDE_IDS.items():
            if callable(compact_ids):
                try:
                    quest_ids = tuple(
                        dict.fromkeys(int(value) for value in compact_ids(guide_id))
                    )
                except (TypeError, ValueError):
                    quest_ids = ()
                if quest_ids:
                    result[str(side)] = quest_ids
                    continue

            if not callable(getter):
                continue
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
