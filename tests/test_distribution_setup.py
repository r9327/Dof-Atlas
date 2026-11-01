"""Validate per-user Windows installation without requiring admin/Windows APIs."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution.setup import install_launcher


class SetupTests(unittest.TestCase):
    def test_install_launcher_creates_stable_binary_and_preserves_user_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "DofusAtlas.exe"
            source.write_bytes(b"MZ" + b"launcher-one")
            app = root / "Programs" / "DofusAtlas"
            personal = root / "DofusAtlas" / "user" / "data"
            personal.mkdir(parents=True)
            profile = personal / "client_profiles.json"
            profile.write_text('{"character":"unchanged"}', encoding="utf-8")
            with patch("app.distribution.setup._create_shortcut") as shortcut:
                result = install_launcher(source, app)
                self.assertEqual(result, app / "DofusAtlas.exe")
                self.assertEqual(result.read_bytes(), source.read_bytes())
                shortcut.assert_called_once_with(result)
                source.write_bytes(b"MZ" + b"launcher-two")
                second = install_launcher(source, app)
                self.assertEqual(second.read_bytes(), source.read_bytes())
            self.assertEqual(profile.read_text(encoding="utf-8"), '{"character":"unchanged"}')

    def test_repeat_setup_skips_rewriting_identical_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "DofusAtlas.exe"
            source.write_bytes(b"MZ" + b"unchanged-launcher")
            app = root / "Programs" / "DofusAtlas"
            with patch("app.distribution.setup._create_shortcut") as shortcut:
                installed = install_launcher(source, app)
                original_stat = installed.stat()
                with patch("app.distribution.setup.tempfile.mkstemp",
                           side_effect=AssertionError("unchanged EXE must not be staged")):
                    self.assertEqual(install_launcher(source, app), installed)
                self.assertEqual(installed.stat().st_mtime_ns, original_stat.st_mtime_ns)
                self.assertEqual(installed.read_bytes(), source.read_bytes())
                self.assertEqual(shortcut.call_count, 2)

    def test_same_size_but_changed_launcher_is_reinstalled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "DofusAtlas.exe"
            source.write_bytes(b"MZcorrect")
            app = root / "Programs" / "DofusAtlas"
            with patch("app.distribution.setup._create_shortcut"):
                installed = install_launcher(source, app)
                installed.write_bytes(b"MZchanged")  # Same length, wrong checksum.
                install_launcher(source, app)
            self.assertEqual(installed.read_bytes(), b"MZcorrect")

    def test_reject_non_executable_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "fake.exe"
            source.write_bytes(b"not-a-win-binary")
            with self.assertRaises(ValueError):
                install_launcher(source, root / "install")
            self.assertFalse((root / "install").exists())


if __name__ == "__main__":
    unittest.main()
