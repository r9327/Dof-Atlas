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
