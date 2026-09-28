from __future__ import annotations

import html
import re
from typing import Any

from PySide6.QtCore import QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.modules.encyclopedia.views.guide_ultime_universal_view import GuideUltimeUniversalView
from app.ui.components import AtlasButton
from app.ui.theme import PALETTE


NPC_COLOR = PALETTE["YELLOW"]
RESOURCE_COLOR = PALETTE["GREEN"]
_NAME_WORD = r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]*"
_NPC_NAME = rf"{_NAME_WORD}(?:\s+(?:(?:de|des|du|d['’]|of|le|la|l['’])\s+)?{_NAME_WORD}){{0,3}}"
_NPC_PATTERNS = (
    re.compile(rf"(?:auprès\s+(?:de|d['’])|aupres\s+(?:de|d['’])|avec|vers|chez)\s+(?:l['’]|le\s+|la\s+|les\s+|du\s+|de\s+la\s+|de\s+l['’])?({_NPC_NAME})"),
    re.compile(rf"(?:parler|parle|parlez)\s+(?:à|a|au|aux|à\s+la|a\s+la|à\s+l['’])\s*(?:l['’])?({_NPC_NAME})", re.IGNORECASE),
    re.compile(rf"(?:libérer|liberer|livrer|présenter|presenter|retrouver)\s+({_NPC_NAME})", re.IGNORECASE),
    re.compile(rf"(?:rendre|donner|présenter|presenter|apporter)[^.;]{{0,80}}?\s+(?:à|a|au|aux|à\s+la|a\s+la|à\s+l['’])\s*(?:l['’])?({_NPC_NAME})", re.IGNORECASE),
)
_RESOURCE_STOP_WORDS = {"de", "du", "des", "la", "le", "les", "d", "l", "à", "au", "aux", "et"}
_NPC_CONNECTORS = {"de", "des", "du", "d'", "d’", "of", "le", "la", "l'", "l’"}


class GuideManualProgressBar(QProgressBar):
    """Completion bar that also acts as a route scrubber without mutating progress."""

    navigationRequested = Signal(float)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton and self.width() > 0:
            ratio = max(0.0, min(1.0, float(event.position().x()) / float(self.width())))
            self.navigationRequested.emit(ratio)
            event.accept()
            return
        super().mousePressEvent(event)


