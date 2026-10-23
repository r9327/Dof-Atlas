"""The first boot must expose the real failure, without breaking offline starts."""
from __future__ import annotations

import tempfile
import unittest
import hashlib
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.distribution import launcher
from app.distribution.release_client import UpdateError
from app.distribution.release_client import RemoteRelease
from app.distribution.install import install_release, mark_healthy, read_state, slot_path
from app.distribution.manifest import parse_manifest


class FirstBootDiagnosticsTests(unittest.TestCase):
    def test_explicit_integrity_check_repairs_corrupt_resources_without_touching_user_data(self):
        files = {"AtlasApp/AtlasApp.exe": b"MZ!",
                 "AtlasApp/_internal/data/quests.json": b"{}\n"}
        manifest = parse_manifest(json.dumps({
            "protocol_version": 1, "app_version": "1", "data_version": "1",
            "schema_version": 1, "source_sha": "a" * 40,
            "entrypoint": "AtlasApp/AtlasApp.exe",
            "files": [{"path": name, "size": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()}
                      for name, data in files.items()],
        }).encode())
        for damage in ("healthy", "missing", "same-size corruption"):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                archive = base / "release.zip"
                with zipfile.ZipFile(archive, "w") as output:
                    for name, data in files.items():
                        output.writestr(name, data)
                root = base / "runtime"
                install_release(root, archive, manifest)
                mark_healthy(root)
                resource = slot_path(root, read_state(root)["active"]) / next(
                    name for name in files if name.endswith(".json"))
                if damage == "missing":
                    resource.unlink()
                elif damage != "healthy":
                    resource.write_bytes(b"BAD")
                user = base / "user"
                user.mkdir()
                marker = user / "settings.json"
                marker.write_bytes(b'{"personal":true}')
                remote = RemoteRelease("v1", "", archive.stat().st_size, manifest)
                with (
                    patch.object(launcher, "ROOT", root),
                    patch.object(launcher, "USER_DIR", user),
                    patch.object(launcher, "latest_release", return_value=remote),
                    patch.object(launcher, "download_archive", return_value=archive) as download,
                    patch.object(launcher, "_launch_with_health", return_value=True),
                    patch.object(launcher, "schedule_launcher_upgrade"),
                ):
                    launcher.run_update(lambda *_: None, verify_installation=True)
                self.assertEqual(download.call_count, int(damage != "healthy"))
                self.assertEqual(resource.read_bytes(), b"{}\n")
                self.assertEqual(marker.read_bytes(), b'{"personal":true}')
                self.assertFalse(read_state(root)["pending"])

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
            self.assertNotIn(("Mise a jour indisponible — mode hors ligne", 90), progress)

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
        remote.manifest.files = ()
        remote.manifest.archive_parts = ()
        remote.archive_size = 0
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
