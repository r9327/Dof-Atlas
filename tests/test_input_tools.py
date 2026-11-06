"""Direct owner tests for emergency keyboard and mouse releases."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from app.input.hotkeys import VK_CONTROL, VK_MENU, VK_SHIFT
from app.macros import input_tools
from app.windows import clicks


class CommonReleaseOwnerTests(unittest.TestCase):
    def test_stop_attempts_every_release_when_sendinput_and_logs_fail_2_to_8(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                logger = Mock()
                logger.warning.side_effect = RuntimeError("broken warning sink")
                logger.exception.side_effect = RuntimeError("broken exception sink")
                with (
                    patch.object(input_tools.os, "name", "nt"),
                    patch("logging.getLogger", return_value=logger),
                    patch.object(clicks, "_send_mouse_flag",
                                 side_effect=[False, OSError("middle refused"),
                                              OSError("right refused")]) as mouse,
                    patch.object(input_tools, "key_up",
                                 side_effect=OSError("key refused")) as keys,
                ):
                    input_tools.release_common_inputs()
                self.assertEqual(mouse.call_args_list, [
                    call(0x0004), call(0x0010), call(0x0040),
                ])
                self.assertEqual(keys.call_args_list, [
                    call(VK_SHIFT), call(VK_CONTROL), call(VK_MENU),
                ])
                self.assertEqual(logger.warning.call_count, 1)
                self.assertEqual(logger.exception.call_count, 5)

    def test_non_windows_stop_never_attempts_mouse_sendinput_2_to_8(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                with (
                    patch.object(input_tools.os, "name", "posix"),
                    patch.object(clicks, "_send_mouse_flag") as mouse,
                    patch.object(input_tools, "key_up") as keys,
                ):
                    input_tools.release_common_inputs()
                mouse.assert_not_called()
                self.assertEqual(keys.call_args_list, [
                    call(VK_SHIFT), call(VK_CONTROL), call(VK_MENU),
                ])


if __name__ == "__main__":
    unittest.main()