class GuideUltimeManualCard(QFrame):
    """A single hand-authored road-book sheet."""

    questRequested = Signal(int, str, int)

    def __init__(self, service, character_key: str, card: dict[str, Any], index: int, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.character_key = character_key
        self.card = card
        self.index = index
        self.setObjectName("GuideManualSheet")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(9)

        title = QLabel(str(card.get("manual_title") or "Fiche de route"))
        title.setObjectName("GuideManualStageTitle")
        title.setWordWrap(True)
        root.addWidget(title)

        location = str(card.get("destination") or "").strip()
        if location:
            where = QLabel(location)
            where.setObjectName("GuideManualLocation")
            where.setWordWrap(True)
            root.addWidget(where)

        self._add_quest_rows(root)

        self._resource_names = [
            str(value).strip()
            for value in card.get("manual_resource_names", []) or []
            if str(value).strip()
        ]
        line_provider = getattr(service, "manual_lines_for_card", None)
        manual_lines = line_provider(character_key, card) if callable(line_provider) else card.get("manual_lines", []) or []
        section_provider = getattr(service, "manual_sections_for_card", None)
        sections = (
            section_provider(character_key, card)
            if callable(section_provider)
            else {"now": manual_lines}
        )
        if not isinstance(sections, dict) or not any(sections.values()):
            sections = {"now": manual_lines}
        sections = self._without_prepare_duplicates(sections)

        self._add_line_section(
            root,
            "À PRÉPARER",
            sections.get("prepare"),
            "GuideManualResourceSection",
        )
        self._add_line_section(
            root,
            "À FAIRE MAINTENANT",
            sections.get("now"),
            "GuideManualActionSection",
        )
        self._add_line_section(
            root,
            "À PROFITER ICI",
            sections.get("opportunity"),
            "GuideManualActionSection",
        )
        self._add_line_section(
            root,
            "À CONSERVER POUR PLUS TARD",
            sections.get("keep"),
            "GuideManualResourceSection",
        )
        self._add_line_section(
            root,
            "BOSS / CAPTURES",
            sections.get("boss"),
            "GuideManualDungeonSection",
        )
        self._add_line_section(
            root,
            "AVANT DE PARTIR",
            sections.get("before_leave"),
            "GuideManualWarningSection",
        )

    @staticmethod
    def _section_row_fingerprint(row: Any) -> str:
        if not isinstance(row, dict):
            return ""
        position = " ".join(str(row.get("position") or "").split()).casefold()
        text = " ".join(str(row.get("text") or "").split()).casefold()
        if not text:
            return ""
        return f"{position}\n{text}"

    @classmethod
    def _without_prepare_duplicates(cls, sections: dict[str, Any]) -> dict[str, list[Any]]:
        """Keep preparation only for instructions not already executed now."""
        visible = {
            str(key): list(rows or []) if isinstance(rows, (list, tuple)) else []
            for key, rows in sections.items()
        }
        now_fingerprints = {
            cls._section_row_fingerprint(row)
            for row in visible.get("now", [])
        }
        now_fingerprints.discard("")
        visible["prepare"] = [
            row
            for row in visible.get("prepare", [])
            if cls._section_row_fingerprint(row) not in now_fingerprints
        ]
        return visible

    def _add_quest_rows(self, root: QVBoxLayout) -> None:
        quest_provider = getattr(self.service, "quest_provider", None)
        if quest_provider is None:
            return
        quest_ids = [
            int(value)
            for value in self.card.get("manual_quest_ids", []) or []
            if isinstance(value, int) or str(value).isdigit()
        ]
        if not quest_ids:
            return

        rows: list[tuple[int, str]] = []
        seen: set[int] = set()
        for quest_id in quest_ids:
            if quest_id in seen:
                continue
            seen.add(quest_id)
            try:
                quest = quest_provider.get_quest(quest_id)
            except Exception:
                quest = None
            name = str(getattr(quest, "name", "") or "").strip()
            if name:
                rows.append((quest_id, name))
        if not rows:
            return

        frame = QFrame()
        frame.setObjectName("GuideManualQuestSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        heading = QLabel("QUÊTES DE L'ÉTAPE")
        heading.setObjectName("GuideManualSectionTitle")
        layout.addWidget(heading)

        stage_id = str(self.card.get("manual_stage_id") or "")
        for quest_id, name in rows:
            button = AtlasButton(name)
            button.setObjectName("GuideManualQuestButton")
            button.setToolTip(
                f"{name}\nOuvrir la fiche canonique dans l'onglet Quêtes."
            )
            button.clicked.connect(
                lambda _checked=False, qid=quest_id, sid=stage_id: self.questRequested.emit(
                    qid,
                    sid,
                    self.index,
                )
            )
            layout.addWidget(button)

        root.addWidget(frame)

    def _add_line_section(
        self,
        root: QVBoxLayout,
        title: str,
        rows,
        object_name: str,
    ) -> None:
        visible = [
            row for row in rows or []
            if isinstance(row, dict) and str(row.get("text") or "").strip()
        ]
        if not visible:
            return

        frame = QFrame()
        frame.setObjectName(object_name)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        heading = QLabel(title)
        heading.setObjectName("GuideManualSectionTitle")
        layout.addWidget(heading)

        for row in visible:
            text = str(row.get("text") or "").strip()
            position = str(row.get("position") or "").strip()
            kind = str(row.get("kind") or "")
            prefix = "⚠ " if kind == "warning" else "• "
            line = QLabel()
            line.setTextFormat(Qt.RichText)
            line.setText(
                self._format_line_html(
                    prefix,
                    position,
                    text,
                    self._npc_names(text),
                    self._resource_names,
                )
            )
            line.setObjectName(self._line_object_name(kind, text))
            line.setWordWrap(True)
            line.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(line)

        root.addWidget(frame)

    @staticmethod
    def _line_object_name(kind: str, text: str) -> str:
        if str(kind or "") == "warning":
            return "GuideManualWarning"
        value = str(text or "").casefold()
        if any(token in value for token in ("donjon", "boss", "combat", "vaincre", "battre")):
            return "GuideManualCombat"
        if any(token in value for token in ("quête spéciale", "quete speciale", "choisir le dialogue", "choisis le dialogue")):
            return "GuideManualSpecial"
        return "GuideManualLine"

    @staticmethod
    def _npc_names(text: str) -> list[str]:
        value = str(text or "")
        found: list[str] = []
        seen: set[str] = set()
        for pattern in _NPC_PATTERNS:
            for match in pattern.finditer(value):
                raw = " ".join(str(match.group(1) or "").split()).strip(" ,.;:!")
                tokens = raw.split()
                kept: list[str] = []
                for token in tokens:
                    clean = token.strip(" ,.;:!")
                    lowered = clean.casefold()
                    if lowered in _NPC_CONNECTORS:
                        if kept:
                            kept.append(clean)
                        continue
                    if clean and clean[0].isupper():
                        kept.append(clean)
                        continue
                    break
                while kept and kept[-1].casefold() in _NPC_CONNECTORS:
                    kept.pop()
                name = " ".join(kept).strip()
                key = name.casefold()
                if name and key not in seen:
                    seen.add(key)
                    found.append(name)
        return sorted(found, key=len, reverse=True)

    @classmethod
    def _format_line_html(
        cls,
        prefix: str,
        position: str,
        text: str,
        npc_names: list[str],
        resource_names: list[str],
    ) -> str:
        prefix_text = str(prefix or "")
        position_text = str(position or "")
        plain = prefix_text + (f"{position_text} — " if position_text else "") + str(text or "")
        spans: list[tuple[int, int, str]] = []

        def add_span(start: int, end: int, kind: str) -> None:
            if start >= end:
                return
            if any(not (end <= existing_start or start >= existing_end) for existing_start, existing_end, _ in spans):
                return
            spans.append((start, end, kind))

        if position_text:
            add_span(len(prefix_text), len(prefix_text) + len(position_text), "position")

        for name in sorted({value for value in npc_names if value}, key=len, reverse=True):
            pattern = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.IGNORECASE)
            for match in pattern.finditer(plain):
                add_span(match.start(), match.end(), "npc")

        for name in sorted({value for value in resource_names if value}, key=len, reverse=True):
            pattern = cls._resource_regex(name)
            for match in pattern.finditer(plain):
                add_span(match.start(), match.end(), "resource")

        if not spans:
            return html.escape(plain)

        spans.sort(key=lambda row: row[0])
        rendered: list[str] = []
        cursor = 0
        for start, end, kind in spans:
            if start < cursor:
                continue
            rendered.append(html.escape(plain[cursor:start]))
            value = html.escape(plain[start:end])
            if kind == "npc":
                rendered.append(f'<span style="color:{NPC_COLOR};"><b>{value}</b></span>')
            elif kind == "resource":
                rendered.append(f'<span style="color:{RESOURCE_COLOR};"><b>{value}</b></span>')
            else:
                rendered.append(f"<b>{value}</b>")
            cursor = end
        rendered.append(html.escape(plain[cursor:]))
        return "".join(rendered)

    @staticmethod
    def _resource_regex(name: str) -> re.Pattern[str]:
        parts = re.split(r"(\s+|['’])", str(name or "").strip())
        pattern_parts: list[str] = []
        for part in parts:
            if not part:
                continue
            if part.isspace():
                pattern_parts.append(r"\s+")
                continue
            if part in {"'", "’"}:
                pattern_parts.append(r"['’]")
                continue
            escaped = re.escape(part)
            normalized = part.casefold().strip(".,;:!?")
            if normalized not in _RESOURCE_STOP_WORDS and len(part) > 2 and not normalized.endswith(("s", "x", "z")):
                escaped += "s?"
            pattern_parts.append(escaped)
        return re.compile(rf"(?<!\w){''.join(pattern_parts)}(?!\w)", re.IGNORECASE)


class GuideUltimeManualView(GuideUltimeUniversalView):
    """Manual Guide Ultime with focused single-sheet navigation."""

    def _build_ui(self) -> None:
        self.filter_mode = "Tout"
        self.navigate_entity = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        progress = QFrame()
        progress.setObjectName("GuideManualProgressFrame")
        progress_layout = QHBoxLayout(progress)
        progress_layout.setContentsMargins(8, 3, 8, 3)
        progress_layout.setSpacing(8)
        self.route_bar = GuideManualProgressBar()
        self.route_bar.setObjectName("GuideManualProgress")
        self.route_bar.setTextVisible(False)
        self.route_bar.setFixedHeight(7)
        self.route_bar.setCursor(Qt.PointingHandCursor)
        self.route_bar.setToolTip("Cliquer dans la barre pour naviguer directement dans le Guide GPS.")
        self.route_bar.navigationRequested.connect(self._jump_from_progress)
        progress_layout.addWidget(self.route_bar, 1)
        self.route_progress_label = QLabel()
        self.route_progress_label.setObjectName("GuideManualPercent")
        progress_layout.addWidget(self.route_progress_label)
        self.route_lock_check = QCheckBox("Verrouiller")
        self.route_lock_check.setObjectName("GuideManualProgressLock")
        self.route_lock_check.setToolTip("Empêcher les sauts accidentels par clic dans la barre de progression.")
        self.route_lock_check.toggled.connect(self._route_lock_toggled)
        progress_layout.addWidget(self.route_lock_check)
        root.addWidget(progress)

        self.route_legend = QLabel(
            "Barre : cliquer pour parcourir les fiches · Verrouiller : bloquer les sauts par clic · Validation : secours manuel uniquement."
        )
        self.route_legend.setObjectName("GuideManualLegend")
        self.route_legend.setWordWrap(True)
        root.addWidget(self.route_legend)

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

        self.nav_page_label = QLabel()
        self.nav_page_label.setObjectName("GuideManualNavPage")
        self.nav_page_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.nav_page_label)

        nav = QFrame()
        nav.setObjectName("GuideManualNav")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(8, 4, 8, 6)
        nav_layout.setSpacing(10)
        self.prev_button = QPushButton("← Précédent")
        self.prev_button.setObjectName("GuideManualPrev")
        self.prev_button.clicked.connect(lambda: self.navigate_relative(-1))
        nav_layout.addWidget(self.prev_button)
        nav_layout.addStretch(1)
        self.validation_check = QCheckBox("Validation")
        self.validation_check.setObjectName("GuideManualValidationCheck")
        self.validation_check.toggled.connect(self._validation_toggled)
        nav_layout.addWidget(self.validation_check)
        nav_layout.addStretch(1)
        self.next_button = QPushButton("Suivant →")
        self.next_button.setObjectName("GuideManualNextButton")
        self.next_button.clicked.connect(lambda: self.navigate_relative(1))
        nav_layout.addWidget(self.next_button)
        root.addWidget(nav)

        self.progress_details = QLabel()
        self.progress_details.setVisible(False)
        self.position_label = QLabel()
        self.position_label.setVisible(False)

    def _sync_order_combo(self) -> None:
        return

    def _route_lock_toggled(self, locked: bool) -> None:
        self.route_bar.setCursor(Qt.ArrowCursor if locked else Qt.PointingHandCursor)
        self.route_bar.setToolTip(
            "Barre verrouillée : décochez Verrouiller pour naviguer par clic."
            if locked
            else "Cliquer dans la barre pour naviguer directement dans le Guide GPS."
        )

    def _refresh_header(self) -> None:
        completed, total = self.service.route_sheet_progress(self.character_key)
        if total <= 0:
            self.route_bar.setRange(0, 0)
            self.route_progress_label.setText("")
            self.nav_page_label.setText("")
            self._disable_validation_control()
            return
        self.route_bar.setRange(0, total)
        self.route_bar.setValue(min(completed, total))
        percent = min(100, round(completed * 100 / total))
        page = max(1, min(total, int(self.view_index) + 1))
        self.nav_page_label.setText(f"Page {page} / {total}")
        self.route_progress_label.setText(f"{percent} %")

    def _show_index(self, index: int) -> None:
        if not self.service.cards:
            return
        self.view_index = max(0, min(len(self.service.cards) - 1, int(index)))
        self._refresh_header()
        self._render_window(reset_scroll=True)

    def _jump_from_progress(self, ratio: float) -> None:
        if self.route_lock_check.isChecked():
            return
        total = len(self.service.cards)
        if total <= 0:
            return
        index = int(round(max(0.0, min(1.0, float(ratio))) * max(0, total - 1)))
        self._show_index(index)

    def navigate_relative(self, delta: int) -> None:
        if not self.service.cards:
            return
        self._show_index(self.view_index + int(delta))

    def go_active(self) -> None:
        self.active_index = self.service.first_incomplete_index(self.character_key)
        self._show_index(self.active_index)

    def _render_window(self, *, reset_scroll: bool = False) -> None:
        self._clear_cards()
        if not self.service.cards:
            self._disable_validation_control()
            return
        index = max(0, min(self.view_index, len(self.service.cards) - 1))
        card = self.service.cards[index]
        self._add_manual_order_choice(card)
        widget = GuideUltimeManualCard(self.service, self.character_key, card, index)
        widget.questRequested.connect(self._open_quest_from_card)
        self.cards_layout.addWidget(widget)
        self.cards_layout.addStretch(1)
        self.rendered_card_count = 1
        self.prev_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < len(self.service.cards) - 1)
        self._sync_validation_control(card, index)
        self._make_positions_copyable(widget)
        if reset_scroll:
            self._reset_scroll_to_top()

    def _open_quest_from_card(self, quest_id: int, stage_id: str, index: int) -> None:
        navigator = self.navigate_entity
        if not callable(navigator):
            return
        navigator(
            "quest",
            int(quest_id),
            source="guide_gps",
            guide_id="guide_complet",
            guide_stage_id=str(stage_id or ""),
            guide_index=int(index),
        )

    def _sync_validation_control(self, card: dict[str, Any], index: int) -> None:
        automatic = bool(self.service.card_auto_complete(self.character_key, card))
        manual = bool(self.service.page_checked(self.character_key, card, index))
        blocking = bool(
            callable(getattr(self.service, "manual_order_choice_blocking", None))
            and self.service.manual_order_choice_blocking(self.character_key, card)
        )
        trigger_ready = bool(
            callable(getattr(self.service, "manual_order_choice_required", None))
            and self.service.manual_order_choice_required(self.character_key, card)
        )

        self.validation_check.blockSignals(True)
        try:
            self.validation_check.setChecked(bool((automatic or manual) and not blocking))
            self.validation_check.setEnabled(not automatic and not blocking)
            if blocking:
                tooltip = (
                    "Choisis ton Ordre Bonta pour continuer."
                    if trigger_ready
                    else "Termine d’abord le rang 20."
                )
            elif automatic:
                tooltip = "Cette fiche est validée automatiquement par la progression canonique."
            else:
                tooltip = "Validation manuelle de secours tant que cette étape ne peut pas être confirmée automatiquement."
            self.validation_check.setToolTip(tooltip)
        finally:
            self.validation_check.blockSignals(False)

    def _disable_validation_control(self) -> None:
        self.validation_check.blockSignals(True)
        try:
            self.validation_check.setChecked(False)
            self.validation_check.setEnabled(False)
            self.validation_check.setToolTip("")
        finally:
            self.validation_check.blockSignals(False)

    def _validation_toggled(self, checked: bool) -> None:
        if not self.service.cards:
            self._disable_validation_control()
            return
        index = max(0, min(self.view_index, len(self.service.cards) - 1))
        card = self.service.cards[index]
        automatic = bool(self.service.card_auto_complete(self.character_key, card))
        blocking = bool(
            callable(getattr(self.service, "manual_order_choice_blocking", None))
            and self.service.manual_order_choice_blocking(self.character_key, card)
        )
        if automatic or blocking:
            self._sync_validation_control(card, index)
            return
        self.service.set_page_checked(
            self.character_key,
            card,
            index,
            bool(checked),
        )
        self._follow_active_after_progress_change()

    def _add_manual_order_choice(self, card: dict[str, Any]) -> None:
        required = getattr(self.service, "manual_order_choice_required", None)
        options_for_card = getattr(self.service, "manual_order_options_for_card", None)
        if not callable(required) or not required(self.character_key, card) or not callable(options_for_card):
            return
        options = tuple(options_for_card(card))
        if not options:
            return

        frame = QFrame()
        frame.setObjectName("GuideManualOrderChoice")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(8)
        title = QLabel("Choisis ton Ordre Bonta")
        title.setObjectName("GuideManualOrderTitle")
        layout.addWidget(title)
        detail = QLabel("Ce choix sera conservé automatiquement aux rangs 40, 60, 80 et 100. Les deux autres branches disparaîtront du parcours.")
        detail.setObjectName("GuideManualOrderDetail")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        for option in options:
            button = QPushButton(option)
            button.setObjectName("GuideManualOrderButton")
            button.clicked.connect(lambda _checked=False, value=option: self._select_manual_order(value))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.cards_layout.addWidget(frame)

    def _select_manual_order(self, order_name: str) -> None:
        self.service.set_bonta_order(self.character_key, order_name)
        self.active_index = self.service.first_incomplete_index(self.character_key)
        self._show_index(self.active_index)

    def refresh_external_progress(self) -> None:
        self.service.reload_progress()
        if not self.service.available:
            self._render_missing_data()
            return
        self._follow_active_after_progress_change()

    def _follow_active_after_progress_change(self) -> None:
        previous = self.active_index
        self.active_index = self.service.first_incomplete_index(self.character_key)
        moved = self.view_index == previous and self.active_index != previous
        if moved:
            self.view_index = self.active_index
        self._refresh_header()
        self._render_window(reset_scroll=moved)

    def _shared_achievement_progress_changed(self) -> None:
        self.service.reload_progress()
        self._follow_active_after_progress_change()

    def _reset_scroll_to_top(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.minimum())
        QTimer.singleShot(
            0,
            lambda: self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().minimum()
            ),
        )
