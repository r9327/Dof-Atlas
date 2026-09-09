from __future__ import annotations

import re
import logging
import time
import weakref
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QIcon, QImage, QMouseEvent, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from app.constants import QUEST_PROGRESS_FILE
from app.core.character_identity import is_character_key
from app.modules.encyclopedia.models import Guide, GuideChapter, GuidePart, GuideSeries, GuideStep
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import (
    ACHIEVEMENT_PROGRESS_FILE,
    GUIDE_PROGRESS_FILE,
    AchievementProgressService,
    GuideProgressCalculator,
    GuideProgressService,
    LinkService,
    ProgressCount,
    QuestGraphService,
    QuestProgressService,
)
from app.modules.encyclopedia.services.guide_auto_validation_contract import (
    build_route_auto_validation_contract,
)
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)
from app.modules.encyclopedia.services.guide_quest_view_model import (
    DisplayItem,
    DisplayReward,
    DisplaySolutionBlock,
    SolutionObjective,
    activity_labels,
    clean_text,
    clean_requirement_line,
    first_position_from_quest,
    format_number,
    guide_activities,
    guide_items,
    guide_rewards,
    quest_rewards,
    quest_solution_blocks,
    quest_solution_steps,
    reward_label,
)
from app.modules.encyclopedia.views.guide_home_image_cache import (
    get_cached_scaled_pixmap,
    store_scaled_pixmap,
)
from app.modules.encyclopedia.views.guide_progress_presentation import guide_progress_state
from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualView
from app.modules.encyclopedia.widgets import CollapsedColumnRail, FixedColumnSplitter, GuideListModel
from app.modules.encyclopedia.widgets.quest_item_row import item_row
from app.quest_catalog import normalize_text
from app.storage import AtlasButton
from app.ui.theme import PALETTE, render_theme_template

Navigator = Callable[..., bool]
TravelLauncher = Callable[[str], None]
LOGGER = logging.getLogger("dofus_atlas.encyclopedia.images")

GUIDE_ULTIME_LEGACY_ID = "guide_complet"
GUIDE_ULTIME_TITLE = "Guide Ultime"

CATEGORY_ORDER = ("aventure", "alignements", "dofus")
CATEGORY_LABELS = {
    "aventure": "AVENTURE",
    "alignements": "ALIGNEMENTS",
    "dofus": "DOFUS",
}
TRAVEL_COORD_RE = re.compile(r"\[(-?\d+)\s*,\s*(-?\d+)\]")
DOFUS_CARD_MIN_WIDTH = 86
DOFUS_CARD_MAX_WIDTH = 126
DOFUS_CARD_HEIGHT = 118
DOFUS_GRID_SPACING = 8
DOFUS_GRID_MAX_COLUMNS = 5
HOME_GUIDE_LEFT_MIN_WIDTH = 285
HOME_GUIDE_LEFT_MAX_WIDTH = 360
GUIDE_STEPS_OPEN_WIDTH = 190
GUIDE_STEPS_COLLAPSED_WIDTH = 44
SOLUTION_IMAGE_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="DofusAtlasQuestImage",
)


class _AsyncImageDelivery(QObject):
    guideImageBytesRead = Signal(object, object, QSize)
    solutionImageBytesRead = Signal(object, bytes)

    def __init__(self) -> None:
        super().__init__()
        self.guideImageBytesRead.connect(self._deliver_guide_image)
        self.solutionImageBytesRead.connect(self._deliver_solution_image)

    @Slot(object, object, QSize)
    def _deliver_guide_image(self, target_ref, candidates, size: QSize) -> None:
        target = target_ref()
        if target is None or not isValid(target):
            return
        image = QImage()
        used_path = ""
        for path, payload in candidates:
            candidate = _decode_qimage(payload, "guide")
            if not candidate.isNull():
                image = candidate
                used_path = path
                break
        target.imageDecoded.emit(image, size, used_path)

    @Slot(object, bytes)
    def _deliver_solution_image(self, target_ref, payload: bytes) -> None:
        target = target_ref()
        if target is None or not isValid(target):
            return
        target.imageLoaded.emit(_decode_qimage(payload, "solution"))


_ASYNC_IMAGE_DELIVERY: _AsyncImageDelivery | None = None


def _decode_qimage(payload: bytes, kind: str) -> QImage:
    started = time.perf_counter()
    image = QImage.fromData(payload)
    LOGGER.debug(
        "QImage decode kind=%s bytes=%d width=%d height=%d ui_ms=%.3f",
        kind,
        len(payload),
        image.width(),
        image.height(),
        (time.perf_counter() - started) * 1000.0,
    )
    return image


def _ensure_async_image_delivery() -> _AsyncImageDelivery:
    global _ASYNC_IMAGE_DELIVERY
    if _ASYNC_IMAGE_DELIVERY is None:
        _ASYNC_IMAGE_DELIVERY = _AsyncImageDelivery()
    return _ASYNC_IMAGE_DELIVERY


def _decode_guide_image(target_ref, paths: tuple[str, ...], size: QSize) -> None:
    candidates: list[tuple[str, bytes]] = []
    for path in paths:
        try:
            candidates.append((path, Path(path).read_bytes()))
        except OSError:
            continue
    delivery = _ASYNC_IMAGE_DELIVERY
    if delivery is not None:
        delivery.guideImageBytesRead.emit(target_ref, candidates, size)


def _decode_solution_image(target_ref, image_path: str) -> None:
    try:
        payload = Path(image_path).read_bytes()
    except OSError:
        payload = b""
    delivery = _ASYNC_IMAGE_DELIVERY
    if delivery is not None:
        delivery.solutionImageBytesRead.emit(target_ref, payload)


def _single_shot(parent: QObject, delay_ms: int, callback: Callable[[], None]) -> None:
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.timeout.connect(callback)
    timer.timeout.connect(timer.deleteLater)
    timer.start(delay_ms)


def _cancel_pending_future(future) -> None:
    if future is not None:
        future.cancel()


