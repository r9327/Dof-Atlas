from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSplitterHandle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.storage import AtlasButton


class HideCompletedButton(AtlasButton):
    stateChanged = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__("Masquer les terminées", parent)
        self.setObjectName("GuideHideCompletedToggle")
        self.setCheckable(True)
        self.toggled.connect(self._sync_state)

    def _sync_state(self, checked: bool) -> None:
        self.setText("✓ Terminées masquées" if checked else "Masquer les terminées")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        self.stateChanged.emit(checked)


class FixedColumnSplitterHandle(QSplitterHandle):
    def __init__(self, orientation: Qt.Orientation, parent: QSplitter | None = None) -> None:
        super().__init__(orientation, parent)
        self.setCursor(Qt.ArrowCursor)

    def enterEvent(self, event) -> None:
        self.setCursor(Qt.ArrowCursor)
        event.accept()

    def mousePressEvent(self, event) -> None:
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        event.accept()


class FixedColumnSplitter(QSplitter):
    def __init__(self, orientation: Qt.Orientation = Qt.Horizontal, parent=None) -> None:
        super().__init__(orientation, parent)
        self.setChildrenCollapsible(False)
        super().setHandleWidth(0)

    def createHandle(self) -> QSplitterHandle:
        return FixedColumnSplitterHandle(self.orientation(), self)

    def setHandleWidth(self, width: int) -> None:
        super().setHandleWidth(0)


class CollapsedColumnRail(QFrame):
    """Shared compact rail used to restore a minimized navigation column."""

    expandedRequested = Signal()

    def __init__(self, tooltip: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideStepsCollapsedRail")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 6, 2, 6)
        layout.setSpacing(0)
        button = QToolButton()
        button.setObjectName("GuideStepsCollapseButton")
        button.setText("\u203a")
        button.setFixedSize(24, 24)
        button.setFocusPolicy(Qt.NoFocus)
        button.setToolTip(tooltip)
        button.clicked.connect(self.expandedRequested)
        layout.addWidget(button, 0, Qt.AlignHCenter)
        layout.addStretch(1)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.expandedRequested.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class EncyclopediaThreePanelDashboard(FixedColumnSplitter):
    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Horizontal, parent)
        self.setObjectName("EncyclopediaThreePanelDashboard")

    def configure_sizes(self, left: int = 180, center: int = 300, right: int = 420) -> None:
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)
        self.setStretchFactor(2, 2)
        self.setSizes([left, center, right])


class EncyclopediaPanel(QFrame):
    def __init__(self, title: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("EncyclopediaPanel")
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(8, 8, 8, 8)
        self.root.setSpacing(6)
        if title:
            label = QLabel(title)
            label.setObjectName("PanelTitle")
            self.root.addWidget(label)


class CompactScroll(QScrollArea):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CompactScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.content = QWidget()
        self.content.setObjectName("CompactScrollContent")
        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
        self.setWidget(self.content)

    def clear(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def finish(self) -> None:
        self.layout.addStretch(1)


class StatusBadge(QLabel):
    def __init__(self, text: str, state: str = "neutral", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("StatusBadge")
        self.setProperty("state", state)


class ActivityBadge(QLabel):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("ActivityBadge")


class ActivitySummary(QFrame):
    def __init__(self, rows: dict[str, int] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ActivitySummary")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        for label, value in (rows or {}).items():
            if int(value or 0) > 0:
                layout.addWidget(ActivityBadge(f"{label} {value}"))
        layout.addStretch(1)


class RequiredItemsWidget(QFrame):
    def __init__(self, items: Iterable[object] = (), title: str = "Objets nécessaires", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RequiredItemsWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        header = QLabel(title)
        header.setObjectName("PanelTitle")
        layout.addWidget(header)
        count = 0
        for item in items:
            row = RequiredItemRow(item)
            layout.addWidget(row)
            count += 1
        if not count:
            empty = QLabel("Aucun objet structuré disponible.")
            empty.setObjectName("MutedLabel")
            empty.setWordWrap(True)
            layout.addWidget(empty)


class RequiredItemRow(QFrame):
    def __init__(self, item: object, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RequiredItemRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        image_path = str(getattr(item, "image_path", "") or "")
        image = QToolButton()
        image.setObjectName("GuideRewardImage")
        image.setFixedSize(30, 30)
        image.setIconSize(QSize(24, 24))
        image.setFocusPolicy(Qt.NoFocus)
        if image_path and Path(image_path).exists():
            image.setIcon(QIcon(image_path))
        layout.addWidget(image)
        name = QLabel(str(getattr(item, "name", "") or "Objet local"))
        name.setObjectName("CompactLabel")
        name.setWordWrap(True)
        layout.addWidget(name, 1)
        quantity = int(getattr(item, "quantity", 1) or 1)
        qty = QLabel(f"× {quantity}")
        qty.setObjectName("MutedLabel")
        layout.addWidget(qty)


class EmptyState(QLabel):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("MutedLabel")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
