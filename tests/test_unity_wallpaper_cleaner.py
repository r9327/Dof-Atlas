"""Pure local-image tests; never require or redistribute a game screenshot."""
from __future__ import annotations

import argparse
import unittest

from PIL import Image, ImageDraw

from tools.assets.clean_unity_wallpaper import parse_box, repair_sky, validate_boxes


class WallpaperCleanerTests(unittest.TestCase):
    def test_three_icons_removed_without_altering_unmasked_pixels(self):
        image = Image.new("RGB", (300, 150))
        pixels = image.load()
        for y in range(150):
            for x in range(300):
                pixels[x, y] = (x // 2, 50 + y // 3, 100)
        original = image.copy()
        boxes = [(200, 10, 14, 14), (230, 10, 14, 14), (260, 10, 14, 14)]
        art = ImageDraw.Draw(image)
        for x, y, w, h in boxes:
            art.rectangle((x, y, x+w-1, y+h-1), fill=(0, 0, 0))
        repaired = repair_sky(image, boxes)
        self.assertEqual(repaired.size, image.size)
        for x, y, w, h in boxes:
            self.assertEqual(repaired.getpixel((x+7, y+7))[:3], original.getpixel((x+7, y+7)))
        self.assertEqual(repaired.getpixel((100, 100)), image.convert("RGBA").getpixel((100, 100)))
        self.assertEqual(image.getpixel((207, 17)), (0, 0, 0))

    def test_invalid_areas_and_coordinates_rejected(self):
        with self.assertRaises(ValueError):
            validate_boxes((300, 150), [(200, 10, 14, 14)])
        with self.assertRaises(ValueError):
            validate_boxes((300, 150), [(200, 10, 14, 14)] * 3)
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_box("bad,2,3,4")
        self.assertEqual(parse_box("210,12,14,15"), (210, 12, 14, 15))


if __name__ == "__main__":
    unittest.main()
