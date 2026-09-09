from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap

from app.constants import DATA_DIR, ROOT_DIR

ASSETS_DIR = DATA_DIR / "cartography" / "assets"
PLACEHOLDER_PATH = ASSETS_DIR / "placeholder" / "placeholder_map.png"


def resolve_asset_path(asset_path: str | None) -> Path | None:
    if not asset_path:
        return None
    path = Path(str(asset_path).strip())
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def ensure_placeholder_asset() -> Path:
    PLACEHOLDER_PATH.parent.mkdir(parents=True, exist_ok=True)
    if PLACEHOLDER_PATH.exists():
        return PLACEHOLDER_PATH

    image = QImage(1400, 880, QImage.Format_ARGB32)
    image.fill(QColor("#0D1724"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.fillRect(0, 0, image.width(), image.height(), QColor("#0A121D"))

    grid_pen = QPen(QColor("#182536"))
    grid_pen.setWidth(1)
    painter.setPen(grid_pen)
    for x in range(0, image.width(), 80):
        painter.drawLine(x, 0, x, image.height())
    for y in range(0, image.height(), 80):
        painter.drawLine(0, y, image.width(), y)

    painter.setPen(QPen(QColor("#223044"), 2))
    painter.drawRoundedRect(70, 70, image.width() - 140, image.height() - 140, 18, 18)
    painter.setPen(QColor("#F2F6FF"))
    font = painter.font()
    font.setPointSize(22)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(
        image.rect(),
        Qt.AlignCenter,
        "Carte locale absente\nPlacez un world.png dans data/cartography/assets/",
    )
    painter.end()
    image.save(str(PLACEHOLDER_PATH), "PNG")
    return PLACEHOLDER_PATH


def load_map_pixmap(asset_path: str | None) -> tuple[QPixmap, Path, bool]:
    resolved = resolve_asset_path(asset_path)
    is_placeholder = resolved is None or not resolved.exists()
    path = ensure_placeholder_asset() if is_placeholder else resolved

    pixmap = QPixmap(str(path))
    if pixmap.isNull() and path != PLACEHOLDER_PATH:
        path = ensure_placeholder_asset()
        is_placeholder = True
        pixmap = QPixmap(str(path))

    if pixmap.isNull():
        pixmap = QPixmap(1400, 880)
        pixmap.fill(QColor("#0D1724"))
        is_placeholder = True
    return pixmap, path, is_placeholder
