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


    def test_single_client_native_noop_never_reads_roster_again(self):
        class ReloadingProfile:
            macro_mode = "macro"
            primary_handle = 101

            def __init__(self):
                self.reads = 0

            @property
            def clients(self):
                self.reads += 1
                if self.reads <= 2:
                    return (SimpleNamespace(handle=101),)
                return (object(),)  # Reload after the accepted snapshot.

        runtime = Mock()
        runtime.settings = ReloadingProfile()
        runtime.macro_lock.should_stop.return_value = False
        macro = SwitchClickMacro(runtime)
        context = SwitchClickContext(
            source_hwnd=101, client_x=5, client_y=10,
            x_ratio=0.5, y_ratio=0.5, reason="cursor",
        )
        self.assertTrue(macro.run_async(
            "Left", 10, 20, 1, "Switch clique",
            captured_context=context, physical_source_delivered=True,
        ))
        # The old implementation read a third roster, which could throw or
        # introduce a different window into a physically delivered click.
        self.assertEqual(runtime.settings.reads, 2)
        runtime._spawn_macro.assert_not_called()


    def test_invalid_mode_before_capture_preserves_click(self):
        for count in (2, 4, 6, 8):
            for mode in (None, "unknown", 123, "deleted"):
                with self.subTest(accounts=count, mode=mode):
                    macro, handles, source = self._macro(count)
                    if mode == "deleted":
                        del macro.runtime.settings.macro_mode
                    else:
                        macro.runtime.settings.macro_mode = mode
                    with patch.object(macro, "_capture_trigger_context") as capture:
                        self.assertFalse(self._dispatch(macro, handles, source))
                    capture.assert_not_called()
                    macro.runtime._spawn_macro.assert_not_called()


    def test_worker_rejects_invalid_targets_before_any_injection(self):
        for count in (2, 4, 6, 8):
            for invalid in (None, object(), [object()]):
                with self.subTest(accounts=count, invalid_type=type(invalid).__name__):
                    macro, handles, source = self._macro(count)
                    context = SwitchClickContext(
                        source, 5, 10, 0.5, 0.5, "cursor",
                    )
                    macro.runtime.switch_character.ordered_clients_from_source.return_value = invalid
                    with (
                        patch("app.macros.switch_click.foreground_window",
                              return_value=source),
                        patch("app.macros.switch_click.current_cursor_pos",
                              return_value=(25, 30)),
                        patch.object(macro, "_validated_context",
                                     return_value=context),
                        patch("app.macros.switch_click.activate_window") as activate,
                        patch("app.macros.switch_click.send_client_click") as sender,
                        patch("app.macros.switch_click.set_cursor_pos") as restore,
                    ):
                        macro._run(
                            "Left", 1, "Miroir", context,
                            exact_source_handle=source,
                            mirror_target_handles=(source, *(h for h in handles if h != source)),
                            settings_at_dispatch=macro.runtime.settings,
                        )
                    activate.assert_not_called()
                    sender.assert_not_called()
                    restore.assert_not_called()

    def test_worker_refuses_roster_detached_during_target_resolution(self):
        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                macro, handles, source = self._macro(count)
                context = SwitchClickContext(source, 5, 10, 0.5, 0.5, "cursor")

                def detach(_source):
                    previous_clients = macro.runtime.settings.clients
                    macro.runtime.settings.clients = None
                    return list(previous_clients)

                macro.runtime.switch_character.ordered_clients_from_source.side_effect = detach
                with (
                    patch("app.macros.switch_click.foreground_window",
                          return_value=source),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(25, 30)),
                    patch.object(macro, "_validated_context",
                                 return_value=context),
                    patch("app.macros.switch_click.activate_window") as activate,
                    patch("app.macros.switch_click.send_client_click") as sender,
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=source,
                        mirror_target_handles=(source, *(h for h in handles if h != source)),
                        settings_at_dispatch=macro.runtime.settings,
                    )
                activate.assert_not_called()
                sender.assert_not_called()

    def test_worker_refuses_roster_detached_during_mirror_recheck(self):
        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                macro, handles, source = self._macro(count)
                stable_clients = macro.runtime.settings.clients

                class FlippingProfile:
                    macro_mode = "mirror"
                    primary_handle = source

                    def __init__(self):
                        self.reads = 0

                    @property
                    def clients(self):
                        self.reads += 1
                        return stable_clients if self.reads <= 2 else None

                profile = FlippingProfile()
                macro.runtime.settings = profile
                macro.runtime.switch_character.ordered_clients_from_source.return_value = list(stable_clients)
                context = SwitchClickContext(source, 5, 10, 0.5, 0.5, "cursor")
                with (
                    patch("app.macros.switch_click.foreground_window",
                          return_value=source),
                    patch("app.macros.switch_click.current_cursor_pos",
                          return_value=(25, 30)),
                    patch.object(macro, "_validated_context",
                                 return_value=context),
                    patch("app.macros.switch_click.activate_window") as activate,
                    patch("app.macros.switch_click.send_client_click") as sender,
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=source,
                        mirror_target_handles=(source, *(h for h in handles if h != source)),
                        settings_at_dispatch=profile,
                    )
                self.assertGreaterEqual(profile.reads, 3)
                activate.assert_not_called()
                sender.assert_not_called()


    def test_raising_client_property_never_crashes_or_blocks_worker(self):
        class DetachedClient:
            @property
            def handle(self):
                raise RuntimeError("Organizer record disposed")

        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                macro, handles, source = self._macro(count)
                settings = macro.runtime.settings
                settings.clients = (DetachedClient(), *settings.clients[1:])
                context = SwitchClickContext(source, 5, 10, 0.5, 0.5, "cursor")
                with (
                    patch("app.macros.switch_click.current_cursor_pos") as cursor,
                    patch("app.macros.switch_click.activate_window") as activate,
                    patch("app.macros.switch_click.send_client_click") as sender,
                    patch("app.macros.switch_click.set_cursor_pos") as restore,
                ):
                    macro._run(
                        "Left", 1, "Miroir", context,
                        exact_source_handle=source,
                        mirror_target_handles=(source, *(h for h in handles if h != source)),
                        settings_at_dispatch=settings,
                    )
                cursor.assert_not_called()
                activate.assert_not_called()
                sender.assert_not_called()
                restore.assert_not_called()
                macro.runtime.input_state.begin_mouse_block.assert_not_called()


if __name__ == "__main__":
    unittest.main()