class GuideHomeCard(QFrame):
    """Carte compacte de la page principale des Guides."""

    selected = Signal(str)
    _atlas_async_image_loader = True
    imageDecoded = Signal(object, object, str)

    def __init__(
        self,
        guide: Guide,
        variant: str = "standard",
        progress: tuple[int, int, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._async_image_target: QLabel | None = None
        self._async_image_size = QSize()
        self._async_image_paths: tuple[str, ...] = ()
        self._async_image_started = False
        super().__init__(parent)
        _ensure_async_image_delivery()
        self.guide = guide
        self.variant = variant
        self.progress = progress
        self.setObjectName(
            "GuideDofusCard"
            if variant == "dofus"
            else "GuideAlignmentCard"
            if variant == "alignment"
            else "GuideAdventureCard"
        )
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setProperty("state", _tuple_progress_state(progress))
        self.setToolTip(f"Ouvrir le guide {guide.title}")

        if variant == "dofus":
            self._build_dofus_card(progress)
        elif variant == "alignment":
            self._build_alignment_card()
        else:
            self._build_adventure_card()
        self.imageDecoded.connect(self._finish_async_image)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._start_async_image()

    def _start_async_image(self) -> None:
        if self._async_image_started or not self._async_image_paths:
            return
        self._async_image_started = True
        future = SOLUTION_IMAGE_EXECUTOR.submit(
            _decode_guide_image,
            weakref.ref(self),
            self._async_image_paths,
            QSize(self._async_image_size),
        )
        self.destroyed.connect(
            lambda _obj=None, pending=future: _cancel_pending_future(pending)
        )

    def _build_adventure_card(self) -> None:
        self.setMinimumWidth(245)
        self.setMaximumWidth(275)
        self.setMinimumHeight(172)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        image = QLabel()
        image.setObjectName("GuideAdventureImage")
        image.setFixedHeight(86)
        image.setMinimumWidth(210)
        image.setAlignment(Qt.AlignCenter)
        image.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        if self._load_image(image, QSize(230, 86)):
            root.addWidget(image)

        title = QLabel(_catalog_guide_title(self.guide))
        title.setObjectName("GuideHomeCardTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        root.addWidget(title)

        subtitle = QLabel(_catalog_subtitle(self.guide))
        subtitle.setObjectName("GuideHomeCardMeta")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        root.addWidget(subtitle)
        progress = _progress_label(self.progress)
        if progress:
            count = QLabel(progress)
            count.setObjectName("GuideHomeProgress")
            count.setAlignment(Qt.AlignCenter)
            count.setProperty("state", _tuple_progress_state(self.progress))
            count.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            root.addWidget(count)

    def _build_alignment_card(self) -> None:
        self.setMinimumWidth(126)
        self.setMaximumWidth(150)
        self.setMinimumHeight(138)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(9)
        root.addStretch(1)

        image = QLabel()
        image.setObjectName("GuideAlignmentImage")
        image.setFixedSize(62, 62)
        image.setAlignment(Qt.AlignCenter)
        image.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        if not self._load_image(image, QSize(58, 58)):
            image.setPixmap(atlas_icon("quest").pixmap(32, 32))
        root.addWidget(image, 0, Qt.AlignCenter)

        title = QLabel(_catalog_guide_title(self.guide))
        title.setObjectName("GuideHomeCardTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        root.addWidget(title)
        progress = _progress_label(self.progress)
        if progress:
            count = QLabel(progress)
            count.setObjectName("GuideHomeProgress")
            count.setAlignment(Qt.AlignCenter)
            count.setProperty("state", _tuple_progress_state(self.progress))
            count.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            root.addWidget(count)
        root.addStretch(1)

    def _build_dofus_card(self, progress: tuple[int, int, str] | None) -> None:
        self.setMinimumWidth(DOFUS_CARD_MIN_WIDTH)
        self.setMaximumWidth(DOFUS_CARD_MAX_WIDTH)
        self.setFixedHeight(DOFUS_CARD_HEIGHT)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(5)

        image = QLabel()
        image.setObjectName("GuideDofusImage")
        image.setFixedSize(34, 34)
        image.setAlignment(Qt.AlignCenter)
        image.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        if not self._load_image(image, QSize(30, 30)):
            image.setPixmap(atlas_icon("item").pixmap(24, 24))
        root.addWidget(image, 0, Qt.AlignCenter)

        title = QLabel(_catalog_guide_title(self.guide))
        title.setObjectName("GuideDofusCardTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setFixedHeight(30)
        title.setToolTip(_catalog_guide_title(self.guide))
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        root.addWidget(title)

        completed, total, _state = progress or (0, 0, "")
        count = QLabel(f"{completed} / {total}" if total else "0 / 0")
        count.setObjectName("GuideDofusProgress")
        count.setProperty("state", _tuple_progress_state(progress))
        count.setAlignment(Qt.AlignCenter)
        count.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        root.addWidget(count)

        bar = QProgressBar()
        bar.setObjectName("GuideDofusHomeBar")
        bar.setProperty("state", _tuple_progress_state(progress))
        bar.setRange(0, total if total else 1)
        bar.setValue(min(completed, total) if total else 0)
        bar.setTextVisible(False)
        bar.setFixedHeight(5)
        bar.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        root.addWidget(bar)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.guide.id)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _load_image(self, label: QLabel, size: QSize) -> bool:
        candidates = (
            str(getattr(self.guide, "image_path", "") or ""),
            str(getattr(getattr(self.guide, "illustration_item", None), "image_path", "") or ""),
            str(getattr(getattr(self.guide, "reward_item", None), "image_path", "") or ""),
        )
        existing: list[str] = []
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            try:
                if path.exists() and path.is_file():
                    existing.append(str(path))
            except OSError:
                continue
        if not existing:
            return False
        first_path = Path(existing[0])
        cached = get_cached_scaled_pixmap(first_path, size)
        if not cached.isNull():
            label.setPixmap(cached)
            return True
        self._async_image_target = label
        self._async_image_size = QSize(size)
        self._async_image_paths = tuple(existing)
        return True

    def _finish_async_image(self, image: QImage, size: QSize, used_path: str) -> None:
        label = self._async_image_target
        if label is None:
            return
        if image.isNull() or not used_path:
            if self.variant == "alignment":
                label.setPixmap(atlas_icon("quest").pixmap(32, 32))
            elif self.variant == "dofus":
                label.setPixmap(atlas_icon("item").pixmap(24, 24))
            else:
                label.hide()
            return
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        scaled = store_scaled_pixmap(Path(used_path), size, scaled)
        label.setPixmap(scaled)


class DofusGuideGrid(QScrollArea):
    """Grille responsive des Dofus disponibles dans l'accueil Guides."""

    def __init__(self, cards: list[GuideHomeCard], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cards = cards
        self.current_columns = 0
        self.current_card_width = 0
        self.setObjectName("GuideDofusGridScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.content = QWidget()
        self.content.setObjectName("GuideDofusGridContent")
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(DOFUS_GRID_SPACING)
        self.grid.setVerticalSpacing(DOFUS_GRID_SPACING)
        self.grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.grid.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.setWidget(self.content)
        self.reflow_now()
        _single_shot(self, 0, self.reflow_now)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.reflow_now()

    def reflow_now(self) -> None:
        if not self.cards:
            return
        available = self.viewport().width() or self.width()
        available = max(1, available)
        spacing = DOFUS_GRID_SPACING
        columns = max(1, int((available + spacing) / (DOFUS_CARD_MIN_WIDTH + spacing)))
        columns = min(DOFUS_GRID_MAX_COLUMNS, columns, len(self.cards))
        while columns > 1 and columns * DOFUS_CARD_MIN_WIDTH + (columns - 1) * spacing > available:
            columns -= 1
        usable = max(1, available - (columns - 1) * spacing)
        card_width = int(usable / columns)
        card_width = min(DOFUS_CARD_MAX_WIDTH, max(DOFUS_CARD_MIN_WIDTH, card_width))
        if card_width > available:
            card_width = available
        if self.current_columns == columns and self.current_card_width == card_width and self.grid.count() == len(self.cards):
            return

        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()

        for index, card in enumerate(self.cards):
            card.setFixedWidth(card_width)
            card.setFixedHeight(DOFUS_CARD_HEIGHT)
            self.grid.addWidget(card, index // columns, index % columns)
            card.show()
        rows = (len(self.cards) + columns - 1) // columns
        previous_rows = (len(self.cards) + max(1, self.current_columns) - 1) // max(1, self.current_columns)
        for row in range(max(rows, previous_rows) + 1):
            self.grid.setRowMinimumHeight(row, 0)
            self.grid.setRowStretch(row, 0)
        for column in range(DOFUS_GRID_MAX_COLUMNS):
            self.grid.setColumnMinimumWidth(column, 0)
            self.grid.setColumnStretch(column, 0)
        for row in range(rows):
            self.grid.setRowMinimumHeight(row, DOFUS_CARD_HEIGHT)
        for column in range(columns):
            self.grid.setColumnMinimumWidth(column, card_width)
        self.content.setMinimumSize(
            columns * card_width + (columns - 1) * spacing,
            rows * DOFUS_CARD_HEIGHT + (rows - 1) * spacing,
        )
        self.content.updateGeometry()
        self.grid.invalidate()
        self.current_columns = columns
        self.current_card_width = card_width



class QuestLine(QFrame):
    selected = Signal(int)
    completionToggled = Signal(int, bool)

    def __init__(
        self,
        step: GuideStep,
        active: bool = False,
        compact: bool = False,
        activity_keys: Iterable[str] = (),
        row_number: int = 0,
        completed: bool | None = None,
        level_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.step = step
        self.active = bool(active)
        self.compact = bool(compact)
        self.completed = bool(completed)

        _ = activity_keys
        _ = row_number

        unavailable = not step.available

        self.setObjectName(
            "GuideQuestLineUnavailable"
            if unavailable
            else "GuideQuestLineActive"
            if active
            else "GuideQuestLine"
        )

        self.setProperty(
            "state",
            "done" if self.completed else "todo",
        )

        self.setCursor(
            Qt.PointingHandCursor
            if (
                step.step_type == "quest"
                and step.entity_id is not None
                and step.available
            )
            else Qt.ArrowCursor
        )

        self.setToolTip(step.display_title)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            8 if compact else 10,
            5,
            8 if compact else 10,
            5,
        )
        layout.setSpacing(8)

        title = QLabel(step.display_title)
        title.setObjectName("GuideQuestLineTitle")
        title.setProperty(
            "state",
            "done" if self.completed else "todo",
        )
        title.setWordWrap(step.step_type != "quest")
        title.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )
        layout.addWidget(title, 1)

        if level_text:
            level = QLabel(level_text)
            level.setObjectName("GuideQuestLevel")
            level.setAlignment(
                Qt.AlignRight | Qt.AlignVCenter
            )
            level.setAttribute(
                Qt.WA_TransparentForMouseEvents,
                True,
            )
            layout.addWidget(level)

        if (
            step.step_type == "quest"
            and step.entity_id is not None
        ):
            marker = QToolButton()
            marker.setObjectName("GuideQuestState")
            marker.setText(
                "\u2713"
                if self.completed
                else "\u25cb"
            )
            marker.setProperty(
                "state",
                "done" if self.completed else "todo",
            )
            marker.setFixedSize(22, 22)
            marker.setCursor(Qt.PointingHandCursor)
            marker.setFocusPolicy(Qt.NoFocus)
            marker.clicked.connect(
                self._toggle_completion
            )
            layout.addWidget(marker)

    def _toggle_completion(self) -> None:
        if (
            self.step.step_type == "quest"
            and self.step.entity_id is not None
        ):
            self.completionToggled.emit(
                int(self.step.entity_id),
                not self.completed,
            )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.LeftButton
            and self.step.step_type == "quest"
            and self.step.entity_id is not None
            and self.step.available
        ):
            self.selected.emit(
                int(self.step.entity_id)
            )
            event.accept()
            return

        super().mouseReleaseEvent(event)



class GuideStructureRow(QFrame):
    selected = Signal(str)
    completionToggled = Signal(object, bool)

    def __init__(
        self,
        title: str,
        series_id: str,
        level: int,
        progress: ProgressCount,
        active: bool,
        quest_ids: Iterable[int] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.series_id = series_id
        self.clickable = bool(series_id)

        self.quest_ids = tuple(
            dict.fromkeys(
                int(value)
                for value in quest_ids
            )
        )

        state = _progress_state(progress)

        self.setObjectName(
            "GuideTreeRowActive"
            if active
            else "GuideTreeRow"
        )
        self.setProperty("state", state)

        self.setCursor(
            Qt.PointingHandCursor
            if self.clickable
            else Qt.ArrowCursor
        )

        self.setAttribute(Qt.WA_Hover, True)
        self.setMinimumHeight(
            24 if level else 28
        )
        self.setMaximumHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            8 + level * 14,
            3,
            8,
            3,
        )
        layout.setSpacing(7)

        text = QLabel(title)
        text.setObjectName(
            "GuideTreePartText"
            if level == 0
            else "GuideTreeChildText"
        )
        text.setProperty("state", state)
        text.setWordWrap(False)
        text.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )
        layout.addWidget(text, 1)

        marker = QToolButton()
        marker.setObjectName("GuideTreeStateButton")
        marker.setProperty("state", state)
        marker.setText(
            "\u2713"
            if progress.is_complete
            else "\u25cf"
            if progress.completed
            else "\u25cb"
        )
        marker.setFixedSize(20, 20)
        marker.setFocusPolicy(Qt.NoFocus)

        marker.setEnabled(bool(self.quest_ids))
        marker.setCursor(
            Qt.PointingHandCursor
            if self.quest_ids
            else Qt.ArrowCursor
        )

        marker.setToolTip(
            "Annuler cette etape"
            if progress.is_complete
            else "Valider cette etape"
        )

        marker.clicked.connect(
            lambda: self.completionToggled.emit(
                self.quest_ids,
                not progress.is_complete,
            )
        )

        layout.addWidget(marker)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.LeftButton
            and self.clickable
        ):
            self.selected.emit(self.series_id)
            event.accept()
            return

        super().mouseReleaseEvent(event)


class GuideSeriesSummaryRow(QFrame):
    selected = Signal(str)

    def __init__(
        self,
        title: str,
        series_id: str,
        progress_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.series_id = series_id
        self.setObjectName("GuideSeriesSummaryRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMinimumHeight(30)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        label = QLabel(title)
        label.setObjectName("GuideSeriesSummaryTitle")
        label.setWordWrap(False)
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(label, 1)

        progress = QLabel(progress_text)
        progress.setObjectName("GuideSeriesSummaryProgress")
        progress.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        progress.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(progress)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.series_id)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class GuideCollapsedStepsRail(CollapsedColumnRail):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Afficher les \u00e9tapes", parent)


class SolutionImageLabel(QLabel):
    imageLoaded = Signal(object)

    def __init__(self, image_path: str, caption: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        _ensure_async_image_delivery()
        self.source = QPixmap()
        self._image_path = str(image_path)
        self._rendered_width = 0
        self._update_scheduled = False
        self._image_load_started = False
        self._image_load_future = None
        self._image_popup: QDialog | None = None
        self.setObjectName("QuestSolutionImage")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(1)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMaximumWidth(540)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(caption)
        self.setText("Chargement de l'image…")
        self.imageLoaded.connect(self.finish_image_load)
        # Let the document and navigation settle before decoding large local
        # screenshots. Fast previous/next navigation then cancels obsolete
        # loads with the deleted widget instead of competing with the click.
        self._image_load_timer = QTimer(self)
        self._image_load_timer.setSingleShot(True)
        self._image_load_timer.timeout.connect(self.start_image_load)
        self._image_load_timer.timeout.connect(self._image_load_timer.deleteLater)

    def event(self, event) -> bool:
        if event.type() == QEvent.DeferredDelete:
            # Stop native timer delivery before Qt tears down the receiver. In a
            # long-lived QApplication, queued timeout events for rapidly removed
            # solution rows can otherwise outlive their Python wrapper.
            if isValid(self._image_load_timer):
                self._image_load_timer.stop()
            _cancel_pending_future(self._image_load_future)
        return super().event(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._image_load_started and not self._image_load_timer.isActive():
            self._image_load_timer.start(250)

    def start_image_load(self) -> None:
        if self._image_load_started:
            return
        self._image_load_started = True
        future = SOLUTION_IMAGE_EXECUTOR.submit(
            _decode_solution_image,
            weakref.ref(self),
            self._image_path,
        )
        self._image_load_future = future
        self.destroyed.connect(
            lambda _obj=None, pending=future: _cancel_pending_future(pending)
        )

    def finish_image_load(self, image: QImage) -> None:
        if image.isNull():
            self.setText("")
            self.setMinimumHeight(0)
            return
        self.source = QPixmap.fromImage(image)
        self.setText("")
        self.setMinimumHeight(0)
        self.update_pixmap()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.schedule_pixmap_update()

    def schedule_pixmap_update(self) -> None:
        if self._update_scheduled:
            return
        self._update_scheduled = True
        _single_shot(self, 0, self.update_pixmap)

    def update_pixmap(self) -> None:
        self._update_scheduled = False
        if self.source.isNull():
            return
        parent_width = self.parentWidget().width() if self.parentWidget() is not None else 520
        available_width = min(520, max(120, parent_width - 24))
        target = self.source.size()
        target.scale(available_width, 320, Qt.KeepAspectRatio)
        width = max(1, target.width())
        if width == self._rendered_width and self.pixmap() is not None:
            return
        pixmap = self.source.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)
        self.setFixedWidth(pixmap.width() + 12)
        self.setFixedHeight(pixmap.height() + 6)
        self._rendered_width = width

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and not self.source.isNull():
            if self._image_popup is not None and self._image_popup.isVisible():
                self._image_popup.close()
                self._image_popup = None
                event.accept()
                return

            dialog = QDialog(self, Qt.Popup)
            dialog.setObjectName("AtlasDialog")
            dialog.setWindowTitle(self.toolTip() or "Image de solution")
            root = QVBoxLayout(dialog)
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(0)

            image = QLabel()
            image.setAlignment(Qt.AlignCenter)
            screen = self.screen()
            available = screen.availableGeometry().size() if screen is not None else QSize(1280, 800)
            max_width = max(320, min(1180, int(available.width() * 0.82)))
            max_height = max(240, min(860, int(available.height() * 0.82)))
            target = self.source.size()
            target.scale(max_width - 24, max_height - 24, Qt.KeepAspectRatio)
            image.setPixmap(self.source.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            root.addWidget(image)
            dialog.resize(target.width() + 16, target.height() + 16)

            center = self.mapToGlobal(self.rect().center())
            dialog.move(center.x() - dialog.width() // 2, center.y() - dialog.height() // 2)
            dialog.finished.connect(lambda _result: setattr(self, "_image_popup", None))
            self._image_popup = dialog
            dialog.show()
            dialog.raise_()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class CollapsibleInfoSection(QFrame):
    toggled = Signal(bool)

    def __init__(
        self,
        title: str,
        status_text: str,
        state: str,
        expanded: bool,
        widgets: list[QWidget],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.expanded = bool(expanded)
        self.setObjectName("GuideCollapsibleSection")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 8)
        root.setSpacing(6)
        if title == "PRÉREQUIS":
            root.addWidget(hidden_label("Prérequis"))

        header = QFrame()
        header.setObjectName("GuideCollapsibleHeader")
        header.setCursor(Qt.PointingHandCursor)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        marker = QLabel("✓" if state == "done" else "●" if state == "partial" else "○")
        marker.setObjectName("GuideTreeState")
        marker.setProperty("state", state)
        marker.setFixedWidth(18)
        marker.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(marker)
        title_label = QLabel(title)
        title_label.setObjectName("GuideInfoSectionTitle")
        header_layout.addWidget(title_label, 1)
        status = QLabel(status_text)
        status.setObjectName("GuideProgressText")
        status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(status)
        self.chevron = QToolButton()
        self.chevron.setObjectName("GuideChevronButton")
        self.chevron.setFixedSize(24, 24)
        self.chevron.setCursor(Qt.PointingHandCursor)
        self.chevron.setFocusPolicy(Qt.NoFocus)
        self.chevron.clicked.connect(self._toggle)
        header_layout.addWidget(self.chevron)
        header.mouseReleaseEvent = self._header_clicked  # type: ignore[method-assign]
        root.addWidget(header)

        self.body = QWidget()
        self.body.setObjectName("GuideCollapsibleBody")
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(6)
        for widget in widgets:
            body_layout.addWidget(widget)
        root.addWidget(self.body)
        self.set_expanded(self.expanded)

    def _header_clicked(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._toggle()
            event.accept()

    def _toggle(self) -> None:
        self.set_expanded(not self.expanded)
        self.toggled.emit(self.expanded)

    def set_expanded(self, expanded: bool) -> None:
        self.expanded = bool(expanded)
        self.body.setVisible(self.expanded)
        self.chevron.setText("▲" if self.expanded else "▼")
        self.chevron.setToolTip(
            "Replier la section"
            if self.expanded
            else "Déplier la section"
        )


class GuidesView(QWidget):
    """Catalogue Guides, vue guide et vue quête dans l'onglet Guides."""

    CATALOG = "CATALOG"
    GUIDE_OVERVIEW = "GUIDE_OVERVIEW"
    QUEST_DETAIL = "QUEST_DETAIL"

    def __init__(
        self,
        status_callback,
        parent: QWidget | None = None,
        provider: GuideProvider | None = None,
        quest_provider: QuestProvider | None = None,
        achievement_provider: AchievementProvider | None = None,
        achievement_progress_service: AchievementProgressService | None = None,
        guide_progress_service: GuideProgressService | None = None,
        quest_progress_path: Path = QUEST_PROGRESS_FILE,
        achievement_progress_path: Path = ACHIEVEMENT_PROGRESS_FILE,
        guide_progress_path: Path = GUIDE_PROGRESS_FILE,
        profile_path: Path | None = None,
        client_index_path: Path | None = None,
        navigate_callback: Navigator | None = None,
        launch_travel_callback: TravelLauncher | None = None,
        character_key: str = "",
        graph: QuestGraphService | None = None,
        initial_progress_by_guide: dict[str, tuple[int, int, str]] | None = None,
        initial_progress_character_key: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GuidesView")

        self.guide_ultime_service: GuideUltimeManualRuntimeService | None = None
        self.guide_ultime_view: GuideUltimeManualView | None = None
        self._external_progress_signature: tuple[object, ...] | None = None
        self._home_render_signature: tuple[object, ...] | None = None
        self._home_progress_cache_signature: tuple[object, ...] | None = None
        self._home_progress_cache: dict[str, tuple[int, int, str]] = {}

        self.status_callback = status_callback
        self.quest_provider = quest_provider or QuestProvider()
        self.achievement_provider = achievement_provider or AchievementProvider(quest_provider=self.quest_provider)
        self.provider = provider or GuideProvider(
            quest_provider=self.quest_provider,
            achievement_provider=self.achievement_provider,
        )
        self.quest_progress_path = quest_progress_path
        self.achievement_progress_service = achievement_progress_service or AchievementProgressService(achievement_progress_path)
        self.guide_progress_service = guide_progress_service or GuideProgressService(guide_progress_path)
        self.quest_progress_service = QuestProgressService(quest_progress_path)
        self.link_service = LinkService(navigate_callback)
        self.launch_travel_callback = launch_travel_callback
        self.current_character_key = character_key or ""
        self.quest_progress = self.quest_progress_service.progress
        self.quest_catalog = self.quest_provider.get_catalog()
        self.progress_calculator = GuideProgressCalculator(
            self.quest_progress_service,
            self.guide_progress_service,
            self.achievement_progress_service,
            self.quest_catalog.by_id,
        )
        self.graph = graph or QuestGraphService(self.quest_provider, self.provider, self.achievement_provider)

        self.search_text = ""
        self.guides: list[Guide] = self.provider.load_all()
        self._sync_achievement_progress()
        self.visible_guides: list[Guide] = list(self.guides)
        self.result_model = GuideListModel(self)
        self.current_guide_id: str | None = None
        self.current_quest_id: int | None = None
        self.state = self.CATALOG
        self.expanded_chapters: dict[str, set[str]] = {}
        self.guide_scroll_positions: dict[str, int] = {}
        self.quest_nav_scroll_positions: dict[str, int] = {}
        self.current_series_by_guide: dict[str, str] = {}
        self.guide_prerequisites_expanded: dict[str, bool] = {}
        self.steps_collapsed = False
        self._initial_progress_by_guide = dict(initial_progress_by_guide or {})
        self._initial_progress_character_key = initial_progress_character_key or ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setObjectName("GuidesStack")
        root.addWidget(self.stack, 1)

        self.home_page = self.build_home_page()
        self.detail_page = self.build_detail_page()
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.detail_page)
        self.stack.setCurrentWidget(self.home_page)

        self.apply_local_style()
        self.refresh_home()
        self._external_progress_signature = self._current_external_progress_signature()
        self.status_callback(f"{len(self.guides)} guide(s) chargés.")

    def build_home_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("GuidesHomePage")
        root = QVBoxLayout(page)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.home_content = QWidget()
        self.home_content.setObjectName("GuidesHomeContent")
        self.home_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.home_layout = QVBoxLayout(self.home_content)
        self.home_layout.setContentsMargins(2, 2, 2, 2)
        self.home_layout.setSpacing(8)

        root.addWidget(self.home_content, 1)
        return page

    def build_detail_page(self) -> QWidget:
        from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView

        page = QWidget()
        page.setObjectName("GuidesDetailPage")
        root = QVBoxLayout(page)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self.detail_header = QFrame()
        self.detail_header.setObjectName("GuideHeader")
        header_layout = QHBoxLayout(self.detail_header)
        header_layout.setContentsMargins(8, 8, 10, 8)
        header_layout.setSpacing(10)

        self.detail_header_image = QLabel()
        self.detail_header_image.setObjectName("GuideHeaderImage")
        self.detail_header_image.setFixedSize(44, 44)
        self.detail_header_image.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.detail_header_image)

        header_text = QVBoxLayout()
        header_text.setContentsMargins(0, 0, 0, 0)
        header_text.setSpacing(2)
        self.detail_header_title = QLabel()
        self.detail_header_title.setObjectName("GuideHeaderTitle")
        self.detail_header_title.setWordWrap(False)
        header_text.addWidget(self.detail_header_title)
        self.detail_header_meta = QLabel()
        self.detail_header_meta.setObjectName("GuideHeaderMeta")
        self.detail_header_meta.setWordWrap(False)
        header_text.addWidget(self.detail_header_meta)
        header_layout.addLayout(header_text, 1)
        self.detail_header_progress = QLabel()
        self.detail_header_progress.setObjectName("GuideHeaderProgress")
        self.detail_header_progress.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(self.detail_header_progress, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.detail_header_done_button = QToolButton()
        self.detail_header_done_button.setObjectName("GuideHeaderDoneButton")
        self.detail_header_done_button.setCursor(Qt.PointingHandCursor)
        self.detail_header_done_button.setFocusPolicy(Qt.NoFocus)
        self.detail_header_done_button.clicked.connect(self.toggle_current_quest_completed)
        header_layout.addWidget(self.detail_header_done_button, 0, Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(self.detail_header)

        self.breadcrumb = QFrame()
        self.breadcrumb.setObjectName("GuideBreadcrumb")
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb)
        self.breadcrumb_layout.setContentsMargins(8, 5, 8, 5)
        self.breadcrumb_layout.setSpacing(5)
        root.addWidget(self.breadcrumb)

        self.splitter = FixedColumnSplitter(Qt.Horizontal)
        self.splitter.setObjectName("GuideDetailSplitter")
        self.detail_stack = QStackedWidget()
        self.detail_stack.setObjectName("GuideDetailContentStack")
        self.detail_stack.addWidget(self.splitter)
        root.addWidget(self.detail_stack, 1)

        self.left_panel, self.left_scroll, self.left_layout = self._build_column("GuideLeftPanel")
        self.center_panel, self.center_scroll, self.center_layout = self._build_column("GuideCenterPanel")
        self.right_panel, self.right_scroll, self.right_layout = self._build_column("GuideRightPanel")

        self.left_panel.setMinimumWidth(GUIDE_STEPS_OPEN_WIDTH)
        self.left_panel.setMaximumWidth(GUIDE_STEPS_OPEN_WIDTH)
        self.right_panel.setMinimumWidth(220)
        self.center_panel.setMinimumWidth(260)

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.center_panel)
        self.splitter.addWidget(self.right_panel)
        self.quest_detail_view = QuestDetailView(
            self.quest_provider,
            self.graph,
            self.quest_progress_service,
            achievement_provider=self.achievement_provider,
            guide_provider=self.provider,
            character_key=self.current_character_key,
            open_quest=self.open_quest_from_guide,
            open_prerequisite=self.open_prerequisite_from_guide,
            navigate_entity=self.link_service.navigate_to_entity,
        )
        self.quest_detail_view.questProgressChanged.connect(self.on_shared_quest_progress_changed)
        self.detail_stack.addWidget(self.quest_detail_view)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 50)
        self.splitter.setStretchFactor(2, 30)
        self.splitter.setSizes([GUIDE_STEPS_OPEN_WIDTH, 350, 230])
        _single_shot(self, 0, self._lock_steps_splitter_handle)
        return page

    def _lock_steps_splitter_handle(self) -> None:
        handle_getter = getattr(
            self.splitter,
            "handle",
            None,
        )

        if not callable(handle_getter):
            return

        handle = handle_getter(1)

        if handle is None:
            return

        handle.setEnabled(False)
        handle.setCursor(Qt.ArrowCursor)

    def _build_column(self, object_name: str) -> tuple[QFrame, QScrollArea, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName(object_name)
        root = QVBoxLayout(panel)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setObjectName(f"{object_name}Scroll")

        content = QWidget()
        content.setObjectName(f"{object_name}Content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        return panel, scroll, layout

    def set_search_text(self, text: str) -> None:
        text = text or ""
        if text == self.search_text:
            return
        self.search_text = text
        self.refresh_home()
        if self.state != self.CATALOG:
            self.show_home()

    def _sync_achievement_progress(self) -> bool:
        if not is_character_key(self.current_character_key):
            return False
        return self.achievement_progress_service.sync_from_quest_progress(
            self.current_character_key,
            self.achievement_provider,
            self.quest_progress_service,
            self.provider,
        )

    def _set_character_key_standard(self, character_key: str) -> None:
        character_key = character_key or ""
        if character_key == self.current_character_key:
            return
        self.current_character_key = character_key
        self.quest_progress = self.quest_progress_service.reload()
        self._sync_achievement_progress()
        self.refresh_home()
        if self.current_guide_id and self.current_quest_id is not None:
            self.show_quest_detail(self.current_quest_id, preserve_scroll=True)
        elif self.current_guide_id:
            self.show_guide_overview(self.current_guide_id, preserve_scroll=True)

    def _refresh_external_progress_standard(self) -> None:
        self.quest_progress = self.quest_progress_service.reload()
        self.guides = self.provider.load_all()
        self._sync_achievement_progress()
        self.refresh_home()
        if self.current_guide_id and self.current_quest_id is not None:
            self.show_quest_detail(self.current_quest_id, preserve_scroll=True)
        elif self.current_guide_id:
            self.show_guide_overview(self.current_guide_id, preserve_scroll=True)

    def _refresh_home_uncached(self) -> None:
        clear_layout(self.home_layout)
        self.visible_guides = self.provider.search(self.search_text)
        self.result_model.set_guides(self.visible_guides)
        if not self.visible_guides:
            empty = QFrame()
            empty.setObjectName("GuidesHomeEmpty")
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(20, 30, 20, 30)
            message = QLabel("Aucun guide ne correspond à la recherche.")
            message.setObjectName("GuidesHomeEmptyText")
            message.setAlignment(Qt.AlignCenter)
            empty_layout.addWidget(message)
            self.home_layout.addWidget(empty)
            self.home_layout.addStretch(1)
            return

        grouped: dict[str, list[Guide]] = {}
        for guide in self.visible_guides:
            grouped.setdefault(guide.category, []).append(guide)
        progress_by_guide = self.initial_home_progress()
        if progress_by_guide is None:
            progress_by_guide = {
                guide.id: self.guide_progress_tuple(guide)
                for guide in self.visible_guides
            }
        self.result_model.set_progress(progress_by_guide)

        catalog = QFrame()
        catalog.setObjectName("GuidesCatalogGrid")
        catalog.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        catalog_layout = QGridLayout(catalog)
        catalog_layout.setContentsMargins(0, 0, 0, 0)
        catalog_layout.setHorizontalSpacing(8)
        catalog_layout.setVerticalSpacing(8)
        catalog_layout.setRowStretch(0, 1)

        column = 0
        if grouped.get("aventure") or grouped.get("alignements"):
            catalog_layout.addWidget(self.build_progression_column(grouped, progress_by_guide), 0, column)
            catalog_layout.setColumnMinimumWidth(column, HOME_GUIDE_LEFT_MIN_WIDTH)
            catalog_layout.setColumnStretch(column, 0)
            column += 1

        dofus_guides = grouped.get("dofus", [])
        if dofus_guides:
            catalog_layout.addWidget(self.build_category_section("dofus", dofus_guides, progress_by_guide=progress_by_guide), 0, column)
            catalog_layout.setColumnStretch(column, 1)
            column += 1

        for category, guides in grouped.items():
            if category not in CATEGORY_ORDER:
                catalog_layout.addWidget(self.build_category_section(category, guides, progress_by_guide=progress_by_guide), 0, column)
                catalog_layout.setColumnStretch(column, 1)
                column += 1

        self.home_layout.addWidget(catalog, 1)

    def _initial_home_progress_uncached(self) -> dict[str, tuple[int, int, str]] | None:
        if not self._initial_progress_by_guide:
            return None
        if self._initial_progress_character_key != self.current_character_key:
            return None
        visible_ids = {guide.id for guide in self.visible_guides}
        if not visible_ids.issubset(self._initial_progress_by_guide):
            return None
        progress = {
            guide_id: self._initial_progress_by_guide[guide_id]
            for guide_id in visible_ids
        }
        self._initial_progress_by_guide = {}
        return progress

    def build_progression_column(
        self,
        grouped: dict[str, list[Guide]],
        progress_by_guide: dict[str, tuple[int, int, str]],
    ) -> QFrame:
        column = QFrame()
        column.setObjectName("GuidesHomeProgressionColumn")
        column.setMinimumWidth(HOME_GUIDE_LEFT_MIN_WIDTH)
        column.setMaximumWidth(HOME_GUIDE_LEFT_MAX_WIDTH)
        column.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        root = QVBoxLayout(column)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        adventure_guides = grouped.get("aventure", [])
        alignment_guides = grouped.get("alignements", [])
        if adventure_guides:
            root.addWidget(self.build_category_section("aventure", adventure_guides, embedded=True, progress_by_guide=progress_by_guide), 5)
        if adventure_guides and alignment_guides:
            root.addWidget(self._home_category_separator())
        if alignment_guides:
            root.addWidget(self.build_category_section("alignements", alignment_guides, embedded=True, progress_by_guide=progress_by_guide), 4)
        root.addStretch(1)
        return column

    def _home_category_separator(self) -> QFrame:
        separator = QFrame()
        separator.setObjectName("GuidesHomeSeparator")
        separator.setFixedHeight(1)
        return separator

    def build_category_section(
        self,
        category: str,
        guides: list[Guide],
        embedded: bool = False,
        progress_by_guide: dict[str, tuple[int, int, str]] | None = None,
    ) -> QFrame:
        section = QFrame()
        section.setObjectName("GuidesHomeSubCategory" if embedded else "GuidesHomeCategory")
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root = QVBoxLayout(section)
        if embedded:
            root.setContentsMargins(0, 0, 0, 0)
        else:
            root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        if category == "dofus":
            section.setMinimumWidth(220)
        elif category == "alignements":
            section.setMinimumWidth(260)
            if not embedded:
                section.setMaximumWidth(330)
        else:
            section.setMinimumWidth(245)
            if not embedded:
                section.setMaximumWidth(295)

        label = CATEGORY_LABELS.get(category, category.title())
        title = QLabel(label)
        title.setObjectName("GuidesHomeCategoryTitle")
        root.addWidget(title)

        sorted_guides = sorted(guides, key=lambda row: (row.order, row.title.casefold()))
        if category == "dofus":
            cards: list[GuideHomeCard] = []
            for guide in sorted_guides:
                card = GuideHomeCard(
                    guide,
                    variant="dofus",
                    progress=(progress_by_guide or {}).get(guide.id) or self.guide_progress_tuple(guide),
                )
                card.selected.connect(self.select_guide)
                cards.append(card)
            root.addWidget(DofusGuideGrid(cards), 1)
        elif category == "alignements":
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(8)
            for index, guide in enumerate(sorted_guides):
                card = GuideHomeCard(
                    guide,
                    variant="alignment",
                    progress=(progress_by_guide or {}).get(guide.id) or self.guide_progress_tuple(guide),
                )
                card.selected.connect(self.select_guide)
                grid.addWidget(card, index // 2, index % 2)
            grid.setColumnMinimumWidth(0, 126)
            grid.setColumnMinimumWidth(1, 126)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            root.addLayout(grid)
        else:
            for guide in sorted_guides:
                card = GuideHomeCard(
                    guide,
                    variant="adventure",
                    progress=(progress_by_guide or {}).get(guide.id) or self.guide_progress_tuple(guide),
                )
                card.selected.connect(self.select_guide)
                root.addWidget(card)
        if category != "dofus":
            root.addStretch(1)
        return section

    def _select_guide_standard(self, guide_id: str) -> bool:
        guide = self.provider.get_by_id(str(guide_id))
        if guide is None:
            self.status_callback("Guide introuvable.")
            return False
        self.current_guide_id = guide.id
        self.current_quest_id = None
        self._ensure_chapters_initialized(guide)
        self.show_guide_overview(guide.id, preserve_scroll=True)
        self.status_callback(f"Guide : {guide.title}")
        return True

    def _show_guide_overview_standard(self, guide_id: str, preserve_scroll: bool = False) -> None:
        guide = self.provider.get_by_id(str(guide_id))
        if guide is None:
            return
        previous_position = self.guide_scroll_positions.get(guide.id, 0) if preserve_scroll else 0
        self.current_guide_id = guide.id
        self.current_quest_id = None
        self.state = self.GUIDE_OVERVIEW
        self._ensure_chapters_initialized(guide)
        self._ensure_selected_series(guide)
        self._configure_detail_layout(guide, False)
        self.detail_header.setVisible(True)
        self._render_header(guide)
        self._render_breadcrumb(guide)
        if self._guide_uses_steps_column(guide):
            self._populate_guide_left(guide)
        else:
            clear_layout(self.left_layout)
        self._populate_series_quests(guide)
        self._populate_guide_info(guide)
        self.stack.setCurrentWidget(self.detail_page)
        _single_shot(
            self,
            0,
            lambda value=previous_position: self.center_scroll.verticalScrollBar().setValue(value),
        )

    def show_quest_detail(self, quest_id: int, preserve_scroll: bool = False) -> bool:
        guide = self.current_guide()
        if guide is None:
            return False
        quest = self.quest_catalog.by_id.get(int(quest_id))
        step = self.step_for_quest(guide, int(quest_id))
        if quest is None or step is None:
            self.status_callback("Quête introuvable dans ce guide.")
            return False
        if self.state == self.GUIDE_OVERVIEW:
            self.guide_scroll_positions[guide.id] = self.center_scroll.verticalScrollBar().value()
        elif self.state == self.QUEST_DETAIL:
            self.quest_nav_scroll_positions[guide.id] = self.left_scroll.verticalScrollBar().value()
        previous_left = self.quest_nav_scroll_positions.get(guide.id, 0) if preserve_scroll else self.left_scroll.verticalScrollBar().value()
        self.current_quest_id = quest.id
        self.state = self.QUEST_DETAIL
        self._ensure_chapters_initialized(guide)
        series_ref = self._series_ref_for_quest(guide, quest.id)
        if series_ref is not None:
            self.current_series_by_guide[guide.id] = series_ref[2].id
        self._configure_detail_layout(guide, True)
        self._render_header(guide)
        self.detail_header.setVisible(True)
        self._render_breadcrumb(guide, quest.name)
        from app.modules.encyclopedia.widgets.quest_detail_view import QuestViewContext

        self.quest_detail_view.set_character_key(self.current_character_key)
        self.quest_detail_view.show_quest(
            int(quest.id),
            QuestViewContext(
                host="guide",
                guide_id=guide.id,
                guide_title=guide.title,
            ),
        )
        self.stack.setCurrentWidget(self.detail_page)
        _single_shot(
            self,
            0,
            lambda value=previous_left: self.left_scroll.verticalScrollBar().setValue(value),
        )
        self.status_callback(f"Quête : {quest.name}")
        return True


    def open_quest_from_guide(
        self,
        quest_id: int,
    ) -> bool:
        return self.show_quest_detail(
            int(quest_id)
        )

    def open_prerequisite_from_guide(self, quest_id: int) -> bool:
        guide = self.current_guide()
        if guide is not None and self.link_service.navigate_to_entity(
            "quest",
            int(quest_id),
            source="guide_prerequisite",
            guide_id=guide.id,
            guide_title=guide.title,
            from_quest_id=self.current_quest_id,
        ):
            return True
        return self.show_quest_detail(int(quest_id))



    def show_home(self) -> None:
        self.current_guide_id = None
        self.current_quest_id = None
        self.state = self.CATALOG

        self.refresh_home()

        self.stack.setCurrentWidget(
            self.home_page
        )

        self.status_callback(
            "Guides : choix du parcours"
        )

    def current_guide(self) -> Guide | None:
        return self.provider.get_by_id(self.current_guide_id) if self.current_guide_id else None

    def open_achievement_context(self, achievement_id: int) -> bool:
        guides = self.provider.get_guides_for_entity("achievement", int(achievement_id))
        if not guides:
            return False
        guide = sorted(
            guides,
            key=lambda item: (
                0 if item.category == "dofus" else 1 if item.category == "alignements" else 2,
                item.order,
                normalize_text(item.title),
            ),
        )[0]
        return self.select_guide(guide.id)

    def step_completed(self, guide: Guide, step: GuideStep) -> bool:
        return self.progress_calculator.step_completed(guide, step, self.current_character_key)

    def set_manual_step(self, guide_id: str, step_id: str, completed: bool) -> None:
        self.guide_progress_service.set_manual_step_completed(
            self.current_character_key,
            str(guide_id),
            str(step_id),
            bool(completed),
        )




    def _update_visible_quest_progress(
        self,
        guide: Guide,
        quest_ids: Iterable[int],
    ) -> None:
        ids = {
            int(value)
            for value in quest_ids
        }

        content = self.center_scroll.widget()

        if content is None:
            return

        for line in content.findChildren(QuestLine):
            step = getattr(
                line,
                "step",
                None,
            )

            if (
                step is None
                or step.step_type != "quest"
                or step.entity_id is None
                or int(step.entity_id) not in ids
            ):
                continue

            completed = bool(
                self.step_completed(
                    guide,
                    step,
                )
            )

            line.completed = completed

            state = (
                "done"
                if completed
                else "todo"
            )

            line.setProperty(
                "state",
                state,
            )

            title = line.findChild(
                QLabel,
                "GuideQuestLineTitle",
            )

            if title is not None:
                title.setProperty(
                    "state",
                    state,
                )

                title.setStyleSheet(
                    render_theme_template("color:#687482;")
                    if completed
                    else ""
                )

            marker = line.findChild(
                QToolButton,
                "GuideQuestState",
            )

            if marker is not None:
                marker.setText(
                    "\u2713"
                    if completed
                    else "\u25cb"
                )

                marker.setProperty(
                    "state",
                    state,
                )

                marker.style().unpolish(
                    marker
                )

                marker.style().polish(
                    marker
                )

                marker.update()

            if completed:
                line.setStyleSheet(
                    render_theme_template(
                        "background:#0c1118;"
                        "border:1px solid #202833;"
                        "border-radius:6px;"
                    )
                )
            else:
                line.setStyleSheet("")

            line.style().unpolish(line)
            line.style().polish(line)
            line.update()

    def _series_progress_title(
        self,
        guide: Guide,
        series: GuideSeries,
    ) -> str:
        heading = (
            _compact_guide_tree_title(
                guide,
                series.title,
            ).upper()
            if guide.category == "aventure"
            else _series_heading(series)
        )
        progress = self._progress_count_for_steps(
            guide,
            series.steps,
        )
        return f"{heading} — {progress.completed}/{progress.total}"

    def _update_visible_series_progress(self, guide: Guide) -> None:
        series_ref = self._selected_series_ref(guide)
        content = self.center_scroll.widget()
        if series_ref is None or content is None:
            return
        title = content.findChild(
            QLabel,
            "GuideSeriesHeaderTitle",
        )
        if title is not None:
            title.setText(
                self._series_progress_title(
                    guide,
                    series_ref[2],
                )
            )


    def set_quest_completed(
        self,
        quest_id: int,
        completed: bool,
    ) -> None:
        guide = self.current_guide()

        left_position = (
            self.left_scroll
            .verticalScrollBar()
            .value()
        )

        right_position = (
            self.right_scroll
            .verticalScrollBar()
            .value()
        )

        self.quest_progress_service.set_quest_completed(
            self.current_character_key,
            int(quest_id),
            bool(completed),
        )

        self.quest_progress = (
            self.quest_progress_service.reload()
        )
        self._sync_achievement_progress()

        if guide is None:
            return

        if self.state == self.GUIDE_OVERVIEW:
            self._update_visible_quest_progress(
                guide,
                (int(quest_id),),
            )

            self._update_visible_series_progress(guide)

            self._populate_guide_left(
                guide
            )

            self._render_header(guide)

            self._populate_guide_info(
                guide
            )

            def restore_side_scrolls() -> None:
                left_bar = (
                    self.left_scroll
                    .verticalScrollBar()
                )

                right_bar = (
                    self.right_scroll
                    .verticalScrollBar()
                )

                left_bar.setValue(
                    min(
                        left_position,
                        left_bar.maximum(),
                    )
                )

                right_bar.setValue(
                    min(
                        right_position,
                        right_bar.maximum(),
                    )
                )

            _single_shot(
                self,
                0,
                restore_side_scrolls,
            )

            _single_shot(
                self,
                50,
                restore_side_scrolls,
            )

            return

        if (
            self.state == self.QUEST_DETAIL
            and self.current_quest_id is not None
        ):
            self.show_quest_detail(
                self.current_quest_id,
                preserve_scroll=True,
            )

    def on_shared_quest_progress_changed(self, quest_id: int) -> None:
        self.quest_progress = self.quest_progress_service.reload()
        self._sync_achievement_progress()
        guide = self.current_guide()
        if guide is not None:
            self._update_visible_quest_progress(guide, (int(quest_id),))
            self._render_header(guide)
            if self.state == self.GUIDE_OVERVIEW:
                self._update_visible_series_progress(guide)
                self._populate_guide_left(guide)
                self._populate_guide_info(guide)





    def _refresh_guide_columns_after_progress(
        self,
        guide: Guide,
        center_pos: int,
        left_pos: int,
        right_pos: int,
    ) -> None:
        self._populate_guide_left(guide)
        self._populate_series_quests(guide)
        self._populate_guide_info(guide)

        def restore_scrolls() -> None:
            center_bar = (
                self.center_scroll
                .verticalScrollBar()
            )

            left_bar = (
                self.left_scroll
                .verticalScrollBar()
            )

            right_bar = (
                self.right_scroll
                .verticalScrollBar()
            )

            center_bar.setValue(
                min(
                    center_pos,
                    center_bar.maximum(),
                )
            )

            left_bar.setValue(
                min(
                    left_pos,
                    left_bar.maximum(),
                )
            )

            right_bar.setValue(
                min(
                    right_pos,
                    right_bar.maximum(),
                )
            )

        # First pass after widget replacement.
        _single_shot(
            self,
            0,
            restore_scrolls,
        )

        # Second pass after Qt recalculates
        # the final scroll ranges.
        _single_shot(
            self,
            50,
            restore_scrolls,
        )

    def _refresh_current_view(self, preserve_scroll: bool = False) -> None:
        self.refresh_home()
        if self.current_guide_id and self.current_quest_id is not None:
            self.show_quest_detail(self.current_quest_id, preserve_scroll=preserve_scroll)
        elif self.current_guide_id:
            self.show_guide_overview(self.current_guide_id, preserve_scroll=preserve_scroll)

    def _guide_progress_tuple_uncached(self, guide: Guide) -> tuple[int, int, str]:
        progress = self.progress_calculator.guide_progress(guide, self.current_character_key)
        return progress.completed, progress.total, self._state(progress.completed, progress.total)

    def guide_state(self, guide: Guide) -> str:
        return self.guide_progress_tuple(guide)[2]

    def select_series(self, series_id: str) -> None:
        guide = self.current_guide()
        if guide is None:
            return
        if self._series_ref_by_id(guide, str(series_id)) is None:
            return
        self.current_series_by_guide[guide.id] = str(series_id)
        self.show_guide_overview(guide.id, preserve_scroll=False)

    def _configure_detail_layout(self, guide: Guide, quest_detail: bool) -> None:
        if quest_detail:
            self.detail_stack.setCurrentWidget(self.quest_detail_view)
            return
        self.detail_stack.setCurrentWidget(self.splitter)
        self.center_panel.setVisible(True)
        self.right_panel.setVisible(True)
        show_steps = self._guide_uses_steps_column(guide) and not quest_detail
        self.left_panel.setVisible(show_steps)
        if not show_steps:
            self.splitter.setStretchFactor(0, 0)
            self.splitter.setStretchFactor(1, 70)
            self.splitter.setStretchFactor(2, 30)
            self.left_panel.setMinimumWidth(0)
            self.left_panel.setMaximumWidth(0)
            self.center_panel.setMinimumWidth(340)
            self.right_panel.setMinimumWidth(220)
            self.splitter.setSizes([0, 560, 230])
            return
        self.left_panel.setVisible(True)
        self.center_panel.setMinimumWidth(260)
        self.right_panel.setMinimumWidth(220)
        if self.steps_collapsed:
            self.left_panel.setMinimumWidth(GUIDE_STEPS_COLLAPSED_WIDTH)
            self.left_panel.setMaximumWidth(GUIDE_STEPS_COLLAPSED_WIDTH)
            self.splitter.setStretchFactor(0, 0)
            self.splitter.setStretchFactor(1, 62)
            self.splitter.setStretchFactor(2, 30)
            self.splitter.setSizes(
                [GUIDE_STEPS_COLLAPSED_WIDTH, 430, 230]
            )
            return
        self.left_panel.setMinimumWidth(GUIDE_STEPS_OPEN_WIDTH)
        self.left_panel.setMaximumWidth(GUIDE_STEPS_OPEN_WIDTH)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 50)
        self.splitter.setStretchFactor(2, 30)
        self.splitter.setSizes([GUIDE_STEPS_OPEN_WIDTH, 350, 230])

    @staticmethod
    def _guide_uses_steps_column(guide: Guide) -> bool:
        return guide.category != "dofus"

    def _render_header(self, guide: Guide, quest=None) -> None:
        title = quest.name if quest is not None else guide.title
        level = (
            ""
            if (
                quest is not None
                or guide.category == "aventure"
            )
            else _display_guide_level_text(guide)
        )
        self.detail_header_title.setText(title)
        self.detail_header_meta.setText(level)
        self.detail_header_meta.setVisible(bool(level))
        progress = self.progress_calculator.guide_progress(
            guide,
            self.current_character_key,
        )
        self.detail_header_progress.setText(
            f"{progress.completed}/{progress.total}"
        )
        self.detail_header_progress.setToolTip("Quêtes terminées / quêtes du guide")
        self.detail_header_progress.setVisible(quest is None)
        self.detail_header_done_button.setVisible(quest is not None)
        if quest is not None:
            done = self.quest_progress_service.is_quest_completed(self.current_character_key, int(quest.id)) or self.progress_calculator.quest_progress(quest, self.current_character_key).is_complete
            self.detail_header_done_button.setText("✓ Quête terminée" if done else "○ Marquer terminée")
            self.detail_header_done_button.setProperty("state", "done" if done else "todo")
            self.detail_header_done_button.style().unpolish(self.detail_header_done_button)
            self.detail_header_done_button.style().polish(self.detail_header_done_button)
        pixmap = None if quest is not None else _guide_pixmap(guide)
        if pixmap is not None and not pixmap.isNull():
            self.detail_header_image.setText("")
            self.detail_header_image.setPixmap(pixmap.scaled(38, 38, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.detail_header_image.setVisible(True)
        else:
            self.detail_header_image.clear()
            self.detail_header_image.setVisible(quest is None)
            if quest is None:
                self.detail_header_image.setPixmap(atlas_icon("item").pixmap(30, 30))

    def toggle_current_quest_completed(self) -> None:
        if self.current_quest_id is None:
            return
        completed = self.quest_progress_service.is_quest_completed(self.current_character_key, int(self.current_quest_id))
        self.set_quest_completed(int(self.current_quest_id), not completed)

    def _ensure_selected_series(self, guide: Guide) -> None:
        if self._selected_series_ref(guide) is not None:
            return
        first = self._first_series_for_guide(guide)
        if first is not None:
            self.current_series_by_guide[guide.id] = first.id

    def _selected_series_id(self, guide: Guide) -> str:
        self._ensure_selected_series(guide)
        return self.current_series_by_guide.get(guide.id, "")

    def _selected_series_ref(self, guide: Guide) -> tuple[GuidePart, GuideChapter, GuideSeries] | None:
        series_id = self.current_series_by_guide.get(guide.id, "")
        ref = self._series_ref_by_id(guide, series_id) if series_id else None
        if ref is not None:
            return ref
        first = self._first_series_for_guide(guide)
        if first is None:
            return None
        self.current_series_by_guide[guide.id] = first.id
        return self._series_ref_by_id(guide, first.id)

    def _series_ref_by_id(self, guide: Guide, series_id: str) -> tuple[GuidePart, GuideChapter, GuideSeries] | None:
        for part, chapter, series in self._series_refs(guide):
            if series.id == series_id:
                return part, chapter, series
        return None

    def _series_ref_for_quest(self, guide: Guide, quest_id: int) -> tuple[GuidePart, GuideChapter, GuideSeries] | None:
        for part, chapter, series in self._series_refs(guide):
            for step in series.steps:
                if step.step_type == "quest" and step.entity_id == int(quest_id):
                    return part, chapter, series
        return None

    def _series_refs(self, guide: Guide) -> list[tuple[GuidePart, GuideChapter, GuideSeries]]:
        refs: list[tuple[GuidePart, GuideChapter, GuideSeries]] = []
        for part in sorted(guide.parts, key=lambda item: (item.order, normalize_text(item.title))):
            for chapter in sorted(part.chapters, key=lambda item: (item.order, normalize_text(item.title))):
                for series in sorted(chapter.series, key=lambda item: (item.order, normalize_text(item.title))):
                    refs.append((part, chapter, series))
        return refs

    def _first_series_for_guide(self, guide: Guide) -> GuideSeries | None:
        refs = self._series_refs(guide)
        return refs[0][2] if refs else None

    def _first_series(self, part: GuidePart) -> GuideSeries | None:
        for chapter in sorted(part.chapters, key=lambda item: (item.order, normalize_text(item.title))):
            first = self._first_series_from_chapter(chapter)
            if first is not None:
                return first
        return None

    @staticmethod
    def _first_series_from_chapter(chapter: GuideChapter) -> GuideSeries | None:
        series = sorted(chapter.series, key=lambda item: (item.order, normalize_text(item.title)))
        return series[0] if series else None

    def _progress_for_steps(self, guide: Guide, steps: Iterable[GuideStep]) -> tuple[int, int]:
        progress = self.progress_calculator.quest_steps_progress(
            guide,
            steps,
            self.current_character_key,
        )
        return progress.completed, progress.total

    def _progress_count_for_steps(self, guide: Guide, steps: Iterable[GuideStep]) -> ProgressCount:
        return self.progress_calculator.quest_steps_progress(
            guide,
            steps,
            self.current_character_key,
        )

    def _series_id_in_part(self, part: GuidePart, series_id: str) -> bool:
        return any(series.id == series_id for chapter in part.chapters for series in chapter.series)

    def _series_id_in_chapter(self, chapter: GuideChapter, series_id: str) -> bool:
        return any(series.id == series_id for series in chapter.series)

    def _part_has_visible_children(self, part: GuidePart) -> bool:
        return any(
            self._chapter_title_useful(part, chapter)
            or any(self._series_title_useful(part, chapter, series) for series in chapter.series)
            for chapter in part.chapters
        )

    def _chapter_has_visible_series(self, part: GuidePart, chapter: GuideChapter) -> bool:
        return any(self._series_title_useful(part, chapter, series) for series in chapter.series)

    @staticmethod
    def _chapter_title_useful(part: GuidePart, chapter: GuideChapter) -> bool:
        title_key = normalize_text(chapter.title)
        if not title_key:
            return False
        if len(part.chapters) == 1 and title_key == normalize_text(part.title):
            return False
        return True

    def _render_breadcrumb(self, guide: Guide, quest_name: str = "") -> None:
        clear_layout(self.breadcrumb_layout)
        guide_home = AtlasButton("Guides")
        guide_home.setObjectName("GuideBreadcrumbButton")
        guide_home.clicked.connect(self.show_home)
        self.breadcrumb_layout.addWidget(guide_home)
        self._add_breadcrumb_separator()

        if quest_name:
            guide_button = AtlasButton(guide.title)
            guide_button.setObjectName("GuideBreadcrumbButton")
            guide_button.clicked.connect(lambda _checked=False, gid=guide.id: self.show_guide_overview(gid, preserve_scroll=True))
            self.breadcrumb_layout.addWidget(guide_button)
            self._add_breadcrumb_separator()
            current = QLabel(quest_name)
            current.setObjectName("GuideBreadcrumbCurrent")
            current.setWordWrap(False)
            self.breadcrumb_layout.addWidget(current, 1)
        else:
            current = QLabel(guide.title)
            current.setObjectName("GuideBreadcrumbCurrentStrong")
            current.setWordWrap(False)
            self.breadcrumb_layout.addWidget(current, 1)

    def _add_breadcrumb_separator(self) -> None:
        separator = QLabel(">")
        separator.setObjectName("GuideBreadcrumbSeparator")
        self.breadcrumb_layout.addWidget(separator)


    def _quest_ids_for_steps(
        self,
        steps: Iterable[GuideStep],
    ) -> tuple[int, ...]:
        return tuple(
            dict.fromkeys(
                int(step.entity_id)
                for step in steps
                if (
                    step.step_type == "quest"
                    and step.entity_id is not None
                )
            )
        )

    def _populate_guide_left(self, guide: Guide) -> None:
        clear_layout(self.left_layout)

        if self.steps_collapsed:
            self._populate_steps_collapsed()
            return

        self.left_layout.addWidget(
            self._steps_header()
        )

        selected_series_id = (
            self._selected_series_id(guide)
        )

        for part in sorted(
            guide.parts,
            key=lambda item: (
                item.order,
                normalize_text(item.title),
            ),
        ):
            first_series = self._first_series(part)

            progress = (
                self._progress_count_for_steps(
                    guide,
                    part.steps,
                )
            )

            row = GuideStructureRow(
                _compact_guide_tree_title(
                    guide,
                    part.title,
                ),
                (
                    first_series.id
                    if first_series is not None
                    else ""
                ),
                0,
                progress,
                (
                    self._series_id_in_part(
                        part,
                        selected_series_id,
                    )
                    and not self._part_has_visible_children(
                        part
                    )
                ),
                quest_ids=self._quest_ids_for_steps(
                    part.steps
                ),
            )

            row.setToolTip(part.title)
            row.selected.connect(
                self.select_series
            )
            row.completionToggled.connect(
                self.set_quest_group_completed
            )
            self.left_layout.addWidget(row)

            for chapter in sorted(
                part.chapters,
                key=lambda item: (
                    item.order,
                    normalize_text(item.title),
                ),
            ):
                show_chapter = (
                    self._chapter_title_useful(
                        part,
                        chapter,
                    )
                )

                first_chapter_series = (
                    self._first_series_from_chapter(
                        chapter
                    )
                )

                if show_chapter:
                    progress = (
                        self._progress_count_for_steps(
                            guide,
                            chapter.steps,
                        )
                    )

                    row = GuideStructureRow(
                        _compact_guide_tree_title(
                            guide,
                            chapter.title,
                        ),
                        (
                            first_chapter_series.id
                            if first_chapter_series is not None
                            else ""
                        ),
                        1,
                        progress,
                        (
                            self._series_id_in_chapter(
                                chapter,
                                selected_series_id,
                            )
                            and not self._chapter_has_visible_series(
                                part,
                                chapter,
                            )
                        ),
                        quest_ids=self._quest_ids_for_steps(
                            chapter.steps
                        ),
                    )

                    row.setToolTip(chapter.title)
                    row.selected.connect(
                        self.select_series
                    )
                    row.completionToggled.connect(
                        self.set_quest_group_completed
                    )
                    self.left_layout.addWidget(row)

                for series in sorted(
                    chapter.series,
                    key=lambda item: (
                        item.order,
                        normalize_text(item.title),
                    ),
                ):
                    if not self._series_title_useful(
                        part,
                        chapter,
                        series,
                    ):
                        continue

                    progress = (
                        self._progress_count_for_steps(
                            guide,
                            series.steps,
                        )
                    )

                    row = GuideStructureRow(
                        _compact_guide_tree_title(
                            guide,
                            series.title,
                        ),
                        series.id,
                        2 if show_chapter else 1,
                        progress,
                        (
                            series.id
                            == selected_series_id
                        ),
                        quest_ids=self._quest_ids_for_steps(
                            series.steps
                        ),
                    )

                    row.setToolTip(series.title)
                    row.selected.connect(
                        self.select_series
                    )
                    row.completionToggled.connect(
                        self.set_quest_group_completed
                    )
                    self.left_layout.addWidget(row)

        if not guide.parts:
            self.left_layout.addWidget(
                text_label(
                    "Aucune structure locale disponible.",
                    "MutedLabel",
                )
            )

        self.left_layout.addStretch(1)

    def _steps_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("GuideStepsHeader")

        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(6)

        layout.addWidget(
            section_title("\u00c9TAPES"),
            1,
        )

        button = QToolButton()
        button.setObjectName("GuideStepsCollapseButton")
        button.setText("\u2039")
        button.setFixedSize(24, 24)
        button.setFocusPolicy(Qt.NoFocus)
        button.setToolTip("R\u00e9duire la colonne")
        button.clicked.connect(
            lambda: self.set_steps_collapsed(True)
        )

        layout.addWidget(button)
        return header

    def _populate_steps_collapsed(self) -> None:
        rail = GuideCollapsedStepsRail()
        rail.expandedRequested.connect(lambda: self.set_steps_collapsed(False))
        self.left_layout.addWidget(rail, 1)

    def set_steps_collapsed(self, collapsed: bool) -> None:
        if self.steps_collapsed == bool(collapsed):
            return
        self.steps_collapsed = bool(collapsed)
        guide = self.current_guide()
        if guide is not None and self.state == self.GUIDE_OVERVIEW:
            self._configure_detail_layout(guide, False)
            if self._guide_uses_steps_column(guide):
                self._populate_guide_left(guide)
            else:
                clear_layout(self.left_layout)


    def _populate_series_quests(self, guide: Guide) -> None:
        clear_layout(self.center_layout)

        series_ref = self._selected_series_ref(
            guide
        )

        if series_ref is None:
            self.center_layout.addWidget(
                text_label(
                    "Aucune serie locale disponible.",
                    "MutedLabel",
                )
            )
            self.center_layout.addStretch(1)
            return

        _part, _chapter, series = series_ref

        header = QFrame()
        header.setObjectName("GuideSeriesHeader")

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(
            10,
            7,
            10,
            7,
        )
        header_layout.setSpacing(8)

        title = QLabel()
        title.setObjectName(
            "GuideSeriesHeaderTitle"
        )
        title.setWordWrap(False)
        title.setText(self._series_progress_title(guide, series))
        header_layout.addWidget(title, 1)
        self.center_layout.addWidget(header)

        for step in sorted(
            series.steps,
            key=lambda item: item.order,
        ):
            quest = (
                self.quest_catalog.by_id.get(
                    int(step.entity_id)
                )
                if (
                    step.step_type == "quest"
                    and step.entity_id is not None
                )
                else None
            )

            line = QuestLine(
                step,
                completed=self.step_completed(
                    guide,
                    step,
                ),
                level_text=(
                    ""
                    if guide.category == "aventure"
                    else _short_quest_level(quest)
                ),
            )

            line.selected.connect(
                self.open_quest_from_guide
            )

            line.completionToggled.connect(
                self.set_quest_completed
            )

            self.center_layout.addWidget(line)

        self.center_layout.addStretch(1)

    def _populate_guide_navigation(
        self,
        guide: Guide,
        target_layout: QVBoxLayout,
        active_quest_id: int | None,
        compact: bool,
    ) -> None:
        clear_layout(target_layout)
        if compact:
            target_layout.addWidget(section_title("Navigation du guide"))
        for part in sorted(guide.parts, key=lambda item: (item.order, normalize_text(item.title))):
            self._add_part_navigation(target_layout, guide, part, active_quest_id, compact)
        if not guide.parts:
            target_layout.addWidget(text_label("Aucune quête structurée locale.", "MutedLabel"))
        target_layout.addStretch(1)

    def _add_part_navigation(
        self,
        target_layout: QVBoxLayout,
        guide: Guide,
        part: GuidePart,
        active_quest_id: int | None,
        compact: bool,
    ) -> None:
        title = QLabel(part.title)
        title.setObjectName("GuidePartTitleCompact" if compact else "GuidePartTitle")
        title.setWordWrap(True)
        target_layout.addWidget(title)
        for chapter in sorted(part.chapters, key=lambda item: (item.order, normalize_text(item.title))):
            self._add_chapter_navigation(target_layout, guide, part, chapter, active_quest_id, compact)

    def _add_chapter_navigation(
        self,
        target_layout: QVBoxLayout,
        guide: Guide,
        part: GuidePart,
        chapter: GuideChapter,
        active_quest_id: int | None,
        compact: bool,
    ) -> None:
        expanded = chapter.id in self.expanded_chapters.get(guide.id, set())
        header = QFrame()
        header.setObjectName("GuideChapterHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(5, 3, 5, 3)
        header_layout.setSpacing(5)

        chevron = QToolButton()
        chevron.setObjectName("GuideChevronButton")
        chevron.setFixedSize(20, 20)
        chevron.setText("▾" if expanded else "›")
        chevron.setFocusPolicy(Qt.NoFocus)
        chevron.clicked.connect(lambda _checked=False, cid=chapter.id: self.toggle_chapter(cid))
        header_layout.addWidget(chevron)

        title = QLabel(chapter.title)
        title.setObjectName("GuideChapterTitle")
        title.setWordWrap(True)
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        header_layout.addWidget(title, 1)
        target_layout.addWidget(header)

        if not expanded:
            return

        for series in sorted(chapter.series, key=lambda item: (item.order, normalize_text(item.title))):
            if self._series_title_useful(part, chapter, series):
                label = QLabel(series.title)
                label.setObjectName("GuideSeriesTitle")
                label.setWordWrap(True)
                target_layout.addWidget(label)
            for step in sorted(series.steps, key=lambda item: item.order):
                active = active_quest_id is not None and step.step_type == "quest" and step.entity_id == active_quest_id
                line = QuestLine(
                    step,
                    active=active,
                    compact=compact,
                    activity_keys=activity_labels(series.activities),
                )
                line.selected.connect(self.open_quest_from_guide)
                line.completionToggled.connect(self.set_quest_completed)
                target_layout.addWidget(line)

    def _selected_series_rewards(
        self,
        guide: Guide,
    ) -> list[DisplayReward]:
        series_ref = self._selected_series_ref(guide)

        if series_ref is None:
            return []

        _part, _chapter, series = series_ref

        rewards: list[DisplayReward] = []
        seen: set[tuple[str, str]] = set()

        for step in sorted(
            series.steps,
            key=lambda item: item.order,
        ):
            if (
                step.step_type != "quest"
                or step.entity_id is None
            ):
                continue

            quest = self.quest_catalog.by_id.get(
                int(step.entity_id)
            )

            if quest is None:
                continue

            achievements = tuple(
                self.achievement_provider.get_by_quest(
                    int(quest.id)
                )
            )

            for reward in quest_rewards(
                quest,
                achievements,
            ):
                key = (
                    reward_label(reward),
                    str(
                        getattr(
                            reward,
                            "image_path",
                            "",
                        )
                        or ""
                    ),
                )

                if key in seen:
                    continue

                seen.add(key)
                rewards.append(reward)

        return rewards

    def _populate_guide_info(self, guide: Guide) -> None:
        clear_layout(self.right_layout)
        self.right_layout.addWidget(hidden_label("Informations du guide"))

        completed, total, _state = self.guide_progress_tuple(guide)
        self.right_layout.addWidget(info_section("PROGRESSION", [progress_summary(completed, total)]))

        prereqs = self._guide_prerequisite_widgets(guide)
        if prereqs:
            expanded = self.guide_prerequisites_expanded.get(guide.id, False)
            section = CollapsibleInfoSection(
                "PRÉREQUIS",
                str(len(prereqs)),
                "neutral",
                expanded,
                prereqs,
            )
            section.toggled.connect(
                lambda value, guide_id=guide.id: self.guide_prerequisites_expanded.__setitem__(guide_id, value)
            )
            self.right_layout.addWidget(section)

        items = guide_items(guide)
        if items:
            self.right_layout.addWidget(info_section("OBJETS NÉCESSAIRES", [item_row(item) for item in items]))

        activities = guide_activities(guide)
        if activities:
            self.right_layout.addWidget(info_section("INFO QUÊTE", [activity_chip_grid(activities)]))

        if guide.category == "aventure":
            rewards = self._selected_series_rewards(guide)
        else:
            rewards = guide_rewards(
                guide,
                self.achievement_provider,
                (
                    self.quest_catalog.by_id[quest_id]
                    for quest_id in self._quest_ids_for_steps(guide.required_steps)
                    if quest_id in self.quest_catalog.by_id
                ),
            )

        if rewards:
            self.right_layout.addWidget(
                info_section(
                    "R\u00c9COMPENSES",
                    [
                        reward_row(reward)
                        for reward in rewards
                    ],
                )
            )

        self.right_layout.addStretch(1)

    def _guide_prerequisite_widgets(self, guide: Guide) -> list[QWidget]:
        rows: list[tuple[str, int | None]] = []
        seen: set[str] = set()
        guide_keys = {
            (step.step_type, int(step.entity_id))
            for step in guide.steps
            if step.entity_id is not None
        }

        def add(text: str, quest_id: int | None = None) -> None:
            clean = clean_requirement_line(text)
            key = normalize_text(clean)
            if clean and key not in seen:
                seen.add(key)
                rows.append((clean, quest_id))

        for step in guide.steps:
            for ref in step.prerequisites:
                if (ref.entity_type, ref.entity_id) in guide_keys:
                    continue
                add(ref.label, int(ref.entity_id) if ref.entity_type == "quest" else None)

        first_quest = next(
            (
                step
                for step in guide.steps
                if step.step_type == "quest" and step.entity_id is not None and step.counts_for_completion
            ),
            None,
        )
        if first_quest is not None:
            quest = self.quest_catalog.by_id.get(int(first_quest.entity_id))
            if quest is not None:
                for line in quest.prerequisites:
                    add(line, self._quest_id_from_requirement_line(line))
            for quest_id in self.graph.previous_ids(int(first_quest.entity_id)):
                if quest_id in guide.quest_ids:
                    continue
                record = self.quest_catalog.by_id.get(int(quest_id))
                if record is not None:
                    add(record.name, int(quest_id))

        return [self._guide_prerequisite_row(text, quest_id) for text, quest_id in rows[:8]]

    def _quest_id_from_requirement_line(self, line: str) -> int | None:
        clean = clean_text(line)
        key = normalize_text(clean)
        prefixes = ("quete_terminee_", "quete_active_")
        prefix = next((value for value in prefixes if key.startswith(value)), "")
        if not prefix:
            return None
        target = key[len(prefix) :]
        for quest in self.quest_catalog.quests:
            if normalize_text(quest.name) == target:
                return int(quest.id)
        return None

    def _guide_prerequisite_row(self, text: str, quest_id: int | None) -> QWidget:
        if quest_id is None:
            return prerequisite_row(text, None)
        row = QFrame()
        row.setObjectName("GuidePrerequisiteRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        marker = QLabel("")
        marker.setObjectName("GuideTreeState")
        marker.setProperty("state", "neutral")
        marker.setFixedWidth(18)
        marker.setAlignment(Qt.AlignCenter)
        layout.addWidget(marker, 0, Qt.AlignTop)
        button = AtlasButton(clean_text(text))
        button.setObjectName("GuideInlineQuestButton")
        button.setToolTip("Ouvrir cette quête")
        button.clicked.connect(lambda _checked=False, qid=int(quest_id): self.open_prerequisite_from_guide(qid))
        layout.addWidget(button, 1)
        return row

    def toggle_chapter(self, chapter_id: str) -> None:
        guide = self.current_guide()
        if guide is None:
            return
        opened = self.expanded_chapters.setdefault(guide.id, set())
        if chapter_id in opened:
            opened.remove(chapter_id)
        else:
            opened.add(chapter_id)
        if self.state == self.QUEST_DETAIL and self.current_quest_id is not None:
            self.show_quest_detail(self.current_quest_id, preserve_scroll=True)
        else:
            self.show_guide_overview(guide.id, preserve_scroll=True)

    def step_for_quest(self, guide: Guide, quest_id: int) -> GuideStep | None:
        for step in guide.steps:
            if step.step_type == "quest" and step.entity_id == int(quest_id):
                return step
        return None

    def _first_guide_position(self, guide: Guide) -> str:
        for quest_id in guide.quest_ids:
            quest = self.quest_catalog.by_id.get(int(quest_id))
            if quest is None:
                continue
            position = first_position_from_quest(quest)
            if position:
                return position
        return ""

    def _ensure_chapters_initialized(self, guide: Guide) -> None:
        if guide.id in self.expanded_chapters:
            return
        self.expanded_chapters[guide.id] = {
            chapter.id
            for part in guide.parts
            for chapter in part.chapters
        }

    @staticmethod
    def _series_title_useful(part: GuidePart, chapter: GuideChapter, series: GuideSeries) -> bool:
        title_key = normalize_text(series.title)
        if not title_key:
            return False
        hidden_keys = {normalize_text(part.title), normalize_text(chapter.title), "quetes", "quêtes"}
        if len(chapter.series) == 1 and title_key in hidden_keys:
            return False
        if len(series.steps) == 1 and normalize_text(series.steps[0].display_title) == title_key:
            return False
        return True


    def apply_local_style(self) -> None:
        self.setStyleSheet(
            render_theme_template(
                """
            QWidget#GuidesHomePage,
            QWidget#GuidesHomeContent,
            QWidget#GuidesDetailPage,
            QWidget#GuideLeftPanelContent,
            QWidget#GuideCenterPanelContent,
            QWidget#GuideRightPanelContent,
            QFrame#GuidesHomeSubCategory {
                background: #080b12;
            }

            QFrame#GuideHeader,
            QFrame#GuideBreadcrumb,
            QFrame#GuidesHomeCategory,
            QFrame#GuidesHomeProgressionColumn,
            QFrame#GuideLeftPanel,
            QFrame#GuideCenterPanel,
            QFrame#GuideRightPanel {
                background: #10141d;
                border: 1px solid #262d3a;
                border-radius: 7px;
            }

            QFrame#GuidesHomeSubCategory {
                border: none;
            }

            QFrame#GuidesHomeSeparator {
                background: #262d3a;
                border: none;
            }

            QFrame#GuideAdventureCard,
            QFrame#GuideAlignmentCard,
            QFrame#GuideDofusCard,
            QFrame#GuideQuestLine,
            QFrame#GuideQuestLineActive,
            QFrame#GuideQuestLineUnavailable,
            QFrame#GuideTreeRow,
            QFrame#GuideTreeRowActive,
            QFrame#GuideSeriesSummaryRow {
                background: #141821;
                border: 1px solid #242b37;
                border-radius: 6px;
            }

            QFrame#GuideAdventureCard:hover,
            QFrame#GuideAlignmentCard:hover,
            QFrame#GuideDofusCard:hover,
            QFrame#GuideQuestLine:hover,
            QFrame#GuideTreeRow:hover,
            QFrame#GuideSeriesSummaryRow:hover {
                background: #1a202b;
                border-color: #5e3d93;
            }

            QFrame#GuideDofusCard[state="done"] {
                border-color: #2e7445;
            }

            QFrame#GuideQuestLineActive,
            QFrame#GuideTreeRowActive {
                background: #24183d;
                border-color: #6f4bb6;
            }

            QFrame#GuideQuestLineUnavailable {
                background: #10141d;
                border-color: #202733;
            }

            QFrame#GuideQuestLine[state="done"],
            QFrame#GuideQuestLineActive[state="done"],
            QFrame#GuideTreeRow[state="done"],
            QFrame#GuideTreeRowActive[state="done"] {
                background: #0d1118;
                border-color: #202733;
            }

            QLabel#GuideQuestLineTitle[state="done"],
            QLabel#GuideTreePartText[state="done"],
            QLabel#GuideTreeChildText[state="done"] {
                color: #68717e;
            }

            QToolButton#GuideTreeStateButton {
                background: transparent;
                border: 1px solid #303847;
                border-radius: 5px;
                color: #8c95a3;
                font-size: 12px;
                font-weight: 800;
                padding: 0px;
            }

            QToolButton#GuideTreeStateButton:hover {
                background: #1a202b;
                border-color: #6f4bb6;
                color: #f1f4fb;
            }

            QToolButton#GuideTreeStateButton[state="done"] {
                color: #68717e;
                border-color: #343b46;
            }

            QLabel#GuidesHomeCategoryTitle,
            QLabel#GuideHeaderTitle,
            QLabel#GuideSeriesHeaderTitle {
                color: #f5f0ff;
                font-weight: 800;
            }

            QLabel#GuidesHomeCategoryTitle {
                color: #e7bf63;
                font-size: 12px;
                letter-spacing: 0px;
            }

            QLabel#GuideHeaderTitle {
                font-size: 19px;
            }

            QLabel#GuideHeaderMeta {
                color: #c9d0dc;
                font-size: 12px;
            }

            QLabel#GuideHeaderProgress {
                color: #e7bf63;
                font-size: 15px;
                font-weight: 800;
                padding: 4px 8px;
                border: 1px solid #5d512d;
                border-radius: 6px;
                background: #1c1a12;
            }

            QLabel#GuideInfoSectionTitle {
                color: #e8edf7;
                font-size: 11px;
                font-weight: 800;
            }

            QLabel#GuideHomeCardTitle,
            QLabel#GuideDofusCardTitle,
            QLabel#GuideTreePartText,
            QLabel#GuideSeriesHeaderTitle,
            QLabel#QuestSolutionStepTitle {
                color: #f1f4fb;
                font-size: 13px;
                font-weight: 750;
            }

            QLabel#GuideDofusCardTitle {
                font-size: 12px;
            }

            QLabel#GuideTreeChildText,
            QLabel#GuideQuestLineTitle,
            QLabel#GuideInfoLine,
            QLabel#QuestSolutionDescription,
            QLabel#GuideActivityText {
                color: #d9dfeb;
                font-size: 12px;
            }

            QLabel#GuideHomeCardMeta,
            QLabel#GuideHomeProgress,
            QLabel#GuideQuestLevel,
            QLabel#GuideDofusProgress,
            QLabel#GuideSeriesHeaderProgress,
            QLabel#GuideSeriesSummaryTitle,
            QLabel#GuideSeriesSummaryProgress,
            QLabel#GuideProgressText,
            QLabel#GuideItemQuantity,
            QLabel#GuideTreeProgress,
            QLabel#GuideInfoKey,
            QLabel#GuideInfoValue,
            QLabel#GuideBreadcrumbSeparator,
            QLabel#GuideBreadcrumbCurrent,
            QLabel#MutedLabel,
            QLabel#GuidesHomeEmptyText {
                color: #9ca5b4;
                font-size: 11px;
            }

            QLabel#GuideBreadcrumbCurrentStrong {
                color: #dfe6f3;
                font-size: 11px;
                font-weight: 700;
            }

            QLabel#GuideQuestNumber {
                color: #a78bda;
                font-size: 12px;
                font-weight: 800;
            }

            QLabel#GuideTreeState {
                color: #727b88;
                font-size: 13px;
                font-weight: 800;
            }

            QLabel#GuideTreeState[state="done"],
            QLabel#GuideTreeProgress[state="done"],
            QLabel#GuideHomeProgress[state="done"],
            QLabel#GuideDofusProgress[state="done"],
            QLabel#GuideSeriesHeaderProgress[state="done"] {
                color: #58c878;
            }

            QLabel#GuideTreeState[state="partial"],
            QLabel#GuideTreeProgress[state="partial"],
            QLabel#GuideHomeProgress[state="partial"],
            QLabel#GuideDofusProgress[state="partial"],
            QLabel#GuideSeriesHeaderProgress[state="partial"] {
                color: #e0b75a;
            }

            QLabel#GuideHeaderImage,
            QLabel#GuideAdventureImage,
            QLabel#GuideAlignmentImage,
            QLabel#GuideDofusImage {
                background: #0b0f17;
                border: 1px solid #2b3341;
                border-radius: 6px;
                color: #e7bf63;
            }

            QFrame#GuideSeriesHeader {
                background: transparent;
                border: none;
            }

            QFrame#GuideInfoRow,
            QFrame#GuideIconRow,
            QFrame#GuideItemRow,
            QFrame#GuideRewardRow,
            QFrame#GuideQuestItemRow,
            QFrame#GuideStepsHeader,
            QFrame#GuidePrerequisiteRow,
            QFrame#GuideProgressSummary,
            QFrame#GuideActivityGrid,
            QWidget#GuideCollapsibleBody {
                background: transparent;
                border: none;
            }

            QFrame#GuideQuestItemRow[state="done"],
            QFrame#GuideItemRow[state="done"],
            QFrame#QuestItemRow[state="done"] {
                background: rgba(52, 142, 78, 0.20);
                border: 1px solid #2e7445;
                border-radius: 5px;
            }

            QFrame#GuideInfoSection,
            QFrame#QuestSolutionStep {
                background: transparent;
                border-top: 1px solid #252c38;
                border-left: none;
                border-right: none;
                border-bottom: none;
                border-radius: 0px;
            }

            QFrame#GuideActivityChip {
                background: #121720;
                border: 1px solid #28303d;
                border-radius: 5px;
            }

            QFrame#GuideStepsCollapsedRail {
                background: #10141d;
                border: none;
                border-radius: 5px;
            }

            QFrame#QuestObjectiveLine:hover,
            QFrame#GuideCollapsibleHeader:hover {
                background: #171d27;
            }

            QToolButton#GuideChevronButton,
            QToolButton#GuideLineIcon,
            QToolButton#GuideLineActivity,
            QToolButton#GuideInfoIcon,
            QToolButton#GuideItemIcon,
            QLabel#GuideInfoIcon,
            QLabel#GuideItemIcon {
                background: transparent;
                border: none;
                padding: 0px;
            }

            QToolButton#GuideItemIcon[state="todo"] {
                border: 1px solid #303847;
                border-radius: 5px;
            }

            QToolButton#GuideItemIcon[state="done"] {
                background: rgba(52, 142, 78, 0.28);
                border: 1px solid #58c878;
                border-radius: 5px;
            }

            QToolButton#GuideQuestState,
            QToolButton#GuideStepsCollapseButton,
            QToolButton#GuideHeaderDoneButton,
            QToolButton#QuestGlobalDoneButton {
                background: transparent;
                border: 1px solid #303847;
                border-radius: 5px;
                color: #8c95a3;
                font-size: 12px;
                font-weight: 800;
                padding: 0px 6px;
            }

            QToolButton#GuideQuestState:hover,
            QToolButton#GuideStepsCollapseButton:hover,
            QToolButton#GuideHeaderDoneButton:hover,
            QToolButton#QuestGlobalDoneButton:hover {
                background: #1a202b;
                border-color: #6f4bb6;
                color: #f1f4fb;
            }

            QToolButton#GuideQuestState[state="done"],
            QToolButton#GuideHeaderDoneButton[state="done"],
            QToolButton#QuestGlobalDoneButton[state="done"] {
                color: #58c878;
                border-color: #2e7445;
            }

            QToolButton#GuideHeaderDoneButton,
            QToolButton#QuestGlobalDoneButton {
                min-height: 26px;
                max-height: 26px;
            }

            QPushButton#GuideBreadcrumbButton,
            QPushButton#GuideInlineQuestButton,
            QPushButton#GuideItemNameButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                color: #aeb7c6;
                font-size: 11px;
                font-weight: 700;
                min-height: 22px;
                max-height: 22px;
                padding: 0px 8px;
                text-align: left;
            }

            QPushButton#GuideBreadcrumbButton:hover,
            QPushButton#GuideInlineQuestButton:hover,
            QPushButton#GuideItemNameButton:hover {
                background: #1a202b;
                border-color: #5e3d93;
                color: #f1f4fb;
            }

            QPushButton#GuideItemNameButton {
                padding-left: 2px;
                padding-right: 2px;
            }

            QLabel#GuideItemQuantity {
                color: #aeb7c6;
                font-size: 11px;
                font-weight: 700;
            }

            QCheckBox#GuideInventoryCheck {
                color: #9ca5b4;
                font-size: 10px;
                padding-left: 2px;
            }

            QScrollArea#GuideDofusGridScroll,
            QScrollArea#GuideLeftPanelScroll,
            QScrollArea#GuideCenterPanelScroll,
            QScrollArea#GuideRightPanelScroll {
                background: transparent;
                border: none;
            }

            QWidget#GuideDofusGridContent {
                background: transparent;
            }

            QSplitter#GuideDetailSplitter::handle {
                background: #242b37;
            }

            QProgressBar#GuideTinyProgress {
                background: #0b0f17;
                border: 1px solid #29313f;
                border-radius: 3px;
            }

            QProgressBar#GuideTinyProgress::chunk {
                background: #58c878;
                border-radius: 2px;
            }

            QProgressBar#GuideDofusHomeBar {
                background: #0b0f17;
                border: 1px solid #27303d;
                border-radius: 2px;
            }

            QProgressBar#GuideDofusHomeBar::chunk {
                background: #7f5bc5;
                border-radius: 2px;
            }

            QProgressBar#GuideDofusHomeBar[state="done"]::chunk {
                background: #58c878;
            }

            QFrame#GuidesHomeEmpty {
                background: #10141d;
                border: 1px dashed #2b3341;
                border-radius: 7px;
            }

            QLabel#GuideStepsVerticalText {
                color: #9ca5b4;
                font-size: 10px;
                font-weight: 800;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 7px;
                margin: 2px 0px 2px 0px;
            }

            QScrollBar::handle:vertical {
                background: #2b3341;
                border-radius: 3px;
                min-height: 28px;
            }

            QScrollBar::handle:vertical:hover {
                background: #465166;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
                height: 0px;
            }

            QScrollBar:horizontal {
                background: transparent;
                height: 0px;
                margin: 0px;
            }

            QScrollBar::handle:horizontal,
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: transparent;
                border: none;
                width: 0px;
            }
                """
            )
        )

    @staticmethod
    def _state(completed: int, total: int) -> str:
        return guide_progress_state(completed, total)

    @staticmethod
    def _progress_file_stamp(path: Path) -> tuple[int, int, int]:
        try:
            stat = Path(path).stat()
        except OSError:
            return (0, 0, 0)
        return (int(stat.st_mtime_ns), int(stat.st_ctime_ns), int(stat.st_size))

    def _current_external_progress_signature(self) -> tuple[object, ...]:
        return (
            self.current_character_key,
            self._progress_file_stamp(Path(self.quest_progress_service.path)),
            self._progress_file_stamp(Path(self.achievement_progress_service.path)),
            self._progress_file_stamp(Path(self.guide_progress_service.path)),
        )

    def _current_home_render_signature(self) -> tuple[object, ...]:
        guide_signature = tuple(
            (
                str(getattr(guide, "id", "")),
                str(getattr(guide, "title", "")),
                str(getattr(guide, "category", "")),
                int(getattr(guide, "order", 0) or 0),
            )
            for guide in getattr(self, "guides", ())
        )
        return (
            str(getattr(self, "search_text", "") or ""),
            self._current_external_progress_signature(),
            guide_signature,
        )

    def _external_progress_changed(self) -> bool:
        signature = self._current_external_progress_signature()
        return signature != self._external_progress_signature

    def _mark_external_progress_refreshed(self) -> None:
        self._external_progress_signature = self._current_external_progress_signature()

    def _ensure_home_progress_cache(self) -> None:
        signature = self._current_external_progress_signature()
        if signature == self._home_progress_cache_signature:
            return
        self._home_progress_cache_signature = signature
        self._home_progress_cache.clear()

    def initial_home_progress(self) -> dict[str, tuple[int, int, str]] | None:
        progress = self._initial_home_progress_uncached()
        if progress is None:
            return None
        self._home_progress_cache_signature = self._current_external_progress_signature()
        self._home_progress_cache.update(progress)
        return progress

    def guide_progress_tuple(self, guide) -> tuple[int, int, str]:
        self._ensure_home_progress_cache()
        guide_id = str(getattr(guide, "id", ""))
        cached = self._home_progress_cache.get(guide_id)
        if cached is not None:
            return cached
        progress = self._guide_progress_tuple_uncached(guide)
        self._home_progress_cache[guide_id] = progress
        return progress

    def ensure_guide_ultime_view(self) -> GuideUltimeManualView | None:
        if self.guide_ultime_view is not None:
            return self.guide_ultime_view

        service = self.guide_ultime_service
        if service is None:
            service = GuideUltimeManualRuntimeService(
                self.quest_progress_service,
                self.achievement_progress_service,
                self.guide_progress_service,
                quest_provider=self.quest_provider,
                autoload=False,
            )
            # The canonical manual route is authoritative. Generated V5 artifacts
            # are loaded only if manual composition actually failed, avoiding two
            # complete route reads on every successful first opening.
            if not service.available:
                service.load()
            # Reuse the exact provider already owned by Guides/Succès. Creating
            # another provider here adds work and risks two catalogue snapshots.
            service.achievement_provider = self.achievement_provider
            service.auto_validation_contract = build_route_auto_validation_contract(
                service.cards,
                achievement_provider=self.achievement_provider,
            )
            self.guide_ultime_service = service

        if not service.available:
            return None

        view = GuideUltimeManualView(
            service,
            character_key=self.current_character_key,
            quest_provider=self.quest_provider,
            quest_graph=getattr(self, "graph", None),
        )
        # Expose the already-existing Encyclopedia navigator to the GPS view. The
        # view never knows how tabs are built; it only asks Atlas to open an entity.
        view.navigate_entity = self.link_service.navigate_to_entity
        view.questProgressChanged.connect(self._on_guide_ultime_quest_progress_changed)
        self.stack.addWidget(view)
        self.guide_ultime_view = view
        # The home catalogue is hidden while Guide Ultime opens. Only its manual
        # route counter needs patching; rebuilding every card/image is wasted work.
        self._refresh_guide_ultime_home_labels()
        return view

    def _refresh_guide_ultime_home_labels(self) -> None:
        if not hasattr(self, "home_content"):
            return
        for label in self.home_content.findChildren(QLabel):
            text = label.text().strip().casefold()
            if "aventure de zéro" in text or "aventure de zero" in text:
                label.setText(GUIDE_ULTIME_TITLE)
        service = self.guide_ultime_service
        if service is None or not service.available:
            return
        completed, total = service.route_sheet_progress(self.current_character_key)
        for label in self.home_content.findChildren(QLabel, "GuideHomeProgress"):
            parent = label.parentWidget()
            title = parent.findChild(QLabel, "GuideHomeCardTitle") if parent is not None else None
            if title is not None and title.text().strip() == GUIDE_ULTIME_TITLE:
                label.setText(f"{completed} / {total} fiches")

    def refresh_home(self) -> None:
        signature = self._current_home_render_signature()
        if signature == self._home_render_signature:
            self._refresh_guide_ultime_home_labels()
            return
        self._refresh_home_uncached()
        self._home_render_signature = self._current_home_render_signature()
        self._refresh_guide_ultime_home_labels()

    def select_guide(self, guide_id: str) -> bool:
        if str(guide_id) == GUIDE_ULTIME_LEGACY_ID:
            # guide_complet is only the legacy catalogue/navigation alias. The
            # manual service is authoritative and is built only when requested.
            view = self.ensure_guide_ultime_view()
            service = self.guide_ultime_service
            if view is None or service is None or not service.available:
                self.status_callback("Guide Ultime indisponible : route manuelle et fallback introuvables.")
                return False
            self.current_guide_id = GUIDE_ULTIME_LEGACY_ID
            self.current_quest_id = None
            self.state = self.GUIDE_OVERVIEW
            view.set_character_key(self.current_character_key)
            self.stack.setCurrentWidget(view)
            if getattr(service, "manual_manifest_active", False):
                count = len(getattr(service, "manual_chapters", ()) or ())
                self.status_callback(f"Guide Ultime — route manuelle canonique ({count} chapitres)")
            else:
                self.status_callback("Guide Ultime — fallback V5 généré")
            return True
        return self._select_guide_standard(guide_id)

    def show_guide_overview(self, guide_id: str, preserve_scroll: bool = False) -> None:
        if str(guide_id) == GUIDE_ULTIME_LEGACY_ID:
            self.select_guide(GUIDE_ULTIME_LEGACY_ID)
            return
        self._show_guide_overview_standard(guide_id, preserve_scroll=preserve_scroll)

    def set_character_key(self, character_key: str) -> None:
        previous = self.current_character_key
        self._set_character_key_standard(character_key)
        if self.guide_ultime_view is not None and self.current_character_key != previous:
            self.guide_ultime_view.set_character_key(self.current_character_key)
        self._mark_external_progress_refreshed()

    def set_quest_group_completed(
        self,
        quest_ids: Iterable[int],
        completed: bool,
    ) -> None:
        ids = tuple(dict.fromkeys(int(value) for value in quest_ids))
        if not ids:
            return

        guide = self.current_guide()
        left_position = self.left_scroll.verticalScrollBar().value()
        right_position = self.right_scroll.verticalScrollBar().value()

        # One authoritative batch mutation replaces the legacy scalar loop that
        # reloaded and rewrote the entire progress JSON once per quest.
        self.quest_progress_service.set_quests_completed(
            self.current_character_key,
            ids,
            bool(completed),
        )
        self.quest_progress = self.quest_progress_service.progress
        self._sync_achievement_progress()
        self._mark_external_progress_refreshed()

        if guide is None:
            return

        if self.state == self.GUIDE_OVERVIEW:
            self._update_visible_quest_progress(guide, ids)
            self._update_visible_series_progress(guide)
            self._populate_guide_left(guide)
            self._render_header(guide)
            self._populate_guide_info(guide)

            def restore_side_scrolls() -> None:
                left_bar = self.left_scroll.verticalScrollBar()
                right_bar = self.right_scroll.verticalScrollBar()
                left_bar.setValue(min(left_position, left_bar.maximum()))
                right_bar.setValue(min(right_position, right_bar.maximum()))

            _single_shot(self, 0, restore_side_scrolls)
            _single_shot(self, 50, restore_side_scrolls)
            return

        if self.state == self.QUEST_DETAIL and self.current_quest_id is not None:
            self.show_quest_detail(self.current_quest_id, preserve_scroll=True)

    def refresh_external_progress(self) -> None:
        if not self._external_progress_changed():
            return
        if self.current_guide_id != GUIDE_ULTIME_LEGACY_ID:
            self._refresh_external_progress_standard()
            if self.guide_ultime_view is not None:
                self.guide_ultime_view.refresh_external_progress()
            self._mark_external_progress_refreshed()
            return
        self.quest_progress = self.quest_progress_service.reload()
        self.guide_progress_service.reload()
        self._sync_achievement_progress()
        self._refresh_guide_ultime_home_labels()
        if self.guide_ultime_view is not None:
            self.guide_ultime_view.refresh_external_progress()
        self._mark_external_progress_refreshed()

    def _on_guide_ultime_quest_progress_changed(self, quest_id: int) -> None:
        self.quest_progress = self.quest_progress_service.reload()
        self._sync_achievement_progress()
        self._refresh_guide_ultime_home_labels()
        if self.guide_ultime_view is not None:
            self.guide_ultime_view.refresh(reset_to_active=False)
        self._mark_external_progress_refreshed()



def _compact_guide_tree_title(
    guide: Guide,
    title: str,
) -> str:
    text = clean_text(title)

    if guide.category != "aventure":
        return text

    # Normalize every kind of dash to ASCII "-".
    text = (
        text
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )

    # Normalize French level ranges:
    # "20 ? 40" -> "20-40"
    text = re.sub(
        r"\s+[a\u00e0]\s+",
        "-",
        text,
        flags=re.IGNORECASE,
    )

    # Remove:
    # -20 - Incarnam
    # 20 - Incarnam
    # Niv. 20 - Incarnam
    # Niveau 20-40 : Incarnam
    text = re.sub(
        r"^\s*-?\s*"
        r"(?:niv(?:eau)?\.?\s*)?"
        r"\d{1,3}"
        r"(?:\s*-\s*\d{1,3})?"
        r"\s*[-:|]*\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    # Remove useless "full succes" wording.
    text = re.sub(
        r"^\s*(?:"
        r"full\s+succ\S*|"
        r"succ\S*\s+complet\S*|"
        r"tous\s+les\s+succ\S*"
        r")\s*[-:|]*\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    key = normalize_text(text)

    # Real short semantic names.
    # No truncation and absolutely no "...".

    if "dimension" in key:
        return "Dimensions"

    if "incarnam" in key:
        return "Incarnam"

    if "astrub" in key:
        return "Astrub"

    if "bonta" in key and "amakna" in key:
        return "Bonta & Amakna"

    if "bwork" in key or "tofu" in key:
        return "Bworks & Tofus"

    if "larve" in key or "kwak" in key:
        return "Larves & Kwaks"

    if "moon" in key or "wabbit" in key:
        return "Moon & Wabbits"

    if "gelee" in key or "saharach" in key:
        return "Gel\u00e9es & Saharach"

    if "otomai" in key:
        return "Otoma\u00ef"

    if "nyee" in key or "abraknyde" in key:
        return "Ny\u00e9e & Abraknydes"

    if "rasboul" in key or "rat" in key:
        return "Rats & Rasboul"

    if "frigost" in key and "pandala" in key:
        return "Frigost & Pandala"

    if "frigost" in key:
        return "Frigost"

    if "pandala" in key:
        return "Pandala"

    if "sufokia" in key:
        return "Sufokia"

    if "brakmar" in key:
        return "Br\u00e2kmar"

    if "bonta" in key:
        return "Bonta"

    if "amakna" in key:
        return "Amakna"

    # Fallback:
    # remove generic useless wording instead of adding "...".
    text = re.sub(
        r"\b(?:"
        r"premiers?\s+succ\S*|"
        r"succ\S*|"
        r"qu[e\u00ea]tes?|"
        r"alentours?|"
        r"environs?|"
        r"zones?|"
        r"progression"
        r")\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s{2,}",
        " ",
        text,
    ).strip(" -,:;|/")

    # If it is still verbose, keep the first meaningful
    # geographic group, without ellipsis.
    for separator in (
        " - ",
        " : ",
        " / ",
        ",",
    ):
        if separator in text:
            candidate = text.split(
                separator,
                1,
            )[0].strip()

            if candidate:
                text = candidate
                break

    return text or "\u00c9tape"


def _catalog_guide_title(guide: Guide) -> str:
    title = str(guide.title or "")
    if guide.category == "alignements":
        for prefix in ("Alignement ", "Alignements "):
            if title.startswith(prefix):
                return title[len(prefix) :]
    return title



def _catalog_subtitle(guide: Guide) -> str:
    if guide.category == "aventure":
        return "Parcours complet"

    return _display_guide_level_text(guide)


def _category_breadcrumb_label(guide: Guide) -> str:
    labels = {"aventure": "Aventure", "alignements": "Alignements", "dofus": "Dofus"}
    return labels.get(guide.category, guide.category.title())


def _display_guide_level_text(guide: Guide) -> str:
    minimum = _positive_int(getattr(guide, "recommended_level_min", None))
    maximum = _positive_int(getattr(guide, "recommended_level_max", None))
    if minimum is not None and maximum is not None and minimum != maximum:
        return f"Niveau {minimum} à {maximum}"
    if minimum is not None:
        return f"Niveau {minimum}"
    if maximum is not None:
        return f"Niveau {maximum}"
    return ""


def _display_quest_level_text(quest) -> str:
    if quest is None:
        return ""
    minimum = _positive_int(getattr(quest, "level_min", None))
    if minimum is not None:
        return f"Niveau minimum : {minimum}"
    return ""


def _short_quest_level(quest) -> str:
    if quest is None:
        return ""
    minimum = _positive_int(getattr(quest, "level_min", None))
    maximum = _positive_int(getattr(quest, "level_max", None))
    if minimum is not None:
        return f"Niv. {minimum}"
    if maximum is not None:
        return f"Niv. {maximum}"
    return ""


def _positive_int(value: object) -> int | None:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None



def _series_heading(series: GuideSeries) -> str:
    title = clean_text(series.title).upper()

    if not title:
        return "QUETES"

    if normalize_text(title).startswith(
        "serie_"
    ):
        return "QUETES"

    return title


def _progress_count(completed: int, total: int) -> str:
    return f"{completed}/{total}" if total else "0/0"


def _progress_label(progress: tuple[int, int, str] | None) -> str:
    completed, total, _state = progress or (0, 0, "")
    return f"{completed}/{total}" if total else ""


def _tuple_progress_state(progress: tuple[int, int, str] | None) -> str:
    completed, total, _state = progress or (0, 0, "")
    if total and completed >= total:
        return "done"
    if completed:
        return "partial"
    return "todo"


def _is_complete(completed: int, total: int) -> bool:
    return bool(total and completed >= total)


def _progress_marker(progress: ProgressCount) -> str:
    if progress.is_complete:
        return "✓"
    if progress.completed:
        return "●"
    return "○"


def _progress_state(progress: ProgressCount) -> str:
    if progress.is_complete:
        return "done"
    if progress.completed:
        return "partial"
    return "todo"


def _unique_texts(lines: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for line in lines:
        text = clean_text(line)
        key = normalize_text(text)
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return tuple(result)


def _guide_pixmap(guide: Guide) -> QPixmap | None:
    return _pixmap_from_paths(
        [
            str(getattr(guide, "image_path", "") or ""),
            str(getattr(getattr(guide, "illustration_item", None), "image_path", "") or ""),
            str(getattr(getattr(guide, "reward_item", None), "image_path", "") or ""),
        ]
    )


def _quest_pixmap(quest) -> QPixmap | None:
    if quest is None:
        return None
    paths: list[str] = []
    for step in getattr(quest, "steps", []):
        for objective in getattr(step, "objectives", []):
            path = str(getattr(objective, "image_path", "") or "")
            if path:
                paths.append(path)
    for reward in getattr(quest, "rewards", []):
        path = str(getattr(reward, "image_path", "") or "")
        if path:
            paths.append(path)
    return _pixmap_from_paths(paths)


def _pixmap_from_paths(paths: Iterable[str]) -> QPixmap | None:
    for candidate in paths:
        path = Path(candidate)
        if not candidate or not path.exists():
            continue
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            return pixmap
    return None


def hidden_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("GuideCompatLabel")
    label.setVisible(False)
    return label


def info_section(title: str, widgets: list[QWidget]) -> QWidget:
    section = QFrame()
    section.setObjectName("GuideInfoSection")
    layout = QVBoxLayout(section)
    layout.setContentsMargins(0, 8, 0, 8)
    layout.setSpacing(6)
    legacy_titles = {
        "PRÉREQUIS": "Prérequis",
        "OBJETS NÉCESSAIRES": "Objets nécessaires",
        "INFO QUÊTE": "Info quête",
        "RÉCOMPENSES": "Récompenses",
    }
    legacy = legacy_titles.get(title)
    if legacy:
        layout.addWidget(hidden_label(legacy))
    layout.addWidget(section_title(title))
    for widget in widgets:
        layout.addWidget(widget)
    return section


def progress_summary(completed: int, total: int) -> QWidget:
    row = QFrame()
    row.setObjectName("GuideProgressSummary")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    bar = QProgressBar()
    bar.setObjectName("GuideTinyProgress")
    bar.setTextVisible(False)
    bar.setRange(0, max(1, total))
    bar.setValue(min(completed, total) if total else 0)
    bar.setFixedHeight(7)
    layout.addWidget(bar, 1)

    label = QLabel(f"{completed} / {total}" if total else "0 / 0")
    label.setObjectName("GuideProgressText")
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    layout.addWidget(label)
    return row


def solution_header(progress: ProgressCount | None = None) -> QWidget:
    header = QFrame()
    header.setObjectName("GuideSeriesHeader")
    layout = QHBoxLayout(header)
    layout.setContentsMargins(0, 0, 0, 2)
    layout.setSpacing(8)
    layout.addWidget(section_title("SOLUTION"), 1)
    return header


def prerequisite_row(text: str, done: bool | None) -> QWidget:
    row = QFrame()
    row.setObjectName("GuidePrerequisiteRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)
    marker = QLabel("✓" if done is True else "○" if done is False else "")
    marker.setObjectName("GuideTreeState")
    marker.setProperty("state", "done" if done is True else "todo" if done is False else "neutral")
    marker.setFixedWidth(18)
    marker.setAlignment(Qt.AlignCenter)
    layout.addWidget(marker, 0, Qt.AlignTop)
    layout.addWidget(text_label(text, "GuideInfoLine"), 1)
    return row


def activity_chip_grid(labels: Iterable[str]) -> QWidget:
    container = QFrame()
    container.setObjectName("GuideActivityGrid")
    grid = QGridLayout(container)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(6)
    grid.setVerticalSpacing(6)
    for index, label in enumerate(labels):
        chip = QFrame()
        chip.setObjectName("GuideActivityChip")
        chip_layout = QHBoxLayout(chip)
        chip_layout.setContentsMargins(6, 3, 7, 3)
        chip_layout.setSpacing(5)
        icon = icon_label(atlas_icon(activity_icon_key(label)), "GuideInfoIcon", 18, 14)
        chip_layout.addWidget(icon)
        text = QLabel(label)
        text.setObjectName("GuideActivityText")
        text.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        chip_layout.addWidget(text)
        grid.addWidget(chip, index // 2, index % 2)
    return container


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)


def panel_title(text: str, object_name: str = "PanelTitle") -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


def section_title(text: str) -> QLabel:
    return panel_title(text, "GuideInfoSectionTitle")


def text_label(text: str, object_name: str = "GuideInfoLine") -> QLabel:
    raw = str(text or "")
    label = QLabel(linkify_travel_text(raw) if TRAVEL_COORD_RE.search(raw) else raw)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    if TRAVEL_COORD_RE.search(raw):
        label.setTextFormat(Qt.RichText)
        label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(copy_travel_link)
    else:
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


def linkify_travel_text(text: str) -> str:
    escaped = escape(str(text or ""))

    def replace(match: re.Match[str]) -> str:
        x = int(match.group(1))
        y = int(match.group(2))
        return f'<a href="atlas-travel:{x},{y}">[{x},{y}]</a>'

    return TRAVEL_COORD_RE.sub(replace, escaped)


def copy_travel_link(href: str) -> None:
    match = re.search(r"(-?\d+)\s*,\s*(-?\d+)", str(href or ""))
    if match:
        QApplication.clipboard().setText(f"/travel {int(match.group(1))},{int(match.group(2))}")


def is_walkthrough_image_path(image_path: str) -> bool:
    path = str(image_path or "").replace("\\", "/").lower()
    return bool(path) and "/images/quests/" in path


def solution_block_widget(block: DisplaySolutionBlock) -> QWidget:
    if block.block_type == "image" and block.image_path and Path(block.image_path).exists():
        container = QFrame()
        container.setObjectName("QuestSolutionImageBlock")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(4)
        layout.addWidget(SolutionImageLabel(block.image_path, block.caption), 0, Qt.AlignHCenter)
        return container
    if block.block_type == "heading":
        return text_label(block.content.rstrip(":"), "QuestSolutionStepTitle")
    object_name = "QuestSolutionCombat" if block.block_type == "combat" else "QuestSolutionDescription"
    return text_label(block.content, object_name)


def quest_solution_document_widgets(quest, *, omit_first_image_path: str = "") -> list[QWidget]:
    """Render a walkthrough as a small number of selectable document blocks."""

    blocks = list(quest_solution_blocks(quest))
    if not blocks:
        for step in quest_solution_steps(quest):
            if step.title:
                blocks.append(DisplaySolutionBlock("heading", step.title))
            if step.description:
                blocks.append(DisplaySolutionBlock("text", step.description))
            for objective in step.objectives:
                if objective.text:
                    blocks.append(
                        DisplaySolutionBlock(
                            "combat" if objective.combat else "text",
                            objective.text,
                            position=objective.position,
                        )
                    )
                # Gameplay-objective assets are not documentary proof.  Only
                # explicit ordered source blocks may place images in a quest.

    widgets: list[QWidget] = []
    text_blocks: list[DisplaySolutionBlock] = []

    def flush_text() -> None:
        if text_blocks:
            widgets.append(solution_text_document(tuple(text_blocks)))
            text_blocks.clear()

    omitted_start_image = False
    for block in blocks:
        if (
            block.block_type == "image"
            and omit_first_image_path
            and not omitted_start_image
            and Path(block.image_path) == Path(omit_first_image_path)
        ):
            omitted_start_image = True
            continue
        if block.block_type == "image":
            flush_text()
            widgets.append(solution_block_widget(block))
        else:
            text_blocks.append(block)
    flush_text()
    return widgets


def solution_text_document(blocks: tuple[DisplaySolutionBlock, ...]) -> QLabel:
    parts: list[str] = []
    for block in blocks:
        content = clean_text(block.content)
        if not content:
            continue
        linked = linkify_travel_text(content)
        if block.block_type == "heading":
            parts.append(
                f'<p style="font-size:13px;font-weight:700;color:#eee7fb;margin:10px 0 4px 0;">'
                f'{linked.rstrip(":")}</p>'
            )
        elif block.block_type == "combat":
            parts.append(f'<p style="color:#e7bf63;margin:6px 0;"><b>Combat :</b> {linked}</p>')
        else:
            parts.append(f'<p style="margin:3px 0;line-height:1.35;">{linked}</p>')
    label = QLabel(render_theme_template("".join(parts)))
    label.setObjectName("QuestSolutionDocument")
    label.setTextFormat(Qt.RichText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextBrowserInteraction)
    label.setOpenExternalLinks(False)
    label.linkActivated.connect(copy_travel_link)
    label.setCursor(Qt.IBeamCursor)
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    return label


def quest_navigation_footer(
    previous_id: int | None,
    next_id: int | None,
    quests_by_id: dict[int, object],
    on_open: Callable[[int], object],
) -> QWidget | None:
    candidates = (("previous", "←", previous_id), ("next", "→", next_id))
    valid = [
        (kind, arrow, int(quest_id))
        for kind, arrow, quest_id in candidates
        if quest_id is not None and int(quest_id) in quests_by_id
    ]
    if not valid:
        return None
    footer = QFrame()
    footer.setObjectName("QuestNavigationFooter")
    layout = QHBoxLayout(footer)
    layout.setContentsMargins(0, 8, 0, 0)
    layout.setSpacing(6)
    for kind, arrow, quest_id in valid:
        if kind == "next":
            layout.addStretch(1)
        quest = quests_by_id[quest_id]
        button = AtlasButton(arrow)
        button.setObjectName("QuestPreviousButton" if kind == "previous" else "QuestNextButton")
        button.setFixedSize(32, 28)
        button.setToolTip(str(getattr(quest, "name", "")))
        prefix = "Quête précédente : " if kind == "previous" else "Quête suivante : "
        button.setAccessibleName(prefix + str(getattr(quest, "name", "")))
        button.clicked.connect(lambda _checked=False, qid=quest_id: on_open(qid))
        layout.addWidget(button)
    if not any(kind == "next" for kind, _arrow, _quest_id in valid):
        layout.addStretch(1)
    return footer


def info_row(key: str, value: str) -> QWidget:
    row = QFrame()
    row.setObjectName("GuideInfoRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    key_label = QLabel(key)
    key_label.setObjectName("GuideInfoKey")
    key_label.setFixedWidth(68)
    value_label = QLabel(value)
    value_label.setObjectName("GuideInfoValue")
    value_label.setWordWrap(True)
    value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(key_label, 0, Qt.AlignTop)
    layout.addWidget(value_label, 1)
    return row


def icon_row(kind: str, text: str) -> QWidget:
    row = QFrame()
    row.setObjectName("GuideIconRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    icon = icon_label(atlas_icon(kind), "GuideInfoIcon", 20, 16)
    layout.addWidget(icon, 0, Qt.AlignTop)
    layout.addWidget(text_label(text), 1)
    return row


def travel_position_row(position: str) -> QWidget:
    button = AtlasButton(str(position or ""))
    button.setObjectName("GuideInlineQuestButton")
    button.setToolTip("Copier la commande /travel")
    button.clicked.connect(lambda _checked=False, value=str(position or ""): copy_travel_position(value))
    return button


def copy_travel_position(position: str) -> None:
    match = TRAVEL_COORD_RE.search(str(position or ""))
    if match:
        QApplication.clipboard().setText(f"/travel {int(match.group(1))},{int(match.group(2))}")


def icon_label(icon: QIcon, object_name: str = "GuideInfoIcon", size: int = 22, icon_size: int = 18) -> QLabel:
    label = QLabel()
    label.setObjectName(object_name)
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignCenter)
    pixmap = icon.pixmap(QSize(icon_size, icon_size))
    if not pixmap.isNull():
        label.setPixmap(pixmap)
    return label






def reward_row(reward: DisplayReward) -> QWidget:
    row = QFrame()
    row.setObjectName("GuideRewardRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)
    if reward.image_path and Path(reward.image_path).exists():
        image = icon_label(QIcon(reward.image_path), "GuideItemIcon")
    else:
        image = icon_label(atlas_icon("item"), "GuideItemIcon")
    layout.addWidget(image, 0, Qt.AlignTop)
    layout.addWidget(text_label(reward_label(reward)), 1)
    return row


def solution_objective_row(objective: SolutionObjective) -> QWidget:
    if is_walkthrough_image_path(objective.image_path):
        container = QFrame()
        container.setObjectName("QuestSolutionImageBlock")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 3, 0, 8)
        layout.setSpacing(6)
        if objective.text:
            layout.addWidget(text_label(clean_text(objective.text), "QuestSolutionDescription"))
        layout.addWidget(SolutionImageLabel(objective.image_path))
        return container

    row = QFrame()
    row.setObjectName("GuideIconRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)
    if objective.image_path and Path(objective.image_path).exists():
        image = icon_label(QIcon(objective.image_path), "GuideInfoIcon")
    else:
        image = icon_label(atlas_icon("combat" if objective.combat else "step"), "GuideInfoIcon")
    layout.addWidget(image, 0, Qt.AlignTop)
    layout.addWidget(text_label(clean_text(objective.text), "QuestSolutionDescription"), 1)
    return row


def atlas_icon(kind: str) -> QIcon:
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(PALETTE["GREEN"]), 1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    if kind == "quest":
        painter.drawRoundedRect(5, 3, 10, 14, 2, 2)
        painter.drawLine(7, 8, 13, 8)
        painter.drawLine(7, 12, 12, 12)
    elif kind == "solo":
        painter.drawLine(6, 16, 14, 4)
        painter.drawLine(10, 12, 14, 16)
        painter.drawLine(9, 11, 5, 7)
        painter.drawLine(5, 17, 8, 14)
    elif kind == "group":
        painter.drawLine(4, 16, 13, 5)
        painter.drawLine(7, 13, 3, 9)
        painter.drawLine(3, 17, 6, 14)
        painter.drawLine(16, 16, 7, 5)
        painter.drawLine(13, 13, 17, 9)
        painter.drawLine(17, 17, 14, 14)
    elif kind == "dungeon":
        painter.drawRoundedRect(4, 7, 12, 10, 1, 1)
        painter.drawArc(5, 2, 10, 10, 0, 180 * 16)
        painter.drawLine(7, 7, 7, 17)
        painter.drawLine(13, 7, 13, 17)
        painter.drawEllipse(9, 12, 2, 2)
    elif kind == "tactical":
        painter.drawEllipse(4, 4, 12, 12)
        painter.drawEllipse(8, 8, 4, 4)
        painter.drawLine(10, 2, 10, 6)
        painter.drawLine(10, 14, 10, 18)
        painter.drawLine(2, 10, 6, 10)
        painter.drawLine(14, 10, 18, 10)
    elif kind == "drop":
        painter.drawLine(10, 3, 15, 10)
        painter.drawArc(5, 8, 10, 9, 200 * 16, 140 * 16)
        painter.drawLine(10, 3, 5, 10)
    elif kind == "item":
        painter.drawPolygon(QPolygon([QPoint(10, 3), QPoint(16, 9), QPoint(10, 17), QPoint(4, 9)]))
    elif kind == "combat":
        painter.drawLine(4, 15, 16, 5)
        painter.drawLine(5, 5, 16, 16)
    else:
        painter.drawEllipse(5, 5, 10, 10)
        painter.drawLine(10, 2, 10, 5)
        painter.drawLine(10, 15, 10, 18)
    painter.end()
    return QIcon(pixmap)


def activity_icon_key(label: str) -> str:
    key = normalize_text(label)
    if "tactique" in key or "tactical" in key:
        return "tactical"
    if "donjon" in key or "dungeon" in key or "boss" in key:
        return "dungeon"
    if "drop" in key or "farm" in key:
        return "drop"
    if "groupe" in key or "group" in key:
        return "group"
    if "solo" in key or key in {"solo_fight"}:
        return "solo"
    if "combat" in key:
        return "combat"
    if key in {"farm", "songes", "dreams", "dalle", "slab"}:
        return "step"
    return "quest"

