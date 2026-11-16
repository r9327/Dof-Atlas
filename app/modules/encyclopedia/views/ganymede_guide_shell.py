"""Metadata-only Ganymede preview using the *real* shared Guide composition.

No new header, navigation, sheet, layout, styling or route implementation.
The 95 indexed guides share one lazily created, non-playable reader.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from app.ui.unity_skin import sprite_icon_path

from app.modules.encyclopedia.views.guide_library_sources import GanymedeListing
from app.modules.encyclopedia.views.shared_manual_guide_view import (
    SharedGuideManualCard, SharedGuideManualView,
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
        # The metadata shell uses a special dash for its 0/0 selector;
        # clear that sentinel before the real 1-based draft navigation.
        self.page_jump.setSpecialValueText("")
        self.page_jump.setEnabled(True)
        # A disabled lime validation button still looks actionable in Unity;
        # the review has no completion authority, so show only navigation.
        self.validation_host.hide()
        self.sheet_meta_label.show()
        # Populate the complete route index once; only a bounded window
        # of cards is ever created in the scrollable main reader.
        self.summary_button.setEnabled(True)
        self._populate_summary()
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

    @staticmethod
    def _compact_review_card(card: dict) -> bool:
        """Limit expensive height estimates to genuine long-text steps."""
        rows = card.get("manual_sections", {}).get("now", ())
        return (
            isinstance(rows, list)
            and 0 < len(rows) <= 8
            and all(isinstance(row.get("text"), str)
                    and len(row["text"]) <= 160 for row in rows)
        )

    def _render_window(self, *, reset_scroll: bool = False) -> None:
        if not self._inspection_active:
            super()._render_window(reset_scroll=reset_scroll)
            return
        self._catalog_prefetch_timer.stop()
        self._catalog_prefetch_index = None
        self._clear_cards()
        cards = self.service.cards
        if not cards:
            self._review_end_index = 0
            return

        # Exactly the same bounded reading window as every shared Guide.
        # The first source step is active; the following ones only fill the
        # scrolling area without becoming validation targets.
        index = max(0, min(int(self.view_index), len(cards) - 1))
        viewport = self.scroll.viewport()
        margins = self.cards_layout.contentsMargins()
        label_width = max(
            120, viewport.width() - margins.left() - margins.right() - 88
        )
        end = index
        for number in self._reading_step_range(index):
            widget = SharedGuideManualCard(
                self.service, self.character_key, cards[number], number,
                # The active stage title already lives in GuideSheetHeader.
                # Following read-ahead stages retain their own titles.
                show_header_title=number != index,
            )
            widget.page_check.setEnabled(False)
            widget.page_check.hide()
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            widget.layout().setAlignment(Qt.AlignTop)

            # Preserve a full source step even when text wraps well beyond
            # the viewport. Qt's scroll area owns the overflow.
            estimated = max(1, widget.sizeHint().height())
            for label in widget.findChildren(QLabel):
                if label.wordWrap() and label.hasHeightForWidth():
                    wrapped = label.heightForWidth(label_width)
                    if wrapped > label.sizeHint().height():
                        estimated += wrapped - label.sizeHint().height()
            if not self._compact_review_card(cards[number]):
                widget.setMinimumHeight(max(1, estimated))
            else:
                widget.setMinimumHeight(widget.minimumSizeHint().height())
            self.cards_layout.addWidget(widget)
            widget.show()
            self.rendered_card_count += 1
            end = number + 1

        self.cards_layout.addStretch(1)
        self._review_end_index = end
        self._review_viewport_size = (viewport.width(), viewport.height())
        self.prev_button.setEnabled(index > 0)
        self.next_button.setEnabled(index + 1 < len(cards))
        self.guide_button.setToolTip("Retour au catalogue des Guides")
        if reset_scroll:
            self._reset_scroll_to_top()

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
            self.summary_button.setChecked(False)
            self.summary_button.setEnabled(False)
            self.summary_panel.hide()
            self.summary_list.clear()
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
