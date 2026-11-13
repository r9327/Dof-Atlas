"""Single Unity visual system for Atlas, with local optional graphic assets.

Game-extracted image and font files stay outside the public Windows release.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFontDatabase, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget


_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "themes" / "dofus_unity"
# A personal theme survives every transactional EXE update and is never
# part of the publicly downloadable runtime.
_PERSONAL_ASSETS = (
    Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    / "DofusAtlas" / "themes" / "dofus_unity"
)
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


def unity_enabled() -> bool:
    """The legacy Atlas presentation is retired; Unity is always active."""
    return True


def _asset_file(relative: Path) -> Path | None:
    """Prefer durable personal assets; keep existing DEV checkout behavior."""
    for root in (_PERSONAL_ASSETS, _ASSETS):
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def wallpaper_path() -> Path | None:
    """Never show original HUD icons; only use a locally cleaned background."""
    if not unity_enabled():
        return None
    return _asset_file(Path("background_selection_clean.png"))


def _sprite_url(filename: str) -> str | None:
    """Render from personal files first, without changing release packaging."""
    candidate = _asset_file(Path("sprites") / filename)
    return candidate.resolve().as_posix() if candidate else None


def sprite_icon_path(icon: str) -> Path | None:
    """Keep Atlas fallback icons if a personal Unity pictogram is absent."""
    if not unity_enabled() or icon not in {
        "guide", "quest", "success", "encyclopedia",
        "character", "dofus", "map", "inventory",
    }:
        return None
    filename = f"Assets_UI_Themes_Figma_menuIcons_1x_{icon}-png.png"
    return _asset_file(Path("sprites") / filename)


def register_unity_fonts() -> tuple[str, ...]:
    """Register local fonts only after QApplication exists; never package them."""
    if not unity_enabled():
        return ()
    families: list[str] = []
    for name in ("Lexend-Regular.ttf", "Lexend-Medium.ttf",
                 "Lexend-SemiBold.ttf", "Lexend-Bold.ttf", "Rowdies-Regular.ttf"):
        path = _asset_file(Path("fonts") / name)
        if path:
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id >= 0:
                families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return tuple(dict.fromkeys(families))


def apply_unity_panel_shadow(widget: QWidget, *, blur: int = 18, vertical: int = 4) -> None:
    """A real Qt shadow for a few fixed Guide panels, never list rows.

    Qt stylesheets cannot render box-shadow. This effect is intentionally
    reserved for lightweight, static panels to protect scrolling performance.
    """
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, vertical)
    effect.setColor(QColor(0, 0, 0, 195))
    widget.setGraphicsEffect(effect)


def unity_skin_stylesheet(palette: Mapping[str, str] | None = None) -> str:
    """Global Qt controls, with optional preview overrides for Unity tokens."""
    if not unity_enabled():
        return ""
    colors = UNITY_PALETTE if palette is None else {**UNITY_PALETTE, **palette}

    def translucent(role: str, alpha: float) -> str:
        """Keep current glass opacity while following live Unity color tokens."""
        color = QColor(colors[role])
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha:.2f})"

    rules = [
        # The wallpaper is painted once by the *parent* of all shell pages.
        # Only root surfaces are translucent; data cards retain dark contrast.
        "QWidget#AtlasUnityBackdrop { background: transparent; }",
        "QStackedWidget#AtlasUnityStack, QWidget#HomePage, "
        "QWidget#EncyclopediaPage, QWidget#organizerPage, "
        "QWidget#worldScanPage, QWidget#QuestsPage, "
        "QWidget#PlaceholderPage, QWidget#SettingsPage, "
        "QWidget[atlasUnityPage=\"true\"] { background: transparent; }",
        # The legacy Guides QSS names these roots explicitly and paints them
        # opaque. Higher-level atlasUnityPage cannot override ID selectors.
        "QWidget#GuidesView, QWidget#GuidesHomePage, "
        "QWidget#GuidesHomeContent, QWidget#GuideLibraryResults, "
        "QWidget#GuidesDetailPage, "
        "QWidget#GuideLeftPanelContent, QWidget#GuideCenterPanelContent, "
        "QWidget#GuideRightPanelContent { background: transparent; }",
        # Real guide panels remain legible, but they no longer blot out the sky.
        "QFrame#GuideHeader, QFrame#GuideBreadcrumb, "
        "QFrame#GuidesHomeCategory, QFrame#GuidesHomeProgressionColumn, "
        "QFrame#GuideLeftPanel, QFrame#GuideCenterPanel, "
        "QFrame#GuideRightPanel, QFrame#GuidesHomeSubCategory { "
        "background: %s; border: 1px solid %s; }" % (
            translucent("PANEL", 0.88), colors["BORDER"],
        ),
        "QListView#GuidesHomeDofusGrid { background: %s; }" %
        translucent("LIST_SURFACE", 0.45),
        "QScrollArea { background: %s; border: none; }" %
        translucent("SCROLL_SURFACE", 0.35),
        "QScrollArea > QWidget > QWidget { background: transparent; }",
        # Shared widget families, never changes their existing geometry or actions.
        "QGroupBox, QTabWidget::pane { "
        "background: %s; color: %s; "
        "border: 1px solid %s; border-radius: 6px; }" % (
            translucent("PANEL", 0.78), colors["TEXT"], colors["BORDER"],
        ),
        "QListView, QTreeView, QTableView, QListWidget, QTreeWidget, QTableWidget { "
        "background: %s; color: %s; "
        "alternate-background-color: %s; "
        "selection-background-color: %s; selection-color: %s; "
        "border: 1px solid %s; }" % (
            translucent("LIST_SURFACE", 0.92), colors["TEXT"],
            translucent("PANEL_2", 0.88), colors["PANEL_ACTIVE"],
            colors["TEXT"], colors["BORDER"],
        ),
        "QHeaderView::section { background: %s; "
        "color: %s; border: 1px solid %s; }" % (
            translucent("PANEL_2", 0.95), colors["TEXT"], colors["BORDER"],
        ),
        f"QTabBar::tab {{ background: {translucent('NAV_SURFACE', 0.93)}; "
        f"color: {colors['TEXT_SOFT']}; "
        f"border: 2px solid {colors['BORDER']}; }}",
        f"QTabBar::tab:hover {{ background: {colors['PANEL_HOVER']}; }}",
        f"QTabBar::tab:selected {{ color: {colors['TEXT']}; "
        f"background: {colors['PANEL_ACTIVE']}; }}",
        "QToolTip { background: %s; color: %s; "
        "border: 1px solid %s; padding: 4px; }" % (
            colors["TOOLTIP_SURFACE"], colors["TEXT"], colors["BORDER_STRONG"],
        ),
        "QProgressBar { background: %s; "
        "color: %s; border: 1px solid %s; "
        "text-align: center; }" % (
            translucent("LIST_SURFACE", 0.85), colors["TEXT"], colors["BORDER"],
        ),
        "QFrame#card, QFrame#HomeCharacterCard, QFrame#HomeTrackingCard, "
        "QFrame#HomeGuideCard, QFrame#HomeNetworkMiniCard, QFrame#HomeAlmanaxCard, "
        "QFrame#GuideFeaturedCard { "
        "background: %s; border: 1px solid %s; "
        "border-radius: 9px; }" % (
            translucent("PANEL", 0.88), colors["BORDER_CARD"],
        ),
        # Featured Guide cards are deliberately accented, but share the same
        # palette and selector ownership as every other Unity surface.
        "QFrame#GuideFeaturedCard { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, "
        "stop:0 %s, stop:1 %s); border: 1px solid %s; border-radius: 8px; }"
        % (colors["PANEL_ACTIVE"], colors["PANEL"], colors["GREEN_BORDER"]),
        "QFrame#GuideFeaturedCard:hover { background: %s; border: 1px solid %s; }"
        % (colors["PANEL_HOVER"], colors["GREEN_HOVER"]),
        "QFrame#GuideFeaturedCard:focus { border: 2px solid %s; }"
        % colors["GREEN_HOVER"],
        "QFrame#GuideFeaturedCard QLabel { border: 0; background: transparent; }",
        "QFrame#GuideFeaturedCard QLabel#GuideFeaturedTitle { "
        "color: %s; font-weight: 800; font-size: 12px; }" % colors["TEXT"],
        "QFrame#GuideFeaturedCard QLabel#FeaturedSubtitle { color: %s; }"
        % colors["TEXT_MUTED"],
        "QFrame#GuideFeaturedCard QProgressBar#GuideFeaturedProgress { "
        "border: 0; background: %s; border-radius: 4px; }" % colors["BORDER_SOFT"],
        "QFrame#GuideFeaturedCard QProgressBar#GuideFeaturedProgress::chunk { "
        "background: %s; border-radius: 4px; }" % colors["GREEN"],
        "QFrame#GuideCompactHeader, QFrame#GuideSheetHeader, "
        "QFrame#GuidePreparationPanel { "
        "background: %s; border: 1px solid %s; }" % (
            translucent("GUIDE_COMPACT_SURFACE", 0.93), colors["BORDER"],
        ),
        # Small bevels and stronger contrast for the real guide surfaces.
        # QSS has no native box-shadow; personal 9-slice sprites can supply
        # the game-native depth when installed.
        "QFrame#GuidePreparationSummary, QFrame#GuideManualWarningSection { "
        "background: qlineargradient(x1:0,y1:0,x2:0,y2:1, "
        "stop:0 %s, stop:1 %s); "
        "border: 1px solid %s; border-radius: 5px; color: %s; }" % (
            translucent("GUIDE_SUMMARY_TOP", 0.97),
            translucent("GUIDE_SUMMARY_BOTTOM", 0.97),
            colors["GUIDE_PREPARATION_BORDER"], colors["GUIDE_PREPARATION_TEXT"],
        ),
        "QFrame#GuidePreparationRow, QFrame#GuidePreparationDetails { "
        "background: %s; border: 1px solid %s; border-radius: 5px; }" % (
            translucent("GUIDE_PREPARATION_ROW", 0.92),
            translucent("GUIDE_PREPARATION_ROW_BORDER", 0.65),
        ),
        "QPushButton#GuidePreparationItemCopy { "
        "text-align: left; background: transparent; border: none; "
        "color: %s; padding: 3px; }" % colors["GUIDE_ITEM_TEXT"],
        "QPushButton#GuidePreparationItemCopy:hover { "
        "background: %s; border-radius: 4px; }" %
        translucent("GUIDE_COPY_HOVER", 0.30),
        "QLabel#GuidePreparationRowStatus, QLabel#GuidePreparationParticipantNeed { "
        "color: %s; font-weight: 600; }" % colors["GUIDE_STATUS_TEXT"],
        "QFrame#GuideManualNav { "
        "background: %s; border-top: 1px solid %s; }" % (
            translucent("GUIDE_MANUAL_NAV_SURFACE", 0.94),
            colors["GUIDE_NAV_BORDER"],
        ),
        "QToolButton#GuidePreparationToggle, QToolButton#GuideSummaryButton, "
        "QToolButton#GuideParticipantsButton { "
        "background: qlineargradient(x1:0,y1:0,x2:0,y2:1, "
        "stop:0 %s, stop:1 %s); "
        "color: %s; border: 1px solid %s; "
        "border-radius: 5px; padding: 3px 8px; }" % (
            colors["GUIDE_TOGGLE_TOP"], colors["GUIDE_TOGGLE_BOTTOM"],
            colors["GUIDE_PREPARATION_TEXT"], colors["GUIDE_TOGGLE_BORDER"],
        ),
        "QToolButton#GuidePreparationToggle:checked, QToolButton#GuideSummaryButton:checked, "
        "QToolButton#GuideParticipantsButton:checked { "
        "background: %s; border: 1px solid %s; }" % (
            colors["GUIDE_TOGGLE_ACTIVE"], colors["GUIDE_TOGGLE_ACTIVE_BORDER"],
        ),
        "QToolButton#GuidePreparationToggle:hover, QToolButton#GuideSummaryButton:hover, "
        "QToolButton#GuideParticipantsButton:hover { "
        "background: %s; }" % colors["GUIDE_TOGGLE_HOVER"],
        "QDialog#AtlasDialog, QMenu { "
        "background: %s; color: %s; "
        "border: 1px solid %s; }" % (
            translucent("NAV_SURFACE", 0.98), colors["TEXT"], colors["BORDER_CARD"],
        ),
        "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, "
        "QPlainTextEdit { "
        "background: %s; color: %s; "
        "border: 1px solid %s; }" % (
            translucent("FIELD_SURFACE", 0.96), colors["TEXT"], colors["BORDER_CARD"],
        ),
        # Focus must be appended AFTER all sprite rules to remain visible.
        "#PageTitle, #HomeGuideTitle, #TopNavBrandText { "
        'font-family: "Rowdies", "Lexend", "Segoe UI"; }',
    ]

    def add_border(selectors: str, image: str, insets: int = 8) -> None:
        url = _sprite_url(image)
        if url:
            rules.append(
                f"{selectors} {{ border: {insets}px solid transparent;"
                f' border-image: url("{url}") {insets} {insets} {insets} {insets} stretch stretch; }}'
            )

    def sprites_for_states(selectors: str, root: str, insets: int = 8) -> None:
        for pseudo, variant in (
            ("", "normal"), (":hover", "over"),
            (":pressed", "pressed"), (":disabled", "disabled"),
        ):
            add_border(
                ", ".join(selector + pseudo for selector in selectors.split(", ")),
                f"{root}_{variant}.png",
                insets,
            )

    # Keep semantic colors / focus from shared theme; the sprite provides relief.
    sprites_for_states(
        "QPushButton#PrimaryActionButton, QPushButton#primaryButton, "
        "QPushButton#HomeContinueButton, QPushButton#FeaturedGuideOpen",
        "btn_green", 8,
    )
    sprites_for_states(
        "QPushButton#SecondaryButton, QPushButton#secondaryButton",
        "btn_yellow2", 8,
    )
    sprites_for_states(
        "QPushButton#GuideManualPageCheck",
        "btn_green", 8,
    )
    # The tiny green button sprite turns the whole Guide header neon yellow
    # at Windows DPI. Keep the dark-stone beveled QSS above for secondary
    # toggles; reserve green action sprites for the actual Valider command.
    add_border(
        "QFrame#GuidePreparationPanel, QFrame#GuideSummaryPanel, QFrame#GuideParticipantsPanel",
        "Assets_UI_Themes_darkStone_common_bg_small_border_light-png.png", 6,
    )
    sprites_for_states(
        "QPushButton#GuideManualNavButton",
        "btn_arrow_pagination", 5,
    )
    sprites_for_states(
        "QPushButton#TopNavSettings",
        "btn_green_small", 6,
    )
    normal = _sprite_url("Assets_UI_Themes_darkStone_common_btn_checkbox_normal-png.png")
    checked = _sprite_url("Assets_UI_Themes_darkStone_common_btn_checkbox_selected-png.png")
    if normal and checked:
        rules.extend((
            f'QCheckBox::indicator {{ width: 19px; height: 19px; image: url("{normal}"); }}',
            f'QCheckBox::indicator:checked {{ image: url("{checked}"); }}',
        ))
    selected_tab = _sprite_url("Assets_UI_Themes_darkStone_common_bg_tab_selected_normal-png.png")
    if selected_tab:
        # Keep the same border box for selected and unselected tabs. A 6px
        # selected-only sprite border makes the tab bar jump on navigation.
        # Encyclopedia has a more specific QSS selector, so it must be
        # included explicitly rather than relying on the generic rule.
        rules.append(
            "QTabBar::tab, QTabWidget#EncyclopediaTabs QTabBar::tab { "
            "border: 6px solid transparent; }"
        )
        rules.append(
            "QTabBar::tab:selected, "
            "QTabWidget#EncyclopediaTabs QTabBar::tab:selected { "
            "border: 6px solid transparent;"
            f' border-image: url("{selected_tab}") 6 6 6 6 stretch stretch; }}'
        )
    # Keep keyboard focus visible even when the button has a border-image.
    rules.append(
        "QPushButton:focus, QToolButton:focus, QCheckBox:focus, "
        "QComboBox:focus, QLineEdit:focus, QSpinBox:focus, "
        "QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus, "
        "QTreeView:focus, QListView:focus, QTableView:focus, "
        "QTreeWidget:focus, QListWidget:focus, QTableWidget:focus { "
        "border: 2px solid %s; }" % colors["TEXT_SOFT"]
    )
    # ID-specific sprite rules otherwise outrank a generic :focus selector.
    # A visible focus outline takes priority over decorative border-images.
    focus_button_names = (
        "PrimaryActionButton", "primaryButton", "HomeContinueButton",
        "FeaturedGuideOpen", "SecondaryButton", "secondaryButton",
        "GuideManualNavButton", "GuideManualPageCheck", "TopNavSettings",
    )
    rules.append(
        ", ".join(f"QPushButton#{name}:focus" for name in focus_button_names)
        + " { border: 2px solid %s; border-image: none; }" % colors["TEXT_SOFT"]
    )
    return "\n".join(rules)


# Deterministic, asset-free fallback used only when no personal Unity sky exists.
# Stable positions prevent flicker and the cost stays bounded on every repaint.
_PUBLIC_SKY_STARS = tuple(
    (
        ((index * 149 + 31) % 991) / 991,
        ((index * 233 + 73) % 997) / 997,
        2.0 if index % 11 == 0 else 1.0,
        130 if index % 11 == 0 else 75,
    )
    for index in range(110)
)


class UnityBackdrop(QWidget):
    """One cached pixmap per shell; paint a centered cover crop without stretching."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AtlasUnityBackdrop")
        image = wallpaper_path()
        self._pixmap = QPixmap(str(image)) if image else QPixmap()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        # A license-independent Unity-colored sky remains visible in public
        # builds where the user's local wallpaper has not been installed.
        # The verified personal background entirely covers this fallback.
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor(UNITY_PALETTE["BG_GRADIENT_START"]))
        gradient.setColorAt(0.52, QColor(UNITY_PALETTE["PANEL"]))
        gradient.setColorAt(1.0, QColor(UNITY_PALETTE["BG"]))
        painter.fillRect(self.rect(), gradient)
        if self._pixmap.isNull() and self.width() > 0 and self.height() > 0:
            # The same subtle fixed sky appears on every shell page. Never
            # paint fallback stars over the user's original cleaned wallpaper.
            star_color = QColor(UNITY_PALETTE["TEXT_SOFT"])
            for x, y, size, alpha in _PUBLIC_SKY_STARS:
                star_color.setAlpha(alpha)
                painter.fillRect(
                    QRectF(x * self.width(), y * self.height(), size, size),
                    star_color,
                )
        if not self._pixmap.isNull() and self.width() > 0 and self.height() > 0:
            source_w = self._pixmap.width()
            source_h = self._pixmap.height()
            dest_w, dest_h = self.width(), self.height()
            # Crop an unchanged image; its celestial objects retain exact proportions.
            ratio = max(dest_w / source_w, dest_h / source_h)
            crop_w, crop_h = dest_w / ratio, dest_h / ratio
            src = QRectF((source_w - crop_w) / 2, (source_h - crop_h) / 2, crop_w, crop_h)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(QRectF(self.rect()), self._pixmap, src)
        painter.end()
