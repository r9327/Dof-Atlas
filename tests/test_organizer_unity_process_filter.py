from __future__ import annotations

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app.windows_embed as embed
import app.windows.unity_windows as unity


class DofusUnityExecutableFilterTests(unittest.TestCase):
    def test_real_absolute_windows_executable_names(self):
        valid = [
            r"C:\Users\player\AppData\Local\Ankama\zaap\dofus\Dofus.exe",
            r"D:\Jeux\DOFUS.EXE",
        ]
        invalid = [
            "", None, "Dofus.exe", r"C:\Jeux\Dofus Retro.exe",
            r"C:\Jeux\Dofus.exe.bak", r"C:\Jeux\Wakfu.exe",
            r"C:\Jeux\UnityPlayer.exe", r"C:\Jeux\DofusOther.exe",
        ]
        for image in valid:
            with self.subTest(image=image):
                self.assertTrue(embed.is_dofus_unity_executable(image))
        for image in invalid:
            with self.subTest(image=image):
                self.assertFalse(embed.is_dofus_unity_executable(image))

    def test_process_requires_unity_class_and_queryable_executable(self):
        with (
            patch.object(embed, "window_class", return_value="UnityWndClass"),
            patch.object(embed, "window_process_id", return_value=42),
            patch.object(embed, "process_image_path", return_value=r"C:\Games\Dofus.exe"),
        ):
            self.assertTrue(embed.is_dofus_unity_process(101))
        with (
            patch.object(embed, "window_class", return_value="UnityWndClass"),
            patch.object(embed, "window_process_id", return_value=42),
            patch.object(embed, "process_image_path", return_value=""),
        ):
            self.assertFalse(embed.is_dofus_unity_process(101))
        with (
            patch.object(embed, "window_class", return_value="OtherGameWindow"),
            patch.object(embed, "window_process_id") as pid,
        ):
            self.assertFalse(embed.is_dofus_unity_process(101))
            pid.assert_not_called()

    def test_scan_excludes_unrelated_unity_game_even_with_dofus_title(self):
        processes = {101: r"C:\Games\Dofus.exe", 202: r"C:\Games\OtherUnity.exe"}
        fake_user32 = SimpleNamespace(IsWindowVisible=lambda _hwnd: True)
        def enumerate_windows(callback, _unused):
            for handle in processes:
                callback(handle, 0)
        fake_user32.EnumWindows = enumerate_windows
        with (
            patch.object(embed, "_ensure_windows_api", return_value=True),
            patch.object(embed, "user32", fake_user32),
            patch.object(embed, "EnumWindowsProc", side_effect=lambda cb: cb),
            patch.object(embed, "window_class", return_value="UnityWndClass"),
            patch.object(embed, "window_title", return_value="Hero - Dofus Unity"),
            patch.object(embed, "window_process_id", side_effect=lambda hwnd: hwnd),
            patch.object(embed, "process_image_path", side_effect=lambda pid: processes[pid]),
        ):
            rows = embed.scan_unity_sessions()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["hwnd"], 101)

    def test_runtime_verifier_checks_executable_not_just_window_class(self):
        fake_gui = SimpleNamespace(
            IsWindow=lambda _hwnd: True,
            GetClassName=lambda _hwnd: unity.UNITY_CLASS,
        )
        with (
            patch.object(unity.os, "name", "nt"),
            patch.object(unity, "_win32", return_value=(None, fake_gui)),
            patch.object(embed, "is_dofus_unity_process", return_value=False),
        ):
            self.assertFalse(unity.is_unity_window(101))
        with (
            patch.object(unity.os, "name", "nt"),
            patch.object(unity, "_win32", return_value=(None, fake_gui)),
            patch.object(embed, "is_dofus_unity_process", return_value=True),
        ):
            self.assertTrue(unity.is_unity_window(101))


if __name__ == "__main__":
    unittest.main()
