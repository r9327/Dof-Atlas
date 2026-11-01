"""Ensure a splash-ready acknowledgment is followed by process stability."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import os

from app.distribution.health import announce_home_ready, announce_ready
from app.distribution.launcher import _is_application_handoff

from app.distribution.launcher import _launch_with_health
from app.distribution import launcher


class WindowHealthTests(unittest.TestCase):
    def launch_with_process(self, root: Path, process, now, *, ready_payload="123"):
        health = root / ".health"
        health.mkdir(parents=True, exist_ok=True)
        (health / "fixed.ready").write_text(ready_payload, encoding="utf-8")
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
            process = SimpleNamespace(pid=123, poll=lambda: 17)
            self.assertFalse(self.launch_with_process(Path(location), process, [0, 0.1]))

    def test_handoff_status_is_emitted_only_after_qt_ack(self):
        with tempfile.TemporaryDirectory() as location:
            messages = []
            root = Path(location)
            fake_exe = root / "AtlasApp.exe"
            fake_exe.write_bytes(b"MZ")
            (root / ".health").mkdir()
            (root / ".health" / "fixed.ready").write_text("123", encoding="ascii")
            process = SimpleNamespace(pid=123, poll=lambda: None)
            with (
                patch.object(launcher, "ROOT", root),
                patch.object(launcher, "USER_DIR", root / "user"),
                patch.object(launcher, "prepare_user_data"),
                patch.object(launcher.uuid, "uuid4",
                             return_value=SimpleNamespace(hex="fixed")),
                patch.object(launcher.subprocess, "Popen", return_value=process),
                patch.object(launcher.time, "monotonic", side_effect=[1, 2, 4]),
                patch.object(launcher.time, "sleep"),
            ):
                self.assertTrue(_launch_with_health(
                    fake_exe, lambda status, *_: messages.append(status),
                    settle_seconds=2,
                ))
            self.assertEqual(messages, [
                "Lancement de Dofus Atlas...", "Prechargement Qt actif",
            ])

    def test_stable_window_passes_without_extra_gui_launches(self):
        with tempfile.TemporaryDirectory() as location:
            process = SimpleNamespace(pid=123, poll=lambda: None)
            self.assertTrue(self.launch_with_process(Path(location), process, [10, 10, 13]))

    def test_home_capability_waits_for_separate_home_ack(self):
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            (root / ".health").mkdir()
            (root / ".health" / "fixed.ready").write_text("123", encoding="utf-8")
            (root / ".health" / "fixed.capable").write_text("123", encoding="utf-8")
            (root / ".health" / "fixed.home").write_text("123", encoding="utf-8")
            process = SimpleNamespace(pid=123, poll=lambda: None)
            self.assertTrue(self.launch_with_process(root, process, [10, 10, 13, 14, 16]))
            self.assertFalse(list((root / ".health").iterdir()))

    def test_process_exit_before_home_ack_is_safe_to_rollback(self):
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            health = root / ".health"
            health.mkdir()
            (health / "fixed.ready").write_text("123", encoding="utf-8")
            (health / "fixed.capable").write_text("123", encoding="utf-8")
            process = SimpleNamespace(pid=123, poll=lambda: 17)
            self.assertFalse(self.launch_with_process(root, process, [10, 10]))
            self.assertFalse(list(health.iterdir()))

    def test_long_home_wait_updates_visible_status_without_premature_handoff(self):
        from app.distribution.release_client import UpdateError
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            health = root / ".health"
            health.mkdir()
            (health / "fixed.ready").write_text("123", encoding="ascii")
            (health / "fixed.capable").write_text("123", encoding="ascii")
            fake_exe = root / "AtlasApp.exe"
            fake_exe.write_bytes(b"MZ")
            process = SimpleNamespace(pid=123, poll=lambda: None)
            messages = []
            with (
                patch.object(launcher, "ROOT", root),
                patch.object(launcher, "USER_DIR", root / "user"),
                patch.object(launcher, "prepare_user_data"),
                patch.object(launcher.uuid, "uuid4",
                             return_value=SimpleNamespace(hex="fixed")),
                patch.object(launcher.subprocess, "Popen", return_value=process),
                patch.object(launcher.time, "monotonic",
                             side_effect=[10] + [11] * 25 + [141]),
                patch.object(launcher.time, "sleep"),
            ):
                with self.assertRaisesRegex(UpdateError, "Home n'a pas confirme"):
                    _launch_with_health(
                        fake_exe, lambda status, pct: messages.append((status, pct))
                    )
            self.assertIn(("Attente de Home (5 s)", 98), messages)
            self.assertNotIn(("Dofus Atlas est pret", 100), messages)
            self.assertNotIn(("Prechargement Qt actif", 98), messages)
            self.assertEqual(list(health.iterdir()), [])

    def test_home_timeout_while_process_alive_must_not_trigger_rollback(self):
        from app.distribution.release_client import UpdateError
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            (root / ".health").mkdir()
            (root / ".health" / "fixed.ready").write_text("123", encoding="utf-8")
            (root / ".health" / "fixed.capable").write_text("123", encoding="utf-8")
            process = SimpleNamespace(pid=123, poll=lambda: None)
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

    def test_empty_ready_marker_blocks_rollback_while_app_still_alive(self):
        from app.distribution.release_client import UpdateError
        with tempfile.TemporaryDirectory() as location:
            process = SimpleNamespace(pid=123, poll=lambda: None)
            with self.assertRaisesRegex(UpdateError, "reste en cours"):
                self.launch_with_process(
                    Path(location), process, [], ready_payload=""
                )

    def test_wrong_ready_pid_blocks_rollback_while_app_still_alive(self):
        from app.distribution.release_client import UpdateError
        with tempfile.TemporaryDirectory() as location:
            process = SimpleNamespace(pid=123, poll=lambda: None)
            with self.assertRaisesRegex(UpdateError, "reste en cours"):
                self.launch_with_process(
                    Path(location), process, [], ready_payload="999"
                )

    def test_wrong_home_pid_does_not_complete_handoff(self):
        from app.distribution.release_client import UpdateError
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            health = root / ".health"
            health.mkdir()
            (health / "fixed.capable").write_text("123", encoding="utf-8")
            (health / "fixed.home").write_text("999", encoding="utf-8")
            process = SimpleNamespace(pid=123, poll=lambda: None)
            with self.assertRaisesRegex(UpdateError, "Home n'a pas confirme"):
                self.launch_with_process(root, process, [10, 141])
            self.assertFalse(list(health.iterdir()))

    def test_wrong_capability_pid_is_never_legacy_downgrade(self):
        from app.distribution.release_client import UpdateError
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            health = root / ".health"
            health.mkdir()
            (health / "fixed.capable").write_text("999", encoding="utf-8")
            process = SimpleNamespace(pid=123, poll=lambda: None)
            with self.assertRaisesRegex(UpdateError, "Confirmation de lancement Atlas invalide"):
                self.launch_with_process(root, process, [])
            self.assertFalse(list(health.iterdir()))

    def test_runtime_migration_holds_both_existing_locks_until_copy_finishes(self):
        root = Path("DofusAtlas-new-runtime")
        launcher_lock = MagicMock()
        instance = MagicMock()
        instance.acquire.return_value = True
        progress = MagicMock()

        def copy_checked(target, *, progress=None):
            self.assertEqual(target, root)
            self.assertIs(progress, expected_progress)
            launcher_lock.close.assert_not_called()
            instance.release.assert_not_called()
            return target

        expected_progress = progress
        with (
            patch.object(launcher, "_run_lock", return_value=launcher_lock),
            patch.object(launcher, "SingleInstanceGuard", return_value=instance),
            patch.object(launcher, "relocate_runtime", side_effect=copy_checked) as copy,
        ):
            self.assertEqual(
                launcher._relocate_runtime_safely(root, progress), root
            )
        copy.assert_called_once()
        instance.acquire.assert_called_once()
        instance.release.assert_called_once()
        launcher_lock.close.assert_called_once()

    def test_runtime_migration_refuses_live_gui_without_copying(self):
        lock = MagicMock()
        instance = MagicMock()
        instance.acquire.return_value = False
        with (
            patch.object(launcher, "_run_lock", return_value=lock),
            patch.object(launcher, "SingleInstanceGuard", return_value=instance),
            patch.object(launcher, "relocate_runtime") as copy,
        ):
            with self.assertRaisesRegex(UpdateError, "Fermez Dofus Atlas"):
                launcher._relocate_runtime_safely(Path("other"))
        copy.assert_not_called()
        instance.release.assert_not_called()
        lock.close.assert_called_once()

    def test_runtime_migration_releases_both_locks_on_interrupted_copy(self):
        lock = MagicMock()
        instance = MagicMock()
        instance.acquire.return_value = True
        with (
            patch.object(launcher, "_run_lock", return_value=lock),
            patch.object(launcher, "SingleInstanceGuard", return_value=instance),
            patch.object(launcher, "relocate_runtime",
                         side_effect=OSError("Interrupted drive")) as copy,
        ):
            with self.assertRaisesRegex(OSError, "Interrupted drive"):
                launcher._relocate_runtime_safely(Path("unavailable"))
        copy.assert_called_once()
        instance.release.assert_called_once()
        lock.close.assert_called_once()

    def test_runtime_migration_refuses_busy_updater_before_gui_probe(self):
        with (
            patch.object(launcher, "_run_lock",
                         side_effect=UpdateError("Dofus Atlas est deja en cours")),
            patch.object(launcher, "SingleInstanceGuard") as instance,
            patch.object(launcher, "relocate_runtime") as copy,
        ):
            with self.assertRaisesRegex(UpdateError, "deja en cours"):
                launcher._relocate_runtime_safely(Path("another"))
        instance.assert_not_called()
        copy.assert_not_called()

    def test_live_atlas_refuses_rollback_download_or_second_launch(self):
        with tempfile.TemporaryDirectory() as location:
            guard = MagicMock()
            guard.acquire.return_value = False  # main.py owns mutex
            messages = []
            with (
                patch.object(launcher, "ROOT", Path(location)),
                patch.object(launcher, "_logger", return_value=MagicMock()),
                patch.object(launcher, "_run_lock", return_value=MagicMock()),
                patch.object(launcher, "SingleInstanceGuard", return_value=guard),
                patch.object(launcher, "read_state", side_effect=AssertionError("no state mutations")),
                patch.object(launcher, "rollback_pending", side_effect=AssertionError("no rollback")),
                patch.object(launcher, "latest_release", side_effect=AssertionError("no update check")),
                patch.object(launcher, "_launch_with_health", side_effect=AssertionError("no second spawn")),
                patch.object(launcher, "recover_data_packs_on_launch",
                             side_effect=AssertionError("no recovery while running")),
            ):
                launcher.run_update(lambda label, value: messages.append((label, value)))
            self.assertEqual(messages, [("Dofus Atlas est deja ouvert", 100)])
            guard.acquire.assert_called_once()
            guard.release.assert_not_called()  # loser closed its native handle

    def test_idle_atlas_probe_releases_mutex_after_failed_recovery(self):
        with tempfile.TemporaryDirectory() as location:
            guard = MagicMock()
            guard.acquire.return_value = True
            def fail_recovery(*_args):
                guard.release.assert_not_called()
                raise RuntimeError("reached recovery")

            with (
                patch.object(launcher, "ROOT", Path(location)),
                patch.object(launcher, "_logger", return_value=MagicMock()),
                patch.object(launcher, "_run_lock", return_value=MagicMock()),
                patch.object(launcher, "SingleInstanceGuard", return_value=guard),
                patch.object(launcher, "recover_data_packs_on_launch",
                             side_effect=fail_recovery),
            ):
                with self.assertRaisesRegex(RuntimeError, "reached recovery"):
                    launcher.run_update(lambda *_: None)
            guard.acquire.assert_called_once()
            guard.release.assert_called_once()

    def test_rollback_refused_when_other_atlas_acquires_mutex_during_spawn(self):
        from app.distribution.release_client import UpdateError
        with tempfile.TemporaryDirectory() as location:
            initial = MagicMock()
            initial.acquire.return_value = True
            concurrent = MagicMock()
            concurrent.acquire.return_value = False
            state = {"active": "v1", "previous": None, "pending": False, "source_sha": "a" * 40}
            pending = {**state, "pending": True}
            with (
                patch.object(launcher, "ROOT", Path(location)),
                patch.object(launcher, "_logger", return_value=MagicMock()),
                patch.object(launcher, "_run_lock", return_value=MagicMock()),
                patch.object(launcher, "SingleInstanceGuard",
                             side_effect=[initial, concurrent]),
                patch.object(launcher, "read_state",
                             side_effect=[state, state, pending]),
                patch.object(launcher, "recover_data_packs_on_launch"),
                patch.object(launcher, "latest_release", return_value=None),
                patch.object(launcher, "active_executable", return_value=Path(location) / "app.exe"),
                patch.object(launcher, "_launch_with_health", return_value=False),
                patch.object(launcher, "rollback_pending",
                             side_effect=AssertionError("rollback of live app forbidden")),
            ):
                with self.assertRaisesRegex(UpdateError, "rollback reporte"):
                    launcher.run_update(lambda *_: None)
            initial.release.assert_called_once()
            concurrent.acquire.assert_called_once()
            concurrent.release.assert_not_called()

    def test_handoff_after_home_ack_or_legacy_qt_preload(self):
        self.assertTrue(_is_application_handoff("Prechargement Qt actif"))
        self.assertFalse(_is_application_handoff("Preparation de Home..."))
        self.assertTrue(_is_application_handoff("Dofus Atlas est pret"))
        self.assertFalse(_is_application_handoff("Lancement de Dofus Atlas..."))
        self.assertFalse(_is_application_handoff("Installation differentielle..."))
        self.assertFalse(_is_application_handoff("Echec : Home indisponible"))


if __name__ == "__main__":
    unittest.main()
