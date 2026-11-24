from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.network.application_coordinator import NetworkApplicationStatus
from app.pages.home_page import HomePage, HomeTrackingRow
from app.core.file_stamp import mtime_ctime_size_stamp_or_zero


class HomeNetworkIndicatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_home_progress_file_stamp_is_shared_and_handles_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quest_progress.json"
            self.assertEqual(HomePage._progress_file_stamp(path), (0, 0, 0))
            path.write_text('{"characters":{}}', encoding="utf-8")
            self.assertEqual(HomePage._progress_file_stamp(path), mtime_ctime_size_stamp_or_zero(path))
            self.assertEqual(HomePage._progress_file_stamp(path)[2], path.stat().st_size)
            path.unlink()
            self.assertEqual(HomePage._progress_file_stamp(path), (0, 0, 0))

    def test_empty_character_icon_uses_logo_and_same_path_replacement_refreshes(self):
        from unittest.mock import patch
        from PySide6.QtGui import QImage, QIcon
        page = HomePage()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                logo = root / "logo.png"
                image = QImage(24, 24, QImage.Format_ARGB32)
                image.fill(0xFF336699)
                self.assertTrue(image.save(str(logo), "PNG"))
                with patch("app.pages.home_page.LOGO_PATH", logo), \
                     patch("app.pages.home_page.atlas_application_icon", return_value=QIcon(str(logo))) as fallback, \
                     patch.object(page, "refresh_progress"):
                    page.set_character("character:1", "Alpha", "")
                    fallback.assert_called_once()
                    self.assertFalse(page.character_portrait.icon().isNull())
                    skin = root / "skin.png"
                    image.save(str(skin), "PNG")
                    page.set_character("character:1", "Alpha", str(skin))
                    before = page._character_icon_signature
                    replacement = QImage(42, 42, QImage.Format_ARGB32)
                    replacement.fill(0xFFFF0000)
                    replacement.save(str(skin), "PNG")
                    page.set_character("character:1", "Alpha", str(skin))
                    self.assertNotEqual(page._character_icon_signature, before)
        finally:
            page.deleteLater()

    def test_home_uses_canonical_runtime_without_optional_legacy_provider(self) -> None:
        from unittest.mock import patch
        page = HomePage()
        try:
            page.character_key = "character:42"
            page.catalog = object()
            page.guide_provider = None
            page._guide_ultime_runtime_allowed = True
            with patch.object(page, "_refresh_rich_progress") as rich, \
                 patch("app.pages.home_page._persisted_manual_summary") as local:
                page.refresh_progress()
                rich.assert_called_once_with()
                local.assert_not_called()
            page._guide_ultime_runtime_allowed = False
            with patch.object(page, "_refresh_rich_progress") as rich, \
                 patch("app.pages.home_page._persisted_manual_summary", return_value={}) as local:
                page.refresh_progress()
                local.assert_called_once_with("character:42")
                rich.assert_not_called()
        finally:
            page.deleteLater()

    def test_home_tracking_key_preserves_accent_and_hyphen_matching(self) -> None:
        self.assertEqual(HomePage._plain_key("  ÉPÉE – Cawotte  "), "epee – cawotte")
        self.assertEqual(HomePage._plain_key(" Cité d’Astrub - Nord "), "cite d'astrub nord")
        self.assertEqual(HomePage._plain_key(None), "")
        self.assertEqual(HomePage._plain_key("a--b"), "a  b".replace("  ", " "))

    def test_tracking_row_shares_clamped_percent_and_grouped_counts(self) -> None:
        row = HomeTrackingRow("•", "Test")
        try:
            self.assertEqual((row.bar.minimum(), row.bar.maximum()), (0, 100))
            self.assertEqual(row.bar.objectName(), "HomeTrackingBar")
            self.assertFalse(row.bar.isTextVisible())
            row.set_progress(2, 3)
            self.assertEqual(row.bar.value(), 67)
            self.assertEqual(row.value.text(), "67 %")
            row.set_progress(1234, 2000, show_count=True)
            self.assertEqual(row.bar.value(), 62)
            self.assertEqual(row.value.text(), "1 234 / 2 000")
            row.set_progress(2, 0)
            self.assertEqual(row.bar.value(), 0)
            self.assertEqual(row.value.text(), "0 %")
        finally:
            row.deleteLater()

    def test_main_guide_progress_keeps_home_style_and_starting_value(self) -> None:
        page = HomePage()
        try:
            self.assertEqual(page.progress_bar.objectName(), "HomeProgressBar")
            self.assertEqual((page.progress_bar.minimum(), page.progress_bar.maximum()), (0, 100))
            self.assertFalse(page.progress_bar.isTextVisible())
            self.assertEqual(page.progress_bar.value(), 0)
        finally:
            page.deleteLater()

    def test_waiting_client_then_live_network_updates_same_indicator(self) -> None:
        page = HomePage()
        self.addCleanup(page.deleteLater)
        self.addCleanup(self.app.processEvents)

        page._on_network_status(
            NetworkApplicationStatus(
                running=False, calibrating=False,
                reason="build_fingerprint_unavailable",
            )
        )
        self.assertEqual(page.network_status.text(), "En attente de Dofus")
        self.assertEqual(page.network_indicator.property("state"), "idle")

        page._on_network_status(
            NetworkApplicationStatus(
                running=True, calibrating=False, reason="running",
            )
        )
        self.assertEqual(page.network_status.text(), "Actif")
        self.assertEqual(page.network_indicator.property("state"), "active")


if __name__ == "__main__":
    unittest.main()
