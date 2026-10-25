"""Pure local-image tests; never require or redistribute a game screenshot."""
from __future__ import annotations

import argparse
import hashlib
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw

from tools.assets.clean_unity_wallpaper import parse_box, repair_sky, validate_boxes, canvas_box, main, SOURCE_CORNER_TOOLBAR


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

    def test_crop_drag_maps_back_to_exact_original_coordinates(self):
        self.assertEqual(canvas_box((100, 90), (50, 20), (1055, 0), (864, 430)), (1105, 20, 50, 70))
        self.assertEqual(canvas_box((-20, -10), (900, 500), (1055, 0), (864, 430)), (1055, 0, 864, 430))

    def test_cli_requires_exact_original_and_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "missing.png"
            output = Path(directory) / "clean.png"
            arguments = ["clean_unity_wallpaper", "--source", str(source),
                         "--output", str(output), "--box", "1200,20,20,20",
                         "--box", "1300,20,20,20", "--box", "1400,20,20,20"]
            with patch("sys.argv", arguments), patch("sys.stderr"):
                with self.assertRaises(SystemExit) as raised:
                    main()
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(output.exists())

    def test_top_right_single_toolbar_including_both_borders(self):
        width, height = 300, 150
        original = Image.new("RGB", (width, height))
        pix = original.load()
        for y in range(height):
            for x in range(width):
                pix[x, y] = (x // 2, y // 2 + 30, 100)
        changed = original.copy()
        # The complete dark background of all three icons touches two edges.
        ImageDraw.Draw(changed).rectangle((260, 0, 299, 17), fill=(0, 0, 0))
        repaired = repair_sky(changed, [(260, 0, 40, 18)])
        self.assertEqual(repaired.getpixel((280, 8))[:3], original.getpixel((280, 8)))
        self.assertEqual(repaired.getpixel((299, 0))[:3], original.getpixel((299, 0)))
        self.assertEqual(repaired.getpixel((259, 8)), changed.convert("RGBA").getpixel((259, 8)))
        self.assertEqual(changed.getpixel((280, 8)), (0, 0, 0))
        with self.assertRaises(ValueError):
            validate_boxes((300, 150), [(259, 0, 40, 18)])

    def test_failed_png_write_preserves_previous_clean_result(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "original.png"
            Image.new("RGB", (1919, 1079), (20, 40, 90)).save(source)
            expected = hashlib.sha256(source.read_bytes()).hexdigest()
            output = Path(directory) / "clean.png"
            output.write_bytes(b"previous approved wallpaper")
            command = ["clean_unity_wallpaper", "--source", str(source),
                       "--output", str(output), "--corner-toolbar"]
            with patch("tools.assets.clean_unity_wallpaper.SOURCE_SHA256", expected), \
                 patch("sys.argv", command), \
                 patch("PIL.Image.Image.save", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    main()
            self.assertEqual(output.read_bytes(), b"previous approved wallpaper")
            self.assertEqual(sorted(x.name for x in Path(directory).iterdir()),
                             ["clean.png", "original.png"])

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
