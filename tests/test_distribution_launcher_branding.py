"""Guard the standalone launcher UI and automatic no-download launch path.

These tests are stdlib-only and need neither a Windows desktop nor Qt.
"""
from __future__ import annotations

import ast
import inspect
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.distribution import launcher, launcher_ui


class LauncherBrandingTests(unittest.TestCase):
    def test_both_palettes_match_real_app_ui_and_remain_stdlib_only(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "app/ui/unity_skin.py").read_text(encoding="utf-8")
        palette = launcher_ui.UNITY_PALETTE
        self.assertEqual(launcher_ui.COLORS, palette)
        for local, upstream in (
            ("background", "BG"), ("panel", "PANEL"), ("border", "BORDER"),
            ("text", "TEXT"), ("muted", "TEXT_MUTED"), ("accent", "GREEN"),
            ("accent_hover", "GREEN_HOVER"),
        ):
            self.assertIn(f'"{upstream}": "{palette[local]}"', source)
        tree = ast.parse(inspect.getsource(launcher_ui))
        imports = [
            node.module or "" for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertFalse(any(name.startswith(("PySide6", "app.ui")) for name in imports))

    def test_launcher_does_not_allow_legacy_palette(self):
        self.assertFalse(hasattr(launcher_ui, "ATLAS_PALETTE"))
        self.assertFalse(hasattr(launcher_ui, "palette_for_theme"))
        self.assertEqual(launcher_ui.COLORS, launcher_ui.UNITY_PALETTE)

    def test_embedded_logo_is_real_png_extracted_from_existing_atlas_icon(self):
        import base64
        import struct
        data = base64.b64decode(launcher_ui.LOGO_PNG_BASE64, validate=True)
        self.assertTrue(data.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertEqual(struct.unpack(">II", data[16:24]), (64, 64))

    def test_no_menu_or_invented_secondary_titles_in_normal_launch(self):
        source = inspect.getsource(launcher.main)
        self.assertIn("add_header(tk, window)", source)
        self.assertNotIn("add_footer(", source)
        self.assertNotIn("phase_for_message", source)
        self.assertNotIn("ATLAS  /  DESKTOP", inspect.getsource(launcher_ui))
        for text in ("Menu", "À propos", "Lancement, mises à jour et préparation"):
            self.assertNotIn(text, source)
        examples = {
            "Differentiel : 30 %": "Téléchargement des fichiers modifiés…",
            "Telechargement : 60 %": "Téléchargement de la mise à jour…",
            "Installation differentielle...": "Installation des fichiers modifiés…",
            "Verification des mises a jour...": "Verification des mises a jour...",
        }
        for status, expected in examples.items():
            self.assertEqual(launcher_ui.display_message(status), expected)

    def test_branding_widgets_are_stdlib_and_have_only_logo_and_title(self):
        tk, window, style = MagicMock(), MagicMock(), MagicMock()
        launcher_ui.add_header(tk, window)
        launcher_ui.progress_style(style)
        style.theme_use.assert_called_once_with("clam")
        style.configure.assert_called_once()
        self.assertEqual(tk.Label.call_count, 2)
        self.assertEqual(launcher_ui.button_options()["bg"],
                         launcher_ui.COLORS["accent"])

    def test_preload_has_exact_same_minimal_surface_and_real_state_progress(self):
        source = (Path(__file__).resolve().parents[1] /
                  "app/ui/preload_popup.py").read_text(encoding="utf-8")
        for required in (
            "atlas_application_icon", 'QLabel("Dofus Atlas")',
            'self.current_label = QLabel(', 'self.progress = QProgressBar()',
            "PRELOAD_TASK_ORDER", "self.progress.setValue(completed)",
            "readyForMainWindow.emit()",
        ):
            self.assertIn(required, source)
        for forbidden in ("PreloadTaskRow", "PreloadPopupElapsed", "Recherche des Dofus"):
            self.assertNotIn(forbidden, source)


class OfficialAppReleaseTests(unittest.TestCase):
    def test_public_release_is_exclusively_in_dof_atlas_app(self):
        from app.distribution import release_client
        repo = "r9327/Dof-Atlas-App"
        self.assertEqual(release_client.REPO, repo)
        self.assertEqual(
            release_client.API_URL,
            f"https://api.github.com/repos/{repo}/releases/latest",
        )
        self.assertEqual(
            release_client.CHANNEL_URL,
            f"https://github.com/{repo}/releases/latest/download/atlas-channel.json",
        )
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/atlas-windows-distribution.yml").read_text(
                        encoding="utf-8"
                    )
        self.assertIn("--repo r9327/Dof-Atlas-App", workflow)
        self.assertIn("repository: r9327/Dof-Atlas-App", workflow)
        self.assertNotIn("--repo r9327/Dof-Atlas \\", workflow)

    def test_windows_pr_candidate_build_is_unpublished_and_exact_branch_only(self):
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/atlas-windows-distribution.yml").read_text(
                        encoding="utf-8"
                    )
        self.assertIn(
            "github.head_ref == 'feature/unified-launcher-auto-update-preload-20261026'",
            workflow,
        )
        self.assertIn("github.event.action == 'ready_for_review'", workflow)
        self.assertIn("atlas-windows-full-candidate-", workflow)
        self.assertIn("if: github.event_name == 'workflow_run'", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("--repo r9327/Dof-Atlas-App", workflow)


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
