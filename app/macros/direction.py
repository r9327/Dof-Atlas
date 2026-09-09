from __future__ import annotations

from typing import TYPE_CHECKING

from app.macros.input_tools import _vk, key_up, press_key
from app.windows.focus import activate_window
from app.windows.unity_windows import foreground_window, is_unity_window

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime


class DirectionMacro:
    def __init__(self, runtime: "AtlasRuntime"):
        self.runtime = runtime

    def run_async(self, key_name: str) -> bool:
        return self.runtime._spawn_macro("Switch deplacement", lambda: self._run(key_name))

    def _run(self, key_name: str) -> None:
        source = foreground_window()
        if not source or not is_unity_window(source) or self.runtime.settings.client_by_handle(source) is None:
            self.runtime.logger.info("Switch deplacement ignore: fenetre active non Unity.")
            self.release_virtual_inputs()
            return
        timings = self.runtime.settings.timings
        for client in self.runtime.switch_character.ordered_clients_from_source(source):
            if self.runtime.macro_lock.should_stop():
                return
            if not is_unity_window(client.handle):
                self.runtime.logger.info("Switch deplacement fenetre introuvable/non Unity: hwnd=%s", client.handle)
                continue
            if activate_window(
                client.handle,
                timings.click_focus_settle_ms,
                timings.activate_attempts,
                timings.activate_retry_ms,
                self.runtime.logger,
                "Switch deplacement",
                should_stop=self.runtime.macro_lock.should_stop,
            ):
                press_key(key_name, timings.movement_key_hold_ms)
                if self.runtime.macro_lock.should_stop():
                    return
        self.runtime.switch_character.restore_preferred_client("Switch deplacement")

    def release_virtual_inputs(self) -> None:
        for key_name in ("HOME", "DELETE", "END", "PAGEDOWN"):
            try:
                key_up(_vk(key_name))
            except Exception:
                pass
