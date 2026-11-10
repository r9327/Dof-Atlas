"""Validate per-user Windows installation without requiring admin/Windows APIs."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.distribution import setup as atlas_setup
from app.distribution.setup import install_launcher, install_maintenance_helper


class SetupTests(unittest.TestCase):
    def test_frozen_platform_requires_windows_10_1809_and_64_bit(self):
        with (patch.object(atlas_setup.sys, "frozen", True, create=True),
              patch.object(atlas_setup.sys, "getwindowsversion",
                           return_value=SimpleNamespace(
                               major=10, minor=0, build=17763), create=True)):
            atlas_setup._verify_frozen_platform()
        with (patch.object(atlas_setup.sys, "frozen", True, create=True),
              patch.object(atlas_setup.sys, "getwindowsversion",
                           return_value=SimpleNamespace(
                               major=10, minor=0, build=17134), create=True)):
            with self.assertRaisesRegex(RuntimeError, "1809"):
                atlas_setup._verify_frozen_platform()
        with (patch.object(atlas_setup.sys, "frozen", True, create=True),
              patch.object(atlas_setup.sys, "getwindowsversion",
                           return_value=SimpleNamespace(
                               major=11, minor=0, build=26000), create=True),
              patch.object(atlas_setup.sys, "maxsize", 2**31 - 1)):
            with self.assertRaisesRegex(RuntimeError, "64 bits"):
                atlas_setup._verify_frozen_platform()

    def test_frozen_setup_rejects_unsupported_windows_before_mutation(self):
        # The real Setup must fail before resolving the embedded binary,
        # invoking the installer, or creating a desktop shortcut.
        with (patch.object(atlas_setup.os, "name", "nt"),
              patch.object(atlas_setup.sys, "frozen", True, create=True),
              patch.object(atlas_setup.sys, "getwindowsversion",
                           return_value=SimpleNamespace(
                               major=10, minor=0, build=17134), create=True),
              patch.object(atlas_setup, "embedded_launcher") as embedded,
              patch.object(atlas_setup, "install_launcher") as install,
              patch.object(atlas_setup, "install_maintenance_helper") as helper,
              patch.object(atlas_setup, "choose_runtime_before_setup") as chooser,
              patch.object(atlas_setup.subprocess, "Popen") as launch):
            self.assertEqual(atlas_setup.main(["--no-launch"]), 1)
        embedded.assert_not_called()
        install.assert_not_called()
        helper.assert_not_called()
        chooser.assert_not_called()
        launch.assert_not_called()

    def test_frozen_platform_rejects_unknown_windows_version(self):
        with (patch.object(atlas_setup.sys, "frozen", True, create=True),
              patch.object(atlas_setup.sys, "getwindowsversion", None, create=True)):
            with self.assertRaisesRegex(RuntimeError, "non verifiable"):
                atlas_setup._verify_frozen_platform()

    def test_source_setup_does_not_probe_or_install_python_or_qt(self):
        with (patch.object(atlas_setup.sys, "frozen", False, create=True),
              patch.object(atlas_setup.sys, "getwindowsversion",
                           side_effect=AssertionError("source mode must not probe"),
                           create=True) as version):
            atlas_setup._verify_frozen_platform()
        version.assert_not_called()


    def test_setup_existing_installation_defers_move_to_launcher_mutex(self):
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "runtime"
            tk = MagicMock()
            tk.messagebox.askyesno.return_value = True
            with (
                patch.dict("sys.modules", {"tkinter": tk}),
                patch("app.distribution.install_location.runtime_root",
                      return_value=current),
                patch("app.distribution.install.read_state",
                      return_value={"active": "v1"}) as state,
                patch("app.distribution.install_location.relocate_runtime") as move,
            ):
                self.assertTrue(atlas_setup.choose_runtime_before_setup())
            state.assert_called_once_with(current)
            move.assert_not_called()
            tk.filedialog.askdirectory.assert_not_called()
            tk.Tk.return_value.destroy.assert_called_once()

    def test_setup_first_install_can_select_drive_without_copying_a_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            current = base / "current" / "runtime"
            selected = base / "Disque été"
            target = selected / "DofusAtlas" / "runtime"
            tk = MagicMock()
            tk.messagebox.askyesno.return_value = True
            tk.filedialog.askdirectory.return_value = str(selected)
            with (
                patch.dict("sys.modules", {"tkinter": tk}),
                patch("app.distribution.install_location.runtime_root",
                      return_value=current),
                patch("app.distribution.install.read_state",
                      return_value={"active": None}),
                patch("app.distribution.install_location.relocate_runtime") as move,
            ):
                self.assertFalse(atlas_setup.choose_runtime_before_setup())
            move.assert_called_once()
            self.assertEqual(move.call_args.args, (target,))
            self.assertIsNotNone(move.call_args.kwargs.get("progress"))
            tk.Toplevel.return_value.destroy.assert_called_once()
            tk.Tk.return_value.destroy.assert_called_once()

    def test_setup_existing_move_launches_configuration_in_one_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "Programs" / "DofusAtlas" / "DofusAtlas.exe"
            with (
                patch.object(atlas_setup, "os", SimpleNamespace(name="nt")),
                patch.object(atlas_setup, "choose_runtime_before_setup",
                             return_value=True),
                patch.object(atlas_setup, "embedded_launcher",
                             return_value=Path(directory) / "Embedded.exe"),
                patch.object(atlas_setup.Path, "cwd", return_value=Path(directory)),
                patch.object(atlas_setup, "install_launcher",
                             return_value=target),
                patch.object(atlas_setup, "install_maintenance_helper"),
                patch.object(atlas_setup.subprocess, "Popen") as launch,
            ):
                self.assertEqual(atlas_setup.main([]), 0)
            launch.assert_called_once_with(
                [str(target), "--atlas-configure"],
                cwd=str(target.parent),
                creationflags=getattr(atlas_setup.subprocess, "CREATE_NO_WINDOW", 0),
            )

    def test_unattended_setup_does_not_open_picker_or_auto_start_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "Programs" / "DofusAtlas.exe"
            with (
                patch.object(atlas_setup, "os", SimpleNamespace(name="nt")),
                patch.object(atlas_setup.Path, "cwd", return_value=Path(directory)),
                patch.object(atlas_setup, "choose_runtime_before_setup") as chooser,
                patch.object(atlas_setup, "embedded_launcher",
                             return_value=Path(directory) / "Embedded.exe"),
                patch.object(atlas_setup, "install_launcher", return_value=target),
                patch.object(atlas_setup, "install_maintenance_helper"),
                patch.object(atlas_setup.subprocess, "Popen") as launch,
            ):
                self.assertEqual(atlas_setup.main(["--no-launch"]), 0)
            chooser.assert_not_called()
            launch.assert_not_called()

    def test_install_launcher_creates_stable_binary_and_preserves_user_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "DofusAtlas.exe"
            source.write_bytes(b"MZ" + b"launcher-one")
            app = root / "Programs" / "DofusAtlas"
            personal = root / "DofusAtlas" / "user" / "data"
            personal.mkdir(parents=True)
            profile = personal / "client_profiles.json"
            profile.write_text('{"character":"unchanged"}', encoding="utf-8")
            with patch("app.distribution.setup._create_shortcut") as shortcut:
                result = install_launcher(source, app)
                self.assertEqual(result, app / "DofusAtlas.exe")
                self.assertEqual(result.read_bytes(), source.read_bytes())
                shortcut.assert_called_once_with(result)
                source.write_bytes(b"MZ" + b"launcher-two")
                second = install_launcher(source, app)
                self.assertEqual(second.read_bytes(), source.read_bytes())
            self.assertEqual(profile.read_text(encoding="utf-8"), '{"character":"unchanged"}')

    def test_repeat_setup_skips_rewriting_identical_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "DofusAtlas.exe"
            source.write_bytes(b"MZ" + b"unchanged-launcher")
            app = root / "Programs" / "DofusAtlas"
            with patch("app.distribution.setup._create_shortcut") as shortcut:
                installed = install_launcher(source, app)
                original_stat = installed.stat()
                with patch("app.distribution.setup.tempfile.mkstemp",
                           side_effect=AssertionError("unchanged EXE must not be staged")):
                    self.assertEqual(install_launcher(source, app), installed)
                self.assertEqual(installed.stat().st_mtime_ns, original_stat.st_mtime_ns)
                self.assertEqual(installed.read_bytes(), source.read_bytes())
                self.assertEqual(shortcut.call_count, 2)

    def test_same_size_but_changed_launcher_is_reinstalled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "DofusAtlas.exe"
            source.write_bytes(b"MZcorrect")
            app = root / "Programs" / "DofusAtlas"
            with patch("app.distribution.setup._create_shortcut"):
                installed = install_launcher(source, app)
                installed.write_bytes(b"MZchanged")  # Same length, wrong checksum.
                install_launcher(source, app)
            self.assertEqual(installed.read_bytes(), b"MZcorrect")

    def test_maintenance_helper_skips_identical_setup_and_repairs_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            programs = root / "Programs"
            programs.mkdir()
            source = root / "DofusAtlasSetup.exe"
            source.write_bytes(b"MZmaintenance-binary")
            helper = install_maintenance_helper(source, programs)
            self.assertEqual(helper.read_bytes(), source.read_bytes())
            with patch("app.distribution.setup.tempfile.mkstemp",
                       side_effect=AssertionError("same maintenance EXE must not be staged")):
                self.assertEqual(install_maintenance_helper(source, programs), helper)
            helper.write_bytes(b"XX" + source.read_bytes()[2:])
            self.assertEqual(helper.stat().st_size, source.stat().st_size)
            install_maintenance_helper(source, programs)
            self.assertEqual(helper.read_bytes(), source.read_bytes())

    def test_reject_non_executable_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "fake.exe"
            source.write_bytes(b"not-a-win-binary")
            with self.assertRaises(ValueError):
                install_launcher(source, root / "install")
            self.assertFalse((root / "install").exists())


if __name__ == "__main__":
    unittest.main()
