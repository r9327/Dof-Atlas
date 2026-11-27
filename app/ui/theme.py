from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache

from app.ui.unity_palette import (
    UNITY_COLOR_ALIAS_ROLES, UNITY_GLASS_INTENSITY, UNITY_RADII, UNITY_SIZES_PX,
    UNITY_SPACING_PX, UNITY_TYPOGRAPHY,
    UNITY_GUIDE_READING_METRICS_PX,
    resolve_unity_colors, unity_glass_gradient,
)
from app.ui.organizer_style import ORGANIZER_STYLE_TEMPLATE
from app.ui.entity_link_roles import entity_link_colors
from app.ui.unity_skin import unity_skin_stylesheet


# Palette, typography and spacing are all indexed in the Qt-free Unity
# contract. QSS, dialog previews and Launcher reuse these exact same tokens.
PALETTE = resolve_unity_colors()
GUIDE_ENTITY_LINK_COLORS = entity_link_colors(PALETTE)
ENTITY_LINK_COLORS = GUIDE_ENTITY_LINK_COLORS
TYPOGRAPHY = dict(UNITY_TYPOGRAPHY)
SPACING = {
    f"SPACE_{name.upper()}": f"{px}px"
    for name, px in UNITY_SPACING_PX.items()
}

# Public compatibility API used by the #363 canonical reading surface.
# Every number is owned by the Qt-free Dev UI index, not a local Guide sheet.
GUIDE_READING_METRICS = UNITY_GUIDE_READING_METRICS_PX

SIZES = {
    **UNITY_RADII,
    "CONTROL_HEIGHT_COMPACT": f'{UNITY_SIZES_PX["control_compact"]}px',
    "CONTROL_HEIGHT_COMPACT_CONTENT": f'{UNITY_SIZES_PX["control_compact"] - 2}px',
    "CONTROL_HEIGHT": f'{UNITY_SIZES_PX["control_normal"]}px',
    "CONTROL_HEIGHT_LARGE": f'{UNITY_SIZES_PX["control_large"]}px',
    "ICON_SIZE_SMALL": f'{UNITY_SIZES_PX["icon_small"]}px',
    "ICON_SIZE_NORMAL": f'{UNITY_SIZES_PX["icon_normal"]}px',
    "ICON_SIZE_LARGE": f'{UNITY_SIZES_PX["icon_large"]}px',
    "ICON_SIZE_XLARGE": f'{UNITY_SIZES_PX["icon_xlarge"]}px',
    "TOP_NAV_HEIGHT": f'{UNITY_SIZES_PX["top_nav_height"]}px',
    "TOP_NAV_CONTROL_HEIGHT": f'{UNITY_SIZES_PX["top_nav_control_height"]}px',
}

THEME_TOKENS = {**PALETTE, **TYPOGRAPHY, **SPACING, **SIZES}

# Transitional aliases let existing module selectors preserve their layout
# while their rendered colors already follow the home-page palette. New QSS
# should use semantic @TOKENS directly; aliases can then shrink over time.
LEGACY_COLOR_ROLES = {
    "#5D512D": "BORDER_STRONG",
    "#1C1A12": "PANEL_2",
    "#101E2F": "PANEL_HOVER",
    "#D7E0EE": "TEXT_SOFT",
    "#16263A": "PANEL_HOVER",
    "#334761": "BORDER_STRONG",
    "#F0444B": "RED_HOVER",
    "#FF6167": "RED_HOVER",
    "#09121F": "PANEL_2",
    "#122139": "PANEL_HOVER",
    "#D6DFEB": "TEXT_SOFT",
    "#2A1118": "DANGER_PANEL",
    "#FFD6D9": "DANGER_TEXT",
    "#0A121D": "PANEL",
    "#64748B": "TEXT_DISABLED",
    "#344B66": "BORDER_STRONG",
    "#09111D": "PANEL",
    "#0D1827": "PANEL",
    "#2A3A51": "BORDER_STRONG",
    "#0A1320": "PANEL",
    "#101C2B": "PANEL_HOVER",
    "#0A4F32": "GREEN_DARK",
    "#10243A": "PANEL_ACTIVE",
    "#DCE5F2": "TEXT_SOFT",
    "#10301F": "PANEL_ACTIVE",
    "#10B981": "GREEN",
    "#0B7F3D": "GREEN_DARK",
    "#08111D": "SIDEBAR",
    "#334B66": "BORDER_STRONG",
    "#344863": "BORDER_STRONG",
    "#49617F": "TEXT_MUTED",
    "#2A2B11": "BADGE_BG",
    "#7D8424": "BADGE_BORDER",
    "#C9D44C": "BADGE_TEXT",
    "#D7DDD8": "TEXT_SOFT",
    "#13243A": "PANEL_HOVER",
    "#F2F6FF": "TEXT",
    "#101A28": "PANEL_2",
    "#9AA8BA": "TEXT_MUTED",
    "#16C766": "GREEN",
    "#F8C84E": "YELLOW",
    "#6EE7A8": "GREEN",
    "#07110C": "BG",
    "#0D1724": "PANEL",
    "#223044": "BORDER",
    "#182536": "BORDER_SOFT",
    "#58C878": "GREEN",
    "#10141D": "PANEL",
    "#F1F4FB": "TEXT",
    "#303847": "BORDER",
    "#1A202B": "PANEL_HOVER",
    "#2E7445": "GREEN_BORDER",
    "#6F4BB6": "GREEN",
    "#0B0F17": "BG",
    "#E7BF63": "YELLOW",
    "#2B3341": "BORDER",
    "#9CA5B4": "TEXT_MUTED",
    "#5E3D93": "GREEN_BORDER",
    "#8C95A3": "TEXT_MUTED",
    "#262D3A": "BORDER",
    "#AEB7C6": "TEXT_MUTED",
    "#242B37": "BORDER_SOFT",
    "#202733": "BORDER_SOFT",
    "#68717E": "TEXT_DISABLED",
    "#A78BDA": "GREEN",
    "#C9D0DC": "TEXT_SOFT",
    "#D9DFEB": "TEXT_SOFT",
    "#DFE6F3": "TEXT_SOFT",
    "#E0B75A": "YELLOW",
    "#7F5BC5": "GREEN_DARK",
    "#727B88": "TEXT_DISABLED",
    "#E8EDF7": "TEXT_SOFT",
    "#EEE7FB": "TEXT",
    "#080B12": "BG",
    "#33D46F": "GREEN",
    "#465166": "BORDER_STRONG",
    "#343B46": "BORDER_STRONG",
    "#29313F": "BORDER",
    "#28303D": "BORDER",
    "#27303D": "BORDER",
    "#252C38": "BORDER_SOFT",
    "#24183D": "PANEL_ACTIVE",
    "#202833": "BORDER",
    "#171D27": "PANEL_HOVER",
    "#141821": "PANEL_2",
    "#121720": "PANEL_2",
    "#0D1118": "PANEL",
    "#0C1118": "PANEL",
    "#687482": "TEXT_DISABLED",
    "#F5F0FF": "TEXT",
}

LEGACY_LITERAL_ALIASES = {
    "rgba(52, 142, 78, 0.20)": "rgba(159, 197, 40, 0.20)",
    "rgba(52, 142, 78, 0.28)": "rgba(159, 197, 40, 0.28)",
}


