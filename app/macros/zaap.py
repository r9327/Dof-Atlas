from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.macros.input_tools import send_chat_command
from app.windows.focus import activate_window
from app.windows.unity_windows import is_unity_window

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime


_ZAAP_COMMAND_RE = re.compile(r"^/zaap\s+(-?\d+)\s*,\s*(-?\d+)$", re.IGNORECASE)


def parse_zaap_command(value: str) -> tuple[int, int] | None:
    match = _ZAAP_COMMAND_RE.fullmatch(str(value or "").strip())
    if match is None:
        return None
    coords = int(match.group(1)), int(match.group(2))
    if -(2**31) in coords:
        return None
    return coords


def zaap_command(x: int, y: int) -> str:
    return f"/zaap {int(x)},{int(y)}"


class ZaapMacro:
    def __init__(self, runtime: "AtlasRuntime"):
        self.runtime = runtime

    def run_async(self, text: str, click_position=None, click_ratios=None) -> bool:
        del click_position, click_ratios  # Legacy callback compatibility only.
        command = str(text or "").replace("\r", " ").replace("\n", " ").strip()
        return self.runtime._spawn_macro("Auto zaap", lambda: self._run(command))

    def _run(self, command: str) -> None:
        coords = parse_zaap_command(command)
        if coords is None:
            self.runtime.logger.info("Auto zaap ignore: commande /zaap invalide.")
            return
        command = zaap_command(*coords)
        clients = self.runtime.switch_character.ordered_clients_from_source()
        if not clients:
            self.runtime.logger.info("Auto zaap ignore: aucune fenetre chargee.")
            return
        timings = self.runtime.settings.timings
        self.runtime.logger.info(
            "Auto zaap lance: clients=%s commande=%s",
            len(clients),
            command,
        )
        sent = 0
        for client in clients:
            if self.runtime.macro_lock.should_stop():
                return
            if not is_unity_window(client.handle):
                self.runtime.logger.info("Auto zaap fenetre introuvable/non Unity: hwnd=%s", client.handle)
                continue
            if not activate_window(
                client.handle,
                timings.travel_focus_settle_ms,
                timings.activate_attempts,
                timings.activate_retry_ms,
                self.runtime.logger,
                "Auto zaap",
                should_stop=self.runtime.macro_lock.should_stop,
            ):
                self.runtime.logger.info("Auto zaap activation echec: hwnd=%s", client.handle)
                continue
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
        self.runtime.switch_character.restore_preferred_client("Auto zaap")
        self.runtime.logger.info("Auto zaap termine: envoyes=%s/%s", sent, len(clients))
