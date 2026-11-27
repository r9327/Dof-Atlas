from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.map_coordinates import quest_launch_position_evidence
from app.modules.encyclopedia.providers import AchievementProvider, QuestProvider
from app.modules.encyclopedia.services import (
    ProgressCount,
    QuestGraphService,
    QuestProgressService,
)
from app.modules.encyclopedia.services.guide_quest_view_model import (
    _canonical_source_coordinate,
    clean_requirement_line,
    clean_text,
    quest_activity_labels,
    quest_blocks_have_instructions,
    quest_fallback_instruction_steps,
    quest_items,
    quest_items_from_objectives,
    quest_rewards,
    quest_start_info,
    resolve_quest_requirement,
)
from app.modules.encyclopedia.widgets.dashboard import FixedColumnSplitter
from app.modules.encyclopedia.widgets.quest_item_row import item_row, set_item_row_checked
from app.quest_catalog import QuestRecord, normalize_text
from app.ui.components import AtlasButton, AtlasGuideReadingHeader, atlas_prerequisite_row, clear_unity_widget_layout, configure_unity_scroll_area, configure_unity_tool_button, set_unity_widget_property
from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX

QUEST_DETAIL_GEOMETRY = UNITY_MODULE_GEOMETRY_PX["quest_detail"]


QuestOpener = Callable[[int], object]
EntityNavigator = Callable[..., bool]


@dataclass(frozen=True)
class QuestViewContext:
    """Presentation context around one canonical QuestRecord."""

    host: str = "quests"
    guide_id: str = ""
    guide_title: str = ""
    achievement_id: int | None = None
    ordered_quest_ids: tuple[int, ...] = ()


@lru_cache(maxsize=1)
def _guide_ui() -> Any:
    """Reuse the established visual primitives without creating a data path."""

    from app.modules.encyclopedia.views import guides_view

    return guides_view


