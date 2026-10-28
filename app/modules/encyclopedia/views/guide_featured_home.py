"""Two prominent playable guide cards, then a compact browsable library."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QBoxLayout, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)

from app.modules.encyclopedia.services.image_service import ENCYCLOPEDIA_IMAGE_SERVICE
from app.ui.theme import PALETTE
from app.ui.unity_skin import sprite_icon_path, unity_enabled


FEATURED = (
    ("guide_complet", "Guide Succès Opti"),
    ("dofus_sylvestre", "Sylvestre Opti"),
)


class FeaturedGuideCard(QFrame):
    """One of only two eagerly constructed cards, not 95 QWidgets."""

    def __init__(self, guide_id: str, title: str, on_open, parent=None) -> None:
        super().__init__(parent)
        self.guide_id = guide_id
        self.setObjectName("GuideFeaturedCard")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(title)
        # A widget-local stylesheet overrides the global Unity QSS. Keep
        # the Atlas default unchanged, but give Unity its intended alpha.
        card_background = (
            "rgba(27, 39, 70, 0.88)"
            if unity_enabled() else PALETTE["PANEL_2"]
        )
        self.setStyleSheet(
            "#GuideFeaturedCard { background: " + card_background
            + "; border: 1px solid " + PALETTE["GREEN_BORDER"]
            + "; border-radius: 8px; }"
            "#GuideFeaturedCard QLabel { border: 0; background: transparent; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(4)
        self.title = QLabel(title)
        self.title.setStyleSheet(
            f"color: {PALETTE['TEXT']}; font-weight: 800; font-size: 14px;"
        )
        title_row = QHBoxLayout()
        self.artwork = QLabel()
        self.artwork.setFixedSize(36, 36)
        self.artwork.setAlignment(Qt.AlignCenter)
        title_row.addWidget(self.artwork)
        title_row.addWidget(self.title, 1)
        layout.addLayout(title_row)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("FeaturedSubtitle")
        self.subtitle.setStyleSheet(f"color: {PALETTE['TEXT_MUTED']};")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(9)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(
            f"QProgressBar {{ border: 0; background: {PALETTE['BORDER_SOFT']};"
            f" border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {PALETTE['GREEN']};"
            f" border-radius: 4px; }}"
        )
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.open_button = QPushButton("Ouvrir →")
        self.open_button.setObjectName("FeaturedGuideOpen")
        self.open_button.clicked.connect(lambda: on_open(self.guide_id))
        actions.addWidget(self.open_button)
        layout.addLayout(actions)
        self.set_guide(None, (0, 0, ""))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            if self.open_button.isEnabled():
                self.open_button.click()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            if self.open_button.isEnabled():
                self.open_button.click()
            event.accept()
            return
        super().keyPressEvent(event)

    def set_guide(self, guide, values: tuple[int, int, str]) -> None:
        done, total, state = values
        usable = guide is not None
        self.open_button.setEnabled(usable)
        self.open_button.setText("Continuer →" if usable and done > 0 else
                                 "Ouvrir →" if usable else "Indisponible")
        raw_description = str(getattr(guide, "description", "") or "").strip()
        # Never slice a French word halfway through; leave room for the
        # state below rather than forcing both strings into one cramped line.
        if len(raw_description) > 68:
            description = raw_description[:68].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
        else:
            description = raw_description
        if not usable:
            status = "Parcours indisponible"
        elif total > 0:
            status = f"{done}/{total} quêtes · {state or 'Non commencé'}"
        else:
            status = "Progression indisponible"
        self.subtitle.setText(f"{description}\n{status}" if description else status)
        # No total means no percentage is known; keep the bar hidden.
        self.progress.setVisible(usable and total > 0)
        if total > 0:
            self.progress.setValue(max(0, min(100, round(done * 100 / total))))
        self.artwork.clear()
        local_icon = sprite_icon_path("guide")
        # Only two featured QIcons, backed by local assets when explicitly enabled.
        self.open_button.setIcon(QIcon(str(local_icon)) if local_icon else QIcon())
        if usable:
            image_path = getattr(guide, "image_path", None)
            if image_path and Path(image_path).is_file():
                from PySide6.QtCore import QSize
                pixmap = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(Path(image_path), QSize(32, 32))
                if pixmap is not None and not pixmap.isNull():
                    self.artwork.setPixmap(pixmap)


class FeaturedPair(QWidget):
    """Keep the two prominent cards side by side, stack only at small width."""

    def __init__(self, cards: tuple[FeaturedGuideCard, FeaturedGuideCard], parent=None):
        super().__init__(parent)
        layout = QBoxLayout(QBoxLayout.LeftToRight, self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for card in cards:
            layout.addWidget(card, 1)
        self.pair_layout = layout

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        wanted = QBoxLayout.LeftToRight if event.size().width() >= 580 else QBoxLayout.TopToBottom
        if self.pair_layout.direction() != wanted:
            self.pair_layout.setDirection(wanted)
