from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Mapping

from app.modules.encyclopedia.services.guide_catalog_route_stats import (
    catalog_route_map_count_hint,
)
from app.modules.encyclopedia.views.guides_view import (
    GUIDE_ULTIME_LEGACY_ID,
    GuidesView as _BaseGuidesView,
)

if TYPE_CHECKING:
    from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
        GuideCatalogManualRuntimeService,
    )
    from app.modules.encyclopedia.services.guide_imported_manual_runtime_service import (
        ImportedSourceManualRuntimeService,
    )
    from app.modules.encyclopedia.views.shared_manual_guide_view import (
        SharedGuideManualView,
    )


CATALOG_MANUAL_GUIDE_IDS = frozenset({"dofus_sylvestre"})


class ManualRouteGuidesView(_BaseGuidesView):
    """Guides catalogue with shared road-book rendering for optimized routes."""

    def __init__(
        self,
        *args,
        imported_source_services: Mapping[str, ImportedSourceManualRuntimeService] | None = None,
        imported_source_factories: Mapping[str, Callable[[], ImportedSourceManualRuntimeService]] | None = None,
        imported_source_authorizer: Callable[[str, dict], bool] | None = None,
        **kwargs,
    ) -> None:
        # An imported route is never discovered from a candidate store, user
        # file or the old Quest catalogue. Future certified app composition
        # injects only explicit source services and an independent authorizer.
        sources = dict(imported_source_services or {})
        factories = dict(imported_source_factories or {})
        if (sources or factories) and not callable(imported_source_authorizer):
            raise ValueError("Source Guide activation requires an independent authorizer")
        if sources.keys() & factories.keys():
            raise ValueError("A source Guide must have exactly one runtime owner")
        if sources or factories:
            from app.modules.encyclopedia.services.guide_imported_manual_runtime_service import (
                ImportedSourceManualRuntimeService,
            )
            from app.modules.encyclopedia.services.guide_shared_route_contract import (
                _identifier as canonical_source_identifier,
            )
        for guide_id in sources.keys() | factories.keys():
            if not isinstance(guide_id, str) or not guide_id.startswith("source_guide:"):
                raise ValueError("Mismatched or non-canonical imported Guide service")
            canonical_source_identifier(guide_id.removeprefix("source_guide:"), "source guide ID")
        for guide_id, service in sources.items():
            if (not isinstance(service, ImportedSourceManualRuntimeService)
                    or service.guide_id != guide_id):
                raise ValueError("Mismatched or non-canonical imported Guide service")
        for guide_id, factory in factories.items():
            if not callable(factory):
                raise ValueError(f"Source Guide factory must be callable: {guide_id}")
        self._imported_source_services = sources
        # Factories come only from trusted composition, not discovered from
        # candidate files. They are called for the selected guide, never at Home.
        self._imported_source_factories = factories
        self._loaded_imported_source_services: dict[str, ImportedSourceManualRuntimeService] = {}
        self._imported_source_authorizer = imported_source_authorizer
        if imported_source_authorizer is not None:
            for service in sources.values():
                service.set_authorization_guard(imported_source_authorizer)
        self._catalog_manual_services: dict[str, GuideCatalogManualRuntimeService | ImportedSourceManualRuntimeService] = {}
        self._catalog_manual_views: dict[str, SharedGuideManualView] = {}
        self._catalog_route_map_counts: dict[str, int] = {}
        super().__init__(*args, **kwargs)

    def _catalog_route_map_count(self, guide_id: str) -> int:
        guide_id = str(guide_id or "")
        cached = self._catalog_route_map_counts.get(guide_id)
        if cached is not None:
            return cached

        service = self._catalog_manual_services.get(guide_id)
        if service is not None and service.cards:
            count = len(service.cards)
        else:
            # The catalogue must stay metadata-only. Computing the count from
            # quest solutions here materializes the entire Sylvestre route just
            # to paint one subtitle and permanently inflates the process RSS.
            # A certified compact hint is replaced by the exact service count on
            # the first explicit open of that optimized guide.
            count = catalog_route_map_count_hint(guide_id)

        if count > 0:
            self._catalog_route_map_counts[guide_id] = int(count)
        return int(count)

    def _refresh_catalog_route_home_labels(self) -> None:
        for guide_id in CATALOG_MANUAL_GUIDE_IDS:
            count = self._catalog_route_map_count(guide_id)
            if count <= 0:
                continue
            suffix = "map" if count == 1 else "maps"
            self.result_model.set_subtitle_override(
                guide_id,
                f"Parcours optimisé · {count} {suffix}",
            )

    def refresh_home(self) -> None:
        super().refresh_home()
        self._refresh_catalog_route_home_labels()

    def ensure_guide_ultime_view(self) -> SharedGuideManualView | None:
        """Keep Guide Succès on the canonical service but use the shared renderer."""
        if self.guide_ultime_view is not None:
            return self.guide_ultime_view  # type: ignore[return-value]

        from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
            GuideUltimeManualRuntimeService,
        )
        from app.modules.encyclopedia.views.shared_manual_guide_view import (
            SharedGuideManualView,
        )

        service = self.guide_ultime_service
        if service is None:
            service = GuideUltimeManualRuntimeService(
                self.quest_progress_service,
                self.achievement_progress_service,
                self.guide_progress_service,
                quest_provider=self.quest_provider,
                autoload=False,
                cache_manual_bundle=False,
                compact_runtime=True,
            )
            if not service.available:
                service.load()
            service.achievement_provider = self.achievement_provider
            # The player renders one sheet at a time. A full 267-card validation
            # contract duplicates route data and creates a large first-open peak.
            # Per-card Success resolution remains lazy through the compact index.
            service.auto_validation_contract = None
            self.guide_ultime_service = service

        if not service.available:
            return None

        view = SharedGuideManualView(
            service,
            character_key=self.current_character_key,
            quest_provider=self.quest_provider,
            quest_graph=getattr(self, "graph", None),
            travel_callback=self.launch_travel_callback,
            participant_service=self.guide_participant_service,
        )
        view.navigate_entity = self.link_service.navigate_to_entity
        view.questProgressChanged.connect(self._on_guide_ultime_quest_progress_changed)
        self.stack.addWidget(view)
        self.guide_ultime_view = view
        self._refresh_guide_ultime_home_labels()
        return view

    def ensure_catalog_manual_view(self, guide_id: str) -> SharedGuideManualView | None:
        from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
            GuideCatalogManualRuntimeService,
        )
        from app.modules.encyclopedia.views.shared_manual_guide_view import (
            SharedGuideManualView,
        )

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
            travel_callback=self.launch_travel_callback,
            participant_service=self.guide_participant_service,
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
        self._catalog_route_map_counts[guide_id] = len(service.cards)
        self._refresh_catalog_route_home_labels()
        return view

    def _source_service(self, guide_id: str) -> ImportedSourceManualRuntimeService | None:
        """Resolve only an explicitly registered source, on demand and once."""
        service = self._imported_source_services.get(guide_id)
        if service is not None:
            return service
        service = self._loaded_imported_source_services.get(guide_id)
        if service is not None:
            return service
        factory = self._imported_source_factories.get(guide_id)
        if factory is None:
            return None
        from app.modules.encyclopedia.services.guide_imported_manual_runtime_service import (
            ImportedSourceManualRuntimeService,
        )
        try:
            service = factory()
            if (not isinstance(service, ImportedSourceManualRuntimeService)
                    or service.guide_id != guide_id):
                return None
            service.set_authorization_guard(self._imported_source_authorizer)
        except Exception:
            # A bad factory must not fall through to the legacy catalogue.
            return None
        self._loaded_imported_source_services[guide_id] = service
        return service

    def _imported_source_authorized(self, guide_id: str) -> bool:
        """Fail closed on absent, revoked or failing independent approval."""
        service = self._source_service(guide_id)
        return bool(service is not None and service.can_write_progress())

    def _release_imported_source_readers(self, *, keep: str | None = None) -> None:
        """Keep at most one source Guide Qt reader; preserve optimized readers.

        Each source sheet can retain a full route, images and participant UI.
        Never accumulate 95 of them while navigating the catalogue. The
        injected source service/authorizer stays under the composition owner;
        only the detached Qt reader is removed here.
        """
        for source_id in tuple(self._catalog_manual_views):
            if not source_id.startswith("source_guide:") or source_id == keep:
                continue
            reader = self._catalog_manual_views.pop(source_id)
            self._catalog_manual_services.pop(source_id, None)
            if self.stack.currentWidget() is reader:
                self.stack.setCurrentWidget(self.home_page)
            self.stack.removeWidget(reader)
            reader.deleteLater()
        # A factory-created service owns the projected route in memory; release
        # it with the reader. Explicit injected services remain caller-owned.
        for source_id in tuple(self._loaded_imported_source_services):
            if source_id != keep:
                self._loaded_imported_source_services.pop(source_id, None)

    def ensure_imported_source_manual_view(self, guide_id: str) -> SharedGuideManualView | None:
        """Open one explicitly authorized route in the sole shared renderer."""
        from app.modules.encyclopedia.views.shared_manual_guide_view import (
            SharedGuideManualView,
        )
        if not self._imported_source_authorized(guide_id):
            return None
        existing = self._catalog_manual_views.get(guide_id)
        if existing is not None:
            return existing
        service = self._source_service(guide_id)
        if service is None or not service.available:
            return None
        view = SharedGuideManualView(
            service,
            character_key=self.current_character_key,
            quest_provider=self.quest_provider,
            quest_graph=getattr(self, "graph", None),
            travel_callback=self.launch_travel_callback,
            participant_service=self.guide_participant_service,
        )
        view.navigate_entity = self.link_service.navigate_to_entity
        view.questProgressChanged.connect(
            lambda quest_id, gid=guide_id: self._on_catalog_manual_quest_progress_changed(
                gid, int(quest_id),
            )
        )
        self.stack.addWidget(view)
        self._catalog_manual_services[guide_id] = service
        self._catalog_manual_views[guide_id] = view
        return view

    def show_home(self) -> None:
        self._release_imported_source_readers()
        super().show_home()

    def select_guide(self, guide_id: str) -> bool:
        guide_id = str(guide_id or "")
        if guide_id.startswith("source_guide:"):
            view = self.ensure_imported_source_manual_view(guide_id)
            service = self._source_service(guide_id)
            if view is None or service is None or not self._imported_source_authorized(guide_id):
                if self.current_guide_id == guide_id:
                    self.current_guide_id = None
                    self.state = self.CATALOG
                    self.stack.setCurrentWidget(self.home_page)
                    self._release_imported_source_readers()
                else:
                    # A denied factory result must not remain in memory, but
                    # a different active authorized source remains untouched.
                    self._loaded_imported_source_services.pop(guide_id, None)
                self.status_callback(f"Parcours source non certifié ou indisponible : {guide_id}")
                return False
            self.current_guide_id = guide_id
            self.current_quest_id = None
            self.state = self.GUIDE_OVERVIEW
            view.set_character_key(self.current_character_key)
            self.stack.setCurrentWidget(view)
            self._release_imported_source_readers(keep=guide_id)
            done, total = service.route_sheet_progress(self.current_character_key)
            self.status_callback(f"{service.guide_title} — parcours ({done}/{total} fiches)")
            return True
        if guide_id not in CATALOG_MANUAL_GUIDE_IDS:
            selected = bool(super().select_guide(guide_id))
            if selected:
                self._release_imported_source_readers()
            return selected

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
        self._release_imported_source_readers()
        completed, total = service.route_sheet_progress(self.current_character_key)
        self.status_callback(
            f"{guide.title} — parcours optimisé ({completed}/{total} fiches)"
        )
        return True

    def show_guide_overview(self, guide_id: str, preserve_scroll: bool = False) -> None:
        del preserve_scroll
        guide_id = str(guide_id or "")
        if guide_id in CATALOG_MANUAL_GUIDE_IDS or guide_id.startswith("source_guide:"):
            self.select_guide(guide_id)
            return
        super().show_guide_overview(guide_id, preserve_scroll=False)
        if not str(self.current_guide_id or "").startswith("source_guide:"):
            self._release_imported_source_readers()

    def set_character_key(self, character_key: str) -> None:
        previous = self.current_character_key
        super().set_character_key(character_key)
        if self.current_character_key == previous:
            return
        for view in self._catalog_manual_views.values():
            view.set_character_key(self.current_character_key)

    def refresh_external_progress(self) -> None:
        active = str(self.current_guide_id or "")
        if active.startswith("source_guide:") and not self._imported_source_authorized(active):
            # Never keep a revoked route visible after the next refresh.
            self.current_guide_id = None
            self.state = self.CATALOG
            self.stack.setCurrentWidget(self.home_page)
            self._release_imported_source_readers()
            self.status_callback("Autorisation du parcours source retirée.")
            return
        if (active not in CATALOG_MANUAL_GUIDE_IDS
                and active not in self._imported_source_services
                and active not in self._imported_source_factories):
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