class QuestDetailView(QWidget):
    """Shared quest sheet used by Quests, Guides and Achievements.

    Quest data always comes from the injected QuestProvider. Hosts only decide
    where related quests and prerequisite quests should open.
    """

    questChanged = Signal(int)
    questProgressChanged = Signal(int)

    def __init__(
        self,
        quest_provider: QuestProvider,
        graph: QuestGraphService,
        quest_progress_service: QuestProgressService,
        achievement_provider: AchievementProvider | None = None,
        guide_provider: Any = None,
        character_key: str = "",
        open_quest: QuestOpener | None = None,
        open_prerequisite: QuestOpener | None = None,
        navigate_entity: EntityNavigator | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("QuestDetailView")
        self.quest_provider = quest_provider
        self.graph = graph
        self.quest_progress_service = quest_progress_service
        self.achievement_provider = achievement_provider
        self.guide_provider = guide_provider
        self.character_key = character_key or ""
        self.open_quest_callback = open_quest
        self.open_prerequisite_callback = open_prerequisite
        self.navigate_entity_callback = navigate_entity
        self.current_quest_id: int | None = None
        self._preparation_rows: list[tuple[int, QWidget]] = []
        self.context = QuestViewContext()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(QUEST_DETAIL_GEOMETRY["root_spacing"])

        self.header = AtlasGuideReadingHeader("", overview=True, show_cover=False)
        self.header.set_overview_progress(0, 0, visible=False)
        header_layout = self.header.title_row
        self.title_label = self.header.guide_title_label
        self.meta_label = self.header.meta_label
        self.done_button = configure_unity_tool_button(
            QToolButton(), object_name="QuestGlobalDoneButton",
            pointing=True, focus_policy=Qt.NoFocus,
        )
        self.done_button.clicked.connect(self.toggle_completed)
        header_layout.addWidget(self.done_button, 0, Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(self.header)

        self.splitter = FixedColumnSplitter(Qt.Horizontal)
        self.splitter.setObjectName("QuestDetailSplitter")
        self.center_panel, self.center_scroll, self.center_layout = self._build_column("GuideCenterPanel")
        self.center_panel.setMinimumWidth(QUEST_DETAIL_GEOMETRY["center_min_width"])
        self.splitter.addWidget(self.center_panel)
        self.splitter.setStretchFactor(0, 1)
        root.addWidget(self.splitter, 1)

        # Keep the empty Quests screen lightweight. Importing the Guide view here
        # used to charge its full presentation module before a quest was selected.
        self.clear("Sélectionnez une quête.")

    @staticmethod
    def _build_column(object_name: str) -> tuple[QFrame, QScrollArea, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName(object_name)
        panel_root = QVBoxLayout(panel)
        inset = QUEST_DETAIL_GEOMETRY["panel_padding"]
        panel_root.setContentsMargins(inset, inset, inset, inset)
        panel_root.setSpacing(QUEST_DETAIL_GEOMETRY["panel_spacing"])
        scroll = configure_unity_scroll_area(
            QScrollArea(), borderless=True, vertical_policy=Qt.ScrollBarAsNeeded,
        )
        scroll.setObjectName(f"{object_name}Scroll")
        content = QWidget()
        content.setObjectName(f"{object_name}Content")
        content.setMinimumWidth(0)
        content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(QUEST_DETAIL_GEOMETRY["content_spacing"])
        scroll.setWidget(content)
        panel_root.addWidget(scroll, 1)
        return panel, scroll, layout

    @classmethod
    def _clear_layout(cls, layout) -> None:
        clear_unity_widget_layout(layout, recursive=True)

    @staticmethod
    def _muted_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("MutedLabel")
        label.setWordWrap(True)
        return label

    def set_character_key(self, character_key: str, *, refresh: bool = True) -> None:
        character_key = character_key or ""
        if character_key == self.character_key:
            return
        self.character_key = character_key
        if refresh:
            self.refresh()

    def update_related_context(
        self,
        *,
        guide_provider: Any = None,
        achievement_provider: AchievementProvider | None = None,
        graph: QuestGraphService | None = None,
    ) -> None:
        if guide_provider is not None:
            self.guide_provider = guide_provider
        if achievement_provider is not None:
            self.achievement_provider = achievement_provider
        if graph is not None:
            self.graph = graph
        if self.current_quest_id is not None:
            self.show_quest(self.current_quest_id, self.context)

    def show_quest(self, quest_id: int, context: QuestViewContext | None = None) -> bool:
        previous_quest_id = self.current_quest_id
        quest = self.quest_provider.get_quest(int(quest_id))
        if quest is None:
            self.clear("Quête introuvable.")
            return False
        self.current_quest_id = int(quest.id)
        if context is not None:
            self.context = context
        self.quest_progress_service.reload()
        guide, step = self._quest_context(quest)
        achievements = self._related_achievements(quest.id)
        self._render_header(quest)
        self._render_solution(quest, step)
        self._render_header_sections(quest, guide, step, achievements,
                                     preserve_open=previous_quest_id == int(quest.id))
        self.questChanged.emit(int(quest.id))
        if self.current_quest_id != previous_quest_id:
            self.center_scroll.verticalScrollBar().setValue(0)
        return True

    def refresh(self) -> None:
        if self.current_quest_id is not None:
            self.show_quest(self.current_quest_id, self.context)

    def clear(self, message: str = "") -> None:
        self.current_quest_id = None
        self._preparation_rows.clear()
        self.title_label.setText("Quêtes")
        self.title_label.setToolTip("Quêtes")
        self.meta_label.clear()
        self.meta_label.setVisible(False)
        self.done_button.setVisible(False)
        self._clear_layout(self.center_layout)
        self.header.set_optional_sections([])
        if message:
            self.center_layout.addWidget(self._muted_label(message))
        self.center_layout.addStretch(1)

    def toggle_completed(self) -> None:
        if self.current_quest_id is None:
            return
        quest_id = int(self.current_quest_id)
        completed = self.quest_progress_service.is_quest_completed(self.character_key, quest_id)
        self.quest_progress_service.set_quest_completed(self.character_key, quest_id, not completed)
        quest = self.quest_provider.get_quest(quest_id)
        if quest is not None:
            self._render_header(quest)
        self.questProgressChanged.emit(quest_id)

    def _render_header(self, quest: QuestRecord) -> None:
        completed = self.quest_progress_service.is_quest_completed(self.character_key, int(quest.id))
        self.title_label.setText(quest.name)
        self.title_label.setToolTip(quest.name)
        level = _guide_ui()._display_quest_level_text(quest).replace("Niveau minimum", "Niveau recommandé")
        self.meta_label.setText(level)
        self.meta_label.setVisible(bool(level))
        self.done_button.setVisible(True)
        self.done_button.setText("✓ Quête terminée" if completed else "○ Marquer terminée")
        set_unity_widget_property(self.done_button, "state", "done" if completed else "todo")

    @staticmethod
    def _start_position_heading(quest: QuestRecord, position: str) -> str:
        """Do not mislabel an objective coordinate as a proven quest start."""
        if not position:
            return "Zone de quête"
        _primary, status, source_positions = quest_launch_position_evidence(quest.source_info)
        if status == "DOCUMENTED_START":
            return "Position d'objectif"
        shown = _canonical_source_coordinate(position)
        if not shown or shown not in source_positions:
            return "Position d'objectif (départ non confirmé)"
        if status == "NATIVE_START_DECLARED":
            return "Position de lancement (source du jeu)"
        if status != "LOCAL_START_DECLARED":
            return "Départ à vérifier (sources incohérentes)"
        return "Position de lancement"

    def _render_solution(self, quest: QuestRecord, step: Any) -> None:
        ui = _guide_ui()
        ui.clear_layout(self.center_layout)
        start = quest_start_info(quest)
        start_map_paths = start.map_image_paths or ((start.map_image_path,) if start.map_image_path else ())
        for map_index, map_image_path in enumerate(start_map_paths, 1):
            self.center_layout.addWidget(
                ui.SolutionImageLabel(
                    map_image_path,
                    "Localisation de départ" if len(start_map_paths) == 1 else f"Localisation de départ {map_index}",
                ),
                0,
                Qt.AlignHCenter,
            )
        launch_parts = [part for part in (start.zone, start.position) if part]
        if launch_parts:
            self.center_layout.addWidget(
                ui.text_label(
                    f"{self._start_position_heading(quest, start.position)} : {' '.join(launch_parts)}",
                    "QuestLaunchPosition",
                )
            )

        if start.launch_instruction:
            self.center_layout.addWidget(ui.text_label(start.launch_instruction))

        documentary_blocks = ui.quest_solution_blocks(quest)
        # Image-only or heading-only documents may coexist with genuine local
        # objectives. Do not discard either source and do not call it complete.
        has_instructions = quest_blocks_have_instructions(documentary_blocks)
        fallback_steps = (
            () if has_instructions else quest_fallback_instruction_steps(quest)
        )
        if fallback_steps:
            self.center_layout.addWidget(
                ui.text_label(
                    "Documentation locale complète indisponible — objectifs affichés à titre de repère.",
                    "MutedLabel",
                )
            )
        widgets = ui.quest_solution_document_widgets(
            quest, omit_first_image_path=start.map_image_path,
            source_blocks=documentary_blocks,
            fallback_steps=fallback_steps,
        )
        if not has_instructions and not fallback_steps:
            self.center_layout.addWidget(
                ui.text_label(
                    "Les données locales ne contiennent pas d'objectifs exploitables pour cette quête.",
                    "MutedLabel",
                )
            )
        for widget in widgets:
            self.center_layout.addWidget(widget)
        previous_id, next_id = self._ordered_neighbors(int(quest.id))
        footer = ui.quest_navigation_footer(
            previous_id,
            next_id,
            self.quest_provider.get_catalog().by_id,
            self.open_related_quest,
        )
        if footer is not None:
            self.center_layout.addWidget(footer)
        self.center_layout.addStretch(1)

    def _ordered_neighbors(self, quest_id: int) -> tuple[int | None, int | None]:
        ordered = self.context.ordered_quest_ids
        if ordered:
            try:
                index = ordered.index(int(quest_id))
            except ValueError:
                index = -1
            if index >= 0:
                previous = ordered[index - 1] if index > 0 else None
                following = ordered[index + 1] if index + 1 < len(ordered) else None
                return previous, following
        return self.graph.reliable_neighbors(int(quest_id), guide_id=self.context.guide_id)

    def _render_header_sections(
        self, quest: QuestRecord, guide: Any, step: Any, achievements: tuple[Any, ...],
        *, preserve_open: bool = False,
    ) -> None:
        ui = _guide_ui()
        prerequisite_rows, progress = self._prerequisite_rows(quest, step)
        required_items = quest_items(guide, quest) if guide is not None else quest_items_from_objectives(quest)
        self._preparation_rows.clear()
        preparation_rows = [self._item_row(quest.id, item) for item in required_items]
        self._preparation_rows = [
            (int(item.item_id), row) for item, row in zip(required_items, preparation_rows)
            if item.item_id is not None
        ]
        ready = self._sync_preparation_rows(int(quest.id))
        tracked = self._preparation_rows
        rewards = quest_rewards(quest, achievements)
        self.header.set_optional_sections([
            ("Prérequis", f"{progress.completed}/{progress.total}" if progress.total else "", prerequisite_rows),
            ("Préparation", f"{ready}/{len(tracked)}" if tracked else "", preparation_rows),
            ("Récompenses", "", [ui.reward_row(reward) for reward in rewards]),
        ], preserve_open=preserve_open)

        # Useful quest context remains in the reading column, without a
        # duplicate linked-success section or a separate information panel.
        activities = quest_activity_labels(guide, quest, step)
        if activities:
            self.center_layout.insertWidget(0, ui.info_section("Info quête", [ui.activity_chip_grid(activities)]))

    def _quest_context(self, quest: QuestRecord) -> tuple[Any | None, Any | None]:
        if self.guide_provider is None:
            return None, None
        guide = None
        if self.context.guide_id:
            guide = self.guide_provider.get_by_id(self.context.guide_id)
        if guide is None:
            guides = self.guide_provider.get_guides_for_entity("quest", int(quest.id))
            guide = guides[0] if guides else None
        if guide is None:
            return None, None
        for step in getattr(guide, "steps", ()):
            if getattr(step, "step_type", "") == "quest" and int(getattr(step, "entity_id", 0) or 0) == int(quest.id):
                return guide, step
        return guide, None

    def _related_achievements(self, quest_id: int) -> tuple[Any, ...]:
        if self.achievement_provider is None:
            return ()
        return tuple(self.achievement_provider.get_by_quest(int(quest_id)))

    def _prerequisite_rows(self, quest: QuestRecord, step: Any) -> tuple[list[QWidget], ProgressCount]:
        rows: list[tuple[str, bool | None, int | None]] = []
        seen: set[str] = set()

        def add(text: str, done: bool | None = None, linked_id: int | None = None) -> None:
            cleaned = clean_requirement_line(text)
            key = normalize_text(cleaned)
            if key.startswith("niveau_"):
                return
            if cleaned and key not in seen:
                seen.add(key)
                rows.append((cleaned, done, linked_id))

        for ref in getattr(step, "prerequisites", ()) if step is not None else ():
            if getattr(ref, "entity_type", "") == "quest":
                linked_id = int(ref.entity_id)
                add(
                    str(getattr(ref, "label", "")),
                    self.quest_progress_service.is_quest_completed(self.character_key, linked_id),
                    linked_id,
                )
            else:
                add(str(getattr(ref, "label", "")))
        for previous_id in self.graph.previous_ids(int(quest.id)):
            record = self.quest_provider.get_quest(int(previous_id))
            if record is not None:
                add(
                    record.name,
                    self.quest_progress_service.is_quest_completed(self.character_key, int(previous_id)),
                    int(previous_id),
                )
        for line in getattr(quest, "prerequisites", ()) or ():
            linked_id = self._quest_id_from_requirement_line(str(line))
            completed = (
                self.quest_progress_service.is_quest_completed(self.character_key, linked_id)
                if linked_id is not None
                else None
            )
            add(str(line), completed, linked_id)
        tracked = [completed for _text, completed, _linked_id in rows if completed is not None]
        progress = ProgressCount(sum(1 for completed in tracked if completed), len(tracked))
        widgets = [self._prerequisite_row(text, completed, linked_id) for text, completed, linked_id in rows]
        return widgets, progress

    def _quest_id_from_requirement_line(self, line: str) -> int | None:
        return resolve_quest_requirement(line, self.quest_provider, owner=self)

    def _prerequisite_row(self, text: str, completed: bool | None, linked_id: int | None) -> QWidget:
        ui = _guide_ui()
        if linked_id is None:
            return ui.prerequisite_row(text, completed)
        button = AtlasButton(clean_text(text))
        button.setObjectName("QuestPrerequisiteButton")
        button.setToolTip("Ouvrir dans l'onglet Quêtes")
        button.clicked.connect(lambda _checked=False, target_id=int(linked_id): self.open_prerequisite_quest(target_id))
        return atlas_prerequisite_row(button, completed)

    def _item_row(self, quest_id: int, item: Any) -> QWidget:
        item_id = int(item.item_id) if item.item_id is not None else None
        row = item_row(
            item,
            checked=(
                self.quest_progress_service.is_item_completed(
                    self.character_key,
                    int(quest_id),
                    item_id,
                )
                if item_id is not None
                else None
            ),
            on_toggle=(
                lambda checked, target_id=item_id: self.set_item_completed(int(quest_id), int(target_id), checked)
                if target_id is not None
                else None
            ),
        )
        row.setObjectName("GuideQuestItemRow")
        return row

    def _sync_preparation_rows(self, quest_id: int) -> int:
        """Keep duplicate display rows in sync with one persisted item ID."""
        ready = 0
        states: dict[int, bool] = {}
        for item_id, row in self._preparation_rows:
            if item_id not in states:
                states[item_id] = self.quest_progress_service.is_item_completed(
                    self.character_key, quest_id, item_id,
                )
            checked = states[item_id]
            set_item_row_checked(row, checked)
            ready += checked
        return ready

    def set_item_completed(self, quest_id: int, item_id: int, completed: bool) -> None:
        self.quest_progress_service.set_item_completed(
            self.character_key,
            int(quest_id),
            int(item_id),
            bool(completed),
        )
        if int(quest_id) == self.current_quest_id:
            ready = self._sync_preparation_rows(int(quest_id))
            total = len(self._preparation_rows)
            self.header.set_optional_section_count("Préparation", f"{ready}/{total}" if total else "")
        else:
            self.show_quest(int(quest_id), self.context)
        self.questProgressChanged.emit(int(quest_id))

    def open_related_quest(self, quest_id: int) -> bool:
        if self.open_quest_callback is not None:
            result = self.open_quest_callback(int(quest_id))
            return result is not False
        return self.show_quest(int(quest_id), self.context)

    def open_prerequisite_quest(self, quest_id: int) -> bool:
        if self.open_prerequisite_callback is not None:
            result = self.open_prerequisite_callback(int(quest_id))
            return result is not False
        return self.open_related_quest(int(quest_id))

    def open_entity(self, entity_type: str, entity_id: int | str) -> bool:
        if self.navigate_entity_callback is None:
            return False
        return bool(
            self.navigate_entity_callback(
                str(entity_type),
                entity_id,
                source=self.context.host,
                guide_id=self.context.guide_id,
                achievement_id=self.context.achievement_id,
            )
        )
