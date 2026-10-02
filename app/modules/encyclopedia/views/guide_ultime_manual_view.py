from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote, unquote

from PySide6.QtCore import QTimer, Signal, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.modules.encyclopedia.services.guide_quest_view_model import quest_items_from_objectives
from app.modules.encyclopedia.views.guide_ultime_universal_view import GuideUltimeUniversalView
from app.ui.components import AtlasButton
from app.ui.theme import PALETTE


NPC_COLOR = PALETTE["YELLOW"]
RESOURCE_COLOR = PALETTE["GREEN"]
POSITION_COLOR = PALETTE["TEXT_SOFT"]
_COORD_RE = re.compile(r"\[(-?\d+)\s*,\s*(-?\d+)\]")
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
        self._resource_names = self._clickable_resource_names(service, card)
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
            where = QLabel()
            where.setObjectName("GuideManualLocation")
            where.setWordWrap(True)
            self._set_clickable_text(where, self._format_line_html("", "", location, [], []))
            root.addWidget(where)

        self._add_quest_links(root)

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

    def _add_quest_links(self, root: QVBoxLayout) -> None:
        quests = self._quest_links()
        if not quests:
            return

        frame = QFrame()
        frame.setObjectName("GuideManualQuestSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        heading = QLabel("QUÊTES DE LA FICHE")
        heading.setObjectName("GuideManualSectionTitle")
        layout.addWidget(heading)

        for quest_id, name in quests:
            button = QPushButton(name)
            button.setObjectName("GuideManualQuestLink")
            button.setProperty("questId", quest_id)
            button.setToolTip(f"Ouvrir « {name} » dans l’onglet Quêtes.")
            button.clicked.connect(
                lambda _checked=False, qid=quest_id: self._open_quest(qid)
            )
            layout.addWidget(button)

        root.addWidget(frame)

    def _quest_links(self) -> list[tuple[int, str]]:
        provider = getattr(self.service, "quest_provider", None)
        getter = getattr(provider, "get_quest", None)
        result: list[tuple[int, str]] = []
        seen: set[int] = set()
        for raw in self.card.get("manual_quest_ids", []) or []:
            try:
                quest_id = int(raw)
            except (TypeError, ValueError):
                continue
            if quest_id in seen:
                continue
            seen.add(quest_id)

            name = ""
            if callable(getter):
                try:
                    quest = getter(quest_id)
                except (KeyError, LookupError, TypeError, ValueError):
                    quest = None
                name = str(getattr(quest, "name", "") or "").strip()
            result.append((quest_id, name or f"Quête #{quest_id}"))
        return result

    @staticmethod
    def _clickable_resource_names(service, card: dict[str, Any]) -> list[str]:
        names = [
            str(value).strip()
            for value in card.get("manual_resource_names", []) or []
            if str(value).strip()
        ]
        provider = getattr(service, "quest_provider", None)
        getter = getattr(provider, "get_quest", None)
        if callable(getter):
            for raw in card.get("manual_quest_ids", []) or []:
                try:
                    quest_id = int(raw)
                    quest = getter(quest_id)
                except (KeyError, LookupError, TypeError, ValueError):
                    continue
                try:
                    items = quest_items_from_objectives(quest)
                except (AttributeError, TypeError, ValueError):
                    continue
                for item in items:
                    name = str(getattr(item, "name", "") or "").strip()
                    if name:
                        names.append(name)

        result: list[str] = []
        seen: set[str] = set()
        for name in names:
            key = name.casefold()
            if key and key not in seen:
                seen.add(key)
                result.append(name)
        return sorted(result, key=len, reverse=True)

    def _open_quest(self, quest_id: int) -> None:
        parent = self.parentWidget()
        while parent is not None:
            navigator = getattr(parent, "navigate_entity", None)
            if callable(navigator):
                # No Guide/Achievement source override here: the UX contract is
                # to open the canonical quest sheet in the Quêtes tab.
                navigator("quest", int(quest_id))
                return
            parent = parent.parentWidget()

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
            line.setObjectName(self._line_object_name(kind, text))
            line.setWordWrap(True)
            layout.addWidget(line)

        root.addWidget(frame)

    def _set_clickable_text(self, label: QLabel, rendered: str) -> None:
        label.setTextFormat(Qt.RichText)
        label.setText(rendered)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(self._copy_link_target)

    @staticmethod
    def _copy_text_for_link(href: str) -> str | None:
        value = str(href or "")
        if value.startswith("item-copy:"):
            name = unquote(value.removeprefix("item-copy:")).strip()
            return name or None
        if value.startswith("travel-copy:"):
            raw = value.removeprefix("travel-copy:")
            match = re.fullmatch(r"(-?\d+),(-?\d+)", raw)
            if not match:
                return None
            return f"/travel {int(match.group(1))},{int(match.group(2))}"
        return None

    def _copy_link_target(self, href: str) -> None:
        value = self._copy_text_for_link(href)
        if not value:
            return
        QApplication.clipboard().setText(value)
        QToolTip.showText(QCursor.pos(), "Copié", self)
        QTimer.singleShot(800, QToolTip.hideText)

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
        plain = prefix_text + (f"{position} — " if position else "") + str(text or "")
        spans: list[tuple[int, int, str, str]] = []

        def add_span(start: int, end: int, kind: str, payload: str = "") -> None:
            if start >= end:
                return
            if any(not (end <= existing_start or start >= existing_end) for existing_start, existing_end, _, _ in spans):
                return
            spans.append((start, end, kind, payload))

        for match in _COORD_RE.finditer(plain):
            add_span(
                match.start(),
                match.end(),
                "position",
                f"{int(match.group(1))},{int(match.group(2))}",
            )

        for name in sorted({value for value in npc_names if value}, key=len, reverse=True):
            pattern = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.IGNORECASE)
            for match in pattern.finditer(plain):
                add_span(match.start(), match.end(), "npc")

        for name in sorted({value for value in resource_names if value}, key=len, reverse=True):
            pattern = cls._resource_regex(name)
            for match in pattern.finditer(plain):
                add_span(match.start(), match.end(), "resource", name)

        if not spans:
            return html.escape(plain)

        spans.sort(key=lambda row: row[0])
        rendered: list[str] = []
        cursor = 0
        for start, end, kind, payload in spans:
            if start < cursor:
                continue
            rendered.append(html.escape(plain[cursor:start]))
            value = html.escape(plain[start:end])
            if kind == "npc":
                rendered.append(f'<span style="color:{NPC_COLOR};"><b>{value}</b></span>')
            elif kind == "resource":
                href = html.escape(f"item-copy:{quote(payload, safe='')}", quote=True)
                rendered.append(
                    f'<a href="{href}" style="color:{RESOURCE_COLOR};text-decoration:none;"><b>{value}</b></a>'
                )
            else:
                href = html.escape(f"travel-copy:{payload}", quote=True)
                rendered.append(
                    f'<a href="{href}" style="color:{POSITION_COLOR};text-decoration:none;"><b>{value}</b></a>'
                )
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
    """Manual Guide Ultime with one focused navigation control."""

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
        self.nav_page_label = QLabel()
        self.nav_page_label.setObjectName("GuideManualNavPage")
        nav_layout.addWidget(self.nav_page_label)
        self.guide_button = AtlasButton("Guide")
        self.guide_button.setObjectName("GuideManualGuideButton")
        self.guide_button.clicked.connect(lambda _checked=False: self._guide_button_clicked())
        nav_layout.addWidget(self.guide_button)
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

    def _refresh_header(self) -> None:
        completed, total = self.service.route_sheet_progress(self.character_key)
        if total <= 0:
            self.route_bar.setRange(0, 0)
            self.route_progress_label.setText("")
            self.nav_page_label.setText("")
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

    def _guide_button_clicked(self) -> None:
        if self.view_index != self.active_index:
            self.go_active()
            return
        self._return_to_guides_catalog()

    def _render_window(self, *, reset_scroll: bool = False) -> None:
        self._clear_cards()
        if not self.service.cards:
            return
        index = max(0, min(self.view_index, len(self.service.cards) - 1))
        card = self.service.cards[index]
        self._add_manual_order_choice(card)
        widget = GuideUltimeManualCard(self.service, self.character_key, card, index)
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
        self._make_positions_copyable(widget)
        if reset_scroll:
            self._reset_scroll_to_top()

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

    def _manual_page_changed(self) -> None:
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
