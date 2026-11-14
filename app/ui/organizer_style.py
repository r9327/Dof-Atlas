"""Organizer-specific geometry and frosted Unity finish, in the shared UI QSS.

Qt consumers do not set a private stylesheet. The application theme appends
these scoped selectors after its global Qt / Unity rules so the Organizer
retains the exact validated visual presentation and hover/disabled states.
Raw QSS is rendered only by app.ui.theme using the canonical Unity tokens.
"""

from __future__ import annotations


ORGANIZER_STYLE_TEMPLATE = r"""
            #organizerPage QFrame#card {
                /* GlassCard paints a cached diffused backdrop and specular
                   rim; QSS cannot render a frosted material on its own. */
                background: transparent;
                border: none;
                border-radius: 10px;
                border-image: none;
            }
            #organizerPage QPushButton#primaryButton,
            #organizerPage QPushButton#secondaryButton,
            #organizerPage QPushButton#PrimaryActionButton,
            #organizerPage QPushButton#SecondaryButton,
            #organizerPage QPushButton#segmentedButton,
            #organizerPage QPushButton#segmentedButtonActive,
            #organizerPage QPushButton#dangerButton {
                background: @GLASS_BUTTON;
                border: 1px solid @BORDER;
                border-radius: 8px;
                border-image: none;
                color: @TEXT_SOFT;
                text-align: center;
                padding: 0px 5px;
            }
            #organizerPage QPushButton#primaryButton,
            #organizerPage QPushButton#PrimaryActionButton,
            #organizerPage QPushButton#segmentedButtonActive {
                background: @GLASS_GREEN;
                border-color: @GREEN_BORDER;
                color: @TEXT;
            }
            #organizerPage QPushButton#dangerButton {
                background: @RED_DARK;
                border-color: @RED;
                color: @TEXT;
                font-weight: 700;
            }
            #organizerPage QPushButton#primaryButton:hover,
            #organizerPage QPushButton#secondaryButton:hover,
            #organizerPage QPushButton#PrimaryActionButton:hover,
            #organizerPage QPushButton#SecondaryButton:hover,
            #organizerPage QPushButton#segmentedButton:hover,
            #organizerPage QPushButton#segmentedButtonActive:hover {
                background: @GLASS_HOVER;
                border-color: @BORDER_STRONG;
                color: @TEXT;
            }
            #organizerPage QPushButton#primaryButton:pressed,
            #organizerPage QPushButton#secondaryButton:pressed,
            #organizerPage QPushButton#PrimaryActionButton:pressed,
            #organizerPage QPushButton#SecondaryButton:pressed,
            #organizerPage QPushButton#segmentedButton:pressed,
            #organizerPage QPushButton#segmentedButtonActive:pressed {
                background: @PANEL_ACTIVE;
                border-color: @GREEN_BORDER;
            }
            #organizerPage QPushButton#dangerButton:hover {
                background: @RED_HOVER;
                border-color: @RED;
            }
            #organizerPage QPushButton#dangerButton:pressed {
                background: @RED_DARK;
                border-color: @RED;
            }
            #organizerPage QPushButton#primaryButton:disabled,
            #organizerPage QPushButton#secondaryButton:disabled,
            #organizerPage QPushButton#PrimaryActionButton:disabled,
            #organizerPage QPushButton#SecondaryButton:disabled,
            #organizerPage QPushButton#segmentedButton:disabled,
            #organizerPage QPushButton#segmentedButtonActive:disabled,
            #organizerPage QPushButton#dangerButton:disabled {
                background: @PANEL;
                border-color: @BORDER_SOFT;
                color: @TEXT_DISABLED;
            }
            /* All seven embedded shortcuts, STOP and character slots are
               the SAME keyBadge family and 52x22 dimensions. */
            #organizerPage QPushButton#keyBadge {
                background: @GLASS_BUTTON;
                border: 1px solid @BORDER_STRONG;
                border-radius: 6px;
                border-image: none;
                color: @TEXT;
                font-size: 10px;
                font-weight: 700;
                min-width: 0px;
                /* 20px content + 2px borders = exact 22px Qt badge.
                   A zero min-height allowed Qt to shrink them to 12px. */
                min-height: 20px;
                max-height: 20px;
                padding: 0px 2px;
                text-align: center;
            }
            #organizerPage QPushButton#keyBadge:hover {
                background: @GLASS_HOVER;
                border-color: @GREEN_BORDER;
            }
            #organizerPage QPushButton#keyBadge:pressed {
                background: @GREEN_DARK;
                border-color: @GREEN;
            }
            #organizerPage QPushButton#keyBadge:disabled {
                background: @PANEL;
                border-color: @BORDER_SOFT;
                color: @TEXT_DISABLED;
            }
            #organizerPage QPushButton#iconButton,
            #organizerPage QPushButton#iconButtonDanger {
                background: @GLASS_BUTTON;
                border: 1px solid @BORDER;
                border-radius: 6px;
                border-image: none;
                color: @TEXT_SOFT;
                padding: 0px;
            }
            #organizerPage QPushButton#iconButton:hover,
            #organizerPage QPushButton#iconButtonDanger:hover {
                background: @GLASS_HOVER;
                border-color: @BORDER_STRONG;
            }
            #organizerPage QPushButton#iconButton:disabled,
            #organizerPage QPushButton#iconButtonDanger:disabled {
                background: @PANEL;
                color: @TEXT_DISABLED;
                border-color: @BORDER_SOFT;
            }
            #organizerPage QWidget#OrganizerTransparentHost {
                background: transparent;
                border: none;
                border-image: none;
            }
            #organizerPage QLineEdit#comboField {
                background: @PANEL_2;
                border: 1px solid @BORDER;
                border-radius: 8px;
                border-image: none;
                color: @TEXT;
                padding: 0px 8px;
            }
            #organizerPage QLineEdit#comboField:focus {
                background: @PANEL_HOVER;
                border-color: @GREEN;
            }
            #organizerPage QFrame#OrganizerSpeedSelector,
            #organizerPage QFrame#OrganizerModeSwitch {
                background: @PANEL;
                border: none;
                border-radius: 8px;
                border-image: none;
            }
            #organizerPage QFrame#OrganizerSpeedHighlight,
            #organizerPage QFrame#OrganizerModeHighlight {
                background: @GREEN_DARK;
                border: 1px solid @GREEN_BORDER;
                border-radius: 7px;
                border-image: none;
            }
            #organizerPage QFrame#OrganizerModeHighlightArmed {
                background: @ACTIVE_GRADIENT;
                border: 1px solid @GREEN;
                border-radius: 7px;
                border-image: none;
            }
            #organizerPage QPushButton#OrganizerSpeedChoice,
            #organizerPage QPushButton#OrganizerSpeedChoiceSelected,
            #organizerPage QPushButton#OrganizerModeChoice {
                background: transparent;
                border: none;
                border-image: none;
                border-radius: 6px;
                padding: 0px 2px;
                color: @TEXT_SOFT;
                font-size: 11px;
                font-weight: 600;
                min-height: 0px;
            }
            #organizerPage QPushButton#OrganizerSpeedChoiceSelected {
                color: @TEXT;
                font-weight: 700;
            }
            #organizerPage QScrollArea#OrganizerContentScroll,
            #organizerPage QScrollArea#OrganizerZaapScroll,
            #organizerPage QWidget#OrganizerContentViewport,
            #organizerPage QWidget#OrganizerZaapViewport,
            #organizerPage QWidget#OrganizerScrollContent,
            #organizerPage QWidget#OrganizerZaapContent,
            #organizerPage QWidget#ZaapFavoritesRow {
                background: transparent;
                border: none;
                border-image: none;
            }
            #organizerPage QWidget#favoriteChip {
                background: @GLASS_BUTTON;
                border: 1px solid @BORDER_CARD;
                border-radius: 8px;
                border-image: none;
            }
            #organizerPage QWidget#favoriteChip:hover {
                background: @GLASS_HOVER;
                border-color: @BORDER_STRONG;
            }
            #organizerPage QFrame#characterSlotEmpty,
            #organizerPage QFrame#characterSlotMissing {
                background: @PANEL_2;
                border: 1px solid @BORDER_SOFT;
                border-radius: 8px;
                border-image: none;
            }
            #organizerPage QFrame#characterSlot {
                background: @PANEL_GRADIENT;
                border: 1px solid @BORDER;
                border-radius: 8px;
                border-image: none;
            }
            #organizerPage QFrame#characterSlotDragging,
            #organizerPage QFrame#characterSlotDropTarget {
                background: @PANEL_ACTIVE;
                border: 1px solid @GREEN_BORDER;
                border-radius: 8px;
                border-image: none;
            }
            /* A macro button that embeds a shortcut gets its own indexed
               content inset. Keep styling in the global Unity system. */
            #organizerPage QPushButton[atlasShortcutInset="true"],
            #organizerPage QPushButton#primaryButton[atlasShortcutInset="true"],
            #organizerPage QPushButton#secondaryButton[atlasShortcutInset="true"],
            #organizerPage QPushButton#PrimaryActionButton[atlasShortcutInset="true"],
            #organizerPage QPushButton#SecondaryButton[atlasShortcutInset="true"],
            #organizerPage QPushButton#dangerButton[atlasShortcutInset="true"] {
                text-align: center;
                padding-left: 4px;
                padding-right: 64px;
                font-size: 10px;
            }
"""
