from __future__ import annotations

from collections.abc import Mapping
from time import monotonic

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app.background_work import install_preload_priority_bridge


PRELOAD_TASK_ORDER = ("quests", "encyclopedia", "craft")
PRELOAD_TASK_LABELS = {
    "quests": "Quêtes",
    "encyclopedia": "Guides & Succès",
    "craft": "Craft",
}
TERMINAL_STATES = {"READY", "FAILED"}

_STATE_LABELS = {
    "IDLE": "En attente",
    "LOADING": "Chargement…",
    "READY": "Prêt",
    "FAILED": "Erreur",
}


class PreloadProgressPopup(QDialog):
    """Visible startup loading screen driven only by real preload states.

    The dialog is application-modal but never opens a nested event loop:
    Qt keeps processing events while Atlas preload workers/processes run, so the
    window stays responsive without letting the user enter half-hydrated modules.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if parent is not None:
            install_preload_priority_bridge(parent)

        self.setObjectName("PreloadProgressPopup")
        self.setWindowTitle("Préparation de Dofus Atlas")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.setModal(True)
        self.setFixedWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Préparation de Dofus Atlas")
        title.setObjectName("PreloadPopupTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Les données utiles sont préparées avant de te laisser naviguer. "
            "L'interface reste responsive pendant le chargement."
        )
        subtitle.setObjectName("PreloadPopupSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.task_status_labels: dict[str, QLabel] = {}
        for task in PRELOAD_TASK_ORDER:
            row = QFrame()
            row.setObjectName("PreloadTaskRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 9, 12, 9)
            row_layout.setSpacing(10)

            name = QLabel(PRELOAD_TASK_LABELS[task])
            name.setObjectName("PreloadTaskName")
            row_layout.addWidget(name, 1)

            status = QLabel(_STATE_LABELS["IDLE"])
            status.setObjectName("PreloadTaskStatus")
            status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_layout.addWidget(status)
            self.task_status_labels[task] = status
            layout.addWidget(row)

        self.current_label = QLabel("Initialisation du préchargement…")
        self.current_label.setObjectName("PreloadPopupCurrent")
        self.current_label.setWordWrap(True)
        layout.addWidget(self.current_label)

        self.progress = QProgressBar()
        self.progress.setObjectName("PreloadPopupProgress")
        self.progress.setRange(0, len(PRELOAD_TASK_ORDER))
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat(f"0/{len(PRELOAD_TASK_ORDER)} étapes prêtes")
        layout.addWidget(self.progress)

        self.elapsed_label = QLabel("Temps écoulé · 0,0 s")
        self.elapsed_label.setObjectName("PreloadPopupElapsed")
        self.elapsed_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.elapsed_label)

        self.setStyleSheet(
            "#PreloadProgressPopup {"
            " background: #111821; border: 1px solid #334155; border-radius: 14px;"
            "}"
            "#PreloadPopupTitle {"
            " color: #f8fafc; font-weight: 700; font-size: 18px;"
            "}"
            "#PreloadPopupSubtitle, #PreloadPopupCurrent, #PreloadPopupElapsed {"
            " color: #aebccd; font-size: 12px;"
            "}"
            "#PreloadTaskRow {"
            " background: #18212c; border: 1px solid #29384a; border-radius: 8px;"
            "}"
            "#PreloadTaskName { color: #edf3f8; font-weight: 600; }"
            "#PreloadTaskStatus { color: #9fb0c2; font-weight: 600; }"
            "#PreloadPopupProgress { min-height: 20px; }"
        )

        self._has_started = False
        self._started_at: float | None = None
        self._hide_generation = 0
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(200)
        self._elapsed_timer.timeout.connect(self._refresh_elapsed)

    def begin(self, states: Mapping[str, str] | None = None) -> None:
        """Show the loading screen before the first worker starts."""

        if self._started_at is None:
            self._started_at = monotonic()
        self._has_started = True
        if not self._elapsed_timer.isActive():
            self._elapsed_timer.start()
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
            (
                task
                for task in PRELOAD_TASK_ORDER
                if task_states[task] == "LOADING"
            ),
            "",
        )
        pending = next(
            (
                task
                for task in PRELOAD_TASK_ORDER
                if task_states[task] == "IDLE"
            ),
            "",
        )

        for task, state in task_states.items():
            status = self.task_status_labels[task]
            status.setText(_STATE_LABELS.get(state, state.title()))

        self.progress.setValue(completed)
        self.progress.setFormat(
            f"{completed}/{len(PRELOAD_TASK_ORDER)} étapes prêtes"
        )

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
                f"Prochaine étape · {PRELOAD_TASK_LABELS[pending]}"
            )

        self._hide_generation += 1
        generation = self._hide_generation
        if completed == len(PRELOAD_TASK_ORDER):
            self._elapsed_timer.stop()
            self._refresh_elapsed()
            delay_ms = 500 if failed == 0 else 1800
            QTimer.singleShot(
                delay_ms,
                lambda: self._hide_if_current(generation),
            )
        elif not self.isVisible():
            self._show_centered()

    def _refresh_elapsed(self) -> None:
        started_at = self._started_at
        elapsed = 0.0 if started_at is None else max(0.0, monotonic() - started_at)
        self.elapsed_label.setText(
            f"Temps écoulé · {elapsed:.1f} s".replace(".", ",")
        )

    def _show_centered(self) -> None:
        parent = self.parentWidget()
        self.adjustSize()
        if parent is not None and parent.isVisible():
            center = parent.mapToGlobal(parent.rect().center())
            self.move(
                center.x() - self.width() // 2,
                center.y() - self.height() // 2,
            )
        self.show()
        self.raise_()

    def _hide_if_current(self, generation: int) -> None:
        if generation != self._hide_generation:
            return
        self.hide()


__all__ = [
    "PRELOAD_TASK_LABELS",
    "PRELOAD_TASK_ORDER",
    "PreloadProgressPopup",
]
