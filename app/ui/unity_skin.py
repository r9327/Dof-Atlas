"""Single Unity visual system for Atlas, with local optional graphic assets.

Game-extracted image and font files stay outside the public Windows release.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFontDatabase, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


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


def unity_skin_stylesheet() -> str:
    """Global Qt controls, with 9-slice and local-only source sprites."""
    if not unity_enabled():
        return ""
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
        "background: rgba(27, 39, 70, 0.88); "
        "border: 1px solid #475F89; }",
        "QListView#GuidesHomeDofusGrid { "
        "background: rgba(21, 32, 59, 0.45); }",
        "QScrollArea { background: rgba(21, 29, 50, 0.35); border: none; }",
        "QScrollArea > QWidget > QWidget { background: transparent; }",
        # Shared widget families, never changes their existing geometry or actions.
        "QGroupBox, QTabWidget::pane { "
        "background: rgba(27, 39, 70, 0.78); color: #F1F6FB; "
        "border: 1px solid #475F89; border-radius: 6px; }",
        "QListView, QTreeView, QTableView, QListWidget, QTreeWidget, QTableWidget { "
        "background: rgba(21, 32, 59, 0.92); color: #F1F6FB; "
        "alternate-background-color: rgba(33, 49, 84, 0.88); "
        "selection-background-color: #344978; selection-color: #F1F6FB; "
        "border: 1px solid #475F89; }",
        "QHeaderView::section { background: rgba(33, 49, 84, 0.95); "
        "color: #F1F6FB; border: 1px solid #475F89; }",
        "QTabBar::tab { background: rgba(25, 38, 75, 0.93); "
        "color: #D9EAF2; border: 1px solid #475F89; }",
        "QTabBar::tab:hover { background: #2C3C69; }",
        "QTabBar::tab:selected { color: #F1F6FB; background: #344978; }",
        "QToolTip { background: #192657; color: #F1F6FB; "
        "border: 1px solid #7B9BC8; padding: 4px; }",
        "QProgressBar { background: rgba(21, 32, 59, 0.85); "
        "color: #F1F6FB; border: 1px solid #475F89; "
        "text-align: center; }",
        "QFrame#card, QFrame#HomeCharacterCard, QFrame#HomeTrackingCard, "
        "QFrame#HomeGuideCard, QFrame#HomeNetworkMiniCard, QFrame#HomeAlmanaxCard, "
        "QFrame#GuideFeaturedCard { "
        "background: rgba(27, 39, 70, 0.88); border: 1px solid #617CA6; "
        "border-radius: 9px; }",
        "QFrame#GuideCompactHeader, QFrame#GuideSheetHeader, "
        "QFrame#GuidePreparationPanel { "
        "background: rgba(24, 37, 70, 0.93); border: 1px solid #475F89; }",
        "QDialog#AtlasDialog, QMenu { "
        "background: rgba(25, 38, 75, 0.98); color: #F1F6FB; "
        "border: 1px solid #617CA6; }",
        "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, "
        "QPlainTextEdit { "
        "background: rgba(20, 29, 55, 0.96); color: #F1F6FB; "
        "border: 1px solid #617CA6; }",
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
        rules.append(
            'QTabBar::tab:selected { border: 6px solid transparent;'
            f' border-image: url("{selected_tab}") 6 6 6 6 stretch stretch; }}'
        )
    # Keep keyboard focus visible even when the button has a border-image.
    rules.append(
        "QPushButton:focus, QToolButton:focus, QCheckBox:focus, "
        "QComboBox:focus, QLineEdit:focus, QTreeView:focus, QListView:focus { "
        "border: 2px solid #D9EAF2; }"
    )
    # ID-specific sprite rules otherwise outrank a generic :focus selector.
    # A visible focus outline takes priority over decorative border-images.
    focus_button_names = (
        "PrimaryActionButton", "primaryButton", "HomeContinueButton",
        "FeaturedGuideOpen", "SecondaryButton", "secondaryButton",
        "GuideManualNavButton", "TopNavSettings",
    )
    rules.append(
        ", ".join(f"QPushButton#{name}:focus" for name in focus_button_names)
        + " { border: 2px solid #D9EAF2; border-image: none; }"
    )
    return "\n".join(rules)


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
