from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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

from app.modules.encyclopedia.services.guide_quest_view_model import quest_solution_steps
from app.modules.encyclopedia.views.guide_ultime_manual_view import (
    GuideManualProgressBar,
    GuideUltimeManualCard,
    GuideUltimeManualView,
)
from app.core.text import normalize_key as normalize_text
from app.ui.components import AtlasButton
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
    """Draw small semantic icons without font glyph or platform-theme drift."""

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color or PALETTE["TEXT_SOFT"]), 1.6)
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
        self.setFixedSize(42, 42)
        self.setIconSize(QSize(32, 32))
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = (
            self.palette().highlight().color()
            if self.isChecked()
            else self.palette().mid().color()
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
            label = "Validé ✓"
        else:
            label = "Valider"
        self.page_check = QPushButton(label)
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
            if isinstance(row, dict) and str(row.get("text") or "").strip()
        ]
        if not visible:
            return

        frame = QFrame()
        frame.setObjectName(
            "GuideManualWarningSection" if section_key == "prepare" else object_name
        )
        if section_key == "boss":
            frame.setStyleSheet(
                "QFrame#GuideManualCombatSection {"
                "background: rgba(174, 183, 177, 0.035);"
                "border: 1px solid rgba(174, 183, 177, 0.16);"
                "border-radius: 6px;"
                "}"
            )
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
        for row_index, row in enumerate(visible):
            text = str(row.get("text") or "").strip()
            position = self._display_position(str(row.get("position") or ""))
            kind = str(row.get("kind") or "")
            prefix = "⚠ " if kind == "warning" else "• "
            combat_line = self._is_combat_row(kind, text)

            row_widget = QFrame()
            row_widget.setObjectName("GuideManualLineRow")
            if section_key == "prepare":
                row_widget.setStyleSheet(
                    "QFrame#GuideManualLineRow { background: transparent; border: none; }"
                )
            elif combat_line:
                row_widget.setStyleSheet(
                    "QFrame#GuideManualLineRow {"
                    "background: rgba(174, 183, 177, 0.045);"
                    "border: 1px solid rgba(174, 183, 177, 0.14);"
                    "border-radius: 4px;"
                    "}"
                )
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(7)

            line = QLabel()
            self._set_clickable_text(
                line,
                self._format_line_html(
                    prefix,
                    position,
                    text,
                    self._npc_names(text),
                    self._resource_names,
                ),
            )
            if section_key == "prepare":
                line.setObjectName("GuideManualLine")
                line.setStyleSheet(
                    "QLabel#GuideManualLine { background: transparent; border: none; padding: 2px 0; }"
                )
            elif combat_line:
                line.setObjectName("GuideManualCombatInlineText")
                line.setStyleSheet(
                    "QLabel#GuideManualCombatInlineText {"
                    "background: transparent; border: none; padding: 5px 7px;"
                    "}"
                )
            else:
                line.setObjectName(self._line_object_name(kind, text))
            line.setWordWrap(True)
            quest_names = {
                quest_id: name for quest_id, name in self._quest_rows
            }
            related_names = [
                quest_names[quest_id]
                for quest_id in self._quest_ids_for_row(row)
                if quest_id in quest_names
            ]
            if related_names:
                line.setToolTip("Quête : " + " · ".join(related_names))
            row_layout.addWidget(line, 1)
            if section_key == "now":
                self._add_inline_quest_links(row_layout, row)

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

        root.addWidget(frame)

    @staticmethod
    def _combat_key(target: dict[str, Any]) -> tuple[int, int]:
        return int(target["quest_id"]), int(target["objective_id"])

    def _combat_evidence(self, target: dict[str, Any]) -> tuple[str, str]:
        key = self._combat_key(target)
        cached = self._combat_evidence_cache.get(key)
        if cached is not None:
            return cached

        position = ""
        objective_text = ""
        provider = getattr(self.service, "quest_provider", None)
        getter = getattr(provider, "get_quest", None)
        if callable(getter):
            try:
                quest = getter(key[0])
            except (KeyError, LookupError, TypeError, ValueError):
                quest = None
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

        direct: list[dict[str, Any]] = []
        same_position: list[dict[str, Any]] = []
        for target in unseen:
            target_position, objective_text = self._combat_evidence(target)
            if self._combat_text_matches(
                row_text,
                target.get("monster"),
                objective_text,
            ):
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

        provider = getattr(self.service, "quest_provider", None)
        getter = getattr(provider, "get_quest", None)
        if not callable(getter):
            return []

        row_position = self._position_key(str(row.get("position") or ""))
        candidates: list[tuple[dict[str, Any], str, str, str]] = []
        seen: set[tuple[int, int]] = set()
        for raw in self.card.get("manual_quest_ids", []) or []:
            try:
                quest_id = int(raw)
                quest = getter(quest_id)
            except (KeyError, LookupError, TypeError, ValueError):
                continue
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
        row.setStyleSheet(
            "QFrame#GuideManualCombatInlineRow {"
            "background: rgba(174, 183, 177, 0.055);"
            "border: 1px solid rgba(174, 183, 177, 0.18);"
            "border-radius: 4px;"
            "}"
        )
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
        checkbox.setStyleSheet(
            "QCheckBox#GuideManualCombatCheck { background: transparent; border: none; }"
        )
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

    ROUTE_LOCK_PROGRESS_KEY = "__ui:shared_route_locked__"

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
        self._preparation_preview: tuple[tuple[str, str, int], ...] = ()
        self._preparation_loaded = False
        self._preparation_visible_limit = 80
        self._participant_buttons: dict[str, _ParticipantPortraitButton] = {}
        root = QVBoxLayout(self)
        # Qt's default layout minimum otherwise forces the guide wider than
        # the available viewport, preventing the compact labels from activating.
        root.setSizeConstraint(QLayout.SetNoConstraint)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._build_compact_header(root)
        self._build_preparation_panel(root)
        self._build_sheet_header(root)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("GuideManualScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget()
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
        self.prev_button = QPushButton("Précédent")
        self.prev_button.setObjectName("GuideManualPrev")
        self.prev_button.setIcon(
            self.prev_button.style().standardIcon(QStyle.SP_ArrowBack)
        )
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
        self.next_button = QPushButton("Suivant")
        self.next_button.setObjectName("GuideManualNextButton")
        self.next_button.setIcon(
            self.next_button.style().standardIcon(QStyle.SP_ArrowForward)
        )
        self.next_button.clicked.connect(lambda: self.navigate_relative(1))
        nav_layout.addWidget(self.next_button)
        root.addWidget(nav)

        self.progress_details = QLabel()
        self.progress_details.setVisible(False)
        self.position_label = QLabel()
        self.position_label.setVisible(False)
        self._restore_route_lock_state()

    def _build_compact_header(self, root: QVBoxLayout) -> None:
        """One left donut, three horizontally expanding metrics, three real panel controls."""
        header = QFrame()
        header.setObjectName("GuideCompactHeader")
        outer = QHBoxLayout(header)
        outer.setContentsMargins(10, 6, 10, 7)
        outer.setSpacing(10)

        self.progress_donut = _GuideProgressDonut()
        outer.addWidget(self.progress_donut, 0, Qt.AlignVCenter)

        right = QVBoxLayout()
        right.setSpacing(6)
        outer.addLayout(right, 1)

        # Row 1: active guide, instant sheet selector and compact commands.
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.guide_button = AtlasButton("←")
        self.guide_button.setObjectName("GuideManualGuideButton")
        self.guide_button.setToolTip("Revenir à la fiche actuelle, puis au catalogue des guides")
        self.guide_button.setAccessibleName("Fiche actuelle ou catalogue des guides")
        self.guide_button.setMaximumWidth(35)
        self.guide_button.clicked.connect(
            lambda _checked=False: self._guide_button_clicked()
        )
        title_row.addWidget(self.guide_button)
        guide_icon = QLabel()
        guide_icon.setObjectName("GuideCompactTitleIcon")
        guide_symbol = "trophy" if "succès" in self._guide_title().casefold() else "guide"
        guide_icon.setPixmap(_guide_symbol_icon(guide_icon, guide_symbol, size=16).pixmap(16, 16))
        guide_icon.setFixedSize(16, 16)
        title_row.addWidget(guide_icon)
        self.guide_title_label = QLabel(self._guide_title())
        self.guide_title_label.setObjectName("GuideCompactTitle")
        self.guide_title_label.setMinimumWidth(0)
        self.guide_title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.guide_title_label.setToolTip(self._guide_title())
        title_row.addWidget(self.guide_title_label, 1)

        self.page_jump = QSpinBox()
        self.page_jump.setObjectName("GuideCompactPageJump")
        self.page_jump.setPrefix("Fiche ")
        self.page_jump.setRange(1, max(1, len(self.service.cards)))
        self.page_jump.setMaximumWidth(115)
        self.page_jump.setToolTip("Ouvrir directement la fiche sélectionnée")
        self.page_jump.valueChanged.connect(
            lambda value: self._show_index(value - 1)
        )
        title_row.addWidget(self.page_jump)
        self.current_button = QPushButton("Actuelle")
        self.current_button.setObjectName("GuideCompactCurrentButton")
        self.current_button.setIcon(_guide_symbol_icon(self.current_button, "current"))
        self.current_button.clicked.connect(self.go_active)
        title_row.addWidget(self.current_button)
        # Compatibility-only sheet position; sheet title appears once below.
        self.nav_page_label = QLabel(self)
        self.nav_page_label.setObjectName("GuideManualNavPage")
        self.nav_page_label.setVisible(False)
        self.overlay_button = QToolButton()
        self.overlay_button.setObjectName("GuideCompactOverlayButton")
        self.overlay_button.setIcon(_guide_symbol_icon(self.overlay_button, "map"))
        self.overlay_button.setIconSize(QSize(16, 16))
        self.overlay_button.setToolTip("Overlay indisponible dans ce runtime")
        self.overlay_button.setAccessibleName("Overlay")
        self.overlay_button.setEnabled(False)
        title_row.addWidget(self.overlay_button)
        self.settings_button = QToolButton()
        self.settings_button.setObjectName("GuideCompactSettingsButton")
        self.settings_button.setIcon(_guide_symbol_icon(self.settings_button, "settings"))
        self.settings_button.setIconSize(QSize(16, 16))
        self.settings_button.setToolTip("Paramètres du Guide")
        self.settings_button.setAccessibleName("Paramètres du Guide")
        self.settings_button.setCheckable(True)
        title_row.addWidget(self.settings_button)
        right.addLayout(title_row)

        # Row 2: THREE horizontal, equal-width blocks (never vertical stack).
        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self._metric_caption_labels: dict[str, QLabel] = {}
        def add_metric(
            name: str, symbol: str, color_key: str, bar: QProgressBar, value: QLabel
        ) -> None:
            block = QVBoxLayout()
            block.setSpacing(2)
            caption = QHBoxLayout()
            caption.setSpacing(4)
            icon = QLabel()
            icon.setObjectName(f"GuideCompactMetricIcon{symbol.title()}")
            icon.setPixmap(
                _guide_symbol_icon(icon, symbol, size=16, color=PALETTE[color_key]).pixmap(16, 16)
            )
            icon.setFixedSize(16, 16)
            caption.addWidget(icon)
            caption_label = QLabel(name)
            caption_label.setToolTip(name)
            caption_label.setMinimumWidth(0)
            self._metric_caption_labels[name] = caption_label
            caption.addWidget(caption_label)
            caption.addStretch(1)
            value.setObjectName("GuideCompactMetricValue")
            caption.addWidget(value)
            block.addLayout(caption)
            bar.setTextVisible(False)
            bar.setFixedHeight(7)
            block.addWidget(bar)
            metrics.addLayout(block, 1)

        self.route_bar = GuideManualProgressBar()
        self.route_bar.setObjectName("GuideManualProgress")
        self.route_bar.setCursor(Qt.PointingHandCursor)
        self.route_bar.navigationRequested.connect(self._jump_from_progress)
        self.route_progress_label = QLabel("—")
        add_metric("Route", "target", "RED", self.route_bar, self.route_progress_label)

        self.preparation_bar = QProgressBar()
        self.preparation_bar.setObjectName("GuideCompactPreparationProgress")
        self.preparation_progress_label = QLabel("—")
        add_metric("Préparation", "cube", "GREEN", self.preparation_bar, self.preparation_progress_label)

        self.success_bar = QProgressBar()
        self.success_bar.setObjectName("GuideCompactSuccessProgress")
        self.success_progress_label = QLabel("—")
        add_metric("Succès", "trophy", "YELLOW", self.success_bar, self.success_progress_label)
        right.addLayout(metrics)

        # Row 3: populated by the existing preparation, summary and participant
        # builders. Their original panels/signals remain owned by those builders.
        self.header_actions_row = QHBoxLayout()
        self.header_actions_row.setSpacing(7)
        right.addLayout(self.header_actions_row)

        self.settings_panel = QFrame()
        self.settings_panel.setObjectName("GuideCompactSettingsPanel")
        settings_layout = QHBoxLayout(self.settings_panel)
        settings_layout.setContentsMargins(8, 5, 8, 5)
        self.route_lock_check = QToolButton()
        self.route_lock_check.setObjectName("GuideManualProgressLock")
        self.route_lock_check.setCheckable(True)
        self.route_lock_check.setCursor(Qt.PointingHandCursor)
        self.route_lock_check.toggled.connect(self._route_lock_toggled)
        settings_layout.addWidget(self.route_lock_check)
        settings_layout.addStretch(1)
        self.settings_panel.setVisible(False)
        self.settings_button.toggled.connect(self.settings_panel.setVisible)
        right.addWidget(self.settings_panel)
        root.addWidget(header)

    def _build_preparation_panel(self, root: QVBoxLayout) -> None:
        self.preparation_button = QToolButton()
        self.preparation_button.setObjectName("GuidePreparationToggle")
        self.preparation_button.setText("Préparation")
        self.preparation_button.setIcon(
            _guide_symbol_icon(self.preparation_button, "clipboard")
        )
        self.preparation_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.preparation_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.preparation_button.setMinimumHeight(32)
        self.preparation_button.setArrowType(Qt.RightArrow)
        self.preparation_button.setCheckable(True)
        self.preparation_button.setCursor(Qt.PointingHandCursor)
        self.preparation_button.toggled.connect(self._preparation_toggled)
        self.header_actions_row.addWidget(self.preparation_button, 1)

        self.preparation_panel = QFrame()
        self.preparation_panel.setObjectName("GuidePreparationPanel")
        panel_layout = QVBoxLayout(self.preparation_panel)
        panel_layout.setContentsMargins(10, 8, 10, 9)
        panel_layout.setSpacing(7)
        filters = QHBoxLayout()
        filters.setSpacing(5)
        self.preparation_filter_group = QButtonGroup(self)
        self.preparation_filter_group.setExclusive(True)
        for label in ("Tout", "Prérequis", "Métiers", "Potions", "Pierres d'âme", "Clefs", "Objets"):
            button = QPushButton(label)
            button.setObjectName("GuidePreparationFilter")
            button.setCheckable(True)
            button.setProperty("filterKey", label)
            button.setChecked(label == "Tout")
            self.preparation_filter_group.addButton(button)
            button.clicked.connect(
                lambda _checked=False, value=label: self._render_preparation(value)
            )
            filters.addWidget(button)
        filters.addStretch(1)
        panel_layout.addLayout(filters)

        self.preparation_scroll = QScrollArea()
        self.preparation_scroll.setObjectName("GuidePreparationScroll")
        self.preparation_scroll.setWidgetResizable(True)
        self.preparation_scroll.setFrameShape(QFrame.NoFrame)
        self.preparation_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preparation_scroll.setMinimumHeight(126)
        self.preparation_scroll.setMaximumHeight(210)
        self.preparation_content = QWidget()
        self.preparation_rows_layout = QVBoxLayout(self.preparation_content)
        self.preparation_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.preparation_rows_layout.setSpacing(4)
        self.preparation_scroll.setWidget(self.preparation_content)
        panel_layout.addWidget(self.preparation_scroll)
        self.preparation_panel.setVisible(False)
        root.addWidget(self.preparation_panel)

    def _build_sheet_header(self, root: QVBoxLayout) -> None:
        header = QFrame()
        header.setObjectName("GuideSheetHeader")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(7)
        labels = QVBoxLayout()
        labels.setSpacing(1)
        self.sheet_meta_label = QLabel()
        self.sheet_meta_label.setObjectName("GuideSheetMeta")
        labels.addWidget(self.sheet_meta_label)
        self.sheet_title_label = QLabel()
        self.sheet_title_label.setObjectName("GuideSheetTitle")
        self.sheet_title_label.setWordWrap(True)
        labels.addWidget(self.sheet_title_label)
        top.addLayout(labels, 1)

        self.participants_button = QToolButton()
        self.participants_button.setObjectName("GuideParticipantsButton")
        self.participants_button.setText("Mes personnages")
        self.participants_button.setIcon(
            _guide_symbol_icon(self.participants_button, "people")
        )
        self.participants_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.participants_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.participants_button.setMinimumHeight(32)
        self.participants_button.setCheckable(True)
        self.participants_button.setCursor(Qt.PointingHandCursor)
        self.summary_button = QToolButton()
        self.summary_button.setObjectName("GuideSummaryButton")
        self.summary_button.setText("Sommaire")
        self.summary_button.setIcon(_guide_symbol_icon(self.summary_button, "summary"))
        self.summary_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.summary_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.summary_button.setMinimumHeight(32)
        self.summary_button.setArrowType(Qt.RightArrow)
        self.summary_button.setCheckable(True)
        self.summary_button.setCursor(Qt.PointingHandCursor)
        self.header_actions_row.addWidget(self.summary_button, 1)
        self.header_actions_row.addWidget(self.participants_button, 1)
        layout.addLayout(top)

        self.participants_panel = QFrame()
        self.participants_panel.setObjectName("GuideParticipantsPanel")
        self.participants_layout = QHBoxLayout(self.participants_panel)
        self.participants_layout.setContentsMargins(7, 5, 7, 5)
        self.participants_layout.setSpacing(5)
        self.participants_panel.setVisible(False)
        self.participants_button.toggled.connect(self.participants_panel.setVisible)
        layout.addWidget(self.participants_panel)

        self.summary_panel = QFrame()
        self.summary_panel.setObjectName("GuideSummaryPanel")
        summary_layout = QVBoxLayout(self.summary_panel)
        summary_layout.setContentsMargins(7, 5, 7, 5)
        summary_layout.setSpacing(5)
        self.summary_search = QLineEdit()
        self.summary_search.setObjectName("GuideSummarySearch")
        self.summary_search.setPlaceholderText("Rechercher une fiche…")
        self.summary_search.textChanged.connect(self._filter_summary)
        summary_layout.addWidget(self.summary_search)
        self.summary_list = QListWidget()
        self.summary_list.setObjectName("GuideSummaryList")
        self.summary_list.setUniformItemSizes(True)
        self.summary_list.setMaximumHeight(190)
        self.summary_list.itemClicked.connect(self._summary_item_clicked)
        summary_layout.addWidget(self.summary_list)
        self.summary_panel.setVisible(False)
        self.summary_button.toggled.connect(self._summary_toggled)
        layout.addWidget(self.summary_panel)
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
        narrow = self.width() < 520
        self.participants_button.setText(str(count) if narrow else full_label)
        for name, label in getattr(self, "_metric_caption_labels", {}).items():
            label.setText("Prép." if narrow and name == "Préparation" else name)
        self.participants_button.setAccessibleName(full_label)
        self.participants_button.setToolTip(
            "Choisir les identités stables utilisées par la progression et les déplacements."
        )
        if hasattr(self, "current_button"):
            current_label = str(self.current_button.property("guideFullText") or "Actuelle")
            self.current_button.setText("" if narrow else current_label)
            self.current_button.setAccessibleName(current_label)
            self.current_button.setToolTip(
                "Revenir à la fiche actuelle" if current_label == "Actuelle"
                else "Toutes les fiches sont terminées."
            ) if narrow else None
            self.page_jump.setMaximumWidth(93 if narrow else 115)

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
                    button.style().standardIcon(QStyle.SP_DirHomeIcon)
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

    def _summary_toggled(self, opened: bool) -> None:
        self.summary_panel.setVisible(bool(opened))
        self.summary_button.setArrowType(
            Qt.DownArrow if opened else Qt.RightArrow
        )
        if opened and self.summary_list.count() == 0:
            self._populate_summary()

    def _populate_summary(self) -> None:
        self.summary_list.clear()
        for index, card in enumerate(self.service.cards):
            chapter = str(card.get("manual_chapter_label") or "").strip()
            title = str(card.get("manual_title") or card.get("destination") or "").strip()
            label = f"{index + 1}. {chapter} — {title}" if chapter else f"{index + 1}. {title}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, index)
            self.summary_list.addItem(item)
        # Rebuilding the model must not silently discard the active search.
        self._filter_summary(self.summary_search.text())

    def _filter_summary(self, value: str) -> None:
        needle = normalize_text(value)
        for index in range(self.summary_list.count()):
            item = self.summary_list.item(index)
            item.setHidden(bool(needle and needle not in normalize_text(item.text())))

    def _summary_item_clicked(self, item: QListWidgetItem) -> None:
        try:
            index = int(item.data(Qt.UserRole))
        except (TypeError, ValueError):
            return
        self._show_index(index)
        # The summary is deliberately sticky. Only an explicit click on the
        # Sommaire button may close it.

    def _preparation_toggled(self, opened: bool) -> None:
        self.preparation_button.setArrowType(
            Qt.DownArrow if opened else Qt.RightArrow
        )
        self.preparation_panel.setVisible(bool(opened))
        if not opened:
            return
        if not self._preparation_loaded:
            self._load_preparation_needs()
        checked = self.preparation_filter_group.checkedButton()
        self._render_preparation(
            str(checked.property("filterKey") if checked is not None else "Tout")
        )

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
        normalized = normalize_text(name)
        return (
            "pierre d ame" in normalized
            or "pierres d ame" in normalized
            or "soul stone" in normalized
        )

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
                (need.category, need.name, need.quantity or 0) for need in summary
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
        checked_button = self.preparation_filter_group.checkedButton()
        current_filter = str(
            checked_button.property("filterKey") if checked_button is not None else "Tout"
        )
        self._render_preparation(current_filter)
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
        checked = self.preparation_filter_group.checkedButton()
        current_filter = str(
            checked.property("filterKey") if checked is not None else "Tout"
        )
        self._render_preparation(current_filter)

    def _append_preparation_more(self, remaining: int) -> None:
        if remaining <= 0:
            return
        button = QPushButton(f"Afficher la suite ({remaining} besoins restants)")
        button.setObjectName("GuidePreparationShowMore")
        button.clicked.connect(lambda _checked=False: self._show_more_preparation())
        self.preparation_rows_layout.addWidget(button)

    def _render_preparation(self, selected_filter: str) -> None:
        self._clear_preparation_rows()
        if not self.selected_participant_keys():
            label = QLabel("Aperçu des préparatifs · sélectionne un personnage pour activer Prêt.")
            label.setObjectName("GuidePreparationEmpty")
            label.setWordWrap(True)
            self.preparation_rows_layout.addWidget(label)
            preview = self._preparation_preview
            if selected_filter != "Tout":
                preview = tuple(row for row in preview if row[0] == selected_filter)
            if not preview:
                self.preparation_rows_layout.addWidget(QLabel("Aucun besoin structuré fiable."))
            else:
                # Read-only text, no checkbox and no anonymous persistence.
                visible = preview[:self._preparation_visible_limit]
                lines = [f"• {quantity if quantity else '?'} × {name} ({category})"
                         for category, name, quantity in visible]
                details = QLabel(chr(10).join(lines))
                details.setObjectName("GuidePreparationPreview")
                details.setWordWrap(True)
                details.setTextInteractionFlags(Qt.TextSelectableByMouse)
                self.preparation_rows_layout.addWidget(details)
                self._append_preparation_more(
                    len(preview) - self._preparation_visible_limit
                )
            self.preparation_rows_layout.addStretch(1)
            return

        if selected_filter == "Tout":
            groups = (
                ("Prérequis", lambda need: need.category == "Prérequis"),
                ("Métiers", lambda need: need.category == "Métiers"),
                ("Potions", lambda need: need.category == "Potions"),
                ("Pierres d'âme", lambda need: need.category == "Pierres d'âme"
                 or self._is_soul_stone(need.name)),
                ("Clefs", lambda need: need.category == "Clefs"),
                ("Objets", lambda need: need.category == "Objets"
                 and not self._is_soul_stone(need.name)),
            )
            if not self._preparation_needs:
                empty = QLabel("Aucun besoin confirmé sur le parcours restant.")
                empty.setObjectName("GuidePreparationEmpty")
                self.preparation_rows_layout.addWidget(empty)
            rendered_count = 0
            for category, predicate in groups:
                matching = [need for need in self._preparation_needs if predicate(need)]
                if not matching:
                    continue
                summary = QFrame()
                summary.setObjectName("GuidePreparationSummary")
                row = QHBoxLayout(summary)
                row.setContentsMargins(8, 5, 8, 5)
                row.addWidget(QLabel(category))
                row.addStretch(1)
                ready_count = sum(1 for need in matching if self._need_ready(need))
                row.addWidget(QLabel(f"{ready_count} / {len(matching)} prêts"))
                self.preparation_rows_layout.addWidget(summary)
                available = max(0, self._preparation_visible_limit - rendered_count)
                for need in matching[:available]:
                    self.preparation_rows_layout.addWidget(self._preparation_row(need))
                rendered_count += min(len(matching), available)
            self._append_preparation_more(
                len(self._preparation_needs) - rendered_count
            )
            self.preparation_rows_layout.addStretch(1)
            return

        matching = [
            need for need in self._preparation_needs if need.category == selected_filter
        ]
        if not matching:
            label = QLabel(f"Aucun besoin détaillé dans {selected_filter}.")
            label.setObjectName("GuidePreparationEmpty")
            self.preparation_rows_layout.addWidget(label)
            return
        for need in matching[:self._preparation_visible_limit]:
            self.preparation_rows_layout.addWidget(self._preparation_row(need))
        self._append_preparation_more(len(matching) - self._preparation_visible_limit)
        self.preparation_rows_layout.addStretch(1)

    def _preparation_row(self, need: _PreparationNeed) -> QWidget:
        frame = QFrame()
        frame.setObjectName("GuidePreparationRow")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(6)
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
        label = QLabel(f"{amount}{need.name} — {status}")
        label.setToolTip(" ; ".join(need.sources[:8])
                         or "Quantité ou provenance à confirmer")
        label.setObjectName("GuidePreparationRowLabel")
        top.addWidget(label, 1)
        ready_button = QToolButton()
        ready_button.setObjectName("GuidePreparationReady")
        ready_button.setIcon(_guide_symbol_icon(ready_button, "check", size=14))
        ready_button.setIconSize(QSize(14, 14))
        ready_button.setCheckable(True)
        ready_button.setChecked(ready)
        ready_button.setToolTip("Déclarer Prêt pour les participants sélectionnés concernés")
        if len(need.required_by_character) > 1 and not callable(
            getattr(getattr(self.service, "guide_progress", None),
                    "set_manual_steps_for_characters", None)
        ):
            ready_button.setEnabled(False)
            ready_button.setToolTip("Sauvegarde atomique indisponible")
        ready_button.toggled.connect(
            lambda checked, row=need: self._set_need_ready(row, checked)
        )
        top.addWidget(ready_button)
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
        if self.preparation_button.isChecked():
            self._load_preparation_needs()
            checked_button = self.preparation_filter_group.checkedButton()
            self._render_preparation(
                str(checked_button.property("filterKey") if checked_button else "Tout")
            )
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
            self.current_button.setEnabled(False)
            self.current_button.setToolTip("Étape actuelle indisponible : progression non déterminable.")
            return
        self.active_index = index
        self._show_index(index)

    def _follow_active_after_progress_change(self) -> None:
        previous = self.active_index
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
        self._preparation_loaded = False
        self._preparation_needs = ()
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
            self.route_bar.setRange(0, max(1, total))
            self.route_bar.setValue(completed)
            self.route_progress_label.setText(f"{percent} %")
            self.progress_donut.set_percent(percent)
        else:
            self.route_bar.setRange(0, 1)
            self.route_bar.setValue(0)
            self.route_progress_label.setText("—")
            self.progress_donut.set_percent(None)

        success_rows: list[tuple[int, int]] = []
        progress_getter = getattr(self.service, "progress", None)
        if callable(progress_getter):
            for character_key in keys:
                try:
                    progress = progress_getter(character_key)
                    success_rows.append(
                        (
                            int(getattr(progress, "full_success_completed", 0) or 0),
                            int(getattr(progress, "full_success_total", 0) or 0),
                        )
                    )
                except (AttributeError, KeyError, TypeError, ValueError):
                    success_rows = []
                    break
        success_total = max((total for _done, total in success_rows), default=0)
        success_done = min((done for done, _total in success_rows), default=0)
        self.success_bar.setRange(0, max(1, success_total))
        self.success_bar.setValue(success_done)
        self.success_progress_label.setText(
            f"{max(0, min(100, round(success_done * 100 / success_total)))} %"
            if success_total else "—"
        )
        self._update_preparation_progress()

        total_cards = len(self.service.cards)
        index = max(0, min(self.view_index, max(0, total_cards - 1)))
        card = self.service.cards[index] if total_cards else {}
        chapter = str(card.get("manual_chapter_label") or "Guide").strip()
        title = str(card.get("manual_title") or card.get("destination") or "Fiche").strip()
        self.sheet_meta_label.setText(f"FICHE {index + 1} · {chapter.upper()}")
        self.sheet_title_label.setText(title)
        self.nav_page_label.setText(f"Page {index + 1} / {total_cards}")
        self.page_jump.blockSignals(True)
        self.page_jump.setRange(1, max(1, total_cards))
        self.page_jump.setValue(index + 1)
        self.page_jump.blockSignals(False)
        actual_index = self._actual_index_for_participants()
        route_finished = bool(keys) and bool(progress_rows) and all(
            total > 0 and completed >= total for completed, total in progress_rows
        )
        self.current_button.setProperty(
            "guideFullText", "Terminé" if route_finished else "Actuelle"
        )
        self._sync_compact_action_labels()
        self.current_button.setEnabled(actual_index is not None)
        self.current_button.setToolTip(
            "Toutes les fiches sont terminées pour les personnages sélectionnés."
            if route_finished else (
                "Revenir à la première fiche encore nécessaire pour au moins un participant."
                if actual_index is not None
                else "Sélectionnez des personnages pour retrouver leur fiche actuelle."
            )
        )

    def _restore_route_lock_state(self) -> None:
        locked = False
        manual_checked = getattr(self.service, "manual_checked", None)
        if self.character_key and callable(manual_checked):
            locked = bool(
                manual_checked(
                    self.character_key,
                    self.ROUTE_LOCK_PROGRESS_KEY,
                )
            )
        self.route_lock_check.blockSignals(True)
        self.route_lock_check.setChecked(locked)
        self.route_lock_check.blockSignals(False)
        self._apply_route_lock_visual(locked)

    def _apply_route_lock_visual(self, locked: bool) -> None:
        label = "Verrouillé" if locked else "Déverrouillé"
        self.route_lock_check.setText(label)
        self.route_lock_check.setIcon(
            _guide_symbol_icon(self.route_lock_check, "lock" if locked else "unlock")
        )
        self.route_lock_check.setIconSize(QSize(14, 14))
        self.route_lock_check.setAccessibleName(label)
        self.route_lock_check.setProperty("state", "locked" if locked else "unlocked")
        self.route_lock_check.style().unpolish(self.route_lock_check)
        self.route_lock_check.style().polish(self.route_lock_check)
        self.route_bar.setCursor(Qt.ArrowCursor if locked else Qt.PointingHandCursor)
        self.route_bar.setToolTip(
            "Barre verrouillée : déverrouillez-la pour naviguer par clic."
            if locked
            else "Cliquer dans la barre pour naviguer directement dans le Guide."
        )
        self.route_lock_check.setToolTip(
            "Déverrouiller la navigation dans la barre de progression."
            if locked
            else "Verrouiller la navigation dans la barre de progression."
        )

    def _route_lock_toggled(self, locked: bool) -> None:
        self._apply_route_lock_visual(bool(locked))
        set_manual_checked = getattr(self.service, "set_manual_checked", None)
        if self.character_key and callable(set_manual_checked):
            set_manual_checked(
                self.character_key,
                self.ROUTE_LOCK_PROGRESS_KEY,
                bool(locked),
            )

    def set_character_key(self, character_key: str) -> None:
        super().set_character_key(character_key)
        self._preparation_loaded = False
        self._preparation_needs = ()
        self._refresh_participants_panel()
        self._restore_route_lock_state()

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
        enabled = bool(statuses) and callable(batcher) and callable(page_key) and not blocked and (not all_done or reversible)
        if not statuses:
            label, hint = "Choisir des personnages", "Sélectionnez un ou plusieurs personnages vérifiés dans Mes personnages."
        elif blocked:
            label, hint = "Choisir l’ordre", "Une fiche de la sélection est bloquée : terminez le choix d’ordre avant de valider."
        elif all_done and reversible:
            label, hint = "Annuler validation", "Retirer uniquement les coches manuelles ; les preuves automatiques sont conservées."
        elif all_done:
            label, hint = "Validé ✓", "Fiche déjà validée automatiquement pour tous les personnages sélectionnés."
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
        if not statuses or blocked or checked == all_done:
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

    def _render_window(self, *, reset_scroll: bool = False) -> None:
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
        self.prev_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < len(self.service.cards) - 1)
        self.guide_button.setToolTip(
            "Revenir à la fiche Guide active."
            if index != self.active_index
            else "Retour au choix des Guides."
        )
        if reset_scroll:
            self._reset_scroll_to_top()

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
