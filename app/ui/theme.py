from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache


# Shared visual language: the home page's near-black surfaces, olive accent and
# warm neutral text. Keep semantic names here so modules do not grow parallel
# palettes while adopting the same navigation, cards and interaction hierarchy.
PALETTE = {
    "BG": "#050A0D",
    "SIDEBAR": "#071012",
    "PANEL": "#081113",
    "PANEL_2": "#091214",
    "PANEL_HOVER": "#0B1714",
    "PANEL_ACTIVE": "#0D2118",
    "BORDER": "#26332D",
    "BORDER_SOFT": "#1C2925",
    "BORDER_STRONG": "#344434",
    "TEXT": "#F5F7F2",
    "TEXT_SOFT": "#E8ECE8",
    "TEXT_MUTED": "#AEB7B1",
    "TEXT_DISABLED": "#6F7968",
    "GREEN": "#9FC528",
    "GREEN_HOVER": "#5C7E1B",
    "GREEN_DARK": "#4B6816",
    "GREEN_BORDER": "#6F941E",
    "RED": "#D71920",
    "RED_HOVER": "#EF2028",
    "RED_DARK": "#9F1016",
    "YELLOW": "#D6B22D",
    "DANGER_PANEL": "#2A1118",
    "DANGER_TEXT": "#FFD6D9",
    "BADGE_BG": "#2A2B11",
    "BADGE_BORDER": "#7D8424",
    "BADGE_TEXT": "#C9D44C",
    "SHELL_GRADIENT": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #071012, stop:1 #050A0D)",
    "PANEL_GRADIENT": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #091214, stop:1 #081113)",
    "ACTIVE_GRADIENT": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5C7E1B, stop:1 #4B6816)",
}

TYPOGRAPHY = {
    "FONT_FAMILY": '"Segoe UI", Arial',
    "FONT_BODY": "12px",
    "FONT_SMALL": "11px",
    "FONT_TITLE": "18px",
}

SPACING = {
    "SPACE_XXS": "2px",
    "SPACE_XS": "4px",
    "SPACE_SM": "6px",
    "SPACE_MD": "8px",
    "SPACE_LG": "10px",
    "SPACE_XL": "14px",
    "SPACE_2XL": "20px",
    "SPACE_3XL": "24px",
}

SIZES = {
    "RADIUS_XS": "4px",
    "RADIUS_SM": "6px",
    "RADIUS_MD": "8px",
    "RADIUS_LG": "10px",
    "CONTROL_HEIGHT_COMPACT": "24px",
    "CONTROL_HEIGHT": "32px",
    "TOP_NAV_HEIGHT": "58px",
}

THEME_TOKENS = {**PALETTE, **TYPOGRAPHY, **SPACING, **SIZES}

# Transitional aliases let existing module selectors preserve their layout
# while their rendered colors already follow the home-page palette. New QSS
# should use semantic @TOKENS directly; aliases can then shrink over time.
LEGACY_COLOR_ROLES = {
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

#sidebar, #SideNav {
    background: @SIDEBAR;
    border-right: 1px solid @BORDER_SOFT;
}

#burgerButton, #MenuButton {
    background: @PANEL_2;
    border: 1px solid @BORDER;
    border-radius: 6px;
    color: @TEXT;
    font-size: 17px;
    font-weight: 700;
    padding: 0px;
}

#burgerButton:hover, #MenuButton:hover {
    background: @PANEL_2;
    border-color: @BORDER;
}

#burgerButton:pressed, #MenuButton:pressed {
    background: @GREEN_DARK;
    border-color: @GREEN;
}

#navItem, #navItemActive, #NavButton, #ActiveNavButton,
#TopmostButton, #TopmostButtonActive {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: @TEXT;
    font-size: 13px;
    font-weight: 600;
    padding: 0px 9px;
    text-align: left;
    min-height: 38px;
    max-height: 38px;
}

#navItem:hover, #NavButton:hover, #TopmostButton:hover {
    background: @PANEL;
    border-color: @BORDER_SOFT;
}

#navItemActive, #ActiveNavButton, #TopmostButtonActive {
    background: @GREEN_DARK;
    border: 1px solid @GREEN;
    border-left: 4px solid @GREEN;
    color: @TEXT;
    font-weight: 800;
    padding-left: 6px;
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

#organizerPage, #worldScanPage, #OrganizerPage, #QuestsPage, #EncyclopediaPage {
    background: @BG;
}

