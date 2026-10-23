"""Fast official-release check without re-downloading the 13 MB manifest."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.distribution import launcher, release_client
from app.distribution.release_client import UpdateError


class StableReleaseShortcutTests(unittest.TestCase):
    def test_exact_stable_tag_skips_manifest_only_for_installed_sha(self) -> None:
        sha = "a" * 40
        doc = {"tag_name": "sha-" + sha[:12], "draft": False, "prerelease": False}
        with patch.object(release_client, "_read_limited", return_value=json.dumps(doc).encode()), \
             patch.object(release_client, "_latest_release_api", side_effect=AssertionError("manifest downloaded")):
            self.assertIsNone(release_client.latest_release(installed_source_sha=sha))

    def test_changed_tag_requires_full_manifest_validation(self) -> None:
        sha = "a" * 40
        doc = {"tag_name": "sha-" + "b" * 12, "draft": False, "prerelease": False}
        candidate = object()
        with patch.object(release_client, "_read_limited", return_value=json.dumps(doc).encode()), \
             patch.object(release_client, "_latest_release_api", return_value=candidate) as full:
            self.assertIs(release_client.latest_release(installed_source_sha=sha), candidate)
            full.assert_called_once()

    def test_invalid_or_unreachable_latest_tag_cannot_skip_manifest(self) -> None:
        sha = "a" * 40
        candidate = object()
        with patch.object(release_client, "_read_limited", side_effect=UpdateError("GitHub unavailable")), \
             patch.object(release_client, "_latest_release_api", return_value=candidate):
            self.assertIs(release_client.latest_release(installed_source_sha=sha), candidate)

    def test_diagnostic_check_always_uses_validated_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sha = "a" * 40
            exe = root / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe"
            state = {"active": "v1", "previous": None, "pending": False, "source_sha": sha}
            remote = SimpleNamespace(manifest=SimpleNamespace(source_sha=sha, files=[]))
            with patch.object(launcher, "ROOT", root), \
                 patch.object(launcher, "_logger", return_value=MagicMock()), \
                 patch.object(launcher, "_run_lock", return_value=MagicMock()), \
                 patch.object(launcher, "read_state", return_value=state), \
                 patch.object(launcher, "active_executable", return_value=exe), \
                 patch.object(launcher, "latest_release", return_value=remote) as latest, \
                 patch.object(launcher, "_launch_with_health", return_value=True), \
                 patch.object(launcher, "schedule_launcher_upgrade"), \
                 patch.object(launcher, "verify_file", return_value=True):
                launcher.run_update(lambda *_: None, verify_installation=True)
                latest.assert_called_once_with(installed_source_sha=None)

    def test_same_release_launches_without_installing_or_upgrading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sha = "a" * 40
            exe = root / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe"
            state = {"active": "v1", "previous": None, "pending": False, "source_sha": sha}
            with patch.object(launcher, "ROOT", root), \
                 patch.object(launcher, "_logger", return_value=MagicMock()), \
                 patch.object(launcher, "_run_lock", return_value=MagicMock()), \
                 patch.object(launcher, "read_state", return_value=state), \
                 patch.object(launcher, "active_executable", return_value=exe), \
                 patch.object(launcher, "latest_release", return_value=None) as latest, \
                 patch.object(launcher, "_launch_with_health", return_value=True) as boot, \
                 patch.object(launcher, "schedule_launcher_upgrade") as upgrade, \
                 patch.object(launcher, "install_release") as install:
                launcher.run_update(lambda *_: None)
                latest.assert_called_once_with(installed_source_sha=sha)
                install.assert_not_called()
                upgrade.assert_not_called()
                boot.assert_called_once()


if __name__ == "__main__":
    unittest.main()
