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

from app.modules.encyclopedia.providers import AchievementProvider, QuestProvider
from app.modules.encyclopedia.services import (
    ProgressCount,
    QuestGraphService,
    QuestProgressService,
)
from app.modules.encyclopedia.services.guide_quest_view_model import (
    clean_requirement_line,
    clean_text,
    quest_activity_labels,
    quest_items,
    quest_items_from_objectives,
    quest_rewards,
    quest_start_info,
)
from app.modules.encyclopedia.widgets.dashboard import FixedColumnSplitter
from app.modules.encyclopedia.widgets.quest_item_row import item_row
from app.quest_catalog import QuestRecord, normalize_text
from app.ui.components import AtlasButton


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
        self.context = QuestViewContext()
        self.prerequisite_expanded: dict[tuple[str, int], bool] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self.header = QFrame()
        self.header.setObjectName("GuideHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(8, 8, 10, 8)
        header_layout.setSpacing(10)
        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        self.title_label = QLabel()
        self.title_label.setObjectName("GuideHeaderTitle")
        self.title_label.setWordWrap(True)
        self.meta_label = QLabel()
        self.meta_label.setObjectName("GuideHeaderMeta")
        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.meta_label)
        header_layout.addLayout(title_layout, 1)
        self.done_button = QToolButton()
        self.done_button.setObjectName("QuestGlobalDoneButton")
        self.done_button.setCursor(Qt.PointingHandCursor)
        self.done_button.setFocusPolicy(Qt.NoFocus)
        self.done_button.clicked.connect(self.toggle_completed)
        header_layout.addWidget(self.done_button, 0, Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(self.header)

        self.splitter = FixedColumnSplitter(Qt.Horizontal)
        self.splitter.setObjectName("QuestDetailSplitter")
        self.center_panel, self.center_scroll, self.center_layout = self._build_column("GuideCenterPanel")
        self.right_panel, self.right_scroll, self.right_layout = self._build_column("GuideRightPanel")
        self.center_panel.setMinimumWidth(340)
        self.right_panel.setMinimumWidth(240)
        self.right_panel.setMaximumWidth(380)
        self.splitter.addWidget(self.center_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 70)
        self.splitter.setStretchFactor(1, 30)
        self.splitter.setSizes([680, 300])
        root.addWidget(self.splitter, 1)

        # Keep the empty Quests screen lightweight. Importing the Guide view here
        # used to charge its full presentation module before a quest was selected.
        self.clear("Sélectionnez une quête.")

    @staticmethod
    def _build_column(object_name: str) -> tuple[QFrame, QScrollArea, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName(object_name)
        panel_root = QVBoxLayout(panel)
        panel_root.setContentsMargins(8, 8, 8, 8)
        panel_root.setSpacing(6)
        scroll = QScrollArea()
        scroll.setObjectName(f"{object_name}Scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        content.setObjectName(f"{object_name}Content")
        content.setMinimumWidth(0)
        content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        scroll.setWidget(content)
        panel_root.addWidget(scroll, 1)
        return panel, scroll, layout

    @classmethod
    def _clear_layout(cls, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            if child_layout is not None:
                cls._clear_layout(child_layout)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    @staticmethod
    def _muted_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("MutedLabel")
        label.setWordWrap(True)
        return label

    def set_character_key(self, character_key: str) -> None:
        character_key = character_key or ""
        if character_key == self.character_key:
            return
        self.character_key = character_key
        self.quest_progress_service.reload()
        if self.current_quest_id is not None:
            self.show_quest(self.current_quest_id, self.context)

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
        self._render_information(quest, guide, step, achievements)
        self.questChanged.emit(int(quest.id))
        if self.current_quest_id != previous_quest_id:
            for scroll in (self.center_scroll, self.right_scroll):
                bar = scroll.verticalScrollBar()
                bar.setValue(bar.minimum())
        return True

    def refresh(self) -> None:
        if self.current_quest_id is not None:
            self.show_quest(self.current_quest_id, self.context)

    def clear(self, message: str = "") -> None:
        self.current_quest_id = None
        self.title_label.setText("Quêtes")
        self.meta_label.clear()
        self.meta_label.setVisible(False)
        self.done_button.setVisible(False)
        self._clear_layout(self.center_layout)
        self._clear_layout(self.right_layout)
        if message:
            self.center_layout.addWidget(self._muted_label(message))
        self.center_layout.addStretch(1)
        self.right_layout.addStretch(1)

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
        level = _guide_ui()._display_quest_level_text(quest)
        self.meta_label.setText(level)
        self.meta_label.setVisible(bool(level))
        self.done_button.setVisible(True)
        self.done_button.setText("✓ Quête terminée" if completed else "○ Marquer terminée")
        self.done_button.setProperty("state", "done" if completed else "todo")
        self.done_button.style().unpolish(self.done_button)
        self.done_button.style().polish(self.done_button)

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
                    f"Position de lancement : {' '.join(launch_parts)}",
                    "QuestLaunchPosition",
                )
            )

        prerequisite_rows, progress = self._prerequisite_rows(quest, step)
        if prerequisite_rows:
            key = (self.character_key, int(quest.id))
            expanded = self.prerequisite_expanded.get(key)
            if expanded is None:
                expanded = not progress.is_complete if progress.total else True
            section = ui.CollapsibleInfoSection(
                "PRÉREQUIS",
                ui._progress_count(progress.completed, progress.total) if progress.total else "",
                ui._progress_state(progress),
                expanded,
                prerequisite_rows,
            )
            section.toggled.connect(lambda value, item_key=key: self.prerequisite_expanded.__setitem__(item_key, value))
            self.center_layout.addWidget(section)

        if not getattr(quest, "solution_blocks", None) and getattr(quest, "source_solution_steps", None):
            self.center_layout.addWidget(
                ui.text_label(
                    "Documentation locale complète indisponible — objectifs affichés à titre de repère.",
                    "MutedLabel",
                )
            )
        widgets = ui.quest_solution_document_widgets(quest, omit_first_image_path=start.map_image_path)
        if not widgets:
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
                pass
            else:
                previous = ordered[index - 1] if index > 0 else None
                following = ordered[index + 1] if index + 1 < len(ordered) else None
                return previous, following
        return self.graph.reliable_neighbors(int(quest_id), guide_id=self.context.guide_id)

    def _render_information(self, quest: QuestRecord, guide: Any, step: Any, achievements: tuple[Any, ...]) -> None:
        ui = _guide_ui()
        ui.clear_layout(self.right_layout)
        self.right_layout.addWidget(ui.hidden_label("Informations de quête"))

        activities = quest_activity_labels(guide, quest, step)
        if activities:
            self.right_layout.addWidget(ui.info_section("INFO QUÊTE", [ui.activity_chip_grid(activities)]))

        if achievements:
            buttons: list[QWidget] = []
            for achievement in achievements[:6]:
                button = AtlasButton(str(getattr(achievement, "name", "")))
                button.setObjectName("GuideInlineQuestButton")
                button.clicked.connect(
                    lambda _checked=False, achievement_id=int(getattr(achievement, "id", 0) or 0): self.open_entity(
                        "achievement", achievement_id
                    )
                )
                buttons.append(button)
            self.right_layout.addWidget(ui.info_section("SUCCÈS LIÉS", buttons))

        required_items = quest_items(guide, quest) if guide is not None else quest_items_from_objectives(quest)
        if required_items:
            self.right_layout.addWidget(
                ui.info_section(
                    "OBJETS NÉCESSAIRES",
                    [self._item_row(quest.id, item) for item in required_items],
                )
            )

        related_rows: list[QWidget] = []
        catalog = self.quest_provider.get_catalog()
        for label, quest_ids in (
            ("Précédente", self.graph.previous_ids(int(quest.id))),
            ("Suivante", self.graph.next_ids(int(quest.id))),
        ):
            for related_id in quest_ids:
                record = catalog.by_id.get(int(related_id))
                if record is None:
                    continue
                button = AtlasButton(f"{label} : {record.name}")
                button.setObjectName("GuideInlineQuestButton")
                button.clicked.connect(
                    lambda _checked=False, target_id=int(record.id): self.open_related_quest(target_id)
                )
                related_rows.append(button)
        if related_rows:
            self.right_layout.addWidget(ui.info_section("QUÊTES LIÉES", related_rows))

        rewards = quest_rewards(quest, achievements)
        if rewards:
            self.right_layout.addWidget(
                ui.info_section("RÉCOMPENSES", [ui.reward_row(reward) for reward in rewards[:14]])
            )
        self.right_layout.addStretch(1)

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
        key = normalize_text(clean_text(line))
        prefix = next(
            (
                value
                for value in ("quete_terminee_", "quete_active_")
                if key.startswith(value)
            ),
            "",
        )
        if not prefix:
            return None
        target = key[len(prefix) :]
        if not target:
            return None

        provider = self.quest_provider
        provider_id = id(provider)
        cached = getattr(self, "_requirement_quest_name_index", None)
        if not (
            isinstance(cached, tuple)
            and len(cached) == 2
            and cached[0] == provider_id
            and isinstance(cached[1], dict)
        ):
            by_name: dict[str, int] = {}
            for quest in provider.list_quests():
                name = normalize_text(getattr(quest, "name", ""))
                try:
                    quest_id = int(getattr(quest, "id"))
                except (TypeError, ValueError):
                    continue
                if name:
                    # Preserve the old linear-search contract: first matching quest
                    # in provider order wins if malformed data contains duplicates.
                    by_name.setdefault(name, quest_id)
            cached = (provider_id, by_name)
            self._requirement_quest_name_index = cached
        return cached[1].get(target)

    def _prerequisite_row(self, text: str, completed: bool | None, linked_id: int | None) -> QWidget:
        ui = _guide_ui()
        if linked_id is None:
            return ui.prerequisite_row(text, completed)
        row = QFrame()
        row.setObjectName("GuidePrerequisiteRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        marker = QLabel("✓" if completed is True else "○" if completed is False else "")
        marker.setObjectName("GuideTreeState")
        marker.setProperty("state", "done" if completed is True else "todo" if completed is False else "neutral")
        marker.setFixedWidth(18)
        marker.setAlignment(Qt.AlignCenter)
        layout.addWidget(marker, 0, Qt.AlignTop)
        button = AtlasButton(clean_text(text))
        button.setObjectName("QuestPrerequisiteButton")
        button.setToolTip("Ouvrir dans l'onglet Quêtes")
        button.clicked.connect(lambda _checked=False, target_id=int(linked_id): self.open_prerequisite_quest(target_id))
        layout.addWidget(button, 1)
        return row

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

    def set_item_completed(self, quest_id: int, item_id: int, completed: bool) -> None:
        self.quest_progress_service.set_item_completed(
            self.character_key,
            int(quest_id),
            int(item_id),
            bool(completed),
        )
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