#PageTitle {
    color: @TEXT;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 0px;
    padding: 0px;
    border: none;
}

QTabWidget#EncyclopediaTabs::pane {
    background: @BG;
    border: none;
    top: -1px;
}

QTabWidget#EncyclopediaTabs QTabBar::tab {
    background: @PANEL;
    border: 1px solid @BORDER;
    border-bottom-color: @BORDER_SOFT;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: @TEXT_MUTED;
    font-size: 11px;
    font-weight: 700;
    min-height: 28px;
    padding: 0px 7px;
}

QTabWidget#EncyclopediaTabs QTabBar::tab:selected {
    background: #101E2F;
    border-color: @GREEN;
    border-bottom: 2px solid @GREEN;
    color: @TEXT;
}

QTabWidget#EncyclopediaTabs QTabBar[guideActive="true"]::tab:selected {
    background: @PANEL_2;
    border-color: @GREEN;
    border-bottom: 2px solid @GREEN;
    color: @TEXT;
}

QTabWidget#EncyclopediaTabs QTabBar::tab:hover {
    background: @PANEL_2;
    border-color: @BORDER;
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

#AchievementsView, #AchievementFilterPanel {
    background: @BG;
}

#AchievementsView #GuideLeftPanel,
#AchievementsView #GuideCenterPanel {
    background: @PANEL;
    border: 1px solid @BORDER;
    border-radius: 8px;
}

QTreeWidget#AchievementCategoryTree,
#AchievementsView QListWidget#QuestResultList {
    background: @BG;
    border: none;
    color: @TEXT_MUTED;
    outline: none;
}

QTreeWidget#AchievementCategoryTree::item,
#AchievementsView QListWidget#QuestResultList::item {
    min-height: 25px;
    padding: 2px 5px;
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
#GuideProgressHeader, #GuideSectionWidget,
#GuideStepWidget, #GuideStepActive, #AchievementContextDetail,
#AchievementSummaryWidget, #AchievementRewardWidget, #GuideCompletedSeriesLabel {
    background: @PANEL;
    border: 1px solid @BORDER;
    border-radius: 8px;
}

#CategoryProgressCard, #RewardCard, #ObjectiveRow, #GuideStepWidget,
#AchievementContextDetail, #AchievementSummaryWidget, #AchievementRewardWidget {
    background: @PANEL_2;
    border-color: @BORDER_SOFT;
}

#GuideStepActive {
    background: @PANEL_2;
    border: 1px solid @YELLOW;
}

#GuideStepStatus {
    color: @YELLOW;
    font-size: 10px;
    font-weight: 800;
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
    border-radius: 6px;
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
    font-size: 11px;
    padding: 7px 9px;
}

#EncyclopediaThreePanelDashboard::handle {
    background: @BORDER_SOFT;
}

#CompactScroll, #CompactScrollContent {
    background: transparent;
    border: none;
}

#RequiredItemRow, #ActivitySummary {
    background: transparent;
    border: none;
}

#StatusBadge, #ActivityBadge {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: 5px;
    color: @TEXT;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
}

#StatusBadge[state="done"] {
    color: @GREEN;
    border-color: @GREEN_DARK;
}

#StatusBadge[state="blocked"] {
    color: @TEXT_MUTED;
}

#StatusBadge[state="active"] {
    color: @YELLOW;
    border-color: @YELLOW;
}

#GuideManualStepCheck {
    color: @TEXT;
    font-size: 11px;
}

#EncyclopediaResultList, #GuideResultList {
    background: @PANEL_2;
    border: 1px solid @BORDER;
    border-radius: 6px;
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
    background: @GREEN_DARK;
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
    border-color: @GREEN;
    background: @GREEN_DARK;
}

#AchievementEntityRow {
    background: transparent;
    border: 1px solid @BORDER_SOFT;
    border-radius: 6px;
}

#AchievementEntityRow:hover,
#ObjectiveRow:hover {
    border-color: @GREEN;
    background: @GREEN_DARK;
}

#AchievementEntityRowText {
    color: @TEXT;
}

#EncyclopediaProgressBar {
    background: @SIDEBAR;
    border: 1px solid @BORDER_SOFT;
    border-radius: 4px;
    height: 7px;
}

#EncyclopediaProgressBar::chunk {
    background: @YELLOW;
    border-radius: 3px;
}

#TitleAccent {
    background: @GREEN;
    border-radius: 2px;
}

