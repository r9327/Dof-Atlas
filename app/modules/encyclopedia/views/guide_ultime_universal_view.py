from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.modules.encyclopedia.views.guide_ultime_generated_view import GuideUltimeGeneratedView
from app.modules.encyclopedia.views.guide_ultime_walkthrough_card import (
    GuideUltimeWalkthroughCard,
    ObjectiveWalkthrough,
    QuestWalkthroughIndex,
)
from app.ui.components import AtlasButton


SENTINEL_COORD = -2147483648
TRAVEL_COORD_RE = re.compile(r"\[(-?\d+)\s*,\s*(-?\d+)\]")

_GENERIC_GATE_TOKENS = (
    "condition réelle du jeu",
    "condition reelle du jeu",
    "ne prétend pas la valider automatiquement",
    "ne pretend pas la valider automatiquement",
    "condition à vérifier",
    "condition a verifier",
    "hard runtime",
)


class GuideUltimeRouteCard(GuideUltimeWalkthroughCard):
    """One concrete route sheet: where to go and what to do, nothing else."""

    def __init__(
        self,
        service,
        character_key: str,
        card: dict[str, Any],
        index: int,
        *,
        active: bool,
        quest_toggle,
        objective_toggle,
        walkthrough: QuestWalkthroughIndex,
        parent: QWidget | None = None,
    ) -> None:
        QFrame.__init__(self, parent)
        self.service = service
        self.character_key = character_key
        self.card = card
        self.index = index
        self.active = active
        self.compact = False
        self.quest_toggle = quest_toggle
        self.objective_toggle = objective_toggle
        self.walkthrough = walkthrough
        self._ordered_actions_rendered = False

        state = service.card_state(character_key, card, index)
        self.setObjectName("GuideUltimeRouteSheet")
        self.setProperty("state", "active" if active else "done" if state.complete else "future")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 20)
        root.setSpacing(12)

        location = QLabel(self._location_text(card))
        location.setObjectName("GuideRouteLocation")
        location.setWordWrap(True)
        root.addWidget(location)

        self._add_preparation(root)
        self._add_route_actions(root)
        self._add_combat_requirements(root)
        self._add_before_leaving(root)
        self._add_next(root)
        self._add_page_validation(root, state)

    def _add_preparation(self, root: QVBoxLayout) -> None:
        rows: list[str] = []
        for raw in list(self.card.get("a_preparer", []) or []) + list(self.card.get("manual_preparation", []) or []):
            text = self._preparation_text(raw)
            if text:
                rows.append(text)
        for raw in self.card.get("profession_gates", []) or []:
            text = self._gate_text(raw)
            if text and not self._generic_gate(text):
                rows.append(text)
        if not rows:
            return
        body = self._section(root, "À PRÉPARER")
        for text in self._dedupe(rows):
            self._add_plain_line(body, text)

    def _add_route_actions(self, root: QVBoxLayout) -> None:
        ordered: list[tuple[str, dict[str, Any]]] = []
        by_id: dict[str, tuple[str, dict[str, Any]]] = {}
        for section in ("a_prendre", "a_faire_ici"):
            for row in self.card.get(section, []) or []:
                if not isinstance(row, dict):
                    continue
                action_id = str(row.get("action_id") or "").strip()
                if action_id:
                    by_id[action_id] = (section, row)

        seen: set[str] = set()
        for action_id in self.card.get("action_sequence", []) or []:
            found = by_id.get(str(action_id))
            if found is None:
                continue
            ordered.append(found)
            seen.add(str(action_id))
        for action_id, found in by_id.items():
            if action_id not in seen:
                ordered.append(found)

        if not ordered:
            for section in ("a_prendre", "a_faire_ici"):
                ordered.extend(
                    (section, row)
                    for row in self.card.get(section, []) or []
                    if isinstance(row, dict)
                )

        concrete_gates = [
            text
            for raw in self.card.get("hard_runtime_gates", []) or []
            if (text := self._gate_text(raw)) and not self._generic_gate(text)
        ]
        if not ordered and not concrete_gates:
            return

        body = QVBoxLayout()
        body.setContentsMargins(0, 2, 0, 2)
        body.setSpacing(7)
        root.addLayout(body)
        for text in self._dedupe(concrete_gates):
            self._add_plain_line(body, text, important=True)
        for section, row in ordered:
            if section == "a_prendre":
                self._add_start_instruction(body, row)
            else:
                self._add_action_row(body, row, start_rows=False)

    def _add_start_instruction(self, body: QVBoxLayout, row: dict[str, Any]) -> None:
        qid = self._safe_int(row.get("quest_id"))
        name = str(row.get("quest_name") or row.get("title") or "").strip()
        if qid is not None:
            name = self.walkthrough.quest_name(qid) or name or f"Quête #{qid}"
        done = bool(qid is not None and self.service.quest_progress.is_quest_completed(self.character_key, qid))

        npc = position = zone = ""
        if qid is not None:
            npc, position, zone = self.walkthrough.start_details(qid)
        if not position:
            position = self._row_position(row)

        text = f"Prends la quête « {name} »" if name else "Prends la quête indiquée"
        if npc:
            text += f" auprès de {npc}"
        location = self._join_location(position, zone)
        if location:
            text += f" — {location}"
        text += "."

        label = QLabel(("✓ " if done else "• ") + text)
        label.setObjectName("GuideRouteAction")
        label.setProperty("state", "done" if done else "todo")
        label.setWordWrap(True)
        body.addWidget(label)

    def _add_action_row(self, body: QVBoxLayout, row: dict[str, Any], *, start_rows: bool) -> None:
        qid = self._safe_int(row.get("quest_id"))
        oid = self._safe_int(row.get("objective_id"))
        checked = self.service.action_completed(self.character_key, row)
        detail = self.walkthrough.objective(qid, oid) if qid is not None and oid is not None else ObjectiveWalkthrough()
        instruction = detail.text or str(row.get("title") or "Action à faire").strip()
        position = detail.position or self._row_position(row)
        if position:
            instruction = f"{instruction} — {position}"

        label = QLabel(("✓ " if checked else "• ") + instruction)
        label.setObjectName("GuideRouteAction")
        label.setProperty("state", "done" if checked else "todo")
        label.setWordWrap(True)
        body.addWidget(label)

    def _add_combat_requirements(self, root: QVBoxLayout) -> None:
        monster = [
            row for row in self.card.get("succes_monstres_a_faire", []) or []
            if isinstance(row, dict) and str(row.get("name") or "").strip()
        ]
        dungeon = [
            row for row in self.card.get("succes_donjon_a_faire", []) or []
            if isinstance(row, dict) and str(row.get("name") or "").strip()
        ]
        context = self.card.get("dungeon_context") if isinstance(self.card.get("dungeon_context"), dict) else {}
        ocre = [row for row in context.get("ocre_capture_targets", []) or [] if isinstance(row, dict)]
        if not monster and not dungeon and not ocre:
            return

        body = self._section(root, "PENDANT LE COMBAT / DONJON")
        for row in monster + dungeon:
            aid = self._safe_int(row.get("achievement_id"))
            done = bool(
                aid is not None
                and self.service.achievement_progress.is_achievement_completed(self.character_key, aid)
            )
            name = str(row.get("name") or "").strip()
            label = QLabel(f"{'✓' if done else '•'} Fais aussi : {name}.")
            label.setObjectName("GuideRouteAction")
            label.setProperty("state", "done" if done else "todo")
            label.setWordWrap(True)
            body.addWidget(label)
        for row in ocre:
            action = str(row.get("action") or "Capture le boss pour l’Ocre").strip()
            boss = str(row.get("boss") or "").strip()
            text = action
            if boss and boss.casefold() not in action.casefold():
                text += f" — {boss}"
            self._add_plain_line(body, text)

    def _add_before_leaving(self, root: QVBoxLayout) -> None:
        rows = [str(row).strip() for row in self.card.get("avant_de_partir", []) or [] if str(row).strip()]
        if not rows:
            return
        body = self._section(root, "AVANT DE PARTIR")
        for text in self._dedupe(rows):
            self._add_plain_line(body, text)

    def _add_next(self, root: QVBoxLayout) -> None:
        nxt = self.card.get("ensuite") if isinstance(self.card.get("ensuite"), dict) else None
        candidate = nxt
        if candidate is None and self.index + 1 < len(self.service.cards):
            candidate = self.service.cards[self.index + 1]
        if not isinstance(candidate, dict):
            return

        coords = ""
        x = self._safe_int(candidate.get("x"))
        y = self._safe_int(candidate.get("y"))
        if x is not None and y is not None and x != SENTINEL_COORD and y != SENTINEL_COORD:
            coords = f"[{x},{y}]"
        zone = str(candidate.get("subzone") or candidate.get("zone") or candidate.get("destination") or "").strip()
        if not coords and not zone:
            return
        text = "Va " + " — ".join(value for value in (coords, zone) if value) + "."
        label = QLabel("→ " + text)
        label.setObjectName("GuideRouteNext")
        label.setWordWrap(True)
        root.addWidget(label)

    def _add_page_validation(self, root: QVBoxLayout, state) -> None:
        automatic = self.service.card_auto_complete(self.character_key, self.card)
        manual = self.service.page_checked(self.character_key, self.card, self.index)
        checkbox = QCheckBox(
            "FICHE VALIDÉE AUTOMATIQUEMENT"
            if automatic
            else "FICHE TERMINÉE — PASSER À LA SUITE"
        )
        checkbox.setObjectName("GuideRoutePageCheck")
        checkbox.setChecked(bool(automatic or manual))
        checkbox.setEnabled(not automatic)
        if automatic:
            checkbox.setToolTip("La quête / les succès liés sont déjà terminés : aucune validation manuelle nécessaire.")
        else:
            checkbox.setToolTip("Une seule validation manuelle pour toute la fiche.")
            checkbox.toggled.connect(self._page_toggled)
        root.addWidget(checkbox)

    def _page_toggled(self, checked: bool) -> None:
        self.service.set_page_checked(self.character_key, self.card, self.index, bool(checked))
        self.manualChanged.emit()

    @staticmethod
    def _preparation_text(row: Any) -> str:
        if isinstance(row, dict):
            quantity = row.get("quantity")
            name = str(
                row.get("name")
                or row.get("item")
                or row.get("requirement")
                or row.get("note")
                or row.get("instruction")
                or ""
            ).strip()
            if not name:
                return ""
            text = f"{quantity} × {name}" if quantity not in (None, "", 0) else name
            source = str(
                row.get("recommended_source")
                or row.get("acquisition_default")
                or row.get("source")
                or ""
            ).strip()
            return f"{text} — {source}" if source else text
        return str(row or "").strip()

    @staticmethod
    def _gate_text(row: Any) -> str:
        if isinstance(row, dict):
            return str(
                row.get("instruction")
                or row.get("note")
                or row.get("requirement")
                or row.get("name")
                or row.get("criterion")
                or ""
            ).strip()
        return str(row or "").strip()

    @staticmethod
    def _generic_gate(text: str) -> bool:
        value = str(text or "").casefold()
        return not value or any(token in value for token in _GENERIC_GATE_TOKENS)

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for raw in values:
            text = str(raw or "").strip()
            key = " ".join(text.casefold().split())
            if text and key not in seen:
                seen.add(key)
                result.append(text)
        return result

    @staticmethod
    def _add_plain_line(body: QVBoxLayout, text: str, *, important: bool = False) -> None:
        label = QLabel("• " + str(text).strip().rstrip(".") + ".")
        label.setObjectName("GuideRouteImportant" if important else "GuideRouteAction")
        label.setWordWrap(True)
        body.addWidget(label)