_STYLE_TEMPLATE = """
QMainWindow, QWidget {
    background: @BG;
    color: @TEXT;
    font-family: @FONT_FAMILY;
    font-size: @FONT_BODY;
}

QLabel {
    background: transparent;
    color: @TEXT;
}

QToolTip {
    background: @PANEL_2;
    color: @TEXT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
    padding: @SPACE_XS @SPACE_SM;
}

/* Sidebar uses the same glass surface, border and radius as a panel.
   No opaque nested black widget or separate navigation palette. */
#sidebar, #SideNav {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 @GLASS_PANEL_TOP, stop:1 @GLASS_PANEL_BOTTOM);
    border: 1px solid @BORDER_SOFT;
    border-top: 1px solid @GLASS_HAIRLINE;
    border-radius: @RADIUS_MD;
}
/* The real side navigation and its Dev UI preview inherit transparency. */
#sidebar QWidget#DevUiSidebarContent,
#SideNav QWidget#DevUiSidebarContent {
    background: transparent;
    border: none;
}

#burgerButton, #MenuButton {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-bottom: 2px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
    color: @TEXT_SOFT;
    font-size: @FONT_SMALL;
    font-weight: 700;
    padding: 0px @SPACE_MD;
    min-height: @CONTROL_HEIGHT_COMPACT;
    max-height: @CONTROL_HEIGHT_COMPACT;
}
#burgerButton:hover, #MenuButton:hover {
    background: @PANEL_HOVER;
    border-bottom-color: @GREEN_BORDER;
    color: @TEXT;
}
#burgerButton:pressed, #MenuButton:pressed {
    background: @PANEL_ACTIVE;
    border-bottom-color: @GREEN;
    color: @GREEN;
}

/* Compact side-nav states use the same blue/green hairline language as
   the selected Unity tabs, never a large full-green rectangle. */
#navItem, #navItemActive, #NavButton, #ActiveNavButton,
#TopmostButton, #TopmostButtonActive {
    background: @GLASS_BUTTON;
    border: 1px solid @BORDER_SOFT;
    border-bottom: 2px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
    color: @TEXT_SOFT;
    font-size: @FONT_SMALL;
    font-weight: 700;
    padding: 0px @SPACE_MD;
    text-align: left;
    min-height: @CONTROL_HEIGHT_COMPACT;
    max-height: @CONTROL_HEIGHT_COMPACT;
}
#navItem:hover, #NavButton:hover, #TopmostButton:hover {
    background: @GLASS_HOVER;
    border-bottom-color: @GREEN_BORDER;
    color: @TEXT;
}
#navItemActive, #ActiveNavButton, #TopmostButtonActive {
    background: @GLASS_HOVER;
    border-bottom: 2px solid @GREEN;
    color: @GREEN;
}
#navItemActive:hover, #ActiveNavButton:hover, #TopmostButtonActive:hover {
    background: @GLASS_HOVER;
    border-bottom-color: @GREEN_HOVER;
    color: @GREEN_HOVER;
}
#navItem:pressed, #navItemActive:pressed, #NavButton:pressed,
#ActiveNavButton:pressed {
    background: @GLASS_HOVER;
    border-bottom-color: @GREEN_BORDER;
}
#navItem:disabled, #navItemActive:disabled, #NavButton:disabled,
#ActiveNavButton:disabled {
    background: @GLASS_BUTTON;
    color: @TEXT_DISABLED;
    border-bottom-color: @BORDER_SOFT;
}

#NavSeparator {
    background: @BORDER_SOFT;
    border: none;
}

#AppTitle {
    color: @TEXT;
    font-size: 18px;
    font-weight: 800;
}

#DialogTitle {
    color: @TEXT;
    font-size: @FONT_TITLE;
    font-weight: 800;
    padding: 0px;
    border: none;
}

#DialogSubtitle, #MutedLabel {
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
}

QDialog#AtlasDialog,
QDialog#CloseActionDialog {
    background: @PANEL_GRADIENT;
    border: 1px solid @BORDER_STRONG;
    border-radius: @RADIUS_LG;
}

#DialogHeader,
#DialogActions {
    background: transparent;
    border: none;
}

#DialogLogo {
    background: @PANEL_2;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_MD;
    padding: @SPACE_XS;
}

#DialogBody {
    color: @TEXT_SOFT;
    font-size: @FONT_BODY;
}

#DialogDivider {
    background: @BORDER_SOFT;
    border: none;
    max-height: 1px;
}

/* Single owner for the launcher handoff popup: no widget-local stylesheet. */
QDialog#PreloadProgressPopup {
    background: @BG;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XL;
}
QLabel#PreloadPopupTitle {
    color: @TEXT;
    font-size: 22px;
    font-weight: 700;
    font-family: @FONT_FAMILY;
}
QLabel#PreloadPopupCurrent {
    color: @TEXT_MUTED;
    font-size: @FONT_BODY;
    font-family: @FONT_FAMILY;
}
QProgressBar#PreloadPopupProgress {
    background: @PANEL_2;
    color: @TEXT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
    min-height: 17px;
    text-align: center;
}
QProgressBar#PreloadPopupProgress::chunk {
    background: @GREEN;
    border-radius: 5px;
}

#organizerPage, #worldScanPage, #OrganizerPage, #QuestsPage, #EncyclopediaPage {
    background: @BG;
}

#PageTitle {
    color: @TEXT;
    font-size: @FONT_TITLE;
    font-weight: 800;
    letter-spacing: 0px;
    padding: 0px;
    border: none;
}

/* The developer catalog inherits the same palette and type scale.
   Only its section framing is scoped; never duplicate widget QSS locally. */
/* The real shell UnityBackdrop stays behind the gallery. Expose its stars
   through the gallery viewport and a soft blue panel gradient. */
QWidget#DevUiPage QScrollArea#DevUiGalleryScroll,
QWidget#DevUiPage QScrollArea#DevUiGalleryScroll > QWidget,
QWidget#DevUiPage QScrollArea#DevUiGalleryScroll > QWidget > QWidget {
    background: transparent;
}
/* Dev UI section frames are the universal Unity section frames. */
QGroupBox {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 @GLASS_PANEL_TOP, stop:1 @GLASS_PANEL_BOTTOM);
    border: 1px solid @BORDER_SOFT;
    border-top: 1px solid @GLASS_HAIRLINE;
    border-radius: @RADIUS_MD;
    margin-top: @SPACE_LG;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    top: @SPACE_MD;
    left: 10px;
    padding: 0px @SPACE_SM;
    color: @TEXT;
    font-size: @FONT_SECTION;
    font-weight: 700;
}
QHeaderView::section {
    font-size: @FONT_SMALL;
    font-weight: 600;
}
QWidget#DevUiPage QWidget#DevUiIconCell {
    background: transparent;
    border: none;
}
QWidget#DevUiPage QLabel#DevUiMissingIcon {
    /* An absent original icon must not create an opaque dark square. */
    background: transparent;
    color: @TEXT_DISABLED;
    border: 1px dashed @BORDER_SOFT;
    border-radius: @RADIUS_XS;
    font-size: @FONT_SECTION;
}
QWidget#DevUiPage QLabel#DevUiMissingIconText {
    color: @TEXT_DISABLED;
    font-size: @FONT_SMALL;
    background: transparent;
    border: none;
}
QTreeWidget::item {
    min-height: 24px;
    padding: 2px @SPACE_XS;
}

/* Lists, dropdowns and tab panes inherit the shared application styles.
   Only these two preview-specific surfaces need a local selector. */
QWidget#DevUiPage QWidget#DevUiTabPage,
QFrame#GuideUltimeGeneratedView {
    background: @PANEL;
    color: @TEXT;
}
/* The family selector keeps the original green active row. Only its
   unobtrusive separators and fixed row height are preview-specific. */
QWidget#DevUiPage QComboBox#DevUiFamilyCombo QAbstractItemView {
    selection-background-color: @GREEN_DARK;
    selection-color: @TEXT;
}

/* Replace Qt's near-black native slider with the existing Unity surface
   and active green, without changing the geometry of other app sliders. */
QSlider {
    background: transparent;
    min-height: 24px;
}
QSlider::groove:horizontal {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    height: 6px;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: @GREEN_DARK;
    border: 1px solid @GREEN_BORDER;
    border-radius: 3px;
}
QSlider::add-page:horizontal {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: @PANEL_ACTIVE;
    border: 2px solid @GREEN_BORDER;
    width: 14px;
    margin: -6px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: @PANEL_HOVER;
    border-color: @GREEN;
}

/* Preview-only resize and scroll surfaces: remove the native dark splitter
   strip and opaque Qt scrollbar track while leaving the thumb usable. */
QSplitter {
    background: transparent;
}
QSplitter::handle:horizontal {
    background: @PANEL_2;
    border-left: 1px solid @BORDER_SOFT;
    border-right: 1px solid @BORDER_SOFT;
}
QSplitter::handle:horizontal:hover {
    background: @PANEL_HOVER;
    border-left-color: @BORDER_CARD;
    border-right-color: @BORDER_CARD;
}
/* An inner QListWidget has its own opaque canvas: a transparent track
   exposed Qt's near-black default instead of the actual list panel. */
QWidget#DevUiPage QListWidget QScrollBar:vertical {
    background: @PANEL;
}
QWidget#DevUiPage QScrollArea#DevUiGalleryScroll QScrollBar:vertical {
    background: transparent;
}
/* A transparent page over a QListWidget reveals its native Qt base, not
   the shell wallpaper. Match the canonical list panel instead of black. */
QWidget#DevUiPage QListWidget QScrollBar::add-page:vertical,
QWidget#DevUiPage QListWidget QScrollBar::sub-page:vertical {
    background: @PANEL;
}

/* Layout-only stacks must reveal the shell backdrop, not the global
   opaque QWidget window color. This also covers the Quêtes tab. */
QTabWidget#EncyclopediaTabs,
QTabWidget#EncyclopediaTabs QStackedWidget#qt_tabwidget_stackedwidget,
QStackedWidget#GuidesStack,
QStackedWidget#GuideDetailContentStack,
QSplitter#GuideDetailSplitter,
QFrame#GuideManualValidationHost {
    background: transparent;
    border: none;
}
QTabWidget#EncyclopediaTabs::pane {
    background: transparent;
    border: none;
    top: -1px;
}

QTabWidget#EncyclopediaTabs QTabBar::tab {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-bottom: 2px solid @BORDER_SOFT;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
    font-weight: 700;
    min-height: 28px;
    padding: 0px 7px;
}

QTabWidget#EncyclopediaTabs QTabBar::tab:selected,
QTabWidget#EncyclopediaTabs QTabBar[guideActive="true"]::tab:selected {
    background: @PANEL_ACTIVE;
    border-color: @BORDER_SOFT;
    border-bottom: 2px solid @GREEN;
    color: @GREEN;
}

QTabWidget#EncyclopediaTabs QTabBar::tab:hover {
    background: @PANEL_HOVER;
    border-bottom-color: @GREEN_BORDER;
    color: @TEXT;
}

#EncyclopediaSearch {
    min-height: 28px;
    max-height: 28px;
    min-width: 220px;
}

#EncyclopediaCharacterCombo {
    min-height: 28px;
    max-height: 28px;
}

/* The Success catalogue must not cover the Unity sky with an opaque root. */
#AchievementsView {
    background: transparent;
}
#AchievementFilterPanel {
    background: @GLASS_BUTTON;
}

#AchievementsView #GuideLeftPanel,
#AchievementsView #GuideCenterPanel {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 @GLASS_PANEL_TOP,stop:1 @GLASS_PANEL_BOTTOM);
    border: 1px solid @BORDER_SOFT;
    border-top: 1px solid @GLASS_HAIRLINE;
    border-radius: @RADIUS_MD;
}

QTreeWidget#AchievementCategoryTree,
#AchievementsView QListWidget#QuestResultList {
    /* Never punch a solid near-black hole through the shared blue panel. */
    background: @PANEL_2;
    border: none;
    color: @TEXT_MUTED;
    outline: none;
}

QTreeWidget#AchievementCategoryTree::item,
#AchievementsView QListWidget#QuestResultList::item {
    min-height: 25px;
    padding: 2px 5px;
    border-left: 2px solid transparent;
}

QTreeWidget#AchievementCategoryTree::item:selected {
    background: @PANEL_2;
    color: @TEXT;
    border-left: 2px solid @GREEN;
}

#AchievementsView QListWidget#QuestResultList::item:selected {
    background: @PANEL_2;
    border-left: 2px solid @GREEN;
}

QSplitter#AchievementCatalogSplitter::handle {
    background: transparent;
    width: 4px;
}

#EncyclopediaPanel, #GuidesListPanel, #ProgressCard, #RewardCard,
#ObjectiveRow, #CategoryProgressCard, #EntityLinksPanel,
#AchievementContextDetail,
#AchievementSummaryWidget, #AchievementRewardWidget, #GuideCompletedSeriesLabel {
    background: @PANEL;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_MD;
}

#CategoryProgressCard, #RewardCard, #ObjectiveRow,
#AchievementContextDetail, #AchievementSummaryWidget, #AchievementRewardWidget {
    background: @PANEL_2;
    border-color: @BORDER_SOFT;
}

#GuideChevronButton {
    background: transparent;
    border: 1px solid transparent;
    color: @TEXT_MUTED;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
    padding: 0px;
    text-align: center;
}

#GuideHeaderImage, #GuideRewardImage {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_SM;
    padding: 0px;
}

#GuideSectionTitle {
    color: @TEXT;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0px;
    padding: 0px;
}

#GuideCompletedSeriesLabel {
    background: @PANEL_2;
    border-color: @BORDER_SOFT;
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
    padding: 7px 9px;
}

#EncyclopediaThreePanelDashboard::handle {
    background: @BORDER_SOFT;
}

#CompactScroll, #CompactScrollContent,
#RequiredItemRow, #ActivitySummary {
    background: transparent;
    border: none;
}

/* Read-only Unity status: a light top/left corner above the label.
   No full border, fill, pill, hover or pointer cursor: this is not a button.
   Both arms always inherit the SAME semantic token as the text. */
#StatusBadge, #ActivityBadge {
    background: transparent;
    border: none;
    border-top: 2px solid @TEXT_MUTED;
    border-left: 2px solid @TEXT_MUTED;
    border-radius: 0px;
    color: @TEXT_MUTED;
    font-size: @FONT_BADGE;
    font-weight: 700;
    padding: 7px 7px 2px 10px;
}

#StatusBadge[state="done"] {
    color: @GREEN;
    border-color: @GREEN;
}
#StatusBadge[state="blocked"] {
    color: @TEXT_MUTED;
    border-color: @TEXT_MUTED;
}
#StatusBadge[state="active"] {
    color: @TEXT_SOFT;
    border-color: @TEXT_SOFT;
}
#StatusBadge[state="danger"] {
    color: @RED_HOVER;
    border-color: @RED_HOVER;
}
#StatusBadge[state="warning"] {
    color: @YELLOW;
    border-color: @YELLOW;
}
#StatusBadge[state="info"] {
    color: @TEXT_SOFT;
    border-color: @TEXT_SOFT;
}
#StatusBadge[state="neutral"] {
    color: @TEXT_MUTED;
    border-color: @TEXT_MUTED;
}

#EncyclopediaResultList, #GuideResultList {
    background: @PANEL_2;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
    outline: 0;
}

#EncyclopediaResultList::item, #GuideResultList::item {
    border-bottom: 1px solid @BORDER_SOFT;
    color: @TEXT;
    min-height: 44px;
    padding: 5px 8px;
}

#EncyclopediaResultList::item:hover, #GuideResultList::item:hover {
    background: @PANEL_2;
}

#EncyclopediaResultList::item:selected, #GuideResultList::item:selected {
    background: @PANEL_ACTIVE;
    border-left: 3px solid @GREEN;
    color: @TEXT;
}

#EncyclopediaDetailPanel, #EncyclopediaDetailContent {
    background: transparent;
    border: none;
}

#DetailTitle {
    color: @TEXT;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 0px;
    padding: 0px;
    border: none;
}

#EntityLinkButton {
    color: @TEXT;
    text-align: left;
    min-height: 26px;
}

#EntityLinkButton:hover {
    border-color: @GREEN_BORDER;
    background: @PANEL_HOVER;
    color: @GREEN;
}

#AchievementEntityRow {
    background: transparent;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_SM;
}

#AchievementEntityRow:hover,
#ObjectiveRow:hover {
    border-color: @GREEN_BORDER;
    background: @PANEL_HOVER;
}

#AchievementEntityRowText {
    color: @TEXT;
}

#EncyclopediaProgressBar {
    background: @SIDEBAR;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
    height: 7px;
}

#EncyclopediaProgressBar::chunk {
    background: @GREEN;
    border-radius: 3px;
}

#TitleAccent {
    background: @GREEN;
    border-radius: 2px;
}

/* One common softly graded blue Unity panel, exactly as in Dev UI. */
#card, #OrganizerPanel, #Panel, #CraftPanel, #QuestPanel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 @GLASS_PANEL_TOP, stop:1 @GLASS_PANEL_BOTTOM);
    border: 1px solid @BORDER_SOFT;
    border-top: 1px solid @GLASS_HAIRLINE;
    border-radius: @RADIUS_MD;
}

/* Reusable nested content role: panels keep their own glass material.
   Never let a plain QWidget hide it with the application root background. */
QWidget#AtlasTransparentHost,
QWidget#CharacterEquipmentGrid,
QWidget#CharacterEquipmentCenter,
#DialogToolbar {
    background: transparent;
    border: none;
}

#cardTitle, #ControlSectionTitle, #PanelTitle {
    color: @TEXT;
    font-size: @FONT_SECTION;
    font-weight: 700;
    letter-spacing: 0px;
    padding: 0px;
}

#CardTitleAccent {
    background: @GREEN;
    border-radius: 1px;
}

#PanelHeaderIcon {
    color: @GREEN;
    font-size: 16px;
    font-weight: 700;
    padding: 0px;
}

#runtimeStatusActive, #runtimeStatusInactive, #RuntimeStatusDot {
    background: transparent;
    font-size: 14px;
    font-weight: 800;
}

#runtimeStatusActive {
    color: @GREEN;
}

#runtimeStatusInactive, #RuntimeStatusDot {
    color: @RED;
}

#CompactLabel {
    color: @TEXT;
    font-size: @FONT_BODY;
    padding: 0px;
}

#WarningLabel {
    color: @YELLOW;
    font-size: @FONT_SMALL;
    padding: 2px 0px;
}

#EmbeddedHost, QListWidget, QComboBox, QSpinBox, QScrollArea, QTextBrowser,
QLineEdit, #inputField, #comboField {
    background: @PANEL_2;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
    color: @TEXT;
}

QLineEdit, QComboBox, QSpinBox, #inputField, #comboField {
    min-height: @CONTROL_HEIGHT_COMPACT;
    padding: 0px @SPACE_LG;
    selection-background-color: @GREEN_DARK;
    selection-color: @TEXT;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, #inputField:focus, #comboField:focus {
    background: @PANEL_HOVER;
    border-color: @GREEN;
}

/* Force list-style Qt popups so maxVisibleItems works with non-editable
   Unity combos on Windows (native menu-style popups ignore that limit). */
QComboBox {
    combobox-popup: 0;
}

/* Qt adds the two 1px Unity borders to this content height. */
QComboBox#GuidePreparationCategoryFilter {
    min-height: @CONTROL_HEIGHT_COMPACT_CONTENT;
}

/* One popup contract for all native dropdowns (including Successes). */
QComboBox:hover {
    border-color: @BORDER_STRONG;
}

QComboBox:disabled {
    background: @PANEL;
    border-color: @BORDER_SOFT;
    color: @TEXT_DISABLED;
}

QComboBox QAbstractItemView {
    background: @PANEL_2;
    color: @TEXT;
    border: 1px solid @BORDER;
    outline: none;
    selection-background-color: @PANEL_ACTIVE;
    selection-color: @TEXT;
}

/* Same counter across Dev UI and real guide pagers; the content owns width. */
QLabel#AtlasPageCounter {
    background: @FIELD_SURFACE;
    color: @TEXT;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
    padding: 2px @SPACE_SM;
    font-weight: 700;
}

QSpinBox#QuantitySpinBox {
    padding-left: @SPACE_MD;
    padding-right: 30px;
}

QSpinBox#QuantitySpinBox::up-button,
QSpinBox#QuantitySpinBox::down-button {
    width: 22px;
}

#organizerPage QLineEdit,
#organizerPage #inputField,
#organizerPage #comboField {
    min-height: 30px;
    max-height: 30px;
    padding: 0px 10px;
}

#worldScanPage QComboBox,
#worldScanPage QSpinBox,
#worldScanPage #inputField {
    min-height: 28px;
    max-height: 28px;
    padding: 0px 8px;
}

QPushButton, QToolButton {
    background: @PANEL_2;
    color: @TEXT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
    padding: @SPACE_XXS @SPACE_LG;
    min-height: 22px;
}

QPushButton[atlasCompactButton="true"] {
    padding-top: 0;
    padding-bottom: 0;
}

QPushButton:hover, QToolButton:hover {
    background: @PANEL_HOVER;
    border-color: @BORDER_STRONG;
}

QPushButton:pressed, QToolButton:pressed {
    background: @PANEL_ACTIVE;
    border-color: @GREEN_BORDER;
    color: @GREEN;
}

QPushButton:disabled, QToolButton:disabled {
    background: @PANEL;
    border-color: @BORDER_SOFT;
    color: @TEXT_DISABLED;
}

/* Primary and secondary are the same control family. Variant-specific
   visuals live below; shared size, text layout and spacing live here. */
#primaryButton, #ActiveButton, #PrimaryActionButton,
#secondaryButton, #SecondaryButton {
    font-size: @FONT_SMALL;
    text-align: left;
    padding-left: @SPACE_LG;
    padding-right: @SPACE_MD;
}

/* Shared action hierarchy: blue at rest, green only for interaction/state.
   No large neon/solid-green rectangles on ordinary Atlas buttons. */
#primaryButton, #PrimaryActionButton {
    background: @PANEL_2;
    border-color: @BORDER_CARD;
    color: @TEXT;
    font-weight: 700;
}
#primaryButton:hover, #PrimaryActionButton:hover {
    background: @PANEL_HOVER;
    border-color: @GREEN_BORDER;
    color: @GREEN;
}
#primaryButton:pressed, #PrimaryActionButton:pressed,
#primaryButton:checked, #PrimaryActionButton:checked {
    background: @PANEL_ACTIVE;
    border-color: @GREEN_BORDER;
    color: @GREEN;
}

#ActiveButton {
    background: @PANEL_ACTIVE;
    border-color: @BORDER_CARD;
    border-bottom: 2px solid @GREEN;
    color: @GREEN;
    font-weight: 700;
}
#ActiveButton:hover, #ActiveButton:pressed {
    background: @PANEL_HOVER;
    color: @GREEN_HOVER;
}
#ActiveButton:focus {
    border-color: @TEXT_SOFT;
    border-bottom-color: @GREEN;
}

#secondaryButton, #SecondaryButton {
    background: @PANEL_2;
    border-color: @BORDER;
    color: @TEXT_SOFT;
    font-weight: 600;
}

#secondaryButton:hover, #SecondaryButton:hover {
    background: @PANEL_HOVER;
    border-color: @GREEN_BORDER;
    color: @TEXT;
}

/* Shared toggle state for real checkable secondary actions. Same semantic
   selection colors as Atlas navigation, no decorative paint or local QSS. */
#SecondaryButton:checked, #secondaryButton:checked {
    background: @PANEL_ACTIVE;
    border-color: @GREEN_BORDER;
    color: @GREEN;
}
#SecondaryButton:checked:hover, #secondaryButton:checked:hover {
    background: @PANEL_HOVER;
    border-color: @GREEN;
    color: @GREEN_HOVER;
}
#SecondaryButton:pressed, #secondaryButton:pressed {
    background: @PANEL_ACTIVE;
    border-color: @GREEN_BORDER;
    color: @GREEN;
}

/* Shared normal/hover/active surfaces for all stateful segmented and
   Guide completion toggles. Different text alignment stays module-owned. */
#GuideHideCompletedToggle,
#segmentedButton, #segmentedButtonActive {
    background: @PANEL_2;
    border-color: @BORDER;
    color: @TEXT_SOFT;
    font-weight: 600;
}

#GuideHideCompletedToggle {
    font-size: @FONT_SMALL;
    text-align: left;
    padding-left: 10px;
    padding-right: 8px;
}

#segmentedButton, #segmentedButtonActive {
    border: 1px solid @BORDER;
    text-align: center;
    padding: 0px 8px;
}

#GuideHideCompletedToggle:hover, #segmentedButton:hover {
    background: @PANEL_HOVER;
    border-color: @BORDER_STRONG;
}

#GuideHideCompletedToggle:hover {
    color: @TEXT;
}

#GuideHideCompletedToggle:checked, #segmentedButtonActive {
    background: @PANEL_ACTIVE;
    border-color: @GREEN_BORDER;
    color: @GREEN;
}

#segmentedButtonActive {
    font-weight: 700;
}

#GuideHideCompletedToggle:checked:hover, #segmentedButtonActive:hover {
    background: @PANEL_HOVER;
    border-color: @GREEN_HOVER;
    color: @GREEN_HOVER;
}

/* Red stays a meaning, not a huge rectangle. Critical Stop Urgence is
   a separately identified emergency action and must remain unmistakable. */
#dangerButton, #DangerButton {
    background: @PANEL_2;
    border-color: @RED;
    color: @RED_HOVER;
    font-size: @FONT_BODY;
    font-weight: 700;
    text-align: center;
    padding-left: 8px;
    padding-right: 8px;
}
#dangerButton:hover, #DangerButton:hover {
    background: @PANEL_HOVER;
    border-color: @RED_HOVER;
    color: @RED_HOVER;
}
#dangerButton:pressed, #DangerButton:pressed {
    background: @PANEL_ACTIVE;
    border-color: @RED;
    color: @TEXT;
}

/* Disabled has the highest priority for each shared button identity.
   Without a matching ID selector the normal text color can override
   the generic QPushButton:disabled rule on some Windows Qt styles. */
#primaryButton:disabled, #ActiveButton:disabled,
#PrimaryActionButton:disabled, #secondaryButton:disabled,
#SecondaryButton:disabled, #segmentedButton:disabled,
#segmentedButtonActive:disabled, #GuideHideCompletedToggle:disabled,
#dangerButton:disabled, #DangerButton:disabled {
    background: @PANEL;
    border-color: @BORDER_SOFT;
    color: @TEXT_DISABLED;
}

/* Reusable clickable text vs. real buttons. Native QPushButton semantics
   retain keyboard activation and a visible :focus outline. */
#InlineActionButton, #PopupLinkButton {
    background: transparent;
    border: 1px solid transparent;
    color: @TEXT_SOFT;
    font-weight: 600;
    font-size: @FONT_SMALL;
    padding: 3px 6px;
    text-align: left;
}
#InlineActionButton:hover, #PopupLinkButton:hover {
    background: @GLASS_SUBTLE_SURFACE;
    border-color: transparent;
    color: @GREEN_HOVER;
}
#InlineActionButton:pressed, #PopupLinkButton:pressed {
    background: @PANEL_HOVER;
    border-color: transparent;
    color: @GREEN;
}
#InlineActionButton:focus, #PopupLinkButton:focus {
    border: 1px solid @GREEN_BORDER;
    background: transparent;
}
#InlineActionButton:disabled, #PopupLinkButton:disabled {
    background: transparent;
    border-color: transparent;
    color: @TEXT_DISABLED;
}

/* Shared semantic interactive chips with normal / hover / pressed /
   selected / keyboard-focus / disabled states. Unlike StatusBadge QLabel,
   these are real actions, not passive statuses. */
/* Clickable chips remain underlined actions, deliberately distinct from passive corner badges:
   transparent at rest, no perimeter; semantic underline on hover/selection.
   Native QPushButton still gives keyboard, click, focus and tooltips. */
#StatusChip {
    background: transparent;
    color: @TEXT_SOFT;
    border: none;
    border-bottom: 2px solid @BORDER_SOFT;
    border-radius: 0px;
    padding: 1px 5px;
    font-size: @FONT_BADGE;
    font-weight: 700;
}
#StatusChip:hover {
    background: @GLASS_SUBTLE_SURFACE;
    border-bottom-color: @BORDER_CARD;
}
#StatusChip:pressed {
    background: @PANEL_HOVER;
}
#StatusChip:checked {
    background: transparent;
    border-bottom-color: @GREEN_BORDER;
}
#StatusChip:focus {
    border: 1px solid @BORDER_CARD;
    border-bottom: 2px solid @GREEN_BORDER;
}
#StatusChip:disabled {
    background: transparent;
    color: @TEXT_DISABLED;
    border-bottom-color: transparent;
}
#StatusChip[tone="success"] { color: @GREEN; }
#StatusChip[tone="success"]:hover { color: @GREEN_HOVER; border-bottom-color: @GREEN_HOVER; }
#StatusChip[tone="danger"] { color: @RED_HOVER; }
#StatusChip[tone="danger"]:hover { border-bottom-color: @RED_HOVER; }
#StatusChip[tone="warning"] { color: @YELLOW; }
#StatusChip[tone="warning"]:hover { border-bottom-color: @YELLOW; }
#StatusChip[tone="info"] { color: @TEXT_SOFT; }
#StatusChip[tone="info"]:hover { color: @TEXT; border-bottom-color: @BORDER_STRONG; }
#StatusChip[tone="neutral"] { color: @TEXT_MUTED; }
#StatusChip[tone="neutral"]:hover { color: @TEXT; border-bottom-color: @BORDER_CARD; }
#StatusChip[tone="success"]:checked { color: @GREEN_HOVER; border-bottom-color: @GREEN; }
#StatusChip[tone="danger"]:checked { border-bottom-color: @RED; }
#StatusChip[tone="warning"]:checked { border-bottom-color: @YELLOW; }
#StatusChip[tone="info"]:checked { color: @TEXT; border-bottom-color: @BORDER_STRONG; }
#StatusChip[tone="neutral"]:checked { color: @TEXT_SOFT; border-bottom-color: @BORDER_CARD; }

#keyBadge, #InlineShortcutButton {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: 5px;
    color: @TEXT;
    font-size: 10px;
    font-weight: 700;
    padding: 0px 5px;
    text-align: center;
    min-width: 34px;
    min-height: 20px;
    max-height: 20px;
}

#keyBadge:hover, #InlineShortcutButton:hover {
    background: @PANEL_HOVER;
    border-color: @GREEN;
}

#worldScanPage QPushButton#primaryButton,
#worldScanPage QPushButton#secondaryButton {
    min-height: 30px;
    max-height: 30px;
    padding: 0px 12px;
    text-align: center;
}

#iconButton, #ClientMenuButton {
    background: @PANEL_2;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
    color: @TEXT;
    font-size: 14px;
    font-weight: 800;
    padding: 0px;
    text-align: center;
}

#iconButton:hover, #ClientMenuButton:hover {
    background: @PANEL_HOVER;
    border-color: @BORDER_STRONG;
    color: @TEXT;
}

#iconButtonDanger, #ShortcutClear {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    color: @TEXT_SOFT;
    font-size: 10px;
    font-weight: 800;
    padding: 0px;
    text-align: center;
}

#iconButtonDanger:hover, #ShortcutClear:hover {
    background: @DANGER_PANEL;
    border-color: @RED;
    color: @DANGER_TEXT;
}

#GhostButton {
    background: @PANEL;
    border-style: dashed;
    border-color: @BORDER;
    color: @TEXT_DISABLED;
}

#GhostTile {
    background: @PANEL_2;
    border: 1px dashed @BORDER;
    border-radius: @RADIUS_SM;
}

#SessionsArea {
    background: transparent;
    border: none;
}

#characterSlot, #ListRow {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: 7px;
    margin: 0px;
}

#characterSlot:hover, #ListRow:hover {
    background: @PANEL_HOVER;
    border-color: @BORDER_STRONG;
}

#characterSlotEmpty, #EmptySessionSlot {
    background: @PANEL;
    border: 1px solid @BORDER_SOFT;
    border-radius: 7px;
    margin: 0px;
}

#characterSlotEmpty:hover, #EmptySessionSlot:hover {
    background: @PANEL;
    border-color: @BORDER_STRONG;
}

#characterSlotMissing, #MissingSessionRow {
    background: @PANEL;
    border: 1px solid @BORDER_SOFT;
    border-radius: 7px;
    margin: 0px;
}

#characterSlotMissing:hover, #MissingSessionRow:hover {
    background: @PANEL_HOVER;
    border-color: @BORDER_STRONG;
}

#characterSlotDragging, #DraggingListRow {
    background: @GREEN_DARK;
    border: 1px solid @GREEN;
    border-radius: 7px;
    margin: 0px;
}

#characterSlotDropTarget, #DropTargetListRow {
    background: @PANEL_ACTIVE;
    border: 1px dashed @GREEN;
    border-radius: 7px;
    margin: 0px;
}

#EmptySlotAdd {
    color: @GREEN;
    font-size: 17px;
    font-weight: 400;
}

#slotIndexBadge, #slotNumberBadge {
    background: @PANEL;
    border: 1px solid @BORDER_SOFT;
    border-radius: 5px;
    color: @TEXT_MUTED;
    font-size: 10px;
    font-weight: 700;
    padding: 0px;
}

#DragHandle {
    background: transparent;
    border: none;
    color: @TEXT_MUTED;
    font-size: 15px;
    font-weight: 800;
    padding: 0px;
}

#DragHandle:hover {
    color: @GREEN;
}

#FavoriteButton, #FavoriteButtonActive {
    background: transparent;
    border: none;
    padding: 0px;
    font-size: 17px;
}

#FavoriteButton {
    color: @TEXT_MUTED;
}

#FavoriteButton:hover, #FavoriteButtonActive {
    color: @YELLOW;
}

#ClientIndexButton, #PrimaryClientIndexButton {
    background: @PANEL;
    border: 1px solid @BORDER;
    border-radius: 5px;
    color: @TEXT;
    font-weight: 800;
    padding: 0px;
}

#PrimaryClientIndexButton {
    border-color: @GREEN;
}

#ZaapSuggestionPopup {
    background: @PANEL_2;
    border: 1px solid @GREEN;
    border-radius: @RADIUS_SM;
    padding: 4px;
}

#ZaapSuggestionPopup::item, QListWidget::item {
    color: @TEXT_SOFT;
    padding: 5px 8px;
    min-height: 25px;
    border-radius: @RADIUS_XS;
    border-bottom: 1px solid @BORDER_SOFT;
}

#ZaapSuggestionPopup::item:selected, #ZaapSuggestionPopup::item:hover,
QListWidget::item:selected {
    background: @PANEL_ACTIVE;
    color: @TEXT;
}

#ZaapFavoritesRow {
    background: transparent;
}

#favoriteChip, #ZaapFavoriteChip {
    background: @PANEL;
    border: 1px solid @BORDER;
    border-radius: 7px;
    min-height: 26px;
    max-height: 26px;
}

#favoriteChipStar, #ZaapFavoriteStar {
    background: transparent;
    color: @GREEN;
    border: none;
    border-radius: 0px;
    padding: 0px;
    font-size: @FONT_BODY;
    font-weight: 800;
}

#favoriteChip:hover, #ZaapFavoriteChip:hover,
#favoriteChipStar:hover, #ZaapFavoriteStar:hover {
    background: @PANEL_ACTIVE;
    border-color: @GREEN;
    color: @TEXT;
}

#favoriteChipName, #ZaapFavoriteName {
    background: transparent;
    color: @TEXT_SOFT;
    border: none;
    border-radius: 0px;
    padding: 0px;
    font-size: @FONT_SMALL;
    font-weight: 700;
    text-align: left;
}

#favoriteChipName:hover, #ZaapFavoriteName:hover {
    background: transparent;
    border: none;
    color: @TEXT;
}

#Divider {
    background: @BORDER_SOFT;
    border: none;
}

#ResourceTile {
    border-color: @GREEN;
    text-align: center;
    padding: 0px;
    font-size: 8px;
    min-width: 52px;
    min-height: 38px;
}

#SelectionRow {
    background: @PANEL_2;
    border-radius: @RADIUS_SM;
}

/* Map and World read-only values share one glass material.
   Local height and inset remain explicit because their layouts differ. */
#WorldDetailValue, #MapDetailValue {
    background: @GLASS_BUTTON;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_SM;
    color: @TEXT;
    font-size: @FONT_SMALL;
}
#WorldDetailValue {
    padding: 4px 6px;
    min-height: 18px;
}

/* Static map chrome uses the same panel glass as the Dev UI gallery.
   The interactive canvas retains its dedicated painting surface. */
#MapToolbar, #WorldDetailPanel {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 @GLASS_PANEL_TOP,stop:1 @GLASS_PANEL_BOTTOM);
    border: 1px solid @BORDER_SOFT;
    border-top: 1px solid @GLASS_HAIRLINE;
    border-radius: @RADIUS_MD;
}
#MapCanvas {
    background: @PANEL;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_MD;
}

#WorldDetailTitle {
    color: @TEXT;
    font-size: 13px;
    font-weight: 800;
}

#WorldScanProgress {
    color: @TEXT_SOFT;
    font-size: @FONT_BODY;
    font-weight: 750;
}

#WorldCacheState {
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
    font-weight: 650;
}

#BreadcrumbLabel {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_SM;
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
    font-weight: 700;
    padding: 0px 10px;
}

#WorldPlanetButton {
    background: @PANEL_2;
    border: 1px solid @BORDER_CARD;
    border-radius: 30px;
    padding: 0px;
}
#WorldPlanetButton:hover {
    background: @PANEL_HOVER;
    border-color: @GREEN_BORDER;
    color: @GREEN;
}
#WorldPlanetButton:pressed {
    background: @PANEL_ACTIVE;
    border-color: @GREEN;
    color: @GREEN;
}

#WorldMenu {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 @GLASS_PANEL_TOP,stop:1 @GLASS_PANEL_BOTTOM);
    border: 1px solid @BORDER_SOFT;
    border-top: 1px solid @GLASS_HAIRLINE;
    border-radius: @RADIUS_MD;
}

#WorldMenuScroll, #WorldMenuContents {
    background: transparent;
    border: none;
}

#WorldMenuScroll QScrollBar:vertical {
    background: @GLASS_PANEL_BOTTOM;
    border: none;
    border-radius: @RADIUS_XS;
    margin: 4px 0px 4px 0px;
    width: 8px;
}

#WorldMenuScroll QScrollBar::handle:vertical {
    background: @BORDER_CARD;
    border-radius: @RADIUS_XS;
    min-height: 36px;
}

#WorldMenuScroll QScrollBar::handle:vertical:hover {
    background: @BORDER_STRONG;
}

#WorldMenuScroll QScrollBar::add-line:vertical,
#WorldMenuScroll QScrollBar::sub-line:vertical {
    background: transparent;
    border: none;
    height: 0px;
}

#WorldMenuScroll QScrollBar::add-page:vertical,
#WorldMenuScroll QScrollBar::sub-page:vertical {
    background: transparent;
}

#WorldMenuDivider {
    background: @BORDER_SOFT;
    border: none;
    margin: 3px 8px;
}

#WorldMenuItem, #WorldMenuItemActive {
    background: transparent;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;
    border-radius: @RADIUS_SM;
    color: @TEXT_SOFT;
    font-size: @FONT_BODY;
    font-weight: 650;
    padding: 0px 10px;
    text-align: left;
}
#WorldMenuItem:hover {
    background: @GLASS_HOVER;
    border-color: @BORDER_STRONG;
    color: @TEXT;
}
#WorldMenuItemActive {
    background: @PANEL_ACTIVE;
    border-color: @GREEN_BORDER;
    border-bottom: 2px solid @GREEN;
    color: @GREEN;
    font-weight: 800;
}
#WorldMenuItemActive:hover {
    background: @PANEL_HOVER;
    border-color: @GREEN_HOVER;
    border-bottom-color: @GREEN_HOVER;
}
#WorldMenuItem:disabled, #WorldMenuItemActive:disabled {
    background: @GLASS_PANEL_BOTTOM;
    border-color: @BORDER_SOFT;
    color: @TEXT_DISABLED;
}

#MapViewTree {
    background: @PANEL;
    border: none;
    color: @TEXT;
    outline: 0;
}

#MapViewTree::item {
    min-height: 28px;
    border-radius: @RADIUS_SM;
    padding: 0px 7px;
    color: @TEXT_SOFT;
}

#MapViewTree::item:hover {
    background: @GLASS_HOVER;
    color: @TEXT;
}

#MapViewTree::item:selected {
    background: @PANEL_ACTIVE;
    color: @TEXT;
    border: 1px solid @GREEN_BORDER;
}

#MapDetailValue {
    padding: 5px 7px;
    min-height: 20px;
}

#ResourceNameButton {
    background: transparent;
    border: none;
    color: @TEXT;
    text-align: left;
    padding: 0px 4px;
    min-height: 22px;
}

#ResourceNameButton:hover {
    background: @PANEL_HOVER;
    border: 1px solid @BORDER;
}

#LevelBadge {
    background: @PANEL_2;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
    color: @GREEN;
    font-size: @FONT_SMALL;
    font-weight: 800;
    padding: 2px 6px;
}

QScrollBar:horizontal {
    height: 0px;
    background: transparent;
}

/* Global compact scrollbars match Dev UI without opaque native wells. */
QScrollBar:vertical {
    background: @PANEL;
    width: 8px;
    margin: 0px;
    border: none;
    border-radius: @RADIUS_XS;
}
QScrollBar::handle:vertical {
    background: @BORDER_CARD;
    min-height: 26px;
    border-radius: @RADIUS_XS;
}
QScrollBar::handle:vertical:hover {
    background: @BORDER_STRONG;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    background: transparent;
    border: none;
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
    border: none;
}

QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid @TEXT;
    background: transparent;
}

QCheckBox::indicator:checked {
    background: @GREEN;
    border-color: @GREEN;
}


#TopNav {
    background: @SHELL_GRADIENT;
    border: none;
    border-bottom: 1px solid @BORDER;
    min-height: @TOP_NAV_HEIGHT;
    max-height: @TOP_NAV_HEIGHT;
}

#TopNavBrand {
    background: transparent;
    border: none;
    color: @TEXT;
    font-size: @FONT_TITLE;
    font-weight: 900;
    padding: 0px 10px;
    min-height: @TOP_NAV_CONTROL_HEIGHT;
    max-height: @TOP_NAV_CONTROL_HEIGHT;
}

#TopNavBrandIcon,
#TopNavBrandText {
    background: transparent;
    border: none;
}

#TopNavBrandText {
    color: @TEXT;
    font-size: @FONT_TITLE;
    font-weight: 900;
}

#TopNavBrand:hover {
    color: @GREEN_HOVER;
    background: @PANEL;
    border-radius: @RADIUS_SM;
}

#TopNavButton, #TopNavButtonActive {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-bottom: 2px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
    color: @TEXT;
    font-size: @FONT_BODY;
    font-weight: 700;
    padding: 0px 8px;
    min-height: @TOP_NAV_CONTROL_HEIGHT;
    max-height: @TOP_NAV_CONTROL_HEIGHT;
}

#TopNavButton:hover {
    background: @PANEL_HOVER;
    border-bottom-color: @GREEN_BORDER;
    color: @TEXT;
}
#TopNavButtonActive {
    background: @PANEL_ACTIVE;
    border-bottom-color: @GREEN;
    color: @GREEN;
}
#TopNavButtonActive:hover {
    background: @PANEL_HOVER;
    border-bottom-color: @GREEN_HOVER;
    color: @GREEN_HOVER;
}

/* Every top-level and Outils/Stuffs sub-tab shares interaction states.
   Keep normal and active geometry identical so focus never moves the row. */
#TopNavButton:pressed, #TopNavButtonActive:pressed {
    background: @PANEL_HOVER;
    border-bottom-color: @GREEN_BORDER;
}
#TopNavButton:disabled, #TopNavButtonActive:disabled {
    background: transparent;
    color: @TEXT_DISABLED;
    border-bottom-color: transparent;
}
#TopNavButton:focus, #TopNavButtonActive:focus {
    border: 1px solid @GREEN_BORDER;
    border-bottom: 2px solid @GREEN;
}

#TopNavSettings {
    background: transparent;
    border: 1px solid transparent;
    border-radius: @RADIUS_SM;
    color: @TEXT_MUTED;
    font-size: 16px;
    font-weight: 800;
    padding: 0px;
}

#TopNavSettings:hover {
    background: @PANEL_2;
    border-color: @BORDER;
    color: @TEXT;
}

QMenu {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 @GLASS_PANEL_TOP,stop:1 @GLASS_PANEL_BOTTOM);
    color: @TEXT;
    border: 1px solid @BORDER_SOFT;
    border-top: 1px solid @GLASS_HAIRLINE;
    border-radius: @RADIUS_MD;
    padding: @SPACE_XS;
}

QMenu::item {
    background: transparent;
    color: @TEXT;
    border-radius: @RADIUS_XS;
    padding: @SPACE_SM 22px @SPACE_SM @SPACE_LG;
}

QMenu::item:selected {
    background: @PANEL_ACTIVE;
    color: @TEXT;
}

QMenu::separator {
    height: 1px;
    background: @BORDER_SOFT;
    margin: 4px 6px;
}

/* Almanax is a true date picker, not a fabricated offrandes feed. */
QWidget#AlmanaxPage { background: transparent; }
QCalendarWidget#AlmanaxCalendar {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 @GLASS_PANEL_TOP,stop:1 @GLASS_PANEL_BOTTOM);
    color: @TEXT;
    border: 1px solid @BORDER_SOFT;
    border-top: 1px solid @GLASS_HAIRLINE;
    border-radius: @RADIUS_MD;
}
QCalendarWidget#AlmanaxCalendar QWidget#qt_calendar_navigationbar {
    background: transparent;
}
QCalendarWidget#AlmanaxCalendar QToolButton {
    background: @GLASS_BUTTON;
    color: @TEXT;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
    min-height: @CONTROL_HEIGHT_COMPACT;
}
QCalendarWidget#AlmanaxCalendar QToolButton:hover {
    background: @GLASS_HOVER;
    border-color: @GREEN_BORDER;
}
/* Qt paints the calendar day grid in an inner table/viewport. Give the
   viewport and its cells the same opaque Unity blue, never Qt black. */
QCalendarWidget#AlmanaxCalendar QAbstractItemView,
QCalendarWidget#AlmanaxCalendar QTableView#qt_calendar_calendarview {
    background: @PANEL_2;
    alternate-background-color: @PANEL_2;
    color: @TEXT;
    border: none;
    gridline-color: @BORDER_SOFT;
    selection-background-color: @PANEL_ACTIVE;
    selection-color: @TEXT;
}
QCalendarWidget#AlmanaxCalendar QTableView#qt_calendar_calendarview::item {
    background: @PANEL_2;
    color: @TEXT;
}
QCalendarWidget#AlmanaxCalendar QTableView#qt_calendar_calendarview::item:selected {
    background: @PANEL_ACTIVE;
    color: @TEXT;
}
QLabel#AlmanaxSelectedDate { color: @TEXT; font-size: @FONT_SECTION; font-weight: 700; }
QLabel#AlmanaxUnavailable { color: @TEXT_MUTED; font-size: @FONT_BODY; }

#HomePage {
    background: transparent;
}

#HomeLeftColumn,
#HomeRightColumn {
    background: transparent;
    border: none;
}

#HomeCharacterCard,
#HomeTrackingCard,
#HomeGuideCard,
#HomeNetworkMiniCard,
#HomeAlmanaxCard {
    background: @PANEL_GRADIENT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_LG;
}

#HomeGuideCard {
    border-color: @BORDER_STRONG;
}

#HomeNetworkMiniCard {
    border-color: @BORDER_SOFT;
}

#HomeNetworkIndicator {
    color: @TEXT_MUTED;
    font-size: 16px;
    font-weight: 900;
    min-width: 16px;
    max-width: 16px;
}

#HomeNetworkIndicator[state="active"] {
    color: @GREEN;
}

#HomeNetworkIndicator[state="pending"] {
    color: @YELLOW;
}

#HomeNetworkIndicator[state="error"] {
    color: @RED;
}

#HomeNetworkMiniTitle {
    color: @TEXT_SOFT;
    font-size: @FONT_BODY;
    font-weight: 700;
}

#HomeNetworkMiniStatus {
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
    font-weight: 500;
}

#HomeCardTitle {
    color: @GREEN;
    font-size: @FONT_TITLE;
    font-weight: 800;
    padding: 0px 0px 3px 0px;
}

#HomeGuideTitle {
    color: @TEXT_SOFT;
    font-size: 16px;
    font-weight: 500;
    padding: 0px 0px 3px 0px;
}

#HomeCharacterName {
    color: @TEXT;
    font-size: 20px;
    font-weight: 800;
}

#HomeCharacterProgress {
    color: @TEXT_MUTED;
    font-size: 13px;
    font-weight: 500;
}

#HomeCharacterPortrait {
    background: @PANEL_HOVER;
    border: 1px solid @BORDER_STRONG;
    border-radius: 49px;
    padding: 5px;
}

#HomeChangeCharacterButton,
#HomeContinueButton,
#HomeAlmanaxButton {
    background: @PANEL_2;
    border: 1px solid @BORDER_CARD;
    border-radius: @RADIUS_SM;
    color: @TEXT;
    font-size: 13px;
    font-weight: 700;
    min-height: 42px;
    max-height: 42px;
    padding: 0px 14px;
    text-align: center;
}

#HomeChangeCharacterButton:hover,
#HomeContinueButton:hover,
#HomeAlmanaxButton:hover {
    background: @PANEL_HOVER;
    border-color: @GREEN_BORDER;
    color: @GREEN;
}
#HomeChangeCharacterButton:pressed,
#HomeContinueButton:pressed,
#HomeAlmanaxButton:pressed {
    background: @PANEL_ACTIVE;
    border-color: @GREEN_BORDER;
    color: @GREEN;
}

#HomeContinueButton:disabled,
#HomeAlmanaxButton:disabled {
    background: @PANEL;
    border-color: @BORDER_SOFT;
    color: @TEXT_DISABLED;
}

#HomeGuideBanner {
    background: @PANEL_2;
    border: 1px solid @BORDER;
    border-radius: 7px;
}

#HomeGuideProgressLabel {
    color: @TEXT_SOFT;
    font-size: 14px;
    font-weight: 600;
}

#HomeGuideProgressPercent {
    color: @GREEN;
    font-size: 16px;
    font-weight: 900;
}

#HomeProgressBar {
    background: @PANEL;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_SM;
    min-height: 13px;
    max-height: 13px;
}

#HomeProgressBar::chunk {
    background: @GREEN;
    border-radius: 5px;
}

#HomeGuideDetailRow {
    background: transparent;
    border: none;
    border-bottom: 1px solid @BORDER_SOFT;
}

#HomeGuideDetailIcon {
    color: @TEXT_MUTED;
    font-size: 19px;
    font-weight: 700;
}

#HomeGuideDetailLabel {
    color: @TEXT_MUTED;
    font-size: 13px;
    font-weight: 500;
}

#HomeGuideDetailValue {
    color: @GREEN;
    font-size: 14px;
    font-weight: 700;
}

#HomeTrackingRow {
    background: transparent;
    border: none;
    min-height: 28px;
    max-height: 28px;
}

#HomeTrackingIcon {
    color: @YELLOW;
    font-size: 15px;
    font-weight: 900;
}

#HomeTrackingLabel {
    color: @TEXT_SOFT;
    font-size: @FONT_SMALL;
    font-weight: 600;
}

#HomeTrackingValue {
    color: @TEXT_SOFT;
    font-size: @FONT_SMALL;
    font-weight: 700;
}

#HomeTrackingBar {
    background: @PANEL_HOVER;
    border: none;
    border-radius: @RADIUS_XS;
    min-height: 8px;
    max-height: 8px;
}

#HomeTrackingBar::chunk {
    background: @GREEN_DARK;
    border-radius: @RADIUS_XS;
}

#HomeAlmanaxPlaceholderIcon {
    background: transparent;
    border: none;
    border-radius: 75px;
    padding: 4px;
}

#HomeAlmanaxText {
    color: @TEXT_SOFT;
    font-size: 14px;
    font-weight: 500;
    padding: 8px 10px;
}

#SettingsPage,
#PlaceholderPage,
#EncyclopediaUnavailableBestiary {
    background: transparent;
}


/* Phase 2 views: application-level visual rules live here. */

                QWidget#AchievementsView {
                    background: transparent;
                }

                QWidget#AchievementsView QLineEdit#EncyclopediaSearch {
                    background: @PANEL;
                    border: 1px solid @BORDER;
                    border-radius: @RADIUS_MD;
                    color: @TEXT;
                    min-height: 32px;
                    max-height: 32px;
                    padding: 0px 10px;
                    selection-background-color: @GREEN_DARK;
                }

                QWidget#AchievementsView QLineEdit#EncyclopediaSearch:focus {
                    border-color: @GREEN;
                }

                QWidget#AchievementsView QFrame#GuideLeftPanel,
                QWidget#AchievementsView QFrame#GuideCenterPanel,
                QWidget#AchievementsView QStackedWidget#AchievementDetailStack {
                    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 @GLASS_PANEL_TOP,stop:1 @GLASS_PANEL_BOTTOM);
                    border: 1px solid @BORDER_SOFT;
                    border-top: 1px solid @GLASS_HAIRLINE;
                    border-radius: @RADIUS_MD;
                }

                QWidget#AchievementsView QLabel#GuideSectionTitle {
                    color: @YELLOW;
                    font-size: @FONT_BODY;
                    font-weight: 800;
                    padding: 1px 2px 6px 2px;
                }

                QWidget#AchievementsView QTreeWidget#AchievementCategoryTree,
                QWidget#AchievementsView QListWidget#QuestResultList {
                    background: transparent;
                    border: none;
                    color: @TEXT_SOFT;
                    outline: none;
                    show-decoration-selected: 0;
                }

                QWidget#AchievementsView QTreeWidget#AchievementCategoryTree::item {
                    min-height: 30px;
                    margin: 1px 0px;
                    padding: 3px 7px;
                    border: 1px solid transparent;
                    border-left: 3px solid transparent;
                    border-radius: @RADIUS_SM;
                }

                QWidget#AchievementsView QTreeWidget#AchievementCategoryTree::item:hover {
                    background: @PANEL_HOVER;
                    border-color: @BORDER_SOFT;
                }

                QWidget#AchievementsView QTreeWidget#AchievementCategoryTree::item:selected {
                    background: @PANEL_ACTIVE;
                    border: 1px solid @GREEN_BORDER;
                    border-left: 3px solid @GREEN;
                    color: @TEXT;
                }

                QWidget#AchievementsView QListWidget#QuestResultList::item {
                    background: @PANEL_2;
                    border: 1px solid @BORDER_SOFT;
                    border-left: 3px solid transparent;
                    border-radius: @RADIUS_SM;
                    color: @TEXT_SOFT;
                    min-height: 48px;
                    margin: 2px 0px;
                    padding: 6px 10px;
                }

                QWidget#AchievementsView QListWidget#QuestResultList::item:hover {
                    background: @PANEL_HOVER;
                    border-color: @BORDER_STRONG;
                }

                QWidget#AchievementsView QListWidget#QuestResultList::item:selected {
                    background: @PANEL_ACTIVE;
                    border: 1px solid @GREEN_BORDER;
                    border-left: 3px solid @GREEN;
                }

                /* Only the scroll/content canvas is opaque. The stacked
                   detail shell keeps the same glass as the two siblings. */
                QWidget#AchievementsView QScrollArea#GuideRightPanelScroll,
                QWidget#AchievementsView QWidget#AchievementDetailContent {
                    background: @PANEL;
                }

                QWidget#AchievementsView QStackedWidget#AchievementDetailStack > QWidget {
                    background: transparent;
                }

                QWidget#AchievementsView QScrollArea#GuideRightPanelScroll {
                    border: none;
                    border-radius: @RADIUS_MD;
                }

                QWidget#AchievementsView QFrame#AchievementDetailBody {
                    background: transparent;
                    border: none;
                }

                QWidget#AchievementsView QFrame#AchievementAlignmentPanel {
                    background: @PANEL_2;
                    border: 1px solid @BORDER_SOFT;
                    border-radius: @RADIUS_SM;
                }

                QWidget#AchievementsView QLabel#AchievementDetailTitle {
                    color: @TEXT;
                    font-size: 18px;
                    font-weight: 800;
                    padding: 0px 0px 2px 0px;
                }

                QWidget#AchievementsView QLabel#AchievementDescription {
                    color: @TEXT_SOFT;
                    font-size: @FONT_BODY;
                    padding: 0px 0px 2px 0px;
                }

                QWidget#AchievementsView QLabel#AchievementProgressText {
                    color: @TEXT_MUTED;
                    font-size: @FONT_SMALL;
                    font-weight: 700;
                }

                QWidget#AchievementsView QLabel#AchievementSectionTitle {
                    color: @YELLOW;
                    font-size: @FONT_SMALL;
                    font-weight: 800;
                    padding: 5px 1px 1px 1px;
                }

                QWidget#AchievementsView QCheckBox#AchievementDoneCheck {
                    color: @TEXT_SOFT;
                    font-weight: 700;
                    spacing: 7px;
                }

                QWidget#AchievementsView QCheckBox#AchievementDoneCheck:checked {
                    color: @GREEN;
                }

                QWidget#AchievementsView QFrame#EntityLinksPanel {
                    background: transparent;
                    border: none;
                    border-radius: 0px;
                }

                QWidget#AchievementsView QFrame#AchievementEntityRow,
                QWidget#AchievementsView QFrame#ObjectiveRow {
                    background: @PANEL_2;
                    border: 1px solid @BORDER_SOFT;
                    border-radius: @RADIUS_SM;
                }

                QWidget#AchievementsView QFrame#AchievementEntityRow:hover,
                QWidget#AchievementsView QFrame#ObjectiveRow:hover {
                    background: @PANEL_HOVER;
                    border-color: @GREEN_BORDER;
                }

                QWidget#AchievementsView QLabel#AchievementEntityRowText {
                    color: @TEXT_SOFT;
                }

                QWidget#AchievementsView QLabel#AchievementEntityChevron {
                    color: @TEXT_MUTED;
                    font-size: 18px;
                    font-weight: 700;
                }

                QWidget#AchievementsView QFrame#AchievementEntityRow:hover QLabel#AchievementEntityChevron {
                    color: @GREEN;
                }

                QWidget#AchievementsView QProgressBar#EncyclopediaProgressBar {
                    background: @BG;
                    border: 1px solid @BORDER_SOFT;
                    border-radius: @RADIUS_XS;
                    min-height: 8px;
                    max-height: 8px;
                }

                QWidget#AchievementsView QProgressBar#EncyclopediaProgressBar::chunk {
                    background: @GREEN;
                    border-radius: 3px;
                }

                QWidget#AchievementsView QSplitter#AchievementCatalogSplitter::handle {
                    background: transparent;
                    width: 6px;
                }


/* Guides catalogue and shared quest-detail primitives. */

            /* Guide root hosts reveal the shared Unity sky. */
            QWidget#GuidesHomePage,
            QWidget#GuidesHomeContent,
            QWidget#GuidesDetailPage,
            QWidget#GuideLeftPanelContent,
            QWidget#GuideCenterPanelContent,
            QWidget#GuideRightPanelContent {
                background: transparent;
            }

            /* One material for the Dev UI gallery and actual Guide panels. */
            QFrame#GuideHeader,
            QFrame#GuideBreadcrumb,
            QFrame#GuidesHomeCategory,
            QFrame#GuidesHomeProgressionColumn,
            QFrame#GuideLeftPanel,
            QFrame#GuideCenterPanel,
            QFrame#GuideRightPanel,
            QFrame#GuidesHomeSubCategory {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 @GLASS_PANEL_TOP,stop:1 @GLASS_PANEL_BOTTOM);
                border: 1px solid @BORDER_SOFT;
                border-top: 1px solid @GLASS_HAIRLINE;
                border-radius: @RADIUS_MD;
            }

            QFrame#GuidesHomeSeparator {
                background: @BORDER;
                border: none;
            }

            QFrame#GuideAdventureCard,
            QFrame#GuideAlignmentCard,
            QFrame#GuideDofusCard,
            QFrame#GuideQuestLine,
            QFrame#GuideQuestLineActive,
            QFrame#GuideQuestLineUnavailable,
            QFrame#GuideTreeRow,
            QFrame#GuideTreeRowActive,
            QFrame#GuideSeriesSummaryRow {
                background: @GLASS_BUTTON;
                border: 1px solid @BORDER_SOFT;
                border-radius: @RADIUS_SM;
            }

            QFrame#GuideAdventureCard:hover,
            QFrame#GuideAlignmentCard:hover,
            QFrame#GuideDofusCard:hover,
            QFrame#GuideQuestLine:hover,
            QFrame#GuideTreeRow:hover,
            QFrame#GuideSeriesSummaryRow:hover {
                background: @GLASS_HOVER;
                border-color: @GREEN_BORDER;
            }

            QFrame#GuideDofusCard[state="done"] {
                border-color: @GREEN_BORDER;
            }

            QFrame#GuideQuestLineActive,
            QFrame#GuideTreeRowActive {
                background: @GLASS_HOVER;
                border-color: @GREEN_BORDER;
                border-bottom: 2px solid @GREEN;
            }

            QFrame#GuideQuestLineUnavailable {
                background: @GLASS_PANEL_BOTTOM;
                border-color: @BORDER_SOFT;
            }

            QFrame#GuideQuestLine[state="done"],
            QFrame#GuideQuestLineActive[state="done"],
            QFrame#GuideTreeRow[state="done"],
            QFrame#GuideTreeRowActive[state="done"] {
                background: @GLASS_PANEL_BOTTOM;
                border-color: @BORDER_SOFT;
            }

            QLabel#GuideQuestLineTitle[state="done"],
            QLabel#GuideTreePartText[state="done"],
            QLabel#GuideTreeChildText[state="done"] {
                color: @TEXT_DISABLED;
            }

            QToolButton#GuideTreeStateButton {
                background: transparent;
                border: 1px solid @BORDER;
                border-radius: 5px;
                color: @TEXT_MUTED;
                font-size: @FONT_BODY;
                font-weight: 800;
                padding: 0px;
            }

            QToolButton#GuideTreeStateButton:hover {
                background: @PANEL_HOVER;
                border-color: @GREEN;
                color: @TEXT;
            }

            QToolButton#GuideTreeStateButton[state="done"] {
                color: @TEXT_DISABLED;
                border-color: @BORDER_STRONG;
            }

            QLabel#GuidesHomeCategoryTitle,
            QLabel#GuideHeaderTitle,
            QLabel#GuideSeriesHeaderTitle {
                color: @TEXT;
                font-weight: 800;
            }

            QLabel#GuidesHomeCategoryTitle {
                color: @YELLOW;
                font-size: @FONT_BODY;
                letter-spacing: 0px;
            }

            QLabel#GuideHeaderTitle {
                font-size: 19px;
            }

            QLabel#GuideHeaderMeta {
                color: @TEXT_SOFT;
                font-size: @FONT_BODY;
            }

            QLabel#GuideHeaderProgress {
                color: @YELLOW;
                font-size: 15px;
                font-weight: 800;
                padding: 4px 8px;
                border: 1px solid @BORDER_STRONG;
                border-radius: @RADIUS_SM;
                background: @PANEL_2;
            }

            QLabel#GuideInfoSectionTitle {
                color: @TEXT_SOFT;
                font-size: @FONT_SMALL;
                font-weight: 800;
            }

            QLabel#GuideHomeCardTitle,
            QLabel#GuideDofusCardTitle,
            QLabel#GuideTreePartText,
            QLabel#GuideSeriesHeaderTitle,
            QLabel#QuestSolutionStepTitle {
                color: @TEXT;
                font-size: 13px;
                font-weight: 750;
            }

            QLabel#GuideDofusCardTitle {
                font-size: @FONT_BODY;
            }

            QLabel#GuideTreeChildText,
            QLabel#GuideQuestLineTitle,
            QLabel#GuideInfoLine,
            QLabel#QuestSolutionDescription,
            QLabel#GuideActivityText {
                color: @TEXT_SOFT;
                font-size: @FONT_BODY;
            }

            QLabel#GuideHomeCardMeta,
            QLabel#GuideHomeProgress,
            QLabel#GuideQuestLevel,
            QLabel#GuideDofusProgress,
            QLabel#GuideSeriesHeaderProgress,
            QLabel#GuideSeriesSummaryTitle,
            QLabel#GuideSeriesSummaryProgress,
            QLabel#GuideProgressText,
            QLabel#GuideItemQuantity,
            QLabel#GuideTreeProgress,
            QLabel#GuideInfoKey,
            QLabel#GuideInfoValue,
            QLabel#GuideBreadcrumbSeparator,
            QLabel#GuideBreadcrumbCurrent,
            QLabel#MutedLabel,
            QLabel#GuidesHomeEmptyText {
                color: @TEXT_MUTED;
                font-size: @FONT_SMALL;
            }

            QLabel#GuideBreadcrumbCurrentStrong {
                color: @TEXT_SOFT;
                font-size: @FONT_SMALL;
                font-weight: 700;
            }

            QLabel#GuideQuestNumber {
                color: @GREEN;
                font-size: @FONT_BODY;
                font-weight: 800;
            }

            QLabel#GuideTreeState {
                color: @TEXT_DISABLED;
                font-size: 13px;
                font-weight: 800;
            }

            QLabel#GuideTreeState[state="done"],
            QLabel#GuideTreeProgress[state="done"],
            QLabel#GuideHomeProgress[state="done"],
            QLabel#GuideDofusProgress[state="done"],
            QLabel#GuideSeriesHeaderProgress[state="done"] {
                color: @GREEN;
            }

            QLabel#GuideTreeState[state="partial"],
            QLabel#GuideTreeProgress[state="partial"],
            QLabel#GuideHomeProgress[state="partial"],
            QLabel#GuideDofusProgress[state="partial"],
            QLabel#GuideSeriesHeaderProgress[state="partial"] {
                color: @YELLOW;
            }

            QLabel#GuideHeaderImage,
            QLabel#GuideAdventureImage,
            QLabel#GuideAlignmentImage,
            QLabel#GuideDofusImage {
                /* Original alpha-bearing Unity icons must not inherit
                   a solid dark rectangle behind their transparent pixels. */
                background: transparent;
                border: 1px solid @BORDER_SOFT;
                border-radius: @RADIUS_SM;
                color: @YELLOW;
            }

            QFrame#GuideSeriesHeader {
                background: transparent;
                border: none;
            }

            QFrame#GuideInfoRow,
            QFrame#GuideIconRow,
            QFrame#GuideItemRow,
            QFrame#GuideRewardRow,
            QFrame#GuideQuestItemRow,
            QFrame#GuideStepsHeader,
            QFrame#GuidePrerequisiteRow,
            QFrame#GuideProgressSummary,
            QFrame#GuideActivityGrid,
            QWidget#GuideCollapsibleBody {
                background: transparent;
                border: none;
            }

            QFrame#GuideInfoSection,
            QFrame#QuestSolutionStep {
                background: transparent;
                border-top: 1px solid @BORDER_SOFT;
                border-left: none;
                border-right: none;
                border-bottom: none;
                border-radius: 0px;
            }

            QFrame#GuideActivityChip {
                background: @GLASS_BUTTON;
                border: 1px solid @BORDER_SOFT;
                border-radius: @RADIUS_XS;
            }

            QFrame#GuideStepsCollapsedRail {
                background: @GLASS_PANEL_BOTTOM;
                border: none;
                border-radius: @RADIUS_XS;
            }

            QFrame#QuestObjectiveLine:hover,
            QFrame#GuideCollapsibleHeader:hover {
                background: @PANEL_HOVER;
            }

            QToolButton#GuideChevronButton,
            QToolButton#GuideLineIcon,
            QToolButton#GuideLineActivity,
            QToolButton#GuideInfoIcon,
            QToolButton#GuideItemIcon,
            QLabel#GuideInfoIcon,
            QLabel#GuideItemIcon {
                background: transparent;
                border: none;
                padding: 0px;
            }

            QToolButton#GuideQuestState,
            QToolButton#GuideStepsCollapseButton,
            QToolButton#GuideHeaderDoneButton,
            QToolButton#QuestGlobalDoneButton {
                background: transparent;
                border: 1px solid @BORDER;
                border-radius: 5px;
                color: @TEXT_MUTED;
                font-size: @FONT_BODY;
                font-weight: 800;
                padding: 0px 6px;
            }

            QToolButton#GuideQuestState:hover,
            QToolButton#GuideStepsCollapseButton:hover,
            QToolButton#GuideHeaderDoneButton:hover,
            QToolButton#QuestGlobalDoneButton:hover {
                background: @PANEL_HOVER;
                border-color: @GREEN;
                color: @TEXT;
            }

            QToolButton#GuideQuestState[state="done"],
            QToolButton#GuideHeaderDoneButton[state="done"],
            QToolButton#QuestGlobalDoneButton[state="done"] {
                color: @GREEN;
                border-color: @GREEN_BORDER;
            }

            QToolButton#GuideHeaderDoneButton,
            QToolButton#QuestGlobalDoneButton {
                min-height: 26px;
                max-height: 26px;
            }

            QPushButton#GuideInlineQuestButton,
            QPushButton#GuideInlineAchievementButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: @RADIUS_XS;
                color: @TEXT_SOFT;
                font-size: @FONT_SMALL;
                font-weight: 600;
                text-decoration: underline;
                min-height: 22px;
                max-height: 22px;
                padding: 0px @SPACE_LG;
                text-align: left;
            }

            QPushButton#GuideInlineQuestButton:hover,
            QPushButton#GuideInlineAchievementButton:hover {
                color: @GREEN;
            }

            QPushButton#GuideInlineQuestButton:focus,
            QPushButton#GuideInlineAchievementButton:focus {
                border-color: @BORDER_STRONG;
            }

            QPushButton#GuideInlineQuestButton:disabled,
            QPushButton#GuideInlineAchievementButton:disabled {
                color: @TEXT_DISABLED;
            }

            QPushButton#GuideItemNameButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: @RADIUS_XS;
                /* Item is the global entity-link category GREEN, not a local gray. */
                color: @GREEN;
                font-size: @FONT_SMALL;
                font-weight: 700;
                min-height: 22px;
                max-height: 22px;
                padding: 0px 8px;
                text-align: left;
            }

            QPushButton#GuideItemNameButton:hover {
                background: @PANEL_HOVER;
                border-color: @GREEN_BORDER;
                color: @GREEN_HOVER;
            }

            QPushButton#GuideItemNameButton {
                padding-left: 2px;
                padding-right: 2px;
            }

            QLabel#GuideItemQuantity {
                color: @TEXT_MUTED;
                font-size: @FONT_SMALL;
                font-weight: 700;
            }

            QCheckBox#GuideInventoryCheck {
                color: @TEXT_MUTED;
                font-size: 10px;
                padding-left: 2px;
            }

            QScrollArea#GuideDofusGridScroll,
            QScrollArea#GuideLeftPanelScroll,
            QScrollArea#GuideCenterPanelScroll,
            QScrollArea#GuideRightPanelScroll {
                background: transparent;
                border: none;
            }

            QWidget#GuideDofusGridContent {
                background: transparent;
            }

            QSplitter#GuideDetailSplitter::handle {
                background: @BORDER_SOFT;
            }

            QProgressBar#GuideTinyProgress {
                background: @BG;
                border: 1px solid @BORDER;
                border-radius: 3px;
            }

            QProgressBar#GuideTinyProgress::chunk {
                background: @GREEN;
                border-radius: 2px;
            }

            QProgressBar#GuideDofusHomeBar {
                background: @BG;
                border: 1px solid @BORDER;
                border-radius: 2px;
            }

            QProgressBar#GuideDofusHomeBar::chunk {
                background: @GREEN_DARK;
                border-radius: 2px;
            }

            QProgressBar#GuideDofusHomeBar[state="done"]::chunk {
                background: @GREEN;
            }

            QFrame#GuidesHomeEmpty {
                background: @GLASS_BUTTON;
                border: 1px dashed @BORDER_SOFT;
                border-radius: @RADIUS_MD;
            }

            QLabel#GuideStepsVerticalText {
                color: @TEXT_MUTED;
                font-size: 10px;
                font-weight: 800;
            }

            /* Scrollbars inherit the single global Unity QSS above.
               Never override their shared colors and dimensions from Guides. */


/* Quest hierarchy and reusable guide/quest item states. */

QTreeWidget#QuestHierarchyTree {
    /* Inherit the same list canvas as the rest of the app, not the window BG. */
    background: @LIST_SURFACE;
    border: none;
    color: @TEXT_MUTED;
    outline: none;
}
QTreeWidget#QuestHierarchyTree::item {
    min-height: 24px;
    padding: 1px 3px;
}
QTreeWidget#QuestHierarchyTree::item:hover {
    background: @PANEL_HOVER;
}
QTreeWidget#QuestHierarchyTree::item:selected {
    background: @PANEL_ACTIVE;
    color: @TEXT;
}

/* Guide category tree uses the same Unity semantic roles as other
   Encyclopedia navigation trees; only its compact geometry is specific. */
/* Section headings are one shared role, with unchanged typography. */
QLabel#GuideLibrarySectionTitle {
    color: @TEXT;
    font-size: 13px;
    font-weight: 800;
}

QTreeWidget#GuideLibraryCategories {
    background: @PANEL_2;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_MD;
    padding: 3px;
    color: @TEXT_SOFT;
    outline: none;
}
QTreeWidget#GuideLibraryCategories::item {
    min-height: 23px;
    padding: 2px 5px;
    border-radius: @RADIUS_XS;
    border-left: 2px solid transparent;
}
QTreeWidget#GuideLibraryCategories::item:hover {
    background: @PANEL_HOVER;
}
QTreeWidget#GuideLibraryCategories::item:selected {
    background: @PANEL_ACTIVE;
    color: @TEXT;
    border-left: 2px solid @GREEN;
}



QFrame#GuideItemRow[state="done"],
QFrame#GuideQuestItemRow[state="done"],
QFrame#QuestItemRow[state="done"] {
    background: @PANEL_ACTIVE;
    border: 1px solid @GREEN_BORDER;
    border-radius: @RADIUS_XS;
}
QToolButton#GuideItemIcon[state="todo"] {
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
}
QToolButton#GuideItemIcon[state="done"] {
    background: @PANEL_ACTIVE;
    border: 1px solid @GREEN;
    border-radius: @RADIUS_XS;
}


/* Quest launch coordinates use the same legible Unity emphasis as
   linked /travel coordinates. The source text and navigation stay untouched. */
QLabel#QuestLaunchPosition {
    color: @TEXT;
    font-size: @FONT_BODY;
    font-weight: 800;
    background: transparent;
    border: none;
}

/* One semantic Unity control for Guide and Quêtes information rails. */
QToolButton#GuideRightPanelToggle {
    background: @PANEL_2;
    color: @TEXT_SOFT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
    min-width: @CONTROL_HEIGHT_COMPACT;
    min-height: @CONTROL_HEIGHT_COMPACT;
}
QToolButton#GuideRightPanelToggle:hover,
QToolButton#GuideRightPanelToggle:focus {
    background: @PANEL_HOVER;
    color: @TEXT;
    border-color: @GREEN_BORDER;
}
QToolButton#GuideRightPanelToggle:pressed,
QToolButton#GuideRightPanelToggle[collapsed="true"] {
    background: @PANEL_ACTIVE;
    border-color: @GREEN_BORDER;
}
QToolButton#GuideRightPanelToggle:disabled {
    color: @TEXT_DISABLED;
    border-color: @BORDER_SOFT;
}

/* Guide Ultime variants. */

QFrame#GuideBreadcrumb {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 @GLASS_PANEL_TOP, stop:1 @GLASS_PANEL_BOTTOM);
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
}

QPushButton#GuideBreadcrumbButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: @RADIUS_XS;
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
    font-weight: 700;
    min-height: 22px;
    max-height: 22px;
    padding: 0px @SPACE_MD;
    text-align: left;
}

QPushButton#GuideBreadcrumbButton:hover {
    background: @PANEL_HOVER;
    border-color: @GREEN_BORDER;
    color: @TEXT;
}

QLabel#GuideBreadcrumbSeparator,
QLabel#GuideBreadcrumbCurrent {
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
}
QLabel#GuideBreadcrumbCurrent {
    color: @GREEN;
    font-weight: 700;
}

#GuideManualProgressFrame {
    background: transparent;
    border: none;
}

/* Shared guide reading surface: glass inside a visible four-sided border. */
QScrollArea#GuideManualScroll {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 @GLASS_PANEL_TOP,stop:1 @GLASS_PANEL_BOTTOM);
    border: 1px solid @BORDER_CARD;
    border-radius: @RADIUS_MD;
}
QWidget#GuideManualContent,
QWidget#SharedGuideManualView,
QScrollArea#GuideManualScroll > QWidget#qt_scrollarea_viewport {
    background: transparent;
}

#GuideManualProgress {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: 3px;
}

#GuideManualProgress::chunk {
    background: @RED;
    border-radius: 2px;
}

#GuideManualPercent {
    color: @TEXT_SOFT;
    font-size: @FONT_BODY;
    font-weight: 700;
}

QToolButton#GuideManualProgressLock {
    background: transparent;
    color: @TEXT_SOFT;
    border: 1px solid transparent;
    border-radius: @RADIUS_XS;
    padding: 0 7px;
    font-size: @FONT_SMALL;
    font-weight: 700;
}

QToolButton#GuideManualProgressLock:hover {
    background: @PANEL_HOVER;
    border-color: @BORDER_SOFT;
}

QToolButton#GuideManualProgressLock[state="locked"] {
    color: @TEXT;
}

QFrame#GuideCompactHeader,
QFrame#GuidePreparationPanel,
QFrame[guideMetricDrawer="true"],
QFrame#GuideSheetHeader,
QFrame#GuideManualNav {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 @GLASS_PANEL_TOP,stop:1 @GLASS_PANEL_BOTTOM);
    border: 1px solid @BORDER_SOFT;
    border-top: 1px solid @GLASS_HAIRLINE;
    border-radius: @RADIUS_MD;
}

/* The expanded body is part of the same parent progress surface. */
QFrame#GuideGlobalDetailsPanel {
    background: transparent;
    border: none;
}

/* Group all three progress meters without another opaque layer of glass. */
QFrame#GuideHeaderProgressGroup {
    background: transparent;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
}

/* Shared Ganymede preparation tabs: blue glass, semantic border/text. */
QFrame#GuidePreparationFilterHost {
    background: transparent;
    border: none;
}

QPushButton#GuidePreparationModeTab,
QPushButton#GuidePreparationFilter {
    background: @PANEL_2;
    color: @BORDER;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
    padding: @SPACE_XS @SPACE_MD;
    font-weight: 700;
}

QPushButton#GuidePreparationModeTab:hover,
QPushButton#GuidePreparationModeTab:checked,
QPushButton#GuidePreparationFilter:hover,
QPushButton#GuidePreparationFilter:checked {
    background: @PANEL_ACTIVE;
    border-color: @GREEN_BORDER;
    color: @GREEN_BORDER;
}

QLabel#GuideCompactTitle {
    color: @TEXT;
    font-size: 15px;
    font-weight: 800;
}

QLabel#GuideCompactDonutHeading {
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
    font-weight: 700;
}

QLabel#GuideCompactDonutCount {
    color: @TEXT_SOFT;
    font-size: @FONT_SMALL;
    font-weight: 700;
}

QLabel#GuideCompactMetricValue,
QLabel#GuideSheetMeta,
QLabel#GuidePreparationParticipantNeed,
QLabel#GuidePreparationEmpty,
QLabel#GuideParticipantsEmpty {
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
}

QLabel#GuideCompactMetricValue {
    min-width: 52px;
}

QProgressBar#GuideCompactSummaryProgress,
QProgressBar#GuideCompactPreparationProgress {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: 3px;
}

QProgressBar#GuideCompactSummaryProgress::chunk,
QProgressBar#GuideCompactPreparationProgress::chunk {
    background: @GREEN;
    border-radius: 2px;
}

QToolButton#GuideCompactSettingsButton,
QToolButton#GuideCompactOverlayButton,
QToolButton#GuideParticipantsButton,
QToolButton#GuideSummaryButton,
QToolButton#GuidePreparationDetailsButton {
    background: transparent;
    color: @TEXT_SOFT;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
    padding: 4px 7px;
    font-weight: 700;
}

QToolButton#GuideCompactSettingsButton:hover,
QToolButton#GuideParticipantsButton:hover,
QToolButton#GuideSummaryButton:hover,
QToolButton#GuidePreparationDetailsButton:hover,
QToolButton#GuideParticipantsButton:checked,
QToolButton#GuideSummaryButton:checked {
    background: @PANEL_HOVER;
    border-color: @GREEN_BORDER;
    color: @TEXT;
}

QToolButton#GuideCompactOverlayButton:disabled {
    color: @TEXT_MUTED;
    border-color: @BORDER_SOFT;
}

QFrame#GuideCompactSettingsPanel,
QFrame#GuideSummaryPanel,
QFrame#GuidePreparationDetails {
    background: @GUIDE_SUMMARY_BOTTOM;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_MD;
}

/* The participant row sits inside the glass Guide header already.
   A second gray/opaque slab here hides the Unity gradient behind portraits. */
QFrame#GuideParticipantsPanel {
    background: transparent;
    border: none;
}

/* The arrow complements its progress bar; it is not a replacement bar. */
QProgressBar#GuideGlobalProgress {
    background: @NAV_SURFACE;
    border: 1px solid @BORDER_SOFT;
    border-radius: 4px;
}
QProgressBar#GuideGlobalProgress::chunk {
    background: @GREEN;
    border-radius: 3px;
}
QLabel#GuideGlobalProgressTitle {
    color: @TEXT_SOFT;
    font-size: @FONT_SMALL;
    font-weight: 600;
    background: transparent;
    border-left: 2px solid @GREEN_BORDER;
    padding-left: 7px;
}
/* Inline Route/Preparation chevrons: small invisible hit target at rest. */
QToolButton#GuideMetricDropdown {
    background: transparent;
    border: 1px solid transparent;
    border-radius: @RADIUS_XS;
    padding: 0;
    /* The 1px borders on each side are included in the 18px control. */
    min-width: 16px;
    max-width: 16px;
    min-height: 16px;
    max-height: 16px;
}
QToolButton#GuideMetricDropdown:hover,
QToolButton#GuideMetricDropdown:checked {
    background: @GLASS_HOVER;
    border-color: @GUIDE_TOGGLE_BORDER;
}
QToolButton#GuideMetricDropdown:disabled {
    background: transparent;
    border: 1px solid transparent;
}
QToolButton#GuideParticipantsButton {
    /* Keep the transparent Unity sprite, but restore the shared visible
       outline on the title-row character selector in every idle state. */
    background: transparent;
    border: 1px solid @GUIDE_TOGGLE_BORDER;
    border-radius: @RADIUS_XS;
    padding: 0;
}
QToolButton#GuideParticipantsButton:hover,
QToolButton#GuideParticipantsButton:focus,
QToolButton#GuideParticipantsButton:checked {
    background: @GLASS_HOVER;
    border-color: @GREEN_BORDER;
}
QToolButton#GuideParticipantsButton:disabled {
    background: transparent;
    border-color: @BORDER_SOFT;
}

/* Shared Guide navigation never falls back to a black native button. */
QPushButton#GuideManualGuideButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 @GUIDE_TOGGLE_TOP,stop:1 @GUIDE_TOGGLE_BOTTOM);
    border: 1px solid @GUIDE_TOGGLE_BORDER;
    border-radius: @RADIUS_XS;
    color: @TEXT;
    padding: 3px 8px;
    font-weight: 700;
}
QPushButton#GuideManualGuideButton:hover {
    background: @GUIDE_TOGGLE_HOVER;
    border-color: @GUIDE_TOGGLE_ACTIVE_BORDER;
}
QPushButton#GuideManualGuideButton:pressed {
    background: @GUIDE_TOGGLE_ACTIVE;
}

/* Guide menus, selection surfaces and counters share the Unity roles. */
QSpinBox#GuideCompactPageJump,
QSpinBox#GuidePreparationQuantity {
    background: @PANEL_2;
    color: @TEXT;
    border: 1px solid @GUIDE_TOGGLE_BORDER;
    border-radius: @RADIUS_XS;
    padding: 3px 4px;
    min-height: 22px;
}
/* This selector gets 6px more left inset than the shared 4px field default.
   Qt positions the native line editor using its parent spinbox padding.
   The shared width-fitting helper reserves the same extra 6px. */
QSpinBox#GuideCompactPageJump {
    padding-left: @SPACE_LG;
}
/* QSpinBox contains a native line editor; its global QLineEdit palette
   must not paint a separate near-black inset over the indexed surface. */
QSpinBox#GuideCompactPageJump QLineEdit,
QSpinBox#GuidePreparationQuantity QLineEdit {
    background: transparent;
    color: @TEXT;
    border: none;
    padding: 0;
}
QSpinBox#GuideCompactPageJump:focus,
QSpinBox#GuidePreparationQuantity:focus {
    border-color: @GREEN_BORDER;
}
QSpinBox#GuideCompactPageJump::up-button,
QSpinBox#GuideCompactPageJump::down-button {
    background: @GLASS_BUTTON;
    border-left: 1px solid @GUIDE_TOGGLE_BORDER;
    width: 17px;
}
QSpinBox#GuideCompactPageJump::up-button:hover,
QSpinBox#GuideCompactPageJump::down-button:hover {
    background: @GLASS_HOVER;
    border-left-color: @GREEN_BORDER;
}
QSpinBox#GuidePreparationQuantity {
    font-size: @FONT_SMALL;
    padding: 1px 2px;
}

QSpinBox#GuidePreparationQuantity::up-button,
QSpinBox#GuidePreparationQuantity::down-button {
    background: @PANEL_HOVER;
    border-left: 1px solid @BORDER_SOFT;
    width: 16px;
}
QListWidget#GuideSummaryList::item {
    background: transparent;
    color: @TEXT_SOFT;
    padding: 5px 8px;
}
QListWidget#GuideSummaryList::item:hover {
    background: @PANEL_HOVER;
    color: @TEXT;
}
QListWidget#GuideSummaryList::item:selected {
    background: @PANEL_ACTIVE;
    border-left: 2px solid @GREEN_BORDER;
    color: @GREEN_BORDER;
}

QToolButton#GuidePreparationToggle {
    background: @GLASS_BUTTON;
    color: @TEXT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
    padding: 7px 10px;
    font-weight: 800;
    text-align: left;
}

QToolButton#GuidePreparationToggle:hover,
QToolButton#GuidePreparationToggle:checked {
    background: @PANEL_HOVER;
    border-color: @GREEN_BORDER;
}

QFrame#GuidePreparationSummary,
QFrame#GuidePreparationRow {
    background: @GUIDE_PREPARATION_ROW;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
}

QFrame#GuidePreparationRow[ready="true"] {
    border-color: @GREEN_BORDER;
}

/* Shared Guide preparation typographic roles, also shown in Dev UI. */
QLabel#GuidePreparationSummaryTitle {
    color: @GUIDE_PREPARATION_TEXT;
    font-size: @FONT_SMALL;
    font-weight: 800;
}
QLabel#GuidePreparationSummaryCount,
QLabel#GuidePreparationRowStatus {
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
}
QLabel#GuidePreparationRowStatus[ready="true"] {
    color: @GREEN;
    font-weight: 700;
}

/* The preparation viewport must not paint native gray over the Unity panel. */
QScrollArea#GuidePreparationScroll,
QScrollArea#GuideHeaderSectionScroll,
QScrollArea#GuideHeaderSectionScroll > QWidget#qt_scrollarea_viewport,
QWidget#GuideHeaderSectionHost,
QWidget#GuideGlobalCharacterProgress,
QWidget#GuidePreparationContent,
QScrollArea#GuidePreparationScroll > QWidget#qt_scrollarea_viewport {
    background: transparent;
    border: none;
}
QLabel#GuidePreparationQuantityPlaceholder {
    background: transparent;
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
}
QPushButton#GuidePreparationItemCopy {
    background: transparent;
    color: @GREEN;
    border: 1px solid transparent;
    border-radius: @RADIUS_XS;
    padding: 0px 3px;
    font-size: @FONT_SMALL;
    font-weight: 700;
    text-align: left;
}
QPushButton#GuidePreparationItemCopy:hover,
QPushButton#GuidePreparationItemCopy:focus {
    background: @PANEL_HOVER;
    border-color: @GREEN_BORDER;
    color: @GREEN_BORDER;
}

QLabel#GuidePreparationRowLabel {
    color: @TEXT_SOFT;
    font-size: @FONT_BODY;
}

QToolButton#GuidePreparationDetailsButton {
    padding: 1px 2px;
    min-width: 16px;
    max-width: 20px;
}

QPushButton#GuidePreparationShowMore {
    padding: 1px @SPACE_SM;
    font-size: @FONT_SMALL;
    color: @TEXT_SOFT;
}

QCheckBox#GuidePreparationReady {
    background: transparent;
    color: @GREEN_BORDER;
    spacing: 0;
}
QCheckBox#GuidePreparationReady::indicator {
    width: 17px;
    height: 17px;
    border: 1px solid @GUIDE_TOGGLE_BORDER;
    border-radius: @RADIUS_XS;
    background: transparent;
}
QCheckBox#GuidePreparationReady::indicator:hover {
    border-color: @GREEN_BORDER;
    background: @PANEL_HOVER;
}
QCheckBox#GuidePreparationReady::indicator:checked {
    background: @GREEN;
    border-color: @GREEN;
}

QLabel#GuideSheetTitle {
    color: @TEXT;
    font-size: 15px;
    font-weight: 800;
}

QLineEdit#GuideSummarySearch {
    background: @FIELD_SURFACE;
    color: @TEXT;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
    selection-background-color: @PANEL_ACTIVE;
    selection-color: @TEXT;
}

QListWidget#GuideSummaryList,
QListWidget#GuideSummaryList > QWidget#qt_scrollarea_viewport {
    background: transparent;
    color: @TEXT;
    border: none;
    selection-background-color: @PANEL_ACTIVE;
    selection-color: @TEXT;
}

QToolButton#GuideParticipantPortrait {
    background: @PANEL;
    border: 1px solid @BORDER_SOFT;
    border-radius: 21px;
    padding: 4px;
}

QToolButton#GuideParticipantPortrait:hover,
QToolButton#GuideParticipantPortrait:checked {
    background: @PANEL_ACTIVE;
    border-color: @GREEN;
}

#GuideManualOrderChoice {
    background: @PANEL;
    border: 1px solid @GREEN_BORDER;
    border-radius: @RADIUS_XS;
}

#GuideManualOrderTitle {
    color: @TEXT;
    font-size: 15px;
    font-weight: 800;
}

#GuideManualOrderDetail {
    color: @TEXT_MUTED;
    font-size: @FONT_BODY;
}

#GuideManualOrderButton {
    background: @PANEL_HOVER;
    color: @TEXT_SOFT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
    padding: 7px 10px;
    font-weight: 700;
}

#GuideManualOrderButton:hover {
    border-color: @GREEN_BORDER;
    color: @TEXT;
}

#GuideManualActionSection,
#GuideManualResourceSection,
#GuideManualDungeonSection,
#GuideManualWarningSection {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 @GLASS_SECTION_TOP,stop:1 @GLASS_SECTION_BOTTOM);
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
}

#GuideManualResourceSection {
    border-color: @GREEN_BORDER;
}

/* Shared roadbook containers: one Unity material for every Guide reader. */
QFrame#GuideManualCombatSection,
QFrame#GuideManualCombatLineRow,
QFrame#GuideManualCombatInlineRow {
    background: @GLASS_SUBTLE_SURFACE;
    border: 1px solid @GLASS_SUBTLE_BORDER;
    border-radius: @RADIUS_XS;
}

QFrame#GuideManualCombatSection {
    border-radius: @RADIUS_SM;
}

QFrame#GuideManualLineRow,
QFrame#GuideManualActionGroup {
    background: transparent;
    border: none;
}

QLabel#GuideManualCombatInlineText {
    background: transparent;
    border: none;
    padding: 5px 7px;
}

QFrame#GuideManualWarningSection QLabel#GuideManualLine {
    background: transparent;
    border: none;
    padding: @SPACE_XXS 0;
}

#GuideManualDungeonSection {
    border-color: @RED_DARK;
}

#GuideManualWarningSection {
    background: @DANGER_PANEL;
    border-color: @RED_DARK;
}

#GuideManualSectionTitle {
    color: @GUIDE_PREPARATION_TEXT;
    font-size: @FONT_BODY;
    font-weight: 800;
}

QFrame#GuideManualResourceSection QLabel#GuideManualSectionTitle {
    color: @GREEN;
}
QFrame#GuideManualCombatSection QLabel#GuideManualSectionTitle,
QFrame#GuideManualWarningSection QLabel#GuideManualSectionTitle,
QLabel#GuideManualCombatTargetsTitle {
    color: @DANGER_TEXT;
    font-weight: 800;
}

#GuideManualLegendCard {
    background: @GLASS_HOVER;
    border: 1px solid @GREEN_BORDER;
    border-radius: @RADIUS_XS;
}

#GuideManualLegendTitle {
    color: @TEXT;
    font-size: 16px;
    font-weight: 800;
}

#GuideManualLegendText {
    color: @TEXT_SOFT;
    font-size: 13px;
    padding: 2px 0;
}

#GuideManualNavPage {
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
    font-weight: 700;
    padding: 0 8px;
}

#GuideManualSheet {
    background: transparent;
    border: none;
}

#GuideManualStageTitle {
    color: @TEXT;
    font-size: 17px;
    font-weight: 800;
}

/* Shared local-image viewer: Quest and Guide reuse the same Qt label.
   No opaque card/background should appear behind PNG or WebP artwork. */
QLabel#QuestSolutionImage {
    color: @TEXT_SOFT;
    background: transparent;
    border: none;
}

#GuideManualLocation {
    color: @TEXT;
    font-size: 14px;
    font-weight: 800;
}

#GuideManualLine {
    color: @TEXT_SOFT;
    font-size: 14px;
    padding: 3px 0;
}

#GuideManualWarning {
    color: @DANGER_TEXT;
    background: @DANGER_PANEL;
    border: 1px solid @RED_DARK;
    border-radius: @RADIUS_XS;
    font-size: 14px;
    font-weight: 800;
    padding: 8px 10px;
}

#GuideManualCombat {
    color: @TEXT;
    background: @PANEL_2;
    border: 1px solid @RED_DARK;
    border-radius: @RADIUS_XS;
    font-size: 14px;
    font-weight: 700;
    padding: 8px 10px;
}

#GuideManualSpecial {
    color: @TEXT;
    background: @PANEL_HOVER;
    border: 1px solid @GREEN_BORDER;
    border-radius: @RADIUS_XS;
    font-size: 14px;
    font-weight: 700;
    padding: 8px 10px;
}

#GuideManualCombatCheck {
    color: @DANGER_TEXT;
    background: transparent;
    border: none;
    spacing: 8px;
    font-size: 14px;
    font-weight: 700;
}

#GuideManualCombatCheck[state="done"] {
    color: @GREEN;
}

#GuideManualCombatCheck::indicator {
    width: 16px;
    height: 16px;
}

/* No extra validation animation: checked state changes text and outline only.
   All colors and geometry stay owned by the shared Unity Dev UI tokens. */
QToolButton#GuideContinuousValidate {
    background: transparent;
    color: @TEXT_SOFT;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
}
QToolButton#GuideContinuousValidate:checked {
    color: @GREEN;
    border-color: @GREEN_BORDER;
}

#GuideManualPageCheck {
    color: @TEXT_SOFT;
    background: @GLASS_BUTTON;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
    padding: 5px 12px;
    spacing: 9px;
    font-size: @FONT_BODY;
    font-weight: 700;
}

#GuideManualPageCheck:hover:!disabled {
    background: @GLASS_HOVER;
    border-color: @GREEN_BORDER;
}
#GuideManualPageCheck:disabled {
    color: @TEXT_MUTED;
}

#GuideManualPageCheck:checked,
#GuideManualPageCheck:checked:disabled {
    color: @GREEN;
    border-color: @GREEN_BORDER;
}

#GuideManualPageCheck::indicator {
    width: 16px;
    height: 16px;
}

#GuideManualPrev,
#GuideManualNextButton {
    background: @GLASS_BUTTON;
    color: @TEXT_SOFT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
    padding: 5px 12px;
    font-weight: 700;
}

#GuideManualPrev:hover,
#GuideManualNextButton:hover {
    border-color: @GREEN_BORDER;
    color: @TEXT;
}

#GuideRouteHeader,
#GuideUltimeRouteSheet {
    background: @PANEL;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
}

#GuideUltimeRouteSheet[state="active"] {
    background: @PANEL;
    border-color: @GREEN_BORDER;
}

#GuideRouteTitle {
    color: @TEXT;
    font-size: 16px;
    font-weight: 800;
}

#GuideRoutePercent {
    color: @GREEN;
    font-size: 14px;
    font-weight: 800;
}

#GuideRouteProgress {
    background: @PANEL_2;
    border: none;
    border-radius: 3px;
}

#GuideRouteProgress::chunk {
    background: @GREEN;
    border-radius: 3px;
}

#GuideRouteInlineOrder {
    background: @PANEL;
    border: 1px solid @GREEN_BORDER;
    border-radius: @RADIUS_XS;
    color: @TEXT_SOFT;
}

#GuideRouteNav {
    background: transparent;
    border: none;
}

#GuideRouteLocation {
    color: @TEXT;
    font-size: 19px;
    font-weight: 800;
}

#GuideUltimeSectionTitle {
    font-size: 14px;
}

#GuideRouteAction,
#GuideRouteNext,
#GuideRouteImportant {
    color: @TEXT_SOFT;
    font-size: 14px;
}

#GuideRouteImportant {
    color: @TEXT;
    font-weight: 700;
}

#GuideRouteAction[state="done"] {
    color: @TEXT_DISABLED;
}

#GuideRouteNext {
    color: @TEXT;
    font-weight: 700;
    margin-top: 8px;
}

#GuideRoutePageCheck {
    color: @TEXT;
    background: @PANEL_2;
    border: 1px solid @GREEN_BORDER;
    border-radius: @RADIUS_XS;
    padding: 10px 14px;
    spacing: 10px;
    font-size: 14px;
    font-weight: 800;
}

#GuideRoutePageCheck:disabled {
    color: @GREEN;
}

#GuideRoutePageCheck::indicator {
    width: 19px;
    height: 19px;
}

/* Guide Ultime buttons keep their domain layout below. Its combo boxes
   inherit the same native dropdown rules as Succès, Quêtes and Personnage. */

#GuideRouteCurrent {
    color: @GREEN;
    font-weight: 750;
}

QLabel[travelCopyEnabled="true"] {
    color: @GREEN;
}

QLabel[travelCopyEnabled="true"]:hover {
    text-decoration: underline;
}


#GuideUltimeGeneratedView {
    background: @BG;
}

#GuideUltimeProgressHeader {
    background: @PANEL;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
}

#GuideUltimeTitle {
    color: @TEXT;
    font-size: 18px;
    font-weight: 800;
}

#GuideUltimeProgressText {
    color: @GREEN;
    font-weight: 800;
    font-size: 14px;
}

#GuideUltimeProgressDetails,
#GuideUltimeBranchStatus,
#GuideUltimePosition {
    color: @TEXT_MUTED;
}

#GuideUltimeProgressBar {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
}

#GuideUltimeProgressBar::chunk {
    background: @GREEN;
    border-radius: 3px;
}

#GuideUltimeNav {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
}

#GuideUltimeCard {
    background: @PANEL;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_SM;
}

#GuideUltimeCard[state="active"] {
    border: 1px solid @GREEN_BORDER;
    background: @PANEL_ACTIVE;
}

#GuideUltimeCard[state="done"] {
    background: @PANEL_2;
    border-color: @BORDER_SOFT;
}

#GuideUltimeCardLevel {
    color: @TEXT;
    font-weight: 800;
}

#GuideUltimeCardLocation,
#GuideUltimeCompactSummary {
    color: @TEXT_MUTED;
}

#GuideUltimeSectionTitle {
    color: @GREEN;
    font-weight: 800;
    margin-top: 4px;
}

#GuideUltimeDoneBadge {
    color: @TEXT_DISABLED;
    font-weight: 700;
}

#GuideUltimeActiveBadge {
    color: @GREEN;
    font-weight: 800;
}

#GuideUltimeInfoLine,
#GuideUltimeNextLine {
    color: @TEXT_SOFT;
}

#GuideUltimeInfoLine[state="done"] {
    color: @TEXT_DISABLED;
}

#GuideUltimeGeneratedView QCheckBox {
    color: @TEXT_SOFT;
    spacing: 8px;
}

#GuideUltimeGeneratedView QCheckBox[state="done"] {
    color: @TEXT_DISABLED;
}

#GuideUltimeGeneratedView QCheckBox::indicator {
    width: 16px;
    height: 16px;
}

#GuideUltimeGeneratedView QPushButton,
#GuideUltimeGeneratedView QToolButton {
    background: @PANEL_HOVER;
    color: @TEXT_SOFT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
    padding: 4px 8px;
}

#GuideUltimeGeneratedView QPushButton:hover,
#GuideUltimeGeneratedView QToolButton:hover {
    border-color: @GREEN_BORDER;
}



"""


