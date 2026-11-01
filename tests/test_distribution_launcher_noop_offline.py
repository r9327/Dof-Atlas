"""Launcher no-op/offline behavior without a full CI or Windows GUI."""
from __future__ import annotations

import socket
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.distribution import launcher, release_client
from app.distribution.release_client import UpdateError


class OfflineProbeTests(unittest.TestCase):
    def test_existing_release_on_dns_failure_does_not_try_three_fallbacks(self):
        with patch.object(
            release_client, "_read_limited",
            side_effect=urllib.error.URLError(socket.gaierror(-2, "no DNS")),
        ) as read, patch.object(
            release_client, "_latest_release_api",
            side_effect=AssertionError("repeated API query"),
        ), patch.object(
            release_client, "_latest_release_channel",
            side_effect=AssertionError("20-second channel timeout"),
        ), patch.object(
            release_client, "_latest_release_web",
            side_effect=AssertionError("20-second web timeout"),
        ):
            with self.assertRaisesRegex(UpdateError, "lancement local"):
                release_client.latest_release(installed_source_sha="a" * 40)
            read.assert_called_once_with(
                release_client.API_URL, 1024 * 1024, timeout=5,
            )

    def test_http_error_does_not_disable_official_fallbacks(self):
        candidate = object()
        with patch.object(
            release_client, "_read_limited",
            side_effect=urllib.error.HTTPError(
                release_client.API_URL, 403, "rate limit", {}, None,
            ),
        ), patch.object(
            release_client, "_latest_release_api",
            return_value=candidate,
        ) as full:
            self.assertIs(
                release_client.latest_release(installed_source_sha="a" * 40),
                candidate,
            )
            full.assert_called_once()

    def test_no_installed_version_keeps_first_install_resilience(self):
        candidate = object()
        with patch.object(
            release_client, "_latest_release_api", return_value=candidate,
        ) as full, patch.object(
            release_client, "_read_limited",
            side_effect=AssertionError("should not run shortcut"),
        ):
            self.assertIs(release_client.latest_release(), candidate)
            full.assert_called_once()

    def test_offline_launcher_boots_last_installed_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "versions" / "v1" / "AtlasApp" / "AtlasApp.exe"
            state = {"active": "v1", "pending": False, "previous": None,
                     "source_sha": "a" * 40}
            with patch.object(launcher, "ROOT", root), patch.object(
                launcher, "_logger", return_value=MagicMock(),
            ), patch.object(
                launcher, "_run_lock", return_value=MagicMock(),
            ), patch.object(
                launcher, "read_state", return_value=state,
            ), patch.object(
                launcher, "active_executable", return_value=exe,
            ), patch.object(
                launcher, "latest_release",
                side_effect=UpdateError("GitHub inaccessible — lancement local"),
            ), patch.object(
                launcher, "_launch_with_health", return_value=True,
            ) as started, patch.object(
                launcher, "install_release",
                side_effect=AssertionError("must not install offline"),
            ):
                launcher.run_update(lambda *_: None)
                started.assert_called_once()


class _Variable:
    def __init__(self, value=None):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class _ImmediateThread:
    def __init__(self, *, target, **_kwargs):
        self.target = target

    def start(self):
        self.target()


