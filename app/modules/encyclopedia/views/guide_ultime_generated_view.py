from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.modules.encyclopedia.services.guide_ultime_generated_service import (
    GuideUltimeGeneratedService,
)


QuestToggle = Callable[[int, bool], None]
ObjectiveToggle = Callable[[int, int, bool], None]


class GuideUltimeCard(QFrame):
    manualChanged = Signal()
    questChanged = Signal(int)

    def __init__(
        self,
        service: GuideUltimeGeneratedService,
        character_key: str,
        card: dict[str, Any],
        index: int,
        *,
        active: bool,
        compact: bool,
        quest_toggle: QuestToggle,
        objective_toggle: ObjectiveToggle,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.character_key = character_key
        self.card = card
        self.index = index
        self.active = active
        self.compact = compact
        self.quest_toggle = quest_toggle
        self.objective_toggle = objective_toggle
        state = service.card_state(character_key, card, index)
        self.setObjectName("GuideUltimeCard")
        self.setProperty("state", "active" if active else "done" if state.complete else "future")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(9)

        header = QHBoxLayout()
        level = card.get("planned_at_level")
        title = QLabel(f"NIVEAU {level}" if level else f"CARTE {index + 1}")
        title.setObjectName("GuideUltimeCardLevel")
        header.addWidget(title)
        header.addStretch(1)
        location = self._location_text(card)
        location_label = QLabel(location)
        location_label.setObjectName("GuideUltimeCardLocation")
        location_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(location_label)
        if state.complete:
            badge = QLabel("✓ TERMINÉE")
            badge.setObjectName("GuideUltimeDoneBadge")
            header.addWidget(badge)
        elif active:
            badge = QLabel("CARTE ACTUELLE")
            badge.setObjectName("GuideUltimeActiveBadge")
            header.addWidget(badge)
        root.addLayout(header)

        if compact:
            summary = QLabel(self._compact_summary(state))
            summary.setObjectName("GuideUltimeCompactSummary")
            summary.setWordWrap(True)
            root.addWidget(summary)
            return

        self._add_actions(root, "À PRENDRE", card.get("a_prendre", []), start_rows=True)
        self._add_actions(root, "À FAIRE ICI", card.get("a_faire_ici", []), start_rows=False)
        self._add_progress_also(root)
        self._add_resources(root)
        self._add_runtime(root)
        self._add_before_leaving(root)
        self._add_next(root)

    @staticmethod
    def _location_text(card: dict[str, Any]) -> str:
        coords = ""
        if card.get("x") is not None and card.get("y") is not None:
            coords = f"[{card['x']},{card['y']}]"
        zone = str(card.get("subzone") or card.get("zone") or "").strip()
        if coords and zone:
            return f"{zone}  •  {coords}"
        return zone or coords or str(card.get("destination") or "Destination")

    @staticmethod
    def _compact_summary(state) -> str:
        bits = []
        if state.automatic_total:
            bits.append(f"{state.automatic_done}/{state.automatic_total} objectifs auto")
        if state.manual_total:
            bits.append(f"{state.manual_done}/{state.manual_total} contrôles manuels")
        if state.historical:
            bits.append("progression historique reconnue")
        return " • ".join(bits) or "Aucune action obligatoire restante."

    def _section(self, root: QVBoxLayout, title: str) -> QVBoxLayout:
        label = QLabel(title)
        label.setObjectName("GuideUltimeSectionTitle")
        root.addWidget(label)
        body = QVBoxLayout()
        body.setContentsMargins(4, 0, 0, 0)
        body.setSpacing(5)
        root.addLayout(body)
        return body

    def _add_actions(self, root: QVBoxLayout, title: str, rows: Any, *, start_rows: bool) -> None:
        values = [row for row in (rows or []) if isinstance(row, dict)]
        if not values:
            return
        body = self._section(root, title)
        for row in values:
            qid = self._safe_int(row.get("quest_id"))
            oid = self._safe_int(row.get("objective_id"))
            checked = self.service.action_completed(self.character_key, row)
            text = str(row.get("title") or row.get("quest_name") or "Action")
            line = QCheckBox(text)
            line.setObjectName("GuideUltimeActionCheck")
            line.setChecked(checked)
            line.setProperty("state", "done" if checked else "todo")
            if qid is None:
                line.setEnabled(False)
            elif start_rows or oid is None:
                line.setToolTip("Validation partagée : coche/décoche la quête pour ce personnage.")
                line.toggled.connect(lambda value, quest_id=qid: self._toggle_quest(quest_id, value))
            else:
                line.setToolTip("Objectif partagé avec la fiche Quête. La quête complète reste la source de vérité finale.")
                line.toggled.connect(lambda value, quest_id=qid, objective_id=oid: self._toggle_objective(quest_id, objective_id, value))
            body.addWidget(line)

    def _add_progress_also(self, root: QVBoxLayout) -> None:
        progress = self.card.get("progresse_aussi") if isinstance(self.card.get("progresse_aussi"), dict) else {}
        quest_ids = [self._safe_int(value) for value in progress.get("quest_ids", []) or []]
        quest_ids = [value for value in quest_ids if value is not None]
        monster = [row for row in self.card.get("succes_monstres_a_faire", []) or [] if isinstance(row, dict)]
        dungeon = [row for row in self.card.get("succes_donjon_a_faire", []) or [] if isinstance(row, dict)]
        dungeon_context = self.card.get("dungeon_context") if isinstance(self.card.get("dungeon_context"), dict) else {}
        ocre = [row for row in dungeon_context.get("ocre_capture_targets", []) or [] if isinstance(row, dict)]
        if not quest_ids and not monster and not dungeon and not ocre:
            return
        body = self._section(root, "PROGRESSE AUSSI")
        for qid in quest_ids:
            done = self.service.quest_progress.is_quest_completed(self.character_key, qid)
            label = QLabel(f"{'✓' if done else '•'} Quête #{qid}")
            label.setProperty("state", "done" if done else "todo")
            label.setObjectName("GuideUltimeInfoLine")
            body.addWidget(label)
        for row in monster:
            self._add_success_line(body, row, "Monstres")
        for row in dungeon:
            self._add_success_line(body, row, "Donjon")
        for row in ocre:
            text = str(row.get("action") or "Capture Ocre")
            boss = str(row.get("boss") or "").strip()
            label = QLabel(f"• Ocre : {text}{' — ' + boss if boss else ''}")
            label.setObjectName("GuideUltimeInfoLine")
            label.setWordWrap(True)
            body.addWidget(label)

    def _add_success_line(self, body: QVBoxLayout, row: dict[str, Any], kind: str) -> None:
        aid = self._safe_int(row.get("achievement_id"))
        done = bool(aid is not None and self.service.achievement_progress.is_achievement_completed(self.character_key, aid))
        name = str(row.get("name") or f"Succès #{aid}")
        label = QLabel(f"{'✓' if done else '•'} Succès {kind} — {name}")
        label.setObjectName("GuideUltimeInfoLine")
        label.setProperty("state", "done" if done else "todo")
        label.setWordWrap(True)
        body.addWidget(label)

    def _add_resources(self, root: QVBoxLayout) -> None:
        rows = [row for row in self.card.get("a_preparer", []) or [] if isinstance(row, dict)]
        rows += [row for row in self.card.get("manual_preparation", []) or [] if isinstance(row, dict)]
        if not rows:
            return
        body = self._section(root, "À PRÉPARER")
        for index, row in enumerate(rows):
            key = self.service.resource_key(self.card, row, index, self.index)
            checked = self.service.manual_checked(self.character_key, key)
            quantity = self._safe_int(row.get("quantity")) or 1
            name = str(row.get("name") or "Ressource")
            recommendation = str(row.get("recommended_source") or row.get("acquisition_default") or row.get("source") or "").strip()
            text = f"{quantity} × {name}"
            if recommendation:
                text += f" — {recommendation}"
            line = QCheckBox(text)
            line.setObjectName("GuideUltimeResourceCheck")
            line.setChecked(checked)
            line.setProperty("state", "done" if checked else "todo")
            line.setToolTip("État propre au Guide Ultime. Ne valide jamais une quête.")
            line.toggled.connect(lambda value, manual_key=key: self._toggle_manual(manual_key, value))
            body.addWidget(line)

    def _add_runtime(self, root: QVBoxLayout) -> None:
        sections = (
            ("hard_runtime_gates", "CONDITIONS RUNTIME"),
            ("profession_gates", "MÉTIERS OBLIGATOIRES"),
        )
        for field, title in sections:
            rows = list(self.card.get(field, []) or [])
            if not rows:
                continue
            body = self._section(root, title)
            for index, row in enumerate(rows):
                key = self.service.manual_action_key(self.card, field, index, self.index)
                checked = self.service.manual_checked(self.character_key, key)
                if isinstance(row, dict):
                    text = str(row.get("instruction") or row.get("note") or row.get("criterion") or row.get("name") or "Condition à vérifier")
                else:
                    text = str(row)
                line = QCheckBox(text)
                line.setObjectName("GuideUltimeManualCheck")
                line.setChecked(checked)
                line.setWordWrap(True) if hasattr(line, "setWordWrap") else None
                line.toggled.connect(lambda value, manual_key=key: self._toggle_manual(manual_key, value))
                body.addWidget(line)

    def _add_before_leaving(self, root: QVBoxLayout) -> None:
        rows = list(self.card.get("avant_de_partir", []) or [])
        if not rows:
            return
        body = self._section(root, "AVANT DE PARTIR")
        for index, row in enumerate(rows):
            key = self.service.manual_action_key(self.card, "avant_de_partir", index, self.index)
            checked = self.service.manual_checked(self.character_key, key)
            line = QCheckBox(str(row))
            line.setObjectName("GuideUltimeManualCheck")
            line.setChecked(checked)
            line.toggled.connect(lambda value, manual_key=key: self._toggle_manual(manual_key, value))
            body.addWidget(line)

    def _add_next(self, root: QVBoxLayout) -> None:
        nxt = self.card.get("ensuite") if isinstance(self.card.get("ensuite"), dict) else None
        if not nxt:
            return
        body = self._section(root, "ENSUITE")
        coords = ""
        if nxt.get("x") is not None and nxt.get("y") is not None:
            coords = f"[{nxt['x']},{nxt['y']}] "
        label = QLabel(f"→ {coords}{nxt.get('subzone') or nxt.get('zone') or nxt.get('destination') or ''}")
        label.setObjectName("GuideUltimeNextLine")
        body.addWidget(label)

    def _toggle_quest(self, quest_id: int, value: bool) -> None:
        self.quest_toggle(int(quest_id), bool(value))
        self.questChanged.emit(int(quest_id))

    def _toggle_objective(self, quest_id: int, objective_id: int, value: bool) -> None:
        self.objective_toggle(int(quest_id), int(objective_id), bool(value))
        self.questChanged.emit(int(quest_id))

    def _toggle_manual(self, key: str, value: bool) -> None:
        self.service.set_manual_checked(self.character_key, key, bool(value))
        self.manualChanged.emit()

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class GuideUltimeGeneratedView(QWidget):
    questProgressChanged = Signal(int)

    WINDOW_BEFORE = 2
    WINDOW_AFTER = 4

    def __init__(
        self,
        service: GuideUltimeGeneratedService,
        *,
        character_key: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GuideUltimeGeneratedView")
        self.service = service
        self.character_key = character_key or ""
        self.active_index = 0
        self.view_index = 0
        self.filter_mode = "À faire"
        self.rendered_card_count = 0
        self._build_ui()
        self.refresh(reset_to_active=True)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.progress_frame = QFrame()
        self.progress_frame.setObjectName("GuideUltimeProgressHeader")
        progress_layout = QVBoxLayout(self.progress_frame)
        progress_layout.setContentsMargins(14, 12, 14, 12)
        progress_layout.setSpacing(6)

        top = QHBoxLayout()
        title = QLabel("GUIDE ULTIME")
        title.setObjectName("GuideUltimeTitle")
        top.addWidget(title)
        top.addStretch(1)
        self.route_progress_label = QLabel()
        self.route_progress_label.setObjectName("GuideUltimeProgressText")
        top.addWidget(self.route_progress_label)
        progress_layout.addLayout(top)

        self.route_bar = QProgressBar()
        self.route_bar.setObjectName("GuideUltimeProgressBar")
        self.route_bar.setTextVisible(False)
        self.route_bar.setFixedHeight(8)
        progress_layout.addWidget(self.route_bar)

        self.progress_details = QLabel()
        self.progress_details.setObjectName("GuideUltimeProgressDetails")
        self.progress_details.setWordWrap(True)
        progress_layout.addWidget(self.progress_details)

        branch_row = QHBoxLayout()
        self.class_status = QLabel()
        self.class_status.setObjectName("GuideUltimeBranchStatus")
        branch_row.addWidget(self.class_status)
        self.order_label = QLabel("Ordre Bonta :")
        self.order_label.setObjectName("GuideUltimeBranchStatus")
        branch_row.addWidget(self.order_label)
        self.order_combo = QComboBox()
        self.order_combo.setObjectName("GuideUltimeOrderCombo")
        self.order_combo.setMinimumWidth(190)
        self.order_combo.currentIndexChanged.connect(self._order_changed)
        branch_row.addWidget(self.order_combo)
        branch_row.addStretch(1)
        progress_layout.addLayout(branch_row)
        root.addWidget(self.progress_frame)

        nav = QFrame()
        nav.setObjectName("GuideUltimeNav")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(8, 6, 8, 6)
        nav_layout.setSpacing(6)
        self.prev_button = QToolButton()
        self.prev_button.setText("←")
        self.prev_button.setToolTip("Carte précédente")
        self.prev_button.clicked.connect(lambda: self.navigate_relative(-1))
        nav_layout.addWidget(self.prev_button)
        self.current_button = QPushButton("Premier objectif non terminé")
        self.current_button.setObjectName("GuideUltimeCurrentButton")
        self.current_button.clicked.connect(self.go_active)
        nav_layout.addWidget(self.current_button)
        self.next_button = QToolButton()
        self.next_button.setText("→")
        self.next_button.setToolTip("Carte suivante")
        self.next_button.clicked.connect(lambda: self.navigate_relative(1))
        nav_layout.addWidget(self.next_button)
        nav_layout.addStretch(1)
        self.position_label = QLabel()
        self.position_label.setObjectName("GuideUltimePosition")
        nav_layout.addWidget(self.position_label)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Tout", "À faire", "Terminé"])
        self.filter_combo.setCurrentText(self.filter_mode)
        self.filter_combo.currentTextChanged.connect(self._filter_changed)
        nav_layout.addWidget(self.filter_combo)
        root.addWidget(nav)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("GuideUltimeScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName("GuideUltimeContent")
        self.cards_layout = QVBoxLayout(self.content)
        self.cards_layout.setContentsMargins(2, 2, 2, 12)
        self.cards_layout.setSpacing(8)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)


    def set_character_key(self, character_key: str) -> None:
        self.character_key = character_key or ""
        self.refresh(reset_to_active=True)

    def refresh_external_progress(self) -> None:
        # refresh() owns progress reloading. Calling the service here as well
        # caused two complete reload passes for every external progress event.
        self.refresh(reset_to_active=False)

    def refresh(self, *, reset_to_active: bool = False) -> None:
        self.service.reload_progress()
        if not self.service.available:
            self._render_missing_data()
            return
        self.active_index = self.service.first_incomplete_index(self.character_key)
        if reset_to_active or not (0 <= self.view_index < len(self.service.cards)):
            self.view_index = self.active_index
        self._sync_order_combo()
        self._refresh_header()
        self._render_window()

    def go_active(self) -> None:
        self.active_index = self.service.first_incomplete_index(self.character_key)
        self.view_index = self.active_index
        self._render_window()

    def navigate_relative(self, delta: int) -> None:
        if not self.service.cards:
            return
        target = self.view_index + int(delta)
        direction = 1 if delta >= 0 else -1
        while 0 <= target < len(self.service.cards):
            state = self.service.card_state(self.character_key, self.service.cards[target], target)
            if self.filter_mode == "Tout" or (self.filter_mode == "À faire" and not state.complete) or (self.filter_mode == "Terminé" and state.complete):
                self.view_index = target
                self._render_window()
                return
            target += direction

    def _filter_changed(self, value: str) -> None:
        self.filter_mode = str(value or "Tout")
        self._render_window()

    def _refresh_header(self) -> None:
        progress = self.service.progress(self.character_key)
        percent = progress.common_percent
        if percent is None:
            self.route_bar.setRange(0, 0)
            self.route_progress_label.setText("Route commune — progression indisponible")
        else:
            self.route_bar.setRange(0, max(1, progress.common_total))
            self.route_bar.setValue(min(progress.common_completed, progress.common_total))
            self.route_progress_label.setText(f"{percent} %")
        details = [f"{progress.common_completed} / {progress.common_total} quêtes de la route commune"]
        if progress.qq_required:
            details.append(f"QQ : {progress.qq_completed} / {progress.qq_required} quêtes validées")
        if progress.full_success_total:
            details.append(f"FULL SUCCÈS ciblés : {progress.full_success_completed} / {progress.full_success_total}")
        details.append(f"Branches : classe {progress.class_completed}/{progress.class_total or 1} • Ordre {progress.order_completed}/{progress.order_total}")
        self.progress_details.setText("   •   ".join(details))

        inferred = self.service.inferred_class_option(self.character_key)
        if inferred is not None:
            self.class_status.setText(f"Classe : {inferred.get('class')} ✓")
        else:
            class_done = progress.class_completed > 0
            self.class_status.setText("Classe : quête reconnue ✓" if class_done else "Classe : carte conditionnelle à faire")

    def _sync_order_combo(self) -> None:
        selected = self.service.selected_order_name(self.character_key)
        allowed = self.service.bonta_order_names()
        self.order_combo.blockSignals(True)
        self.order_combo.clear()
        self.order_combo.addItem("Choisir un Ordre", "")
        for name in allowed:
            self.order_combo.addItem(name, name)
        target = self.order_combo.findData(selected) if selected else 0
        self.order_combo.setCurrentIndex(max(0, target))
        self.order_combo.blockSignals(False)

    def _order_changed(self, index: int) -> None:
        value = str(self.order_combo.itemData(index) or "").strip()
        if not value:
            return
        self.service.set_bonta_order(self.character_key, value)
        self._refresh_header()
        self._render_window()

    def _render_missing_data(self) -> None:
        self._clear_cards()
        frame = QFrame()
        frame.setObjectName("GuideUltimeMissing")
        layout = QVBoxLayout(frame)
        title = QLabel("Guide Ultime V5 indisponible")
        title.setObjectName("GuideUltimeTitle")
        layout.addWidget(title)
        text = QLabel(
            "Le moteur UI ne régénère pas la route. Le fichier source attendu est :\n"
            f"{self.service.route_path}\n\n"
            "Génère/replace guide_ultime_gps_route.json via le pipeline V5 STRICT puis rouvre le module."
        )
        text.setWordWrap(True)
        text.setObjectName("GuideUltimeProgressDetails")
        layout.addWidget(text)
        self.cards_layout.addWidget(frame)
        self.cards_layout.addStretch(1)
        self.rendered_card_count = 0
        self.route_bar.setRange(0, 1)
        self.route_bar.setValue(0)
        self.route_progress_label.setText("Source V5 absente")
        self.progress_details.setText("Aucune progression inventée.")

    def _visible_indices(self) -> list[int]:
        if not self.service.cards:
            return []
        start = max(0, self.view_index - self.WINDOW_BEFORE)
        stop = min(len(self.service.cards), self.view_index + self.WINDOW_AFTER + 1)
        result: list[int] = []
        for index in range(start, stop):
            state = self.service.card_state(self.character_key, self.service.cards[index], index)
            if self.filter_mode == "À faire" and state.complete and index != self.view_index:
                continue
            if self.filter_mode == "Terminé" and not state.complete and index != self.view_index:
                continue
            result.append(index)
        if self.view_index not in result:
            result.append(self.view_index)
            result.sort()
        return result

    def _render_window(self) -> None:
        self._clear_cards()
        if not self.service.cards:
            return
        indices = self._visible_indices()
        for index in indices:
            card = self.service.cards[index]
            state = self.service.card_state(self.character_key, card, index)
            active = index == self.active_index
            compact = index != self.view_index and not active
            widget = GuideUltimeCard(
                self.service,
                self.character_key,
                card,
                index,
                active=active,
                compact=compact,
                quest_toggle=self._set_quest,
                objective_toggle=self._set_objective,
            )
            widget.manualChanged.connect(self._manual_progress_changed)
            widget.questChanged.connect(self._quest_progress_changed)
            self.cards_layout.addWidget(widget)
        self.cards_layout.addStretch(1)
        self.rendered_card_count = len(indices)
        self.position_label.setText(
            f"Carte {self.view_index + 1} / {len(self.service.cards)}  •  active {self.active_index + 1}"
        )
        self.prev_button.setEnabled(self.view_index > 0)
        self.next_button.setEnabled(self.view_index < len(self.service.cards) - 1)

    def _set_quest(self, quest_id: int, completed: bool) -> None:
        self.service.quest_progress.set_quest_completed(self.character_key, int(quest_id), bool(completed))
        self.service.achievement_progress.sync_from_quest_progress(
            self.character_key,
            getattr(self, "achievement_provider", None) or _NullAchievementProvider(),
            self.service.quest_progress,
        ) if False else None

    def _set_objective(self, quest_id: int, objective_id: int, completed: bool) -> None:
        self.service.quest_progress.set_objective_completed(
            self.character_key, int(quest_id), int(objective_id), bool(completed)
        )

    def _quest_progress_changed(self, quest_id: int) -> None:
        self.questProgressChanged.emit(int(quest_id))
        self.active_index = self.service.first_incomplete_index(self.character_key)
        self._refresh_header()
        self._render_window()

    def _manual_progress_changed(self) -> None:
        self.active_index = self.service.first_incomplete_index(self.character_key)
        self._refresh_header()
        self._render_window()

    def _clear_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()



class _NullAchievementProvider:
    def load_retained(self):
        return ()
