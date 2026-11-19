from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.macros.travel import TravelMacro


class GuideTravelPreflightTests(unittest.TestCase):
    @staticmethod
    def _macro(*clients):
        runtime = SimpleNamespace(
            settings=SimpleNamespace(clients=list(clients)),
            logger=Mock(),
            _emit_status=Mock(),
            _spawn_macro=Mock(return_value=True),
        )
        return TravelMacro(runtime), runtime

    def test_offline_team_is_refused_before_spawning(self):
        macro, runtime = self._macro()
        self.assertFalse(macro.run_async("/travel 3,-6", ("character:1",)))
        runtime._spawn_macro.assert_not_called()
        runtime._emit_status.assert_called_once()
        self.assertIn("hors ligne", runtime._emit_status.call_args.args[0])

    def test_selected_connected_character_can_launch(self):
        client = SimpleNamespace(handle=123, character_key="character:1")
        macro, runtime = self._macro(client)
        self.assertTrue(macro.run_async("/travel 3,-6", ("character:1",)))
        runtime._spawn_macro.assert_called_once()

    def test_invalid_command_never_reports_accepted_request(self):
        client = SimpleNamespace(handle=123, character_key="character:1")
        macro, runtime = self._macro(client)
        self.assertFalse(macro.run_async("/travel position inconnue", ("character:1",)))
        runtime._spawn_macro.assert_not_called()


if __name__ == "__main__":
    unittest.main()
