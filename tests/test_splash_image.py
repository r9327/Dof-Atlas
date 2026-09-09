from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage

from app.ui.splash_image import clear_connected_dark_background


class SplashImageTests(unittest.TestCase):
    @staticmethod
    def _image(width: int, height: int, color: QColor) -> QImage:
        image = QImage(width, height, QImage.Format_RGBA8888)
        image.fill(color)
        return image

    @staticmethod
    def _alpha(image: QImage, x: int, y: int) -> int:
        return QColor.fromRgba(image.pixel(x, y)).alpha()

    def test_only_edge_connected_dark_background_becomes_transparent(self) -> None:
        image = self._image(7, 7, QColor(20, 20, 20, 255))
        # Bright ring isolates the center dark pixel from the border-connected
        # background. Historical flood-fill semantics must preserve that center.
        for x in range(2, 5):
            image.setPixelColor(x, 2, QColor(220, 210, 190, 255))
            image.setPixelColor(x, 4, QColor(220, 210, 190, 255))
        for y in range(2, 5):
            image.setPixelColor(2, y, QColor(220, 210, 190, 255))
            image.setPixelColor(4, y, QColor(220, 210, 190, 255))
        image.setPixelColor(3, 3, QColor(12, 12, 12, 255))

        result = clear_connected_dark_background(image)

        self.assertEqual(self._alpha(result, 0, 0), 0)
        self.assertEqual(self._alpha(result, 1, 3), 0)
        self.assertEqual(self._alpha(result, 3, 3), 255)
        self.assertEqual(self._alpha(result, 3, 2), 255)

    def test_dark_colored_edge_pixel_is_not_background_when_spread_exceeds_18(self) -> None:
        image = self._image(3, 3, QColor(20, 20, 20, 255))
        image.setPixelColor(1, 0, QColor(40, 10, 10, 255))

        result = clear_connected_dark_background(image)

        self.assertEqual(self._alpha(result, 0, 0), 0)
        self.assertEqual(self._alpha(result, 1, 0), 255)

    def test_threshold_42_and_spread_18_match_historical_rule(self) -> None:
        image = self._image(4, 2, QColor(200, 200, 200, 255))
        image.setPixelColor(0, 0, QColor(42, 24, 24, 255))  # brightness 42, spread 18: yes
        image.setPixelColor(1, 0, QColor(43, 43, 43, 255))  # brightness 43: no
        image.setPixelColor(2, 0, QColor(42, 23, 23, 255))  # spread 19: no
        image.setPixelColor(3, 0, QColor(0, 0, 0, 255))
        # Bottom row is bright so each top pixel is evaluated only through the
        # edge seed itself, not via another removable dark region.

        result = clear_connected_dark_background(image)

        self.assertEqual(self._alpha(result, 0, 0), 0)
        self.assertEqual(self._alpha(result, 1, 0), 255)
        self.assertEqual(self._alpha(result, 2, 0), 255)
        self.assertEqual(self._alpha(result, 3, 0), 0)

    def test_null_image_is_returned_safely(self) -> None:
        image = QImage()
        result = clear_connected_dark_background(image)
        self.assertTrue(result.isNull())


if __name__ == "__main__":
    unittest.main()
