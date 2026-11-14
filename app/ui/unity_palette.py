"""Canonical Qt-free Unity color tokens shared by the main UI and Tk launcher.

Keep all color literals here. Importing this module must never initialize Qt,
local artwork or any game runtime; the updater is an independent small EXE.
"""
from __future__ import annotations

from collections.abc import Mapping


UNITY_PALETTE = {
    "BG": "#151821",
    "BG_GRADIENT_START": "#253967",
    "SIDEBAR": "#19243F",
    "PANEL": "#1B2746",
    "PANEL_2": "#213154",
    "PANEL_HOVER": "#2C3C69",
    "PANEL_ACTIVE": "#344978",
    # Glass/overlay surfaces are semantic Unity roles, never per-page palettes.
    "LIST_SURFACE": "#15203B",
    "NAV_SURFACE": "#19264B",
    "SCROLL_SURFACE": "#151D32",
    "TOOLTIP_SURFACE": "#192657",
    "FIELD_SURFACE": "#141D37",
    "BORDER": "#475F89",
    "BORDER_SOFT": "#354966",
    "BORDER_CARD": "#617CA6",
    "BORDER_STRONG": "#7B9BC8",
    "TEXT": "#F1F6FB",
    "TEXT_SOFT": "#D9EAF2",
    "TEXT_MUTED": "#B8C6E3",
    "TEXT_DISABLED": "#8998B6",
    "GREEN": "#9FCE51",
    "GREEN_HOVER": "#B1DC64",
    "GREEN_DARK": "#497332",
    "GREEN_BORDER": "#94BA62",
    "GUIDE_PREPARATION_BORDER": "#8299C0",
    "GUIDE_PREPARATION_TEXT": "#FFFFFF",
    "GUIDE_ITEM_TEXT": "#F6F8FE",
    "GUIDE_STATUS_TEXT": "#E4EDFC",
    "GUIDE_NAV_BORDER": "#6B87B3",
    "GUIDE_TOGGLE_TOP": "#445B89",
    "GUIDE_TOGGLE_BOTTOM": "#273A62",
    "GUIDE_TOGGLE_BORDER": "#8098BF",
    "GUIDE_TOGGLE_ACTIVE": "#536F9D",
    "GUIDE_TOGGLE_ACTIVE_BORDER": "#B8CBE8",
    "GUIDE_TOGGLE_HOVER": "#516EA0",
    # Dedicated Guide surfaces: named in the same Unity palette and not QSS literals.
    "GUIDE_COMPACT_SURFACE": "#182546",
    "GUIDE_SUMMARY_TOP": "#455B8C",
    "GUIDE_SUMMARY_BOTTOM": "#18264A",
    "GUIDE_PREPARATION_ROW": "#1F3057",
    "GUIDE_PREPARATION_ROW_BORDER": "#7295C4",
    "GUIDE_COPY_HOVER": "#668BC4",
    "GUIDE_MANUAL_NAV_SURFACE": "#131F3B",
    "SHELL_GRADIENT": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #192657, stop:1 #151821)",
    "PANEL_GRADIENT": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #24395F, stop:1 #192657)",
    "ACTIVE_GRADIENT": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6E9B41, stop:1 #497332)",
}


# Shared geometrical tokens for Qt theme and Unity skin. Keep the exact
# existing values: a style override must reach both layers without drift.
UNITY_RADII = {
    "RADIUS_XS": "4px",
    "RADIUS_SM": "6px",
    "RADIUS_MD": "8px",
    "RADIUS_LG": "10px",
    "RADIUS_XL": "12px",
}


