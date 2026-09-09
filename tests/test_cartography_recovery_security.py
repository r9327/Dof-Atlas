from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from app.services.maps.cartography_asset_recovery import run_recovery_commands


class CartographyRecoverySecurityTests(unittest.TestCase):
    @patch("app.services.maps.cartography_asset_recovery.subprocess.run")
    def test_doduda_commands_never_use_shell(self, mocked_run) -> None:
        mocked_run.return_value = subprocess.CompletedProcess(
            args=["C:/safe/doduda.exe", "map"],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        code, output = run_recovery_commands(
            "C:/safe/doduda.exe",
            [[], ["map"]],
        )

        self.assertEqual(0, code)
        self.assertIn("ok", output)
        self.assertEqual(2, mocked_run.call_count)
        first_call = mocked_run.call_args_list[0]
        second_call = mocked_run.call_args_list[1]
        self.assertEqual(["C:/safe/doduda.exe"], first_call.args[0])
        self.assertEqual(["C:/safe/doduda.exe", "map"], second_call.args[0])
        self.assertFalse(first_call.kwargs["shell"])
        self.assertFalse(second_call.kwargs["shell"])

    @patch("app.services.maps.cartography_asset_recovery.subprocess.run")
    def test_shell_operator_is_rejected_before_execution(self, mocked_run) -> None:
        code, output = run_recovery_commands(
            "C:/safe/doduda.exe",
            [["map", "&&", "cmd.exe"]],
        )

        self.assertNotEqual(0, code)
        self.assertIn("operateur shell interdit", output)
        mocked_run.assert_not_called()

    @patch("app.services.maps.cartography_asset_recovery.subprocess.run")
    def test_config_cannot_replace_resolved_executable(self, mocked_run) -> None:
        mocked_run.return_value = subprocess.CompletedProcess(
            args=["C:/safe/doduda.exe", "cmd.exe"],
            returncode=0,
            stdout="",
            stderr="",
        )

        code, _output = run_recovery_commands(
            "C:/safe/doduda.exe",
            [["cmd.exe", "/c", "echo", "hello"]],
        )

        self.assertEqual(0, code)
        self.assertEqual(
            ["C:/safe/doduda.exe", "cmd.exe", "/c", "echo", "hello"],
            mocked_run.call_args.args[0],
        )
        self.assertFalse(mocked_run.call_args.kwargs["shell"])


if __name__ == "__main__":
    unittest.main()
