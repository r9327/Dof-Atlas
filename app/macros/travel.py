from __future__ import annotations

from typing import TYPE_CHECKING

from app.macros.input_tools import send_chat_command
from app.windows.focus import activate_window
from app.windows.unity_windows import is_unity_window

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime


class TravelMacro:
    def __init__(self, runtime: "AtlasRuntime"):
        self.runtime = runtime

    def run_async(self, text: str) -> bool:
        command = str(text or "").strip()
        return self.runtime._spawn_macro("Travel", lambda: self._run(command))

    def _run(self, command: str) -> None:
        if not command:
            self.runtime.logger.info("Travel ignore: texte vide.")
            return
        clients = self.runtime.switch_character.ordered_clients_from_source()
        if not clients:
            self.runtime.logger.info("Travel ignore: aucune fenetre chargee.")
            return
        timings = self.runtime.settings.timings
        sent = 0
        for client in clients:
            if self.runtime.macro_lock.should_stop():
                return
            if not is_unity_window(client.handle):
                self.runtime.logger.info("Travel fenetre introuvable/non Unity: hwnd=%s", client.handle)
                continue
            if activate_window(
                client.handle,
                timings.travel_focus_settle_ms,
                timings.activate_attempts,
                timings.activate_retry_ms,
                self.runtime.logger,
                "Travel",
                should_stop=self.runtime.macro_lock.should_stop,
            ):
                if not send_chat_command(
                    command,
                    self.runtime.logger,
                    submit_twice=True,
                    chat_open_ms=timings.auto_group_chat_open_ms,
                    key_step_ms=timings.auto_group_key_step_ms,
                    paste_settle_ms=timings.auto_group_paste_settle_ms,
                    should_stop=self.runtime.macro_lock.should_stop,
                ):
                    if self.runtime.macro_lock.should_stop():
                        return
                    continue
                sent += 1
        self.runtime.switch_character.restore_preferred_client("Travel")
        self.runtime.logger.info("Travel termine: envoyes=%s/%s", sent, len(clients))
