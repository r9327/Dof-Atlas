from __future__ import annotations

import unittest
from unittest.mock import patch

import app.windows_embed as windows_embed


class _FakeUser32:
    def __init__(self) -> None:
        self.next_handle = 100
        self.installed: list[tuple[int, int]] = []
        self.unhooked: list[int] = []

    def SetWinEventHook(self, event_min, event_max, _module, _callback, _pid, _thread, _flags):
        self.installed.append((int(event_min), int(event_max)))
        self.next_handle += 1
        return self.next_handle

    def UnhookWinEvent(self, hook):
        self.unhooked.append(int(hook))
        return True


class UnityWindowEventWatcherTests(unittest.TestCase):
    def test_start_stop_restart_and_event_filtering(self) -> None:
        fake_user32 = _FakeUser32()
        received: list[tuple[int, int]] = []

        with (
            patch.object(windows_embed, "_ensure_windows_api", return_value=True),
            patch.object(windows_embed, "user32", fake_user32),
            patch.object(windows_embed, "WinEventProc", side_effect=lambda callback: callback),
            patch.object(
                windows_embed,
                "window_class",
                side_effect=lambda hwnd: "UnityWndClass" if hwnd == 42 else "OtherWindow",
            ),
        ):
            watcher = windows_embed.UnityWindowEventWatcher(
                lambda event_id, hwnd: received.append((event_id, hwnd))
            )
            self.assertTrue(watcher.start())
            self.assertTrue(watcher.active)
            self.assertEqual(
                fake_user32.installed,
                [(event_id, event_id) for event_id in windows_embed.UNITY_WINDOW_EVENTS],
            )

            watcher._event_proc(
                None,
                windows_embed.EVENT_OBJECT_SHOW,
                42,
                windows_embed.OBJID_WINDOW,
                0,
                0,
                0,
            )
            watcher._event_proc(
                None,
                windows_embed.EVENT_OBJECT_NAMECHANGE,
                99,
                windows_embed.OBJID_WINDOW,
                0,
                0,
                0,
            )
            watcher._event_proc(
                None,
                windows_embed.EVENT_OBJECT_HIDE,
                42,
                windows_embed.OBJID_WINDOW,
                0,
                0,
                0,
            )
            self.assertEqual(
                received,
                [
                    (windows_embed.EVENT_OBJECT_SHOW, 42),
                    (windows_embed.EVENT_OBJECT_HIDE, 42),
                ],
            )

            watcher.stop()
            self.assertFalse(watcher.active)
            self.assertEqual(len(fake_user32.unhooked), len(windows_embed.UNITY_WINDOW_EVENTS))
            self.assertTrue(watcher.start())
            watcher.stop()
            self.assertEqual(len(fake_user32.unhooked), 2 * len(windows_embed.UNITY_WINDOW_EVENTS))


if __name__ == "__main__":
    unittest.main()