class HiddenUpdaterWindowTests(unittest.TestCase):
    def _drive(self, status, *, fail=False):
        fake_tk = MagicMock()
        fake_ttk = MagicMock()
        fake_tk.IntVar.side_effect = _Variable
        fake_tk.StringVar.side_effect = _Variable
        window = fake_tk.Tk.return_value
        window.after.side_effect = lambda _delay, callback: callback()

        def update(report, *, verify_installation=False):
            for label, percent in status:
                report(label, percent)
            if fail:
                raise UpdateError("App failed")

        with patch.dict(
            sys.modules, {"tkinter": fake_tk, "tkinter.ttk": fake_ttk},
        ), patch.object(
            sys, "argv", ["DofusAtlas.exe", "--atlas-auto-install"],
        ), patch.object(
            launcher, "read_state", return_value={"active": "v1"},
        ), patch.object(
            launcher, "run_update", side_effect=update,
        ), patch.object(
            launcher, "_logger", return_value=MagicMock(),
        ), patch.object(
            launcher.threading, "Thread", _ImmediateThread,
        ):
            result = launcher.main()
        return result, window

    def test_same_release_uses_one_launcher_window_until_home(self):
        status = [
            ("Verification des mises a jour...", 5),
            ("Atlas est a jour", 96),
            ("Lancement de Dofus Atlas...", 98),
            ("Dofus Atlas est pret", 100),
        ]
        result, window = self._drive(status)
        self.assertEqual(result, 0)
        self.assertEqual(window.deiconify.call_count, 1)  # displayed at spawn
        self.assertEqual(window.withdraw.call_count, 2)  # initial + Home
        window.destroy.assert_called_once()

    def test_visible_updater_waits_for_home_ack_before_hiding(self):
        result, window = self._drive([
            ("Differentiel : 10 %", 17),
            ("Lancement de Dofus Atlas...", 98),
            ("Preparation de Home...", 98),
            ("Dofus Atlas est pret", 100),
        ])
        self.assertEqual(result, 0)
        self.assertEqual(window.deiconify.call_count, 1)
        # One initial hide, one real Home takeover; never hide at Qt preload.
        self.assertEqual(window.withdraw.call_count, 2)

    def test_spawn_without_qt_ack_keeps_updater_visible(self):
        result, window = self._drive([
            ("Installation differentielle...", 83),
            ("Lancement de Dofus Atlas...", 98),
        ])
        self.assertEqual(result, 0)
        self.assertEqual(window.deiconify.call_count, 1)
        self.assertEqual(window.withdraw.call_count, 1)  # initial hidden only

    def test_rollback_reveals_updater_until_old_qt_is_ready(self):
        result, window = self._drive([
            ("Differentiel : 10 %", 17),
            ("Lancement de Dofus Atlas...", 98),
            ("Preparation de Home...", 98),
            ("Demarrage echoue — restauration precedente", 95),
            ("Lancement de Dofus Atlas...", 98),
            ("Preparation de Home...", 98),
            ("Dofus Atlas est pret", 100),
        ])
        self.assertEqual(result, 0)
        self.assertEqual(window.deiconify.call_count, 1)
        self.assertEqual(window.withdraw.call_count, 2)

    def test_qt_preload_never_hides_launcher_before_home(self):
        result, window = self._drive([
            ("Lancement de Dofus Atlas...", 98),
            ("Preparation de Home...", 98),
        ])
        self.assertEqual(result, 0)
        self.assertEqual(window.deiconify.call_count, 1)
        window.withdraw.assert_called_once()  # initial withdraw only

    def test_legacy_client_hands_over_to_its_qt_preload(self):
        result, window = self._drive([
            ("Lancement de Dofus Atlas...", 98),
            ("Prechargement Qt actif", 98),
        ])
        self.assertEqual(result, 0)
        self.assertEqual(window.deiconify.call_count, 1)
        self.assertEqual(window.withdraw.call_count, 2)  # Tk -> legacy Qt

    def test_gui_handoff_flag_is_scoped_to_worker(self):
        with patch.dict("os.environ", {}, clear=True):
            result, _ = self._drive([
                ("Lancement de Dofus Atlas...", 98),
                ("Dofus Atlas est pret", 100),
            ])
            self.assertEqual(result, 0)
            self.assertNotIn("DOFUS_ATLAS_LAUNCHER_HANDOFF", __import__("os").environ)

    def test_folder_picker_guards_migration_before_launch_and_handoff(self):
        """The visible path selection must call the locked migration, not raw copy."""
        fake_tk = MagicMock()
        fake_ttk = MagicMock()
        fake_tk.IntVar.side_effect = _Variable
        fake_tk.StringVar.side_effect = _Variable
        window = fake_tk.Tk.return_value
        scheduled = []
        window.after.side_effect = lambda _delay, callback: scheduled.append(callback)
        source = Path("OldDisk") / "Atlas" / "runtime"
        parent = Path("NewDisk") / "Games"
        destination = parent / "DofusAtlas" / "runtime"
        fake_tk.filedialog.askdirectory.return_value = str(parent)
        order = []

        def relocate(target, *, progress=None):
            self.assertEqual(target, destination)
            self.assertEqual(launcher.ROOT, source)
            self.assertIsNotNone(progress)
            order.append("guarded_migration")
            return target

        def run_after_move(report, *, verify_installation=False):
            self.assertEqual(launcher.ROOT, destination)
            order.append("launch")
            report("Dofus Atlas est pret", 100)

        def drive_mainloop():
            buttons = fake_tk.Button.call_args_list
            self.assertGreaterEqual(len(buttons), 2)
            buttons[0].kwargs["command"]()  # select the external folder
            buttons[-1].kwargs["command"]()  # install and start
            for _ in range(5):
                if not scheduled:
                    break
                scheduled.pop(0)()

        window.mainloop.side_effect = drive_mainloop
        with (
            patch.dict(sys.modules, {"tkinter": fake_tk,
                                     "tkinter.ttk": fake_ttk}),
            patch.object(sys, "argv", ["DofusAtlas.exe", "--atlas-configure"]),
            patch.object(launcher, "ROOT", source),
            patch.object(launcher, "read_state", return_value={"active": "v1"}),
            patch.object(launcher, "has_saved_location", return_value=True),
            patch.object(launcher, "_relocate_runtime_safely",
                         side_effect=relocate) as guarded,
            patch.object(launcher, "relocate_runtime",
                         side_effect=AssertionError("unlocked migration")) as raw_copy,
            patch.object(launcher, "run_update", side_effect=run_after_move),
            patch.object(launcher.threading, "Thread", _ImmediateThread),
        ):
            self.assertEqual(launcher.main(), 0)
        self.assertEqual(order, ["guarded_migration", "launch"])
        guarded.assert_called_once()
        raw_copy.assert_not_called()

    def test_real_delta_shows_progress_only_once(self):
        result, window = self._drive([
            ("Verification des mises a jour...", 5),
            ("Differentiel : 10 %", 17),
            ("Installation differentielle...", 83),
        ])
        self.assertEqual(result, 0)
        window.deiconify.assert_called_once()

    def test_unchanged_large_file_reports_actual_copy_progress(self):
        import hashlib
        from app.distribution.install import _copy_unchanged_verified
        from app.distribution.manifest import ReleaseFile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = b"Atlas!" * 600000
            source = root / "source.bin"
            destination = root / "destination.bin"
            source.write_bytes(payload)
            marks = []
            entry = ReleaseFile(
                "AtlasApp/source.bin", len(payload),
                hashlib.sha256(payload).hexdigest(),
            )
            _copy_unchanged_verified(
                source, destination, entry, progress=marks.append,
            )
            self.assertGreater(len(marks), 1)
            self.assertEqual(marks[-1], len(payload))
            self.assertEqual(marks, sorted(marks))
            self.assertEqual(destination.read_bytes(), payload)

    def test_failure_reveals_error_even_when_initially_hidden(self):
        result, window = self._drive([("Atlas est a jour", 96)], fail=True)
        self.assertEqual(result, 1)
        window.deiconify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