#card, #OrganizerPanel, #Panel, #CraftPanel, #QuestPanel {
    background: @PANEL;
    border: 1px solid @BORDER;
    border-radius: 8px;
}

#DialogToolbar {
    background: transparent;
    border: none;
}

#cardTitle, #ControlSectionTitle, #PanelTitle {
    color: @TEXT;
    font-size: 14px;
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
    font-size: 12px;
    padding: 0px;
}

#WarningLabel {
    color: @YELLOW;
    font-size: 11px;
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

QPushButton:hover, QToolButton:hover {
    background: @PANEL_HOVER;
    border-color: @BORDER_STRONG;
}

QPushButton:pressed, QToolButton:pressed {
    background: @GREEN_DARK;
    border-color: @GREEN;
}

QPushButton:disabled, QToolButton:disabled {
    background: @PANEL;
    border-color: @BORDER_SOFT;
    color: @TEXT_DISABLED;
}

#primaryButton, #ActiveButton, #PrimaryActionButton {
    background: @ACTIVE_GRADIENT;
    border-color: @GREEN_BORDER;
    color: @TEXT;
    font-size: 11px;
    font-weight: 800;
    text-align: left;
    padding-left: 10px;
    padding-right: 8px;
}

#primaryButton:hover, #ActiveButton:hover, #PrimaryActionButton:hover {
    background: @GREEN_HOVER;
    border-color: @GREEN;
    color: @TEXT;
}

#secondaryButton, #SecondaryButton {
    background: @PANEL_2;
    border-color: @BORDER;
    color: @TEXT_SOFT;
    font-size: 11px;
    font-weight: 600;
    text-align: left;
    padding-left: 10px;
    padding-right: 8px;
}

#secondaryButton:hover, #SecondaryButton:hover {
    background: @PANEL_HOVER;
    border-color: @BORDER_STRONG;
    color: @TEXT;
}

#GuideHideCompletedToggle {
    background: @PANEL_2;
    border-color: @BORDER;
    color: #D7E0EE;
    font-size: 11px;
    font-weight: 600;
    text-align: left;
    padding-left: 10px;
    padding-right: 8px;
}

#GuideHideCompletedToggle:hover {
    background: #16263A;
    border-color: #334761;
    color: @TEXT;
}

#GuideHideCompletedToggle:checked {
    background: @GREEN_DARK;
    border-color: @GREEN;
    color: @TEXT;
}

#GuideHideCompletedToggle:checked:hover {
    background: @GREEN_HOVER;
    border-color: @GREEN_HOVER;
    color: @TEXT;
}

#dangerButton, #DangerButton {
    background: @RED;
    border-color: #F0444B;
    color: @TEXT;
    font-size: 12px;
    font-weight: 700;
    text-align: center;
    padding-left: 8px;
    padding-right: 8px;
}

#dangerButton:hover, #DangerButton:hover {
    background: @RED_HOVER;
    border-color: #FF6167;
}

#dangerButton:pressed, #DangerButton:pressed {
    background: @RED_DARK;
    border-color: @RED;
}

#segmentedButton, #segmentedButtonActive {
    background: @PANEL_2;
    border: 1px solid @BORDER;
    color: #D7E0EE;
    font-weight: 600;
    text-align: center;
    padding: 0px 8px;
}

#segmentedButton:hover {
    background: #16263A;
    border-color: #334761;
}

#segmentedButtonActive {
    background: @GREEN_DARK;
    border-color: @GREEN;
    color: @TEXT;
    font-weight: 700;
}

#keyBadge, #InlineShortcutButton {
    background: #09121F;
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
    background: #122139;
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
    border-radius: 6px;
    color: @TEXT;
    font-size: 14px;
    font-weight: 800;
    padding: 0px;
    text-align: center;
}

#iconButton:hover, #ClientMenuButton:hover {
    background: #16263A;
    border-color: #334761;
    color: @TEXT;
}

#iconButtonDanger, #ShortcutClear {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    color: #D6DFEB;
    font-size: 10px;
    font-weight: 800;
    padding: 0px;
    text-align: center;
}

#iconButtonDanger:hover, #ShortcutClear:hover {
    background: #2A1118;
    border-color: @RED;
    color: #FFD6D9;
}

#GhostButton {
    background: #0A121D;
    border-style: dashed;
    border-color: @BORDER;
    color: #64748B;
}

#GhostTile {
    background: @PANEL_2;
    border: 1px dashed @BORDER;
    border-radius: 6px;
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
    background: #16263A;
    border-color: #344B66;
}