# The scoped Organizer CSS is part of the same global Qt stylesheet, never
# a local page override. It keeps all approved geometry and effects.
_STYLE_TEMPLATE += "\n" + ORGANIZER_STYLE_TEMPLATE


def _soft_alpha(color: str, alpha: str) -> str:
    """Generate a light QSS tint from the current Unity semantic color.

    Unsupported override formats pass through unchanged rather than breaking
    previews; the canonical PANEL_HOVER/BORDER_SOFT values are #RRGGBB.
    """
    value = str(color)
    if len(value) == 7 and value.startswith("#"):
        try:
            channels = tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))
        except ValueError:
            pass
        else:
            return f"rgba({channels[0]}, {channels[1]}, {channels[2]}, {alpha})"
    return value


def _render_theme_template(
    template: str,
    overrides: Mapping[str, str] | None = None,
) -> str:
    """Render any application/module QSS through the shared semantic tokens."""

    tokens = dict(THEME_TOKENS)
    if overrides:
        unknown = sorted(set(overrides) - set(tokens))
        if unknown:
            raise KeyError(f"Unknown theme token(s): {', '.join(unknown)}")
        tokens.update({key: str(value) for key, value in overrides.items()})
    # Guide-compatible aliases must follow the shared source *after* palette
    # overrides. Explicit legacy Guide overrides remain supported.
    for alias, role in UNITY_COLOR_ALIAS_ROLES.items():
        if not overrides or alias not in overrides:
            tokens[alias] = tokens[role]
    # Derived translucent roles track palette overrides automatically. A
    # subtle glass treatment must not become a second hard-coded gray palette.
    tokens["GLASS_SUBTLE_SURFACE"] = _soft_alpha(tokens["PANEL_HOVER"], "0.05")
    tokens["GLASS_SUBTLE_BORDER"] = _soft_alpha(tokens["BORDER_SOFT"], "0.18")
    # Small optical glint (16% edge), not a full iOS-style backdrop blur.
    # Blue-panel opacity remains high: stars are not smeared or washed out.
    tokens["GLASS_HAIRLINE"] = _soft_alpha(
        tokens["TEXT_SOFT"], f"{UNITY_GLASS_INTENSITY:.2f}"
    )
    tokens["GLASS_PANEL_TOP"] = _soft_alpha(tokens["PANEL_2"], "0.82")
    tokens["GLASS_PANEL_BOTTOM"] = _soft_alpha(tokens["PANEL"], "0.88")
    # Translucent Unity section styling is shared outside the Dev UI gallery.
    tokens["GLASS_SECTION_TOP"] = tokens["GLASS_PANEL_TOP"]
    tokens["GLASS_SECTION_BOTTOM"] = tokens["GLASS_PANEL_BOTTOM"]
    # The exact same Unity glass gradient is consumed by Organizer and the
    # global stylesheet. All three derive from canonical theme overrides.
    tokens["GLASS_BUTTON"] = unity_glass_gradient(palette=tokens)
    tokens["GLASS_HOVER"] = unity_glass_gradient(
        "PANEL_HOVER", "PANEL_ACTIVE",
        top_alpha=199, bottom_alpha=206, palette=tokens,
    )
    tokens["GLASS_GREEN"] = unity_glass_gradient(
        "GREEN_DARK", "GREEN_DARK",
        top_alpha=196, bottom_alpha=218, palette=tokens,
    )
    style = str(template)
    for literal, role in LEGACY_COLOR_ROLES.items():
        token = f"@{role}"
        style = style.replace(literal, token).replace(literal.lower(), token)
    for literal, replacement in LEGACY_LITERAL_ALIASES.items():
        style = style.replace(literal, replacement)
    for key in sorted(tokens, key=len, reverse=True):
        style = style.replace(f"@{key}", tokens[key])
    return style


@lru_cache(maxsize=192)
def _render_static_theme_template(template: str) -> str:
    return _render_theme_template(template)


def render_theme_template(
    template: str,
    overrides: Mapping[str, str] | None = None,
) -> str:
    """Render QSS, caching immutable templates while validating overrides."""

    if overrides:
        return _render_theme_template(template, overrides)
    return _render_static_theme_template(str(template))


def clear_theme_cache() -> None:
    _render_static_theme_template.cache_clear()


def atlas_stylesheet(overrides: Mapping[str, str] | None = None) -> str:
    """Render the application stylesheet from one shared token map.

    ``overrides`` is intentionally small and optional; it lets previews and
    future theme variants change the whole application without rewriting QSS.
    """

    style = render_theme_template(_STYLE_TEMPLATE, overrides)
    if not overrides:
        return style + "\n" + unity_skin_stylesheet()
    # Preview variants must use the same tokens in the Unity widget layer.
    # The regular stylesheet still shares the original cached path.
    return style + "\n" + unity_skin_stylesheet(overrides)
