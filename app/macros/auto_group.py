from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.text import clean_auto_group_name, normalize_key
from app.macros.input_tools import send_chat_command
from app.windows.focus import activate_window
from app.windows.unity_windows import foreground_window, is_unity_window

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
        eligible = 0
        seen_recipients: set[str] = set()
        focus_lost = False
        try:
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
                recipient_key = normalize_key(name)
                if recipient_key == sender_key:
                    self.runtime.logger.debug("Auto groupe ignore lanceur: %s sender=%s", name, sender.handle)
                    continue
                # Duplicated session rows must never send repeated invitations.
                if recipient_key in seen_recipients:
                    self.runtime.logger.debug("Auto groupe ignore doublon: %s", name)
                    continue
                seen_recipients.add(recipient_key)
                eligible += 1
                # Every invitation is a distinct operation. Never type into
                # another window if focus was stolen after activation.
                if foreground_window() != int(sender.handle):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto groupe interrompu: focus perdu avant invitation hwnd=%s",
                        sender.handle,
                    )
                    return
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
                    if foreground_window() != int(sender.handle):
                        focus_lost = True
                        self.runtime.logger.warning(
                            "Auto groupe interrompu: focus perdu après échec du chat hwnd=%s",
                            sender.handle,
                        )
                        return
                    continue
                # The command returned successful: retain this emission
                # in telemetry even when Stop arrives immediately afterward.
                sent += 1
                if self.runtime.macro_lock.should_stop():
                    return
                if timings.auto_group_invite_gap_ms > 0:
                    if self.runtime.macro_lock.wait(timings.auto_group_invite_gap_ms):
                        return
        finally:
            stopped = self.runtime.macro_lock.should_stop()
            if not stopped and not focus_lost:
                try:
                    self.runtime.switch_character.restore_preferred_client("Auto groupe")
                except Exception:
                    self.runtime.logger.exception(
                        "Auto groupe: retour au favori impossible."
                    )
            state = (
                "interrompu" if stopped or focus_lost
                else "ignore" if not eligible
                else "termine" if sent == eligible
                else "partiel"
            )
            self.runtime.logger.info(
                "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
                state, sent, eligible, len(invite_entries), sender.handle,
            )
