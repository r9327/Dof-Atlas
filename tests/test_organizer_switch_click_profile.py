from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.macros.switch_click import SwitchClickContext, SwitchClickMacro


class SwitchClickProfileAdmissionTests(unittest.TestCase):
    """A bad or changed Organizer roster must not consume a physical click."""

    def _macro(self, count: int):
        handles = tuple(range(101, 101 + count))
        source = handles[-1]  # The explicit favorite need not be first.
        settings = SimpleNamespace(
            macro_mode="mirror",
            primary_handle=source,
            clients=tuple(SimpleNamespace(handle=hwnd) for hwnd in handles),
        )
        runtime = Mock()
        runtime.settings = settings
        runtime.macro_lock.should_stop.return_value = False
        return SwitchClickMacro(runtime), handles, source

    def _dispatch(self, macro, handles, source):
        return macro.run_async(
            "Left", 10, 20, 1, "Miroir",
            exact_source_handle=source,
            mirror_target_handles=(source, *(h for h in handles if h != source)),
        )

    def test_missing_profile_preserves_physical_click(self):
        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                macro, handles, source = self._macro(count)
                macro.runtime.settings = None
                with patch.object(macro, "_capture_trigger_context") as capture:
                    self.assertFalse(self._dispatch(macro, handles, source))
                capture.assert_not_called()
                macro.runtime._spawn_macro.assert_not_called()

    def test_missing_client_handle_before_capture_preserves_click(self):
        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                macro, handles, source = self._macro(count)
                clients = macro.runtime.settings.clients
                macro.runtime.settings.clients = (object(), *clients[1:])
                with patch.object(macro, "_capture_trigger_context") as capture:
                    self.assertFalse(self._dispatch(macro, handles, source))
                capture.assert_not_called()
                macro.runtime._spawn_macro.assert_not_called()

    def test_client_detached_during_capture_preserves_click(self):
        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                macro, handles, source = self._macro(count)
                context = SwitchClickContext(
                    source_hwnd=source, client_x=5, client_y=10,
                    x_ratio=0.5, y_ratio=0.5, reason="cursor",
                )

                def detach(*_args):
                    clients = macro.runtime.settings.clients
                    macro.runtime.settings.clients = (object(), *clients[1:])
                    return context

                with patch.object(
                    macro, "_capture_trigger_context", side_effect=detach,
                ):
                    self.assertFalse(self._dispatch(macro, handles, source))
                macro.runtime._spawn_macro.assert_not_called()

    def test_mode_removed_during_capture_preserves_click(self):
        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                macro, handles, source = self._macro(count)
                context = SwitchClickContext(
                    source_hwnd=source, client_x=5, client_y=10,
                    x_ratio=0.5, y_ratio=0.5, reason="cursor",
                )

                def detach_mode(*_args):
                    del macro.runtime.settings.macro_mode
                    return context

                with patch.object(
                    macro, "_capture_trigger_context", side_effect=detach_mode,
                ):
                    self.assertFalse(self._dispatch(macro, handles, source))
                macro.runtime._spawn_macro.assert_not_called()


if __name__ == "__main__":
    unittest.main()
