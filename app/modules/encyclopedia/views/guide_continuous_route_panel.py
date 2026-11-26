"""Compact, source-only manual progress panel for continuous Ganymède routes.

No invented quest completion, preparation quantities, Zaap claims or automatic
progression. Sommaire stays open until the user explicitly closes it.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from app.constants import DATA_DIR
from app.core.character_identity import is_character_key
from app.core.map_coordinates import exact_map_coordinates
from app.core.numbers import clamped_percent
from app.modules.encyclopedia.services.guide_continuous_navigation import (
    ContinuousGuideNavigation,
)
from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    certified_payload_sha256,
)
from app.modules.encyclopedia.services.guide_continuous_preparation import (
    visible_object_references,
)
from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.services.guide_participant_service import connected_travel_recipients
from app.ui.components import (
    AtlasGuideReadingHeader, AtlasGuideParticipantPortrait, configure_unity_scroll_area, configure_unity_tool_button,
)
from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX


ROUTE_GEOMETRY = UNITY_MODULE_GEOMETRY_PX["guide_route"]


class ContinuousGuideRoutePanel(QWidget):
    selectedCharactersChanged = Signal(tuple)
    travelRequested = Signal(str, tuple)

    def __init__(
        self,
        route: Mapping[str, object],
        progress: GuideProgressService,
        character_keys: Iterable[str] = (),
        parent: QWidget | None = None,
        *,
        available_characters: Iterable[object] = (),
        verified_travel_plans: Mapping[str, Mapping[str, object]] | None = None,
        available_characters_provider: Callable[[], Iterable[object]] | None = None,
        guide_title: str = "",
        image_path: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GuideContinuousRoutePanel")
        self.route = route
        self.navigation = ContinuousGuideNavigation(route, progress, character_keys)
        self.rows = route["sections"][0]["steps"]
        # A plan produced for a previous source edition must not send commands
        # against today's steps, even when their stable step IDs were reused.
        self._source_payload_sha256 = certified_payload_sha256(dict(route))
        # Runtime-only planner overlay. Never trust a similarly named field
        # inside Ganymède's imported/signed source JSON.
        self._verified_travel_plans = self._snapshot_travel_plans(verified_travel_plans or {})
        # Only expose registered stable Atlas characters, including offline
        # ones. A removed window must not silently deselect its character.
        self.available_characters = tuple(
            row for row in available_characters
            if is_character_key(getattr(row, "key", ""))
        )
        self._available_characters_provider = available_characters_provider
        self._character_actions = {}
        self.character_icon_buttons = {}
        self._preparation_open = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(7)
        title = guide_title or str(route.get("title") or "Guide")
        self.compact_header = AtlasGuideReadingHeader(
            title, image_path=image_path, category="dofus" if "dofus" in title.casefold() else "guide",
        )
        header = self.compact_header
        header.set_summary_provider(lambda: tuple(
            self._sheet_title(index) for index in range(len(self.rows))
        ))
        header.summaryRequested.connect(lambda index: self.show_step(self.navigation.step_ids[index]))
        self.position_label = QLabel()
        self.position_label.setObjectName("GuideContinuousPosition")
        self.position_label.setTextFormat(Qt.PlainText)
        header.title_row.insertWidget(header.title_row.count() - 1, self.position_label)
        self.participants_button = header.participants_button
        # Keep the existing verified-identity menu, not a second title row.
        self.participants_button.setCheckable(False)
        self.participants_button.setPopupMode(QToolButton.InstantPopup)
        self._characters_menu = QMenu(self.participants_button)
        self.participants_button.setMenu(self._characters_menu)
        for character in self.available_characters:
            if character.key in self._character_actions:
                continue
            title = str(getattr(character, "label", "") or character.key)
            if getattr(character, "connected", False) is False:
                title += " (hors ligne)"
            action = self._characters_menu.addAction(title)
            action.setCheckable(True)
            action.toggled.connect(
                lambda checked, key=character.key: self._character_toggled(key, checked)
            )
            self._character_actions[character.key] = action
        if not self._character_actions:
            empty = self._characters_menu.addAction("Aucun personnage identifié")
            empty.setEnabled(False)
        portraits = header.participants_layout
        for character in self.available_characters:
            if character.key in self.character_icon_buttons:
                continue
            button = AtlasGuideParticipantPortrait(character.key, progress=None)
            button.setToolTip(str(getattr(character, "label", "") or character.key))
            class_key = str(getattr(character, "class_key", "") or "").strip().lower()
            if class_key.isascii() and class_key.isalpha():
                image_path = DATA_DIR / "images" / "classes" / f"{class_key}.png"
                icon = QIcon(str(image_path))
                if not icon.isNull():
                    button.setIcon(icon)
                    button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            if button.icon().isNull():
                button.setText(button.toolTip()[:1].upper() or "?")
            button.toggled.connect(
                lambda checked, key=character.key: self._character_toggled(key, checked)
            )
            self.character_icon_buttons[character.key] = button
            portraits.addWidget(button)
        if self.character_icon_buttons:
            portraits.addStretch(1)
            header.participants_panel.show()
        work = QHBoxLayout()
        work.setSpacing(9)
        content = QFrame()
        content.setObjectName("GuideContinuousCard")
        detail = QVBoxLayout(content)
        detail.setContentsMargins(8, 8, 8, 8)
        detail.setSpacing(6)
        self.title_label = QLabel()
        self.title_label.setObjectName("GuideContinuousTitle")
        self.title_label.setTextFormat(Qt.PlainText)
        self.title_label.setWordWrap(True)
        detail.addWidget(self.title_label)
        self.body_label = QLabel()
        self.body_label.setObjectName("GuideContinuousActions")
        self.body_label.setTextFormat(Qt.PlainText)
        self.body_label.setWordWrap(True)
        detail.addWidget(self.body_label)
        # Bounded, optional view: even a guide with dozens of object hints
        # must not push step navigation out of the visible window.
        self.preparation_toggle = header.preparation_button
        self.preparation_toggle.setText("À préparer")
        header.set_preparation_description(
            "Références d'objets à vérifier — quantités et achats non certifiés"
        )
        self.preparation_scroll = configure_unity_scroll_area(QScrollArea())
        self.preparation_scroll.setObjectName("GuideContinuousPreparationScroll")
        self.preparation_scroll.setMaximumHeight(ROUTE_GEOMETRY["detail_max_height"])
        self.preparation_label = QLabel()
        self.preparation_label.setObjectName("GuideContinuousPreparationItems")
        self.preparation_label.setTextFormat(Qt.PlainText)
        self.preparation_label.setWordWrap(True)
        self.preparation_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.preparation_scroll.setWidget(self.preparation_label)
        self.progress_label = QLabel()
        self.progress_label.setObjectName("GuideContinuousProgress")
        self.progress_label.setWordWrap(True)
        detail.addWidget(self.progress_label)
        detail.addStretch(1)

        nav = QHBoxLayout()
        self.previous_button = self._button("Précédent", "GuideContinuousPrevious")
        self.previous_button.clicked.connect(self.previous_step)
        nav.addWidget(self.previous_button)
        self.next_button = self._button("Suivant", "GuideContinuousNext")
        self.next_button.clicked.connect(self.next_step)
        nav.addWidget(self.next_button)
        self.actual_button = self._button("Actuelle", "GuideContinuousActual")
        self.actual_button.clicked.connect(self.show_actual)
        nav.addWidget(self.actual_button)
        self.travel_button = self._button("Aller à l'étape", "GuideContinuousTravel")
        self.travel_button.clicked.connect(self.request_current_travel)
        self.travel_button.setToolTip(
            "Déplacement indisponible sans trajet vérifié et participants identifiés"
        )
        self.validate_button = self._button("Valider", "GuideContinuousValidate")
        self.validate_button.setCheckable(True)
        self.validate_button.setToolTip(
            "Cocher/décocher manuellement cette fiche pour les personnages sélectionnés"
        )
        self.validate_button.clicked.connect(self.toggle_manual_current)
        nav.addWidget(self.validate_button)
        detail.addLayout(nav)
        # The four navigation controls stay in one compact row; the travel
        # action has its own width so it cannot squeeze or overlap them.
        detail.addWidget(self.travel_button)
        work.addWidget(content, 3)

        self.global_progress_bar = header.global_progress_bar
        self.global_progress_value = header.global_progress_label
        self.preparation_bar = header.preparation_bar
        self.preparation_bar.setRange(0, 1)
        self.preparation_bar.setValue(0)
        self.preparation_bar.setToolTip(
            "Préparation non certifiée : uniquement des références indicatives"
        )
        self.preparation_toggle.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.participants_button.setToolTip("Sélectionner les personnages")
        self.participants_button.setAccessibleName("Personnages")
        header.global_details_rows.hide()
        # The parent disclosure is the only entry point to Préparation and
        # Sommaire, exactly as in the optimized reader and Dev UI.
        header.attach_preparation(self.preparation_scroll)
        self.preparation_toggle.toggled.connect(self._on_preparation_toggled)
        layout.insertWidget(0, header)
        layout.addLayout(work, 1)
        self.navigation.show_actual()
        self.refresh()

    def _sheet_title(self, index: int) -> str:
        return str(self.rows[index].get("title") or "").strip() or f"Fiche {index + 1}"

    @staticmethod
    def _button(text: str, name: str) -> QToolButton:
        return configure_unity_tool_button(
            QToolButton(), object_name=name, text=text, pointing=True,
        )

    def toggle_preparation(self) -> None:
        if self.preparation_toggle.isEnabled():
            self.preparation_toggle.setChecked(not self.preparation_toggle.isChecked())

    def _on_preparation_toggled(self, opened: bool) -> None:
        self._preparation_open = opened
        self.preparation_scroll.setVisible(
            opened and self.preparation_toggle.isEnabled()
        )
        # Disclosure accessibility and direction are owned by the shared header.

    def set_characters(self, character_keys: Iterable[str]) -> None:
        previous = self.navigation.selected_character_keys
        self.navigation.select_characters(character_keys)
        if self.navigation.selected_character_keys != previous:
            # A previous action plan is scoped to the old participant
            # selection, even if the user later selects the same team again.
            self._verified_travel_plans.clear()
        self.refresh()

    def _character_toggled(self, character_key: str, checked: bool) -> None:
        if character_key not in self._character_actions:
            return
        keys = list(self.navigation.selected_character_keys)
        if checked and character_key not in keys:
            keys.append(character_key)
        elif not checked:
            keys = [key for key in keys if key != character_key]
        self.set_characters(keys)
        self.selectedCharactersChanged.emit(self.navigation.selected_character_keys)

    def show_step(self, step_id: str) -> None:
        self.navigation.show_step(step_id)
        self.refresh()

    def show_actual(self) -> None:
        self.navigation.show_actual()
        self.refresh()

    def previous_step(self) -> None:
        self.navigation.previous_step()
        self.refresh()

    def next_step(self) -> None:
        self.navigation.next_step()
        self.refresh()

    def toggle_manual_current(self) -> None:
        step_id = self.navigation.viewed_step_id
        if step_id is None or not self.navigation.selected_character_keys:
            return
        all_done = all(
            self.navigation.progress.is_manual_step_completed(
                key, self.navigation.guide_id, step_id,
            ) for key in self.navigation.selected_character_keys
        )
        self.navigation.mark_manual_step(step_id, not all_done)
        self.refresh()

    @staticmethod
    def _exact_coordinates(value: object) -> tuple[int, int] | None:
        return exact_map_coordinates(value)

    @staticmethod
    def _snapshot_travel_plans(plans: Mapping[str, Mapping[str, object]]) -> dict:
        # A caller modifying its payload after publication must not change an
        # already authorized command. New evidence requires a new publication.
        return {key: deepcopy(dict(plan)) for key, plan in plans.items()
                if isinstance(key, str) and isinstance(plan, Mapping)}

    def set_verified_travel_plans(
        self, plans: Mapping[str, Mapping[str, object]],
    ) -> None:
        """Replace only the in-memory Atlas planner overlay, then refresh."""
        if not isinstance(plans, Mapping):
            raise ValueError("Verified travel plans must be a mapping")
        self._verified_travel_plans = self._snapshot_travel_plans(plans)
        self.refresh()

    def apply_projected_runtime_plan(self, projection: Mapping[str, object]) -> bool:
        """Bind a matching #226 projection; clear stale commands on mismatch."""
        valid = (
            isinstance(projection, Mapping)
            and projection.get("status") == "TRUSTED_SOURCE_STEPS_MANUAL_ONLY"
            and projection.get("atlas_guide_id") == self.navigation.guide_id
            and projection.get("source_payload_sha256") == self._source_payload_sha256
            and projection.get("selected_character_keys")
            == list(self.navigation.selected_character_keys)
            and isinstance(projection.get("runtime_verified_travel_plans"), Mapping)
        )
        if not valid:
            self.set_verified_travel_plans({})
            return False
        self.set_verified_travel_plans(projection["runtime_verified_travel_plans"])
        return True

    def _travel_availability(self) -> tuple[tuple[str, tuple[str, ...]] | None, str]:
        """Evaluate the current evidence once for the UI and for dispatch."""
        step_id = self.navigation.viewed_step_id
        selected = self.navigation.selected_character_keys
        registered = {row.key for row in self.available_characters}
        if not step_id:
            return None, "Aucune fiche sélectionnée"
        if not selected or any(key not in registered for key in selected):
            return None, "Sélectionnez des personnages identifiés"
        if any(
            self.navigation.progress.is_manual_step_completed(
                key, self.navigation.guide_id, step_id,
            ) for key in selected
        ):
            # A projection computed before the participant checked this step
            # must never move that participant again with the whole team.
            return None, "La fiche est déjà validée pour un personnage sélectionné"
        # Source step dicts can contain arbitrary imported metadata. They must
        # never enable game input without an independently supplied runtime plan.
        plan = self._verified_travel_plans.get(step_id)
        if (not isinstance(plan, Mapping)
                or plan.get("atlas_guide_id") != self.navigation.guide_id
                or plan.get("source_step_id") != step_id
                or plan.get("source_payload_sha256") != self._source_payload_sha256):
            return None, "Aucun trajet vérifié pour cette fiche"
        keys = plan.get("participant_keys")
        if (not isinstance(keys, (list, tuple))
                or tuple(keys) != selected):
            # A stale plan for a different selection must never be broadcast.
            return None, "Le trajet doit être recalculé pour les personnages sélectionnés"
        if not isinstance(plan.get("evidence"), str) or not plan["evidence"].strip():
            return None, "Source du trajet non vérifiée"
        # Preserve offline identities for manual progress, but do not send
        # game input to an old connected snapshot. Re-read the verified
        # participant inventory only when a signed travel plan is usable.
        try:
            rows = (
                self._available_characters_provider()
                if callable(self._available_characters_provider)
                else self.available_characters
            )
            online = connected_travel_recipients(rows, selected)
        except ValueError:
            return None, "Identité de connexion ambiguë"
        except Exception:
            from app.core.logger import get_runtime_logger
            get_runtime_logger().exception("Guide participant connection lookup failed")
            return None, "État de connexion indisponible"
        if online != selected:
            return None, "Un ou plusieurs personnages sélectionnés sont hors ligne"
        destination = self._exact_coordinates(plan.get("destination"))
        if destination is None:
            return None, "Coordonnées de destination non vérifiées"
        command = f"/travel {destination[0]},{destination[1]}"
        explanation = f"Envoyer {command} aux personnages sélectionnés"
        mode = plan.get("mode")
        if mode == "direct":
            if plan.get("zaap") is not None:
                return None, "Trajet direct incohérent"
        elif mode == "zaap_then_travel":
            zaap = self._exact_coordinates(plan.get("zaap"))
            if (zaap is None or not isinstance(plan.get("world"), str)
                    or not plan["world"].strip()):
                return None, "Zaap ou monde de destination non vérifié"
            # The planner establishes the layout of a route. The current
            # capture confirms identity only, so use the exact destination
            # without assuming that the group can use this Zaap.
            explanation = f"Zaap non confirmé en jeu. {explanation}."
        else:
            return None, "Mode de déplacement non vérifié"
        return (command, selected), explanation

    def _sync_travel_button(self) -> tuple[str, tuple[str, ...]] | None:
        request, explanation = self._travel_availability()
        self.travel_button.setEnabled(request is not None)
        self.travel_button.setToolTip(explanation)
        self.travel_button.setAccessibleDescription(explanation)
        return request

    def refresh_connection_state(self) -> None:
        """Refresh live action availability without rebuilding the current sheet."""
        self._sync_travel_button()

    def request_current_travel(self) -> None:
        # A disconnect between paint and click must also update the button.
        request = self._sync_travel_button()
        if request is not None:
            self.travelRequested.emit(*request)

    def refresh(self) -> None:
        position = self.navigation.position()
        total_checks = position.total_steps * len(position.selected_character_keys)
        completed_checks = sum(position.completed_by_character.values())
        percent = clamped_percent(completed_checks, total_checks)
        self.global_progress_bar.setValue(percent)
        self.global_progress_value.setText(
            f"{percent} %" if total_checks else "—"
        )
        selected = set(position.selected_character_keys)
        self.participants_button.setText(f"Mes personnages ({len(selected)})")
        self.participants_button.setAccessibleName(self.participants_button.text())
        for key, action in self._character_actions.items():
            with QSignalBlocker(action):
                if action.isChecked() != (key in selected):
                    action.setChecked(key in selected)
        for key, button in self.character_icon_buttons.items():
            button.set_progress(
                self.navigation.completed_count(key), position.total_steps
            )
            with QSignalBlocker(button):
                if button.isChecked() != (key in selected):
                    button.setChecked(key in selected)
        current = position.viewed_step_id
        actual = position.actual_step_id
        self.actual_button.setEnabled(actual is not None)
        self.validate_button.setEnabled(
            current is not None and bool(position.selected_character_keys)
        )
        self.validate_button.setVisible(current is not None)
        all_validated = bool(current and position.selected_character_keys) and all(
            self.navigation.progress.is_manual_step_completed(
                key, self.navigation.guide_id, current,
            ) for key in position.selected_character_keys
        )
        self.validate_button.setChecked(all_validated)
        self.validate_button.setText("Valider")
        self.validate_button.setToolTip(
            "Annuler la validation manuelle de cette fiche pour les personnages sélectionnés"
            if all_validated else
            "Valider manuellement cette fiche pour les personnages sélectionnés"
        )
        self._sync_travel_button()
        if current is None:
            self.title_label.setText("Aucune fiche sélectionnée")
            self.body_label.setText(
                "Sélectionnez un personnage pour accéder à l’étape actuelle."
                if position.status == "NO_SELECTED_CHARACTER"
                else "Toutes les fiches du parcours sont terminées."
            )
            index = -1
        else:
            index = self.navigation.step_ids.index(current)
            row = self.rows[index]
            self.title_label.setText(self._sheet_title(index))
            self.body_label.setText(str(row.get("content") or
                                        "Actions de cette étape non renseignées."))
        references = (
            visible_object_references(self.route, current) if current else ()
        )
        self.preparation_toggle.setText(f"À préparer ({len(references)})")
        self.compact_header.preparation_caption.setText(f"Préparation ({len(references)})")
        self.preparation_toggle.setEnabled(bool(references))
        self.compact_header.set_metric_available("preparation", bool(references))
        self.compact_header.set_metric_available("summary", bool(position.total_steps))
        self.preparation_scroll.setVisible(bool(references) and self._preparation_open)
        self.preparation_label.setText(
            "Références à vérifier (aucun achat présumé) :\n"
            + "\n".join(
                item.label
                + (" · facultatif" if item.optional_or_conditional else "")
                + (" · sur le trajet" if item.obtainable_on_route else "")
                + (f" · étape {item.needed_at_step}"
                   if item.needed_at_step != index + 1 else "")
                for item in references
            ) if references else ""
        )
        self.position_label.setText(
            f"FICHE {index + 1}" if index >= 0
            else "PARCOURS CONTINU"
        )
        self.compact_header.set_summary_position(index)
        self.previous_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < position.total_steps - 1)
        self.progress_label.setText(
            "Suivi manuel : "
            + " · ".join(
                f"{key} {done}/{position.total_steps}"
                for key, done in position.completed_by_character.items()
            )
            if position.completed_by_character
            else "Aucun personnage sélectionné"
        )


__all__ = ["ContinuousGuideRoutePanel"]
