"""Canonical Qt-free Unity color tokens shared by the main UI and Tk launcher.

Keep all color literals here. Importing this module must never initialize Qt,
local artwork or any game runtime; the updater is an independent small EXE.
"""
from __future__ import annotations

from collections.abc import Mapping

from app.ui.entity_link_roles import ENTITY_LINK_COLOR_ROLES as GUIDE_ENTITY_LINK_ROLES


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
    # Existing map-canvas paint colors, centralized without changing artwork.
    "MAP_GRID": "#182536",
    "MAP_OUTLINE": "#223044",
    "MAP_SELECTION": "#F8C84E",
    "MAP_LINK": "#A98222",
    "MAP_LINK_BORDER": "#FFE082",
    "MAP_LABEL": "#F2F6FF",
    "SHELL_GRADIENT": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #192657, stop:1 #151821)",
    "PANEL_GRADIENT": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #24395F, stop:1 #192657)",
    "ACTIVE_GRADIENT": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6E9B41, stop:1 #497332)",
    # Semantic statuses already used throughout Atlas QSS. Their color
    # values live in the same Qt-free palette as the other Unity roles.
    "RED": "#D71920",
    "RED_HOVER": "#EF2028",
    "RED_DARK": "#9F1016",
    "YELLOW": "#D6B22D",
    "DANGER_PANEL": "#2A1118",
    "DANGER_TEXT": "#FFD6D9",
    "BADGE_BG": "#2A2B11",
    "BADGE_BORDER": "#7D8424",
    "BADGE_TEXT": "#C9D44C",
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
# Approved optical glass strength across Unity panels, controls and hairlines.
# 16% of the original translucent delta: preserves readability and darkStone palette.
UNITY_GLASS_INTENSITY = 0.16

# Single gentle relief shared by all static demo surfaces.
UNITY_PANEL_SHADOW = {"blur": 17, "vertical": 5, "alpha": 135}


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


# QPainter-drawn UI glyphs and splash text use semantic Unity roles too.
# This is a role index, NOT an independent palette with arbitrary colors.
UNITY_PAINTED_UI_ROLES = {
    "splash.status": "TEXT_SOFT",
    "organizer.grip": "TEXT_MUTED",
    "organizer.favorite": "YELLOW",
    "organizer.favorite_idle": "TEXT_MUTED",
    "organizer.warning_outline": "TEXT_SOFT",
    "organizer.warning_fill": "YELLOW",
    "organizer.warning_detail": "BG",
    "organizer.refresh": "TEXT_SOFT",
    "organizer.action": "TEXT_SOFT",
    "organizer.action_fill": "TEXT_SOFT",
    "organizer.shadow": "BG",
    # World Map placeholder and planet glyph use the same Unity chrome roles.
    "world_scan.placeholder": "PANEL",
    "world_scan.planet_outline": "TEXT",
    "world_scan.planet_fill": "GREEN_DARK",
}


def unity_painted_ui_color(
    name: str, overrides: Mapping[str, str] | None = None,
) -> str:
    """Resolve painter colors through the same canonical Unity token map."""
    return resolve_unity_colors(overrides)[UNITY_PAINTED_UI_ROLES[name]]


# Spacing, fonts and sizes have ONE Qt-free source for both the
# application QSS and the real QWidget layouts, with no layout redesign.
UNITY_SPACING_PX = {
    "xxs": 2, "xs": 4, "sm": 6, "md": 8,
    "lg": 10, "xl": 14, "2xl": 20, "3xl": 24,
}

# Rich text headings and Character score keep their existing pixel sizes.
# Only the token registry owns these typographic measurements.
UNITY_CONTENT_TYPOGRAPHY_PX = {
    "quest_h1": 22,
    "quest_h2": 15,
    "quest_h3": 13,
    "character_score_compact": 18,
    "character_score_regular": 23,
}

UNITY_TYPOGRAPHY = {
    # Approved local font families, with standard system fallbacks.
    "FONT_FAMILY": '"Lexend", "Segoe UI", Arial',
    "FONT_BODY": "12px",
    "FONT_SMALL": "11px",
    "FONT_TITLE": "18px",
    "FONT_SECTION": "14px",
    "FONT_BADGE": "10px",
    "FONT_CONTENT_H1": f'{UNITY_CONTENT_TYPOGRAPHY_PX["quest_h1"]}px',
    "FONT_CONTENT_H2": f'{UNITY_CONTENT_TYPOGRAPHY_PX["quest_h2"]}px',
    "FONT_CONTENT_H3": f'{UNITY_CONTENT_TYPOGRAPHY_PX["quest_h3"]}px',
    "FONT_CHARACTER_SCORE_COMPACT": f'{UNITY_CONTENT_TYPOGRAPHY_PX["character_score_compact"]}px',
    "FONT_CHARACTER_SCORE_REGULAR": f'{UNITY_CONTENT_TYPOGRAPHY_PX["character_score_regular"]}px',
}

