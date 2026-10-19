"""Compact, source-only manual progress panel for continuous Ganymède routes.

No invented quest completion, preparation quantities, Zaap claims or automatic
progression. Sommaire stays open until the user explicitly closes it.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from PySide6.QtCore import Qt, QStringListModel
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListView, QToolButton, QVBoxLayout, QWidget,
)

from app.modules.encyclopedia.services.guide_continuous_navigation import (
    ContinuousGuideNavigation,
)
from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService


class ContinuousGuideRoutePanel(QWidget):
    def __init__(
        self,
        route: Mapping[str, object],
        progress: GuideProgressService,
        character_keys: Iterable[str] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GuideContinuousRoutePanel")
        self.route = route
        self.navigation = ContinuousGuideNavigation(route, progress, character_keys)
        self.rows = route["sections"][0]["steps"]
        self._summary_open = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(7)
        head = QHBoxLayout()
        self.position_label = QLabel()
        self.position_label.setObjectName("GuideContinuousPosition")
        head.addWidget(self.position_label, 1)
        self.summary_toggle = QToolButton()
        self.summary_toggle.setObjectName("GuideContinuousSommaireButton")
        self.summary_toggle.setText("Sommaire")
        self.summary_toggle.clicked.connect(self.toggle_summary)
        head.addWidget(self.summary_toggle)
        layout.addLayout(head)

        work = QHBoxLayout()
        work.setSpacing(9)
        self.summary = QListView()
        self.summary.setObjectName("GuideContinuousSommaire")
        self.summary.setMinimumWidth(170)
        self.summary.setMaximumWidth(250)
        self.summary_model = QStringListModel([
            f"Fiche {i} — {str(row.get('title') or f'Étape {i}')}"
            for i, row in enumerate(self.rows, 1)
        ], self)
        self.summary.setModel(self.summary_model)
        self.summary.clicked.connect(
            lambda index: self.show_step(self.navigation.step_ids[index.row()])
        )
        work.addWidget(self.summary, 1)

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
        self.validate_button = self._button("✓", "GuideContinuousValidate")
        self.validate_button.setToolTip(
            "Cocher/décocher manuellement cette fiche pour les personnages sélectionnés"
        )
        self.validate_button.clicked.connect(self.toggle_manual_current)
        nav.addWidget(self.validate_button)
        detail.addLayout(nav)
        work.addWidget(content, 3)
        layout.addLayout(work, 1)
        self.refresh()

    @staticmethod
    def _button(text: str, name: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName(name)
        button.setText(text)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def toggle_summary(self) -> None:
        self._summary_open = not self._summary_open
        self.summary.setVisible(self._summary_open)

    def set_characters(self, character_keys: Iterable[str]) -> None:
        self.navigation.select_characters(character_keys)
        self.refresh()

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

    def refresh(self) -> None:
        position = self.navigation.position()
        current = position.viewed_step_id
        actual = position.actual_step_id
        self.actual_button.setEnabled(actual is not None)
        self.validate_button.setEnabled(
            current is not None and bool(position.selected_character_keys)
        )
        self.validate_button.setVisible(current is not None)
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
            self.title_label.setText(str(row.get("title") or f"Fiche {index + 1}"))
            self.body_label.setText(str(row.get("content") or
                                        "Actions de cette étape non renseignées."))
        self.position_label.setText(
            f"FICHE {index + 1}/{position.total_steps}" if index >= 0
            else "PARCOURS CONTINU"
        )
        self.previous_button.setEnabled(index > 0)
        self.next_button.setEnabled(0 <= index < position.total_steps - 1)
        self.progress_label.setText(
            "Suivi manuel : "
            + " · ".join(
                f"{key} {done}/{position.total_steps}"
                for key, done in position.completed_by_character.items()
            )
            if position.completed_by_character
            else "Aucun personnage sélectionné"
        )
        if index >= 0:
            self.summary.selectionModel().clearSelection()
            self.summary.setCurrentIndex(self.summary_model.index(index))
        self.summary.setVisible(self._summary_open)


__all__ = ["ContinuousGuideRoutePanel"]