# What each color does in the actual UI, not another color palette.
# Keep the darkStone component sprites and their original Qt state mapping.
UNITY_UI_USAGE = (
    ("Fond de fenêtre", "BG", "BORDER"),
    ("Carte et panneau", "PANEL", "BORDER"),
    ("En-tête et navigation", "NAV_SURFACE", "TEXT_SOFT"),
    ("Onglet sélectionné", "PANEL_ACTIVE", "GREEN_BORDER"),
    ("Contrôle secondaire", "PANEL_2", "BORDER_CARD"),
    ("Champ de saisie", "FIELD_SURFACE", "BORDER"),
    ("Liste et tableau", "LIST_SURFACE", "BORDER"),
    ("Survol", "PANEL_HOVER", "BORDER_STRONG"),
    ("Info-bulle", "TOOLTIP_SURFACE", "TEXT"),
    ("Action validée", "GREEN", "GREEN_BORDER"),
)

# The gallery highlights the small, meaningful palette. Full technical
# variants remain available separately and never become a second theme.
UNITY_MAIN_ROLES = (
    "BG", "PANEL", "PANEL_2", "NAV_SURFACE", "FIELD_SURFACE",
    "BORDER", "TEXT", "TEXT_MUTED", "PANEL_ACTIVE", "GREEN",
)

# The exact frosted-glass intensity previously owned by Organizer is
# centralized here so the shell, global QSS and its preview cannot drift.
# This module stays Qt-free for the standalone Tk launcher.
UNITY_GLASS_INTENSITY = 0.5


def unity_rgba(
    role: str, opacity: int, palette: Mapping[str, str] | None = None,
) -> str:
    """Qt-free equivalent of QColor('#RRGGBB') for QSS gradients."""
    colors = UNITY_PALETTE if palette is None else palette
    color = str(colors[role])
    try:
        if len(color) != 7 or not color.startswith("#"):
            raise ValueError(color)
        red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    except ValueError:
        # QColor invalid-input semantics used by the previous Organizer code.
        red, green, blue = 0, 0, 0
    return f"rgba({red}, {green}, {blue}, {opacity})"


def unity_glass_gradient(
    top: str = "PANEL_ACTIVE", bottom: str = "PANEL_2", *,
    top_alpha: int = 180, bottom_alpha: int = 196,
    palette: Mapping[str, str] | None = None,
) -> str:
    """One formula for Unity Organizer glass, regardless of consumer."""
    alpha = lambda value: 255 - round((255 - value) * UNITY_GLASS_INTENSITY)
    return (
        "qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        f"stop:0 {unity_rgba(top, alpha(top_alpha), palette)},"
        f"stop:1 {unity_rgba(bottom, alpha(bottom_alpha), palette)})"
    )


# Pixel metrics shared by the stylesheet and the real Qt components.
# Preserves the existing compact/normal sizing (no layout redesign).
UNITY_SIZES_PX = {
    "control_compact": 24,
    "control_normal": 32,
    "control_large": 40,
    "icon_small": 16,
    "icon_normal": 20,
    "icon_large": 24,
    "icon_xlarge": 32,
}
UNITY_ICON_NAMES = (
    "guide", "quest", "success", "encyclopedia",
    "character", "dofus", "map", "inventory",
)

# Additional module slots: the *same* Unity sprites folder is the source
# of truth. Assets may use a French/English extraction name depending on
# the archive; do not treat a missing exact English filename as a missing
# original logo or substitute a made-up one.
UNITY_ICON_PENDING = (
    "jobs", "bestiary", "craft", "equipment", "organizer", "almanax",
)
UNITY_ICON_FILE_ALIASES = {
    "jobs": ("jobs", "job", "metier", "metiers", "profession", "professions"),
    "bestiary": ("bestiary", "bestiaire", "monster", "monsters"),
    "craft": ("craft", "crafts", "crafting"),
    "equipment": ("equipment", "stuff", "stuffs"),
    "organizer": ("organizer", "organiseur"),
    "almanax": ("almanax",),
}

# Single shared state index for every interactive visual family.
UNITY_INTERACTION_STATES = (
    "normal", "hover", "pressed", "selected", "focus", "disabled",
)
UNITY_CHIP_TONES = ("success", "danger", "warning", "info", "neutral")

