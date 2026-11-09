"""Windows focus probe failures must never leak /zaap input across DOFUS clients."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.macros.zaap import ZaapMacro


class OrganizerZaapFocusFailureTests(unittest.TestCase):
    def test_focus_probe_failure_or_recovery_never_sends_to_later_clients(self) -> None:
        # Validate pre-send, mid-command, and rejected-chat focus probes.
        # A transient focus theft must remain latched even if focus returns.
        for count in (2, 4, 6, 8):
            for stage in ("before_chat", "during_chat", "after_refusal", "focus_returns"):
                with self.subTest(clients=count, stage=stage):
                    runtime = Mock()
                    runtime.settings.primary_handle = 101
                    runtime.settings.macro_mode = "macro"
                    runtime.macro_lock.should_stop.return_value = False
                    runtime.switch_character.ordered_clients_from_source.return_value = [
                        SimpleNamespace(handle=101 + i) for i in range(count)
                    ]
                    reads = [0]

                    def foreground() -> int:
                        reads[0] += 1
                        if stage == "before_chat" or (
                            stage in ("during_chat", "after_refusal")
                            and reads[0] >= 2
                        ):
                            raise OSError("GetForegroundWindow failed")
                        if stage == "focus_returns" and reads[0] == 2:
                            return 999
                        return 101

                    def chat(_command, _logger, **kwargs) -> bool:
                        if stage in ("during_chat", "focus_returns"):
                            self.assertTrue(kwargs["should_stop"]())
                        return False

                    with (
                        patch("app.macros.zaap.is_unity_window", return_value=True),
                        patch("app.macros.zaap.is_dofus_unity_process", return_value=True),
                        patch("app.macros.zaap.activate_window", return_value=True) as activate,
                        patch("app.macros.zaap.foreground_window", side_effect=foreground),
                        patch("app.macros.zaap.send_chat_command", side_effect=chat) as send,
                    ):
                        ZaapMacro(runtime)._run("/zaap 1,2")

                    activate.assert_called_once()
                    self.assertEqual(send.call_count, 0 if stage == "before_chat" else 1)
                    runtime.switch_character.restore_preferred_client.assert_not_called()
                    runtime._emit_status.assert_called_once_with(
                        f"Auto zaap interrompu : 0/{count} commandes émises "
                        "(réception DOFUS non vérifiée)."
                    )
                    if stage == "focus_returns":
                        self.assertEqual(reads[0], 3)
                    if stage in ("before_chat", "during_chat", "after_refusal"):
                        runtime.logger.exception.assert_any_call(
                            "Auto zaap interrompu: focus Windows illisible hwnd=%s.", 101,
                        )


if __name__ == "__main__":
    unittest.main()
