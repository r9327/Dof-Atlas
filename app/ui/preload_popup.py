"""Atlas launch handoff: one lightweight progress screen using real task states."""
from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QVBoxLayout, QWidget

from app.background_work import install_preload_priority_bridge
from app.ui.components import atlas_application_icon
from app.ui.theme import PALETTE, TYPOGRAPHY


PRELOAD_TASK_ORDER = ("quests", "encyclopedia", "craft")
PRELOAD_TASK_LABELS = {
    "quests": "Quêtes",
    "encyclopedia": "Guides & Succès",
    "craft": "Craft",
}
TERMINAL_STATES = {"READY", "FAILED"}


class PreloadProgressPopup(QDialog):
    """Show logo, title, task status and real progress, never fake percentages.

    The main Atlas window remains hidden until all preloading tasks have
    reached a terminal state. No nested Qt event loop or duplicate workers.
    """

    readyForMainWindow = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if parent is not None:
            install_preload_priority_bridge(parent)

        self.setObjectName("PreloadProgressPopup")
        self.setWindowTitle("Préparation de Dofus Atlas")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.setModal(True)
        self.setFixedWidth(470)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 28)
        layout.setSpacing(14)

        icon = atlas_application_icon()
        if not icon.isNull():
            self.logo_label = QLabel(self)
            self.logo_label.setObjectName("PreloadPopupLogo")
            self.logo_label.setAlignment(Qt.AlignCenter)
            self.logo_label.setPixmap(icon.pixmap(QSize(64, 64)))
            layout.addWidget(self.logo_label)

        title = QLabel("Dofus Atlas")
        title.setObjectName("PreloadPopupTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.current_label = QLabel("Initialisation du préchargement…")
        self.current_label.setObjectName("PreloadPopupCurrent")
        self.current_label.setAlignment(Qt.AlignCenter)
        self.current_label.setWordWrap(True)
        layout.addWidget(self.current_label)

        self.progress = QProgressBar()
        self.progress.setObjectName("PreloadPopupProgress")
        self.progress.setRange(0, len(PRELOAD_TASK_ORDER))
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p %")
        layout.addWidget(self.progress)

        self.setStyleSheet(
            "#PreloadProgressPopup {"
            f" background: {PALETTE['BG']}; border: 1px solid {PALETTE['BORDER']};"
            " border-radius: 12px;"
            "}"
            "#PreloadPopupTitle {"
            f" color: {PALETTE['TEXT']}; font-size: 22px; font-weight: 700;"
            f" font-family: {TYPOGRAPHY['FONT_FAMILY']};"
            "}"
            "#PreloadPopupCurrent {"
            f" color: {PALETTE['TEXT_MUTED']}; font-size: 12px;"
            ' font-family: "Lexend", "Segoe UI";'
            "}"
            "#PreloadPopupProgress {"
            f" background: {PALETTE['PANEL_2']}; color: {PALETTE['TEXT']};"
            f" border: 1px solid {PALETTE['BORDER']}; border-radius: 6px;"
            " min-height: 17px; text-align: center;"
            "}"
            "#PreloadPopupProgress::chunk {"
            f" background: {PALETTE['GREEN']}; border-radius: 5px;"
            "}"
        )

        self._has_started = False
        self._finished = False
        self._hide_generation = 0

    def begin(self, states: Mapping[str, str] | None = None) -> None:
        """Show preload before any application pages are made visible."""
        self._has_started = True
        self.update_states(states or {})
        if not self.isVisible():
            self._show_centered()

    def update_states(self, states: Mapping[str, str]) -> None:
        task_states = {
            task: str(states.get(task, "IDLE")).upper()
            for task in PRELOAD_TASK_ORDER
        }
        started = any(state != "IDLE" for state in task_states.values())
        if not self._has_started:
            if not started:
                return
            self.begin(task_states)
            return

        completed = sum(
            state in TERMINAL_STATES for state in task_states.values()
        )
        failed = sum(state == "FAILED" for state in task_states.values())
        loading = next(
            (task for task in PRELOAD_TASK_ORDER
             if task_states[task] == "LOADING"), ""
        )
        pending = next(
            (task for task in PRELOAD_TASK_ORDER
             if task_states[task] == "IDLE"), ""
        )
        self.progress.setValue(completed)

        if loading:
            self.current_label.setText(
                f"Chargement en cours · {PRELOAD_TASK_LABELS[loading]}"
            )
        elif completed == len(PRELOAD_TASK_ORDER):
            self.current_label.setText(
                "Dofus Atlas est prêt."
                if failed == 0
                else (
                    f"Préchargement terminé avec {failed} erreur(s). "
                    "Les modules concernés pourront retenter leur chargement à l'ouverture."
                )
            )
        elif pending:
            self.current_label.setText(
                f"Préparation de {PRELOAD_TASK_LABELS[pending]}…"
            )

        self._finished = completed == len(PRELOAD_TASK_ORDER)
        self._hide_generation += 1
        generation = self._hide_generation
        if self._finished:
            QTimer.singleShot(
                500 if failed == 0 else 1800,
                lambda: self._hide_if_current(generation),
            )
        elif not self.isVisible():
            self._show_centered()

    def _show_centered(self) -> None:
        parent = self.parentWidget()
        self.adjustSize()
        if parent is not None and parent.isVisible():
            center = parent.mapToGlobal(parent.rect().center())
        else:
            screen = QApplication.primaryScreen()
            center = screen.availableGeometry().center() if screen else None
        if center is not None:
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
        self.show()
        self.raise_()

    def reject(self) -> None:
        if self._finished:
            super().reject()

    def closeEvent(self, event) -> None:
        if self._finished:
            event.accept()
            return
        event.ignore()

    def _hide_if_current(self, generation: int) -> None:
        if generation != self._hide_generation or not self._finished:
            return
        self._hide_generation += 1
        self.hide()
        self.readyForMainWindow.emit()


__all__ = [
    "PRELOAD_TASK_LABELS", "PRELOAD_TASK_ORDER", "PreloadProgressPopup",
]
