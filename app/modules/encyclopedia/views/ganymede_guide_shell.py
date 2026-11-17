"""Metadata-only Ganymede preview using the *real* shared Guide composition.

No new header, navigation, sheet, layout, styling or route implementation.
The 95 indexed guides share one lazily created, non-playable reader.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QWidget

from app.ui.unity_skin import sprite_icon_path

from app.modules.encyclopedia.views.guide_library_sources import GanymedeListing
from app.modules.encyclopedia.views.shared_manual_guide_view import (
    SharedGuideManualView,
)


class _MetadataOnlyGuide:
    """Strictly the title and empty card list: never a runtime Guide service."""

    def __init__(self) -> None:
        self.guide_title = ""
        self.cards: tuple[dict, ...] = ()

    @staticmethod
    def can_write_progress() -> bool:
        return False

    @staticmethod
    def card_auto_complete(_character_key: str, _card: dict) -> bool:
        return False

    @staticmethod
    def page_checked(_character_key: str, _card: dict, _index: int) -> bool:
        return False

    @staticmethod
    def card_key(card: dict, _index: int) -> str:
        return str(card.get("source_step_id") or "")


class GanymedeGuideShell(SharedGuideManualView):
    """An empty state of the canonical shared reader, not a parallel UI."""

    def __init__(
        self,
        on_back: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        self._listing: GanymedeListing | None = None
        self._inspection_active = False
        self._review_end_index = 0
        self._review_history: list[int] = []
        self._review_viewport_size: tuple[int, int] = (0, 0)

        # Initialize the real Qt inheritance chain. The preview overrides
        # refresh and participant loading, so this only constructs the shared
        # widgets; no playable route or progress service is ever created.
        super().__init__(
            _MetadataOnlyGuide(),
            parent=parent,
            participant_service=object(),
        )

        self._review_resize_timer = QTimer(self)
        self._review_resize_timer.setSingleShot(True)
        self._review_resize_timer.timeout.connect(self._refit_review_cards)
        self.backToGuidesRequested.connect(on_back)
        self.guide_button.setToolTip("Retour au catalogue des Guides")
        self.guide_button.setAccessibleName("Retour aux Guides")
        self.sheet_meta_label.clear()
        self.sheet_meta_label.hide()
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
            self.preparation_bar,
            self.preparation_button,
            self.overlay_button,
            self.page_jump,
            self.participants_button,
            self.prev_button,
            self.next_button,
        ):
            widget.setEnabled(False)
        for progress in (
            self.global_progress_bar,
            self.preparation_bar,
        ):
            progress.setRange(0, 1)
            progress.setValue(0)
            progress.setAccessibleName("Progression indisponible : aucune route certifiée")
        self.global_progress_label.setText("—")
        self.preparation_progress_label.setText("—")

    def _refresh_participants_panel(self) -> None:
        """No account/character lookup for a metadata-only container."""

    def selected_participant_keys(self) -> tuple[str, ...]:
        return ()

    def _progress_participant_keys(self) -> tuple[str, ...]:
        # The review has NO participant service and must never resolve one.
        return ()

    def refresh(self, *, reset_to_active: bool = False) -> None:
        """No progress or guide-runtime refresh is permitted in preview."""

    def _guide_button_clicked(self) -> None:
        if self._inspection_active:
            self.backToGuidesRequested.emit()
            return
        super()._guide_button_clicked()

    def show_cawotte_review(self) -> bool:
        """Review 64 local unverified steps; NEVER write player progress."""
        if self._listing is None or self._listing.source_id != 2205:
            return False
        from app.modules.encyclopedia.services.guide_cawotte_pilot_preview import (
            cawotte_review_cards,
        )
        self.service.cards = cawotte_review_cards()
        self._inspection_active = True
        self.service.guide_title = "Dofus Cawotte"
        self.guide_title_label.setText(self.service.guide_title)
        self.guide_title_label.setToolTip(self.service.guide_title)
        self.view_index = 0
        self.active_index = 0
        self._review_end_index = 0
        self._review_history.clear()
        self._preview_preparation_checked.clear()
        # The metadata shell uses a special dash for its 0/0 selector;
        # clear that sentinel before the real 1-based draft navigation.
        self.page_jump.setSpecialValueText("")
        self.page_jump.setEnabled(True)
        # A disabled lime validation button still looks actionable in Unity;
        # the review has no completion authority, so show only navigation.
        self.validation_host.hide()
        self.sheet_meta_label.show()
        # Only the current source fiche is mounted in the bounded reader.
        # Review-only metadata contains typed prerequisites/materials. Allow
        # inspecting their own tabs without granting gameplay/progress writes.
        self._preparation_loaded = False
        self._preparation_needs = ()
        self._preparation_preview = ()
        self.preparation_button.setEnabled(True)
        for tab in self.preparation_tab_group.buttons():
            if tab.property("tabKey") == "Prérequis":
                tab.setChecked(True)
                break
        self._preparation_tab_changed("Prérequis")
        self._refresh_header()
        self._render_window()
        return True


    def _show_index(self, index: int) -> None:
        if self._inspection_active:
            # A direct jump selects a source step, not a fabricated page ID.
            self._review_history.clear()
        super()._show_index(index)

    def navigate_relative(self, delta: int) -> None:
        # Précédent/Suivant always moves one active step, even when more
        # steps are visible below in the same scrollable reading viewport.
        super().navigate_relative(delta)

    def _render_window(self, *, reset_scroll: bool = False) -> None:
        # All 95 source containers and authorized imports use the same shared
        # card construction, source layout and 1:1 reading/navigation policy.
        # The metadata-only pilot adds only read-only state, never its own UI.
        super()._render_window(reset_scroll=reset_scroll)
        if self._inspection_active:
            self._review_end_index = self.view_index + self.rendered_card_count
            viewport = self.scroll.viewport()
            self._review_viewport_size = (viewport.width(), viewport.height())
            self.guide_button.setToolTip("Retour au catalogue des Guides")

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        if self._inspection_active and hasattr(self, "_review_resize_timer"):
            self._review_resize_timer.start(0)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        if self._inspection_active and hasattr(self, "_review_resize_timer"):
            # The real catalogue sets the page visible AFTER the initial
            # candidate construction. Qt must lay out the actual viewport
            # before we measure/present cards, or page 1 may paint blank.
            self._review_viewport_size = (0, 0)
            self._review_resize_timer.start(0)

    def _refit_review_cards(self) -> None:
        if not self._inspection_active:
            return
        viewport = self.scroll.viewport()
        size = (viewport.width(), viewport.height())
        if size != self._review_viewport_size:
            # A resized viewport invalidates page-history boundaries, never
            # the identities or ordering of the 64 original source steps.
            self._review_history.clear()
            self._refresh_header()
            self._render_window(reset_scroll=True)

    def set_listing(self, listing: GanymedeListing, *, artwork: QPixmap | None = None) -> None:
        """Switch metadata and evict draft sheets from the reused renderer."""
        if not isinstance(listing, GanymedeListing):
            raise TypeError("GanymedeListing required")
        if listing.playable:
            raise ValueError("Playable Guides must use the authorized runtime")
        if self._inspection_active:
            self._inspection_active = False
            self._review_resize_timer.stop()
            self._review_history.clear()
            self._review_end_index = 0
            self._review_viewport_size = (0, 0)
            self.preparation_button.setChecked(False)
            self.preparation_button.setEnabled(False)
            self.preparation_panel.hide()
            self._preparation_loaded = False
            self._preparation_preview = ()
            self._preparation_needs = ()
            for tab in self.preparation_tab_group.buttons():
                if tab.property("tabKey") == "À préparer":
                    tab.setChecked(True)
                    break
            self._preparation_tab_changed("À préparer")
            self.service.cards = ()
            self._clear_cards()
            # The validation host owns the temporary read-only check button,
            # so clearing cards alone would leave an orphaned widget visible.
            while self.validation_layout.count():
                item = self.validation_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
            self.sheet_meta_label.clear()
            self.sheet_meta_label.hide()
            self.page_jump.blockSignals(True)
            self.page_jump.setRange(0, 0)
            self.page_jump.setSuffix("")
            self.page_jump.setSpecialValueText("—")
            self.page_jump.blockSignals(False)
            self.page_jump.setEnabled(False)
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
        # Switching source must not retain the previous guide's drawer tab.
        self._source_prerequisites_defaulted = False
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

        self.sheet_title_label.setText("Aucune fiche chargée")
