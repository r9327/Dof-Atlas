"""Direct owner tests for DirectionMacro emergency key releases."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from app.macros.direction import DirectionMacro


class DirectionReleaseOwnerTests(unittest.TestCase):
    def test_all_virtual_keys_get_release_attempt_after_failed_logger_2_to_8(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                runtime = Mock()
                runtime.logger.warning.side_effect = RuntimeError("broken sink")
                macro = DirectionMacro(runtime)
                mapping = {
                    "HOME": 36, "DELETE": 46, "END": 35, "PAGEDOWN": 34,
                }
                with (
                    patch("app.macros.direction._vk",
                          side_effect=lambda key: mapping[key]),
                    patch("app.macros.direction.key_up",
                          side_effect=OSError("SendInput refused")) as release,
                ):
                    result = macro.release_virtual_inputs()
                self.assertIs(result, False)
                self.assertEqual(release.call_args_list, [
                    call(36), call(46), call(35), call(34),
                ])
                self.assertEqual(runtime.logger.warning.call_count, 4)

    def test_successful_emergency_release_has_no_warning_2_to_8(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                runtime = Mock()
                macro = DirectionMacro(runtime)
                with (
                    patch("app.macros.direction._vk",
                          side_effect=lambda name: len(name)),
                    patch("app.macros.direction.key_up") as release,
                ):
                    result = macro.release_virtual_inputs()
                self.assertIs(result, True)
                self.assertEqual(release.call_count, 4)
                runtime.logger.warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