UNITY_SIZES_PX = {
    "control_compact": 24,
    "control_normal": 32,
    "control_large": 40,
    "top_nav_height": 58,
    "top_nav_control_height": 32,
    "icon_small": 16,
    "icon_normal": 20,
    "icon_large": 24,
    "icon_xlarge": 32,
}

# Window geometry remains Qt-free so both the shell and Dev UI use exactly the
# same values. These are reference viewport sizes, not global widget scaling.
UNITY_WINDOW_PRESETS_PX = {
    "compact": (900, 600),
    "standard": (1180, 720),
    "large": (1440, 900),
    "full_hd": (1920, 1080),
}

# Layout metrics specify reusable relationships, not compulsory fixed panel
# widths. Specific content (maps, equipment grids) can require exceptions.
UNITY_LAYOUT_SIZES_PX = {
    "page_margin": 16,
    "module_padding": 12,
    "module_gap": 10,
    "splitter_handle": 6,
    "dialog_padding_x": 24,
    "dialog_padding_y": 22,
    "dialog_gap": 16,
    # Shared compact density keeps existing Craft windows readable.
    "dialog_compact_padding_x": 14,
    "dialog_compact_padding_y": 12,
    "dialog_compact_gap": 8,
    "dialog_header_gap": 14,
    "dialog_header_text_gap": 5,
    "breadcrumb_item_gap": 5,
    "breadcrumb_compact_inset": 3,
    "breadcrumb_normal_inset": 5,
    "gallery_section_header_inset": 22,
    # The exact same Guide header geometry is used by the live viewer and Dev UI.
    "guide_header_margin_x": 10,
    "guide_header_margin_top": 6,
    "guide_header_margin_bottom": 7,
    "guide_header_outer_spacing": 10,
    "guide_header_content_spacing": 6,
    "guide_metric_column_spacing": 12,
    "guide_metric_row_spacing": 2,
    "guide_metric_caption_spacing": 4,
}

UNITY_CONTROL_SIZES_PX = {
    "dropdown_row": 24,
    "checkbox_indicator": 18,
    "guide_tree_state_width": 18,  # One marker column for every Guide state.
    "progress_primary": 11,
    "progress_secondary": 7,
    "progress_home_compact": 5,
    "progress_route": 6,
    "progress_generated_route": 8,
    "progress_toggle_width": 18,
    "progress_toggle_height": 18,
    "progress_toggle_icon": 14,
    "guide_character_button": 24,
    "guide_character_icon": 20,
    # Guide portrait rings and sheet selector are shared with Dev UI previews.
    "guide_portrait_button": 42,
    "guide_portrait_icon": 32,
    "guide_portrait_stroke": 3,
    "guide_portrait_inset": 2,
    "guide_donut_box": 66,
    "guide_donut_inset": 7,
    "guide_donut_stroke": 6,
    "guide_symbol_icon": 18,
    "guide_quest_shortcut_icon": 18,
    "guide_quest_shortcut_box": 30,
    "guide_page_jump_compact_max_width": 90,
    "guide_page_jump_normal_max_width": 110,
    "dialog_min_width": 400,
    "dialog_header_icon_box": 52,
    "dialog_header_icon_artwork": 44,
    "gallery_selector_min_width": 240,
    "gallery_selector_max_width": 420,
    "gallery_sidebar_min_width": 192,
    "gallery_sidebar_max_width": 240,
    "guide_quantity_width": 58,  # Minimum; real x / x counters fit their content.
    "guide_quantity_chrome_width": 26,  # Compact arrows/padding; content still grows.
    "guide_preparation_icon": 16,
    "guide_preparation_min_height": 48,
    "guide_validation_width": 22,
}

# Counts are not pixel sizes and must remain distinct from geometry tokens.
UNITY_CONTROL_LIMITS = {
    "dropdown_visible_rows": 8,
}

# Shared Guide-reading metrics from the canonical #363 reader.
# The Qt-free index keeps source images, copied quantities and nested drawers
# adjustable in Dev UI without introducing another Guide theme.
UNITY_GUIDE_READING_METRICS_PX = {
    "sheet_horizontal": UNITY_SPACING_PX["lg"],
    "sheet_vertical": UNITY_SPACING_PX["md"],
    "sheet_spacing": UNITY_SPACING_PX["sm"],
    "section_horizontal": UNITY_SPACING_PX["md"],
    "section_vertical": UNITY_SPACING_PX["sm"],
    "section_spacing": UNITY_SPACING_PX["xs"],
    "row_spacing": UNITY_SPACING_PX["xs"],
    "reading_gap": UNITY_SPACING_PX["sm"],
    "source_image_max_width": 240,
    "source_image_max_height": 160,
    # One shared Quests/Guides image viewer, with two indexed preview roles.
    "quest_image_max_width": 520,
    "quest_image_max_height": 320,
    "image_preview_min_loading_height": 120,
    "image_preview_parent_inset": 24,
    "image_preview_outer_width": 20,
    "image_preview_frame_width": 12,
    "image_preview_frame_height": 6,
    "image_load_delay_ms": 250,
    "source_quantity_width": 90,
    "source_drawer_max_height": 340,
    "source_drawer_min_height": 280,
    "source_drawer_compact_min_height": 156,
    "normal_drawer_max_height": 210,
    "normal_drawer_min_height": 126,
    "zoom_dialog_width": 1180,
    "zoom_dialog_height": 860,
    "zoom_screen_percent": 82,
    "zoom_min_width": 320,
    "zoom_min_height": 240,
    "zoom_content_inset": 24,
    "zoom_margin": UNITY_SPACING_PX["sm"],
}

