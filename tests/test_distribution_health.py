"""Ensure a splash-ready acknowledgment is followed by process stability."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import os

from app.distribution.health import announce_home_ready, announce_ready
from app.distribution.launcher import _is_application_handoff

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

    def test_home_capability_waits_for_separate_home_ack(self):
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            (root / ".health").mkdir()
            (root / ".health" / "fixed.ready").write_text("123", encoding="utf-8")
            (root / ".health" / "fixed.capable").write_text("123", encoding="utf-8")
            (root / ".health" / "fixed.home").write_text("123", encoding="utf-8")
            process = SimpleNamespace(poll=lambda: None)
            self.assertTrue(self.launch_with_process(root, process, [10, 10, 13, 14, 16]))
            self.assertFalse(list((root / ".health").iterdir()))

    def test_process_exit_before_home_ack_is_safe_to_rollback(self):
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            health = root / ".health"
            health.mkdir()
            (health / "fixed.ready").write_text("123", encoding="utf-8")
            (health / "fixed.capable").write_text("123", encoding="utf-8")
            process = SimpleNamespace(poll=lambda: 17)
            self.assertFalse(self.launch_with_process(root, process, [10, 10]))
            self.assertFalse(list(health.iterdir()))

    def test_home_timeout_while_process_alive_must_not_trigger_rollback(self):
        from app.distribution.release_client import UpdateError
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            (root / ".health").mkdir()
            (root / ".health" / "fixed.ready").write_text("123", encoding="utf-8")
            (root / ".health" / "fixed.capable").write_text("123", encoding="utf-8")
            process = SimpleNamespace(poll=lambda: None)
            with self.assertRaisesRegex(UpdateError, "Home n'a pas confirme"):
                self.launch_with_process(root, process, [10, 141])
            self.assertFalse(list((root / ".health").iterdir()))

    def test_legacy_and_new_home_health_markers_are_distinct(self):
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            ready, home = root / "fixed.ready", root / "fixed.home"
            with patch.dict(os.environ, {
                "DOFUS_ATLAS_HEALTH_FILE": str(ready),
                "DOFUS_ATLAS_HOME_HEALTH_FILE": str(home),
            }):
                announce_ready()
                self.assertTrue(ready.is_file())
                self.assertTrue(home.with_suffix(".capable").is_file())
                self.assertFalse(home.exists())
                announce_home_ready()
                self.assertTrue(home.is_file())
                announce_home_ready()  # Repeated Qt callback stays harmless.

    def test_old_app_health_marker_keeps_legacy_semantics(self):
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            ready = root / "fixed.ready"
            with patch.dict(os.environ, {"DOFUS_ATLAS_HEALTH_FILE": str(ready)}, clear=True):
                announce_ready()
                self.assertTrue(ready.exists())
                self.assertEqual(list(root.glob("*.capable")), [])

    def test_handoff_is_only_the_launch_transition(self):
        self.assertTrue(_is_application_handoff("Lancement de Dofus Atlas..."))
        self.assertFalse(_is_application_handoff("Installation differentielle..."))
        self.assertFalse(_is_application_handoff("Echec : Home indisponible"))


if __name__ == "__main__":
    unittest.main()
