"""Four prominent playable guide cards, then a compact browsable library."""
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


FEATURED = (
    ("guide_complet", "Guide Succès"),
    ("dofus_sylvestre", "Sylvestre Opti"),
    ("alignement_bonta", "Bonta"),
    ("alignement_brakmar", "Brâkmar"),
)


class FeaturedGuideCard(QFrame):
    """One of only four eagerly constructed cards, not 95 QWidgets."""

    def __init__(self, guide_id: str, title: str, on_open, parent=None) -> None:
        super().__init__(parent)
        self.guide_id = guide_id
        self.setObjectName("GuideFeaturedCard")
        self.setStyleSheet(
            "#GuideFeaturedCard { background: " + PALETTE["PANEL_2"]
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
        layout.addWidget(self.title)
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

    def set_guide(self, guide, values: tuple[int, int, str]) -> None:
        done, total, state = values
        usable = guide is not None
        self.open_button.setEnabled(usable)
        self.open_button.setText("Continuer →" if usable and done > 0 else
                                 "Ouvrir →" if usable else "Indisponible")
        self.subtitle.setText(
            (str(getattr(guide, "description", "") or "").strip()[:110]
             if usable else "Parcours indisponible")
        )
        # A count of zero is not evidence of zero percent progress.
        self.progress.setVisible(usable and total > 0)
        if total > 0:
            self.progress.setValue(max(0, min(100, round(done * 100 / total))))
            if not self.subtitle.text():
                self.subtitle.setText(f"{done}/{total} quêtes · {state}")
        if usable:
            image_path = getattr(guide, "image_path", None)
            if image_path and Path(image_path).is_file():
                from PySide6.QtCore import QSize
                pixmap = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(Path(image_path), QSize(32, 32))
                if pixmap is not None and not pixmap.isNull():
                    self.open_button.setIcon(QIcon(pixmap))


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