#characterSlotEmpty, #EmptySessionSlot {
    background: #09111D;
    border: 1px solid @BORDER_SOFT;
    border-radius: 7px;
    margin: 0px;
}

#characterSlotEmpty:hover, #EmptySessionSlot:hover {
    background: #0D1827;
    border-color: #2A3A51;
}

#characterSlotMissing, #MissingSessionRow {
    background: #0A1320;
    border: 1px solid @BORDER_SOFT;
    border-radius: 7px;
    margin: 0px;
}

#characterSlotMissing:hover, #MissingSessionRow:hover {
    background: #101C2B;
    border-color: #344B66;
}

#characterSlotDragging, #DraggingListRow {
    background: #0A4F32;
    border: 1px solid @GREEN;
    border-radius: 7px;
    margin: 0px;
}

#characterSlotDropTarget, #DropTargetListRow {
    background: #10243A;
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
    background: #0A121D;
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
    background: #0A121D;
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
    border-radius: 6px;
    padding: 4px;
}

#ZaapSuggestionPopup::item, QListWidget::item {
    color: #DCE5F2;
    padding: 5px 8px;
    min-height: 25px;
    border-radius: 4px;
    border-bottom: 1px solid @BORDER_SOFT;
}

#ZaapSuggestionPopup::item:selected, #ZaapSuggestionPopup::item:hover,
QListWidget::item:selected {
    background: @GREEN_DARK;
    color: @TEXT;
}

#ZaapFavoritesRow {
    background: transparent;
}

#favoriteChip, #ZaapFavoriteChip {
    background: #0A121D;
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
    font-size: 12px;
    font-weight: 800;
}

#favoriteChip:hover, #ZaapFavoriteChip:hover,
#favoriteChipStar:hover, #ZaapFavoriteStar:hover {
    background: #10301F;
    border-color: @GREEN;
    color: @TEXT;
}

#favoriteChipName, #ZaapFavoriteName {
    background: transparent;
    color: #DCE5F2;
    border: none;
    border-radius: 0px;
    padding: 0px;
    font-size: 11px;
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
    border-color: #10B981;
    text-align: center;
    padding: 0px;
    font-size: 8px;
    min-width: 52px;
    min-height: 38px;
}

#SelectionRow {
    background: @PANEL_2;
    border-radius: 6px;
}

#WorldDetailValue {
    background: #09121F;
    border: 1px solid @BORDER_SOFT;
    border-radius: 5px;
    color: @TEXT;
    font-size: 11px;
    padding: 4px 6px;
    min-height: 18px;
}

#MapToolbar, #MapCanvas, #WorldDetailPanel {
    background: @PANEL;
    border: 1px solid @BORDER;
    border-radius: 8px;
}

#MapToolbar {
    background: @PANEL;
}

#WorldDetailPanel {
    background: @PANEL;
}

#WorldDetailTitle {
    color: @TEXT;
    font-size: 13px;
    font-weight: 800;
}

#WorldScanProgress {
    color: #DCE5F2;
    font-size: 12px;
    font-weight: 750;
}

#WorldCacheState {
    color: @TEXT_MUTED;
    font-size: 11px;
    font-weight: 650;
}

#BreadcrumbLabel {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: 6px;
    color: @TEXT_MUTED;
    font-size: 11px;
    font-weight: 700;
    padding: 0px 10px;
}

#WorldPlanetButton {
    background: #0B7F3D;
    border: 1px solid @GREEN;
    border-radius: 30px;
    padding: 0px;
}

#WorldPlanetButton:hover {
    background: @GREEN_HOVER;
    border-color: @GREEN_HOVER;
}

#WorldPlanetButton:pressed {
    background: @GREEN_DARK;
    border-color: @GREEN;
}

#WorldMenu {
    background: #0A121D;
    border: 1px solid @BORDER;
    border-radius: 8px;
}

#WorldMenuScroll, #WorldMenuContents {
    background: transparent;
    border: none;
}

#WorldMenuScroll QScrollBar:vertical {
    background: #08111D;
    border: none;
    border-radius: 4px;
    margin: 4px 0px 4px 0px;
    width: 8px;
}

#WorldMenuScroll QScrollBar::handle:vertical {
    background: #2A3A51;
    border-radius: 4px;
    min-height: 36px;
}

#WorldMenuScroll QScrollBar::handle:vertical:hover {
    background: #334B66;
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
    border-radius: 6px;
    color: #DCE5F2;
    font-size: 12px;
    font-weight: 650;
    padding: 0px 10px;
    text-align: left;
}

