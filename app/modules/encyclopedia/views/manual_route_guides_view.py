from __future__ import annotations

from app.modules.encyclopedia.services.guide_auto_validation_contract import (
    build_route_auto_validation_contract,
)
from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
    GuideCatalogManualRuntimeService,
)
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)
from app.modules.encyclopedia.views.guides_view import (
    GUIDE_ULTIME_LEGACY_ID,
    GuidesView as _BaseGuidesView,
)
from app.modules.encyclopedia.views.shared_manual_guide_view import (
    SharedGuideManualView,
)


CATALOG_MANUAL_GUIDE_IDS = frozenset({"dofus_sylvestre"})


class ManualRouteGuidesView(_BaseGuidesView):
    """Guides catalogue with shared road-book rendering for optimized routes."""

    def __init__(self, *args, **kwargs) -> None:
        self._catalog_manual_services: dict[str, GuideCatalogManualRuntimeService] = {}
        self._catalog_manual_views: dict[str, SharedGuideManualView] = {}
        super().__init__(*args, **kwargs)

    def ensure_guide_ultime_view(self) -> SharedGuideManualView | None:
        """Keep Guide Succès on the canonical service but use the shared renderer."""
        if self.guide_ultime_view is not None:
            return self.guide_ultime_view  # type: ignore[return-value]

        service = self.guide_ultime_service
        if service is None:
            service = GuideUltimeManualRuntimeService(
                self.quest_progress_service,
                self.achievement_progress_service,
                self.guide_progress_service,
                quest_provider=self.quest_provider,
                autoload=False,
            )
            if not service.available:
                service.load()
            service.achievement_provider = self.achievement_provider
            service.auto_validation_contract = build_route_auto_validation_contract(
                service.cards,
                achievement_provider=self.achievement_provider,
            )
            self.guide_ultime_service = service

        if not service.available:
            return None

        view = SharedGuideManualView(
            service,
            character_key=self.current_character_key,
            quest_provider=self.quest_provider,
            quest_graph=getattr(self, "graph", None),
        )
        view.navigate_entity = self.link_service.navigate_to_entity
        view.questProgressChanged.connect(self._on_guide_ultime_quest_progress_changed)
        self.stack.addWidget(view)
        self.guide_ultime_view = view
        self._refresh_guide_ultime_home_labels()
        return view

    def ensure_catalog_manual_view(self, guide_id: str) -> SharedGuideManualView | None:
        guide_id = str(guide_id or "")
        existing = self._catalog_manual_views.get(guide_id)
        if existing is not None:
            return existing

        guide = self.provider.get_by_id(guide_id)
        if guide is None:
            return None

        service = GuideCatalogManualRuntimeService(
            self.quest_progress_service,
            self.achievement_progress_service,
            self.guide_progress_service,
            guide=guide,
            quest_provider=self.quest_provider,
        )
        if not service.available:
            return None

        view = SharedGuideManualView(
            service,
            character_key=self.current_character_key,
            quest_provider=self.quest_provider,
            quest_graph=getattr(self, "graph", None),
        )
        view.navigate_entity = self.link_service.navigate_to_entity
        view.questProgressChanged.connect(
            lambda quest_id, gid=guide_id: self._on_catalog_manual_quest_progress_changed(
                gid,
                int(quest_id),
            )
        )
        self.stack.addWidget(view)
        self._catalog_manual_services[guide_id] = service
        self._catalog_manual_views[guide_id] = view
        return view

    def select_guide(self, guide_id: str) -> bool:
        guide_id = str(guide_id or "")
        if guide_id not in CATALOG_MANUAL_GUIDE_IDS:
            return bool(super().select_guide(guide_id))

        guide = self.provider.get_by_id(guide_id)
        view = self.ensure_catalog_manual_view(guide_id)
        service = self._catalog_manual_services.get(guide_id)
        if guide is None or view is None or service is None or not service.available:
            self.status_callback(f"Guide optimisé indisponible : {guide_id}")
            return False

        self.current_guide_id = guide_id
        self.current_quest_id = None
        self.state = self.GUIDE_OVERVIEW
        view.set_character_key(self.current_character_key)
        self.stack.setCurrentWidget(view)
        completed, total = service.route_sheet_progress(self.current_character_key)
        self.status_callback(
            f"{guide.title} — parcours optimisé ({completed}/{total} fiches)"
        )
        return True

    def show_guide_overview(self, guide_id: str, preserve_scroll: bool = False) -> None:
        del preserve_scroll
        guide_id = str(guide_id or "")
        if guide_id in CATALOG_MANUAL_GUIDE_IDS:
            self.select_guide(guide_id)
            return
        super().show_guide_overview(guide_id, preserve_scroll=False)

    def set_character_key(self, character_key: str) -> None:
        previous = self.current_character_key
        super().set_character_key(character_key)
        if self.current_character_key == previous:
            return
        for view in self._catalog_manual_views.values():
            view.set_character_key(self.current_character_key)

    def refresh_external_progress(self) -> None:
        active = str(self.current_guide_id or "")
        if active not in CATALOG_MANUAL_GUIDE_IDS:
            super().refresh_external_progress()
            return

        self.quest_progress = self.quest_progress_service.reload()
        self.guide_progress_service.reload()
        self._sync_achievement_progress()
        self._home_progress_cache_signature = None
        self._home_render_signature = None
        self.refresh_home()
        view = self._catalog_manual_views.get(active)
        if view is not None:
            view.refresh_external_progress()
        self._mark_external_progress_refreshed()

    def _on_catalog_manual_quest_progress_changed(
        self,
        guide_id: str,
        quest_id: int,
    ) -> None:
        self.quest_progress = self.quest_progress_service.reload()
        self._sync_achievement_progress()
        self._home_progress_cache_signature = None
        self._home_render_signature = None
        self.refresh_home()
        view = self._catalog_manual_views.get(str(guide_id))
        if view is not None:
            view.refresh(reset_to_active=False)
        self._mark_external_progress_refreshed()


__all__ = ["CATALOG_MANUAL_GUIDE_IDS", "ManualRouteGuidesView"]
