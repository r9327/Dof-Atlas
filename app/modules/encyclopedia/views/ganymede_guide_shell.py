"""Metadata-only Ganymede preview using the *real* shared Guide composition.

No new header, navigation, sheet, layout, styling or route implementation.
The 95 indexed guides share one lazily created, non-playable reader.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QWidget

from app.ui.unity_skin import sprite_icon_path

from app.modules.encyclopedia.views.guide_library_sources import GanymedeListing
from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView


class _MetadataOnlyGuide:
    """Strictly the title and empty card list: never a runtime Guide service."""

    def __init__(self) -> None:
        self.guide_title = ""
        self.cards: tuple[()] = ()


class GanymedeGuideShell(SharedGuideManualView):
    """An empty state of the canonical shared reader, not a parallel UI."""

    def __init__(
        self,
        on_back: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        self._listing: GanymedeListing | None = None

        # Initialize the real Qt inheritance chain. The preview overrides
        # refresh and participant loading, so this only constructs the shared
        # widgets; no playable route or progress service is ever created.
        super().__init__(
            _MetadataOnlyGuide(),
            parent=parent,
            participant_service=object(),
        )

        self.backToGuidesRequested.connect(on_back)
        self.guide_button.setToolTip("Retour au catalogue des Guides")
        self.guide_button.setAccessibleName("Retour aux Guides")
        self.sheet_meta_label.setText("Ganymède · parcours non certifié")
        self.sheet_title_label.setText("Aucune fiche chargée")
        # An empty indexed route has no page 1. Keep the original selector
        # present but disabled, without displaying a fictitious "1 / 0".
        self.page_jump.setSuffix("")
        self.page_jump.setRange(0, 0)
        self.page_jump.setSpecialValueText("—")

        # The shell shows structure only. No invented progression, actions,
        # controls or enabled behavior without an authorized source route.
        for widget in (
            self.global_progress_bar,
            self.route_bar,
            self.preparation_bar,
            self.summary_button,
            self.preparation_button,
            self.overlay_button,
            self.settings_button,
            self.route_lock_check,
            self.page_jump,
            self.participants_button,
            self.prev_button,
            self.next_button,
        ):
            widget.setEnabled(False)
        for progress in (
            self.global_progress_bar,
            self.route_bar,
            self.preparation_bar,
        ):
            progress.setRange(0, 1)
            progress.setValue(0)
            progress.setAccessibleName("Progression indisponible : aucune route certifiée")
        self.global_progress_label.setText("—")
        self.route_progress_label.setText("—")
        self.preparation_progress_label.setText("—")

    def _restore_route_lock_state(self) -> None:
        """An untrusted metadata entry has no persistent Guide preferences."""

    def _refresh_participants_panel(self) -> None:
        """No account/character lookup for a metadata-only container."""

    def selected_participant_keys(self) -> tuple[str, ...]:
        return ()

    def refresh(self, *, reset_to_active: bool = False) -> None:
        """No progress or guide-runtime refresh is permitted in preview."""

    def set_listing(self, listing: GanymedeListing, *, artwork: QPixmap | None = None) -> None:
        """Update only verified title metadata; never turn it into a route."""
        if not isinstance(listing, GanymedeListing):
            raise TypeError("GanymedeListing required")
        if listing.playable:
            raise ValueError("Playable Guides must use the authorized runtime")
        self._listing = listing
        self.service.guide_title = listing.title
        self.guide_title_label.setText(listing.title)
        self.guide_title_label.setToolTip(listing.title)
        # Use the Home card's own artwork, never a mismatched Dofus icon.
        if artwork is not None and not artwork.isNull():
            pixmap = artwork.scaled(QSize(32, 32), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            fallback = sprite_icon_path("guide")
            pixmap = QIcon(str(fallback)).pixmap(QSize(32, 32)) if fallback else None
        if pixmap is not None and not pixmap.isNull():
            self.guide_icon_label.setPixmap(pixmap)
            self.guide_icon_label.setToolTip(listing.title)
            self.guide_icon_label.show()
        else:
            self.guide_icon_label.clear()
            self.guide_icon_label.hide()
        self.sheet_meta_label.setText("Ganymède · parcours non certifié")
        self.sheet_title_label.setText("Aucune fiche chargée")
