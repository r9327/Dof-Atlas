from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.text import clean_auto_group_name, normalize_key
from app.macros.input_tools import send_chat_command
from app.windows.focus import activate_window
from app.windows.unity_windows import is_unity_window

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime


class AutoGroupMacro:
    def __init__(self, runtime: "AtlasRuntime"):
        self.runtime = runtime

    def run_async(self, invite_entries: list[dict[str, object]]) -> bool:
        entries = [dict(entry) for entry in invite_entries if isinstance(entry, dict)]
        return self.runtime._spawn_macro("Auto groupe", lambda: self._run(entries))

    def _run(self, invite_entries: list[dict[str, Any]]) -> None:
        if not invite_entries:
            self.runtime.logger.info("Auto groupe ignore: aucune invitation.")
            return
        sender = self.runtime.switch_character.logical_active_client()
        if sender is None or not is_unity_window(sender.handle):
            self.runtime.logger.info("Auto groupe ignore: aucune fenetre Dofus valide.")
            return
        timings = self.runtime.settings.timings
        if not activate_window(
            sender.handle,
            timings.travel_focus_settle_ms,
            timings.activate_attempts,
            timings.activate_retry_ms,
            self.runtime.logger,
            "Auto groupe",
            should_stop=self.runtime.macro_lock.should_stop,
        ):
            self.runtime.logger.info("Auto groupe activation fenetre echec: hwnd=%s", sender.handle)
            return
        sender_name = clean_auto_group_name(sender.display_name)
        sender_key = normalize_key(sender_name)
        sent = 0
        for entry in invite_entries:
            if self.runtime.macro_lock.should_stop():
                return
            name = clean_auto_group_name(entry.get("name", ""))
            if not name:
                continue
            try:
                handle = int(entry.get("handle", 0) or 0)
            except (TypeError, ValueError):
                handle = 0
            if handle > 0 and handle == sender.handle:
                self.runtime.logger.debug("Auto groupe ignore lanceur: %s sender=%s", name, sender.handle)
                continue
            if normalize_key(name) == sender_key:
                self.runtime.logger.debug("Auto groupe ignore lanceur: %s sender=%s", name, sender.handle)
                continue
            if not send_chat_command(
                f"/invite {name}",
                self.runtime.logger,
                chat_open_ms=timings.auto_group_chat_open_ms,
                key_step_ms=timings.auto_group_key_step_ms,
                paste_settle_ms=timings.auto_group_paste_settle_ms,
                should_stop=self.runtime.macro_lock.should_stop,
            ):
                if self.runtime.macro_lock.should_stop():
                    return
                continue
            if self.runtime.macro_lock.should_stop():
                return
            sent += 1
            if timings.auto_group_invite_gap_ms > 0:
                if self.runtime.macro_lock.wait(timings.auto_group_invite_gap_ms):
                    return
        self.runtime.switch_character.restore_preferred_client("Auto groupe")
        self.runtime.logger.info("Auto groupe termine: envoyes=%s/%s sender=%s", sent, len(invite_entries), sender.handle)
