from __future__ import annotations

from threading import Thread
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton

from app.constants import QUEST_PROGRESS_FILE
from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.services import (
    ACHIEVEMENT_PROGRESS_FILE,
    GUIDE_PROGRESS_FILE,
    AchievementProgressService,
    GuideProgressService,
    QuestProgressService,
)
from app.pages.home_page import HomePage as _BaseHomePage
from app.quest_catalog import QuestCatalog


class HomePage(_BaseHomePage):
    """Home runtime that keeps route composition and repeated progress work off UI."""

    guideServiceReady = Signal(int, object, str)

    def __init__(self, *args, **kwargs) -> None:
        self._guide_service_build_token = 0
        self._guide_service_building = False
        self._guide_service_context_key: tuple[int, int] = (0, 0)
        super().__init__(*args, **kwargs)
        character_button = self.findChild(QPushButton, "HomeChangeCharacterButton")
        if character_button is not None:
            character_button.setText("Mon personnage")
            character_button.setToolTip("Ouvrir la fiche du personnage actif")
        self.guideServiceReady.connect(self._on_guide_service_ready)

    @staticmethod
    def _build_guide_service(
        catalog: QuestCatalog,
        achievement_provider: Any = None,
    ) -> tuple[Any | None, str]:
        try:
            # Manual route composition and its validation contract are imported
            # only inside this worker, after Encyclopedia context exists.
            from app.modules.encyclopedia.services.guide_auto_validation_contract import (
                build_route_auto_validation_contract,
            )
            from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
                GuideUltimeManualRuntimeService,
            )

            service = GuideUltimeManualRuntimeService(
                QuestProgressService(QUEST_PROGRESS_FILE),
                AchievementProgressService(ACHIEVEMENT_PROGRESS_FILE),
                GuideProgressService(GUIDE_PROGRESS_FILE),
                quest_provider=QuestProvider(catalog=catalog),
                # Manual manifest is authoritative. Loading generated V5 first
                # would duplicate route I/O before composing the manual cards.
                autoload=False,
            )
            if not service.available:
                # Preserve the historical generated V5 emergency fallback only
                # when the canonical manual bundle could not be composed.
                service.load()
            service.achievement_provider = achievement_provider
            # Contract construction walks the complete route and resolves Success
            # names. Pay that cost in the same worker as manual route composition;
            # Guides later reuses the revision-aware cache instead of freezing Qt
            # on its first Guide Ultime opening.
            service.auto_validation_contract = build_route_auto_validation_contract(
                service.cards,
                achievement_provider=achievement_provider,
            )
            return service, ""
        except Exception as exc:
            return None, f"{type(exc).__name__}: {exc}"

    def _rebuild_guide_ultime_service(self) -> None:
        catalog = self.catalog
        if not isinstance(catalog, QuestCatalog):
            self.guide_ultime_service = None
            return

        achievement_provider = self.achievement_provider
        context_key = (id(catalog), id(achievement_provider))
        if context_key != self._guide_service_context_key:
            self._guide_service_context_key = context_key
            self.guide_ultime_error = ""
            self.guide_ultime_service = None
            self._last_progress_signature = None
        elif self._guide_service_building or self.guide_ultime_service is not None:
            return
        elif self.guide_ultime_error:
            # A failed build for the same immutable context must not respawn an
            # endless worker loop every time Home refreshes. Base Home can still
            # render its compatibility fallback from GuideProvider.
            return

        self._guide_service_build_token += 1
        token = self._guide_service_build_token
        self._guide_service_building = True

        def worker() -> None:
            service, error = self._build_guide_service(catalog, achievement_provider)
            try:
                self.guideServiceReady.emit(token, service, error)
            except RuntimeError:
                # Home may have been destroyed while Atlas shuts down.
                pass

        Thread(target=worker, name="DofusAtlasHomeGuide", daemon=True).start()

    def _on_guide_service_ready(self, token: int, service: object, error: str) -> None:
        if int(token) != self._guide_service_build_token:
            return
        self._guide_service_building = False
        self.guide_ultime_error = str(error or "")
        if service is not None:
            from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
                GuideUltimeManualRuntimeService,
            )

            valid_service = isinstance(service, GuideUltimeManualRuntimeService)
        else:
            valid_service = False
        if valid_service:
            # The matching worker was built from the same catalogue/provider
            # context represented by the current token.
            self.guide_ultime_service = service
        else:
            self.guide_ultime_service = None
        self._last_progress_signature = None
        # Heavy pure-Python route/contract composition is finished. The remaining
        # Home projection uses the batched quest snapshot overrides below.
        _BaseHomePage.refresh_progress(self)

    def refresh_progress(self) -> None:
        if self.catalog is not None:
            context_key = (id(self.catalog), id(self.achievement_provider))
            context_changed = context_key != self._guide_service_context_key
            if context_changed or (
                self.guide_ultime_service is None and not self.guide_ultime_error
            ):
                self._rebuild_guide_ultime_service()
                if self._guide_service_building:
                    self._show_preparing()
                    return
        _BaseHomePage.refresh_progress(self)

    def _refresh_tracking(self, guide: Any, calculator: Any, achievement_progress_service: Any) -> None:
        """Project legacy Home counters with one quest completion snapshot.

        The historical implementation asked QuestProgressService for the same
        character completion map once per quest step. Home needs one coherent
        snapshot for the whole projection, so resolve it once and pass it into
        GuideProgressCalculator.step_completed().
        """

        counters = {
            "quests": [0, 0],
            "achievement_quests": [0, 0],
            "achievement_monsters": [0, 0],
            "achievement_dungeons": [0, 0],
            "dungeons": [0, 0],
            "dofus": [0, 0],
            "alignment": [0, 0],
        }
        dungeon_state: dict[int, bool] = {}
        completed_quest_ids = calculator.quest_progress_service.completed_quest_ids(
            self.character_key
        )

        for part_title, chapter_title, series_title, step in self._iter_guide_steps(guide):
            if not step.counts_for_completion:
                continue
            completed = calculator.step_completed(
                guide,
                step,
                self.character_key,
                completed_quest_ids=completed_quest_ids,
            )
            context = self._plain_key(
                " ".join((part_title, chapter_title, series_title, step.display_title))
            )

            if step.step_type == "quest":
                self._bump(counters["quests"], completed)
            elif step.step_type == "achievement" and step.entity_id is not None:
                achievement = (
                    self.achievement_provider.get_by_id(int(step.entity_id))
                    if self.achievement_provider is not None
                    else None
                )
                achievement_completed = achievement_progress_service.is_achievement_completed(
                    self.character_key,
                    int(step.entity_id),
                )
                achievement_text = context
                if achievement is not None:
                    achievement_text = self._plain_key(
                        " ".join(
                            (
                                achievement.name,
                                achievement.category_name,
                                achievement.subcategory_name or "",
                            )
                        )
                    )
                if achievement is not None and (
                    achievement.linked_dungeons
                    or "donjon" in achievement_text
                    or "boss" in achievement_text
                ):
                    self._bump(counters["achievement_dungeons"], achievement_completed)
                elif achievement is not None and (
                    achievement.linked_monsters or "monstre" in achievement_text
                ):
                    self._bump(counters["achievement_monsters"], achievement_completed)
                else:
                    self._bump(counters["achievement_quests"], achievement_completed)

                if achievement is not None:
                    for dungeon_ref in achievement.linked_dungeons:
                        dungeon_id = int(dungeon_ref.entity_id)
                        dungeon_state[dungeon_id] = (
                            dungeon_state.get(dungeon_id, False) or achievement_completed
                        )
            elif step.step_type == "dungeon":
                dungeon_id = int(step.entity_id) if step.entity_id is not None else hash(step.id)
                dungeon_state[dungeon_id] = dungeon_state.get(dungeon_id, False) or completed

            if self._contains_any(context, self._DOFUS_KEYWORDS):
                self._bump(counters["dofus"], completed)
            if self._contains_any(context, self._ALIGNMENT_KEYWORDS):
                self._bump(counters["alignment"], completed)

        counters["dungeons"] = [
            sum(1 for done in dungeon_state.values() if done),
            len(dungeon_state),
        ]
        for key, row in self.tracking_rows.items():
            completed, total = counters[key]
            row.set_progress(completed, total, show_count=key == "dofus")

    def _first_incomplete_step(self, guide: Any, calculator: Any):
        completed_quest_ids = calculator.quest_progress_service.completed_quest_ids(
            self.character_key
        )
        for _part_title, chapter_title, _series_title, step in self._iter_guide_steps(guide):
            if not step.counts_for_completion:
                continue
            if not calculator.step_completed(
                guide,
                step,
                self.character_key,
                completed_quest_ids=completed_quest_ids,
            ):
                return chapter_title, step
        return None


__all__ = ["HomePage"]
