from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING, Any

from app.core.text import clean_auto_group_name, normalize_key
from app.macros.input_tools import send_chat_command
from app.macros.mirror_plan import is_dofus_unity_process, mirror_latency_percentiles_ms
from app.windows.focus import activate_window
from app.windows.unity_windows import foreground_window, is_unity_window

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime


def _client_handle_snapshot(settings: object) -> tuple[tuple[type, object], ...] | None:
    clients = getattr(settings, "clients", None)
    if not isinstance(clients, (list, tuple)):
        return None
    # Keep strict Python types: 101.0 and True must not alias Win32 HWND 101.
    snapshot = []
    for client in clients:
        hwnd = getattr(client, "handle", None)
        snapshot.append((type(hwnd), hwnd))
    return tuple(snapshot)


class AutoGroupMacro:
    def __init__(self, runtime: "AtlasRuntime"):
        self.runtime = runtime

    def run_async(self, invite_entries: list[dict[str, object]]) -> bool:
        # A scanner may report eight valid windows PLUS duplicate/empty
        # rows, so raw item count is not the participant count. Bound the
        # untrusted raw payload, then reject more than eight distinct names
        # before ever reserving a worker. The worker removes the sender and
        # checks its final recipient count against the same total capacity.
        if not isinstance(invite_entries, (list, tuple)) or len(invite_entries) > 32:
            self.runtime.logger.warning(
                "Auto groupe refusé: liste invalide ou scanner trop volumineux."
            )
            return False
        entries = [dict(entry) for entry in invite_entries if isinstance(entry, dict)]
        names = {
            normalize_key(clean_auto_group_name(entry.get("name", "")))
            for entry in entries
        }
        names.discard("")
        if not names:
            self.runtime.logger.info(
                "Auto groupe non lancé : aucun nom de personnage adressable."
            )
            return False
        if len(names) > 8:
            self.runtime.logger.warning(
                "Auto groupe refusé: plus de huit participants distincts."
            )
            return False
        if not entries:
            self.runtime.logger.info("Auto groupe non lancé : aucune session candidate.")
            return False
        profile_at_dispatch = self.runtime.settings
        if profile_at_dispatch is None:
            return False
        roster_at_dispatch = _client_handle_snapshot(profile_at_dispatch)
        if roster_at_dispatch is not None and (
                not 1 <= len(roster_at_dispatch) <= 8
                or any(kind is not int or not 0 < hwnd <= (2**64 - 1)
                       for kind, hwnd in roster_at_dispatch)
                or len({hwnd for _, hwnd in roster_at_dispatch}) != len(roster_at_dispatch)):
            self.runtime.logger.warning(
                "Auto groupe refusé: roster Organizer invalide avant dispatch."
            )
            return False
        dispatch_context = (
            profile_at_dispatch.primary_handle, profile_at_dispatch.macro_mode,
        )
        admitted = self.runtime._spawn_macro(
            "Auto groupe",
            lambda: self._run(
                entries, profile_at_dispatch=profile_at_dispatch,
                dispatch_context=dispatch_context,
                roster_at_dispatch=roster_at_dispatch,
            ),
        )
        # Admission may yield to an Organizer reload. The worker already
        # refuses stale generations; the UI must not report false acceptance.
        return bool(admitted and not self.runtime.macro_lock.should_stop()
                    and self.runtime.settings is profile_at_dispatch
                    and (profile_at_dispatch.primary_handle,
                         profile_at_dispatch.macro_mode) == dispatch_context
                    and (roster_at_dispatch is None
                         or _client_handle_snapshot(profile_at_dispatch)
                         == roster_at_dispatch))

    def _run(
        self, invite_entries: list[dict[str, Any]],
        *, profile_at_dispatch: object | None = None,
        dispatch_context: tuple[object, object] | None = None,
        roster_at_dispatch: tuple[tuple[type, object], ...] | None = None,
    ) -> None:
        # _run is also used directly by integrations/tests. Keep malformed
        # scanner payloads bounded, but count distinct valid participants
        # AFTER sender/dedup filtering instead of truncating raw rows.
        if not isinstance(invite_entries, (list, tuple)) or len(invite_entries) > 32:
            self.runtime.logger.warning(
                "Auto groupe refusé: liste invalide ou scanner trop volumineux."
            )
            self.runtime._emit_status(
                "Auto-groupe non lancé : liste invalide ou trop volumineuse."
            )
            return
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
        if (dispatch_context is not None and
                (settings_at_start.primary_handle, settings_at_start.macro_mode)
                != dispatch_context):
            self.runtime._emit_status("Auto-groupe interrompu : favori ou mode modifié avant worker.")
            return
        if (roster_at_dispatch is not None
                and _client_handle_snapshot(settings_at_start) != roster_at_dispatch):
            self.runtime._emit_status(
                "Auto-groupe interrompu : sessions Organizer modifiées avant worker."
            )
            return
        favorite_at_start = settings_at_start.primary_handle
        mode_at_start = settings_at_start.macro_mode
        # Freeze the native roster once. Organizer can mutate client.handle
        # in place without replacing settings or changing the favorite.
        initial_roster = (
            roster_at_dispatch if roster_at_dispatch is not None
            else _client_handle_snapshot(settings_at_start)
        )

        def dispatch_context_changed() -> bool:
            roster_changed = (
                initial_roster is not None
                and _client_handle_snapshot(settings_at_start) != initial_roster
            )
            return (
                settings_at_start.primary_handle != favorite_at_start
                or settings_at_start.macro_mode != mode_at_start
                or roster_changed
            )
        sender = self.runtime.switch_character.logical_active_client()
        # Capture the exact source HWND before native probes or recipient
        # preparation; the client object may be edited in place by Organizer.
        sender_hwnd = sender.handle if sender is not None else 0
        if (self.runtime.settings is not settings_at_start
                or dispatch_context_changed()):
            self.runtime.logger.info(
                "Auto groupe annulé: profil, favori ou mode changé pendant lecture source."
            )
            self.runtime._emit_status("Auto-groupe interrompu : contexte Organizer modifié.")
            return
        if (sender is None or type(sender_hwnd) is not int
                or not 0 < sender_hwnd <= (2**64 - 1)
                or not is_unity_window(sender_hwnd)
                or not is_dofus_unity_process(sender_hwnd)
                or sender.handle != sender_hwnd):
            self.runtime.logger.info("Auto groupe ignore: aucune fenetre Dofus valide.")
            self.runtime._emit_status("Auto-groupe ignoré : fenêtre DOFUS introuvable.")
            return

        sender_name = clean_auto_group_name(sender.display_name)
        sender_key = normalize_key(sender_name)
        recipients: list[str] = []
        seen_recipients: set[str] = set()
        seen_recipient_hwnds: dict[int, str] = {}
        ambiguous_windows = 0
        excluded_sender = 0
        excluded_duplicate = 0
        excluded_empty = 0
        for entry in invite_entries:
            if not isinstance(entry, dict):
                excluded_empty += 1
                continue
            name = clean_auto_group_name(entry.get("name", ""))
            key = normalize_key(name)
            # Match Organizer's own invite-name eligibility. A nonempty
            # punctuation-only label is not a DOFUS character to invite.
            if not name or not key:
                excluded_empty += 1
                continue
            # Organizer HWNDs are integers (legacy decimal strings are
            # accepted). Never truncate 101.9 to 101 and accidentally discard
            # a different named invitee as if it were the sender.
            raw_handle = entry.get("handle", 0)
            handle = 0
            if type(raw_handle) is int:
                candidate = raw_handle
            elif (type(raw_handle) is str and raw_handle.isascii()
                  and raw_handle.strip().isdecimal()):
                try:
                    candidate = int(raw_handle.strip())
                except ValueError:
                    candidate = 0
            else:
                candidate = 0
            if 0 < candidate <= (2**64 - 1):
                handle = candidate
            if (handle > 0 and handle == sender_hwnd) or key == sender_key:
                excluded_sender += 1
                continue
            if key in seen_recipients:
                excluded_duplicate += 1
                continue
            # Two different names from the same real HWND are not two
            # independent DOFUS accounts. Fail closed instead of silently
            # inviting one or both from an ambiguous scanner roster.
            if handle > 0 and handle in seen_recipient_hwnds:
                ambiguous_windows += 1
                continue
            if handle > 0:
                seen_recipient_hwnds[handle] = key
            seen_recipients.add(key)
            recipients.append(name)

        self.runtime.logger.info(
            "Auto groupe préparé: invitations=%s doublons=%s lanceur=%s vides=%s",
            len(recipients), excluded_duplicate, excluded_sender, excluded_empty,
        )
        if ambiguous_windows:
            self.runtime.logger.warning(
                "Auto groupe refusé: %s fenêtre(s) associée(s) à plusieurs noms.",
                ambiguous_windows,
            )
            self.runtime._emit_status(
                "Auto-groupe non lancé : fenêtre(s) ambiguë(s), actualiser Organizer."
            )
            return
        if len(recipients) > 7:
            # The source is the eighth possible account. Never send a
            # ninth participant's invite, even when raw input had only
            # eight rows and omitted the active sender.
            self.runtime.logger.warning(
                "Auto groupe refusé: trop de destinataires (source comprise)."
            )
            self.runtime._emit_status(
                "Auto-groupe non lancé : plus de huit comptes source comprise."
            )
            return
        if not recipients:
            # A one-client roster must not steal focus just to do nothing.
            self.runtime.logger.info(
                "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
                "ignore", 0, 0, len(invite_entries), sender_hwnd,
            )
            self.runtime._emit_status("Auto-groupe ignoré : aucun autre personnage à inviter.")
            return

        if self.runtime.macro_lock.should_stop():
            self.runtime._emit_status("Auto-groupe arrêté avant envoi.")
            return
        timings = settings_at_start.timings
        if (self.runtime.settings is not settings_at_start
                or sender.handle != sender_hwnd
                or dispatch_context_changed()):
            self.runtime._emit_status("Auto-groupe interrompu : session ou favori modifié.")
            return
        try:
            activated = activate_window(
                sender_hwnd,
                timings.travel_focus_settle_ms,
                timings.activate_attempts,
                timings.activate_retry_ms,
                self.runtime.logger,
                "Auto groupe",
                should_stop=lambda: (
                    self.runtime.macro_lock.should_stop()
                    or self.runtime.settings is not settings_at_start
                    or sender.handle != sender_hwnd
                    or dispatch_context_changed()
                ),
            )
        except Exception:
            # A native activation exception makes the target foreground
            # unverifiable. Never attempt an invitation in this state.
            self.runtime.logger.exception(
                "Auto groupe: erreur activation native hwnd=%s.", sender_hwnd,
            )
            self.runtime._emit_status(
                "Auto-groupe non envoyé : activation DOFUS impossible."
            )
            return
        if not activated:
            if (self.runtime.macro_lock.should_stop()
                    or self.runtime.settings is not settings_at_start
                    or sender.handle != sender_hwnd
                    or dispatch_context_changed()):
                self.runtime.logger.info(
                    "Auto groupe interrompu: session ou favori changé pendant activation."
                )
                self.runtime._emit_status(
                    "Auto-groupe interrompu : session ou favori modifié."
                )
                return
            self.runtime.logger.info("Auto groupe activation fenetre echec: hwnd=%s", sender_hwnd)
            self.runtime._emit_status("Auto-groupe non envoyé : activation DOFUS échouée.")
            return
        sent = 0
        eligible = 0
        focus_lost = False
        action_started_at = perf_counter()
        chat_steps_ms: list[float] = []
        try:
            for index, name in enumerate(recipients):
                if (self.runtime.macro_lock.should_stop()
                        or self.runtime.settings is not settings_at_start):
                    return
                if dispatch_context_changed():
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto groupe interrompu: favori modifié entre invitations."
                    )
                    return
                eligible += 1
                # Every invitation is a distinct operation. Never type into
                # another window if focus was stolen after activation.
                # A native identity probe may yield focus to another app.
                # Check the foreground last, then Stop before opening chat.
                if (self.runtime.settings is not settings_at_start
                        or not is_dofus_unity_process(sender_hwnd)
                        or foreground_window() != int(sender_hwnd)
                        or sender.handle != sender_hwnd
                        or dispatch_context_changed()):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto groupe interrompu: focus ou identité DOFUS perdus avant invitation hwnd=%s",
                        sender_hwnd,
                    )
                    return
                if self.runtime.macro_lock.should_stop():
                    return
                chat_started_at = perf_counter()
                try:
                    accepted = send_chat_command(
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
                        or sender.handle != sender_hwnd
                        or dispatch_context_changed()
                        or foreground_window() != int(sender_hwnd)
                    ),
                    )
                finally:
                    chat_steps_ms.append(
                        max(0.0, (perf_counter() - chat_started_at) * 1000.0)
                    )
                if not accepted:
                    if (self.runtime.macro_lock.should_stop()
                            or self.runtime.settings is not settings_at_start):
                        return
                    if (not is_dofus_unity_process(sender_hwnd)
                            or foreground_window() != int(sender_hwnd)
                            or sender.handle != sender_hwnd
                            or dispatch_context_changed()):
                        focus_lost = True
                        self.runtime.logger.warning(
                            "Auto groupe interrompu: focus ou identité DOFUS perdus après échec du chat hwnd=%s",
                            sender_hwnd,
                        )
                        return
                    continue
                # The command returned successful: retain this emission
                # in telemetry even when Stop arrives immediately afterward.
                sent += 1
                if sender.handle != sender_hwnd:
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto groupe interrompu: session mutée après invitation hwnd=%s",
                        sender_hwnd,
                    )
                    return
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
            restore_skipped = (
                self.runtime.settings is not settings_at_start
                or sender.handle != sender_hwnd
                or settings_at_start.macro_mode != mode_at_start
                or dispatch_context_changed()
            )
            if restore_skipped:
                self.runtime.logger.info("Auto groupe: retour ignoré, profil remplacé.")
            if (not stopped and not focus_lost and not restore_skipped
                    and not is_dofus_unity_process(sender_hwnd)):
                focus_lost = True
                self.runtime.logger.warning(
                    "Auto groupe: identité DOFUS perdue avant restauration hwnd=%s", sender_hwnd,
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
                    if foreground_window() != int(sender_hwnd):
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
                    and self.runtime.settings is settings_at_start
                    and sender.handle == sender_hwnd
                    and not dispatch_context_changed()):
                try:
                    self.runtime.switch_character.restore_preferred_client("Auto groupe")
                except Exception:
                    self.runtime.logger.exception(
                        "Auto groupe: retour au favori impossible."
                    )
            stopped = self.runtime.macro_lock.should_stop()
            state = (
                "interrompu" if (stopped or focus_lost
                                  or self.runtime.settings is not settings_at_start
                                  or sender.handle != sender_hwnd
                                  or dispatch_context_changed())
                else "ignore" if not eligible
                else "termine" if sent == eligible
                else "partiel"
            )
            self.runtime.logger.info(
                "Auto groupe %s: envoyes=%s/%s candidats=%s sender=%s",
                state, sent, eligible, len(invite_entries), sender_hwnd,
            )
            self.runtime._emit_status(
                f"Auto-groupe {state} : {sent}/{len(recipients)} commandes émises "
                "(réception DOFUS non vérifiée)."
            )
            # Per-invitation durations include only the actual chat sender,
            # not the inter-invite pacing. A successful SendInput is still
            # not evidence that DOFUS accepted an invite.
            quantiles = mirror_latency_percentiles_ms(chat_steps_ms)
            self.runtime.logger.info(
                "Auto groupe mesures: etapes=%s/%s p50_p95_p99_ms=%s "
                "total_ms=%.2f (envoi, pas reception Unity)",
                len(chat_steps_ms), len(recipients),
                quantiles if quantiles is not None else "NOT_MEASURED",
                max(0.0, (perf_counter() - action_started_at) * 1000.0),
            )
