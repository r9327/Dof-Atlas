"""Fast startup must not recalculate the entire installed package SHA-256."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from app.distribution import launcher


class LauncherFastStartTests(unittest.TestCase):
    def _run(self, root: Path, *, full_check: bool):
        sha = "a" * 40
        state = {"active": "v1", "previous": None, "pending": False, "source_sha": sha}
        remote = SimpleNamespace(manifest=SimpleNamespace(
            source_sha=sha, files=[SimpleNamespace(path="AtlasApp/AtlasApp.exe")]))
        executable = root / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe"
        with (patch.object(launcher, "ROOT", root),
              patch.object(launcher, "_logger", return_value=MagicMock()),
              patch.object(launcher, "_run_lock", return_value=MagicMock()),
              patch.object(launcher, "read_state", return_value=state),
              patch.object(launcher, "latest_release", return_value=remote),
              patch.object(launcher, "active_executable", return_value=executable),
              patch.object(launcher, "_launch_with_health", return_value=True),
              patch.object(launcher, "schedule_launcher_upgrade") as upgrade,
              patch.object(launcher, "install_release") as install,
              patch.object(launcher, "verify_file", return_value=True) as checksum):
            launcher.run_update(lambda *_: None, verify_installation=full_check)
            install.assert_not_called()
            upgrade.assert_called_once()
            return checksum.call_count

    def test_normal_launch_skips_full_package_hashing(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self._run(Path(temp), full_check=False), 0)

    def test_explicit_diagnostic_keeps_complete_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self._run(Path(temp), full_check=True), 1)


if __name__ == "__main__":
    unittest.main()
