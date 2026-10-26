"""Guard the standalone launcher UI and automatic no-download launch path.

These tests are stdlib-only and need neither a Windows desktop nor Qt.
"""
from __future__ import annotations

import ast
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.distribution import launcher, launcher_ui


class LauncherBrandingTests(unittest.TestCase):
    def test_uses_default_app_palette_without_importing_qt(self):
        theme = (Path(__file__).resolve().parents[1] / "app/ui/theme.py").read_text(
            encoding="utf-8"
        )
        for launcher_key, app_key in (
            ("background", "BG"), ("panel", "PANEL"), ("border", "BORDER"),
            ("text", "TEXT"), ("muted", "TEXT_MUTED"), ("accent", "GREEN"),
        ):
            value = launcher_ui.COLORS[launcher_key]
            self.assertIn(f'"{app_key}": "{value}"', theme)
        tree = ast.parse(inspect.getsource(launcher_ui))
        imports = [
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertFalse(any(name.startswith(("PySide6", "app.ui")) for name in imports))

    def test_progress_labels_are_phases_not_fake_preload_percentages(self):
        examples = {
            "Verification des mises a jour...": "VÉRIFICATION GITHUB",
            "Atlas est a jour": "VÉRIFICATION GITHUB",
            "Differentiel : 30 %": "TÉLÉCHARGEMENT",
            "Telechargement complet de la nouvelle version...": "TÉLÉCHARGEMENT",
            "Installation differentielle...": "INSTALLATION",
            "Lancement de Dofus Atlas...": "OUVERTURE D'ATLAS",
            "Mise a jour indisponible — mode hors ligne": "MODE HORS LIGNE",
        }
        for message, expected in examples.items():
            with self.subTest(message=message):
                self.assertEqual(launcher_ui.phase_for_message(message), expected)

    def test_branding_widgets_do_not_require_qt_or_real_window(self):
        tk, window, style = MagicMock(), MagicMock(), MagicMock()
        launcher_ui.add_header(tk, window)
        launcher_ui.add_footer(tk, window)
        launcher_ui.progress_style(style)
        style.theme_use.assert_called_once_with("clam")
        style.configure.assert_called_once()
        self.assertEqual(launcher_ui.button_options()["bg"],
                         launcher_ui.COLORS["accent"])


class LauncherAutomaticStartTests(unittest.TestCase):
    def test_no_release_change_starts_existing_exe_without_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = {
                "active": "v1", "pending": False, "previous": None,
                "source_sha": "a" * 40,
            }
            exe = root / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe"
            events = []
            with (
                patch.object(launcher, "ROOT", root),
                patch.object(launcher, "_logger", return_value=MagicMock()),
                patch.object(launcher, "_run_lock", return_value=MagicMock()),
                patch.object(launcher, "read_state", return_value=state),
                patch.object(launcher, "active_executable", return_value=exe),
                patch.object(launcher, "latest_release", return_value=None) as check,
                patch.object(launcher, "download_archive") as download,
                patch.object(launcher, "install_release") as install,
                patch.object(launcher, "_launch_with_health", return_value=True) as start,
            ):
                launcher.run_update(lambda label, percent: events.append(label))
            check.assert_called_once_with(installed_source_sha="a" * 40)
            download.assert_not_called()
            install.assert_not_called()
            start.assert_called_once()
            self.assertIn("Atlas est a jour", events)
            self.assertIn("Dofus Atlas est pret", events)
            self.assertFalse(launcher._requires_updater_window("Atlas est a jour"))
            self.assertTrue(launcher._requires_updater_window("Differentiel : 30 %"))


if __name__ == "__main__":
    unittest.main()
