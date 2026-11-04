from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.text import clean_auto_group_name, normalize_key
from app.macros.input_tools import send_chat_command
from app.macros.mirror_plan import is_dofus_unity_process
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
        if (sender is None or not is_unity_window(sender.handle)
                or not is_dofus_unity_process(sender.handle)):
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
        favorite_at_start = self.runtime.settings.primary_handle
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
                except (TypeError, ValueError, OverflowError):
                    # Corrupt/stale Organizer entries must never abort a group.
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
                # A native identity probe may yield focus to another app.
                # Check the foreground last, then Stop before opening chat.
                if (not is_dofus_unity_process(sender.handle)
                        or foreground_window() != int(sender.handle)):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto groupe interrompu: focus ou identité DOFUS perdus avant invitation hwnd=%s",
                        sender.handle,
                    )
                    return
                if self.runtime.macro_lock.should_stop():
                    return
                if not send_chat_command(
                    f"/invite {name}",
                    self.runtime.logger,
                    chat_open_ms=timings.auto_group_chat_open_ms,
                    key_step_ms=timings.auto_group_key_step_ms,
                    paste_settle_ms=timings.auto_group_paste_settle_ms,
                    # send_chat_command rechecks this predicate between
                    # every chat key. Stop if focus moves mid-paste instead
                    # of typing Ctrl+A/Delete/Enter into another program.
                    should_stop=lambda: (
                        self.runtime.macro_lock.should_stop()
                        or foreground_window() != int(sender.handle)
                    ),
                ):
                    if self.runtime.macro_lock.should_stop():
                        return
                    if (not is_dofus_unity_process(sender.handle)
                            or foreground_window() != int(sender.handle)):
                        focus_lost = True
                        self.runtime.logger.warning(
                            "Auto groupe interrompu: focus ou identité DOFUS perdus après échec du chat hwnd=%s",
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
            restore_skipped = False
            if not stopped and not focus_lost and not is_dofus_unity_process(sender.handle):
                focus_lost = True
                self.runtime.logger.warning(
                    "Auto groupe: identité DOFUS perdue avant restauration hwnd=%s", sender.handle,
                )
            # The favorite may change via Organizer while the worker is
            # running. Never activate a newly selected favorite on cleanup.
            if (
                not self.runtime.macro_lock.should_stop() and not focus_lost
                and self.runtime.settings.primary_handle != favorite_at_start
            ):
                restore_skipped = True
                self.runtime.logger.info(
                    "Auto groupe: retour favori ignoré, favori changé."
                )
            # The user may focus another application AFTER the last
            # invitation, or while clipboard restoration is finishing.
            # A completed SendInput is not permission to steal focus back.
            if (not self.runtime.macro_lock.should_stop() and not focus_lost
                    and not restore_skipped and eligible):
                try:
                    if foreground_window() != int(sender.handle):
                        restore_skipped = True
                        self.runtime.logger.info(
                            "Auto groupe: retour favori ignoré, focus utilisateur changé."
                        )
                except Exception:
                    restore_skipped = True
                    self.runtime.logger.exception(
                        "Auto groupe: focus illisible avant retour au favori."
                    )
            # Stop may be requested while identity is being checked.
            # Never restore focus on a stale snapshot of the stop flag.
            if (not self.runtime.macro_lock.should_stop() and not focus_lost
                    and not restore_skipped):
                try:
                    self.runtime.switch_character.restore_preferred_client("Auto groupe")
                except Exception:
                    self.runtime.logger.exception(
                        "Auto groupe: retour au favori impossible."
                    )
            stopped = self.runtime.macro_lock.should_stop()
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
