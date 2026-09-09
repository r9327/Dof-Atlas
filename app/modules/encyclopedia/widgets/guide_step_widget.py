from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from app.modules.encyclopedia.models import EntityRef, GuideStep
from app.modules.encyclopedia.widgets.entity_link_button import EntityLinkButton
from app.storage import AtlasButton

STEP_TYPE_LABELS = {
    "info": "Information",
    "quest": "Quête",
    "achievement": "Succès",
    "dungeon": "Donjon",
    "monster": "Monstre",
    "wanted": "Avis de recherche",
    "archmonster": "Archimonstre",
}


class GuideStepWidget(QFrame):
    """Ligne interactive représentant une étape d'un guide."""

    stepSelected = Signal(str)
    openEntityRequested = Signal(str, object)
    manualStepToggled = Signal(str, bool)
    achievementDetailsRequested = Signal(int)

    def __init__(
        self,
        step: GuideStep,
        number: int,
        completed: bool,
        blocked: bool,
        missing_prerequisites: list[EntityRef],
        active: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.step = step
        self.active = bool(active)

        # "blocked" et "missing_prerequisites" restent dans la signature pour
        # conserver la compatibilité avec GuidesView, mais ils ne bloquent plus
        # l'affichage ni les actions de la ligne.
        _ = blocked, missing_prerequisites

        self.setObjectName("GuideStepActive" if self.active else "GuideStepWidget")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Afficher cette étape dans la fiche du guide")

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(8)

        self.status_label = QLabel(
            self._status_text(
                completed=completed,
                optional=step.optional,
                active=self.active,
            )
        )
        self.status_label.setObjectName("GuideStepStatus")
        self.status_label.setMinimumWidth(94)
        self._make_click_through(self.status_label)
        root.addWidget(self.status_label)

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(3)

        self.title_label = QLabel(f"{number}. {step.display_title}")
        self.title_label.setObjectName("CompactLabel")
        self.title_label.setWordWrap(True)
        self._make_click_through(self.title_label)
        texts.addWidget(self.title_label)

        self.meta_label = QLabel(
            self._meta_text(
                step=step,
                completed=completed,
                active=self.active,
            )
        )
        self.meta_label.setObjectName("MutedLabel")
        self.meta_label.setWordWrap(True)
        self._make_click_through(self.meta_label)
        texts.addWidget(self.meta_label)

        if step.content:
            content = QLabel(step.content)
            content.setObjectName("MutedLabel")
            content.setWordWrap(True)
            self._make_click_through(content)
            texts.addWidget(content)

        if step.notes:
            notes = QLabel(step.notes)
            notes.setObjectName("MutedLabel")
            notes.setWordWrap(True)
            self._make_click_through(notes)
            texts.addWidget(notes)

        if step.validation_errors:
            errors = QLabel(" | ".join(step.validation_errors))
            errors.setObjectName("WarningLabel")
            errors.setWordWrap(True)
            self._make_click_through(errors)
            texts.addWidget(errors)

        root.addLayout(texts, 1)

        if step.step_type == "info":
            check = QCheckBox("Terminer")
            check.setObjectName("GuideManualStepCheck")
            check.setChecked(completed)
            check.toggled.connect(
                lambda value, step_id=step.id: self.manualStepToggled.emit(
                    step_id,
                    value,
                )
            )
            root.addWidget(check)

        elif step.step_type == "achievement" and step.entity_id is not None:
            button = AtlasButton("Afficher les détails")
            button.setObjectName("SecondaryButton")
            button.setEnabled(step.available)
            button.clicked.connect(
                lambda _checked=False, aid=int(step.entity_id):
                self.achievementDetailsRequested.emit(aid)
            )
            root.addWidget(button)

        elif step.entity_ref is not None:
            button_text = (
                "Ouvrir dans Quêtes"
                if step.step_type == "quest"
                else "Ouvrir"
            )
            button = EntityLinkButton(step.entity_ref, text=button_text)

            # Une quête du guide reste toujours consultable et ouvrable.
            if step.step_type != "quest":
                button.setEnabled(step.available)

            button.entityActivated.connect(self.openEntityRequested)
            root.addWidget(button)

    @staticmethod
    def _make_click_through(widget: QLabel) -> None:
        widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.stepSelected.emit(self.step.id)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @staticmethod
    def _status_text(
        completed: bool,
        optional: bool,
        active: bool,
    ) -> str:
        if completed:
            return "✓ Terminée"
        if active:
            return "▶ Sélectionnée"
        if optional:
            return "◇ Optionnelle"
        return "○ À faire"

    @staticmethod
    def _meta_text(
        step: GuideStep,
        completed: bool,
        active: bool,
    ) -> str:
        parts = [
            STEP_TYPE_LABELS.get(step.step_type, step.step_type),
            "Optionnelle" if step.optional else "Obligatoire",
        ]

        if completed:
            parts.append("Terminée")
        elif active:
            parts.append("Sélectionnée")
        else:
            parts.append("À faire")

        return " • ".join(parts)