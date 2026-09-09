from __future__ import annotations

from PySide6.QtCore import Signal

from app.modules.encyclopedia.services.guide_quest_view_model import (
    quest_rewards,
    reward_label,
)
from app.modules.encyclopedia.views.guides_view import (
    GUIDE_ULTIME_LEGACY_ID,
    GuidesView as _OptimizedGuidesView,
)


class DeferredAchievementGuidesView(_OptimizedGuidesView):
    """Paint Guide content before the rich Success runtime is required."""

    achievementRuntimeRequested = Signal()

    def __init__(self, *args, **kwargs) -> None:
        self._deferred_guide_id = ""
        self._deferred_achievement_context_id: int | None = None
        self._deferred_quest_id: int | None = None
        self._deferred_quest_preserve_scroll = False
        super().__init__(*args, **kwargs)

    def _achievement_runtime_ready(self) -> bool:
        provider = getattr(self, "achievement_provider", None)
        return bool(provider is not None and getattr(provider, "_loaded", False))

    def _sync_achievement_progress(self) -> bool:
        # Character changes and external refreshes can happen after construction.
        # Never let those paths turn a cold Success provider into a synchronous
        # full-catalogue read on the Qt thread.
        if not self._achievement_runtime_ready():
            return False
        return bool(super()._sync_achievement_progress())

    def _selected_series_rewards(self, guide):
        """Quest rewards never need the Success provider.

        The legacy implementation queried every quest's linked achievements even
        though quest_rewards() deliberately ignores that argument. Keep the exact
        visible reward result without waking the large Success catalogue.
        """

        series_ref = self._selected_series_ref(guide)
        if series_ref is None:
            return []
        _part, _chapter, series = series_ref
        rewards = []
        seen: set[tuple[str, str]] = set()
        for step in sorted(series.steps, key=lambda item: item.order):
            if step.step_type != "quest" or step.entity_id is None:
                continue
            quest = self.quest_catalog.by_id.get(int(step.entity_id))
            if quest is None:
                continue
            for reward in quest_rewards(quest):
                key = (
                    reward_label(reward),
                    str(getattr(reward, "image_path", "") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                rewards.append(reward)
        return rewards

    def _populate_guide_info(self, guide) -> None:
        if self._achievement_runtime_ready():
            super()._populate_guide_info(guide)
            return

        # Non-adventure guide rewards can include achievement rewards. Render
        # every quest/guide-native section now and enrich the Success-only rewards
        # once the shared provider finishes loading in the background.
        provider = self.achievement_provider
        self.achievement_provider = None
        try:
            super()._populate_guide_info(guide)
        finally:
            self.achievement_provider = provider

    def select_guide(self, guide_id: str) -> bool:
        guide_id = str(guide_id or "")
        if not guide_id:
            return False

        # Guide Ultime builds a rich auto-validation contract that genuinely uses
        # Success data. Keep that one action deferred instead of doing the read on
        # the UI thread. Ordinary guides can paint immediately from the Guide index.
        if guide_id == GUIDE_ULTIME_LEGACY_ID and not self._achievement_runtime_ready():
            self._deferred_guide_id = guide_id
            self.status_callback("Préparation du Guide Ultime en arrière-plan...")
            self.achievementRuntimeRequested.emit()
            return True

        selected = bool(super().select_guide(guide_id))
        if selected and not self._achievement_runtime_ready():
            self.status_callback("Guide affiché · enrichissement Succès en arrière-plan...")
            self.achievementRuntimeRequested.emit()
        return selected

    def show_quest_detail(self, quest_id: int, preserve_scroll: bool = False) -> bool:
        if not self._achievement_runtime_ready():
            self._deferred_quest_id = int(quest_id)
            self._deferred_quest_preserve_scroll = bool(preserve_scroll)
            self.status_callback("Préparation des données liées à la quête en arrière-plan...")
            self.achievementRuntimeRequested.emit()
            return True
        return bool(super().show_quest_detail(quest_id, preserve_scroll=preserve_scroll))

    def open_achievement_context(self, achievement_id: int) -> bool:
        if not self._achievement_runtime_ready():
            self._deferred_achievement_context_id = int(achievement_id)
            self.status_callback("Préparation du contexte Succès en arrière-plan...")
            self.achievementRuntimeRequested.emit()
            return True
        return bool(super().open_achievement_context(achievement_id))

    def apply_achievement_runtime(self) -> bool:
        """Project rich Success data once, enrich the active Guide, then resume."""

        if not self._achievement_runtime_ready():
            return False

        changed = bool(super()._sync_achievement_progress())
        self.quest_progress = self.quest_progress_service.reload()
        self._home_progress_cache_signature = None
        self._home_render_signature = None
        self.refresh_home()

        # Provider readiness is not represented by the progress-file signature.
        # Explicitly redraw an already-visible normal Guide once so achievement
        # rewards/links appear even when synchronization did not modify a file.
        active_guide_id = str(self.current_guide_id or "")
        if (
            active_guide_id
            and active_guide_id != GUIDE_ULTIME_LEGACY_ID
            and self.current_quest_id is None
            and self.state == self.GUIDE_OVERVIEW
        ):
            super().show_guide_overview(active_guide_id, preserve_scroll=True)
        elif (
            active_guide_id == GUIDE_ULTIME_LEGACY_ID
            and self.guide_ultime_view is not None
        ):
            self.guide_ultime_view.refresh_external_progress()
        self._mark_external_progress_refreshed()

        guide_id = self._deferred_guide_id
        context_id = self._deferred_achievement_context_id
        quest_id = self._deferred_quest_id
        preserve_scroll = self._deferred_quest_preserve_scroll
        self._deferred_guide_id = ""
        self._deferred_achievement_context_id = None
        self._deferred_quest_id = None
        self._deferred_quest_preserve_scroll = False

        if context_id is not None:
            super().open_achievement_context(context_id)
        elif guide_id:
            super().select_guide(guide_id)
        elif quest_id is not None:
            super().show_quest_detail(quest_id, preserve_scroll=preserve_scroll)
        return changed


__all__ = ["DeferredAchievementGuidesView"]