# Index of the EXISTING Dev UI showcase, not a second theme or widget library.
# Every visual family references the current Qt/theme owner and real samples.
# "module" and "prototype" deliberately do not claim global adoption.
# Colors, fonts, sizes and QSS stay in their existing canonical mappings.
UNITY_UI_FAMILY_INDEX = {
    "buttons": {
        "title": "Boutons · variantes et états",
        "components": ("AtlasButton", "PrimaryActionButton", "SecondaryButton", "DangerButton", "TopNavButton", "InlineActionButton", "PopupLinkButton"),
        "style_owner": "app/ui/components.py + app/ui/theme.py",
        "scope": "shared",
    },
    "navigation": {
        "title": "Onglets · menus et navigation",
        "components": ("QTabWidget", "QTabBar", "QMenu", "AtlasButton"),
        "style_owner": "app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "data_views": {
        "title": "Listes · arborescences · tableaux",
        "components": ("QTreeWidget", "QTableWidget", "QHeaderView", "QListWidget"),
        "style_owner": "app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "scroll_resize": {
        "title": "Défilement · listes · redimensionnement",
        "components": ("QSplitter", "QScrollArea", "QScrollBar", "QListWidget", "Panel"),
        "style_owner": "app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "fields": {
        "title": "Saisie · sélection · progression",
        "components": ("QLineEdit", "QComboBox", "QSpinBox", "QPlainTextEdit", "QCheckBox", "QRadioButton", "QProgressBar", "QSlider"),
        "style_owner": "app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "advanced_fields": {
        "title": "Formulaires avancés · états et formats",
        "components": ("QLineEdit", "QDoubleSpinBox", "QDateEdit", "QTimeEdit", "QCheckBox"),
        "style_owner": "app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "statuses": {
        "title": "États · badges · retours visuels",
        "components": ("AtlasStatusBadge", "StatusBadge", "StatusChip", "GuideSummaryButton", "QProgressBar"),
        "style_owner": "app/ui/components.py + app/ui/theme.py",
        "scope": "shared",
    },
    "surfaces": {
        "title": "Surfaces · cartes · typographie",
        "components": ("AtlasPageTitle", "PageTitle", "PanelTitle", "MutedLabel", "card", "Panel", "QuestPanel", "QFrame"),
        "style_owner": "app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "metrics": {
        "title": "Tailles · typographie · espacements",
        "components": ("UNITY_SIZES_PX", "SIZES", "SPACING", "TYPOGRAPHY", "UNITY_RADII"),
        "style_owner": "app/ui/unity_palette.py + app/ui/theme.py",
        "scope": "shared",
    },
    "panels": {
        "title": "Panneaux · transparence · réduction",
        "components": ("AtlasPanelToggle", "GuideRightPanelToggle", "card", "QGroupBox"),
        "style_owner": "app/ui/components.py + app/ui/theme.py",
        "scope": "shared",
    },
    "startup": {
        "title": "Préchargement · même thème Unity",
        "components": ("PreloadPopupTitle", "PreloadPopupCurrent", "PreloadPopupProgress"),
        "style_owner": "app/ui/preload_popup.py + app/ui/theme.py",
        "scope": "shared",
    },
    "guides": {
        "title": "Guides · panneaux Unity partagés",
        "components": ("GuidePreparationSummary", "GuidePreparationRow", "GuideManualNav", "GuideUltimeGeneratedView", "QComboBox"),
        "style_owner": "app/ui/theme.py + app/modules/encyclopedia/",
        "scope": "module",
    },
    "assets": {
        "title": "Icônes · raccourcis · tooltips",
        "components": ("UNITY_ICON_NAMES", "UNITY_ICON_PENDING", "unity_original_preview_icon", "InlineShortcutButton", "QToolTip"),
        "style_owner": "app/ui/unity_palette.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "motion": {
        "title": "Motion Gallery · prototypes à comparer",
        "components": ("QPropertyAnimation", "QGraphicsOpacityEffect", "QProgressBar", "AtlasButton"),
        "style_owner": "app/pages/dev_ui_page.py",
        "scope": "prototype",
    },
    "coverage": {
        "title": "Couverture · modules consommateurs",
        "components": ("UNITY_UI_CONSUMERS", "UNITY_UI_FAMILY_INDEX"),
        "style_owner": "app/ui/unity_palette.py",
        "scope": "audit",
    },
    "dialogs": {
        "title": "Dialogues · icônes · typographie",
        "components": ("AtlasDialog", "AtlasDialogHeader", "AtlasPageTitle", "MutedLabel", "unity_original_preview_icon"),
        "style_owner": "app/ui/components.py + app/ui/theme.py",
        "scope": "shared",
    },
    "palette": {
        "title": "Palette Unity · source de vérité",
        "components": ("UNITY_PALETTE", "UNITY_MAIN_ROLES", "UNITY_UI_USAGE", "UNITY_COLOR_ALIAS_ROLES"),
        "style_owner": "app/ui/unity_palette.py + app/ui/theme.py",
        "scope": "shared",
    },
}

