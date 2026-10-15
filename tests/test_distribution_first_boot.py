"""The first boot must expose the real failure, without breaking offline starts."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution import launcher
from app.distribution.release_client import UpdateError


class FirstBootDiagnosticsTests(unittest.TestCase):
    def test_first_boot_reports_actual_github_failure(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(launcher, "ROOT", Path(directory)), \
             patch.object(launcher, "latest_release",
                          side_effect=UpdateError("HTTP Error 403")), \
             patch.object(launcher, "active_executable", return_value=None):
            progress = []
            with self.assertRaisesRegex(UpdateError,
                                        "Premiere installation impossible : HTTP Error 403"):
                launcher.run_update(lambda message, value: progress.append((message, value)))
            self.assertIn(("Mise a jour indisponible — mode hors ligne", 90), progress)

    def test_offline_launch_of_existing_version_still_works(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(launcher, "ROOT", Path(directory)), \
             patch.object(launcher, "latest_release",
                          side_effect=UpdateError("HTTP Error 503")), \
             patch.object(launcher, "active_executable",
                          return_value=Path(directory) / "AtlasApp.exe"), \
             patch.object(launcher, "_launch_with_health", return_value=True) as launch:
            launcher.run_update(lambda message, value: None)
            launch.assert_called_once()

    def test_first_boot_preserves_failed_download_reason(self):
        from unittest.mock import Mock
        remote = Mock()
        remote.manifest.source_sha = "a" * 40
        remote.manifest.delta = None
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(launcher, "ROOT", Path(directory)), \
             patch.object(launcher, "latest_release", return_value=remote), \
             patch.object(launcher, "active_executable", return_value=None), \
             patch.object(launcher, "download_archive",
                          side_effect=UpdateError("Multipart archive SHA-256 mismatch")):
            with self.assertRaisesRegex(UpdateError,
                                        "Multipart archive SHA-256 mismatch"):
                launcher.run_update(lambda message, value: None)


if __name__ == "__main__":
    unittest.main()
