"""No download or Windows API required for the persistent install selector."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution import install_location as loc
from app.distribution.release_client import UpdateError


class RuntimeLocationTests(unittest.TestCase):
    def test_custom_runtime_root_persists_across_launcher_restarts(self):
        with tempfile.TemporaryDirectory() as temp:
            user = Path(temp) / "AppData" / "DofusAtlas"
            custom = Path(temp) / "Games" / "DofusAtlas" / "runtime"
            with (patch.object(loc, "APP_DATA", user),
                  patch.object(loc, "_SETTINGS", user / "installation.json"),
                  patch.object(loc, "DEFAULT_RUNTIME", user / "runtime")):
                self.assertEqual(loc.runtime_root(), user / "runtime")
                self.assertEqual(loc.set_runtime_root(custom), custom.resolve())
                self.assertEqual(loc.runtime_root(), custom.resolve())
                self.assertEqual(json.loads((user / "installation.json").read_text())["schema_version"], 1)
                self.assertFalse(custom.exists(), "Path selection must not extract or install files")

    def test_invalid_path_cannot_replace_last_working_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            user = Path(temp) / "Data"
            with (patch.object(loc, "APP_DATA", user),
                  patch.object(loc, "_SETTINGS", user / "installation.json")):
                location = Path(temp) / "Good" / "runtime"
                loc.set_runtime_root(location)
                with self.assertRaises(UpdateError):
                    loc.set_runtime_root(Path("relative/folder"))
                self.assertEqual(loc.runtime_root(), location.resolve())
                (user / "installation.json").write_text('{"schema_version":99}')
                with self.assertRaises(UpdateError):
                    loc.runtime_root()

    def test_symlink_destination_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "target"
            target.mkdir()
            link = Path(temp) / "alias"
            try:
                link.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable on this host")
            with self.assertRaises(UpdateError):
                loc.set_runtime_root(link)


if __name__ == "__main__":
    unittest.main()
