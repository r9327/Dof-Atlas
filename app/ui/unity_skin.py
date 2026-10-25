"""Opt-in local DOFUS Unity skin. Licensed Atlas UI remains the fallback.

The reference sprites and screenshot are *not* authorized for redistribution.
No font extracted from the game is registered by this module.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "themes" / "dofus_unity"
UNITY_PALETTE = {
    "BG": "#151821",
    "SIDEBAR": "#19243F",
    "PANEL": "#1B2746",
    "PANEL_2": "#213154",
    "PANEL_HOVER": "#2C3C69",
    "PANEL_ACTIVE": "#344978",
    "BORDER": "#475F89",
    "BORDER_SOFT": "#354966",
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
    """Local-only opt-in; the default distributable theme never loads these assets."""
    return os.environ.get("ATLAS_THEME", "").strip().casefold() == "dofus_unity"


def wallpaper_path() -> Path | None:
    candidate = _ASSETS / "background_selection_original.png"
    return candidate if unity_enabled() and candidate.is_file() else None


def _sprite_url(filename: str) -> str | None:
    """Only named, bundled files; no runtime archive extraction or network lookup."""
    candidate = _ASSETS / "sprites" / filename
    if not candidate.is_file():
        return None
    return candidate.resolve().as_posix()


def unity_skin_stylesheet() -> str:
    """Global Qt controls, using 9-slice borders for verified local source sprites."""
    if not unity_enabled():
        return ""
    rules = [
        "QWidget#AtlasUnityBackdrop { background: transparent; }",
        "QStackedWidget#AtlasUnityStack, QWidget#HomePage { background: transparent; }",
        "QPushButton:focus, QToolButton:focus, QCheckBox:focus { border: 2px solid #D9EAF2; }",
    ]

    def add_border(selectors: str, image: str, insets: int = 8) -> None:
        url = _sprite_url(image)
        if url:
            rules.append(
                f"{selectors} {{ border: {insets}px solid transparent;"
                f' border-image: url("{url}") {insets} {insets} {insets} {insets} stretch stretch; }}'
            )

    primary = "QPushButton#PrimaryActionButton, QPushButton#FeaturedGuideOpen"
    for pseudo, name in (
        ("", "btn_green_normal.png"),
        (":hover", "btn_green_over.png"),
        (":pressed", "btn_green_pressed.png"),
        (":disabled", "btn_green_disabled.png"),
    ):
        add_border(", ".join(selector + pseudo for selector in primary.split(", ")), name)
    for pseudo, name in (
        ("", "btn_arrow_pagination_normal.png"),
        (":hover", "btn_arrow_pagination_over.png"),
        (":pressed", "btn_arrow_pagination_pressed.png"),
        (":disabled", "btn_arrow_pagination_disabled.png"),
    ):
        add_border("QPushButton#GuideManualNavButton" + pseudo, name, 5)
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
        painter.fillRect(self.rect(), QColor(UNITY_PALETTE["BG"]))
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