#WorldMenuItem:hover {
    background: #16263A;
    border-color: #334761;
}

#WorldMenuItemActive {
    background: @GREEN_DARK;
    border-color: @GREEN;
    color: @TEXT;
    font-weight: 800;
}

#MapViewTree {
    background: @PANEL;
    border: none;
    color: @TEXT;
    outline: 0;
}

#MapViewTree::item {
    min-height: 28px;
    border-radius: 6px;
    padding: 0px 7px;
    color: #DCE5F2;
}

#MapViewTree::item:hover {
    background: #16263A;
}

#MapViewTree::item:selected {
    background: @GREEN_DARK;
    color: @TEXT;
    border: 1px solid @GREEN;
}

#MapDetailValue {
    background: #09121F;
    border: 1px solid @BORDER_SOFT;
    border-radius: 6px;
    color: @TEXT;
    font-size: 11px;
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
    background: #13243A;
    border: 1px solid @BORDER;
}

#LevelBadge {
    background: #09121F;
    border: 1px solid @BORDER;
    border-radius: 4px;
    color: @GREEN;
    font-size: 11px;
    font-weight: 800;
    padding: 2px 6px;
}

QScrollBar:horizontal {
    height: 0px;
    background: transparent;
}

QScrollBar:vertical {
    background: @PANEL;
    width: 8px;
    margin: 1px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #344863;
    min-height: 26px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #49617F;
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
    min-height: 40px;
    max-height: 40px;
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
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: @RADIUS_XS;
    color: @TEXT;
    font-size: 12px;
    font-weight: 700;
    padding: 0px 8px;
    min-height: 40px;
    max-height: 40px;
}

#TopNavButton:hover {
    background: @PANEL_2;
    border-bottom-color: @BORDER;
}

#TopNavButtonActive {
    background: @PANEL_ACTIVE;
    border-bottom-color: @GREEN;
    color: @TEXT;
}

#TopNavCharacterCombo {
    background: @PANEL_2;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
    color: @TEXT;
    min-height: 38px;
    max-height: 38px;
    padding: 0px 9px;
    font-size: 12px;
    font-weight: 700;
}

#TopNavCharacterCombo:hover,
#TopNavCharacterCombo:focus {
    border-color: @GREEN;
    background: @PANEL_HOVER;
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
    background: @PANEL_2;
    color: @TEXT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
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

#HomePage {
    background: @BG;
}

#HomeLeftColumn {
    background: transparent;
    border: none;
}

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

#HomeCharacterCard {
    background: @PANEL_GRADIENT;
}

#HomeTrackingCard {
    background: @PANEL_GRADIENT;
}

#HomeGuideCard {
    background: @PANEL_GRADIENT;
    border-color: @BORDER_STRONG;
}

#HomeAlmanaxCard {
    background: @PANEL_GRADIENT;
}

#HomeNetworkMiniCard {
    background: @PANEL_GRADIENT;
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
    font-size: 12px;
    font-weight: 700;
}

#HomeNetworkMiniStatus {
    color: @TEXT_MUTED;
    font-size: 11px;
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
    background: @ACTIVE_GRADIENT;
    border: 1px solid @GREEN_BORDER;
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
#HomeContinueButton:hover {
    background: @GREEN_HOVER;
    border-color: @GREEN;
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
    font-size: 11px;
    font-weight: 600;
}

#HomeTrackingValue {
    color: @TEXT_SOFT;
    font-size: 11px;
    font-weight: 700;
}

#HomeTrackingBar {
    background: @PANEL_HOVER;
    border: none;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
}

#HomeTrackingBar::chunk {
    background: @GREEN_DARK;
    border-radius: 4px;
}

#HomeAlmanaxPlaceholderIcon {
    background: transparent;
    border: none;
    border-radius: 75px;
    padding: 4px;
}

#HomePlaceholderBadge {
    background: #2A2B11;
    border: 1px solid #7D8424;
    border-radius: 5px;
    color: #C9D44C;
    font-size: 11px;
    font-weight: 900;
    padding: 4px 10px;
}

#HomeAlmanaxText {
    color: #D7DDD8;
    font-size: 14px;
    font-weight: 500;
    padding: 8px 10px;
}

#SettingsPage,
#PlaceholderPage {
    background: @BG;
}

"""


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

    return render_theme_template(_STYLE_TEMPLATE, overrides)
