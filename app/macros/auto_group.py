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
        if not entries:
            self.runtime.logger.info("Auto groupe non lancé : aucune session candidate.")
            return False
        profile_at_dispatch = self.runtime.settings
        return self.runtime._spawn_macro(
            "Auto groupe",
            lambda: self._run(
                entries, profile_at_dispatch=profile_at_dispatch,
            ),
        )

    def _run(
        self, invite_entries: list[dict[str, Any]],
        *, profile_at_dispatch: object | None = None,
    ) -> None:
        if not invite_entries:
            self.runtime.logger.info("Auto groupe ignore: aucune invitation.")
            self.runtime._emit_status("Auto-groupe ignoré : aucun destinataire.")
            return
        if self.runtime.macro_lock.should_stop():
            self.runtime.logger.info("Auto groupe ignoré : Stop déjà demandé.")
            self.runtime._emit_status("Auto-groupe arrêté avant lancement.")
            return
        settings_at_start = self.runtime.settings
        if (profile_at_dispatch is not None
                and settings_at_start is not profile_at_dispatch):
            self.runtime.logger.info("Auto groupe annulé: profil remplacé avant worker.")
            self.runtime._emit_status("Auto-groupe interrompu : profil Organizer modifié.")
            return
        sender = self.runtime.switch_character.logical_active_client()
        if self.runtime.settings is not settings_at_start:
            self.runtime.logger.info("Auto groupe annulé: profil Organizer remplacé.")
            self.runtime._emit_status("Auto-groupe interrompu : profil modifié.")
            return
        if (sender is None or not is_unity_window(sender.handle)
                or not is_dofus_unity_process(sender.handle)):
            self.runtime.logger.info("Auto groupe ignore: aucune fenetre Dofus valide.")
            self.runtime._emit_status("Auto-groupe ignoré : fenêtre DOFUS introuvable.")
            return

        sender_name = clean_auto_group_name(sender.display_name)
        sender_key = normalize_key(sender_name)
        recipients: list[str] = []
        seen_recipients: set[str] = set()
        excluded_sender = 0
        excluded_duplicate = 0
        excluded_empty = 0
        for entry in invite_entries:
            if not isinstance(entry, dict):
                excluded_empty += 1
                continue
            name = clean_auto_group_name(entry.get("name", ""))
            if not name:
                excluded_empty += 1
                continue
            try:
                raw_handle = entry.get("handle", 0)
                handle = int(raw_handle or 0)
            except (TypeError, ValueError, OverflowError):
                # A corrupt Organizer HWND must not drop an otherwise
                # valid named recipient. Names, not HWNDs, identify /invite.
                handle = 0
            key = normalize_key(name)
            if (handle > 0 and handle == sender.handle) or key == sender_key:
                excluded_sender += 1
                continue
            if key in seen_recipients:
                excluded_duplicate += 1
                continue
            seen_recipients.add(key)
            recipients.append(name)

        self.runtime.logger.info(
            "Auto groupe préparé: invitations=%s doublons=%s lanceur=%s vides=%s",
            len(recipients), excluded_duplicate, excluded_sender, excluded_empty,
        )
        if not recipients:
            # A one-client roster must not steal focus just to do nothing.
            self.runtime.logger.info(
                "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
                "ignore", 0, 0, len(invite_entries), sender.handle,
            )
            self.runtime._emit_status("Auto-groupe ignoré : aucun autre personnage à inviter.")
            return

        if self.runtime.macro_lock.should_stop():
            self.runtime._emit_status("Auto-groupe arrêté avant envoi.")
            return
        timings = settings_at_start.timings
        if self.runtime.settings is not settings_at_start:
            self.runtime._emit_status("Auto-groupe interrompu : profil modifié.")
            return
        if not activate_window(
            sender.handle,
            timings.travel_focus_settle_ms,
            timings.activate_attempts,
            timings.activate_retry_ms,
            self.runtime.logger,
            "Auto groupe",
            should_stop=lambda: (
                self.runtime.macro_lock.should_stop()
                or self.runtime.settings is not settings_at_start
            ),
        ):
            self.runtime.logger.info("Auto groupe activation fenetre echec: hwnd=%s", sender.handle)
            self.runtime._emit_status("Auto-groupe non envoyé : activation DOFUS échouée.")
            return
        favorite_at_start = settings_at_start.primary_handle
        sent = 0
        eligible = 0
        focus_lost = False
        try:
            for index, name in enumerate(recipients):
                if (self.runtime.macro_lock.should_stop()
                        or self.runtime.settings is not settings_at_start):
                    return
                eligible += 1
                # Every invitation is a distinct operation. Never type into
                # another window if focus was stolen after activation.
                # A native identity probe may yield focus to another app.
                # Check the foreground last, then Stop before opening chat.
                if (self.runtime.settings is not settings_at_start
                        or not is_dofus_unity_process(sender.handle)
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
                        or self.runtime.settings is not settings_at_start
                        or foreground_window() != int(sender.handle)
                    ),
                ):
                    if (self.runtime.macro_lock.should_stop()
                            or self.runtime.settings is not settings_at_start):
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
                if (self.runtime.macro_lock.should_stop()
                        or self.runtime.settings is not settings_at_start):
                    return
                # There is no next /invite after the last recipient. Do
                # not make two accounts feel slower for no functional reason.
                if index + 1 < len(recipients) and timings.auto_group_invite_gap_ms > 0:
                    if self.runtime.macro_lock.wait(timings.auto_group_invite_gap_ms):
                        return
        finally:
            stopped = self.runtime.macro_lock.should_stop()
            restore_skipped = self.runtime.settings is not settings_at_start
            if restore_skipped:
                self.runtime.logger.info("Auto groupe: retour ignoré, profil remplacé.")
            if (not stopped and not focus_lost and not restore_skipped
                    and not is_dofus_unity_process(sender.handle)):
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
                    and not restore_skipped
                    and self.runtime.settings is settings_at_start):
                try:
                    self.runtime.switch_character.restore_preferred_client("Auto groupe")
                except Exception:
                    self.runtime.logger.exception(
                        "Auto groupe: retour au favori impossible."
                    )
            stopped = self.runtime.macro_lock.should_stop()
            state = (
                "interrompu" if stopped or focus_lost or self.runtime.settings is not settings_at_start
                else "ignore" if not eligible
                else "termine" if sent == eligible
                else "partiel"
            )
            self.runtime.logger.info(
                "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
                state, sent, eligible, len(invite_entries), sender.handle,
            )
            self.runtime._emit_status(
                f"Auto-groupe {state} : {sent}/{len(recipients)} commandes émises "
                "(réception DOFUS non vérifiée)."
            )
