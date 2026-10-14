"""Updater tests for verified Windows launcher self-upgrade."""
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution.manifest import parse_manifest
from app.distribution.release_client import RemoteRelease, UpdateError
from app.distribution.self_update import stage_launcher
from app.distribution.setup import finish_launcher_upgrade


def remote(binary):
    doc = {
        "protocol_version": 1, "app_version": "1.0", "data_version": "1",
        "schema_version": 1, "source_sha": "a" * 40,
        "entrypoint": "AtlasApp/AtlasApp.exe",
        "files": [{"path": "AtlasApp/AtlasApp.exe", "size": 3,
                   "sha256": hashlib.sha256(b"MZ!").hexdigest()}],
        "launcher_sha256": hashlib.sha256(binary).hexdigest(),
        "launcher_size": len(binary),
    }
    manifest = parse_manifest(json.dumps(doc).encode())
    base = "https://github.com/r9327/Dof-Atlas-App/releases/download/v1/"
    return RemoteRelease("v1", base + "atlas-windows.zip", 42,
                         manifest, base + "DofusAtlas.exe")


class LauncherUpgradeTests(unittest.TestCase):
    def test_download_verified_and_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = b"MZnew-launcher"
            with patch("app.distribution.self_update._open", return_value=io.BytesIO(binary)):
                candidate = stage_launcher(remote(binary), Path(directory))
            self.assertEqual(candidate.read_bytes(), binary)
            with patch("app.distribution.self_update._open", side_effect=AssertionError("network")):
                self.assertEqual(stage_launcher(remote(binary), Path(directory)), candidate)

    def test_corrupt_download_not_published(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("app.distribution.self_update._open", return_value=io.BytesIO(b"MZbad")):
                with self.assertRaises(UpdateError):
                    stage_launcher(remote(b"MZexpected"), Path(directory))
            self.assertFalse(list(Path(directory).glob("*.exe")))

    def test_swap_keeps_previous_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            downloads = base / "DofusAtlas" / "runtime" / "downloads"
            downloads.mkdir(parents=True)
            programs = base / "Programs" / "DofusAtlas"
            programs.mkdir(parents=True)
            target = programs / "DofusAtlas.exe"
            target.write_bytes(b"MZold")
            candidate = downloads / "new.exe"
            candidate.write_bytes(b"MZnew")
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            with patch.dict(os.environ, {"LOCALAPPDATA": str(base)}), patch(
                "app.distribution.setup._wait_for_parent"
            ) as waiter, patch(
                "app.distribution.setup._verify_launcher_starts"
            ) as verify:
                finish_launcher_upgrade(candidate, digest, 123, root=programs)
                waiter.assert_called_once_with(123)
                self.assertEqual(verify.call_count, 2)
            self.assertEqual(target.read_bytes(), b"MZnew")
            self.assertEqual((programs / "DofusAtlas.exe.previous").read_bytes(), b"MZold")

    def test_failure_after_swap_restores_last_working_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            downloads = base / "DofusAtlas" / "runtime" / "downloads"
            downloads.mkdir(parents=True)
            program = base / "Programs" / "DofusAtlas"
            program.mkdir(parents=True)
            original = program / "DofusAtlas.exe"
            original.write_bytes(b"MZprevious-good")
            candidate = downloads / "new.exe"
            candidate.write_bytes(b"MZnew-but-broken")
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            with patch.dict(os.environ, {"LOCALAPPDATA": str(base)}), patch(
                "app.distribution.setup._wait_for_parent"
            ), patch("app.distribution.setup._verify_launcher_starts",
                     side_effect=[None, RuntimeError("failed after replacement")]):
                with self.assertRaisesRegex(RuntimeError, "failed after replacement"):
                    finish_launcher_upgrade(candidate, digest, 123, root=program)
            self.assertEqual(original.read_bytes(), b"MZprevious-good")

    def test_external_candidate_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            program = base / "Programs"
            program.mkdir()
            (program / "DofusAtlas.exe").write_bytes(b"MZold")
            candidate = base / "untrusted.exe"
            candidate.write_bytes(b"MZnew")
            with patch.dict(os.environ, {"LOCALAPPDATA": str(base)}):
                with self.assertRaises(ValueError):
                    finish_launcher_upgrade(candidate, hashlib.sha256(b"MZnew").hexdigest(),
                                            123, root=program)
            self.assertEqual((program / "DofusAtlas.exe").read_bytes(), b"MZold")


if __name__ == "__main__":
    unittest.main()