# The four reference sizes are calibration points, NOT forced window sizes.
# Layout geometry interpolates smoothly between them. Do not resize text,
# icons, checkboxes, buttons or menu rows proportionally with the window.
# These remain semantic control roles, regardless of the viewport.
UNITY_LAYOUT_PROFILE_PX = {
    "compact": {"page_margin": 12, "module_padding": 10, "module_gap": 8},
    "standard": {
        "page_margin": UNITY_LAYOUT_SIZES_PX["page_margin"],
        "module_padding": UNITY_LAYOUT_SIZES_PX["module_padding"],
        "module_gap": UNITY_LAYOUT_SIZES_PX["module_gap"],
    },
    "large": {"page_margin": 18, "module_padding": 14, "module_gap": 12},
    "full_hd": {"page_margin": 20, "module_padding": 16, "module_gap": 14},
}


def unity_layout_metrics(window_width: int) -> dict[str, int]:
    """Interpolate spacing at any width, without changing panel placement.

    Widths below compact or beyond Full HD use the nearest reference, rather
    than extrapolating huge margins. Qt-free for all widgets and the Launcher.
    """
    sizes = list(UNITY_WINDOW_PRESETS_PX)
    left_key = sizes[0]
    if window_width <= UNITY_WINDOW_PRESETS_PX[left_key][0]:
        return dict(UNITY_LAYOUT_PROFILE_PX[left_key])
    for right_key in sizes[1:]:
        left_width = UNITY_WINDOW_PRESETS_PX[left_key][0]
        right_width = UNITY_WINDOW_PRESETS_PX[right_key][0]
        if window_width <= right_width:
            portion = (window_width - left_width) / (right_width - left_width)
            left_metrics = UNITY_LAYOUT_PROFILE_PX[left_key]
            right_metrics = UNITY_LAYOUT_PROFILE_PX[right_key]
            return {
                key: round(left_metrics[key] + portion * (right_metrics[key] - left_metrics[key]))
                for key in left_metrics
            }
        left_key = right_key
    return dict(UNITY_LAYOUT_PROFILE_PX[sizes[-1]])


# Optional, *only* for collections of independent cards. Never use these
# breakpoints to reorder a page's structural modules, controls or submenus.
UNITY_LAYOUT_BREAKPOINTS_PX = {
    "two_columns_min": 560,
    "three_columns_min": 1000,
    # Only abbreviates Guide captions/selector; never reorders modules.
    "guide_header_compact_below": 520,
}


def unity_responsive_columns(usable_width: int) -> int:
    """Shared width-only decision, safe to use without a QApplication."""
    if usable_width >= UNITY_LAYOUT_BREAKPOINTS_PX["three_columns_min"]:
        return 3
    if usable_width >= UNITY_LAYOUT_BREAKPOINTS_PX["two_columns_min"]:
        return 2
    return 1


_ORGANIZER_MODE_BUTTON_WIDTH = 170
_ORGANIZER_PANEL_GUTTER = 8

UNITY_ORGANIZER_METRICS_PX = {
    # Preserved module-specific geometry, now visible in the global UI index.
    "card_padding": 12,
    "card_spacing": 10,
    "button_height": 30,
    "input_height": UNITY_SIZES_PX["control_normal"],
    "key_badge_height": 22,
    "key_badge_min_width": 34,
    "favorite_chip_height": 28,
    "character_slot_height": 36,
    "stop_button_height": 34,
    "mode_switch_width": 2 * _ORGANIZER_MODE_BUTTON_WIDTH + _ORGANIZER_PANEL_GUTTER,
    "mode_button_width": _ORGANIZER_MODE_BUTTON_WIDTH,
    "zaap_panel_min_width": 220,
    "refresh_button_width": 32,
    "speed_caption_width": 52,
    "speed_legacy_width": 78,
    "root_margin_left": 14,
    "root_margin_top": 12,
    "root_margin_right": 14,
    "root_margin_bottom": 20,
    "panel_gutter": _ORGANIZER_PANEL_GUTTER,
    # Existing visual constraints in Organizer UI; no Macro/Zaap behavior.
    "control_panel_height": 146,
    "key_badge_width": 52,
    "speed_row_gap": 4,
    "root_spacing": 12,
    "slot_name_height": UNITY_SIZES_PX["control_compact"],
    "slot_indicator_width": UNITY_SIZES_PX["icon_small"],
    "slot_horizontal_spacing": 8,
    "slot_vertical_spacing": 6,
}

