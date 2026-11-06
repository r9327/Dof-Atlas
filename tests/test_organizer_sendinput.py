from __future__ import annotations

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from app.input import hotkeys as _hotkeys  # preload before monkeypatching os.name
from app.macros import input_tools
from app.windows import clicks


class OrganizerSendInputTests(unittest.TestCase):

    def test_chat_refuses_stale_clipboard_after_windows_clipboard_lock_timeout(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.OpenClipboard.side_effect = OSError("locked by another process")
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools.time, "sleep"),
            patch.object(input_tools, "press_key") as press,
        ):
            with self.assertRaisesRegex(OSError, "Clipboard non prepare"):
                input_tools.send_chat_command("/zaap 1,2", Mock())
        self.assertEqual(clipboard.OpenClipboard.call_count, 10)
        press.assert_not_called()

    def test_clipboard_restore_never_swallows_chat_sendinput_failure(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.GetClipboardData.return_value = "previous text"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         side_effect=RuntimeError("SendInput refused")),
            patch.object(input_tools, "press_key") as press,
        ):
            with self.assertRaisesRegex(RuntimeError, "SendInput refused"):
                input_tools.send_chat_command("/zaap 1,2", Mock())
        self.assertEqual(
            clipboard.SetClipboardText.call_args_list,
            [call("/zaap 1,2", 13), call("previous text", 13)],
        )
        press.assert_not_called()

    def test_clipboard_restore_failure_keeps_original_send_error(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.GetClipboardData.return_value = "original"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        clipboard.OpenClipboard.side_effect = [
            None, *(OSError("clipboard locked") for _ in range(10)),
        ]
        logger = Mock()
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools.time, "sleep"),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         side_effect=RuntimeError("chat aborted")),
        ):
            with self.assertRaisesRegex(RuntimeError, "chat aborted"):
                input_tools.send_chat_command("/invite Friend", logger)
        self.assertEqual(clipboard.OpenClipboard.call_count, 11)
        logger.warning.assert_called_once_with(
            "Clipboard: restauration impossible."
        )

    def test_preparation_failure_restores_original_clipboard_then_retries(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.GetClipboardData.return_value = "user text"
        clipboard.EnumClipboardFormats.side_effect = (
            lambda old: 13 if old == 0 else 0
        )
        clipboard.SetClipboardText.side_effect = [
            OSError("first SetClipboardText refused"), None, None, None,
        ]
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools.time, "sleep"),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         return_value=True),
            patch.object(input_tools, "press_key") as press,
        ):
            self.assertTrue(input_tools.send_chat_command("/zaap 1,2", Mock()))
        self.assertEqual(
            clipboard.SetClipboardText.call_args_list,
            [
                call("/zaap 1,2", 13), call("user text", 13),
                call("/zaap 1,2", 13), call("user text", 13),
            ],
        )
        self.assertEqual(clipboard.OpenClipboard.call_count, 3)
        self.assertEqual(clipboard.CloseClipboard.call_count, 3)
        press.assert_called_once_with("ENTER")

    def test_preparation_and_recovery_failure_stops_without_retry(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.GetClipboardData.return_value = "user text"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        clipboard.SetClipboardText.side_effect = [
            OSError("first SetClipboardText refused"),
            OSError("restoration refused"),
        ]
        logger = Mock()
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools.time, "sleep"),
            patch.object(input_tools, "press_key") as press,
        ):
            with self.assertRaisesRegex(OSError, "Clipboard non restaure"):
                input_tools.send_chat_command("/zaap 1,2", logger)
        self.assertEqual(clipboard.SetClipboardText.call_count, 2)
        self.assertEqual(clipboard.OpenClipboard.call_count, 1)
        clipboard.CloseClipboard.assert_called_once()
        logger.exception.assert_called_once()
        press.assert_not_called()

    def test_chat_rejects_non_text_clipboard_without_erasing_user_data(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.GetClipboardData.side_effect = TypeError("CF_UNICODETEXT missing")
        clipboard.EnumClipboardFormats.return_value = 8  # CF_DIB image data
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools.time, "sleep"),
            patch.object(input_tools, "press_key") as press,
        ):
            with self.assertRaisesRegex(OSError, "Clipboard multi-format"):
                input_tools.send_chat_command("/zaap 1,2", Mock())
        self.assertEqual(clipboard.OpenClipboard.call_count, 1)
        clipboard.EmptyClipboard.assert_not_called()
        clipboard.SetClipboardText.assert_not_called()
        press.assert_not_called()

    def test_chat_rejects_rich_clipboard_even_with_unicode_text(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.GetClipboardData.return_value = "plain part of rich text"
        clipboard.EnumClipboardFormats.side_effect = [13, 0xC001]  # registered HTML
        logger = Mock()
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "press_key") as press,
        ):
            with self.assertRaisesRegex(OSError, "Clipboard multi-format"):
                input_tools.send_chat_command("/invite Friend", logger)
        clipboard.EmptyClipboard.assert_not_called()
        clipboard.SetClipboardText.assert_not_called()
        logger.warning.assert_called_once()
        press.assert_not_called()

    def test_chat_accepts_plain_clipboard_with_standard_text_formats(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.GetClipboardData.return_value = "original"
        clipboard.EnumClipboardFormats.side_effect = [1, 7, 13, 16, 0]
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         return_value=True),
            patch.object(input_tools, "press_key") as press,
        ):
            self.assertTrue(input_tools.send_chat_command("/invite Friend", Mock()))
        self.assertEqual(clipboard.EmptyClipboard.call_count, 2)
        self.assertEqual(
            clipboard.SetClipboardText.call_args_list,
            [call("/invite Friend", 13), call("original", 13)],
        )
        press.assert_called_once_with("ENTER")

    def test_chat_cancels_before_ctrl_a_after_user_copy(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardData.return_value = "original"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        clipboard.GetClipboardSequenceNumber.side_effect = [100, 100, 100, 101, 101]
        logger = Mock()
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "press_key") as press,
            patch.object(input_tools, "press_hotkey") as chord,
        ):
            self.assertFalse(input_tools.send_chat_command("/zaap 1,2", logger))
        press.assert_called_once_with("SPACE")
        chord.assert_not_called()
        clipboard.SetClipboardText.assert_called_once_with("/zaap 1,2", 13)
        logger.warning.assert_any_call("Clipboard modifie pendant le chat: envoi annule.")

    def test_chat_never_enters_foreign_clipboard_after_paste(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardData.return_value = "original"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        clipboard.GetClipboardSequenceNumber.side_effect = [100, 100, 101, 101]
        logger = Mock()
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         return_value=True) as paste,
            patch.object(input_tools, "press_key") as press,
        ):
            self.assertFalse(input_tools.send_chat_command("/invite Friend", logger))
        paste.assert_called_once()
        press.assert_not_called()
        clipboard.SetClipboardText.assert_called_once_with("/invite Friend", 13)
        logger.warning.assert_any_call("Clipboard modifie pendant le chat: envoi annule.")

    def test_zaap_double_enter_aborts_when_clipboard_changes_after_first_enter(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardData.return_value = "user before"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        clipboard.GetClipboardSequenceNumber.side_effect = [100, 100, 100, 101, 101]
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         return_value=True),
            patch.object(input_tools, "_sleep_ms", return_value=False),
            patch.object(input_tools, "press_key") as press,
        ):
            self.assertFalse(input_tools.send_chat_command(
                "/zaap 1,2", Mock(), submit_twice=True,
            ))
        press.assert_called_once_with("ENTER")
        clipboard.SetClipboardText.assert_called_once_with("/zaap 1,2", 13)
        clipboard.EmptyClipboard.assert_called_once()

    def test_chat_cancels_on_unreadable_revision_without_enter(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardData.return_value = "user before"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        clipboard.GetClipboardSequenceNumber.side_effect = [
            100, 100, OSError("Windows clipboard revision read refused"),
            *([100] * 1),
        ]
        logger = Mock()
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         return_value=True),
            patch.object(input_tools, "press_key") as press,
        ):
            self.assertFalse(input_tools.send_chat_command("/invite Friend", logger))
        press.assert_not_called()
        logger.warning.assert_any_call(
            "Clipboard: revision Win32 illisible, chat annule."
        )

    def test_chat_accepts_negative_signed_win32_revision(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardData.return_value = "original"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        clipboard.GetClipboardSequenceNumber.return_value = -2147483647
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         return_value=True),
            patch.object(input_tools, "press_key") as press,
        ):
            self.assertTrue(input_tools.send_chat_command("/invite Friend", Mock()))
        press.assert_called_once_with("ENTER")
        self.assertEqual(
            clipboard.SetClipboardText.call_args_list,
            [call("/invite Friend", 13), call("original", 13)],
        )

    def test_clipboard_postwrite_missing_revision_restores_before_unlock(self) -> None:
        for postwrite in (0, OSError("revision lost")):
            with self.subTest(revision=repr(postwrite)):
                clipboard = Mock()
                clipboard.GetClipboardData.return_value = "old clipboard"
                clipboard.EnumClipboardFormats.side_effect = [13, 0]
                clipboard.GetClipboardSequenceNumber.side_effect = [100, postwrite]
                logger = Mock()
                with (
                    patch.object(input_tools.os, "name", "nt"),
                    patch.dict("sys.modules", {
                        "win32clipboard": clipboard,
                        "win32con": SimpleNamespace(CF_UNICODETEXT=13),
                    }),
                    patch.object(input_tools, "press_key") as press,
                ):
                    with self.assertRaisesRegex(
                        OSError, "Clipboard revision Win32 indisponible",
                    ):
                        input_tools.send_chat_command("/zaap 1,2", logger)
                self.assertEqual(clipboard.OpenClipboard.call_count, 1)
                clipboard.CloseClipboard.assert_called_once()
                self.assertEqual(clipboard.EmptyClipboard.call_count, 2)
                self.assertEqual(
                    clipboard.SetClipboardText.call_args_list,
                    [call("/zaap 1,2", 13), call("old clipboard", 13)],
                )
                press.assert_not_called()
                logger.warning.assert_any_call(
                    "Clipboard conserve: revision Win32 non fiable."
                )

    def test_clipboard_empty_state_is_restored_if_postwrite_serial_fails(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardData.side_effect = TypeError("empty clipboard")
        clipboard.EnumClipboardFormats.return_value = 0
        clipboard.GetClipboardSequenceNumber.side_effect = [101, 0]
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "press_key") as press,
        ):
            with self.assertRaisesRegex(OSError, "Clipboard revision Win32 indisponible"):
                input_tools.send_chat_command("/zaap 1,2", Mock())
        clipboard.OpenClipboard.assert_called_once()
        clipboard.CloseClipboard.assert_called_once()
        self.assertEqual(clipboard.EmptyClipboard.call_count, 2)
        clipboard.SetClipboardText.assert_called_once_with("/zaap 1,2", 13)
        press.assert_not_called()

    def test_clipboard_postwrite_repair_refusal_never_retries_or_sends(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardData.return_value = "old clipboard"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        clipboard.GetClipboardSequenceNumber.side_effect = [100, 0]
        clipboard.SetClipboardText.side_effect = [
            None, OSError("restoration denied"),
        ]
        logger = Mock()
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "press_key") as press,
        ):
            with self.assertRaisesRegex(OSError, "Clipboard non restaure"):
                input_tools.send_chat_command("/invite Friend", logger)
        clipboard.OpenClipboard.assert_called_once()
        clipboard.CloseClipboard.assert_called_once()
        self.assertEqual(clipboard.SetClipboardText.call_count, 2)
        logger.exception.assert_called_once_with(
            "Clipboard: reparation apres compteur Win32 invalide impossible."
        )
        press.assert_not_called()

    def test_clipboard_preflight_rejects_unreadable_or_nonnumeric_revision(self) -> None:
        for revision in (None, "invalid", OSError("access denied")):
            with self.subTest(revision=repr(revision)):
                clipboard = Mock()
                clipboard.GetClipboardData.return_value = "important user text"
                clipboard.EnumClipboardFormats.side_effect = [13, 0]
                if isinstance(revision, Exception):
                    clipboard.GetClipboardSequenceNumber.side_effect = revision
                else:
                    clipboard.GetClipboardSequenceNumber.return_value = revision
                logger = Mock()
                with (
                    patch.object(input_tools.os, "name", "nt"),
                    patch.dict("sys.modules", {
                        "win32clipboard": clipboard,
                        "win32con": SimpleNamespace(CF_UNICODETEXT=13),
                    }),
                    patch.object(input_tools, "press_key") as press,
                ):
                    with self.assertRaisesRegex(
                        OSError, "Clipboard revision Win32 indisponible",
                    ):
                        input_tools.send_chat_command("/invite Friend", logger)
                clipboard.OpenClipboard.assert_called_once()
                clipboard.CloseClipboard.assert_called_once()
                clipboard.EmptyClipboard.assert_not_called()
                clipboard.SetClipboardText.assert_not_called()
                press.assert_not_called()
                logger.warning.assert_any_call(
                    "Clipboard conserve: revision Win32 non fiable."
                )

    def test_chat_refuses_submission_without_clipboard_revision(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardData.return_value = "original"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        clipboard.GetClipboardSequenceNumber.return_value = 0
        logger = Mock()
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "replace_chat_text_with_clipboard") as paste,
            patch.object(input_tools, "press_key") as press,
        ):
            with self.assertRaisesRegex(OSError, "Clipboard revision Win32 indisponible"):
                input_tools.send_chat_command("/invite Friend", logger)
        paste.assert_not_called()
        press.assert_not_called()
        clipboard.EmptyClipboard.assert_not_called()
        clipboard.SetClipboardText.assert_not_called()
        logger.warning.assert_any_call(
            "Clipboard conserve: revision Win32 non fiable."
        )

    def test_clipboard_user_copy_during_command_is_preserved(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.GetClipboardData.return_value = "old clipboard"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        clipboard.GetClipboardSequenceNumber.side_effect = [100, 100, 100, 101]
        logger = Mock()
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         return_value=True),
            patch.object(input_tools, "press_key") as press,
        ):
            self.assertTrue(input_tools.send_chat_command("/zaap 1,2", logger))
        clipboard.SetClipboardText.assert_called_once_with("/zaap 1,2", 13)
        clipboard.EmptyClipboard.assert_called_once()
        logger.info.assert_called_once_with(
            "Clipboard utilisateur modifie pendant la macro: restauration ignoree."
        )
        press.assert_called_once_with("ENTER")

    def test_clipboard_unchanged_sequence_restores_original_text(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.GetClipboardData.return_value = "old clipboard"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        # The same revision is checked at every chat keyboard boundary.
        clipboard.GetClipboardSequenceNumber.return_value = 100
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         return_value=True),
            patch.object(input_tools, "press_key"),
        ):
            self.assertTrue(input_tools.send_chat_command("/zaap 1,2", Mock()))
        self.assertEqual(clipboard.EmptyClipboard.call_count, 2)
        self.assertEqual(
            clipboard.SetClipboardText.call_args_list,
            [call("/zaap 1,2", 13), call("old clipboard", 13)],
        )

    def test_clipboard_revision_snapshot_is_taken_before_unlocking(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.GetClipboardData.return_value = "before"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        opened = [False]
        calls = []

        def open_clipboard():
            self.assertFalse(opened[0])
            opened[0] = True
            calls.append("open")

        def close_clipboard():
            self.assertTrue(opened[0])
            opened[0] = False
            calls.append("close")

        def read_revision():
            # The prepare and restore snapshots occur inside the Win32
            # lease; intermediate lightweight safety checks do not open it.
            calls.append("serial_locked" if opened[0] else "serial_check")
            return 99

        clipboard.OpenClipboard.side_effect = open_clipboard
        clipboard.CloseClipboard.side_effect = close_clipboard
        clipboard.GetClipboardSequenceNumber.side_effect = read_revision
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         return_value=True),
            patch.object(input_tools, "press_key"),
        ):
            self.assertTrue(input_tools.send_chat_command("/invite Friend", Mock()))
        self.assertEqual(
            calls,
            ["open", "serial_locked", "serial_locked", "close", "serial_check",
             "open", "serial_locked", "close"],
        )
        self.assertFalse(opened[0])
        self.assertEqual(clipboard.EmptyClipboard.call_count, 2)

    def test_clipboard_changed_during_sender_error_keeps_original_exception(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.GetClipboardData.return_value = "old clipboard"
        clipboard.EnumClipboardFormats.side_effect = [13, 0]
        clipboard.GetClipboardSequenceNumber.side_effect = [100, 100, 101]
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         side_effect=OSError("SendInput refused")),
        ):
            with self.assertRaisesRegex(OSError, "SendInput refused"):
                input_tools.send_chat_command("/invite Friend", Mock())
        clipboard.SetClipboardText.assert_called_once_with("/invite Friend", 13)
        clipboard.EmptyClipboard.assert_called_once()

    def test_chat_accepts_truly_empty_clipboard_and_restores_empty_state(self) -> None:
        clipboard = Mock()
        clipboard.GetClipboardSequenceNumber.return_value = 100
        clipboard.GetClipboardData.side_effect = TypeError("clipboard empty")
        clipboard.EnumClipboardFormats.return_value = 0
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": clipboard,
                "win32con": SimpleNamespace(CF_UNICODETEXT=13),
            }),
            patch.object(input_tools, "replace_chat_text_with_clipboard",
                         return_value=True),
            patch.object(input_tools, "press_key") as press,
        ):
            self.assertTrue(input_tools.send_chat_command("/zaap 1,2", Mock()))
        self.assertEqual(clipboard.EmptyClipboard.call_count, 2)
        clipboard.SetClipboardText.assert_called_once_with("/zaap 1,2", 13)
        press.assert_called_once_with("ENTER")

    def test_chat_clipboard_cycles_two_four_six_eight_remain_balanced(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                clipboard = Mock()
                clipboard.GetClipboardSequenceNumber.return_value = 100
                clipboard.GetClipboardData.return_value = "original"
                clipboard.EnumClipboardFormats.side_effect = (
                    lambda previous: 13 if previous == 0 else 0
                )
                clipboard.GetClipboardSequenceNumber.return_value = 77
                with (
                    patch.object(input_tools.os, "name", "nt"),
                    patch.dict("sys.modules", {
                        "win32clipboard": clipboard,
                        "win32con": SimpleNamespace(CF_UNICODETEXT=13),
                    }),
                    patch.object(input_tools, "replace_chat_text_with_clipboard",
                                 return_value=True),
                    patch.object(input_tools, "press_key") as press,
                ):
                    for index in range(count):
                        self.assertTrue(input_tools.send_chat_command(
                            f"/invite Player{index}", Mock(),
                        ))
                self.assertEqual(clipboard.OpenClipboard.call_count, 2 * count)
                self.assertEqual(clipboard.CloseClipboard.call_count, 2 * count)
                self.assertEqual(clipboard.EmptyClipboard.call_count, 2 * count)
                self.assertEqual(
                    clipboard.SetClipboardText.call_count, 2 * count,
                )
                for index in range(count):
                    self.assertEqual(
                        clipboard.SetClipboardText.call_args_list[2 * index:2 * index + 2],
                        [call(f"/invite Player{index}", 13), call("original", 13)],
                    )
                self.assertEqual(press.call_count, count)

    def test_chat_never_pastes_user_clipboard_when_pywin32_missing(self) -> None:
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.dict("sys.modules", {
                "win32clipboard": None,
                "win32con": None,
            }),
            patch.object(input_tools, "press_key") as press,
        ):
            with self.assertRaisesRegex(OSError, "Clipboard indisponible"):
                input_tools.send_chat_command("/zaap 1,2", Mock())
        press.assert_not_called()


    def test_stop_before_chat_never_opens_or_modifies_clipboard(self) -> None:
        logger = Mock()
        with (
            patch.object(input_tools, "clipboard_text") as clipboard,
            patch.object(input_tools, "replace_chat_text_with_clipboard") as paste,
            patch.object(input_tools, "press_key") as press,
        ):
            self.assertFalse(input_tools.send_chat_command(
                "/zaap 1,2", logger, should_stop=lambda: True,
            ))
        clipboard.assert_not_called()
        paste.assert_not_called()
        press.assert_not_called()
        logger.info.assert_called_once_with(
            "Commande chat stoppee avant preparation du clipboard."
        )

    def test_chat_never_submits_after_stop_during_clipboard_paste(self) -> None:
        stopped = False

        def finish_paste(**_kwargs) -> bool:
            nonlocal stopped
            stopped = True
            return True

        with (
            patch.object(input_tools, "clipboard_text"),
            patch.object(input_tools, "replace_chat_text_with_clipboard", side_effect=finish_paste),
            patch.object(input_tools, "press_key") as press,
        ):
            delivered = input_tools.send_chat_command(
                "/zaap 1,2", Mock(), should_stop=lambda: stopped,
            )
        self.assertFalse(delivered)
        press.assert_not_called()

    def test_chat_stop_between_double_submissions_never_sends_second_enter(self) -> None:
        # First check is before clipboard preparation, second before first
        # ENTER; third prevents the final ENTER after the inter-key delay.
        checks = iter((False, False, True))
        with (
            patch.object(input_tools, "clipboard_text"),
            patch.object(input_tools, "replace_chat_text_with_clipboard", return_value=True),
            patch.object(input_tools, "_sleep_ms", return_value=False),
            patch.object(input_tools, "press_key") as press,
        ):
            delivered = input_tools.send_chat_command(
                "/zaap 1,2", Mock(), submit_twice=True,
                should_stop=lambda: next(checks),
            )
        self.assertFalse(delivered)
        press.assert_called_once_with("ENTER")

    def test_keyboard_union_keeps_mouse_sized_native_input(self) -> None:
        self.assertGreaterEqual(ctypes.sizeof(clicks.INPUT_UNION), ctypes.sizeof(clicks.MOUSEINPUT))
        self.assertGreaterEqual(ctypes.sizeof(clicks.INPUT_UNION), ctypes.sizeof(clicks.KEYBDINPUT))

    def test_key_down_and_up_use_sendinput_with_extended_key_and_marker(self) -> None:
        recorded = []
        user32 = Mock()
        user32.MapVirtualKeyW.return_value = 0x47

        def emit(count, ptr, size):
            item = ctypes.cast(ptr, ctypes.POINTER(clicks.INPUT)).contents
            self.assertEqual(count, 1)
            self.assertEqual(size, ctypes.sizeof(clicks.INPUT))
            recorded.append((
                int(item.type),
                int(item.union.ki.wVk),
                int(item.union.ki.wScan),
                int(item.union.ki.dwFlags),
                int(item.union.ki.dwExtraInfo or 0),
            ))
            return 1

        user32.SendInput.side_effect = emit
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.object(input_tools.ctypes, "windll", SimpleNamespace(user32=user32), create=True),
        ):
            input_tools.key_down(0x24)
            input_tools.key_up(0x24)

        marker = input_tools.ATLAS_SYNTHETIC_KEYBOARD_EXTRA_INFO
        self.assertEqual(recorded, [
            (1, 0x24, 0x47, 0x0001, marker),
            (1, 0x24, 0x47, 0x0003, marker),
        ])

    def test_windows_input_layout_and_extended_modifier_flags(self) -> None:
        import os
        if os.name == "nt":
            expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
            self.assertEqual(ctypes.sizeof(clicks.INPUT), expected)
        # Right-side modifiers and divide have an E0 scancode in Win32.
        for vk in (0x5C, 0x6F, 0xA3, 0xA5):
            self.assertIn(vk, input_tools.EXTENDED_VKS)
        user32 = Mock()
        user32.MapVirtualKeyW.return_value = 0x38
        observed = []
        def emit(_count, ptr, _size):
            item = ctypes.cast(ptr, ctypes.POINTER(clicks.INPUT)).contents
            observed.append(int(item.union.ki.dwFlags))
            return 1
        user32.SendInput.side_effect = emit
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.object(input_tools.ctypes, "windll",
                         SimpleNamespace(user32=user32), create=True),
        ):
            input_tools.key_down(0xA5)
            input_tools.key_up(0xA5)
        self.assertEqual(observed, [0x0001, 0x0003])

    def test_failed_sendinput_does_not_claim_key_delivered(self) -> None:
        user32 = Mock()
        user32.MapVirtualKeyW.return_value = 0x1E
        user32.SendInput.return_value = 0
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.object(input_tools.ctypes, "windll", SimpleNamespace(user32=user32), create=True),
        ):
            with self.assertRaisesRegex(OSError, "SendInput refused"):
                input_tools.key_down(0x41)

    def test_failed_sendinput_includes_immediate_win32_diagnostic(self) -> None:
        user32 = Mock()
        user32.MapVirtualKeyW.return_value = 0x1E
        user32.SendInput.return_value = 0
        kernel32 = Mock()
        kernel32.GetLastError.return_value = 5
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.object(input_tools.ctypes, "windll",
                         SimpleNamespace(user32=user32, kernel32=kernel32), create=True),
        ):
            with self.assertRaisesRegex(OSError, "win32_error=5"):
                input_tools.key_down(0x41)
        kernel32.GetLastError.assert_called_once_with()

    def test_non_windows_path_never_sends_synthetic_input(self) -> None:
        with patch.object(input_tools.os, "name", "posix"):
            with patch.object(input_tools, "_configure_keyboard_api", side_effect=AssertionError("wrong OS")):
                input_tools.key_down(0x41)
                input_tools.key_up(0x41)

    def test_hotkey_releases_first_key_if_second_down_fails(self) -> None:
        with (
            patch.object(input_tools, "_vk", side_effect=[0x11, 0x41]),
            patch.object(input_tools, "key_down", side_effect=[None, OSError("blocked")]) as down,
            patch.object(input_tools, "key_up") as up,
        ):
            with self.assertRaisesRegex(OSError, "blocked"):
                input_tools.press_hotkey("CTRL", "A")
        self.assertEqual(down.call_args_list, [call(0x11), call(0x41)])
        up.assert_called_once_with(0x11)

    def test_single_key_preserves_hold_exception_if_release_refused(self) -> None:
        with (
            patch.object(input_tools, "_vk", return_value=0x41),
            patch.object(input_tools, "key_down") as down,
            patch.object(input_tools.time, "sleep",
                         side_effect=RuntimeError("hold interrupted")),
            patch.object(input_tools, "key_up",
                         side_effect=OSError("release refused")) as release,
        ):
            with self.assertRaisesRegex(RuntimeError, "hold interrupted"):
                input_tools.press_key("A", hold_ms=100)
        down.assert_called_once_with(0x41)
        release.assert_called_once_with(0x41)

    def test_original_sendinput_error_survives_release_error(self) -> None:
        with (
            patch.object(input_tools, "_vk", side_effect=[0x11, 0x41]),
            patch.object(input_tools, "key_down",
                         side_effect=[None, OSError("original keyboard failure")]),
            patch.object(input_tools, "key_up",
                         side_effect=OSError("cleanup failure")) as release,
        ):
            with self.assertRaisesRegex(OSError, "original keyboard failure"):
                input_tools.press_hotkey("CTRL", "A")
        release.assert_called_once_with(0x11)

    def test_emergency_release_attempts_every_button_and_modifier(self) -> None:
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.object(clicks, "_send_mouse_flag", side_effect=[False, True, True]) as mouse,
            patch.object(input_tools, "key_up", side_effect=[OSError("blocked"), None, None]) as key,
        ):
            input_tools.release_common_inputs()
        self.assertEqual(mouse.call_args_list, [call(0x0004), call(0x0010), call(0x0040)])
        self.assertEqual(key.call_count, 3)


    def test_finite_excessive_click_delay_refuses_before_mouse_guard(self) -> None:
        for field in range(4):
            for amount in (1001, 10**9):
                with self.subTest(field=field, amount=amount):
                    guard, logger = Mock(), Mock()
                    timings = [0, 0, 0, 0]
                    timings[field] = amount
                    expected_budget = amount * (2 if field == 0 else 1)
                    with (
                        patch.object(clicks.os, "name", "nt"),
                        patch.object(clicks, "set_cursor_pos") as move,
                        patch.object(clicks, "_send_mouse_flag") as sender,
                    ):
                        self.assertFalse(clicks.send_screen_click(
                            300, 200, "Left", 2, *timings, guard, logger,
                        ))
                    move.assert_not_called()
                    sender.assert_not_called()
                    guard.begin.assert_not_called()
                    guard.end.assert_not_called()
                    logger.warning.assert_called_once_with(
                        "Clic synthetique refuse: temporisation excessive budget=%s ms.",
                        expected_budget,
                    )

    def test_valid_timing_budget_still_emits_exactly_one_double_click(self) -> None:
        guard, logger = Mock(), Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "set_cursor_pos"),
            patch.object(clicks, "wait_ms", return_value=False),
            patch.object(clicks, "_send_mouse_flag", return_value=True) as sender,
        ):
            self.assertTrue(clicks.send_screen_click(
                300, 200, "Left", 2, 2, 3, 2, 2, guard, logger,
            ))
        self.assertEqual(sender.call_args_list, [
            call(clicks.MOUSEEVENTF_LEFTDOWN),
            call(clicks.MOUSEEVENTF_LEFTUP),
            call(clicks.MOUSEEVENTF_LEFTDOWN),
            call(clicks.MOUSEEVENTF_LEFTUP),
        ])
        guard.begin.assert_called_once_with(250)
        guard.end.assert_called_once_with(120)

    def test_corrupted_click_timings_fail_closed_before_cursor_or_input(self) -> None:
        for index in range(4):
            for invalid in (float("nan"), float("inf"), None):
                with self.subTest(field=index, invalid=invalid):
                    guard, logger = Mock(), Mock()
                    timings = [20, 30, 40, 50]
                    timings[index] = invalid
                    with (
                        patch.object(clicks.os, "name", "nt"),
                        patch.object(clicks, "set_cursor_pos") as move,
                        patch.object(clicks, "_send_mouse_flag") as send,
                    ):
                        self.assertFalse(clicks.send_screen_click(
                            300, 200, "Left", 2,
                            *timings, guard, logger,
                        ))
                    move.assert_not_called()
                    send.assert_not_called()
                    guard.begin.assert_not_called()
                    guard.end.assert_not_called()
                    logger.warning.assert_called_once_with(
                        "Clic synthetique refuse: temporisation invalide."
                    )

    def test_invalid_or_infinite_client_hwnd_never_targets_unity(self) -> None:
        for invalid in (
            float("inf"), float("nan"), None, object(), False, True,
            0, -1, 2**64, 101.0, 101.9, "101",
        ):
            with self.subTest(handle=repr(invalid)):
                with (
                    patch.object(clicks, "is_unity_window") as check,
                    patch.object(clicks, "send_screen_click") as send,
                ):
                    self.assertFalse(clicks.send_client_click(
                        invalid, 10, 20, "Left", 1, 20, 0, 0, 0,
                        Mock(), Mock(),
                    ))
                check.assert_not_called()
                send.assert_not_called()

    def test_cursor_read_refusal_never_returns_false_zero_origin(self) -> None:
        user32 = SimpleNamespace(GetCursorPos=Mock(return_value=0))
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks.ctypes, "windll",
                         SimpleNamespace(user32=user32), create=True),
        ):
            with self.assertRaisesRegex(OSError, "GetCursorPos refused"):
                clicks.current_cursor_pos()
        user32.GetCursorPos.assert_called_once()

    def test_cursor_read_preserves_negative_multimonitor_coordinates(self) -> None:
        def get_pos(pointer):
            point = ctypes.cast(
                pointer, ctypes.POINTER(ctypes.wintypes.POINT),
            ).contents
            point.x, point.y = -1280, 540
            return 1

        user32 = SimpleNamespace(GetCursorPos=Mock(side_effect=get_pos))
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks.ctypes, "windll",
                         SimpleNamespace(user32=user32), create=True),
        ):
            self.assertEqual(clicks.current_cursor_pos(), (-1280, 540))
        user32.GetCursorPos.assert_called_once()

    def test_successful_cursor_move_preserves_negative_desktop_point(self) -> None:
        def read_position(pointer):
            point = ctypes.cast(
                pointer, ctypes.POINTER(ctypes.wintypes.POINT),
            ).contents
            point.x, point.y = -1200, 600
            return 1

        user32 = SimpleNamespace(
            SetCursorPos=Mock(return_value=1),
            GetCursorPos=Mock(side_effect=read_position),
        )
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks.ctypes, "windll",
                         SimpleNamespace(user32=user32), create=True),
        ):
            self.assertIsNone(clicks.set_cursor_pos(-1200, 600))
        user32.SetCursorPos.assert_called_once_with(-1200, 600)
        user32.GetCursorPos.assert_called_once()

    def test_clipcursor_clamp_refuses_click_without_mouse_down(self) -> None:
        def clipped_position(pointer):
            point = ctypes.cast(
                pointer, ctypes.POINTER(ctypes.wintypes.POINT),
            ).contents
            point.x, point.y = 120, 60
            return 1

        user32 = SimpleNamespace(
            SetCursorPos=Mock(return_value=1),
            GetCursorPos=Mock(side_effect=clipped_position),
        )
        guard, logger = Mock(), Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks.ctypes, "windll",
                         SimpleNamespace(user32=user32), create=True),
            patch.object(clicks, "_send_mouse_flag") as sender,
        ):
            with self.assertRaisesRegex(
                OSError, "cursor confined or moved",
            ):
                clicks.set_cursor_pos(300, 200)
            self.assertFalse(clicks.send_screen_click(
                300, 200, "Right", 2,
                30, 25, 40, 0, guard, logger,
            ))
        sender.assert_not_called()
        guard.end.assert_called_once_with(120)
        logger.exception.assert_called_once_with(
            "Erreur pendant le clic synthetique: button=%s x=%s y=%s",
            "Right", 300, 200,
        )

    def test_cursor_move_win32_refusal_has_diagnostic_and_no_ghost_click(self) -> None:
        user32 = SimpleNamespace(SetCursorPos=Mock(return_value=0))
        kernel32 = SimpleNamespace(GetLastError=Mock(return_value=5))
        windll = SimpleNamespace(user32=user32, kernel32=kernel32)
        guard, logger = Mock(), Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks.ctypes, "windll", windll, create=True),
            patch.object(clicks, "_send_mouse_flag") as sender,
        ):
            with self.assertRaisesRegex(
                OSError, r"SetCursorPos refused at \(300,200\).*win32_error=5",
            ):
                clicks.set_cursor_pos(300, 200)
            self.assertFalse(clicks.send_screen_click(
                300, 200, "Left", 2, 20, 20, 20, 20, guard, logger,
            ))
        user32.SetCursorPos.assert_called_with(300, 200)
        sender.assert_not_called()
        logger.exception.assert_called_once_with(
            "Erreur pendant le clic synthetique: button=%s x=%s y=%s",
            "Left", 300, 200,
        )
        guard.end.assert_called_once_with(120)

    def test_unity_hover_settle_follows_pointer_move_before_mouse_down(self) -> None:
        events = []
        guard = Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "set_cursor_pos",
                         side_effect=lambda *_: events.append("move")),
            patch.object(clicks, "wait_ms",
                         side_effect=lambda ms, _: events.append(("hover", ms)) or False),
            patch.object(clicks, "_send_mouse_flag",
                         side_effect=lambda flag: events.append(("input", flag)) or True),
        ):
            self.assertTrue(clicks.send_screen_click(
                320, 240, "Left", 1, 40, 0, 45, 0, guard, Mock(),
            ))
        self.assertEqual(events, [
            "move", ("hover", 45),
            ("input", clicks.MOUSEEVENTF_LEFTDOWN),
            ("hover", 40),
            ("input", clicks.MOUSEEVENTF_LEFTUP),
        ])
        guard.end.assert_called_once_with(120)

    def test_unity_hover_stop_after_move_sends_no_down(self) -> None:
        events = []
        guard = Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "set_cursor_pos",
                         side_effect=lambda *_: events.append("move")),
            patch.object(clicks, "wait_ms",
                         side_effect=lambda *_: events.append("stop") or True),
            patch.object(clicks, "_send_mouse_flag",
                         side_effect=AssertionError("clicked after stop")),
        ):
            self.assertFalse(clicks.send_screen_click(
                320, 240, "Left", 1, 40, 0, 45, 0,
                guard, Mock(), should_stop=lambda: False,
            ))
        self.assertEqual(events, ["move", "stop"])
        guard.end.assert_called_once_with(120)


    def test_failed_mouse_up_retries_and_reports_final_failure(self) -> None:
        for retry_works in (True, False):
            with self.subTest(retry_works=retry_works):
                guard = Mock()
                logger = Mock()
                with (
                    patch.object(clicks.os, "name", "nt"),
                    patch.object(clicks, "set_cursor_pos"),
                    patch.object(clicks, "_send_mouse_flag",
                                 side_effect=[True, False, retry_works]) as sender,
                ):
                    result = clicks.send_screen_click(
                        300, 200, "Left", 1, 0, 0, 0, 0, guard, logger,
                    )
                self.assertFalse(result)
                self.assertEqual(
                    [c.args[0] for c in sender.call_args_list],
                    [clicks.MOUSEEVENTF_LEFTDOWN,
                     clicks.MOUSEEVENTF_LEFTUP,
                     clicks.MOUSEEVENTF_LEFTUP],
                )
                guard.end.assert_called_once_with(120)
                if retry_works:
                    logger.warning.assert_not_called()
                else:
                    logger.warning.assert_called_once_with(
                        "Relachement souris de secours refuse: button=%s",
                        "Left",
                    )

    def test_infinite_click_count_is_bounded_to_single_complete_pair(self) -> None:
        guard = Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "set_cursor_pos"),
            patch.object(clicks, "_send_mouse_flag", return_value=True) as send,
        ):
            self.assertTrue(clicks.send_screen_click(
                300, 200, "Left", float("inf"),
                0, 0, 0, 0, guard, Mock(),
            ))
        self.assertEqual(send.call_args_list, [
            call(clicks.MOUSEEVENTF_LEFTDOWN),
            call(clicks.MOUSEEVENTF_LEFTUP),
        ])
        guard.end.assert_called_once_with(120)

    def test_stop_during_mouse_down_hold_releases_one_matching_up(self) -> None:
        for button in ("Left", "Right"):
            with self.subTest(button=button):
                stopped = [False]
                guard = Mock()
                down = (
                    clicks.MOUSEEVENTF_LEFTDOWN if button == "Left"
                    else clicks.MOUSEEVENTF_RIGHTDOWN
                )
                up = (
                    clicks.MOUSEEVENTF_LEFTUP if button == "Left"
                    else clicks.MOUSEEVENTF_RIGHTUP
                )
                with (
                    patch.object(clicks.os, "name", "nt"),
                    patch.object(clicks, "set_cursor_pos"),
                    patch.object(clicks, "_send_mouse_flag",
                                 return_value=True) as sender,
                    patch.object(clicks, "wait_ms",
                                 side_effect=lambda *_: True),
                ):
                    self.assertFalse(clicks.send_screen_click(
                        300, 200, button, 2, 40, 0, 0, 0,
                        guard, Mock(), should_stop=lambda: stopped[0],
                    ))
                self.assertEqual(sender.call_args_list, [
                    call(down), call(up),
                ])
                guard.end.assert_called_once_with(120)

    def test_double_gap_stop_never_emits_second_down(self) -> None:
        for button in ("Left", "Right"):
            with self.subTest(button=button):
                guard = Mock()
                down = (
                    clicks.MOUSEEVENTF_LEFTDOWN if button == "Left"
                    else clicks.MOUSEEVENTF_RIGHTDOWN
                )
                up = (
                    clicks.MOUSEEVENTF_LEFTUP if button == "Left"
                    else clicks.MOUSEEVENTF_RIGHTUP
                )
                with (
                    patch.object(clicks.os, "name", "nt"),
                    patch.object(clicks, "set_cursor_pos"),
                    patch.object(clicks, "_send_mouse_flag",
                                 return_value=True) as sender,
                    patch.object(clicks, "wait_ms",
                                 side_effect=lambda *_: True),
                ):
                    self.assertFalse(clicks.send_screen_click(
                        300, 200, button, 2, 0, 30, 0, 0,
                        guard, Mock(), should_stop=lambda: False,
                    ))
                self.assertEqual(sender.call_args_list, [
                    call(down), call(up),
                ])
                guard.end.assert_called_once_with(120)

    def test_post_up_settle_exception_retains_successful_send(self) -> None:
        for button in ("Left", "Right"):
            with self.subTest(button=button):
                guard, logger = Mock(), Mock()
                down = (
                    clicks.MOUSEEVENTF_LEFTDOWN if button == "Left"
                    else clicks.MOUSEEVENTF_RIGHTDOWN
                )
                up = (
                    clicks.MOUSEEVENTF_LEFTUP if button == "Left"
                    else clicks.MOUSEEVENTF_RIGHTUP
                )
                with (
                    patch.object(clicks.os, "name", "nt"),
                    patch.object(clicks, "set_cursor_pos"),
                    patch.object(clicks, "_send_mouse_flag",
                                 return_value=True) as sender,
                    patch.object(clicks, "wait_ms",
                                 side_effect=OSError("settle failed")),
                ):
                    self.assertTrue(clicks.send_screen_click(
                        300, 200, button, 1, 0, 0, 0, 35,
                        guard, logger,
                    ))
                self.assertEqual(sender.call_args_list, [call(down), call(up)])
                logger.exception.assert_called_once_with(
                    "Clic envoyé: temporisation après UP impossible; livraison conservée."
                )
                guard.end.assert_called_once_with(120)

    def test_post_up_stop_does_not_erase_completed_click_delivery(self) -> None:
        for button in ("Left", "Right"):
            for count in (1, 2):
                with self.subTest(button=button, clicks=count):
                    stopped = [False]
                    guard, logger = Mock(), Mock()
                    down = (
                        clicks.MOUSEEVENTF_LEFTDOWN if button == "Left"
                        else clicks.MOUSEEVENTF_RIGHTDOWN
                    )
                    up = (
                        clicks.MOUSEEVENTF_LEFTUP if button == "Left"
                        else clicks.MOUSEEVENTF_RIGHTUP
                    )
                    flags = []

                    def send(flag):
                        flags.append(flag)
                        if len(flags) == count * 2:
                            stopped[0] = True
                        return True

                    with (
                        patch.object(clicks.os, "name", "nt"),
                        patch.object(clicks, "set_cursor_pos"),
                        patch.object(clicks, "_send_mouse_flag",
                                     side_effect=send),
                        patch.object(clicks, "wait_ms",
                                     side_effect=lambda *_: stopped[0]) as wait,
                    ):
                        self.assertTrue(clicks.send_screen_click(
                            300, 200, button, count, 0, 0, 0, 50,
                            guard, logger, should_stop=lambda: stopped[0],
                        ))
                    self.assertEqual(flags, [down, up] * count)
                    wait.assert_called_once_with(50, unittest.mock.ANY)
                    guard.end.assert_called_once_with(120)

    def test_failed_first_up_aborts_double_click_before_second_down(self) -> None:
        for retry_works in (True, False):
            for button in ("Left", "Right"):
                with self.subTest(retry=retry_works, button=button):
                    down = (
                        clicks.MOUSEEVENTF_LEFTDOWN
                        if button == "Left" else clicks.MOUSEEVENTF_RIGHTDOWN
                    )
                    up = (
                        clicks.MOUSEEVENTF_LEFTUP
                        if button == "Left" else clicks.MOUSEEVENTF_RIGHTUP
                    )
                    guard, logger = Mock(), Mock()
                    with (
                        patch.object(clicks.os, "name", "nt"),
                        patch.object(clicks, "set_cursor_pos"),
                        patch.object(clicks, "_send_mouse_flag",
                                     side_effect=[True, False, retry_works]) as send,
                    ):
                        self.assertFalse(clicks.send_screen_click(
                            300, 200, button, 2, 0, 0, 0, 0, guard, logger,
                        ))
                    self.assertEqual(
                        [call.args[0] for call in send.call_args_list],
                        [down, up, up],
                    )
                    guard.end.assert_called_once_with(120)
                    if retry_works:
                        logger.warning.assert_not_called()
                    else:
                        logger.warning.assert_called_once_with(
                            "Relachement souris de secours refuse: button=%s",
                            button,
                        )

    def test_refused_mouse_down_does_not_send_unpaired_up(self) -> None:
        sent = []
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "set_cursor_pos"),
            patch.object(clicks, "_send_mouse_flag",
                         side_effect=lambda flag: sent.append(flag) or False),
        ):
            result = clicks.send_screen_click(
                300, 200, "Left", 1, 0, 0, 0, 0, Mock(), Mock(),
            )
        self.assertFalse(result)
        self.assertEqual(sent, [clicks.MOUSEEVENTF_LEFTDOWN])

    def test_second_mouse_down_refusal_does_not_emit_second_up(self) -> None:
        sent = []
        def sender(flag):
            sent.append(flag)
            return flag != clicks.MOUSEEVENTF_LEFTDOWN or len(sent) == 1

        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "set_cursor_pos"),
            patch.object(clicks, "_send_mouse_flag", side_effect=sender),
        ):
            result = clicks.send_screen_click(
                300, 200, "Left", 2, 0, 0, 0, 0, Mock(), Mock(),
            )
        self.assertFalse(result)
        self.assertEqual(sent, [
            clicks.MOUSEEVENTF_LEFTDOWN,
            clicks.MOUSEEVENTF_LEFTUP,
            clicks.MOUSEEVENTF_LEFTDOWN,
        ])

    def test_client_click_aborts_on_focus_theft_during_hover(self) -> None:
        focused = [202]
        guard = Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "is_unity_window", return_value=True),
            patch.object(clicks, "clamp_client_point", return_value=(10, 20)),
            patch.object(clicks, "client_to_screen", return_value=(300, 200)),
            patch.object(clicks, "foreground_window",
                         side_effect=lambda: focused[0]),
            patch.object(clicks, "set_cursor_pos",
                         side_effect=lambda *_: focused.__setitem__(0, 999)),
            patch.object(clicks, "wait_ms",
                         side_effect=lambda ms, stop: stop()),
            patch.object(clicks, "_send_mouse_flag") as sender,
        ):
            result = clicks.send_client_click(
                202, 10, 20, "Left", 1, 35, 0, 50, 0, guard, Mock(),
                should_stop=lambda: False,
            )
        self.assertFalse(result)
        sender.assert_not_called()
        guard.end.assert_called_once_with(120)

    def test_client_click_respects_emergency_stop_before_cursor_move(self) -> None:
        guard = Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "is_unity_window", return_value=True),
            patch.object(clicks, "clamp_client_point", return_value=(10, 20)),
            patch.object(clicks, "client_to_screen", return_value=(300, 200)),
            patch.object(clicks, "foreground_window",
                         side_effect=AssertionError("focus after stop")),
            patch.object(clicks, "set_cursor_pos") as move,
            patch.object(clicks, "_send_mouse_flag") as sender,
        ):
            result = clicks.send_client_click(
                202, 10, 20, "Right", 1, 35, 0, 50, 0, guard, Mock(),
                should_stop=lambda: True,
            )
        self.assertFalse(result)
        move.assert_not_called()
        sender.assert_not_called()
        guard.end.assert_called_once_with(120)

    def test_client_double_click_checks_focus_before_second_down(self) -> None:
        focused = [202]
        events = []
        guard = Mock()
        def send(flag):
            events.append(flag)
            if flag == clicks.MOUSEEVENTF_LEFTUP:
                focused[0] = 999
            return True

        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "is_unity_window", return_value=True),
            patch.object(clicks, "clamp_client_point", return_value=(10, 20)),
            patch.object(clicks, "client_to_screen", return_value=(300, 200)),
            patch.object(clicks, "foreground_window",
                         side_effect=lambda: focused[0]),
            patch.object(clicks, "set_cursor_pos"),
            patch.object(clicks, "wait_ms",
                         side_effect=lambda ms, stop: stop()),
            patch.object(clicks, "_send_mouse_flag", side_effect=send),
        ):
            result = clicks.send_client_click(
                202, 10, 20, "Left", 2, 35, 60, 50, 0, guard, Mock(),
                should_stop=lambda: False,
            )
        self.assertFalse(result)
        self.assertEqual(events, [
            clicks.MOUSEEVENTF_LEFTDOWN,
            clicks.MOUSEEVENTF_LEFTUP,
        ])
        guard.end.assert_called_once_with(120)

    def test_physical_source_up_reaches_unity_after_replay_starts(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            LLMHF_INJECTED, MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONUP,
        )

        state = InputState()
        logger = logging.getLogger("test_native_switch_click")
        calls = []

        def released(button, x, y):
            calls.append((button, x, y))
            state.begin_mouse_block("Switch clique")
            return True

        hook = MouseHook(
            state, SyntheticInputGuard(logger), logger,
            Mock(return_value=False), release_callback=released,
        )
        mouse = MSLLHOOKSTRUCT()
        mouse.pt.x, mouse.pt.y = 300, 240
        user32 = Mock()
        user32.CallNextHookEx.return_value = 51
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            addr = ctypes.addressof(mouse)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 51)
            self.assertFalse(state.is_mouse_blocked())
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 51)
            self.assertEqual(calls, [("Left", 300, 240)])
            self.assertTrue(state.is_mouse_blocked())
            # No right-button DOWN was intercepted by Atlas. Its UP must
            # remain native even though the left-button replay just started.
            self.assertEqual(hook._mouse_proc(0, WM_RBUTTONUP, addr), 51)
            # Synthesized releases never trigger physical replay.
            mouse.flags = LLMHF_INJECTED
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 51)
            self.assertEqual(len(calls), 1)

    def test_busy_mouse_hook_remains_fail_closed_when_logging_fails(self) -> None:
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP,
        )

        logger = Mock()
        state = InputState()
        hook = MouseHook(state, SyntheticInputGuard(logger), logger, Mock())
        event = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 42
        with (
            patch.object(
                ctypes, "windll", SimpleNamespace(user32=user32), create=True,
            ),
            patch.object(
                hook, "_log_blocked_event",
                side_effect=RuntimeError("log formatter failed"),
            ),
        ):
            state.begin_mouse_block("Miroir")
            addr = ctypes.addressof(event)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 1)
            self.assertEqual(hook._consumed_releases, {WM_LBUTTONUP})
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 1)
            self.assertEqual(hook._consumed_releases, set())
            state.clear_mouse_block()
        logger.exception.assert_called_once_with(
            "Hook souris: journalisation blocage impossible.",
        )
        user32.CallNextHookEx.assert_not_called()

    def test_busy_mouse_hook_bursts_two_four_six_eight_are_counted(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEWHEEL,
        )

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                logger = logging.getLogger("test_busy_hook_bursts")
                state = InputState()
                click = Mock(return_value=False)
                wheel = Mock(return_value=False)
                hook = MouseHook(
                    state, SyntheticInputGuard(logger), logger,
                    click, wheel_callback=wheel,
                )
                event = MSLLHOOKSTRUCT()
                event.pt.x, event.pt.y = 30, 40
                event.mouseData = 120 << 16
                user32 = Mock()
                user32.CallNextHookEx.return_value = 51

                with patch.object(
                    ctypes, "windll", SimpleNamespace(user32=user32),
                    create=True,
                ):
                    addr = ctypes.addressof(event)
                    state.begin_mouse_block("Miroir")
                    for _ in range(count):
                        self.assertEqual(
                            hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 1,
                        )
                        self.assertEqual(
                            hook._mouse_proc(0, WM_MOUSEWHEEL, addr), 1,
                        )
                        self.assertEqual(
                            hook._mouse_proc(0, WM_LBUTTONUP, addr), 1,
                        )
                    self.assertEqual(hook._blocked_click_count, count)
                    self.assertEqual(hook._blocked_wheel_count, count)
                    self.assertEqual(hook._consumed_releases, set())
                    state.clear_mouse_block()
                    # The first new click after Stop must be a real
                    # click, not a replay of a previously blocked gesture.
                    self.assertEqual(
                        hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 51,
                    )
                    self.assertEqual(
                        hook._mouse_proc(0, WM_LBUTTONUP, addr), 51,
                    )
                click.assert_called_once_with("Left", 30, 40)
                wheel.assert_not_called()
                self.assertEqual(hook._blocked_click_count, count)
                self.assertEqual(hook._blocked_wheel_count, count)

    def test_native_up_from_press_before_busy_worker_is_not_swallowed(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP,
            WM_RBUTTONDOWN, WM_RBUTTONUP,
            WM_MBUTTONDOWN, WM_MBUTTONUP,
            WM_XBUTTONDOWN, WM_XBUTTONUP,
        )

        for down, up in (
            (WM_LBUTTONDOWN, WM_LBUTTONUP),
            (WM_RBUTTONDOWN, WM_RBUTTONUP),
            (WM_MBUTTONDOWN, WM_MBUTTONUP),
            (WM_XBUTTONDOWN, WM_XBUTTONUP),
        ):
            with self.subTest(down=down):
                state = InputState()
                logger = logging.getLogger("test_pressed_before_busy")
                callback = Mock(return_value=False)
                release = Mock(return_value=False)
                hook = MouseHook(
                    state, SyntheticInputGuard(logger), logger,
                    callback, release_callback=release,
                )
                event = MSLLHOOKSTRUCT()
                event.pt.x, event.pt.y = 10, 20
                user32 = Mock()
                user32.CallNextHookEx.return_value = 42
                with patch.object(
                    ctypes, "windll", SimpleNamespace(user32=user32),
                    create=True,
                ):
                    addr = ctypes.addressof(event)
                    # Physical press starts in the client before the worker.
                    self.assertEqual(hook._mouse_proc(0, down, addr), 42)
                    self.assertEqual(hook._consumed_releases, set())
                    state.begin_mouse_block("Miroir")
                    # This must pass; swallowing only UP can leave a held
                    # button in the client that received the native DOWN.
                    self.assertEqual(hook._mouse_proc(0, up, addr), 42)
                    self.assertEqual(hook._consumed_releases, set())
                    self.assertEqual(hook._blocked_click_count, 0)
                    state.end_mouse_block()
                if down in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
                    callback.assert_called_once()
                    release.assert_called_once()
                else:
                    callback.assert_not_called()
                    release.assert_not_called()

    def test_native_up_during_block_never_creates_a_false_drop_count(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import MSLLHOOKSTRUCT, MouseHook, WM_LBUTTONUP

        state = InputState()
        logger = logging.getLogger("test_busy_release_counts")
        hook = MouseHook(state, SyntheticInputGuard(logger), logger, Mock())
        event = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 99
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32),
            create=True,
        ):
            state.begin_mouse_block("Miroir")
            self.assertEqual(
                hook._mouse_proc(0, WM_LBUTTONUP, ctypes.addressof(event)),
                99,
            )
            state.end_mouse_block()
        self.assertEqual(hook._blocked_click_count, 0)
        self.assertEqual(hook._blocked_wheel_count, 0)

    def test_busy_down_keeps_matching_up_consumed_after_worker_finishes(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP,
            WM_RBUTTONDOWN, WM_RBUTTONUP,
            WM_MBUTTONDOWN, WM_MBUTTONUP,
            WM_XBUTTONDOWN, WM_XBUTTONUP,
        )

        for down, up in (
            (WM_LBUTTONDOWN, WM_LBUTTONUP),
            (WM_RBUTTONDOWN, WM_RBUTTONUP),
            (WM_MBUTTONDOWN, WM_MBUTTONUP),
            (WM_XBUTTONDOWN, WM_XBUTTONUP),
        ):
            with self.subTest(down=down):
                logger = logging.getLogger("test_busy_mouse_pairs")
                state = InputState()
                click = Mock(return_value=False)
                released = Mock(return_value=False)
                hook = MouseHook(
                    state, SyntheticInputGuard(logger), logger, click,
                    release_callback=released,
                )
                event = MSLLHOOKSTRUCT()
                event.pt.x, event.pt.y = 30, 40
                user32 = Mock()
                user32.CallNextHookEx.return_value = 51
                with patch.object(
                    ctypes, "windll",
                    SimpleNamespace(user32=user32), create=True,
                ):
                    state.begin_mouse_block("Miroir")
                    addr = ctypes.addressof(event)
                    self.assertEqual(hook._mouse_proc(0, down, addr), 1)
                    self.assertEqual(hook._consumed_releases, {up})
                    state.end_mouse_block()
                    # The worker is gone, but the physical UP still belongs
                    # to the swallowed DOWN, not to the active Unity window.
                    self.assertEqual(hook._mouse_proc(0, up, addr), 1)
                    self.assertEqual(hook._consumed_releases, set())
                    self.assertEqual(hook._mouse_proc(0, up, addr), 51)
                click.assert_not_called()
                released.assert_not_called()

    def test_busy_xbuttons_remain_independent_after_stop_and_synthetic_up(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            LLMHF_INJECTED, MSLLHOOKSTRUCT, MouseHook,
            WM_XBUTTONDOWN, WM_XBUTTONUP,
        )

        for first, second in ((1, 2), (2, 1)):
            with self.subTest(first=first, second=second):
                state = InputState()
                callback = Mock(return_value=False)
                logger = logging.getLogger("test_busy_thumb_buttons")
                hook = MouseHook(
                    state, SyntheticInputGuard(logger), logger, callback,
                )
                event = MSLLHOOKSTRUCT()
                user32 = Mock()
                user32.CallNextHookEx.return_value = 51
                with patch.object(
                    ctypes, "windll",
                    SimpleNamespace(user32=user32), create=True,
                ):
                    pointer = ctypes.addressof(event)
                    state.begin_mouse_block("Miroir")
                    event.mouseData = first << 16
                    self.assertEqual(
                        hook._mouse_proc(0, WM_XBUTTONDOWN, pointer), 1,
                    )
                    event.mouseData = second << 16
                    self.assertEqual(
                        hook._mouse_proc(0, WM_XBUTTONDOWN, pointer), 1,
                    )
                    self.assertEqual(hook._blocked_click_count, 2)
                    self.assertEqual(
                        hook._consumed_releases,
                        {WM_XBUTTONUP | (first << 16),
                         WM_XBUTTONUP | (second << 16)},
                    )
                    # Stop ends the global block, but both swallowed DOWNs
                    # still own their separate UPs across different clients.
                    state.clear_mouse_block()
                    event.flags = LLMHF_INJECTED
                    self.assertEqual(
                        hook._mouse_proc(0, WM_XBUTTONUP, pointer), 51,
                    )
                    self.assertEqual(len(hook._consumed_releases), 2)
                    event.flags = 0
                    self.assertEqual(
                        hook._mouse_proc(0, WM_XBUTTONUP, pointer), 1,
                    )
                    self.assertEqual(
                        hook._consumed_releases,
                        {WM_XBUTTONUP | (first << 16)},
                    )
                    event.mouseData = first << 16
                    self.assertEqual(
                        hook._mouse_proc(0, WM_XBUTTONUP, pointer), 1,
                    )
                    self.assertFalse(hook._consumed_releases)
                    # Only a NEW unpaired UP can reach the active window.
                    self.assertEqual(
                        hook._mouse_proc(0, WM_XBUTTONUP, pointer), 51,
                    )
                callback.assert_not_called()

    def test_busy_mouse_moves_do_not_decode_xbutton_release(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook,
            WM_MOUSEMOVE, WM_XBUTTONDOWN, WM_XBUTTONUP,
        )

        state = InputState()
        logger = logging.getLogger("test_mouse_move_flood_xbutton")
        hook = MouseHook(state, SyntheticInputGuard(logger), logger, Mock())
        event = MSLLHOOKSTRUCT()
        event.mouseData = 1 << 16
        user32 = Mock()
        user32.CallNextHookEx.return_value = 51
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            ptr = ctypes.addressof(event)
            state.begin_mouse_block("Miroir")
            self.assertEqual(hook._mouse_proc(0, WM_XBUTTONDOWN, ptr), 1)
            with patch(
                "app.input.mouse_hooks._physical_release_token",
                side_effect=AssertionError("Move must not decode XBUTTON"),
            ):
                for _ in range(200):
                    self.assertEqual(hook._mouse_proc(0, WM_MOUSEMOVE, ptr), 1)
            self.assertEqual(
                hook._consumed_releases, {WM_XBUTTONUP | (1 << 16)},
            )
            state.end_mouse_block()
            self.assertEqual(hook._mouse_proc(0, WM_XBUTTONUP, ptr), 1)
            self.assertFalse(hook._consumed_releases)
        self.assertEqual(hook._blocked_click_count, 1)

    def test_busy_xbutton_up_from_other_thumb_is_not_swallowed(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook, WM_XBUTTONDOWN, WM_XBUTTONUP,
        )

        state = InputState()
        hook = MouseHook(
            state, SyntheticInputGuard(logging.getLogger("test_xbutton_up")),
            logging.getLogger("test_xbutton_up"), Mock(),
        )
        event = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 51
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            pointer = ctypes.addressof(event)
            state.begin_mouse_block("Miroir")
            event.mouseData = 1 << 16
            self.assertEqual(hook._mouse_proc(0, WM_XBUTTONDOWN, pointer), 1)
            state.end_mouse_block()
            event.mouseData = 2 << 16
            self.assertEqual(hook._mouse_proc(0, WM_XBUTTONUP, pointer), 51)
            self.assertEqual(
                hook._consumed_releases, {WM_XBUTTONUP | (1 << 16)},
            )
            event.mouseData = 1 << 16
            self.assertEqual(hook._mouse_proc(0, WM_XBUTTONUP, pointer), 1)
            self.assertFalse(hook._consumed_releases)

    def test_emergency_clear_keeps_blocked_physical_pair_balanced(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook, WM_LBUTTONDOWN, WM_LBUTTONUP,
        )

        logger = logging.getLogger("test_blocked_stop_pairs")
        state = InputState()
        click = Mock(return_value=False)
        hook = MouseHook(
            state, SyntheticInputGuard(logger), logger, click,
        )
        event = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 51
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            addr = ctypes.addressof(event)
            state.begin_mouse_block("Miroir")
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 1)
            self.assertEqual(hook._consumed_releases, {WM_LBUTTONUP})
            # Emergency stop clears the mouse block asynchronously.
            state.clear_mouse_block()
            self.assertFalse(state.is_mouse_blocked())
            # The native UP is still paired with the swallowed DOWN.
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 1)
            self.assertEqual(hook._consumed_releases, set())
            # A NEW native click after Stop remains untouched.
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 51)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 51)
        click.assert_called_once_with("Left", 0, 0)

    def test_synthetic_up_cannot_unlock_busy_physical_down(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            LLMHF_INJECTED, MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP,
        )

        logger = logging.getLogger("test_synthetic_up_busy_pair")
        state = InputState()
        hook = MouseHook(
            state, SyntheticInputGuard(logger), logger, Mock(),
        )
        event = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 51
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            state.begin_mouse_block("Miroir")
            addr = ctypes.addressof(event)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 1)
            state.end_mouse_block()
            event.flags = LLMHF_INJECTED
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 51)
            self.assertEqual(hook._consumed_releases, {WM_LBUTTONUP})
            event.flags = 0
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 1)
            self.assertEqual(hook._consumed_releases, set())

    def test_native_release_callback_keeps_consumed_pairs_balanced(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook, WM_LBUTTONDOWN, WM_LBUTTONUP,
        )

        logger = logging.getLogger("test_native_switch_pair")
        click = Mock(return_value=True)
        release = Mock(return_value=False)
        hook = MouseHook(
            InputState(), SyntheticInputGuard(logger), logger,
            click, release_callback=release,
        )
        mouse = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 41
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            addr = ctypes.addressof(mouse)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 1)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 1)
        # A swallowed DOWN keeps ownership of its UP. Releasing it to
        # Unity (or dispatching physical-source replay) would split the pair.
        release.assert_not_called()
        self.assertEqual(hook._consumed_releases, set())

    def test_consumed_down_up_pair_is_not_stolen_by_native_release(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            LLMHF_INJECTED, MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP,
        )

        logger = logging.getLogger("test_native_consumed_release_order")
        click = Mock(return_value=True)
        release = Mock(return_value=True)
        hook = MouseHook(
            InputState(), SyntheticInputGuard(logger), logger, click,
            release_callback=release,
        )
        event = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 37
        with patch.object(ctypes, "windll",
                          SimpleNamespace(user32=user32), create=True):
            addr = ctypes.addressof(event)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 1)
            self.assertEqual(hook._consumed_releases, {WM_LBUTTONUP})
            # Synthetic UP must never discharge the physical release lease.
            event.flags = LLMHF_INJECTED
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 37)
            self.assertEqual(hook._consumed_releases, {WM_LBUTTONUP})
            event.flags = 0
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 1)
            self.assertEqual(hook._consumed_releases, set())
        release.assert_not_called()
        click.assert_called_once()

    def test_busy_input_counters_include_events_hidden_by_warning_throttle(self) -> None:
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MouseHook, WM_LBUTTONDOWN, WM_MOUSEWHEEL, WM_MOUSEMOVE,
            WM_LBUTTONUP, WM_RBUTTONDOWN,
        )

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                logger = Mock()
                hook = MouseHook(
                    InputState(), SyntheticInputGuard(logger), logger, Mock(),
                )
                with patch("app.input.mouse_hooks.time.monotonic",
                           return_value=1.0):
                    for _ in range(count):
                        hook._log_blocked_event(WM_LBUTTONDOWN, 12, 15)
                        hook._log_blocked_event(WM_MOUSEWHEEL, 12, 15)
                        hook._log_blocked_event(WM_MOUSEMOVE, 12, 15)
                        hook._log_blocked_event(WM_LBUTTONUP, 12, 15)
                self.assertEqual(hook._blocked_click_count, count)
                self.assertEqual(hook._blocked_wheel_count, count)
                self.assertEqual(logger.info.call_count, 2)
                logger.info.assert_any_call(
                    "Organizer entrées physiques bloquées: clics=%s molettes=%s",
                    1, 0,
                )
                logger.info.assert_any_call(
                    "Organizer entrées physiques bloquées: clics=%s molettes=%s",
                    1, 1,
                )
                with patch("app.input.mouse_hooks.time.monotonic",
                           return_value=1.5):
                    hook._log_blocked_event(WM_RBUTTONDOWN, 12, 15)
                self.assertEqual(hook._blocked_click_count, count + 1)
                logger.info.assert_called_with(
                    "Organizer entrées physiques bloquées: clics=%s molettes=%s",
                    count + 1, count,
                )

    def test_timeout_stopping_live_hook_retains_physical_release_lease(self) -> None:
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import MouseHook, WM_LBUTTONUP

        logger = Mock()
        hook = MouseHook(InputState(), SyntheticInputGuard(logger), logger, Mock())
        hook._consumed_releases.add(WM_LBUTTONUP)
        live_thread = Mock()
        live_thread.is_alive.return_value = True
        hook._thread = live_thread
        with patch("app.input.mouse_hooks.stop_message_hook") as stop:
            hook.stop()
        stop.assert_called_once_with(hook)
        self.assertEqual(hook._consumed_releases, {WM_LBUTTONUP})
        logger.warning.assert_called_once_with(
            "Hook souris toujours actif après stop: relâchements réservés=%s",
            1,
        )
        # The existing hook-thread finally block owns final cleanup.
        hook._consumed_releases.clear()
        self.assertEqual(hook._consumed_releases, set())

    def test_stop_preserves_native_release_lease_until_hook_is_removed(self) -> None:
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import MouseHook, WM_LBUTTONUP

        logger = Mock()
        hook = MouseHook(InputState(), SyntheticInputGuard(logger), logger, Mock())
        hook._consumed_releases.add(WM_LBUTTONUP)
        observed = []
        with patch(
            "app.input.mouse_hooks.stop_message_hook",
            side_effect=lambda current: observed.append(
                set(current._consumed_releases)
            ),
        ):
            hook.stop()
        self.assertEqual(observed, [{WM_LBUTTONUP}])
        self.assertEqual(hook._consumed_releases, set())
        self.assertEqual(hook._last_block_log, 0.0)

    def test_busy_input_telemetry_resets_on_mouse_hook_stop(self) -> None:
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import MouseHook, WM_LBUTTONDOWN, WM_MOUSEWHEEL

        logger = Mock()
        hook = MouseHook(InputState(), SyntheticInputGuard(logger), logger, Mock())
        with patch("app.input.mouse_hooks.time.monotonic", return_value=1.0):
            hook._log_blocked_event(WM_LBUTTONDOWN, 10, 20)
            hook._log_blocked_event(WM_MOUSEWHEEL, 10, 20)
        self.assertEqual((hook._blocked_click_count, hook._blocked_wheel_count),
                         (1, 1))
        with patch("app.input.mouse_hooks.stop_message_hook") as stop_hook:
            hook.stop()
        stop_hook.assert_called_once_with(hook)
        logger.info.assert_any_call(
            "Organizer hooks arrêtés: clics bloqués=%s molettes bloquées=%s",
            1, 1,
        )
        self.assertEqual((hook._blocked_click_count, hook._blocked_wheel_count),
                         (0, 0))

    def test_busy_native_click_warning_not_hidden_by_mouse_move_flood(self) -> None:
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MouseHook, WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_RBUTTONDOWN,
        )

        logger = Mock()
        state = InputState()
        state.begin_mouse_block("Miroir")
        hook = MouseHook(state, SyntheticInputGuard(logger), logger, Mock())
        with patch("app.input.mouse_hooks.time.monotonic",
                   side_effect=[1.0, 1.1, 1.5]):
            for _ in range(500):
                hook._log_blocked_event(WM_MOUSEMOVE, 12, 15)
            hook._log_blocked_event(WM_LBUTTONDOWN, 12, 15)
            hook._log_blocked_event(WM_RBUTTONDOWN, 12, 15)
            hook._log_blocked_event(WM_RBUTTONDOWN, 12, 15)
        self.assertEqual(logger.warning.call_count, 2)
        logger.warning.assert_any_call(
            "Clic physique non diffusé (macro occupée=%s): event=%s",
            "Miroir", "left_down",
        )
        self.assertEqual(logger.debug.call_count, 0)

    def test_busy_mouse_up_cannot_hide_next_down_warning(self) -> None:
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MouseHook, WM_LBUTTONUP, WM_RBUTTONUP,
            WM_LBUTTONDOWN, WM_MOUSEWHEEL,
        )

        logger = Mock()
        state = InputState()
        state.begin_mouse_block("Miroir")
        hook = MouseHook(state, SyntheticInputGuard(logger), logger, Mock())
        with patch("app.input.mouse_hooks.time.monotonic",
                   side_effect=[1.0, 1.5]):
            for _ in range(100):
                hook._log_blocked_event(WM_LBUTTONUP, 10, 20)
                hook._log_blocked_event(WM_RBUTTONUP, 10, 20)
            hook._log_blocked_event(WM_LBUTTONDOWN, 10, 20)
            hook._log_blocked_event(WM_MOUSEWHEEL, 10, 20)
        logger.warning.assert_any_call(
            "Clic physique non diffusé (macro occupée=%s): event=%s",
            "Miroir", "left_down",
        )
        logger.warning.assert_any_call(
            "Molette physique non diffusée (macro occupée=%s): event=%s",
            "Miroir", "wheel",
        )
        self.assertEqual(logger.warning.call_count, 2)

    def test_physical_click_and_wheel_survive_residual_synthetic_time_guard(self) -> None:
        import logging
        from app.input.input_state import (
            ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO, InputState, SyntheticInputGuard,
        )
        from app.input.mouse_hooks import (
            LLMHF_INJECTED, MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEWHEEL,
        )

        logger = logging.getLogger("test_native_event_after_sendinput")
        guard = SyntheticInputGuard(logger)
        guard.begin(10000)
        click = Mock(return_value=True)
        wheel = Mock(return_value=True)
        hook = MouseHook(
            InputState(), guard, logger, click, wheel_callback=wheel,
        )
        mouse = MSLLHOOKSTRUCT()
        mouse.pt.x = 15
        mouse.pt.y = 20
        mouse.mouseData = 120 << 16
        user32 = Mock()
        user32.CallNextHookEx.return_value = 37
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            addr = ctypes.addressof(mouse)
            # The temporal guard is active, but Win32 identifies these
            # events as PHYSICAL. Do not silently miss a fast second gesture.
            self.assertEqual(hook._mouse_proc(0, WM_MOUSEWHEEL, addr), 1)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 1)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 1)
            wheel.assert_called_once_with(120, 15, 20, False)
            click.assert_called_once_with("Left", 15, 20)
            # Actually injected events still never enter user callbacks.
            mouse.flags = LLMHF_INJECTED
            self.assertEqual(hook._mouse_proc(0, WM_MOUSEWHEEL, addr), 37)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 37)
            mouse.flags = 0
            mouse.dwExtraInfo = ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 37)
            self.assertEqual(hook._mouse_proc(0, WM_MOUSEWHEEL, addr), 37)
        click.assert_called_once()
        wheel.assert_called_once()
        guard.reset()

    def test_actual_mouse_block_still_rejects_physical_clicks(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook, WM_LBUTTONDOWN,
        )

        logger = logging.getLogger("test_mirror_block_stays_active")
        state = InputState()
        state.begin_mouse_block("Miroir")
        click = Mock(return_value=True)
        hook = MouseHook(state, SyntheticInputGuard(logger), logger, click)
        mouse = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 37
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            self.assertEqual(
                hook._mouse_proc(0, WM_LBUTTONDOWN, ctypes.addressof(mouse)), 1,
            )
        click.assert_not_called()
        state.end_mouse_block()

    def test_native_release_and_mirror_wheel_callbacks_coexist(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEWHEEL,
        )

        logger = logging.getLogger("test_organizer_combined_mouse_callbacks")
        click = Mock(return_value=False)
        wheel = Mock(return_value=True)
        release = Mock(return_value=True)
        hook = MouseHook(
            InputState(), SyntheticInputGuard(logger), logger, click,
            wheel_callback=wheel, release_callback=release,
        )
        mouse = MSLLHOOKSTRUCT()
        mouse.pt.x = 30
        mouse.pt.y = 40
        mouse.mouseData = 120 << 16
        user32 = Mock()
        user32.CallNextHookEx.return_value = 51
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            addr = ctypes.addressof(mouse)
            self.assertEqual(hook._mouse_proc(0, WM_MOUSEWHEEL, addr), 1)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 51)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 51)
        wheel.assert_called_once_with(120, 30, 40, False)
        click.assert_called_once_with("Left", 30, 40)
        release.assert_called_once_with("Left", 30, 40)
        self.assertEqual(hook._consumed_releases, set())



    def test_mouse_and_wheel_blocked_warnings_have_independent_throttle(self):
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MouseHook, WM_LBUTTONDOWN, WM_MOUSEWHEEL, WM_RBUTTONDOWN,
        )

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                logger = Mock()
                state = InputState()
                state.begin_mouse_block("Miroir")
                hook = MouseHook(state, SyntheticInputGuard(logger), logger, Mock())
                with patch("app.input.mouse_hooks.time.monotonic",
                           return_value=1.0):
                    for _ in range(count):
                        hook._log_blocked_event(WM_MOUSEWHEEL, 5, 8)
                    hook._log_blocked_event(WM_LBUTTONDOWN, 5, 8)
                    for _ in range(count):
                        hook._log_blocked_event(WM_RBUTTONDOWN, 5, 8)
                self.assertEqual(hook._blocked_wheel_count, count)
                self.assertEqual(hook._blocked_click_count, count + 1)
                self.assertEqual(logger.warning.call_count, 2)
                logger.warning.assert_any_call(
                    "Molette physique non diffusée (macro occupée=%s): event=%s",
                    "Miroir", "wheel",
                )
                logger.warning.assert_any_call(
                    "Clic physique non diffusé (macro occupée=%s): event=%s",
                    "Miroir", "left_down",
                )
                # Neither click nor wheel warning is allowed to hide the
                # other category; both counters remain exhaustive.
                with patch("app.input.mouse_hooks.time.monotonic",
                           return_value=1.1):
                    hook._log_blocked_event(WM_MOUSEWHEEL, 5, 8)
                    hook._log_blocked_event(WM_LBUTTONDOWN, 5, 8)
                self.assertEqual(logger.warning.call_count, 2)
                self.assertEqual(hook._blocked_wheel_count, count + 1)
                self.assertEqual(hook._blocked_click_count, count + 2)



if __name__ == "__main__":
    unittest.main()