# Target modules for adoption/visual checks. Coverage is NOT certification.
UNITY_UI_CONSUMERS = ("Accueil", "Personnage", "Quêtes", "Succès", "Guides", "Bestiaire", "Outils", "Stuffs", "Organizer", "Almanax", "Réseau", "Launcher")

# Guide-compatible names still exist for old selectors and explicit
# per-role previews, but their normal colors now follow shared Unity
# surfaces. Do not maintain a second blue palette for this one module.
UNITY_COLOR_ALIAS_ROLES = {
    "GUIDE_PREPARATION_BORDER": "BORDER_CARD",
    "GUIDE_PREPARATION_TEXT": "TEXT",
    "GUIDE_ITEM_TEXT": "TEXT",
    "GUIDE_STATUS_TEXT": "TEXT_SOFT",
    "GUIDE_NAV_BORDER": "BORDER",
    "GUIDE_TOGGLE_TOP": "PANEL_ACTIVE",
    "GUIDE_TOGGLE_BOTTOM": "PANEL_2",
    "GUIDE_TOGGLE_BORDER": "BORDER_CARD",
    "GUIDE_TOGGLE_ACTIVE": "PANEL_ACTIVE",
    "GUIDE_TOGGLE_ACTIVE_BORDER": "GREEN_BORDER",
    "GUIDE_TOGGLE_HOVER": "PANEL_HOVER",
    "GUIDE_COMPACT_SURFACE": "PANEL",
    "GUIDE_SUMMARY_TOP": "PANEL_ACTIVE",
    "GUIDE_SUMMARY_BOTTOM": "PANEL",
    "GUIDE_PREPARATION_ROW": "PANEL_2",
    "GUIDE_PREPARATION_ROW_BORDER": "BORDER_CARD",
    "GUIDE_COPY_HOVER": "PANEL_HOVER",
    "GUIDE_MANUAL_NAV_SURFACE": "NAV_SURFACE",
}


def resolve_unity_colors(
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve semantic aliases after overrides; preserve explicit Guide overrides.

    With no override, a Guide uses exactly the same surface/hover/border
    colors as the rest of the application, even after a live theme update.
    """
    colors = dict(UNITY_PALETTE)
    if overrides:
        colors.update(overrides)
    for alias, role in UNITY_COLOR_ALIAS_ROLES.items():
        if not overrides or alias not in overrides:
            colors[alias] = colors[role]
    return colors


_LAUNCHER_ROLES = {
    "background": "BG",
    "panel": "PANEL",
    "border": "BORDER",
    "track": "PANEL_2",
    "text": "TEXT",
    "muted": "TEXT_MUTED",
    "accent": "GREEN",
    "accent_hover": "GREEN_HOVER",
}


def launcher_colors(palette: Mapping[str, str] | None = None) -> dict[str, str]:
    """Adapt the same Unity tokens for Tk without loading Qt or game files."""
    tokens = UNITY_PALETTE if palette is None else palette
    return {label: tokens[role] for label, role in _LAUNCHER_ROLES.items()}
