"""Two prominent playable guide cards, then a compact browsable library."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QBoxLayout, QFrame, QHBoxLayout, QLabel, QProgressBar,
    QVBoxLayout, QWidget,
)

from app.core.numbers import clamped_percent
from app.core.file_stamp import mtime_ctime_size_stamp
from app.modules.encyclopedia.services.image_service import ENCYCLOPEDIA_IMAGE_SERVICE
from app.ui.components import AtlasButton, configure_unity_progress_bar
from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX
from app.ui.unity_skin import apply_unity_panel_shadow, sprite_icon_path

GUIDE_CARD_GEOMETRY = UNITY_MODULE_GEOMETRY_PX["guide_cards"]


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
        # All card/child colors and states come from the shared Unity QSS.
        apply_unity_panel_shadow(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*GUIDE_CARD_GEOMETRY["featured_compact_margins"])
        layout.setSpacing(GUIDE_CARD_GEOMETRY["featured_compact_spacing"])
        self.setMinimumHeight(GUIDE_CARD_GEOMETRY["featured_compact_min_height"])
        self.setMaximumHeight(GUIDE_CARD_GEOMETRY["featured_compact_max_height"])
        self.title = QLabel(title)
        self.title.setObjectName("GuideFeaturedTitle")
        title_row = QHBoxLayout()
        self.artwork = QLabel()
        artwork_box = GUIDE_CARD_GEOMETRY["featured_compact_artwork_box"]
        self.artwork.setFixedSize(artwork_box, artwork_box)
        self.artwork.setAlignment(Qt.AlignCenter)
        title_row.addWidget(self.artwork)
        title_row.addWidget(self.title, 1)
        layout.addLayout(title_row)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("FeaturedSubtitle")
        self.subtitle.setWordWrap(False)
        layout.addWidget(self.subtitle)
        self.progress = configure_unity_progress_bar(
            QProgressBar(), object_name="GuideFeaturedProgress",
        )
        self.progress.setMaximumHeight(GUIDE_CARD_GEOMETRY["featured_compact_progress_max_height"])
        layout.addWidget(self.progress)
        self.open_button = AtlasButton("Ouvrir →")
        self.open_button.setObjectName("FeaturedGuideOpen")
        self.open_button.clicked.connect(lambda: on_open(self.guide_id))
        # A card already opens on click, Enter and Space; a second visible
        # "Ouvrir" action consumed height without adding functionality.
        # Retain the signal owner for existing keyboard/API integrations.
        self.open_button.setHidden(True)
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
        # Artwork has an independent source revision. Progress-only updates
        # must not trigger another image decode or replace the current pixmap.
        raw_image = getattr(guide, "image_path", None)
        image_path = Path(raw_image) if raw_image else None
        local_icon = sprite_icon_path("guide" if self.guide_id == "guide_complet" else "dofus")
        artwork_signature = (
            str(image_path), mtime_ctime_size_stamp(image_path) if image_path is not None else None,
            str(local_icon), mtime_ctime_size_stamp(Path(local_icon)) if local_icon else None,
        )
        artwork_changed = artwork_signature != getattr(self, "_artwork_signature", None)
        if (getattr(self, "_rendered_guide", object()) is guide
                and getattr(self, "_rendered_values", None) == values and not artwork_changed):
            return
        self._rendered_guide = guide
        self._rendered_values = values
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
        self.subtitle.setText(status)
        self.subtitle.setToolTip(description or status)
        # No total means no percentage is known; keep the bar hidden.
        self.progress.setVisible(usable and total > 0)
        if total > 0:
            self.progress.setValue(clamped_percent(done, total))
        if not artwork_changed:
            return
        self._artwork_signature = artwork_signature
        self.artwork.clear()
        # Only two featured QIcons, backed by local assets when explicitly enabled.
        # Visual artwork belongs on the card, not the hidden compatibility button.
        if local_icon:
            self.artwork.setPixmap(QIcon(str(local_icon)).pixmap(24, 24))
        if usable and image_path is not None and image_path.is_file():
            art_box = GUIDE_CARD_GEOMETRY["featured_compact_artwork_box"]
            pixmap = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(image_path, QSize(art_box, art_box))
            if not pixmap.isNull():
                self.artwork.setPixmap(pixmap)


class FeaturedPair(QWidget):
    """Keep the two prominent cards side by side, stack only at small width."""

    def __init__(self, cards: tuple[FeaturedGuideCard, FeaturedGuideCard], parent=None):
        super().__init__(parent)
        layout = QBoxLayout(QBoxLayout.LeftToRight, self)
        # Reserve a few pixels so the real card shadows aren't cropped.
        layout.setContentsMargins(*GUIDE_CARD_GEOMETRY["featured_pair_margins"])
        layout.setSpacing(GUIDE_CARD_GEOMETRY["featured_pair_spacing"])
        for card in cards:
            layout.addWidget(card, 1)
        self.pair_layout = layout

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        wanted = (
            QBoxLayout.LeftToRight
            if event.size().width() >= GUIDE_CARD_GEOMETRY["featured_pair_horizontal_min_width"]
            else QBoxLayout.TopToBottom
        )
        if self.pair_layout.direction() != wanted:
            self.pair_layout.setDirection(wanted)
