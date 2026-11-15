"""UI-only Ganymède catalogue shell, using existing indexed Guide roles.

No source steps, fake progress, runtime activation, or source-specific QSS.
The authorized reader remains SharedGuideManualView; this shell is only
the blank catalogue container until a route is independently certified.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QScrollArea,
    QVBoxLayout, QWidget,
)

from app.modules.encyclopedia.views.guide_library_sources import GanymedeListing
from app.ui.components import AtlasButton
from app.ui.theme import SPACING
from app.ui.unity_skin import apply_unity_panel_shadow


def _space(name: str) -> int:
    """Use the common Dev UI spacing token; no per-guide pixel values."""
    return int(SPACING[name].removesuffix("px"))


class GanymedeGuideShell(QWidget):
    """One reusable, non-playable container for every indexed source guide."""

    def __init__(self, on_back: Callable[[], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuidesDetailPage")
        self._listing: GanymedeListing | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(_space("SPACE_MD"))

        header = QFrame(self)
        header.setObjectName("GuideCompactHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setSpacing(_space("SPACE_SM"))

        heading = QHBoxLayout()
        heading.setSpacing(_space("SPACE_SM"))
        self.back_button = AtlasButton("Retour", variant="secondary")
        self.back_button.clicked.connect(on_back)
        heading.addWidget(self.back_button)
        self.title_label = QLabel()
        self.title_label.setObjectName("GuideCompactTitle")
        self.title_label.setWordWrap(True)
        heading.addWidget(self.title_label, 1)
        header_layout.addLayout(heading)

        self.availability_label = QLabel("Parcours non disponible dans Atlas")
        self.availability_label.setObjectName("GuideHeaderMeta")
        header_layout.addWidget(self.availability_label)

        overall = QHBoxLayout()
        overall_title = QLabel("PROGRESSION GLOBALE")
        overall_title.setObjectName("GuideGlobalProgressTitle")
        overall.addWidget(overall_title)
        overall.addStretch(1)
        unavailable = QLabel("—")
        unavailable.setObjectName("GuideCompactMetricValue")
        overall.addWidget(unavailable)
        header_layout.addLayout(overall)

        self.global_progress = self._unavailable_bar("GuideGlobalProgress")
        header_layout.addWidget(self.global_progress)

        metrics = QHBoxLayout()
        metrics.setSpacing(_space("SPACE_MD"))
        for label, role in (
            ("Route", "GuideManualProgress"),
            ("Préparation", "GuideCompactPreparationProgress"),
        ):
            column = QVBoxLayout()
            column.setSpacing(_space("SPACE_XXS"))
            metric = QLabel(label)
            metric.setObjectName("GuideCompactMetricValue")
            column.addWidget(metric)
            column.addWidget(self._unavailable_bar(role))
            metrics.addLayout(column, 1)
        header_layout.addLayout(metrics)
        apply_unity_panel_shadow(header)
        root.addWidget(header)

        # The same indexed sheet and scroll surfaces as the shared Guide UI.
        # The empty sheet deliberately contains no invented source action.
        sheet_header = QFrame(self)
        sheet_header.setObjectName("GuideSheetHeader")
        sheet_header_layout = QVBoxLayout(sheet_header)
        sheet_header_layout.setSpacing(_space("SPACE_XXS"))
        self.sheet_meta = QLabel("Ganymède · référencé uniquement")
        self.sheet_meta.setObjectName("GuideSheetMeta")
        sheet_header_layout.addWidget(self.sheet_meta)
        self.sheet_title = QLabel("Aucune fiche chargée")
        self.sheet_title.setObjectName("GuideSheetTitle")
        sheet_header_layout.addWidget(self.sheet_title)
        apply_unity_panel_shadow(sheet_header)
        root.addWidget(sheet_header)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("GuideManualScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.empty_sheet = QFrame(self.scroll)
        self.empty_sheet.setObjectName("GuideManualSheet")
        self.scroll.setWidget(self.empty_sheet)
        root.addWidget(self.scroll, 1)

        nav = QFrame(self)
        nav.setObjectName("GuideManualNav")
        nav_layout = QHBoxLayout(nav)
        previous = AtlasButton("Précédent", variant="secondary")
        previous.setEnabled(False)
        nav_layout.addWidget(previous)
        nav_layout.addStretch(1)
        following = AtlasButton("Suivant", variant="secondary")
        following.setEnabled(False)
        nav_layout.addWidget(following)
        apply_unity_panel_shadow(nav)
        root.addWidget(nav)

    @staticmethod
    def _unavailable_bar(role: str) -> QProgressBar:
        bar = QProgressBar()
        bar.setObjectName(role)
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setEnabled(False)
        bar.setAccessibleName("Progression indisponible : aucune route certifiée")
        return bar

    def set_listing(self, listing: GanymedeListing) -> None:
        """Only render verified index metadata; never load a source route."""
        if not isinstance(listing, GanymedeListing):
            raise TypeError("GanymedeListing required")
        self._listing = listing
        self.title_label.setText(listing.title)
        self.title_label.setToolTip(listing.title)
        self.sheet_meta.setText("Ganymède · parcours non certifié")
        self.sheet_title.setText("Aucune fiche chargée")
