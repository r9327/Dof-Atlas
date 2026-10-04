from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout, QWidget

from app.background_work import install_preload_priority_bridge


PRELOAD_TASK_ORDER = ("quests", "encyclopedia", "craft")
PRELOAD_TASK_LABELS = {
    "quests": "Index des quêtes",
    "encyclopedia": "Guides, succès et progression",
    "craft": "Données Craft",
}
TERMINAL_STATES = {"READY", "FAILED"}


class PreloadProgressPopup(QDialog):
    """Non-blocking progress popup for functional data warm-up only.

    Runtime, tray and network startup are deliberately excluded: this widget
    reports data that makes later user clicks faster, not background services.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if parent is not None:
            install_preload_priority_bridge(parent)
        self.setObjectName("PreloadProgressPopup")
        self.setWindowTitle("Préchargement")
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setModal(False)
        self.setFixedWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)

        title = QLabel("Préchargement")
        title.setObjectName("PreloadPopupTitle")
        layout.addWidget(title)

        self.status_label = QLabel("Préparation des données utiles…")
        self.status_label.setObjectName("CompactLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setObjectName("PreloadPopupProgress")
        self.progress.setRange(0, len(PRELOAD_TASK_ORDER))
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        self.setStyleSheet(
            "#PreloadProgressPopup {"
            " background: #161d27; border: 1px solid #334155; border-radius: 10px;"
            "}"
            "#PreloadPopupTitle { font-weight: 700; font-size: 14px; }"
            "#PreloadPopupProgress { min-height: 16px; }"
        )

        self._has_started = False
        self._hide_generation = 0

    def update_states(self, states: Mapping[str, str]) -> None:
        task_states = {task: str(states.get(task, "IDLE")) for task in PRELOAD_TASK_ORDER}
        started = any(state != "IDLE" for state in task_states.values())
        if not started and not self._has_started:
            return
        self._has_started = True

        completed = sum(state in TERMINAL_STATES for state in task_states.values())
        failed = sum(state == "FAILED" for state in task_states.values())
        loading = next(
            (task for task in PRELOAD_TASK_ORDER if task_states[task] == "LOADING"),
            "",
        )
        pending = next(
            (task for task in PRELOAD_TASK_ORDER if task_states[task] == "IDLE"),
            "",
        )

        self.progress.setValue(completed)
        self.progress.setFormat(f"{completed}/{len(PRELOAD_TASK_ORDER)}")

        if loading:
            self.status_label.setText(PRELOAD_TASK_LABELS[loading])
        elif completed == len(PRELOAD_TASK_ORDER):
            self.status_label.setText(
                "Préchargement prêt."
                if failed == 0
                else f"Préchargement terminé avec {failed} tâche(s) en erreur."
            )
        elif pending:
            self.status_label.setText(f"En attente · {PRELOAD_TASK_LABELS[pending]}")

        self._hide_generation += 1
        generation = self._hide_generation
        if completed == len(PRELOAD_TASK_ORDER):
            if not self.isVisible():
                self._show_near_parent()
            QTimer.singleShot(900, lambda: self._hide_if_current(generation))
            return

        if not self.isVisible():
            self._show_near_parent()

    def _show_near_parent(self) -> None:
        parent = self.parentWidget()
        self.adjustSize()
        if parent is not None and parent.isVisible():
            anchor = parent.mapToGlobal(parent.rect().bottomRight())
            self.move(
                anchor.x() - self.width() - 18,
                anchor.y() - self.height() - 18,
            )
        self.show()
        self.raise_()

    def _hide_if_current(self, generation: int) -> None:
        if generation == self._hide_generation:
            self.hide()


__all__ = [
    "PRELOAD_TASK_LABELS",
    "PRELOAD_TASK_ORDER",
    "PreloadProgressPopup",
]