class GuideUltimeUniversalView(GuideUltimeGeneratedView):
    """Guide Ultime rendered as a single concrete road-book sheet."""

    backToGuidesRequested = Signal()

    def __init__(self, *args, quest_provider: Any = None, quest_graph: Any = None, **kwargs) -> None:
        self.quest_provider = quest_provider
        self.walkthrough = QuestWalkthroughIndex(quest_provider, quest_graph)
        self.order_combo: QComboBox | None = None
        super().__init__(*args, **kwargs)

    def _build_ui(self) -> None:
        self.filter_mode = "Tout"
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self.breadcrumb = QFrame()
        self.breadcrumb.setObjectName("GuideBreadcrumb")
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb)
        self.breadcrumb_layout.setContentsMargins(8, 5, 8, 5)
        self.breadcrumb_layout.setSpacing(5)
        home = AtlasButton("Guides")
        home.setObjectName("GuideBreadcrumbButton")
        home.clicked.connect(lambda _checked=False: self._return_to_guides_catalog())
        self.breadcrumb_layout.addWidget(home)
        separator = QLabel(">")
        separator.setObjectName("GuideBreadcrumbSeparator")
        self.breadcrumb_layout.addWidget(separator)
        current = QLabel("Guide Ultime")
        current.setObjectName("GuideBreadcrumbCurrent")
        self.breadcrumb_layout.addWidget(current)
        self.breadcrumb_layout.addStretch(1)
        root.addWidget(self.breadcrumb)

        header = QFrame()
        header.setObjectName("GuideRouteHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 8, 14, 8)
        header_layout.setSpacing(8)
        title = QLabel("GUIDE ULTIME — FICHE DE ROUTE")
        title.setObjectName("GuideRouteTitle")
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        self.route_progress_label = QLabel()
        self.route_progress_label.setObjectName("GuideRoutePercent")
        header_layout.addWidget(self.route_progress_label)
        root.addWidget(header)

        self.route_bar = QProgressBar()
        self.route_bar.setObjectName("GuideRouteProgress")
        self.route_bar.setTextVisible(False)
        self.route_bar.setFixedHeight(6)
        root.addWidget(self.route_bar)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("GuideRouteScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.cards_layout = QVBoxLayout(self.content)
        self.cards_layout.setContentsMargins(8, 4, 8, 8)
        self.cards_layout.setSpacing(8)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

        nav = QFrame()
        nav.setObjectName("GuideRouteNav")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(8, 6, 8, 6)
        self.prev_button = QPushButton("← Précédent")
        self.prev_button.clicked.connect(lambda: self.navigate_relative(-1))
        nav_layout.addWidget(self.prev_button)
        nav_layout.addStretch(1)
        self.current_button = QPushButton("Revenir à la fiche actuelle")
        self.current_button.setObjectName("GuideRouteCurrent")
        self.current_button.clicked.connect(self.go_active)
        nav_layout.addWidget(self.current_button)
        nav_layout.addStretch(1)
        self.next_button = QPushButton("Suivant →")
        self.next_button.clicked.connect(lambda: self.navigate_relative(1))
        nav_layout.addWidget(self.next_button)
        root.addWidget(nav)

        self.progress_details = QLabel()
        self.progress_details.setVisible(False)
        self.position_label = QLabel()
        self.position_label.setVisible(False)


    def _return_to_guides_catalog(self) -> None:
        self.backToGuidesRequested.emit()
        parent = self.parentWidget()
        while parent is not None:
            show_home = getattr(parent, "show_home", None)
            if callable(show_home):
                show_home()
                return
            parent = parent.parentWidget()

    def _refresh_header(self) -> None:
        progress = self.service.progress(self.character_key)
        percent = progress.common_percent
        if percent is None:
            self.route_bar.setRange(0, 0)
            self.route_progress_label.setText("Progression indisponible")
        else:
            self.route_bar.setRange(0, max(1, progress.common_total))
            self.route_bar.setValue(min(progress.common_completed, progress.common_total))
            self.route_progress_label.setText(f"{percent} %")

    def _sync_order_combo(self) -> None:
        # L'Ordre n'est jamais demandé dans l'en-tête. Le choix apparaît seulement
        # sur la fiche qui contient la première quête d'Ordre.
        return

    def _first_order_card(self) -> dict[str, Any] | None:
        branches = self.service.route.get("conditional_branches")
        if not isinstance(branches, dict):
            return None
        cards = [row for row in branches.get("order_cards", []) or [] if isinstance(row, dict)]
        if not cards:
            return None
        return min(cards, key=lambda row: self._safe_int(row.get("rank")) or 9999)

    def _card_requires_first_order_choice(self, card: dict[str, Any]) -> bool:
        if self.service.selected_order_name(self.character_key):
            return False
        first = self._first_order_card()
        if first is None:
            return False
        option_ids = {
            qid
            for qid in (self._safe_int(row.get("quest_id")) for row in first.get("options", []) or [] if isinstance(row, dict))
            if qid is not None
        }
        if not option_ids:
            return False
        if option_ids.intersection(self.service.card_quest_ids(card)):
            return True
        for gate in card.get("conditional_branch_gates", []) or []:
            if not isinstance(gate, dict):
                continue
            values = {
                value
                for value in (self._safe_int(raw) for raw in gate.values())
                if value is not None
            }
            if option_ids.intersection(values):
                return True
            gate_type = str(gate.get("gate_type") or "").casefold()
            rank = self._safe_int(gate.get("rank") or gate.get("order_rank") or gate.get("alignment_level"))
            if "order" in gate_type and rank in {1, 20}:
                return True
        return False

    def _add_inline_order_choice(self, card: dict[str, Any]) -> None:
        if not self._card_requires_first_order_choice(card):
            self.order_combo = None
            return
        first = self._first_order_card()
        if first is None:
            return
        frame = QFrame()
        frame.setObjectName("GuideRouteInlineOrder")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 9, 12, 9)
        label = QLabel("Première quête d’Ordre : choisis l’Ordre Bonta que tu garderas jusqu’au rang 100.")
        label.setWordWrap(True)
        layout.addWidget(label, 1)
        combo = QComboBox()
        combo.setObjectName("GuideRouteInlineOrderCombo")
        combo.addItem("Choisir maintenant", "")
        for row in first.get("options", []) or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("order") or "").strip()
            if name:
                combo.addItem(name, name)
        combo.currentIndexChanged.connect(self._inline_order_changed)
        layout.addWidget(combo)
        self.order_combo = combo
        self.cards_layout.addWidget(frame)

    def _inline_order_changed(self, index: int) -> None:
        combo = self.order_combo
        if combo is None:
            return
        value = str(combo.itemData(index) or "").strip()
        if not value:
            return
        self.service.set_bonta_order(self.character_key, value)
        self._refresh_header()
        self._render_window()

    def navigate_relative(self, delta: int) -> None:
        if not self.service.cards:
            return
        self.view_index = max(0, min(len(self.service.cards) - 1, self.view_index + int(delta)))
        self._render_window()

    def _render_window(self) -> None:
        self._clear_cards()
        if not self.service.cards:
            return
        index = max(0, min(self.view_index, len(self.service.cards) - 1))
        card = self.service.cards[index]
        self._add_inline_order_choice(card)
        widget = GuideUltimeRouteCard(
            self.service,
            self.character_key,
            card,
            index,
            active=index == self.active_index,
            quest_toggle=self._set_quest,
            objective_toggle=self._set_objective,
            walkthrough=self.walkthrough,
        )
        widget.manualChanged.connect(self._manual_progress_changed)
        widget.questChanged.connect(self._quest_progress_changed)
        self.cards_layout.addWidget(widget)
        self.cards_layout.addStretch(1)
        self.rendered_card_count = 1
        self.prev_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < len(self.service.cards) - 1)
        self.current_button.setVisible(index != self.active_index)
        self._make_positions_copyable(widget)
        QApplication.processEvents()

    def _quest_progress_changed(self, quest_id: int) -> None:
        previous_active = self.active_index
        self.questProgressChanged.emit(int(quest_id))
        self.active_index = self.service.first_incomplete_index(self.character_key)
        if self.view_index == previous_active and self.active_index != previous_active:
            self.view_index = self.active_index
        self._refresh_header()
        self._render_window()

    def _manual_progress_changed(self) -> None:
        previous_active = self.active_index
        self.active_index = self.service.first_incomplete_index(self.character_key)
        if self.view_index == previous_active and self.active_index != previous_active:
            self.view_index = self.active_index
        self._refresh_header()
        self._render_window()

    def _make_positions_copyable(self, root) -> None:
        if root is None:
            return
        labels = [root] if isinstance(root, QLabel) else []
        labels.extend(root.findChildren(QLabel))
        for label in labels:
            match = TRAVEL_COORD_RE.search(label.text())
            if not match:
                continue
            x = self._safe_int(match.group(1))
            y = self._safe_int(match.group(2))
            if x is None or y is None or x == SENTINEL_COORD or y == SENTINEL_COORD:
                continue
            command = f"/travel {x},{y}"
            label.setProperty("travelCopyEnabled", True)
            label.setProperty("travelCommand", command)
            label.setCursor(Qt.PointingHandCursor)
            label.setToolTip(f"Cliquer pour copier {command}")
            if not bool(label.property("travelEventFilterInstalled")):
                label.installEventFilter(self)
                label.setProperty("travelEventFilterInstalled", True)
            label.style().unpolish(label)
            label.style().polish(label)

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() == QEvent.MouseButtonRelease
            and isinstance(watched, QLabel)
            and bool(watched.property("travelCopyEnabled"))
            and event.button() == Qt.LeftButton
        ):
            command = str(watched.property("travelCommand") or "").strip()
            if command:
                QApplication.clipboard().setText(command)
                watched.setToolTip(f"Copié : {command}")
                event.accept()
                return True
        return super().eventFilter(watched, event)


    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
