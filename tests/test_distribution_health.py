"""Ensure a splash-ready acknowledgment is followed by process stability."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.distribution.launcher import _launch_with_health


class WindowHealthTests(unittest.TestCase):
    def launch_with_process(self, root: Path, process, now):
        health = root / ".health"
        health.mkdir(parents=True)
        (health / "fixed.ready").write_text("123", encoding="utf-8")
        fake_exe = root / "AtlasApp.exe"
        fake_exe.write_bytes(b"MZ")
        with patch("app.distribution.launcher.ROOT", root), \
             patch("app.distribution.launcher.USER_DIR", root / "user"), \
             patch("app.distribution.launcher.prepare_user_data"), \
             patch("app.distribution.launcher.uuid.uuid4", return_value=SimpleNamespace(hex="fixed")), \
             patch("app.distribution.launcher.subprocess.Popen", return_value=process), \
             patch("app.distribution.launcher.time.monotonic", side_effect=now), \
             patch("app.distribution.launcher.time.sleep"):
            return _launch_with_health(fake_exe, lambda *_: None, settle_seconds=2)

    def test_exit_just_after_ready_rejects_candidate(self):
        with tempfile.TemporaryDirectory() as location:
            process = SimpleNamespace(poll=lambda: 17)
            self.assertFalse(self.launch_with_process(Path(location), process, [0, 0.1]))

    def test_stable_window_passes_without_extra_gui_launches(self):
        with tempfile.TemporaryDirectory() as location:
            process = SimpleNamespace(poll=lambda: None)
            self.assertTrue(self.launch_with_process(Path(location), process, [10, 10, 13]))


if __name__ == "__main__":
    unittest.main()