# Module-specific content sizes and geometry actually present in Atlas source.
# These must NOT replace common control metrics or move structural panels.
# A module only inherits future changes after being explicitly connected.
UNITY_MODULE_GEOMETRY_PX = {
    "shell": {
        "brand_min_width": 170, "brand_icon_box": 32,
        "character_selector_min_width": 150, "character_selector_max_width": 210,
        "settings_button_box": 34, "settings_icon": 20, "nav_icon": 18,
        "subnav_margins": (10, 4, 10, 4), "subnav_spacing": 4,
        "top_nav_margins": (10, 6, 10, 6), "top_nav_spacing": 4,
        "brand_padding_x": 8, "brand_spacing": 8, "brand_artwork": 30,
        "nav_content_gap": 8,
    },
    "home": {
        "page_margin": 26, "column_gutter": 18,
        "left_column_min_width": 286, "left_column_max_width": 350,
        "guide_min_width": 300,
        "right_column_min_width": 205, "right_column_max_width": 330,
        "portrait_box": 98, "portrait_artwork": 88,
        "almanax_box": 150, "almanax_artwork": 126,
        "banner_min_height": 145, "banner_max_height": 205,
        "network_card_min_height": 64, "network_card_max_height": 72,
        "card_padding": 20, "card_gutter": 10,
        "left_column_spacing": 16, "right_column_spacing": 12,
        "tracking_spacing": 7, "tracking_icon_width": 20,
        "tracking_name_min_width": 92, "tracking_bar_min_width": 62,
        "tracking_value_min_width": 46,
        "identity_margins": (0, 4, 0, 2), "identity_spacing": 14,
        "identity_text_spacing": 8,
        "guide_progress_margins": (0, 7, 0, 0), "guide_progress_spacing": 8,
        "network_card_margins": (15, 10, 15, 10),
        "network_card_spacing": 10, "network_text_spacing": 1,
        "detail_row_margins": (5, 9, 5, 9),
        "detail_row_spacing": 10, "detail_row_icon_width": 28,
    },
    "character": {
        "page_margins": (10, 8, 10, 10),
        "equipment_min_width": 610, "stats_min_width": 235,
        "stats_max_width": 340, "selector_min_width": 260,
        "selector_max_width": 360, "selector_icon": 38,
        "equipment_slot_box": 64, "equipment_icon": 54,
        "equipment_panel_margins": (8, 6, 8, 8),
        "stats_panel_margins": (10, 8, 10, 10),
        "portrait_min_size": (230, 300), "portrait_max_size": (300, 360),
    },
    # Existing compatibility character view, distinct from the active page.
    "character_compat": {
        "page_margins": (20, 18, 20, 20), "page_spacing": 12,
        "columns_spacing": 14, "identity_min_width": 270,
        "identity_max_width": 340, "stats_min_width": 250,
        "equipment_min_width": 460, "panel_padding": 16,
        "panel_spacing": 10, "selector_icon": 36,
        "order_icon": 30, "order_min_height": 132,
        "order_max_height": 190, "equipment_grid_margins": (6, 8, 6, 6),
        "equipment_slot_box": 62, "equipment_icon": 52,
        "portrait_min_size": (214, 292), "portrait_max_size": (274, 332),
    },
    "achievements": {
        "category_min_width": 235, "category_max_width": 300,
        "success_list_min_width": 285, "detail_min_width": 240,
        "initial_splitter_sizes": (245, 315, 640),
        "detail_padding": 12, "detail_gap": 10,
    },
    "craft": {
        "quantity_width": 86, "search_max_width": 360,
        "resource_dialog_size": (500, 540), "item_set_dialog_size": (390, 460),
        "leveling_dialog_size": (660, 560), "route_dialog_size": (560, 420),
        "resource_icon_box": 28, "leveling_icon_box": 30,
        "resource_tile_box": (56, 42), "resource_tile_artwork": 16,
        "leveling_level_badge_width": 88,
        "leveling_copy_action_width": 64,
        "leveling_add_action_width": 38,
        "leveling_action_height": 28,
        # Craft route captures keep their independent wheel/step interactions,
        # while decoding uses the Encyclopedia's existing image service.
        "route_image_min_height": 230,
        "route_preview_min_width": 180,
        "route_preview_min_height": 160,
        "route_zoom_min_percent": 45,
        "route_zoom_max_percent": 300,
        "route_zoom_step_percent": 15,
    },
    "guide_catalog": {"category_tree_max_height": 250},
    "guide_cards": {
        "featured_min_width": 245, "featured_max_width": 275,
        "featured_min_height": 172, "featured_image_height": 86,
        "featured_image_min_width": 210,
        "small_min_width": 126, "small_max_width": 150,
        "small_min_height": 138,
        "dofus_card_min_width": 86, "dofus_card_max_width": 126,
        "dofus_card_height": 118, "dofus_grid_gap": 8,
        "dofus_grid_max_columns": 5,
        "home_left_min_width": 285, "home_left_max_width": 360,
        "guide_steps_open_width": 190,
        # Existing compact Guide catalogue cards and responsive columns.
        "featured_compact_margins": (9, 6, 9, 6),
        "featured_compact_spacing": 3,
        "featured_compact_min_height": 64,
        "featured_compact_max_height": 85,
        "featured_compact_artwork_box": 28,
        "featured_compact_progress_max_height": 5,
        "featured_pair_margins": (3, 3, 5, 7),
        "featured_pair_spacing": 7,
        "featured_pair_horizontal_min_width": 580,
        "library_columns_spacing": 14,
        "library_left_max_width": 295,
        "library_left_stacked_max_height": 220,
        "library_columns_horizontal_min_width": 730,
    },
    "guide_reading_header": {
        "participant_margins": (7, 5, 7, 5), "participant_gap": 5,
        "sheet_margins": (10, 7, 10, 7), "sheet_gap": 6,
        "sheet_row_gap": 7, "sheet_title_gap": 1,
        "back_icon": 14, "back_max_width": 35,
        "footer_margins": (8, 4, 8, 6), "footer_gap": 8,
        "preparation_detail_margins": (8, 2, 8, 3),
        "overview_cover_box": 44, "overview_cover_artwork": 38,
    },
    "guide_route": {
        "selector_min_width": 170, "route_icon_box": 34,
        "route_icon_artwork": 21, "detail_max_height": 136,
    },
    "world_scan": {
        "page_margins": (12, 10, 12, 10), "page_gutter": 8,
        "world_icon_box": 60, "world_icon_artwork": 34,
        "summary_height": 74, "menu_button_min_width": 108,
        "toolbar_button_height": 30, "world_menu_item_height": 28,
        "header_spacing": 10, "header_accent_size": (4, 24),
        "header_title_height": 28,
        "toolbar_margins": (10, 8, 10, 8), "toolbar_spacing": 8,
        "breadcrumb_height": 24,
        "menu_margins": (6, 6, 6, 6),
        "menu_item_margins": (2, 2, 2, 2), "menu_item_spacing": 4,
        "detail_margins": (12, 7, 12, 7), "detail_spacing": 4,
        "status_height": 18, "menu_divider_height": 1,
    },
    "world_map": {"canvas_min_size": (420, 320)},
    "unavailable_page": {"margins": (24, 24, 24, 24), "spacing": 10},
    "encyclopedia_warmup": {"margins": (18, 18, 18, 18), "spacing": 12, "progress_max_width": 360},
    # Existing Quêtes hierarchy and search dimensions, not forced across modules.
    "quests": {
        "hierarchy_open_width": 300, "hierarchy_collapsed_width": 44,
        "search_min_height": 34, "quest_list_max_height": 220,
        "collapse_button_box": UNITY_SIZES_PX["icon_large"],
        "detail_initial_width": 900, "deferred_detail_padding": 18,
        "category_button_max_width": 180, "series_button_max_width": 280,
        "item_quantity_width": 88,
    },
    # Existing Succès filter panel: preserve its distinct card/selector spacing.
    "achievement_filters": {
        "page_margins": (8, 8, 8, 8), "page_spacing": 7,
        "category_spacing": 5, "card_margins": (7, 6, 7, 6),
        "card_spacing": 4,
    },
    # Existing Quêtes / Guides detail splitter and panel geometry.
    "quest_detail": {
        "root_spacing": 6, "header_margins": (8, 8, 10, 8),
        "header_spacing": 10, "title_spacing": 2,
        "saved_right_width": 300, "center_min_width": 340,
        "prerequisite_row_spacing": 7, "prerequisite_marker_width": UNITY_CONTROL_SIZES_PX["guide_tree_state_width"],
        "right_min_width": 240, "right_max_width": 380,
        "initial_splitter_sizes": (680, 300),
        "panel_padding": 8, "panel_spacing": 6, "content_spacing": 6,
    },
    # Existing Tk geometry, separate from the Qt four-size window calibration.
    "launcher": {
        "normal_window_size": (470, 252), "install_window_size": (520, 425),
        "install_path_wrap_length": 515, "status_wrap_length": 420,
        "progress_width": 408, "header_top_padding": 24,
        "logo_bottom_padding": 11, "progress_thickness": 12,
        "button_padding_x": 16, "button_padding_y": 8,
    },
    # Existing lightweight equipment entry (no embedded browser).
    "equipment": {"page_margins": (18, 16, 18, 18), "page_spacing": 12},
    # Existing startup modal dimensions; do not force global dialog sizes.
    "preload_popup": {
        "dialog_width": 470, "page_margins": (32, 24, 32, 28),
        "page_spacing": 14, "logo_box": 64,
    },
}

