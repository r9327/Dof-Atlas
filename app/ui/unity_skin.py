"""Single Unity visual system for Atlas, with local optional graphic assets.

Game-extracted image and font files stay outside the public Windows release.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontDatabase, QIcon, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from app.ui.unity_palette import (
    UNITY_ICON_NAMES, UNITY_PALETTE, UNITY_RADII, UNITY_SIZES_PX,
    resolve_unity_colors,
)


_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "themes" / "dofus_unity"
# A personal theme survives every transactional EXE update and is never
# part of the publicly downloadable runtime.
_PERSONAL_ASSETS = (
    Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    / "DofusAtlas" / "themes" / "dofus_unity"
)

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
    if not unity_enabled() or icon not in UNITY_ICON_NAMES:
        return None
    filename = f"Assets_UI_Themes_Figma_menuIcons_1x_{icon}-png.png"
    return _asset_file(Path("sprites") / filename)



@lru_cache(maxsize=48)
def unity_ui_icon(name: str, size: int = 24) -> QIcon:
    """Actual local Unity pictogram when permitted; otherwise a clean white icon.

    The fallback is drawn with Qt paths, not with a game asset or a unicode
    glyph that might show as a colored square on Windows.
    """
    if name not in UNITY_ICON_NAMES:
        raise ValueError(f"Unknown Unity UI icon: {name}")
    if size not in {UNITY_SIZES_PX[key] for key in (
        "icon_small", "icon_normal", "icon_large", "icon_xlarge"
    )}:
        raise ValueError(f"Unsupported Unity UI icon size: {size}")
    path = sprite_icon_path(name)
    if path is not None:
        return QIcon(str(path))

    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / 24.0, size / 24.0)
    painter.setPen(QPen(QColor(UNITY_PALETTE["TEXT"]), 1.8, Qt.SolidLine,
                        Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    if name == "guide":
        painter.drawRoundedRect(QRectF(3, 5, 18, 15), 1.5, 1.5)
        painter.drawLine(12, 5, 12, 20)
        painter.drawLine(6, 9, 10, 9)
        painter.drawLine(14, 9, 18, 9)
    elif name == "quest":
        painter.drawRoundedRect(QRectF(5, 3, 14, 18), 2, 2)
        for y in (8, 12, 16):
            painter.drawLine(8, y, 16, y)
    elif name == "success":
        painter.drawArc(QRectF(6, 3, 12, 12), 0, 180 * 16)
        painter.drawLine(6, 9, 9, 15)
        painter.drawLine(18, 9, 15, 15)
        painter.drawLine(12, 15, 12, 19)
        painter.drawLine(8, 21, 16, 21)
    elif name == "encyclopedia":
        painter.drawRoundedRect(QRectF(4, 4, 13, 16), 1, 1)
        painter.drawRoundedRect(QRectF(8, 2, 13, 16), 1, 1)
        painter.drawLine(11, 7, 17, 7)
        painter.drawLine(11, 11, 17, 11)
    elif name == "character":
        painter.drawEllipse(QRectF(8, 3, 8, 8))
        painter.drawArc(QRectF(4, 12, 16, 11), 0, 180 * 16)
    elif name == "dofus":
        painter.drawEllipse(QRectF(7, 3, 10, 18))
        painter.drawArc(QRectF(9, 6, 6, 9), 40 * 16, 100 * 16)
    elif name == "map":
        painter.drawEllipse(QRectF(6, 3, 12, 12))
        painter.drawEllipse(QRectF(10, 7, 4, 4))
        painter.drawLine(7, 14, 12, 21)
        painter.drawLine(17, 14, 12, 21)
    elif name == "inventory":
        painter.drawRoundedRect(QRectF(4, 8, 16, 13), 2, 2)
        painter.drawArc(QRectF(8, 3, 8, 10), 0, 180 * 16)
    painter.end()
    return QIcon(pix)

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
    colors = resolve_unity_colors(palette)
    radii = {
        **UNITY_RADII,
        **{key: value for key, value in (palette or {}).items() if key in UNITY_RADII},
    }

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
        "border: 1px solid %s; border-radius: %s; }" % (
            translucent("PANEL", 0.78), colors["TEXT"], colors["BORDER"],
            radii["RADIUS_SM"],
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
        "stop:0 %s, stop:1 %s); border: 1px solid %s; border-radius: %s; }"
        % (
            colors["PANEL_ACTIVE"], colors["PANEL"], colors["GREEN_BORDER"],
            radii["RADIUS_MD"],
        ),
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
        "border: 0; background: %s; border-radius: %s; }"
        % (colors["BORDER_SOFT"], radii["RADIUS_XS"]),
        "QFrame#GuideFeaturedCard QProgressBar#GuideFeaturedProgress::chunk { "
        "background: %s; border-radius: %s; }"
        % (colors["GREEN"], radii["RADIUS_XS"]),
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
        "background: %s; border-radius: %s; }" % (
            translucent("GUIDE_COPY_HOVER", 0.30), radii["RADIUS_XS"],
        ),
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

    # Shared buttons must use the same palette everywhere. The optional
    # darkStone btn_yellow2 image is GOLD and overrides the blue secondary
    # role; btn_green can appear neon in Windows offscreen captures. Neither
    # is an appropriate skin for the universal AtlasButton variants.
    # Their normal / hover / pressed / disabled colors are already provided
    # by app.ui.theme. Preserve optional artwork on dedicated controls only.
    sprites_for_states(
        "QPushButton#HomeContinueButton, QPushButton#FeaturedGuideOpen",
        "btn_green", 8,
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
    # Selected tabs use PANEL_ACTIVE / GREEN_BORDER from the real palette.
    # The optional darkStone 9-slice has a beige-gold tint, and forcing a 6px
    # border changes geometry. Do not let decorative art replace shared tabs.
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
