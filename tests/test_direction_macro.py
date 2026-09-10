from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch

from app.macros.direction import DirectionMacro


class DirectionMacroTests(unittest.TestCase):
    def test_release_virtual_inputs_logs_failure_and_continues_releasing(self) -> None:
        runtime = Mock()
        macro = DirectionMacro(runtime)
        release_error = RuntimeError("release failed")

        with (
            patch("app.macros.direction._vk", side_effect=lambda key_name: key_name),
            patch(
                "app.macros.direction.key_up",
                side_effect=(release_error, None, None, None),
            ) as key_up,
        ):
            macro.release_virtual_inputs()

        self.assertEqual(
            key_up.call_args_list,
            [call("HOME"), call("DELETE"), call("END"), call("PAGEDOWN")],
        )
        runtime.logger.warning.assert_called_once_with(
            "Relachement touche virtuelle impossible: key=%s error=%s",
            "HOME",
            release_error,
        )


if __name__ == "__main__":
    unittest.main()
