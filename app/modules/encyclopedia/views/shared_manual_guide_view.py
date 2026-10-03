from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.modules.encyclopedia.views.guide_ultime_manual_view import (
    GuideManualProgressBar,
    GuideUltimeManualCard,
    GuideUltimeManualView,
)
from app.quest_catalog import normalize_text
from app.ui.components import AtlasButton


class SharedGuideManualCard(GuideUltimeManualCard):
    """Canonical Guide Succès/Lanyel card with inline route semantics."""

    def __init__(self, service, character_key: str, card: dict[str, Any], index: int, parent=None) -> None:
        # Keep the mature manual-card helpers but own the visual composition here:
        # no duplicated location header and no detached combat block above the route.
        QFrame.__init__(self, parent)
        self.service = service
        self.character_key = character_key
        self.card = card
        self.index = index
        self._quest_rows = self._canonical_quest_rows()
        self._shown_quest_map_links: set[tuple[int, str]] = set()
        self._resource_names = self._clickable_resource_names(service, card)
        self._combat_targets = self._quest_combat_targets()
        self._rendered_combat_keys: set[tuple[int, int]] = set()
        self._combat_evidence_cache: dict[tuple[int, int], tuple[str, str]] = {}
        self.setObjectName("GuideManualSheet")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(9)

        if index == 0:
            self._add_legend(root)

        title_text = self._visible_stage_title()
        if title_text:
            title = QLabel(title_text)
            title.setObjectName("GuideManualStageTitle")
            title.setWordWrap(True)
            root.addWidget(title)

        line_provider = getattr(service, "manual_lines_for_card", None)
        manual_lines = (
            line_provider(character_key, card)
            if callable(line_provider)
            else card.get("manual_lines", []) or []
        )
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
            "prepare",
        )
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
            "GuideManualDungeonSection",
            "boss",
        )
        # Defensive fallback: an objective that could only be tied to the current
        # route sheet still stays in the body at combat time, never in the header.
        self._add_unmatched_combats(root)
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
        if not automatic and not blocking:
            self.page_check.setToolTip(
                "Valider cette fiche. La progression automatique reste prioritaire lorsqu’Atlas dispose de la preuve."
            )
            self.page_check.toggled.connect(self._page_toggled)

    def _visible_stage_title(self) -> str:
        """Keep authored action titles, hide redundant route/zone headings."""
        title = " ".join(str(self.card.get("manual_title") or "").split()).strip()
        if not title or normalize_text(title) in {"fiche_de_route", "etape_gps"}:
            return ""
        normalized = normalize_text(title)
        if normalized.startswith("etape_gps"):
            return ""
        for field in ("manual_route_position", "zone", "subzone", "destination"):
            candidate = normalize_text(self.card.get(field))
            if candidate and (normalized == candidate or normalized in candidate):
                return ""
        return title

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

        # The red semantic belongs to the whole preparation section. Individual
        # rows stay transparent so « À préparer » remains one coherent block.
        frame = QFrame()
        frame.setObjectName(
            "GuideManualWarningSection" if section_key == "prepare" else object_name
        )
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

            row_widget = QFrame()
            row_widget.setObjectName("GuideManualLineRow")
            if section_key == "prepare":
                row_widget.setStyleSheet(
                    "QFrame#GuideManualLineRow { background: transparent; border: none; }"
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
            line.setObjectName(
                "GuideManualLine"
                if section_key == "prepare"
                else self._line_object_name(kind, text)
            )
            if section_key == "prepare":
                line.setStyleSheet(
                    "QLabel#GuideManualLine { background: transparent; border: none; padding: 2px 0; }"
                )
            line.setWordWrap(True)
            row_layout.addWidget(line, 1)
            if section_key == "now":
                self._add_inline_quest_links(row_layout, row)
            layout.addWidget(row_widget)

            for target in self._combat_targets_for_row(row, section_key):
                self._add_combat_target(layout, target)

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
        row_text = normalize_text(row.get("text"))
        row_position = self._position_key(str(row.get("position") or ""))
        unseen = [
            target
            for target in self._combat_targets
            if self._combat_key(target) not in self._rendered_combat_keys
        ]
        direct: list[dict[str, Any]] = []
        for target in unseen:
            target_position, objective_text = self._combat_evidence(target)
            monster = normalize_text(target.get("monster"))
            objective = normalize_text(objective_text)
            if monster and monster in row_text:
                direct.append(target)
                continue
            if objective and (objective in row_text or row_text in objective):
                direct.append(target)
                continue
            if (
                section_key == "boss"
                and row_position
                and self._position_key(target_position) == row_position
                and len(unseen) == 1
            ):
                direct.append(target)
        if direct:
            return direct

        # A generated Lanyel combat row is explicitly typed as combat. If the
        # catalogue text was normalized differently, keep a one-to-one fallback.
        if section_key == "boss" or str(row.get("kind") or "") == "combat":
            remaining = [
                target
                for target in unseen
                if self._combat_key(target) not in self._rendered_combat_keys
            ]
            if len(remaining) == 1:
                return remaining
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
        row_layout.setContentsMargins(12, 2, 0, 2)
        row_layout.setSpacing(6)

        quest_id, objective_id = key
        quantity = int(target["quantity"])
        monster = str(target["monster"])
        quest_name = str(target["quest_name"])
        text = f"{quantity} × {monster}"
        if quest_name:
            text += f" — {quest_name}"
        checkbox = QCheckBox(text)
        checkbox.setObjectName("GuideManualCombatCheck")
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
        checkbox.setToolTip("Progression partagée avec l’objectif de la fiche Quête.")
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

    def _add_unmatched_combats(self, root: QVBoxLayout) -> None:
        remaining = [
            target
            for target in self._combat_targets
            if self._combat_key(target) not in self._rendered_combat_keys
        ]
        if not remaining:
            return
        frame = QFrame()
        frame.setObjectName("GuideManualDungeonSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        for target in remaining:
            self._add_combat_target(layout, target)
        root.addWidget(frame)


class SharedGuideManualView(GuideUltimeManualView):
    """Canonical manual road-book renderer reusable by Guide Succès and Lanyel."""

    ROUTE_LOCK_PROGRESS_KEY = "__ui:shared_route_locked__"

    def _build_ui(self) -> None:
        self.filter_mode = "Tout"
        self.navigate_entity = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

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

        # Body navigation: exactly the three actions tied to the current sheet.
        nav = QFrame()
        nav.setObjectName("GuideManualNav")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(8, 4, 8, 6)
        nav_layout.setSpacing(8)
        self.prev_button = QPushButton("← Précédent")
        self.prev_button.setObjectName("GuideManualPrev")
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
        self.next_button = QPushButton("Suivant →")
        self.next_button.setObjectName("GuideManualNextButton")
        self.next_button.clicked.connect(lambda: self.navigate_relative(1))
        nav_layout.addWidget(self.next_button)
        root.addWidget(nav)

        # End/footer: Guide first, then real route progress, persistent lock and
        # pagination at the far right.
        footer = QFrame()
        footer.setObjectName("GuideManualProgressFrame")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 4, 8, 5)
        footer_layout.setSpacing(8)

        self.guide_button = AtlasButton("Guide")
        self.guide_button.setObjectName("GuideManualGuideButton")
        self.guide_button.clicked.connect(
            lambda _checked=False: self._guide_button_clicked()
        )
        footer_layout.addWidget(self.guide_button)

        self.route_bar = GuideManualProgressBar()
        self.route_bar.setObjectName("GuideManualProgress")
        self.route_bar.setTextVisible(False)
        self.route_bar.setFixedHeight(7)
        self.route_bar.navigationRequested.connect(self._jump_from_progress)
        footer_layout.addWidget(self.route_bar, 1)

        self.route_progress_label = QLabel()
        self.route_progress_label.setObjectName("GuideManualPercent")
        footer_layout.addWidget(self.route_progress_label)

        self.route_lock_check = QToolButton()
        self.route_lock_check.setObjectName("GuideManualProgressLock")
        self.route_lock_check.setCheckable(True)
        self.route_lock_check.setMinimumWidth(126)
        self.route_lock_check.toggled.connect(self._route_lock_toggled)
        footer_layout.addWidget(self.route_lock_check)

        self.nav_page_label = QLabel()
        self.nav_page_label.setObjectName("GuideManualNavPage")
        self.nav_page_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.nav_page_label.setMinimumWidth(94)
        footer_layout.addWidget(self.nav_page_label)
        root.addWidget(footer)

        self.progress_details = QLabel()
        self.progress_details.setVisible(False)
        self.position_label = QLabel()
        self.position_label.setVisible(False)
        self._restore_route_lock_state()

    def _restore_route_lock_state(self) -> None:
        locked = False
        if self.character_key:
            locked = bool(
                self.service.manual_checked(
                    self.character_key,
                    self.ROUTE_LOCK_PROGRESS_KEY,
                )
            )
        self.route_lock_check.blockSignals(True)
        self.route_lock_check.setChecked(locked)
        self.route_lock_check.blockSignals(False)
        self._apply_route_lock_visual(locked)

    def _apply_route_lock_visual(self, locked: bool) -> None:
        self.route_lock_check.setText(
            "🔒 Verrouillé" if locked else "🔓 Déverrouillé"
        )
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
        if self.character_key:
            self.service.set_manual_checked(
                self.character_key,
                self.ROUTE_LOCK_PROGRESS_KEY,
                bool(locked),
            )

    def set_character_key(self, character_key: str) -> None:
        super().set_character_key(character_key)
        self._restore_route_lock_state()

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
        )
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
