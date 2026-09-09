from __future__ import annotations

import html
import re
from typing import Any

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.modules.encyclopedia.services.guide_auto_validation_contract import route_progress_counts
from app.modules.encyclopedia.views.guide_ultime_universal_view import GuideUltimeUniversalView
from app.ui.components import AtlasButton
from app.ui.styles import guide_manual_stylesheet
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
    """A single hand-authored road-book sheet. No per-line validation."""

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

        resource_names = [
            str(value).strip()
            for value in card.get("manual_resource_names", []) or []
            if str(value).strip()
        ]
        line_provider = getattr(service, "manual_lines_for_card", None)
        manual_lines = line_provider(character_key, card) if callable(line_provider) else card.get("manual_lines", []) or []
        for row in manual_lines:
            if not isinstance(row, dict):
                continue
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            position = str(row.get("position") or "").strip()
            kind = str(row.get("kind") or "")
            prefix = "⚠ " if kind == "warning" else "• "
            rich_text = self._format_line_html(
                prefix,
                position,
                text,
                self._npc_names(text),
                resource_names,
            )
            line = QLabel()
            line.setTextFormat(Qt.RichText)
            line.setText(rich_text)
            line.setObjectName(self._line_object_name(kind, text))
            line.setWordWrap(True)
            line.setTextInteractionFlags(Qt.TextSelectableByMouse)
            root.addWidget(line)

        self._add_success_targets(root)

        next_card = service.cards[index + 1] if index + 1 < len(service.cards) else None
        if isinstance(next_card, dict):
            destination = str(next_card.get("destination") or "").strip()
            if destination:
                next_line = QLabel(f"→ Prochaine destination : {destination}")
                next_line.setObjectName("GuideManualNext")
                next_line.setWordWrap(True)
                root.addWidget(next_line)

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
            label = "CHOISIS TON ORDRE POUR CONTINUER" if trigger_ready else "TERMINE D’ABORD LE RANG 20"
        elif automatic:
            label = "FICHE VALIDÉE AUTOMATIQUEMENT"
        else:
            label = "VALIDATION MANUELLE DE SECOURS"
        self.page_check = QCheckBox(label)
        self.page_check.setObjectName("GuideManualPageCheck")
        self.page_check.setChecked(bool((automatic or manual) and not blocking))
        self.page_check.setEnabled(not automatic and not blocking)
        if not automatic and not blocking:
            self.page_check.setToolTip("Secours temporaire tant que la validation automatique n'est pas branchée.")
            self.page_check.toggled.connect(self._page_toggled)
        root.addWidget(self.page_check)

    def _contract_row(self) -> dict[str, Any]:
        contract = getattr(self.service, "auto_validation_contract", None)
        if not isinstance(contract, dict):
            return {}
        contract_id = id(contract)
        cached = getattr(self.service, "_manual_contract_row_index_cache", None)
        if not (
            isinstance(cached, tuple)
            and len(cached) == 2
            and cached[0] == contract_id
            and isinstance(cached[1], dict)
        ):
            index: dict[str, dict[str, Any]] = {}
            for row in contract.get("cards", []) or []:
                if not isinstance(row, dict):
                    continue
                key = str(row.get("card_key") or "").strip()
                if key and key not in index:
                    index[key] = row
            cached = (contract_id, index)
            self.service._manual_contract_row_index_cache = cached
        card_key = self.service.card_key(self.card, self.index)
        return cached[1].get(str(card_key or "").strip(), {})

    def _add_success_targets(self, root: QVBoxLayout) -> None:
        targets = [
            row
            for row in self._contract_row().get("successes", []) or []
            if isinstance(row, dict) and str(row.get("name") or "").strip()
        ]
        if not targets:
            return

        frame = QFrame()
        frame.setObjectName("GuideManualSuccessBlock")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        title = QLabel("SUCCÈS LIÉS")
        title.setObjectName("GuideManualSuccessTitle")
        layout.addWidget(title)

        for target in targets:
            achievement_id = self._safe_int(target.get("achievement_id"))
            name = str(target.get("name") or "").strip()
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            done = bool(
                achievement_id is not None
                and self.service.achievement_progress.is_achievement_completed(
                    self.character_key, achievement_id
                )
            )
            checkbox = QCheckBox(name)
            checkbox.setObjectName("GuideManualSuccessCheck")
            checkbox.setChecked(done)
            checkbox.setProperty("state", "done" if done else "todo")
            checkbox.setEnabled(achievement_id is not None)
            if achievement_id is None:
                checkbox.setToolTip("Succès non résolu dans le catalogue Atlas : aucune progression n'est inventée.")
            else:
                checkbox.setToolTip("Progression partagée avec l'onglet Succès pour ce personnage.")
                checkbox.toggled.connect(
                    lambda value, aid=achievement_id: self._success_toggled(aid, value)
                )
            row_layout.addWidget(checkbox, 1)

            open_button = QPushButton("Ouvrir dans Succès")
            open_button.setObjectName("GuideManualSuccessOpen")
            open_button.setEnabled(achievement_id is not None)
            if achievement_id is not None:
                open_button.clicked.connect(
                    lambda _checked=False, aid=achievement_id: self._open_success(aid)
                )
            row_layout.addWidget(open_button)
            layout.addLayout(row_layout)

        root.addWidget(frame)

    def _success_toggled(self, achievement_id: int, checked: bool) -> None:
        self.service.achievement_progress.set_achievement_completed(
            self.character_key,
            int(achievement_id),
            bool(checked),
        )
        parent = self.parentWidget()
        while parent is not None:
            handler = getattr(parent, "_shared_achievement_progress_changed", None)
            if callable(handler):
                handler()
                return
            parent = parent.parentWidget()

    def _open_success(self, achievement_id: int) -> None:
        parent = self.parentWidget()
        while parent is not None:
            navigator = getattr(parent, "navigate_entity", None)
            if callable(navigator):
                navigator("achievement", int(achievement_id), source="achievement")
                return
            parent = parent.parentWidget()

    def _page_toggled(self, checked: bool) -> None:
        self.service.set_page_checked(self.character_key, self.card, self.index, bool(checked))
        parent = self.parentWidget()
        while parent is not None:
            handler = getattr(parent, "_manual_page_changed", None)
            if callable(handler):
                handler()
                return
            parent = parent.parentWidget()

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

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
        plain = str(prefix or "") + (f"{position} — " if position else "") + str(text or "")
        spans: list[tuple[int, int, str]] = []

        def add_span(start: int, end: int, kind: str) -> None:
            if start >= end:
                return
            if any(not (end <= existing_start or start >= existing_end) for existing_start, existing_end, _ in spans):
                return
            spans.append((start, end, kind))

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
            else:
                rendered.append(f'<span style="color:{RESOURCE_COLOR};"><b>{value}</b></span>')
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
    """Manual Guide Ultime using the exact Quêtes breadcrumb structure."""

    def _build_ui(self) -> None:
        self.filter_mode = "Tout"
        self.navigate_entity = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self.breadcrumb = QFrame()
        self.breadcrumb.setObjectName("GuideBreadcrumb")
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb)
        self.breadcrumb_layout.setContentsMargins(8, 5, 8, 5)
        self.breadcrumb_layout.setSpacing(5)
        root.addWidget(self.breadcrumb)

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
        root.addWidget(progress)

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
        self.prev_button = QPushButton("← Précédent")
        self.prev_button.setObjectName("GuideManualPrev")
        self.prev_button.clicked.connect(lambda: self.navigate_relative(-1))
        nav_layout.addWidget(self.prev_button)
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

        self._apply_manual_style()

    def _sync_order_combo(self) -> None:
        return

    def _refresh_header(self) -> None:
        completed, total = self.service.route_sheet_progress(self.character_key)
        if total <= 0:
            self.route_bar.setRange(0, 0)
            self.route_progress_label.setText("")
            return
        self.route_bar.setRange(0, total)
        self.route_bar.setValue(min(completed, total))
        percent = min(100, round(completed * 100 / total))
        counts = route_progress_counts(
            self.service,
            self.character_key,
            getattr(self.service, "auto_validation_contract", None),
        )
        page = max(1, min(total, int(self.view_index) + 1))
        self.route_progress_label.setText(
            f"Page {page}/{total}  •  "
            f"Quêtes {counts['quests_completed']}/{counts['quests_total']}  •  "
            f"Donjons {counts['dungeons_completed']}/{counts['dungeons_total']}  •  "
            f"{percent} %"
        )

    def _jump_from_progress(self, ratio: float) -> None:
        total = len(self.service.cards)
        if total <= 0:
            return
        index = int(round(max(0.0, min(1.0, float(ratio))) * max(0, total - 1)))
        self.view_index = index
        self._refresh_header()
        self._render_window()

    def navigate_relative(self, delta: int) -> None:
        if not self.service.cards:
            return
        self.view_index = max(0, min(len(self.service.cards) - 1, self.view_index + int(delta)))
        self._refresh_header()
        self._render_window()

    def go_active(self) -> None:
        self.active_index = self.service.first_incomplete_index(self.character_key)
        self.view_index = self.active_index
        self._refresh_header()
        self._render_window()

    def _render_window(self) -> None:
        self._clear_cards()
        if not self.service.cards:
            return
        index = max(0, min(self.view_index, len(self.service.cards) - 1))
        card = self.service.cards[index]
        self._render_breadcrumb(card)
        self._add_manual_order_choice(card)
        widget = GuideUltimeManualCard(self.service, self.character_key, card, index)
        self.cards_layout.addWidget(widget)
        self.cards_layout.addStretch(1)
        self.rendered_card_count = 1
        self.prev_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < len(self.service.cards) - 1)
        self._make_positions_copyable(widget)

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
        self._refresh_header()
        self._render_window()

    def _render_breadcrumb(self, card: dict[str, Any]) -> None:
        while self.breadcrumb_layout.count():
            item = self.breadcrumb_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        guides = AtlasButton("Guides")
        guides.setObjectName("GuideBreadcrumbButton")
        guides.clicked.connect(lambda _checked=False: self._return_to_guides_catalog())
        self.breadcrumb_layout.addWidget(guides)
        self._add_breadcrumb_separator()

        guide = AtlasButton("Guide Ultime")
        guide.setObjectName("GuideBreadcrumbButton")
        guide.clicked.connect(lambda _checked=False: self.go_active())
        self.breadcrumb_layout.addWidget(guide)
        self._add_breadcrumb_separator()

        chapter_name = str(card.get("manual_chapter_label") or "").strip()
        if not chapter_name:
            chapter_name = self._chapter_label(str(card.get("manual_chapter_id") or ""))
        chapter = AtlasButton(chapter_name)
        chapter.setObjectName("GuideBreadcrumbButton")
        chapter.clicked.connect(
            lambda _checked=False, chapter_id=str(card.get("manual_chapter_id") or ""): self._go_chapter(chapter_id)
        )
        self.breadcrumb_layout.addWidget(chapter)
        self._add_breadcrumb_separator()

        current_text = str(card.get("manual_title") or "Fiche de route")
        current = QLabel(current_text)
        current.setObjectName("GuideBreadcrumbCurrent")
        current.setWordWrap(False)
        current.setToolTip(current_text)
        current.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.breadcrumb_layout.addWidget(current, 1)

    def _add_breadcrumb_separator(self) -> None:
        separator = QLabel(">")
        separator.setObjectName("GuideBreadcrumbSeparator")
        self.breadcrumb_layout.addWidget(separator)

    def _go_chapter(self, chapter_id: str) -> None:
        for index, card in enumerate(self.service.cards):
            if str(card.get("manual_chapter_id") or "") == str(chapter_id):
                self.view_index = index
                self._refresh_header()
                self._render_window()
                return

    def _manual_page_changed(self) -> None:
        previous = self.active_index
        self.active_index = self.service.first_incomplete_index(self.character_key)
        if self.view_index == previous and self.active_index != previous:
            self.view_index = self.active_index
        self._refresh_header()
        self._render_window()

    def _shared_achievement_progress_changed(self) -> None:
        self.service.reload_progress()
        self.active_index = self.service.first_incomplete_index(self.character_key)
        self._refresh_header()
        self._render_window()

    @staticmethod
    def _chapter_label(chapter_id: str) -> str:
        return chapter_id.replace("_", " ").title() or "Parcours"

    def _apply_manual_style(self) -> None:
        self.setStyleSheet(guide_manual_stylesheet())
