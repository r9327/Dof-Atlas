"""Atlas launch handoff: one lightweight progress screen using real task states."""
from __future__ import annotations

from collections.abc import Mapping
import os

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QVBoxLayout, QWidget

from app.background_work import install_preload_priority_bridge
from app.ui.components import atlas_application_icon, configure_unity_progress_bar
from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX


PRELOAD_GEOMETRY = UNITY_MODULE_GEOMETRY_PX["preload_popup"]


PRELOAD_TASK_ORDER = ("quests", "encyclopedia", "craft")
PRELOAD_TASK_LABELS = {
    "quests": "Quêtes",
    "encyclopedia": "Guides & Succès",
    "craft": "Craft",
}
TERMINAL_STATES = {"READY", "FAILED"}


class PreloadProgressPopup(QDialog):
    """Show logo, title, task status and real progress, never fake percentages.

    Home appears when the Quest base is ready; optional warmups continue
    without an application-modal popup. No duplicate workers or event loops.
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
        self.setFixedWidth(PRELOAD_GEOMETRY["dialog_width"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*PRELOAD_GEOMETRY["page_margins"])
        layout.setSpacing(PRELOAD_GEOMETRY["page_spacing"])

        icon = atlas_application_icon()
        if not icon.isNull():
            self.logo_label = QLabel(self)
            self.logo_label.setObjectName("PreloadPopupLogo")
            self.logo_label.setAlignment(Qt.AlignCenter)
            size = PRELOAD_GEOMETRY["logo_box"]
            self.logo_label.setPixmap(icon.pixmap(QSize(size, size)))
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

        self.progress = configure_unity_progress_bar(
            QProgressBar(), object_name="PreloadPopupProgress",
            maximum=len(PRELOAD_TASK_ORDER), text_visible=True,
            display_format="%p %",
        )
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # The standalone launcher remains the only visible progress window.
        # The same Qt state machine still drives Home's reveal in silent mode.
        self._silent_handoff = os.environ.get("DOFUS_ATLAS_LAUNCHER_HANDOFF") == "1"
        self._has_started = False
        self._finished = False
        self._handed_off = False
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_when_finished)

    def begin(self, states: Mapping[str, str] | None = None) -> None:
        """Show preload before any application pages are made visible."""
        self._has_started = True
        self.update_states(states or {})
        if not self._silent_handoff and not self.isVisible():
            self._show_centered()

    def update_states(self, states: Mapping[str, str]) -> None:
        # Once Home is visible, background warmups must never reopen a
        # modal dialog or emit a second launch handoff.
        if self._handed_off:
            return
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
        if self._finished:
            if not self._hide_timer.isActive():
                self._hide_timer.start(0 if self._silent_handoff else (500 if failed == 0 else 1800))
        else:
            self._hide_timer.stop()
            if not self._silent_handoff and not self.isVisible():
                self._show_centered()

    def handoff(self) -> None:
        """Release the modal gate once the Quest preload reaches terminal state."""
        if not self._has_started or self._handed_off:
            return
        self._handed_off = True
        # The dialog's lifecycle is finished even if background cache tasks
        # remain active; permit close/reject and prevent a hidden modal gate.
        self._finished = True
        self._hide_timer.stop()
        self.hide()
        self.readyForMainWindow.emit()

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

    def _hide_when_finished(self) -> None:
        if self._finished and not self._handed_off:
            self.handoff()


__all__ = [
    "PRELOAD_TASK_LABELS", "PRELOAD_TASK_ORDER", "PreloadProgressPopup",
]
