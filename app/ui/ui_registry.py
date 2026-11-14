"""Executable Qt-free index of the real Dev UI style contract.

This is not another palette, stylesheet or component implementation.
The 17 showcase families and the 12 consumers are owned by unity_palette;
this index attaches real QSS selectors, interactive states and source paths
so an audit can detect missing adoption instead of merely listing names.
"""

from __future__ import annotations

from app.ui.unity_palette import (
    UNITY_PAINTED_UI_ROLES, UNITY_UI_FAMILY_INDEX, UNITY_UI_CONSUMERS,
)


UI_FAMILY_QSS_SELECTORS: dict[str, tuple[str, ...]] = {
    "buttons": (
        "#PrimaryActionButton", "#SecondaryButton", "#DangerButton",
        "#InlineActionButton", "#PopupLinkButton", "#TopNavButton",
    ),
    "navigation": ("QTabBar::tab", "QTabWidget::pane", "QMenu {"),
    "data_views": ("QTreeWidget::item", "QTableWidget", "QHeaderView::section"),
    "scroll_resize": (
        "QSplitter::handle:horizontal", "QScrollBar:vertical",
        "QScrollArea", "QScrollBar::handle:vertical",
    ),
    "fields": (
        "QLineEdit", "QComboBox", "QSpinBox", "QPlainTextEdit",
        "QCheckBox", "QRadioButton", "QSlider::groove:horizontal",
    ),
    "advanced_fields": ("QDoubleSpinBox", "QDateEdit", "QTimeEdit"),
    "statuses": ('#StatusBadge[state="done"]', "#StatusChip"),
    "surfaces": ("#PageTitle", "#PanelTitle", "#MutedLabel", "#card"),
    "metrics": (),  # Values resolve into QSS, not standalone selectors.
    "panels": (
        "#OrganizerPanel", "#GuideRightPanelToggle",
        "#organizerPage QFrame#card", "QGroupBox",
    ),
    "startup": (
        "#PreloadPopupTitle", "#PreloadPopupCurrent", "#PreloadPopupProgress",
    ),
    "guides": (
        "#GuidePreparationPanel", "#GuideManualNav", "#GuideUltimeGeneratedView",
    ),
    "assets": ("#InlineShortcutButton", "QToolTip"),
    "motion": (),  # Unapproved animation prototypes; never promise adoption.
    "coverage": (),  # Documentation / source index, not a painted widget.
    "dialogs": ("#AtlasDialog", "#DialogHeader", "#DialogTitle"),
    "palette": (),  # Colors resolve into other families, not standalone QSS.
}


# Painted Qt iconography has no QSS selector, but belongs to the same
# Dev UI family registry. Derive roles by namespace to prevent duplicate maps.
UI_FAMILY_PAINTED_ROLES = {
    "startup": tuple(role for role in UNITY_PAINTED_UI_ROLES
                     if role.startswith("splash.")),
    "assets": tuple(role for role in UNITY_PAINTED_UI_ROLES
                    if role.startswith("organizer.") and role != "organizer.shadow"),
    "panels": ("organizer.shadow",),
}


# Each state is checked against the SAME compiled QSS that all Qt pages use.
UI_INTERACTION_QSS_SELECTORS = {
    "buttons": (
        "QPushButton:hover", "QPushButton:pressed",
        "QPushButton:disabled", "QPushButton:focus",
    ),
    "navigation": (
        "QTabBar::tab:hover", "QTabBar::tab:selected",
        "QTabBar::tab:selected:hover",
    ),
    "fields": ("QComboBox:hover", "QComboBox:disabled"),
    "statuses": ("#StatusChip:hover", "#StatusChip:checked"),
    "panels": (
        '#organizerPage QPushButton#primaryButton:hover',
        '#organizerPage QPushButton#primaryButton:pressed',
        '#organizerPage QPushButton#primaryButton:disabled',
        '#organizerPage QPushButton[atlasShortcutInset="true"]',
    ),
}


# Real source owners, not an assertion that every functional click was certified.
# Qt consumers inherit QApplication.setStyleSheet(atlas_stylesheet()).
# Organizer's exceptions are now *also* compiled into that global sheet.
# Launcher gets its colors through the Qt-free launcher_colors adapter.
UI_CONSUMER_INDEX = {
    "Accueil": {
        "paths": ("app/pages/home_page.py",), "adapter": "qt",
    },
    "Personnage": {
        "paths": ("app/pages/character_page.py", "app/pages/_character_page_impl.py"),
        "adapter": "qt",
    },
    "Quêtes": {
        "paths": ("app/pages/_quests_page_impl.py",), "adapter": "qt",
    },
    "Succès": {
        "paths": ("app/modules/encyclopedia/views/achievements_view.py",),
        "adapter": "qt",
    },
    "Guides": {
        "paths": (
            "app/modules/encyclopedia/views/guides_view.py",
            "app/modules/encyclopedia/views/shared_manual_guide_view.py",
        ), "adapter": "qt",
    },
    "Bestiaire": {
        "paths": ("app/modules/encyclopedia/views/encyclopedia_page.py",),
        "adapter": "qt",
    },
    "Outils": {
        "paths": ("app/pages/craft_page.py", "app/ui/world_scan_panel.py"),
        "adapter": "qt",
    },
    "Stuffs": {
        "paths": ("app/pages/equipment_page.py",), "adapter": "qt",
    },
    "Organizer": {
        "paths": (
            "app/pages/organizer/organizer_ui.py",
            "app/ui/organizer_style.py",
        ), "adapter": "qt_scoped",
    },
    "Almanax": {
        "paths": ("app/pages/home_page.py",), "adapter": "qt",
    },
    "Réseau": {
        "paths": ("app/ui/network_bridge.py",), "adapter": "qt",
    },
    "Launcher": {
        "paths": (
            "app/distribution/launcher.py", "app/distribution/launcher_ui.py",
        ), "adapter": "tk",
    },
}


def validate_ui_index() -> None:
    """Fail promptly if a Dev UI family or consumer lacks its index entry."""
    families = tuple(UNITY_UI_FAMILY_INDEX)
    if families != tuple(UI_FAMILY_QSS_SELECTORS):
        raise ValueError("Dev UI family selector index differs from gallery order")
    if tuple(UNITY_UI_CONSUMERS) != tuple(UI_CONSUMER_INDEX):
        raise ValueError("Dev UI consumer index differs from module list")
    painted = [role for group in UI_FAMILY_PAINTED_ROLES.values() for role in group]
    if len(painted) != len(set(painted)) or set(painted) != set(UNITY_PAINTED_UI_ROLES):
        raise ValueError("Unindexed or duplicated painted Unity role")
    if any(name not in UI_FAMILY_QSS_SELECTORS for name in UI_FAMILY_PAINTED_ROLES):
        raise ValueError("Painted Unity role belongs to an unknown Dev UI family")
    for name, info in UI_CONSUMER_INDEX.items():
        if not info["paths"] or info["adapter"] not in {"qt", "qt_scoped", "tk"}:
            raise ValueError(f"Invalid UI consumer registration: {name}")
