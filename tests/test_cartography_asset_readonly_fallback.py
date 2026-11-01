"""Windows read-only install: cartography must not crash on missing map artwork."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.cartography.map_asset_loader import (
    ensure_placeholder_asset, load_map_pixmap,
)


class CartographyReadonlyFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_unwritable_placeholder_directory_does_not_crash_map(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing_placeholder = Path(temporary) / "protected" / "placeholder_map.png"
            missing_map = "data/cartography/assets/caves/__doctor_nonexistent_map__.png"
            with (
                patch("app.cartography.map_asset_loader.PLACEHOLDER_PATH",
                      missing_placeholder),
                patch.object(Path, "mkdir", side_effect=PermissionError("read-only app")),
            ):
                self.assertEqual(ensure_placeholder_asset(), missing_placeholder)
                pixmap, path, is_placeholder = load_map_pixmap(missing_map)
            self.assertEqual(path, missing_placeholder)
            self.assertTrue(is_placeholder)
            self.assertFalse(pixmap.isNull())
            self.assertGreater(pixmap.width(), 0)
            self.assertFalse(missing_placeholder.exists())


if __name__ == "__main__":
    unittest.main()
