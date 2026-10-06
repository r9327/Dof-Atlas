from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListView, QVBoxLayout, QWidget

from app.modules.encyclopedia.services.guide_catalog_hints import (
    catalog_route_map_count_hint,
)
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.widgets.guide_card import (
    GUIDE_ID_ROLE,
    GuideCardDelegate,
    GuideListModel,
)

GUIDE_SUCCESS_CATALOG_ID = "guide_complet"
GUIDE_ULTIME_TITLE = "Guide Ultime"
CATALOG_MANUAL_GUIDE_IDS = frozenset({"dofus_sylvestre"})


class GuideCatalogView(QWidget):
    """Small Guide catalogue surface; rich Guide UI is imported on selection only."""

    guideRequested = Signal(str)
    achievementRuntimeRequested = Signal()

    CATALOG = "catalog"
    QUEST_DETAIL = "quest_detail"

    def __init__(
        self,
        status_callback,
        *,
        provider,
        quest_progress_path,
        character_key: str = "",
        initial_progress_by_guide: dict[str, tuple[int, int, str]] | None = None,
        initial_progress_character_key: str = "",
        graph=None,
        achievement_provider=None,
        defer_runtime: bool = False,
        **_kwargs,
    ) -> None:
        super().__init__()
        self.setObjectName("GuidesView")
        self.status_callback = status_callback
        self.provider = provider
        self.quest_progress_path = quest_progress_path
        self.current_character_key = str(character_key or "")
        self.current_guide_id: str | None = None
        self.current_quest_id: int | None = None
        self.state = self.CATALOG
        self.graph = graph
        self.achievement_provider = achievement_provider
        self._runtime_ready = False
        self.search_text = ""
        self.guides = []
        self.visible_guides = []
        self._initial_progress_by_guide = dict(initial_progress_by_guide or {})
        self._initial_progress_character_key = str(initial_progress_character_key or "")

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.result_model = GuideListModel(self)
        self.home_list = QListView()
        self.home_list.setObjectName("GuidesHomeList")
        self.home_list.setModel(self.result_model)
        self.home_list.setItemDelegate(GuideCardDelegate(self.home_list))
        self.home_list.setMouseTracking(True)
        self.home_list.setUniformItemSizes(False)
        self.home_list.clicked.connect(self._on_clicked)
        root.addWidget(self.home_list, 1)

        self.home_empty = QLabel("Aucun guide ne correspond à la recherche.")
        self.home_empty.setObjectName("GuidesHomeEmptyText")
        self.home_empty.setAlignment(Qt.AlignCenter)
        self.home_empty.setVisible(False)
        root.addWidget(self.home_empty, 1)

        if defer_runtime:
            self._show_runtime_loading()
        else:
            self.hydrate_runtime(
                graph=graph,
                initial_progress_by_guide=initial_progress_by_guide,
                initial_progress_character_key=initial_progress_character_key,
            )

    def _show_runtime_loading(self) -> None:
        self.home_list.setVisible(False)
        self.home_empty.setText("Chargement des guides…")
        self.home_empty.setWordWrap(False)
        self.home_empty.setVisible(True)

    def show_runtime_error(self, message: str) -> None:
        self.home_list.setVisible(False)
        self.home_empty.setText(str(message or "Chargement des guides impossible."))
        self.home_empty.setWordWrap(True)
        self.home_empty.setVisible(True)

    def hydrate_runtime(
        self,
        *,
        graph=None,
        initial_progress_by_guide: dict[str, tuple[int, int, str]] | None = None,
        initial_progress_character_key: str = "",
    ) -> bool:
        if self._runtime_ready:
            return True
        guides = self.provider.load_all()
        if not guides:
            raise RuntimeError("Aucun guide chargé depuis catalog.json")
        self.graph = graph
        self.guides = list(guides)
        if initial_progress_by_guide is not None:
            self._initial_progress_by_guide = dict(initial_progress_by_guide)
        if initial_progress_character_key:
            self._initial_progress_character_key = str(initial_progress_character_key)
        self._runtime_ready = True
        self.refresh_home()
        self.status_callback(f"{len(self.guides)} guide(s) chargés.")
        return True

    def _on_clicked(self, index) -> None:
        guide_id = index.data(GUIDE_ID_ROLE)
        if guide_id:
            self.select_guide(str(guide_id))

    def select_guide(self, guide_id: str) -> bool:
        guide_id = str(guide_id or "")
        if not guide_id:
            return False
        if not any(str(getattr(guide, "id", "")) == guide_id for guide in self.guides):
            return False
        self.current_guide_id = guide_id
        self.guideRequested.emit(guide_id)
        return True

    def set_search_text(self, text: str) -> None:
        text = str(text or "")
        if text == self.search_text:
            return
        self.search_text = text
        if self._runtime_ready:
            self.refresh_home()

    def set_character_key(self, character_key: str) -> None:
        character_key = str(character_key or "")
        if character_key == self.current_character_key:
            return
        self.current_character_key = character_key
        self._initial_progress_by_guide = {}
        self._initial_progress_character_key = ""
        if self._runtime_ready:
            self.refresh_home()

    def refresh_external_progress(self) -> None:
        if not self._runtime_ready:
            return
        self._initial_progress_by_guide = {}
        self._initial_progress_character_key = ""
        self.refresh_home()

    def _progress_snapshot(self) -> dict[str, tuple[int, int, str]]:
        visible_ids = {str(getattr(guide, "id", "")) for guide in self.visible_guides}
        if (
            self._initial_progress_by_guide
            and self._initial_progress_character_key == self.current_character_key
            and visible_ids.issubset(self._initial_progress_by_guide)
        ):
            result = {
                guide_id: self._initial_progress_by_guide[guide_id]
                for guide_id in visible_ids
            }
            self._initial_progress_by_guide = {}
            return result

        completed_ids = QuestProgressService(
            self.quest_progress_path
        ).completed_quest_ids(self.current_character_key)
        compact_ids = getattr(self.provider, "progress_quest_ids_for", None)
        result: dict[str, tuple[int, int, str]] = {}
        for guide in self.visible_guides:
            guide_id = str(getattr(guide, "id", ""))
            if guide_id == GUIDE_SUCCESS_CATALOG_ID:
                result[guide_id] = (0, 0, "")
                continue
            raw_ids = (
                compact_ids(guide_id)
                if callable(compact_ids)
                else getattr(guide, "quest_ids", ())
            )
            ids: list[int] = []
            seen: set[int] = set()
            for raw_id in raw_ids or ():
                try:
                    quest_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if quest_id in seen:
                    continue
                seen.add(quest_id)
                ids.append(quest_id)
            completed = sum(1 for quest_id in ids if quest_id in completed_ids)
            total = len(ids)
            state = (
                "Terminé"
                if total and completed >= total
                else "En cours"
                if completed
                else "Non commencé"
            )
            result[guide_id] = (completed, total, state)
        return result

    def _apply_catalog_overrides(self) -> None:
        self.result_model.set_title_override(
            GUIDE_SUCCESS_CATALOG_ID,
            GUIDE_ULTIME_TITLE,
        )
        for guide_id in CATALOG_MANUAL_GUIDE_IDS:
            count = int(catalog_route_map_count_hint(guide_id) or 0)
            if count <= 0:
                continue
            suffix = "map" if count == 1 else "maps"
            self.result_model.set_subtitle_override(
                guide_id,
                f"Parcours optimisé · {count} {suffix}",
            )

    def refresh_home(self) -> None:
        self.visible_guides = self.provider.search(self.search_text)
        self.result_model.set_guides(self.visible_guides)
        self._apply_catalog_overrides()
        if not self.visible_guides:
            self.result_model.set_progress({})
            self.home_list.setVisible(False)
            self.home_empty.setText("Aucun guide ne correspond à la recherche.")
            self.home_empty.setVisible(True)
            return
        self.result_model.set_progress(self._progress_snapshot())
        self.home_empty.setVisible(False)
        self.home_list.setVisible(True)


__all__ = ["GuideCatalogView"]