# Each visible Dev UI entry links to the code owning the real constraint.
UNITY_MODULE_GEOMETRY_OWNERS = {
    "shell": "main.py",
    "home": "app/pages/home_page.py",
    "character": "app/pages/character_page.py",
    "character_compat": "app/pages/_character_page_impl.py",
    "achievements": "app/modules/encyclopedia/views/achievements_view.py",
    "craft": "app/pages/craft_page.py",
    "guide_catalog": "app/modules/encyclopedia/views/guide_catalog_view.py",
    "guide_cards": "app/modules/encyclopedia/views/guides_view.py",
    "guide_reading_header": "app/ui/components.py",
    "guide_route": "app/modules/encyclopedia/views/guide_continuous_route_panel.py",
    "world_scan": "app/ui/world_scan_panel.py",
    "world_map": "app/ui/map_canvas_widget.py",
    "unavailable_page": "app/ui/components.py",
    "encyclopedia_warmup": "app/modules/encyclopedia/views/encyclopedia_bootstrap_views.py",
    "quests": "app/pages/_quests_page_impl.py",
    "achievement_filters": "app/modules/encyclopedia/widgets/filter_panel.py",
    "quest_detail": "app/modules/encyclopedia/widgets/quest_detail_view.py",
    "launcher": "app/distribution/launcher.py",
    "equipment": "app/pages/equipment_page.py",
    "preload_popup": "app/ui/preload_popup.py",
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

# The global UI-unification checklist, linked to live Dev UI families.
# Every planned visual concern has a reachable preview; this list makes no
# claim that all indexed screens have been migrated or certified.
UNITY_UI_UNIFICATION_CONTRACT = (
    ("Boutons et variantes", "buttons"),
    ("Textes cliquables et actions popup", "buttons"),
    ("Boutons favoris Zaap : rôle existant AtlasButton", "buttons"),
    ("Onglets et sélection", "navigation"),
    ("Navigation latérale, menu et sélection", "sidebar"),
    ("Menus contextuels", "navigation"),
    ("Sous-menus et actions cochables", "navigation"),
    ("Pagination, précédent, suivant et retour", "navigation"),
    ("Fil d'Ariane et hiérarchie", "breadcrumbs"),
    ("Fil d'Ariane compact et niveau courant", "breadcrumbs"),
    ("En-têtes de page, module, guide et dialogue", "headers"),
    ("Listes, tableaux, arborescences", "data_views"),
    ("Défilement et scrollbars", "scroll_resize"),
    ("Resize et séparateurs de panneaux", "scroll_resize"),
    ("Grilles, colonnes et alignements", "layouts"),
    ("Saisie, focus et placeholders", "fields"),
    ("Menus déroulants et sélections", "fields"),
    ("Cases, radios et commutateurs", "fields"),
    ("Formats numériques, date et heure", "advanced_fields"),
    ("Sélecteurs compacts : valeurs négatives, préfixes et x/x", "fields"),
    ("États normal, survol, actif et désactivé", "statuses"),
    ("États pressé, focus, chargement et sélection", "statuses"),
    ("Badges passifs et actions de statut", "statuses"),
    ("Chargement, progression et succès", "statuses"),
    ("Notifications et messages d'alerte", "notifications"),
    ("Titres, textes et légendes", "surfaces"),
    ("Cartes, ombres et bordures", "surfaces"),
    ("Accents de titre et séparateurs", "surfaces"),
    ("Tailles, marges et espacements", "metrics"),
    ("Typographies, rayons et dimensions", "metrics"),
    ("Panneaux ouverts et repliés", "panels"),
    ("Overlays radial et sélection Organizer", "panels"),
    ("Effets glass et transparence", "panels"),
    ("Fond Unity, sprite et dégradé", "backdrop"),
    ("Préchargement et transitions de lancement", "startup"),
    ("Splash transparent et progression du préchargement", "startup"),
    ("Guides et panneaux spécialisés", "guides"),
    ("Lecteur universel, préparation et validation des fiches Guides", "guides"),
    ("Icônes Unity d'origine et transparence", "assets"),
    ("Raccourcis clavier et infobulles", "assets"),
    ("Animations et transitions candidates", "motion"),
    ("Écrans et adaptateurs consommateurs", "coverage"),
    ("Popups réels, sous-vues et overlays : propriétaires et exceptions", "coverage"),
    ("Dialogues et fenêtres popup", "dialogs"),
    ("Dialogues information, attention, erreur", "dialogs"),
    ("Même AtlasDialog : information, erreur, confirmation et contenu métier", "dialogs"),
    ("En-tête, boutons de validation et fermeture du dialogue commun", "dialogs"),
    ("Contenu variable, dimensionnement naturel et limites partagées", "dialogs"),
    ("Fermeture, Craft, Leveling, équipement et route", "dialogs"),
    ("Zoom d’image et suggestions Zaap", "dialogs"),
    ("Menus et suggestions légers : widgets Qt existants, sans AtlasDialog", "navigation"),
    ("Zoom, radial, splash : UI spécialisée et styles Unity communs", "coverage"),
    ("Palette et dégradés sémantiques", "palette"),
)

# Index of the EXISTING Dev UI showcase, not a second theme or widget library.
# Every visual family references the current Qt/theme owner and real samples.
# "module" and "prototype" deliberately do not claim global adoption.
# Colors, fonts, sizes and QSS stay in their existing canonical mappings.
UNITY_UI_FAMILY_INDEX = {
    "buttons": {
        "title": "Boutons · variantes et états",
        "components": ("AtlasButton", "PrimaryActionButton", "SecondaryButton", "ActiveButton", "DangerButton", "TopNavButton", "TopNavButtonActive",
                       "InlineActionButton", "PopupLinkButton", "favoriteChipName"),
        "style_owner": "app/ui/components.py + app/ui/theme.py",
        "scope": "shared",
    },
    "navigation": {
        "title": "Onglets · menus et navigation",
        "components": (
            "QTabWidget", "QTabBar", "QMenu", "AtlasButton",
            "AtlasPageNavigator", "AtlasPageCounter",
            "WorldMenu", "WorldMenuItem", "WorldMenuItemActive",
        ),
        "style_owner": "app/ui/components.py + app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "breadcrumbs": {
        "title": "Fil d'Ariane · niveaux et navigation",
        "components": ("AtlasBreadcrumb", "GuideBreadcrumb", "GuideBreadcrumbButton", "GuideBreadcrumbSeparator", "GuideBreadcrumbCurrent",
                       "GuideBreadcrumbCurrentStrong"),
        "style_owner": "app/ui/theme.py + app/ui/components.py",
        "scope": "shared",
    },
    "headers": {
        "title": "En-têtes · page, module, guide et dialogue",
        "components": (
            "AtlasPageTitle", "PageTitle", "PanelTitle", "GuideHeader",
            "GuideHeaderTitle", "GuideHeaderMeta", "GuideCompactHeader",
            "GuideHeaderSectionHost", "GuideHeaderSectionScroll", "GuideHeaderProgressGroup",
            "GuideCompactTitle", "GuideCompactPageJump",
            "GuideManualProgress", "GuideCompactPreparationProgress", "GuideCompactSummaryProgress", "GuideSummaryList",
            "GuideCompactDonutHeading", "GuideCompactDonutCount",
            "GuideSheetHeader", "AtlasGuideReadingHeader", "AtlasGuideSheetHeader",
            "GuideSheetMeta", "GuideSheetTitle", "AtlasDialogHeader",
            "GuideCompactDonut", "AtlasGuideProgressDonut", "AtlasGuideParticipantPortrait",
            "GuideCompactTitleIcon",
            "GuideCompactOverlayButton", "GuideCompactSettingsButton",
            "GuideParticipantsButton", "GuidePreparationToggle",
            "GuideGlobalDetailsPanel", "GuidePreparationModeTab",
            "GuideManualGuideButton",
        ),
        "style_owner": "app/ui/components.py + app/ui/theme.py + app/modules/encyclopedia/views/shared_manual_guide_view.py",
        "scope": "shared",
    },
    "sidebar": {
        "title": "Navigation latérale · menu et sélection",
        "components": ("sidebar", "MenuButton", "navItem", "navItemActive", "NavSeparator"),
        "style_owner": "app/ui/theme.py + app/ui/components.py",
        "scope": "shared",
    },
    "data_views": {
        "title": "Listes · arborescences · tableaux",
        "components": (
            "QTreeWidget", "QTableWidget", "QHeaderView", "QListWidget",
            "MapViewTree", "QuestHierarchyTree",
            "AchievementsView", "GuideLeftPanel",
            "GuideCenterPanel", "AchievementDetailStack",
        ),
        "style_owner": "app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "scroll_resize": {
        "title": "Défilement · listes · redimensionnement",
        "components": ("QSplitter", "QScrollArea", "QScrollBar", "QListWidget", "Panel"),
        "style_owner": "app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "layouts": {
        "title": "Grilles · colonnes · alignements",
        "components": ("QGridLayout", "QHBoxLayout", "QVBoxLayout", "card", "Panel"),
        "style_owner": "app/ui/unity_palette.py + app/ui/theme.py",
        "scope": "shared",
    },
    "fields": {
        "title": "Saisie · sélection · progression",
        "components": ("QLineEdit", "AtlasComboBox", "QComboBox", "QSpinBox", "QPlainTextEdit", "QCheckBox", "QRadioButton", "QProgressBar", "QSlider"),
        "style_owner": "app/ui/components.py + app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "advanced_fields": {
        "title": "Formulaires avancés · états et formats",
        "components": (
            "QLineEdit", "QDoubleSpinBox", "QDateEdit", "QTimeEdit",
            "QCheckBox", "QCalendarWidget", "AlmanaxCalendar",
        ),
        "style_owner": "app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "statuses": {
        "title": "États · badges · retours visuels",
        "components": ("AtlasStatusBadge", "StatusBadge", "StatusChip", "GuideSummaryButton", "QProgressBar"),
        "style_owner": "app/ui/components.py + app/ui/theme.py",
        "scope": "shared",
    },
    "notifications": {
        "title": "Notifications · messages et alertes",
        "components": ("AtlasStatusBadge", "StatusBadge", "QLabel", "card"),
        "style_owner": "app/ui/components.py + app/ui/theme.py",
        "scope": "prototype",
    },
    "surfaces": {
        "title": "Surfaces · cartes · typographie",
        "components": (
            "AtlasPageTitle", "PageTitle", "PanelTitle", "MutedLabel",
            "card", "Panel", "QuestPanel", "QFrame",
            "AtlasUnavailablePage", "PlaceholderPage", "EncyclopediaUnavailableBestiary",
            "MapToolbar", "WorldDetailPanel", "WorldDetailValue", "MapDetailValue",
        ),
        "style_owner": "app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "shared",
    },
    "metrics": {
        "title": "Dimensions · responsive · typographie · espacements",
        "components": (
            "UNITY_SIZES_PX", "UNITY_WINDOW_PRESETS_PX", "UNITY_LAYOUT_SIZES_PX",
            "UNITY_LAYOUT_PROFILE_PX", "unity_layout_metrics",
            "UNITY_CONTROL_SIZES_PX", "UNITY_CONTROL_LIMITS",
            "UNITY_MODULE_GEOMETRY_PX", "UNITY_MODULE_GEOMETRY_OWNERS",
            "UNITY_LAYOUT_BREAKPOINTS_PX",
            "unity_responsive_columns", "UNITY_ORGANIZER_METRICS_PX",
            "UNITY_CONTENT_TYPOGRAPHY_PX", "UNITY_GUIDE_READING_METRICS_PX",
            "UNITY_SPACING_PX", "UNITY_TYPOGRAPHY",
            "SIZES", "SPACING", "TYPOGRAPHY", "UNITY_RADII",
        ),
        "style_owner": "app/ui/unity_palette.py + app/ui/theme.py",
        "scope": "shared",
    },
    "panels": {
        "title": "Panneaux · transparence · réduction",
        "components": ("AtlasPanelToggle", "GuideRightPanelToggle", "card", "QGroupBox"),
        "style_owner": "app/ui/components.py + app/ui/theme.py",
        "scope": "shared",
    },
    "backdrop": {
        "title": "Fond Unity · texture et dégradé",
        "components": ("UnityBackdrop", "AtlasUnityBackdrop", "card"),
        "style_owner": "app/ui/unity_skin.py + app/ui/theme.py",
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
        "components": (
            "GuideHeader", "GuidesHomeCategory", "GuideDofusCard",
            "GuideQuestLineActive", "GuideCompactHeader",
            "GuidePreparationSummary", "GuidePreparationRow", "AtlasGuidePreparationRow",
            "AtlasGuidePreparationPanel", "AtlasGuidePreparationSummary",
            "AtlasGuideReadingNav", "AtlasGuideValidationButton",
            "GuideManualNav", "GuideUltimeGeneratedView", "SharedGuideManualView",
            "QuestLaunchPosition", "QComboBox",
        ),
        "style_owner": "app/ui/theme.py + app/ui/unity_skin.py",
        "scope": "module",
    },
    "assets": {
        "title": "Icônes · raccourcis · tooltips",
        "components": ("UNITY_ICON_NAMES", "UNITY_ICON_PENDING", "unity_original_preview_icon", "atlas_guide_symbol_icon", "atlas_quest_shortcut_icon", "InlineShortcutButton", "QToolTip"),
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
        "components": ("AtlasDialog", "AtlasDialogHeader", "AtlasImagePopup", "present_transient_dialog", "exec_transient_dialog", "AtlasPageTitle", "MutedLabel", "unity_original_preview_icon"),
        "style_owner": "app/ui/components.py + app/ui/theme.py",
        "scope": "shared",
    },
    "palette": {
        "title": "Palette Unity · source de vérité",
        "components": (
            "UNITY_PALETTE", "UNITY_MAIN_ROLES", "UNITY_UI_USAGE",
            "UNITY_COLOR_ALIAS_ROLES", "ENTITY_LINK_COLOR_ROLES",
            "entity_link_markup",
        ),
        "style_owner": "app/ui/unity_palette.py + app/ui/theme.py",
        "scope": "shared",
    },
}

# Target modules for adoption/visual checks. Coverage is NOT certification.
UNITY_UI_CONSUMERS = (
    "Accueil", "Personnage", "Quêtes", "Succès", "Guides", "Bestiaire",
    "Outils", "Stuffs", "Organizer", "Almanax", "Réseau", "Launcher",
    # These are real Atlas surfaces, not additional theme implementations.
    "Craft", "Carte du monde", "Paramètres", "Dev UI",
    "Popups et dialogues", "Overlays et démarrage",
)

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
    "button_bg": "PANEL_2",
    "button_hover": "PANEL_HOVER",
    "button_fg": "TEXT_SOFT",
    "button_hover_fg": "GREEN",
    "button_border": "BORDER_SOFT",
    "button_focus": "GREEN_BORDER",
    "disabled_text": "TEXT_DISABLED",
}


def launcher_colors(palette: Mapping[str, str] | None = None) -> dict[str, str]:
    """Adapt the same Unity tokens for Tk without loading Qt or game files."""
    tokens = UNITY_PALETTE if palette is None else palette
    return {label: tokens[role] for label, role in _LAUNCHER_ROLES.items()}
