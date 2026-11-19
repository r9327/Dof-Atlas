from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.modules.encyclopedia.services.guide_quest_view_model import (local_item_image_path, quest_solution_steps)
from app.modules.encyclopedia.services.guide_source_media import (
    has_source_images,
    resolved_source_images,
)
from app.modules.encyclopedia.views.guide_ultime_manual_view import (
    GuideUltimeManualCard,
    GuideUltimeManualView,
)
from app.core.text import normalize_key as normalize_text
from app.ui.components import AtlasButton, AtlasComboBox, AtlasGuideDisclosure, AtlasGuideCover, AtlasGuideParticipantButton, atlas_guide_arrow_icon, atlas_guide_character_icon, fit_unity_number_spinbox
from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX, UNITY_LAYOUT_SIZES_PX, UNITY_GUIDE_READING_METRICS_PX, UNITY_SIZES_PX, UNITY_SPACING_PX
from app.ui.unity_skin import apply_unity_panel_shadow
from app.constants import DATA_DIR
from app.modules.encyclopedia.services.image_service import ENCYCLOPEDIA_IMAGE_SERVICE
from app.ui.theme import PALETTE


_COMBAT_STOP_WORDS = {
    "affronter",
    "battre",
    "boss",
    "capture",
    "combat",
    "contre",
    "dans",
    "des",
    "du",
    "elle",
    "faire",
    "les",
    "monstre",
    "pour",
    "quete",
    "tuer",
    "une",
    "vaincre",
}

_PREPARATION_QUANTITY_RE = re.compile(
    r"\bpr[ée]pare\s+(\d+)\s*[×x]\s*(.+?)(?:[.;]|$)",
    re.IGNORECASE,
)


def _guide_symbol_icon(
    widget: QWidget, symbol: str, *, size: int = 18, color: str | None = None
) -> QIcon:
    """Share tiny semantic Qt icons instead of repainting one per row."""
    # Retain the historical widget-taking API; this artwork is independent of
    # widget identity and must not pin deleted QObjects in a global cache.
    return _cached_guide_symbol_icon(symbol, size, color or PALETTE["TEXT_SOFT"])


