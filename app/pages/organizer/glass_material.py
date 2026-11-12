"""Unity-colored glass surfaces for Organizer, independent of the input runtime.

A small, cached low-resolution copy of the *static* Unity wallpaper diffuses
behind each panel. Specular edges simulate glass without GPU shaders, per-frame
backdrop capture, third-party dependencies or blurring interactive children.
This is not the native iOS Liquid Glass compositor.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import QFrame, QWidget

from app.ui.components import AtlasButton
from app.ui.unity_skin import UNITY_PALETTE, wallpaper_path


# The user-approved glass surface at 50% of the previous visual intensity.
# A single factor controls transmission and highlights, without altering
# the canonical Unity colors, geometry or interactive behavior.
GLASS_INTENSITY = 0.5


def _reflection_alpha(alpha: int) -> int:
    return round(alpha * GLASS_INTENSITY)


def _surface_alpha(alpha: int) -> int:
    """Half the transparency: 255 is opaque and zero is transparent."""
    return 255 - round((255 - alpha) * GLASS_INTENSITY)


def unity_rgba(role: str, opacity: int) -> str:
    """Give a canonical Unity color an alpha channel, not a second palette."""
    color = QColor(UNITY_PALETTE[role])
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {opacity})"


def unity_glass_gradient(top: str = "PANEL_ACTIVE",
                         bottom: str = "PANEL_2", *,
                         top_alpha: int = 180,
                         bottom_alpha: int = 196) -> str:
    return (
        "qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        f"stop:0 {unity_rgba(top, _surface_alpha(top_alpha))},"
        f"stop:1 {unity_rgba(bottom, _surface_alpha(bottom_alpha))})"
    )


@lru_cache(maxsize=2)
def _diffuse_unity_wallpaper(width: int, height: int, local_image: str) -> QImage:
    """Render a tiny, static diffusion texture (not a live screen grab).

    The returned texture is roughly 1/14 of each dimension: blur is obtained
    through downsampling and smooth magnification. The low-resolution result
    stays cached; large full-window image buffers never remain in memory.
    """
    sw = max(1, width // 14)
    sh = max(1, height // 14)
    image = QImage(sw, sh, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    base = QLinearGradient(0, 0, sw, sh)
    base.setColorAt(0, QColor(UNITY_PALETTE["BG_GRADIENT_START"]))
    base.setColorAt(0.52, QColor(UNITY_PALETTE["PANEL"]))
    base.setColorAt(1, QColor(UNITY_PALETTE["BG"]))
    painter.fillRect(image.rect(), QBrush(base))
    if local_image:
        picture = QPixmap(local_image)
        if not picture.isNull():
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            ratio = max(sw / picture.width(), sh / picture.height())
            crop_w = sw / ratio
            crop_h = sh / ratio
            crop = QRectF(
                (picture.width() - crop_w) / 2,
                (picture.height() - crop_h) / 2,
                crop_w, crop_h,
            )
            painter.drawPixmap(QRectF(0, 0, sw, sh), picture, crop)
    painter.end()
    return image


class OrganizerGlassCard(QFrame):
    """Reusable panel with diffused Unity backdrop and iOS-like edge glints.

    Only the panel is painted. No blur effect touches child controls or text.
    """

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.width() < 4 or self.height() < 4:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rectangle = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        outline = QPainterPath()
        outline.addRoundedRect(rectangle, 10, 10)
        painter.setClipPath(outline)

        backdrop = self.window().findChild(QWidget, "AtlasUnityBackdrop")
        if backdrop is not None and backdrop.width() > 0 and backdrop.height() > 0:
            local = wallpaper_path()
            image = _diffuse_unity_wallpaper(
                backdrop.width(), backdrop.height(), str(local) if local else "",
            )
            origin = backdrop.mapFrom(self, QPoint(0, 0))
            sx = image.width() / backdrop.width()
            sy = image.height() / backdrop.height()
            source = QRectF(
                origin.x() * sx, origin.y() * sy,
                self.width() * sx, self.height() * sy,
            )
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawImage(QRectF(self.rect()), image, source)

        # Translucent Unity tint. Background blur remains visible underneath.
        tint = QLinearGradient(0, 0, 0, self.height())
        top = QColor(UNITY_PALETTE["PANEL_ACTIVE"])
        bottom = QColor(UNITY_PALETTE["PANEL"])
        top.setAlpha(_surface_alpha(143))
        bottom.setAlpha(_surface_alpha(173))
        tint.setColorAt(0, top)
        tint.setColorAt(1, bottom)
        painter.fillPath(outline, QBrush(tint))

        # Optical reflection, not a brighter invented blue.
        glint = QLinearGradient(0, 0, self.width(), self.height())
        glint.setColorAt(0, QColor(255, 255, 255, _reflection_alpha(46)))
        glint.setColorAt(0.27, QColor(255, 255, 255, _reflection_alpha(10)))
        glint.setColorAt(0.68, QColor(255, 255, 255, 0))
        glint.setColorAt(1, QColor(255, 255, 255, _reflection_alpha(24)))
        painter.fillPath(outline, QBrush(glint))
        painter.setClipping(False)

        edge = QLinearGradient(0, 0, self.width(), self.height())
        edge.setColorAt(0, QColor(245, 250, 255, _reflection_alpha(132)))
        edge.setColorAt(0.52, QColor(214, 229, 255, _reflection_alpha(49)))
        edge.setColorAt(1, QColor(240, 250, 255, _reflection_alpha(87)))
        painter.setPen(QPen(QBrush(edge), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(outline)
        if self.width() >= 38:
            painter.setPen(QPen(QColor(255, 255, 255, _reflection_alpha(60)), 1.0))
            painter.drawLine(
                QPoint(15, 2), QPoint(self.width() - 15, 2),
            )
        painter.end()


class OrganizerGlassButton(AtlasButton):
    """Small specular reflection over the shared Unity button QSS.

    All interactions, checked state, keyboard focus and click handling remain
    standard QPushButton behavior.
    """

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.isEnabled() or self.width() < 28 or self.height() < 22:
            return
        if self.objectName() in (
            "OrganizerSpeedChoice", "OrganizerSpeedChoiceSelected",
            "OrganizerModeChoice", "DragHandle",
        ):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rectangle = QRectF(self.rect()).adjusted(0.7, 0.7, -0.7, -0.7)
        clip = QPainterPath()
        clip.addRoundedRect(rectangle, 7, 7)
        painter.setClipPath(clip)
        shine = QLinearGradient(0, 0, 0, max(1, self.height() * 0.52))
        shine.setColorAt(0, QColor(255, 255, 255, _reflection_alpha(31 if not self.isDown() else 13)))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillRect(QRectF(0, 0, self.width(), self.height() * 0.52), QBrush(shine))
        painter.setClipping(False)
        painter.setPen(QPen(QColor(244, 250, 255, _reflection_alpha(75)), 1.0))
        painter.drawLine(QPoint(9, 2), QPoint(self.width() - 9, 2))
        painter.end()