@lru_cache(maxsize=32)
def _cached_guide_symbol_icon(symbol: str, size: int, color: str) -> QIcon:
    """Build at most 32 lightweight icon rasters, on the Qt GUI thread."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    if symbol == "target":
        painter.drawEllipse(QPointF(9, 9), 5.3, 5.3)
        painter.drawEllipse(QPointF(9, 9), 2.2, 2.2)
        painter.drawLine(QPointF(9, 1), QPointF(9, 5))
        painter.drawLine(QPointF(9, 13), QPointF(9, 17))
        painter.drawLine(QPointF(1, 9), QPointF(5, 9))
        painter.drawLine(QPointF(13, 9), QPointF(17, 9))
    elif symbol == "cube":
        painter.drawPolyline([QPointF(9, 2), QPointF(16, 5.5), QPointF(9, 9), QPointF(2, 5.5), QPointF(9, 2)])
        painter.drawPolyline([QPointF(2, 5.5), QPointF(2, 13), QPointF(9, 17), QPointF(16, 13), QPointF(16, 5.5)])
        painter.drawLine(QPointF(9, 9), QPointF(9, 17))
    elif symbol == "trophy":
        painter.drawRoundedRect(QRectF(5, 2, 8, 9), 2, 2)
        painter.drawArc(QRectF(1.5, 2.5, 6.5, 8), 125 * 16, 205 * 16)
        painter.drawArc(QRectF(10, 2.5, 6.5, 8), 210 * 16, 205 * 16)
        painter.drawLine(QPointF(9, 11), QPointF(9, 15))
        painter.drawLine(QPointF(5, 16), QPointF(13, 16))
    elif symbol == "guide":
        painter.drawPolyline([QPointF(9, 4), QPointF(6, 2.5), QPointF(2, 3.5), QPointF(2, 14), QPointF(6, 13), QPointF(9, 15)])
        painter.drawPolyline([QPointF(9, 4), QPointF(12, 2.5), QPointF(16, 3.5), QPointF(16, 14), QPointF(12, 13), QPointF(9, 15)])
        painter.drawLine(QPointF(9, 4), QPointF(9, 15))
    elif symbol == "settings":
        center = QPointF(size / 2, size / 2)
        painter.drawEllipse(center, 3.0, 3.0)
        painter.drawEllipse(center, 5.6, 5.6)
        for dx, dy in ((0, -7), (0, 7), (-7, 0), (7, 0), (-5, -5), (5, 5), (-5, 5), (5, -5)):
            start = QPointF(center.x() + dx * 0.72, center.y() + dy * 0.72)
            end = QPointF(center.x() + dx, center.y() + dy)
            painter.drawLine(start, end)
    elif symbol == "map":
        painter.drawPolyline(
            [QPointF(2, 4), QPointF(6.5, 2), QPointF(11.5, 4), QPointF(16, 2)]
        )
        painter.drawPolyline(
            [QPointF(2, 4), QPointF(2, 15), QPointF(6.5, 13), QPointF(11.5, 15), QPointF(16, 13), QPointF(16, 2)]
        )
        painter.drawLine(QPointF(6.5, 2), QPointF(6.5, 13))
        painter.drawLine(QPointF(11.5, 4), QPointF(11.5, 15))
    elif symbol == "location":
        painter.drawEllipse(QPointF(9, 6.5), 4.2, 4.2)
        painter.drawEllipse(QPointF(9, 6.5), 1.2, 1.2)
        painter.drawLine(QPointF(6.2, 9.7), QPointF(9, 16))
        painter.drawLine(QPointF(11.8, 9.7), QPointF(9, 16))
    elif symbol == "clipboard":
        painter.drawRoundedRect(QRectF(3, 3, 12, 13), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(6, 1.5, 6, 4), 1.2, 1.2)
        painter.drawLine(QPointF(6, 9), QPointF(12, 9))
        painter.drawLine(QPointF(6, 12), QPointF(12, 12))
    elif symbol == "people":
        painter.drawEllipse(QPointF(6.2, 6), 2.6, 2.6)
        painter.drawEllipse(QPointF(12.2, 7), 2.2, 2.2)
        painter.drawArc(QRectF(1.5, 8.5, 9.5, 7), 20 * 16, 140 * 16)
        painter.drawArc(QRectF(8, 10, 8, 5), 20 * 16, 140 * 16)
    elif symbol == "summary":
        for y in (4, 9, 14):
            painter.drawEllipse(QPointF(3, y), 0.8, 0.8)
            painter.drawLine(QPointF(6, y), QPointF(16, y))
    elif symbol == "current":
        painter.drawArc(QRectF(3, 3, 11, 11), 35 * 16, 285 * 16)
        painter.drawLine(QPointF(3, 4), QPointF(3, 9))
        painter.drawLine(QPointF(3, 4), QPointF(8, 4))
    elif symbol == "lock":
        painter.drawRoundedRect(QRectF(4, 8, 10, 8), 1.5, 1.5)
        painter.drawArc(QRectF(6, 2, 6, 9), 0, 180 * 16)
    elif symbol == "unlock":
        painter.drawRoundedRect(QRectF(4, 8, 10, 8), 1.5, 1.5)
        painter.drawArc(QRectF(8, 2, 6, 9), 0, 180 * 16)
    elif symbol == "back":
        painter.drawLine(QPointF(13, 9), QPointF(3, 9))
        painter.drawLine(QPointF(8, 4), QPointF(3, 9))
        painter.drawLine(QPointF(3, 9), QPointF(8, 14))
    elif symbol == "check":
        painter.drawLine(QPointF(3, 9), QPointF(7, 13))
        painter.drawLine(QPointF(7, 13), QPointF(15, 4))
    painter.end()
    return QIcon(pixmap)


@dataclass(frozen=True, slots=True)
class _PreparationNeed:
    item_key: str
    item_id: int | None
    name: str
    category: str
    required_by_character: tuple[tuple[str, int | None], ...]
    confidence_by_character: tuple[tuple[str, str], ...] = ()
    sources: tuple[str, ...] = ()

    @property
    def required_total(self) -> int | None:
        values = [quantity for _key, quantity in self.required_by_character]
        return sum(values) if all(value is not None for value in values) else None


class _GuideProgressDonut(QWidget):
    """Small palette-aware route progress indicator used in the fixed header."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._percent: int | None = None
        self.setObjectName("GuideCompactDonut")
        self.setFixedSize(66, 66)

    def set_percent(self, value: int | None) -> None:
        value = None if value is None else max(0, min(100, int(value)))
        if value == self._percent:
            return
        self._percent = value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        ring = self.rect().adjusted(7, 7, -7, -7)
        pen = QPen(self.palette().mid().color(), 6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(ring, 0, 360 * 16)
        pen.setColor(self.palette().highlight().color())
        painter.setPen(pen)
        if self._percent is not None:
            painter.drawArc(ring, 90 * 16, -round(360 * 16 * self._percent / 100))
        painter.setPen(self.palette().text().color())
        painter.drawText(self.rect(), Qt.AlignCenter,
                         f"{self._percent} %" if self._percent is not None else "—")


class _ParticipantPortraitButton(QToolButton):
    """Real class portrait button with a compact individual progress ring."""

    def __init__(
        self,
        character_key: str,
        *,
        progress: int | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.character_key = str(character_key)
        self.progress = None if progress is None else max(0, min(100, int(progress)))
        self.setObjectName("GuideParticipantPortrait")
        self.setCheckable(True)
        self.setFixedSize(
            UNITY_CONTROL_SIZES_PX["guide_portrait_button"],
            UNITY_CONTROL_SIZES_PX["guide_portrait_button"],
        )
        self.setIconSize(QSize(
            UNITY_CONTROL_SIZES_PX["guide_portrait_icon"],
            UNITY_CONTROL_SIZES_PX["guide_portrait_icon"],
        ))
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Keep the ring in Unity accents; gray looks like a disabled portrait.
        color = QColor(
            PALETTE["GREEN"] if self.isChecked() else PALETTE["BORDER_STRONG"]
        )
        pen = QPen(color, 3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        if self.progress is not None:
            painter.drawArc(
                self.rect().adjusted(2, 2, -2, -2),
                90 * 16,
                -round(360 * 16 * self.progress / 100),
            )


class SharedGuideManualCard(GuideUltimeManualCard):
    """Guide-agnostic canonical card with inline route semantics."""

    def __init__(
        self,
        service,
        character_key: str,
        card: dict[str, Any],
        index: int,
        parent=None,
        *,
        travel_command_callback=None,
        show_header_title: bool = True,
        page_validation_callback=None,
    ) -> None:
        QFrame.__init__(self, parent)
        self.service = service
        self.character_key = character_key
        self.card = card
        self.index = index
        self.travel_command_callback = travel_command_callback
        self._quest_rows = self._canonical_quest_rows()
        self._quest_row_names_by_id = dict(self._quest_rows)
        self._quest_normalized_rows = tuple(
            (quest_id, self._quest_name_key(name))
            for quest_id, name in self._quest_rows if name
        )
        self._waypoint_quest_ids_by_position = None
        # One visible quest shortcut per quest and per rendered guide sheet.
        self._shown_quest_ids: set[int] = set()
        self._resource_names = self._clickable_resource_names(service, card)
        self._combat_targets: list[dict[str, Any]] = []
        self._rendered_combat_keys: set[tuple[int, int]] = set()
        self._combat_evidence_cache: dict[tuple[int, int], tuple[str, str]] = {}
        self._last_route_position_key = ""
        self.setObjectName("GuideManualSheet")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(9)

        if index == 0:
            self._add_legend(root)

        title_text = self._visible_stage_title()
        if show_header_title and title_text:
            title = QLabel(title_text)
            title.setObjectName("GuideManualStageTitle")
            title.setWordWrap(True)
            root.addWidget(title)

        section_provider = getattr(service, "manual_sections_for_card", None)
        if callable(section_provider):
            sections = section_provider(character_key, card)
            # The section provider already owns line materialization. Do not call
            # manual_lines_for_card first and build the same visible sheet twice.
            manual_lines = []
        else:
            line_provider = getattr(service, "manual_lines_for_card", None)
            manual_lines = (
                line_provider(character_key, card)
                if callable(line_provider)
                else card.get("manual_lines", []) or []
            )
            sections = {"now": manual_lines}
        if not isinstance(sections, dict) or not any(sections.values()):
            if not manual_lines:
                line_provider = getattr(service, "manual_lines_for_card", None)
                manual_lines = (
                    line_provider(character_key, card)
                    if callable(line_provider)
                    else card.get("manual_lines", []) or []
                )
            sections = {"now": manual_lines}
        sections = self._without_prepare_duplicates(sections)
        self._combat_targets = self._quest_combat_targets(sections)

        # Preparation belongs to the single global, participant-aware panel.
        # Repeating every requirement on each sheet made the route unreadable
        # and could contradict the saved ``Prêt`` state.
        self._add_line_section(
            root,
            "À FAIRE MAINTENANT",
            sections.get("now"),
            "GuideManualActionSection",
            "now",
        )
        self._add_line_section(
            root,
            "À PROFITER ICI",
            sections.get("opportunity"),
            "GuideManualActionSection",
            "opportunity",
        )
        self._add_line_section(
            root,
            "À CONSERVER POUR PLUS TARD",
            sections.get("keep"),
            "GuideManualResourceSection",
            "keep",
        )
        self._add_line_section(
            root,
            "BOSS / CAPTURES",
            sections.get("boss"),
            "GuideManualCombatSection",
            "boss",
        )
        self._add_line_section(
            root,
            "AVANT DE PARTIR",
            sections.get("before_leave"),
            "GuideManualWarningSection",
            "before_leave",
        )

        automatic = service.card_auto_complete(character_key, card)
        manual = service.page_checked(character_key, card, index)
        blocking = bool(
            callable(getattr(service, "manual_order_choice_blocking", None))
            and service.manual_order_choice_blocking(character_key, card)
        )
        trigger_ready = bool(
            callable(getattr(service, "manual_order_choice_required", None))
            and service.manual_order_choice_required(character_key, card)
        )
        if blocking:
            label = "Choisir l’ordre" if trigger_ready else "Rang 20 requis"
        elif automatic:
            label = "Valider"
        else:
            label = "Valider"
        self.page_check = AtlasButton(label)
        self.page_check.setObjectName("GuideManualPageCheck")
        self.page_check.setCheckable(True)
        self.page_check.setChecked(bool((automatic or manual) and not blocking))
        self.page_check.setEnabled(not automatic and not blocking)
        if page_validation_callback is not None:
            # Shared Guide owns selection-aware writes; do not also write to the
            # fallback global character through the legacy card handler.
            self.page_check.toggled.connect(page_validation_callback)
        elif not automatic and not blocking:
            self.page_check.setToolTip(
                "Valider cette fiche. La progression automatique reste prioritaire lorsqu’Atlas dispose de la preuve."
            )
            self.page_check.toggled.connect(self._page_toggled)

    def _visible_stage_title(self) -> str:
        """Keep authored action titles, hide redundant route/zone headings."""
        title = " ".join(str(self.card.get("manual_title") or "").split()).strip()
        normalized = normalize_text(title)
        if not title or normalized in {"fiche de route", "etape gps"}:
            return ""
        if normalized.startswith("etape gps"):
            return ""
        for field in ("manual_route_position", "zone", "subzone", "destination"):
            candidate = normalize_text(self.card.get(field))
            if candidate and (normalized == candidate or normalized in candidate):
                return ""
        return title

    @staticmethod
    def _is_combat_row(kind: str, text: str) -> bool:
        if str(kind or "").casefold() == "combat":
            return True
        normalized = normalize_text(text)
        return any(
            token in normalized
            for token in ("combat", "battre", "vaincre", "tuer", "affronter", "boss", "capture")
        )

    @staticmethod
    def _combat_tokens(value: Any) -> set[str]:
        normalized = normalize_text(value)
        return {
            token
            for token in normalized.split()
            if len(token) >= 4 and token not in _COMBAT_STOP_WORDS
        }

    @classmethod
    def _combat_text_matches(cls, row_text: Any, *candidates: Any) -> bool:
        row_normalized = normalize_text(row_text)
        if not row_normalized:
            return False
        row_tokens = cls._combat_tokens(row_text)
        for candidate in candidates:
            normalized = normalize_text(candidate)
            if not normalized:
                continue
            if normalized in row_normalized or row_normalized in normalized:
                return True
            candidate_tokens = cls._combat_tokens(candidate)
            if candidate_tokens and row_tokens.intersection(candidate_tokens):
                return True
        return False

    def _display_position(self, raw_position: str) -> str:
        """Show one coordinate per contiguous map group for every shared guide."""
        value = str(raw_position or "").strip()
        key = self._position_key(value)
        if not key:
            return value
        if key == self._last_route_position_key:
            return ""
        self._last_route_position_key = key
        return value

    @staticmethod
    def _append_source_images(
        layout: QVBoxLayout, image_paths: tuple[str, ...], caption: str,
    ) -> None:
        if not image_paths:
            return
        # Reuse the existing asynchronous, clickable zoom viewer from Quêtes;
        # the shared Dev UI metrics own the small inline preview geometry.
        from app.modules.encyclopedia.views.guides_view import SolutionImageLabel

        size = (
            UNITY_GUIDE_READING_METRICS_PX["source_image_max_width"],
            UNITY_GUIDE_READING_METRICS_PX["source_image_max_height"],
        )
        for path in image_paths:
            layout.addWidget(
                SolutionImageLabel(
                    path, caption=caption, max_preview_size=size,
                ),
                0, Qt.AlignLeft,
            )

    def _add_line_section(
        self,
        root: QVBoxLayout,
        title: str,
        rows,
        object_name: str,
        section_key: str,
    ) -> None:
        visible = [
            row
            for row in rows or []
            if isinstance(row, dict) and (
                str(row.get("text") or "").strip()
                or has_source_images(row)
            )
        ]
        if not visible:
            return

        frame = QFrame()
        frame.setObjectName(
            "GuideManualWarningSection" if section_key == "prepare" else object_name
        )
        # The global Unity stylesheet owns the combat/section material.
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        heading = QLabel(title)
        heading.setObjectName("GuideManualSectionTitle")
        layout.addWidget(heading)

        # Share only presentation containers for contiguous, proven map
        # coordinates. Preserve each authored action, its click targets and
        # exact ordering; never fuse objectives or infer that a zone is a map.
        def group_key(row: dict[str, Any]) -> str:
            if section_key != "now" or str(row.get("kind") or "") != "action":
                return ""
            if self._is_combat_row("action", str(row.get("text") or "")):
                return ""
            key = self._position_key(str(row.get("position") or ""))
            return key if re.fullmatch(r"-?\d+,-?\d+", key) else ""

        group_keys = [group_key(row) for row in visible]
        group_layout = None
        group_position = ""
        combat_heading_added = False
        # This catalogue index is immutable for one sheet. Rebuilding it for
        # every rendered line multiplied the cost of long Guides by the
        # number of linked Quests, even for a simple hover tooltip.
        quest_names = getattr(self, "_quest_row_names_by_id", None)
        if quest_names is None:
            quest_names = dict(self._quest_rows)
        for row_index, row in enumerate(visible):
            # A Ganymède source line is already a row: its printed bullet
            # must not become a second Atlas bullet beside the same action.
            # Preserve hyphenated words and negative map coordinates.
            original_text = str(row.get("text") or "").strip()
            text = re.sub(
                r"^(?:(?:[•●▪◦]\s*)|(?:[-–—*]\s+))+",
                "", original_text,
            ).strip() or original_text
            position = self._display_position(str(row.get("position") or ""))
            images = resolved_source_images(row, roots=(DATA_DIR.parent, DATA_DIR))
            if not text and has_source_images(row):
                # Source images are valid standalone guide content. The
                # waypoint remains clickable where one was explicitly given,
                # without inventing a blank "action" or trailing dash.
                if position:
                    location = QLabel()
                    location.setObjectName("GuideManualLine")
                    location.setWordWrap(True)
                    self._set_clickable_text(
                        location,
                        self._format_line_html("", "", position, [], []),
                    )
                    layout.addWidget(location)
                if images:
                    self._append_source_images(
                        layout, images, str(row.get("caption") or ""),
                    )
                else:
                    missing = QLabel("Illustration absente des fichiers locaux")
                    missing.setObjectName("GuideManualWarning")
                    layout.addWidget(missing)
                continue
            kind = str(row.get("kind") or "")
            prefix = "⚠ " if kind == "warning" else ""
            combat_line = self._is_combat_row(kind, text)

            row_widget = QFrame()
            row_widget.setObjectName(
                "GuideManualCombatLineRow" if combat_line else "GuideManualLineRow"
            )
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(7)

            line = QLabel()
            # Keep the source text unchanged for navigation/Doctor oracles.
            # Qt's shared QSS owns base text colors; only known entities
            # receive the inline semantic markup from _format_line_html.
            self._set_clickable_text(
                line,
                self._format_line_html(
                    prefix, position, text, self._npc_names(text),
                    self._resource_names,
                ),
            )
            if section_key == "prepare":
                line.setObjectName("GuideManualLine")
            elif combat_line:
                line.setObjectName("GuideManualCombatInlineText")
            else:
                line.setObjectName(self._line_object_name(kind, text))
            line.setWordWrap(True)
            related_quest_ids = self._quest_ids_for_row(row)
            related_names = [
                quest_names[quest_id]
                for quest_id in related_quest_ids
                if quest_id in quest_names
            ]
            if related_names:
                line.setToolTip("Quête : " + " · ".join(related_names))
            row_layout.addWidget(line, 1)
            if section_key == "now":
                self._add_inline_quest_links(
                    row_layout, row, quest_ids=related_quest_ids
                )

            current_key = group_keys[row_index]
            adjacent = bool(current_key) and (
                (row_index > 0 and group_keys[row_index - 1] == current_key)
                or (
                    row_index + 1 < len(group_keys)
                    and group_keys[row_index + 1] == current_key
                )
            )
            if adjacent:
                if group_layout is None or group_position != current_key:
                    group = QFrame()
                    group.setObjectName("GuideManualActionGroup")
                    group_layout = QVBoxLayout(group)
                    group_layout.setContentsMargins(0, 0, 0, 0)
                    group_layout.setSpacing(2)
                    layout.addWidget(group)
                    group_position = current_key
                group_layout.addWidget(row_widget)
            else:
                group_layout = None
                group_position = ""
                layout.addWidget(row_widget)
            target_layout = group_layout if adjacent else layout

            combat_targets = self._combat_targets_for_row(row, section_key)
            if combat_targets and not combat_heading_added:
                combat_heading = QLabel("Faire les combats :")
                combat_heading.setObjectName("GuideManualCombatTargetsTitle")
                target_layout.addWidget(combat_heading)
                combat_heading_added = True
            for target in combat_targets:
                self._add_combat_target(target_layout, target)
            if images:
                self._append_source_images(
                    target_layout, images,
                    str(row.get("caption") or text),
                )
            elif has_source_images(row):
                missing = QLabel("Illustration absente des fichiers locaux")
                missing.setObjectName("GuideManualWarning")
                target_layout.addWidget(missing)

        root.addWidget(frame)

    @staticmethod
    def _combat_key(target: dict[str, Any]) -> tuple[int, int]:
        return int(target["quest_id"]), int(target["objective_id"])

    def _cached_quest_for_combat(self, quest_id: int) -> Any:
        """Never compile a cold rich Quest while painting a Guide sheet.

        Canonical compact combat evidence and the authored Guide remain the
        first sources. Rich objective/solution fallback is permitted only when
        those details have already been hydrated by a Quest worker or an
        earlier user action. No background job is launched from Qt painting.
        """
        provider = getattr(self.service, "quest_provider", None)
        getter = getattr(provider, "get_quest", None)
        if not callable(getter):
            return None
        catalog = getattr(provider, "_catalog", None)
        if bool(getattr(catalog, "deferred_details", False)):
            cached = getattr(catalog, "is_detail_cached", None)
            if not callable(cached) or not bool(cached(int(quest_id))):
                return None
        try:
            return getter(int(quest_id))
        except (KeyError, LookupError, TypeError, ValueError):
            return None

    def _combat_evidence(self, target: dict[str, Any]) -> tuple[str, str]:
        key = self._combat_key(target)
        cached = self._combat_evidence_cache.get(key)
        if cached is not None:
            return cached

        position = ""
        objective_text = ""
        quest = self._cached_quest_for_combat(key[0])
        if quest is not None:
            for step in getattr(quest, "steps", ()) or ():
                for objective in getattr(step, "objectives", ()) or ():
                    try:
                        objective_id = int(getattr(objective, "id", 0) or 0)
                    except (TypeError, ValueError):
                        continue
                    if objective_id != key[1]:
                        continue
                    objective_text = str(getattr(objective, "text", "") or "").strip()
                    position = str(
                        getattr(objective, "map_label", "")
                        or getattr(objective, "position", "")
                        or ""
                    ).strip()
                    break
                if objective_text or position:
                    break

        evidence = (position, objective_text)
        self._combat_evidence_cache[key] = evidence
        return evidence

    def _combat_targets_for_row(
        self,
        row: dict[str, Any],
        section_key: str,
    ) -> list[dict[str, Any]]:
        row_text = str(row.get("text") or "")
        row_position = self._position_key(str(row.get("position") or ""))
        row_is_combat = self._is_combat_row(str(row.get("kind") or ""), row_text)
        unseen = [
            target
            for target in self._combat_targets
            if self._combat_key(target) not in self._rendered_combat_keys
        ]

        # The compact Guide evidence already contains the monster name and
        # objective ID. Match it before touching any deferred rich Quest.
        # _combat_evidence() can hydrate a cold 69 MiB source catalogue on
        # the Qt thread; doing that for every ordinary text row caused the
        # 19-second mid-route stall observed in the Windows Guide benchmark.
        direct = [
            target for target in unseen
            if self._combat_text_matches(row_text, target.get("monster"))
        ]
        if direct:
            return direct
        # Non-combat rows can never consume position/solution fallbacks;
        # avoid triggering even one rich Quest hydration for such rows.
        if not row_is_combat:
            return []

        same_position: list[dict[str, Any]] = []
        for target in unseen:
            target_position, objective_text = self._combat_evidence(target)
            if self._combat_text_matches(row_text, objective_text):
                direct.append(target)
                continue
            if (
                row_position
                and self._position_key(target_position) == row_position
            ):
                same_position.append(target)
        if direct:
            return direct

        solution_targets = self._solution_combat_targets_for_row(row)
        if solution_targets:
            return solution_targets

        if row_is_combat and len(same_position) == 1:
            return same_position

        # Last safe fallback: only one still-unrendered combat and the current
        # row itself is explicitly a combat row. Never dump unrelated combats
        # into a detached block at the end of the sheet.
        if row_is_combat and len(unseen) == 1:
            return unseen
        return []

    def _solution_combat_targets_for_row(
        self,
        row: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Resolve source-solution combats against the exact route row."""
        row_text = str(row.get("text") or "")
        row_kind = str(row.get("kind") or "")
        row_is_combat = self._is_combat_row(row_kind, row_text)
        if not row_is_combat:
            return []

        row_position = self._position_key(str(row.get("position") or ""))
        candidates: list[tuple[dict[str, Any], str, str, str]] = []
        seen: set[tuple[int, int]] = set()
        for raw in self.card.get("manual_quest_ids", []) or []:
            try:
                quest_id = int(raw)
            except (TypeError, ValueError):
                continue
            quest = self._cached_quest_for_combat(quest_id)
            if quest is None:
                continue
            quest_name = str(getattr(quest, "name", "") or "").strip()
            local_objectives: dict[int, Any] = {}
            for quest_step in getattr(quest, "steps", ()) or ():
                for local in getattr(quest_step, "objectives", ()) or ():
                    objective_id = self._safe_positive_int(getattr(local, "id", None))
                    if objective_id is not None:
                        local_objectives[objective_id] = local

            try:
                solution_steps = quest_solution_steps(quest)
            except (AttributeError, TypeError, ValueError):
                continue
            for solution_step in solution_steps:
                for objective in getattr(solution_step, "objectives", ()) or ():
                    if not bool(getattr(objective, "combat", False)):
                        continue
                    objective_id = self._safe_positive_int(
                        getattr(objective, "objective_id", None)
                    )
                    if objective_id is None:
                        continue
                    key = (quest_id, objective_id)
                    if key in seen or key in self._rendered_combat_keys:
                        continue

                    local = local_objectives.get(objective_id)
                    local_text = str(
                        getattr(local, "text", "")
                        or getattr(objective, "text", "")
                        or ""
                    ).strip()
                    objective_text = str(getattr(objective, "text", "") or "").strip()
                    monster = str(
                        getattr(local, "image_label", "")
                        or objective_text
                        or local_text
                    ).strip()
                    quantity = (
                        self._combat_quantity(local, local_text)
                        if local is not None
                        else self._safe_positive_int(getattr(objective, "quantity", None)) or 1
                    )
                    objective_position = self._position_key(
                        str(getattr(objective, "position", "") or "")
                    )
                    target = {
                        "quest_id": quest_id,
                        "objective_id": objective_id,
                        "quest_name": quest_name,
                        "monster": monster,
                        "quantity": quantity,
                    }
                    seen.add(key)
                    candidates.append((target, objective_text, local_text, objective_position))

        direct = [
            target
            for target, objective_text, local_text, _position in candidates
            if self._combat_text_matches(
                row_text,
                target.get("monster"),
                objective_text,
                local_text,
            )
        ]
        if direct:
            return direct

        same_position = [
            target
            for target, _objective_text, _local_text, objective_position in candidates
            if row_position and objective_position == row_position
        ]
        if len(same_position) == 1:
            return same_position
        return []

    def _add_combat_target(
        self,
        layout: QVBoxLayout,
        target: dict[str, Any],
    ) -> None:
        key = self._combat_key(target)
        if key in self._rendered_combat_keys:
            return
        self._rendered_combat_keys.add(key)

        row = QFrame()
        row.setObjectName("GuideManualCombatInlineRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(16, 3, 6, 3)
        row_layout.setSpacing(6)

        quest_id, objective_id = key
        quantity = int(target["quantity"])
        monster = str(target["monster"])
        quest_name = str(target["quest_name"])
        # The source objective supplies the quantity and monster identity.
        # Keep the action legible: quest identity belongs in the tooltip.
        checkbox = QCheckBox(f"×{quantity} {monster}")
        checkbox.setObjectName("GuideManualCombatCheck")
        # Long monster names must not impose their unbounded sizeHint on the
        # complete route sheet. The full context remains available in the
        # tooltip while the row follows the viewport width.
        checkbox.setMinimumWidth(0)
        checkbox.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        progress = getattr(self.service, "quest_progress", None)
        checked = bool(
            progress is not None
            and callable(getattr(progress, "is_objective_completed", None))
            and progress.is_objective_completed(
                self.character_key,
                quest_id,
                objective_id,
            )
        )
        checkbox.setChecked(checked)
        checkbox.setProperty("state", "done" if checked else "todo")
        tooltip = f"×{quantity} {monster}"
        if quest_name:
            tooltip += f" — {quest_name}"
        checkbox.setToolTip(
            f"{tooltip}\nProgression partagée avec l’objectif de la fiche Quête."
        )
        checkbox.toggled.connect(
            lambda value, qid=quest_id, oid=objective_id, box=checkbox: self._combat_toggled(
                qid,
                oid,
                box,
                value,
            )
        )
        row_layout.addWidget(checkbox, 1)
        layout.addWidget(row)


class SharedGuideManualView(GuideUltimeManualView):
    """Guide-agnostic canonical manual road-book renderer."""

    def _clear_cards(self) -> None:
        """Detach prior sheets immediately; Qt may defer their destruction.

        Removing the layout item alone leaves the old sheet as a visible child
        until DeferredDelete is processed. Rapid page changes then temporarily
        paint both old and new guide pages.
        """
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.rendered_card_count = 0

    def _build_ui(self) -> None:
        self.filter_mode = "Tout"
        self.navigate_entity = None
        self._preparation_needs: tuple[_PreparationNeed, ...] = ()
        self._preparation_preview: tuple[tuple[str, str, int, int | None], ...] = ()
        self._preparation_loaded = False
        self._preparation_visible_limit = 80
        # Draft counts are session-local; only the explicit Prêt action is persisted.
        self._preparation_quantity_drafts: dict[str, int] = {}
        self._participant_buttons: dict[str, _ParticipantPortraitButton] = {}
        # One bounded SQLite detail per tick. A navigation change stops the
        # previous neighborhood before reading anything for the new sheet.
        self._catalog_prefetch_index: int | None = None
        self._catalog_prefetch_timer = QTimer(self)
        self._catalog_prefetch_timer.setInterval(16)
        self._catalog_prefetch_timer.timeout.connect(self._prefetch_catalog_slice)
        root = QVBoxLayout(self)
        # Qt's default layout minimum otherwise forces the guide wider than
        # the available viewport, preventing the compact labels from activating.
        root.setSizeConstraint(QLayout.SetNoConstraint)
        # Real shadows need an unpainted edge; 6px is enough without
        # expanding the header or sacrificing scroll space.
        root.setContentsMargins(6, 5, 6, 6)
        root.setSpacing(8)

        self._build_compact_header(root)
        self._build_preparation_panel(root)
        self._build_sheet_header(root)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("GuideManualScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName("GuideManualContent")
        self.cards_layout = QVBoxLayout(self.content)
        self.cards_layout.setContentsMargins(8, 2, 8, 8)
        self.cards_layout.setSpacing(8)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

        nav = QFrame()
        nav.setObjectName("GuideManualNav")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(8, 4, 8, 6)
        nav_layout.setSpacing(8)
        self.prev_button = AtlasButton("Précédent")
        self.prev_button.setObjectName("GuideManualPrev")
        self.prev_button.setIcon(atlas_guide_arrow_icon("left"))
        self.prev_button.setIconSize(QSize(14, 14))
        self.prev_button.clicked.connect(lambda: self.navigate_relative(-1))
        nav_layout.addWidget(self.prev_button)
        nav_layout.addStretch(1)
        self.validation_host = QFrame()
        self.validation_host.setObjectName("GuideManualValidationHost")
        self.validation_layout = QHBoxLayout(self.validation_host)
        self.validation_layout.setContentsMargins(0, 0, 0, 0)
        self.validation_layout.setSpacing(0)
        nav_layout.addWidget(self.validation_host)
        nav_layout.addStretch(1)
        self.next_button = AtlasButton("Suivant")
        self.next_button.setObjectName("GuideManualNextButton")
        self.next_button.setIcon(atlas_guide_arrow_icon("right"))
        self.next_button.setIconSize(QSize(14, 14))
        self.next_button.clicked.connect(lambda: self.navigate_relative(1))
        nav_layout.addWidget(self.next_button)
        apply_unity_panel_shadow(nav)
        root.addWidget(nav)

        self.progress_details = QLabel()
        self.progress_details.setVisible(False)
        self.position_label = QLabel()
        self.position_label.setVisible(False)

    def _build_compact_header(self, root: QVBoxLayout) -> None:
        """One indexed global-progress disclosure with nested À préparer."""
        header = QFrame()
        header.setObjectName("GuideCompactHeader")
        outer = QHBoxLayout(header)
        outer.setContentsMargins(
            UNITY_LAYOUT_SIZES_PX["guide_header_margin_x"],
            UNITY_LAYOUT_SIZES_PX["guide_header_margin_top"],
            UNITY_LAYOUT_SIZES_PX["guide_header_margin_x"],
            UNITY_LAYOUT_SIZES_PX["guide_header_margin_bottom"],
        )
        outer.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_header_outer_spacing"])

        right = QVBoxLayout()
        right.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_header_content_spacing"])
        outer.addLayout(right, 1)
        # Retain the historical progress object for internal callers, but
        # do not paint a second route indicator in the header.
        self.progress_donut = _GuideProgressDonut()
        self.progress_donut.hide()
        self.donut_count_label = QLabel()
        self.donut_count_label.hide()
        self.global_progress_bar = QProgressBar()
        self.global_progress_bar.setObjectName("GuideGlobalProgress")
        self.global_progress_bar.setRange(0, 100)
        self.global_progress_bar.setTextVisible(False)
        self.global_progress_bar.setFixedHeight(
            UNITY_CONTROL_SIZES_PX["progress_primary"]
        )
        self.global_progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.global_progress_label = QLabel("—")
        self.global_progress_label.setObjectName("GuideCompactMetricValue")
        self._metric_columns: dict[str, QVBoxLayout] = {}

        # Row 1: active guide, instant sheet selector and compact commands.
        title_row = QHBoxLayout()
        title_row.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_header_content_spacing"])
        self.guide_button = AtlasButton("")
        self.guide_button.setIcon(atlas_guide_arrow_icon("left"))
        self.guide_button.setIconSize(QSize(14, 14))
        self.guide_button.setObjectName("GuideManualGuideButton")
        self.guide_button.setToolTip("Revenir à la fiche actuelle, puis au catalogue des guides")
        self.guide_button.setAccessibleName("Fiche actuelle ou catalogue des guides")
        self.guide_button.setMaximumWidth(35)
        self.guide_button.clicked.connect(
            lambda _checked=False: self._guide_button_clicked()
        )
        # Keep the back action available beside the sheet title, outside
        # the three-row compact progress header agreed with the user.
        guide_icon = AtlasGuideCover()
        self.guide_icon_label = guide_icon
        guide_data = getattr(self.service, "guide", None)
        guide_icon.set_artwork(
            getattr(self.service, "image_path", None) or getattr(guide_data, "image_path", None),
            category="dofus" if "dofus" in self._guide_title().casefold() else "guide",
        )
        title_row.addWidget(guide_icon)
        self.guide_title_label = QLabel(self._guide_title())
        self.guide_title_label.setObjectName("GuideCompactTitle")
        self.guide_title_label.setMinimumWidth(0)
        self.guide_title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.guide_title_label.setToolTip(self._guide_title())
        title_row.addWidget(self.guide_title_label, 1)

        # The sheet selector lives beside its stage title, not here.
        self.nav_page_label = QLabel(self)
        self.nav_page_label.setObjectName("GuideManualNavPage")
        self.nav_page_label.setVisible(False)
        # No dead Overlay control in the compact title row: this runtime
        # has no overlay handler to launch. Keep room for real actions only.
        right.addLayout(title_row)
        self._compact_title_row = title_row

        # Shared #363 layout: progress is global; preparation is inside details.
        overall_caption = QHBoxLayout()
        title = QLabel("Progression globale")
        title.setObjectName("GuideGlobalProgressTitle")
        overall_caption.addWidget(title)
        self.global_details_button = AtlasGuideDisclosure()
        self.global_details_button.setFixedSize(
            UNITY_CONTROL_SIZES_PX["progress_toggle_width"],
            UNITY_CONTROL_SIZES_PX["progress_toggle_height"],
        )
        self.global_details_button.setToolTip("Afficher la progression et les préparatifs")
        self.global_details_button.setAccessibleName("Déplier la progression globale")
        overall_caption.addWidget(self.global_details_button, 0, Qt.AlignVCenter)
        overall_caption.addStretch(1)
        overall_caption.addWidget(self.global_progress_label)
        right.addLayout(overall_caption)
        right.addWidget(self.global_progress_bar)

        self.global_details_panel = QFrame()
        self.global_details_panel.setObjectName("GuideGlobalDetailsPanel")
        details = QVBoxLayout(self.global_details_panel)
        details.setContentsMargins(
            UNITY_SPACING_PX["sm"], UNITY_SPACING_PX["xs"],
            UNITY_SPACING_PX["sm"], UNITY_SPACING_PX["sm"],
        )
        details.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
        self.global_details_rows = QWidget()
        self.global_details_rows.setObjectName("GuideGlobalCharacterProgress")
        self.global_details_layout = QVBoxLayout(self.global_details_rows)
        self.global_details_layout.setContentsMargins(0, 0, 0, 0)
        self.global_details_layout.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
        details.addWidget(self.global_details_rows)

        preparation_metric = QVBoxLayout()
        preparation_metric.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
        caption = QHBoxLayout()
        caption.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_caption_spacing"])
        icon = QLabel()
        icon.setObjectName("GuideCompactMetricIconCube")
        icon.setPixmap(
            _guide_symbol_icon(icon, "cube", size=16, color=PALETTE["GREEN"]).pixmap(16, 16)
        )
        icon.setFixedSize(UNITY_SIZES_PX["icon_small"], UNITY_SIZES_PX["icon_small"])
        caption.addWidget(icon)
        caption_label = QLabel("À préparer")
        caption_label.setToolTip("Préparation")
        caption.addWidget(caption_label)
        self._metric_caption_labels = {"Préparation": caption_label}
        caption.addStretch(1)
        self.preparation_progress_label = QLabel("—")
        self.preparation_progress_label.setObjectName("GuideCompactMetricValue")
        caption.addWidget(self.preparation_progress_label)
        self.preparation_button = AtlasGuideDisclosure()
        self.preparation_button.setFixedSize(
            UNITY_CONTROL_SIZES_PX["progress_toggle_width"],
            UNITY_CONTROL_SIZES_PX["progress_toggle_height"],
        )
        self.preparation_button.setToolTip("Ouvrir Préparation")
        self.preparation_button.setAccessibleName("Afficher Préparation")
        caption.insertWidget(2, self.preparation_button, 0, Qt.AlignVCenter)
        preparation_metric.addLayout(caption)
        self.preparation_bar = QProgressBar()
        self.preparation_bar.setObjectName("GuideCompactPreparationProgress")
        self.preparation_bar.setTextVisible(False)
        self.preparation_bar.setFixedHeight(UNITY_CONTROL_SIZES_PX["progress_secondary"])
        self.preparation_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        preparation_metric.addWidget(self.preparation_bar)
        drawer = QVBoxLayout()
        drawer.setContentsMargins(0, 0, 0, 0)
        self._metric_columns = {"Préparation": drawer}
        preparation_metric.addLayout(drawer)
        details.addLayout(preparation_metric)
        self.global_details_panel.setVisible(False)
        self.global_details_button.toggled.connect(self._global_details_toggled)
        right.addWidget(self.global_details_panel)
        self._header_content_layout = right

        apply_unity_panel_shadow(header)
        root.addWidget(header)

    def _build_preparation_panel(self, root: QVBoxLayout) -> None:
        # Arrow is owned by the Preparation progress metric.
        self.preparation_button.toggled.connect(self._preparation_toggled)

        self.preparation_panel = QFrame()
        self.preparation_panel.setObjectName("GuidePreparationPanel")
        panel_layout = QVBoxLayout(self.preparation_panel)
        panel_layout.setContentsMargins(
            UNITY_SPACING_PX["sm"], UNITY_SPACING_PX["xs"],
            UNITY_SPACING_PX["sm"], UNITY_SPACING_PX["xs"],
        )
        panel_layout.setSpacing(UNITY_SPACING_PX["xs"])
        # Reuse the shared Unity combo instead of seven buttons competing
        # with the two-column progress header on compact windows.
        self.preparation_filter = AtlasComboBox()
        self.preparation_filter.setObjectName("GuidePreparationCategoryFilter")
        self.preparation_filter.addItems((
            "Tout", "Prérequis", "Métiers", "Potions", "Pierres d'âme", "Clefs", "Objets",
        ))
        self.preparation_filter.setFixedHeight(UNITY_SIZES_PX["control_compact"])
        self.preparation_filter.setToolTip("Filtrer les besoins de préparation")
        self.preparation_filter.setAccessibleName("Catégorie de préparation")
        self.preparation_filter.currentTextChanged.connect(self._render_preparation)
        panel_layout.addWidget(self.preparation_filter, 0, Qt.AlignLeft)

        self.preparation_scroll = QScrollArea()
        self.preparation_scroll.setObjectName("GuidePreparationScroll")
        self.preparation_scroll.setWidgetResizable(True)
        self.preparation_scroll.setFrameShape(QFrame.NoFrame)
        self.preparation_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preparation_scroll.setMinimumHeight(UNITY_CONTROL_SIZES_PX["guide_preparation_min_height"])
        self.preparation_scroll.setMaximumHeight(UNITY_GUIDE_READING_METRICS_PX["normal_drawer_max_height"])
        self.preparation_content = QWidget()
        self.preparation_content.setObjectName("GuidePreparationContent")
        self.preparation_rows_layout = QVBoxLayout(self.preparation_content)
        self.preparation_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.preparation_rows_layout.setSpacing(UNITY_SPACING_PX["xxs"])
        self.preparation_scroll.setWidget(self.preparation_content)
        panel_layout.addWidget(self.preparation_scroll)
        self.preparation_panel.setVisible(False)
        apply_unity_panel_shadow(self.preparation_panel)
        self._metric_columns["Préparation"].addWidget(self.preparation_panel)

    def _build_sheet_header(self, root: QVBoxLayout) -> None:
        header = QFrame()
        header.setObjectName("GuideSheetHeader")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(7)
        top.addWidget(self.guide_button, 0, Qt.AlignVCenter)
        labels = QVBoxLayout()
        labels.setSpacing(1)
        self.sheet_title_label = QLabel()
        self.sheet_title_label.setObjectName("GuideSheetTitle")
        self.sheet_title_label.setWordWrap(True)
        labels.addWidget(self.sheet_title_label)
        top.addLayout(labels, 1)
        self.page_jump = QSpinBox()
        self.page_jump.setObjectName("GuideCompactPageJump")
        self.page_jump.setRange(1, max(1, len(self.service.cards)))
        self.page_jump.setSuffix(f"/{len(self.service.cards)}")
        fit_unity_number_spinbox(self.page_jump)
        self.page_jump.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.page_jump.setToolTip("Ouvrir directement la fiche sélectionnée")
        self.page_jump.setAccessibleName("Sélectionner la fiche du guide")
        self.page_jump.valueChanged.connect(
            lambda value: self._show_index(value - 1)
        )
        top.addWidget(self.page_jump, 0, Qt.AlignTop)

        self.participants_button = AtlasGuideParticipantButton()
        self.participants_button.setObjectName("GuideParticipantsButton")
        self.participants_button.setText("")
        character_icon = atlas_guide_character_icon(UNITY_CONTROL_SIZES_PX["guide_character_icon"])
        if character_icon.isNull():
            character_icon = _guide_symbol_icon(self.participants_button, "people")
        self.participants_button.setIcon(character_icon)
        self.participants_button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.participants_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.participants_button.setFixedSize(
            UNITY_CONTROL_SIZES_PX["guide_character_button"],
            UNITY_CONTROL_SIZES_PX["guide_character_button"],
        )
        self.participants_button.setIconSize(QSize(
            UNITY_CONTROL_SIZES_PX["guide_character_icon"],
            UNITY_CONTROL_SIZES_PX["guide_character_icon"],
        ))
        self.participants_button.setCheckable(True)
        self.participants_button.setCursor(Qt.PointingHandCursor)
        # One row with Guide title / Overlay / Personnages / Paramètres.
        self._compact_title_row.addWidget(
            self.participants_button, 0, Qt.AlignVCenter,
        )
        layout.addLayout(top)

        self.participants_panel = QFrame()
        self.participants_panel.setObjectName("GuideParticipantsPanel")
        self.participants_layout = QHBoxLayout(self.participants_panel)
        self.participants_layout.setContentsMargins(7, 5, 7, 5)
        self.participants_layout.setSpacing(5)
        self.participants_panel.setVisible(False)
        self.participants_button.toggled.connect(self.participants_panel.setVisible)
        # Character dropdown unfolds immediately below the title/actions,
        # above the global-progress caption and bar.
        self._header_content_layout.insertWidget(1, self.participants_panel)

        apply_unity_panel_shadow(header)
        root.addWidget(header)
        self._refresh_participants_panel()

    def _guide_title(self) -> str:
        title = str(getattr(self.service, "guide_title", "") or "").strip()
        return title or "Guide Succès"

    def _sync_compact_action_labels(self) -> None:
        """Preserve clickable actions and screen-reader names when space is scarce."""
        if not hasattr(self, "participants_button"):
            return
        count = len(self.selected_participant_keys())
        full_label = f"Mes personnages · {count}"
        # Icon-only participant selector: the count remains accessible through
        # its tooltip and accessibility label without stretching the header.
        self.participants_button.setText("")
        for name, label in getattr(self, "_metric_caption_labels", {}).items():
            label.setText("À préparer" if name == "Préparation" else name)
        self.participants_button.setAccessibleName(full_label)
        self.participants_button.setToolTip(
            "Choisir les identités stables utilisées par la progression et les déplacements."
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if hasattr(self, "participants_button"):
            self._sync_compact_action_labels()

    def _participant_source_signature(self) -> tuple[object, ...]:
        from app.pages.quest_character_cache import quest_character_source_signature

        service = self.participant_service
        profile_path = getattr(service, "profile_path", None)
        client_index_path = getattr(service, "client_index_path", None)
        binding_path = getattr(service, "binding_path", None)
        if any(path is None for path in (profile_path, client_index_path, binding_path)):
            # Some in-memory participant providers expose no files. Never
            # guess a source signature or turn their absence into a UI crash.
            return ("in_memory_participants", id(service))
        return quest_character_source_signature(
            profile_path,
            client_index_path,
            binding_path=binding_path,
        )

    def _refresh_participants_panel(self) -> None:
        self._last_participant_source_signature = self._participant_source_signature()
        while self.participants_layout.count():
            item = self.participants_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._participant_buttons.clear()
        selected = set(self.selected_participant_keys())
        characters = tuple(self.participant_service.available_characters())
        for character in characters:
            progress = self._participant_progress(character.key)
            button = _ParticipantPortraitButton(
                character.key,
                progress=progress,
            )
            button.setChecked(character.key in selected)
            icon_path, class_label = self._participant_icon(character)
            if icon_path:
                button.setIcon(QIcon(icon_path))
            else:
                button.setIcon(
                    _guide_symbol_icon(button, "people", color=PALETTE["TEXT_SOFT"])
                )
            button.setProperty("guideClassLabel", class_label)
            button.setToolTip(self._participant_tooltip(character, class_label, progress))
            button.setAccessibleName(character.label)
            button.toggled.connect(
                lambda checked, key=character.key: self._participant_toggled(key, checked)
            )
            self._participant_buttons[character.key] = button
            self.participants_layout.addWidget(button)
        if not characters:
            empty = QLabel("Aucun personnage vérifié")
            empty.setObjectName("GuideParticipantsEmpty")
            self.participants_layout.addWidget(empty)
        self.participants_layout.addStretch(1)
        self._sync_compact_action_labels()

    @staticmethod
    def _participant_tooltip(character, class_label: str, progress: int | None) -> str:
        status = "en ligne" if character.connected else "hors ligne"
        progress_label = f"{progress} %" if progress is not None else "progression inconnue"
        return (
            f"{character.label} · {class_label or 'classe inconnue'} · "
            f"{progress_label} · {status}"
        )

    def _refresh_participant_progress(self) -> None:
        """Refresh external progress without rebuilding portrait widgets."""
        for character in self.participant_service.available_characters():
            button = self._participant_buttons.get(character.key)
            if button is None:
                continue
            progress = self._participant_progress(character.key)
            if button.progress != progress:
                button.progress = progress
                button.update()
            class_label = str(button.property("guideClassLabel") or "")
            button.setToolTip(self._participant_tooltip(character, class_label, progress))

    def _participant_icon(self, character) -> tuple[str, str]:
        """Render portraits from the verified identity, never a window-name guess."""
        from app.pages.organizer.common import (
            DOFUS_CLASS_DEFINITIONS,
            class_icon_candidates,
        )

        class_key = str(getattr(character, "class_key", "") or "").strip().casefold()
        definition = DOFUS_CLASS_DEFINITIONS.get(class_key)
        if not definition:
            return "", ""
        label = str(definition["label"])
        for path in class_icon_candidates(class_key):
            if path.is_file():
                return str(path), label
        return "", label

    def _participant_progress(self, character_key: str) -> int | None:
        try:
            completed, total = self.service.route_sheet_progress(character_key)
        except (AttributeError, KeyError, TypeError, ValueError):
            return None
        return min(100, round(completed * 100 / total)) if total > 0 else None

    def _global_details_toggled(self, opened: bool) -> None:
        self.global_details_panel.setVisible(bool(opened))
        self.global_details_button.setAccessibleName(
            "Replier la progression globale" if opened else "Déplier la progression globale"
        )
        self.global_details_button.setToolTip(
            "Masquer la progression et les préparatifs"
            if opened else "Afficher la progression et les préparatifs"
        )
        if opened:
            self._refresh_global_details()
            # The drawer may have been hidden when progress changed. Materialize
            # its latest needs only when the user reopens the parent.
            if self.preparation_button.isChecked() and not self._preparation_loaded:
                self._load_preparation_needs()
                self._render_preparation(self.preparation_filter.currentText())

    def _refresh_global_details(self) -> None:
        while self.global_details_layout.count():
            item = self.global_details_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        keys = self._progress_participant_keys()
        if not keys:
            label = QLabel("Sélectionne un personnage pour afficher sa progression.")
            label.setObjectName("GuidePreparationEmpty")
            label.setWordWrap(True)
            self.global_details_layout.addWidget(label)
            return
        names = {row.key: row.label for row in self.participant_service.available_characters()}
        for key in keys:
            percent = self._participant_progress(key)
            label = QLabel(
                f"{names.get(key, key)} · {percent} %"
                if percent is not None else
                f"{names.get(key, key)} · progression inconnue"
            )
            label.setObjectName("GuidePreparationParticipantNeed")
            label.setWordWrap(True)
            self.global_details_layout.addWidget(label)

    def _preparation_toggled(self, opened: bool) -> None:
        self.preparation_panel.setVisible(bool(opened))
        if not opened:
            return
        if not self._preparation_loaded:
            self._load_preparation_needs()
        self._render_preparation(self.preparation_filter.currentText())

    def _progress_participant_keys(self) -> tuple[str, ...]:
        # A global character is a browsing context, never implicit consent to
        # change that character's saved progression.
        known = {row.key for row in self.participant_service.available_characters()}
        return tuple(key for key in self.selected_participant_keys() if key in known)

    def _card_complete(self, character_key: str, card: dict[str, Any], index: int) -> bool:
        state_getter = getattr(self.service, "card_state", None)
        if callable(state_getter):
            try:
                return bool(state_getter(character_key, card, index).complete)
            except (AttributeError, KeyError, TypeError, ValueError):
                pass
        automatic = getattr(self.service, "card_auto_complete", None)
        checked = getattr(self.service, "page_checked", None)
        return bool(
            (callable(automatic) and automatic(character_key, card))
            or (callable(checked) and checked(character_key, card, index))
        )

    @staticmethod
    def _preparation_category(name: str) -> str:
        normalized = normalize_text(name)
        if "potion" in normalized:
            return "Potions"
        return "Objets"

    @staticmethod
    def _is_soul_stone(name: str) -> bool:
        # normalize_key joins tokens with underscores, never spaces.
        normalized = normalize_text(name)
        return any(
            token in normalized
            for token in ("pierre_d_ame", "pierres_d_ame", "soul_stone")
        )

    @classmethod
    def _preparation_matches_filter(
        cls, category: str, name: str, selected_filter: str,
    ) -> bool:
        if selected_filter == "Tout":
            return True
        soul_stone = cls._is_soul_stone(name)
        if selected_filter == "Pierres d'âme":
            return category == selected_filter or (
                category == "Objets" and soul_stone
            )
        if selected_filter == "Objets":
            return category == "Objets" and not soul_stone
        return category == selected_filter

    @staticmethod
    def _preparation_item_key(item_id: int | None, name: str) -> str:
        if item_id is not None:
            return f"item:{item_id}"
        digest = hashlib.sha256(normalize_text(name).encode("utf-8")).hexdigest()[:16]
        return f"name:{digest}"

    @classmethod
    def _requirements_from_card(
        cls,
        service,
        character_key: str,
        card: dict[str, Any],
    ) -> tuple[tuple[int | None, str, int, str], ...]:
        rows: list[tuple[int | None, str, int, str]] = []
        structured = [
            raw for raw in card.get("a_preparer", ()) or ()
            if isinstance(raw, dict)
        ]
        for raw in structured:
            name = str(raw.get("name") or raw.get("label") or "").strip()
            try:
                quantity = max(1, int(raw.get("quantity") or 1))
            except (TypeError, ValueError):
                quantity = 1
            try:
                item_id = int(raw.get("item_id")) if raw.get("item_id") is not None else None
            except (TypeError, ValueError):
                item_id = None
            if name:
                rows.append((item_id, name, quantity, cls._preparation_category(name)))
        if not rows:
            sections_for_card = getattr(service, "manual_sections_for_card", None)
            sections = sections_for_card(character_key, card) if callable(sections_for_card) else {}
            for raw in sections.get("prepare", ()) if isinstance(sections, dict) else ():
                text = str(raw.get("text") or "") if isinstance(raw, dict) else str(raw or "")
                for match in _PREPARATION_QUANTITY_RE.finditer(text):
                    name = " ".join(match.group(2).split()).strip()
                    if name:
                        rows.append(
                            (None, name, max(1, int(match.group(1))), cls._preparation_category(name))
                        )
        for raw in card.get("profession_gates", ()) or ():
            if isinstance(raw, dict):
                name = str(raw.get("name") or raw.get("label") or raw.get("text") or "").strip()
            else:
                name = str(raw or "").strip()
            if name:
                rows.append((None, name, 1, "Métiers"))
        return tuple(rows)

    def _load_preparation_needs(self) -> None:
        from app.modules.encyclopedia.services.guide_preparation_model import (
            aggregate_remaining,
        )

        # A browsing character is never consent for Prêt. The no-selection
        # state remains readable without manufacturing an inventory/progress ID.
        participant_keys = self._progress_participant_keys()
        if not participant_keys:
            summary = aggregate_remaining((card, False) for card in self.service.cards)
            self._preparation_preview = tuple(
                (need.category, need.name, need.quantity or 0, need.item_id)
                for need in summary
            )
            self._preparation_needs = ()
            self._preparation_loaded = True
            self._update_preparation_progress()
            return

        self._preparation_preview = ()
        aggregated: dict[tuple[str, str], dict[str, Any]] = {}
        sections_getter = getattr(self.service, "manual_sections_for_card", None)
        for character_key in participant_keys:
            # No full Qt card materialization; one bounded data traversal for
            # each explicitly selected verified identity.
            rows = (
                (card, self._card_complete(character_key, card, index))
                for index, card in enumerate(self.service.cards)
            )
            for need in aggregate_remaining(
                rows,
                sections_for_card=(
                    lambda card, key=character_key: (
                        None if "_manual_stage_payload" in card else
                        card.get("manual_sections", {})
                        if card.get("_catalog_route_detail_lazy") else
                        sections_getter(key, card) if callable(sections_getter)
                        else card.get("manual_sections", {})
                    )
                ),
            ):
                item_key = self._preparation_item_key(need.item_id, need.name)
                row = aggregated.setdefault(
                    (item_key, need.category),
                    {
                        "item_id": need.item_id, "name": need.name,
                        "category": need.category, "required": {},
                        "confidence": {}, "sources": set(),
                    },
                )
                row["required"][character_key] = need.quantity
                row["confidence"][character_key] = need.confidence
                row["sources"].update(need.sources)

        self._preparation_needs = tuple(
            _PreparationNeed(
                item_key=item_key,
                item_id=row["item_id"],
                name=row["name"],
                category=row["category"],
                required_by_character=tuple(sorted(row["required"].items())),
                confidence_by_character=tuple(sorted(row["confidence"].items())),
                sources=tuple(sorted(row["sources"])),
            )
            for (item_key, _category), row in sorted(
                aggregated.items(),
                key=lambda item: (item[1]["category"], normalize_text(item[1]["name"])),
            )
        )
        self._preparation_loaded = True
        self._update_preparation_progress()

    def _ready_progress_key(self, need: _PreparationNeed) -> str:
        guide_id = str(getattr(self.service, "guide_id", "guide_complet") or "guide_complet")
        return f"__ui:preparation_ready:{guide_id}:{need.item_key}"

    def _need_ready(self, need: _PreparationNeed) -> bool:
        getter = getattr(self.service, "manual_checked", None)
        if not callable(getter) or not need.required_by_character:
            return False
        key = self._ready_progress_key(need)
        return all(getter(character_key, key) for character_key, _qty in need.required_by_character)

    def _set_need_ready(self, need: _PreparationNeed, checked: bool) -> None:
        key = self._ready_progress_key(need)
        known = set(self._progress_participant_keys())
        keys = tuple(character_key for character_key, _quantity in need.required_by_character
                     if character_key in known)
        getter = getattr(self.service, "manual_checked", None)
        batcher = getattr(getattr(self.service, "guide_progress", None),
                          "set_manual_steps_for_characters", None)
        setter = getattr(self.service, "set_manual_checked", None)
        if not keys or not callable(getter):
            return
        expected = {character_key: bool(getter(character_key, key)) for character_key in keys}
        if all(value == bool(checked) for value in expected.values()):
            return
        if callable(batcher):
            from app.modules.encyclopedia.services.guide_ultime_generated_service import (
                GUIDE_ULTIME_PROGRESS_ID,
            )
            progress_id = str(getattr(self.service, "progress_id", None)
                              or GUIDE_ULTIME_PROGRESS_ID)
            try:
                batcher(keys, progress_id, key, bool(checked),
                        expected_completed=expected)
            except RuntimeError:
                # Atomic compare-and-swap rejected concurrent progress edits;
                # never overwrite the other instance's work.
                self.service.reload_progress()
                self.validation_host.setToolTip(
                    "Préparation modifiée ailleurs ; actualisez les besoins."
                )
        elif len(keys) == 1 and callable(setter):
            setter(keys[0], key, bool(checked))
        else:
            self.validation_host.setToolTip(
                "Sauvegarde atomique multi-personnages indisponible."
            )
            return
        self._render_preparation(self.preparation_filter.currentText())
        self._update_preparation_progress()

    def _clear_preparation_rows(self) -> None:
        while self.preparation_rows_layout.count():
            item = self.preparation_rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _show_more_preparation(self) -> None:
        self._preparation_visible_limit += 80
        self._render_preparation(self.preparation_filter.currentText())

    def _append_preparation_more(self, remaining: int) -> None:
        if remaining <= 0:
            return
        button = AtlasButton(f"Afficher la suite ({remaining} besoins restants)", size="compact")
        button.set_style_name("GuidePreparationShowMore")
        button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        button.clicked.connect(lambda _checked=False: self._show_more_preparation())
        self.preparation_rows_layout.addWidget(button, 0, Qt.AlignLeft)

    def _fit_preparation_scroll_height(self) -> None:
        """Fit short preparation lists without losing scrolling for long ones."""
        self.preparation_rows_layout.activate()
        natural = (
            self.preparation_rows_layout.sizeHint().height() + UNITY_SPACING_PX["xs"]
        )
        self.preparation_scroll.setFixedHeight(min(
            UNITY_GUIDE_READING_METRICS_PX["normal_drawer_max_height"],
            max(UNITY_CONTROL_SIZES_PX["guide_preparation_min_height"], natural),
        ))
        self.preparation_content.adjustSize()
        # Checking a distant material must not jump back to the first item.
        # Changing the category deliberately resets the new list to its top.
        self.preparation_scroll.verticalScrollBar().setValue(
            getattr(self, "_preparation_restore_position", 0)
        )

    def _render_preparation(self, selected_filter: str) -> None:
        scrollbar = self.preparation_scroll.verticalScrollBar()
        previous_filter = getattr(self, "_preparation_last_filter", None)
        self._preparation_restore_position = (
            scrollbar.value() if selected_filter == previous_filter else 0
        )
        if previous_filter is not None and previous_filter != selected_filter:
            # Opening 200 rows in "Tout" must not make a newly selected
            # category equally long. Start each new category at normal density.
            self._preparation_visible_limit = 80
        self._preparation_last_filter = selected_filter
        self._clear_preparation_rows()
        if not self._progress_participant_keys():
            # A saved but deleted/unregistered character is not an active
            # participant. Keep the read-only preview rather than incorrectly
            # showing an empty verified team and hiding all requirements.
            label = QLabel("Aperçu des préparatifs · sélectionne un personnage pour activer Prêt.")
            label.setObjectName("GuidePreparationEmpty")
            label.setWordWrap(True)
            self.preparation_rows_layout.addWidget(label)
            preview = self._preparation_preview
            if selected_filter != "Tout":
                preview = tuple(
                    row for row in preview
                    if self._preparation_matches_filter(row[0], row[1], selected_filter)
                )
            if not preview:
                self.preparation_rows_layout.addWidget(QLabel("Aucun besoin structuré fiable."))
            else:
                # Read-only progress, but names are still copyable and
                # existing item artwork should be visible in preview mode.
                visible = preview[:self._preparation_visible_limit]
                for category, name, quantity, item_id in visible:
                    row = QFrame()
                    row.setObjectName("GuidePreparationRow")
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(
                        UNITY_SPACING_PX["xs"], UNITY_SPACING_PX["xxs"],
                        UNITY_SPACING_PX["xs"], UNITY_SPACING_PX["xxs"],
                    )
                    visible_category = (
                        "Pierres d'âme"
                        if category == "Objets" and self._is_soul_stone(name)
                        else category
                    )
                    row_layout.addWidget(self._copyable_preparation_item(
                        name,
                        f"{quantity if quantity else '?'} × {name} ({visible_category})",
                        item_id,
                    ))
                    self.preparation_rows_layout.addWidget(row)
                self._append_preparation_more(
                    len(preview) - self._preparation_visible_limit
                )
            self.preparation_rows_layout.addStretch(1)
            self._fit_preparation_scroll_height()
            return

        if selected_filter == "Tout":
            categories = (
                "Prérequis", "Métiers", "Potions", "Pierres d'âme",
                "Clefs", "Objets",
            )
            if not self._preparation_needs:
                empty = QLabel("Aucun besoin confirmé sur le parcours restant.")
                empty.setObjectName("GuidePreparationEmpty")
                self.preparation_rows_layout.addWidget(empty)
            rendered_count = 0
            for category in categories:
                matching = [
                    need for need in self._preparation_needs
                    if self._preparation_matches_filter(
                        need.category, need.name, category,
                    )
                ]
                if not matching:
                    continue
                summary = QFrame()
                summary.setObjectName("GuidePreparationSummary")
                row = QHBoxLayout(summary)
                row.setContentsMargins(
                    UNITY_SPACING_PX["sm"], UNITY_SPACING_PX["xxs"],
                    UNITY_SPACING_PX["sm"], UNITY_SPACING_PX["xxs"],
                )
                category_label = QLabel(category)
                category_label.setObjectName("GuidePreparationSummaryTitle")
                row.addWidget(category_label)
                row.addStretch(1)
                ready_count = sum(1 for need in matching if self._need_ready(need))
                count_label = QLabel(f"{ready_count} / {len(matching)} prêts")
                count_label.setObjectName("GuidePreparationSummaryCount")
                row.addWidget(count_label)
                self.preparation_rows_layout.addWidget(summary)
                available = max(0, self._preparation_visible_limit - rendered_count)
                for need in matching[:available]:
                    self.preparation_rows_layout.addWidget(self._preparation_row(need))
                rendered_count += min(len(matching), available)
            self._append_preparation_more(
                len(self._preparation_needs) - rendered_count
            )
            self.preparation_rows_layout.addStretch(1)
            self._fit_preparation_scroll_height()
            return

        matching = [
            need for need in self._preparation_needs
            if self._preparation_matches_filter(
                need.category, need.name, selected_filter,
            )
        ]
        if not matching:
            label = QLabel(f"Aucun besoin détaillé dans {selected_filter}.")
            label.setObjectName("GuidePreparationEmpty")
            self.preparation_rows_layout.addWidget(label)
            self._fit_preparation_scroll_height()
            return
        for need in matching[:self._preparation_visible_limit]:
            self.preparation_rows_layout.addWidget(self._preparation_row(need))
        self._append_preparation_more(len(matching) - self._preparation_visible_limit)
        self.preparation_rows_layout.addStretch(1)
        self._fit_preparation_scroll_height()

    def _copyable_preparation_item(self, name: str, display: str,
                                   item_id: int | None) -> QPushButton:
        button = AtlasButton(display, size="compact")
        button.set_style_name("GuidePreparationItemCopy")
        # The indexed transparent-button QSS already removes its chrome;
        # Qt flat mode can suppress stylesheet text rendering on Windows.
        button.setFlat(False)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(f"Cliquer pour copier : {name}")
        button.setAccessibleName(f"Copier {name}")
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if item_id is not None:
            # Quest and Preparation use the same item -> iconId catalogue.
            # Sprite filenames are icon IDs, not necessarily database IDs.
            image_path = local_item_image_path(item_id)
            if image_path:
                icon_size = UNITY_CONTROL_SIZES_PX["guide_preparation_icon"]
                pixmap = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(
                    Path(image_path), QSize(icon_size, icon_size),
                )
                if not pixmap.isNull():
                    button.setIcon(QIcon(pixmap))
        # Missing IDs or missing shipped artwork are NOT the same inventory
        # object. Show no icon rather than a misleading generic backpack.
        button.setIconSize(QSize(UNITY_CONTROL_SIZES_PX["guide_preparation_icon"], UNITY_CONTROL_SIZES_PX["guide_preparation_icon"]))
        button.clicked.connect(lambda _checked=False, value=name:
                               QApplication.clipboard().setText(value))
        return button

    def _preparation_row(self, need: _PreparationNeed) -> QWidget:
        frame = QFrame()
        frame.setObjectName("GuidePreparationRow")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            UNITY_SPACING_PX["xs"], 0,
            UNITY_SPACING_PX["xs"], 0,
        )
        layout.setSpacing(UNITY_SPACING_PX["xxs"])
        top = QHBoxLayout()
        top.setSpacing(UNITY_SPACING_PX["xs"])
        ready = self._need_ready(need)
        confirmed = sum(
            1 for character_key, _quantity in need.required_by_character
            if callable(getattr(self.service, "manual_checked", None))
            and self.service.manual_checked(character_key, self._ready_progress_key(need))
        )
        total = len(need.required_by_character)
        quantity = need.required_total
        amount = (
            "" if need.category in {"Prérequis", "Métiers"}
            else f"{quantity} × " if quantity is not None else "? × "
        )
        status = "Prêt" if ready else f"{confirmed}/{total} prêts"
        item_button = self._copyable_preparation_item(
            need.name, need.name, need.item_id,
        )
        item_button.setToolTip("Cliquer pour copier le nom · " +
                               (" ; ".join(need.sources[:8]) or "Provenance à confirmer"))
        status_label = QLabel(status)
        status_label.setObjectName("GuidePreparationRowStatus")
        status_label.setProperty("ready", "true" if ready else "false")
        counter = None
        if quantity is not None and quantity > 0 and need.category not in {"Prérequis", "Métiers"}:
            counter = QSpinBox()
            counter.setObjectName("GuidePreparationQuantity")
            counter.setFixedHeight(UNITY_SIZES_PX["control_compact"])
            counter.setRange(0, max(1, int(quantity)))
            counter.setSuffix(f"/{quantity}")
            fit_unity_number_spinbox(counter)
            counter.setToolTip("Quantité déjà possédée (brouillon de cette session)")
            draft = self._preparation_quantity_drafts.get(
                need.item_key, int(quantity) if ready else 0
            )
            counter.setValue(max(0, min(int(quantity), draft)))
            counter.valueChanged.connect(
                lambda value, key=need.item_key:
                self._preparation_quantity_drafts.__setitem__(key, value)
            )
        ready_button = QCheckBox()
        ready_button.setObjectName("GuidePreparationReady")
        ready_button.setChecked(ready)
        ready_button.setToolTip("Confirmer Prêt pour les participants sélectionnés concernés")
        ready_button.setAccessibleName(f"Valider {need.name}")
        ready_button.setCursor(Qt.PointingHandCursor)
        if len(need.required_by_character) > 1 and not callable(
            getattr(getattr(self.service, "guide_progress", None),
                    "set_manual_steps_for_characters", None)
        ):
            ready_button.setEnabled(False)
            ready_button.setToolTip("Sauvegarde atomique indisponible")
        if counter is not None:
            # The stock counter is a session draft, not a saved proof of
            # preparation. Reflect its useful remaining count immediately,
            # but never check the saved Prêt box automatically.
            def update_stock_label(value: int) -> None:
                remaining = max(0, int(quantity) - int(value))
                if ready:
                    status_label.setText("Prêt")
                elif remaining:
                    # Show useful inventory shortage even for a whole team.
                    # Keep the saved per-character readiness detail in hover
                    # instead of stretching every row's compact layout.
                    status_label.setText(f"Manque {remaining}")
                elif total > 1 and confirmed:
                    status_label.setText(f"{confirmed}/{total} prêts")
                else:
                    status_label.setText("À valider")
                hint = (
                    f"Encore {remaining} à obtenir"
                    if remaining else "Quantité atteinte · coche Prêt pour confirmer"
                )
                if total > 1:
                    hint += f" · {confirmed}/{total} personnages prêts"
                status_label.setToolTip(hint)

            counter.valueChanged.connect(update_stock_label)
            update_stock_label(counter.value())
        ready_button.toggled.connect(
            lambda checked, row=need: self._preparation_quantity_drafts.__setitem__(
                row.item_key, int(row.required_total or 0) if checked else 0
            )
        )
        ready_button.toggled.connect(
            lambda checked, row=need: self._set_need_ready(row, checked)
        )
        # Same indexed row in every guide: ready | quantity | copyable name.
        ready_button.setFixedWidth(
            UNITY_CONTROL_SIZES_PX["guide_validation_width"]
        )
        top.addWidget(ready_button, 0, Qt.AlignVCenter)
        if counter is not None:
            top.addWidget(counter, 0, Qt.AlignVCenter)
        else:
            missing_quantity = QLabel("—")
            missing_quantity.setObjectName("GuidePreparationQuantityPlaceholder")
            missing_quantity.setFixedWidth(
                UNITY_CONTROL_SIZES_PX["guide_quantity_width"]
            )
            missing_quantity.setAlignment(Qt.AlignCenter)
            top.addWidget(missing_quantity, 0, Qt.AlignVCenter)
        top.addWidget(item_button, 1, Qt.AlignVCenter)
        top.addWidget(status_label, 0, Qt.AlignVCenter)
        details_button = QToolButton()
        details_button.setObjectName("GuidePreparationDetailsButton")
        details_button.setArrowType(Qt.RightArrow)
        details_button.setCheckable(True)
        top.addWidget(details_button)
        layout.addLayout(top)
        details = QFrame()
        details.setObjectName("GuidePreparationDetails")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(8, 2, 8, 3)
        details_layout.setSpacing(2)
        # Most preparation rows stay collapsed. The previous implementation
        # fetched all character labels and constructed a QLabel per participant
        # for EVERY need, even if the user never opened its details.
        # Populate on the first expansion only, preserving copy/ready actions.
        def populate_details(opened: bool) -> None:
            if not opened or details_layout.count():
                return
            labels_by_key = {
                character.key: character.label
                for character in self.participant_service.available_characters()
            }
            for character_key, quantity in need.required_by_character:
                detail = QLabel(
                    f"{labels_by_key.get(character_key, character_key)} : "
                    f"besoin {quantity if quantity is not None else 'à confirmer'}"
                )
                detail.setObjectName("GuidePreparationParticipantNeed")
                details_layout.addWidget(detail)

        details.setVisible(False)
        details_button.toggled.connect(populate_details)
        details_button.toggled.connect(details.setVisible)
        details_button.toggled.connect(
            lambda opened, button=details_button: button.setArrowType(
                Qt.DownArrow if opened else Qt.RightArrow
            )
        )
        layout.addWidget(details)
        return frame

    def _update_preparation_progress(self) -> None:
        total = len(self._preparation_needs)
        ready = sum(1 for need in self._preparation_needs if self._need_ready(need))
        self.preparation_bar.setRange(0, max(1, total))
        self.preparation_bar.setValue(ready)
        self.preparation_progress_label.setText(
            f"{max(0, min(100, round(ready * 100 / total)))} %" if total else "—"
        )

    def _participant_toggled(self, character_key: str, checked: bool) -> None:
        selected = list(self.selected_participant_keys())
        if checked and character_key not in selected:
            selected.append(character_key)
        elif not checked:
            selected = [key for key in selected if key != character_key]
        self.participant_service.save_selected_keys(selected)
        self._sync_compact_action_labels()
        self._preparation_loaded = False
        self._preparation_needs = ()
        # Counts belong to the previous team composition, not the new one.
        # Keep quantity drafts session-local but never apply the old team's
        # stock to a different participant selection.
        self._preparation_quantity_drafts.clear()
        self._preparation_visible_limit = 80
        if self.preparation_button.isChecked():
            self._load_preparation_needs()
            self._render_preparation(self.preparation_filter.currentText())
        self._refresh_header()
        # Selection changes must immediately replace the live Valider control.
        self._render_window()

    def _actual_index_for_participants(self) -> int | None:
        keys = self._progress_participant_keys()
        if not keys or not self.service.cards:
            return None
        indexes: list[int] = []
        for character_key in keys:
            try:
                done, total = self.service.route_sheet_progress(character_key)
                if total <= 0:
                    return None  # Unknown route: do not invent a current sheet.
                if done >= total:
                    continue  # All sheets completed: no phantom final-sheet target.
                indexes.append(int(self.service.first_incomplete_index(character_key)))
            except (AttributeError, KeyError, TypeError, ValueError):
                return None
        return max(0, min(len(self.service.cards) - 1, min(indexes))) if indexes else None

    def refresh(self, *, reset_to_active: bool = False) -> None:
        self.service.reload_progress()
        if self._participant_source_signature() != getattr(
            self, "_last_participant_source_signature", None
        ):
            self._refresh_participants_panel()
        else:
            self._refresh_participant_progress()
        if not self.service.available:
            self._render_missing_data()
            return
        actual_index = self._actual_index_for_participants()
        if actual_index is not None:
            self.active_index = actual_index
            if reset_to_active or not (0 <= self.view_index < len(self.service.cards)):
                self.view_index = actual_index
        self._preparation_loaded = False
        self._preparation_needs = ()
        self._sync_order_combo()
        self._refresh_header()
        self._render_window()

    def go_active(self) -> None:
        index = self._actual_index_for_participants()
        if index is None:
            return
        self.active_index = index
        self._show_index(index)

    def _follow_active_after_progress_change(self) -> None:
        previous = self.active_index
        # Every progress edit can change the remaining inventory, including
        # the *final* sheet completion where there is no next active index.
        # Invalidate before the end-of-route branch so an open À préparer
        # drawer never keeps requirements from a finished route.
        self._preparation_loaded = False
        self._preparation_needs = ()
        actual_index = self._actual_index_for_participants()
        if actual_index is None:
            # End-of-route and empty-selection transitions must replace the
            # live validation button, not keep its previous checked/label state.
            self._refresh_participants_panel()
            self._refresh_header()
            self._render_window()
            return
        self.active_index = actual_index
        moved = self.view_index == previous and actual_index != previous
        if moved:
            self.view_index = actual_index
        self._refresh_participants_panel()
        self._refresh_header()
        self._render_window(reset_scroll=moved)

    @staticmethod
    def _common_sheet_count(keys, cards, is_complete) -> int:
        """Count sheet identities completed by ALL selected characters."""
        return sum(
            1 for index, card in enumerate(cards)
            if all(is_complete(key, card, index) for key in keys)
        )

    def _refresh_header(self) -> None:
        keys = self._progress_participant_keys()
        progress_rows: list[tuple[int, int]] = []
        for character_key in keys:
            try:
                progress_rows.append(self.service.route_sheet_progress(character_key))
            except (AttributeError, KeyError, TypeError, ValueError):
                progress_rows = []
                break
        if progress_rows and all(total > 0 for _completed, total in progress_rows):
            total = max(total for _completed, total in progress_rows)
            # Common progress is the intersection of completed sheet IDs.
            # The minimum of two counts is not evidence of shared completion.
            if len(keys) > 1:
                completed = self._common_sheet_count(
                    keys, self.service.cards, self._card_complete,
                )
            else:
                completed = min(done for done, _total in progress_rows)
            percent = min(100, round(completed * 100 / total)) if total > 0 else None
            self.progress_donut.set_percent(percent)
            self.global_progress_bar.setRange(0, max(1, total))
            self.global_progress_bar.setValue(completed)
            self.global_progress_label.setText(f"{percent} %")
            self.donut_count_label.setText(f"{completed} fiches validées")
        else:
            self.progress_donut.set_percent(None)
            self.global_progress_bar.setRange(0, 1)
            self.global_progress_bar.setValue(0)
            self.global_progress_label.setText("—")
            self.donut_count_label.setText("Fiches à valider")

        # An already open preparation drawer must be refreshed alongside its
        # progress bar after a quest, participant or external progress change.
        # Otherwise the header displays 0 while stale prepared rows remain.
        if (
            self.global_details_button.isChecked()
            and self.preparation_button.isChecked()
            and not self._preparation_loaded
        ):
            self._load_preparation_needs()
            self._render_preparation(self.preparation_filter.currentText())
        else:
            self._update_preparation_progress()
        if self.global_details_panel.isVisible():
            self._refresh_global_details()

        total_cards = len(self.service.cards)
        index = max(0, min(self.view_index, max(0, total_cards - 1)))
        card = self.service.cards[index] if total_cards else {}
        title = str(card.get("manual_title") or card.get("destination") or "Fiche").strip()
        self.sheet_title_label.setText(title)
        self.nav_page_label.setText(f"{index + 1}/{total_cards}")
        self.page_jump.blockSignals(True)
        self.page_jump.setRange(1, max(1, total_cards))
        self.page_jump.setSuffix(f"/{total_cards}")
        fit_unity_number_spinbox(self.page_jump)
        self.page_jump.setValue(index + 1)
        self.page_jump.blockSignals(False)

    def set_character_key(self, character_key: str) -> None:
        # The base setter invokes refresh() synchronously. Invalidate the
        # previous browsing context BEFORE it redraws the open preparation;
        # otherwise it briefly restores stale quantities, then clears the
        # model while leaving those stale widgets visible.
        if (character_key or "") != self.character_key:
            self._preparation_quantity_drafts.clear()
            self._preparation_loaded = False
            self._preparation_needs = ()
        super().set_character_key(character_key)
        self._refresh_participants_panel()

    def _validation_status(self, card: dict[str, Any], index: int):
        keys = self._progress_participant_keys()
        statuses = []
        for key in keys:
            automatic = bool(self.service.card_auto_complete(key, card))
            manual = bool(self.service.page_checked(key, card, index))
            blocking = getattr(self.service, "manual_order_choice_blocking", None)
            blocked = bool(callable(blocking) and blocking(key, card))
            statuses.append((key, automatic, manual, blocked))
        return statuses

    def _sync_validation_control(self, button: QPushButton, card: dict[str, Any], index: int) -> None:
        statuses = self._validation_status(card, index)
        all_done = bool(statuses) and all(auto or manual for _, auto, manual, _ in statuses)
        blocked = any(blocked and not (auto or manual) for _, auto, manual, blocked in statuses)
        reversible = any(manual for _, _, manual, _ in statuses)
        batcher = getattr(getattr(self.service, "guide_progress", None), "set_manual_steps_for_characters", None)
        page_key = getattr(self.service, "page_key", None)
        enabled = (not statuses) or (bool(statuses) and callable(batcher) and callable(page_key)
                                   and not blocked and (not all_done or reversible))
        if not statuses:
            label, hint = "Valider", "Choisissez d'abord un personnage avec le bouton portrait ; ce clic ouvre le sélecteur."
        elif blocked:
            label, hint = "Choisir l’ordre", "Une fiche de la sélection est bloquée : terminez le choix d’ordre avant de valider."
        elif all_done and reversible:
            label, hint = "Valider", "Retirer uniquement les coches manuelles ; les preuves automatiques sont conservées."
        elif all_done:
            label, hint = "Valider", "Fiche déjà validée automatiquement pour tous les personnages sélectionnés."
        else:
            label, hint = "Valider", "Valider la fiche pour les personnages sélectionnés qui en ont besoin."
        if statuses and (not callable(batcher) or not callable(page_key)):
            hint = "Sauvegarde multi-personnages indisponible : aucune écriture autorisée."
        button.blockSignals(True)
        try:
            button.setChecked(all_done)
            button.setText(label)
            button.setEnabled(enabled)
            button.setToolTip(hint)
        finally:
            button.blockSignals(False)

    def _page_toggled_for_participants(self, card: dict[str, Any], index: int, checked: bool) -> None:
        # Ignore deferred signals from an old card after navigation.
        if index != self.view_index or index >= len(self.service.cards) or self.service.cards[index] is not card:
            return
        self.service.reload_progress()
        statuses = self._validation_status(card, index)
        all_done = bool(statuses) and all(auto or manual for _, auto, manual, _ in statuses)
        blocked = any(blocked and not (auto or manual) for _, auto, manual, blocked in statuses)
        if not statuses:
            # A visible "Valider" must never silently write to the browsing
            # character. Open the explicit portrait selector on first click.
            self.participants_button.setChecked(True)
            self._render_window()
            return
        if blocked or checked == all_done:
            self._render_window()
            return
        # A mixed team click fills only incomplete manual states; undo removes
        # only manually checked states without erasing quest/success evidence.
        targets = (
            tuple(key for key, auto, manual, _ in statuses if not auto and not manual)
            if checked else tuple(key for key, _, manual, _ in statuses if manual)
        )
        batcher = getattr(getattr(self.service, "guide_progress", None), "set_manual_steps_for_characters", None)
        page_key = getattr(self.service, "page_key", None)
        if not targets or not callable(batcher) or not callable(page_key):
            self._render_window()
            return
        from app.modules.encyclopedia.services.guide_ultime_generated_service import GUIDE_ULTIME_PROGRESS_ID
        progress_id = str(getattr(self.service, "progress_id", None) or GUIDE_ULTIME_PROGRESS_ID)
        try:
            batcher(
                targets, progress_id, page_key(card, index), checked,
                expected_completed={key: manual for key, _, manual, _ in statuses if key in targets},
            )
        except RuntimeError:
            # Another instance updated the same page after we read its state.
            # The compare-and-swap service rejects the entire stale batch.
            self.validation_host.setToolTip("Progression modifiée ailleurs ; l’état a été rechargé.")
        finally:
            self._follow_active_after_progress_change()

    def _add_manual_order_choice(self, card: dict[str, Any]) -> None:
        # Order selection is per character and can be irreversible. Unlike
        # ordinary page validation, never write an unselected browsing
        # character's Order or apply one click to multiple profiles.
        keys = self._progress_participant_keys()
        required = getattr(self.service, "manual_order_choice_required", None)
        if not callable(required) or not any(required(key, card) for key in keys):
            return
        if len(keys) != 1:
            notice = QFrame()
            notice.setObjectName("GuideManualOrderChoice")
            layout = QVBoxLayout(notice)
            layout.setContentsMargins(14, 11, 14, 11)
            label = QLabel(
                "Choisis un seul personnage dans le sélecteur pour définir son Ordre Bonta."
            )
            label.setObjectName("GuideManualOrderDetail")
            label.setWordWrap(True)
            layout.addWidget(label)
            self.cards_layout.addWidget(notice)
            return
        super()._add_manual_order_choice(card, character_key=keys[0])

    def _select_manual_order(
        self, order_name: str, character_key: str | None = None,
    ) -> None:
        keys = self._progress_participant_keys()
        if len(keys) != 1 or character_key != keys[0]:
            return
        self.service.set_bonta_order(character_key, order_name)
        self._follow_active_after_progress_change()

    def _render_window(self, *, reset_scroll: bool = False) -> None:
        self._catalog_prefetch_timer.stop()
        self._catalog_prefetch_index = None
        self._clear_cards()
        if not self.service.cards:
            return
        index = max(0, min(self.view_index, len(self.service.cards) - 1))
        card = self.service.cards[index]
        self._add_manual_order_choice(card)
        widget = SharedGuideManualCard(
            self.service,
            self.character_key,
            card,
            index,
            travel_command_callback=(
                self._launch_travel_command
                if callable(self.travel_callback)
                else None
            ),
            show_header_title=False,
            page_validation_callback=lambda checked, sheet=card, sheet_index=index: (
                self._page_toggled_for_participants(sheet, sheet_index, bool(checked))
            ),
        )
        self._sync_validation_control(widget.page_check, card, index)
        widget.questRequested.connect(self._open_quest_from_card)
        self._set_validation_widget(widget.page_check)
        self.cards_layout.addWidget(widget)
        self.cards_layout.addStretch(1)
        self.rendered_card_count = 1
        # Schedule neighbor disk reads after the visible Qt sheet is ready.
        # Never read nine SQLite bodies synchronously during _render_window.
        if callable(getattr(self.service, "prefetch_route_near", None)):
            self._catalog_prefetch_index = index
            self._catalog_prefetch_timer.start()
        self.prev_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < len(self.service.cards) - 1)
        self.guide_button.setToolTip(
            "Revenir à la fiche Guide active."
            if index != self.active_index
            else "Retour au choix des Guides."
        )
        if reset_scroll:
            self._reset_scroll_to_top()

    def _prefetch_catalog_slice(self) -> None:
        """Allow event processing between adjacent catalog-detail reads."""
        index = self._catalog_prefetch_index
        prefetch = getattr(self.service, "prefetch_route_near", None)
        if index is None or not callable(prefetch) or index != self.view_index:
            self._catalog_prefetch_timer.stop()
            return
        if not prefetch(index, max_reads=1):
            self._catalog_prefetch_timer.stop()

    def _open_quest_from_card(self, quest_id: int, stage_id: str, index: int) -> None:
        navigator = self.navigate_entity
        if not callable(navigator):
            return
        guide_id = str(getattr(self.service, "guide_id", "") or "guide_complet")
        navigator(
            "quest",
            int(quest_id),
            source="guide_gps",
            guide_id=guide_id,
            guide_stage_id=str(stage_id or ""),
            guide_index=int(index),
        )


__all__ = ["SharedGuideManualCard", "SharedGuideManualView"]
