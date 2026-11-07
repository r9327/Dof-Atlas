from __future__ import annotations

import re
from time import perf_counter
from typing import TYPE_CHECKING

from app.macros.input_tools import send_chat_command
from app.macros.mirror_plan import is_dofus_unity_process, mirror_latency_percentiles_ms
from app.windows.focus import activate_window
from app.windows.unity_windows import foreground_window, is_unity_window

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime


_ZAAP_COMMAND_RE = re.compile(r"^/zaap\s+(-?\d+)\s*,\s*(-?\d+)$", re.IGNORECASE)


def parse_zaap_command(value: str) -> tuple[int, int] | None:
    match = _ZAAP_COMMAND_RE.fullmatch(str(value or "").strip())
    if match is None:
        return None
    try:
        coords = int(match.group(1)), int(match.group(2))
    except ValueError:
        # Python can refuse huge integer strings; clipboard commands are
        # untrusted text and must never crash the UI event handler.
        return None
    if any(not -(2**31) < value < 2**31 for value in coords):
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
        if parse_zaap_command(command) is None:
            self.runtime.logger.info("Auto zaap refuse: commande /zaap invalide.")
            return False
        profile_at_dispatch = self.runtime.settings
        if profile_at_dispatch is None:
            return False
        dispatch_context = (
            profile_at_dispatch.primary_handle, profile_at_dispatch.macro_mode,
        )
        admitted = self.runtime._spawn_macro(
            "Auto zaap",
            lambda: self._run(
                command, profile_at_dispatch=profile_at_dispatch,
                dispatch_context=dispatch_context,
            ),
        )
        # A profile changed during admission cannot be a confirmed launch.
        # The queued worker will independently cancel before its first send.
        return bool(admitted and not self.runtime.macro_lock.should_stop()
                    and self.runtime.settings is profile_at_dispatch
                    and (profile_at_dispatch.primary_handle,
                         profile_at_dispatch.macro_mode) == dispatch_context)

    def _run(
        self, command: str, *, profile_at_dispatch: object | None = None,
        dispatch_context: tuple[object, object] | None = None,
    ) -> None:
        coords = parse_zaap_command(command)
        if coords is None:
            self.runtime.logger.info("Auto zaap ignore: commande /zaap invalide.")
            self.runtime._emit_status("Auto zaap ignoré : commande invalide.")
            return
        command = zaap_command(*coords)
        settings_at_start = self.runtime.settings
        if (profile_at_dispatch is not None
                and settings_at_start is not profile_at_dispatch):
            self.runtime.logger.info("Auto zaap annulé: profil remplacé avant worker.")
            self.runtime._emit_status("Auto zaap interrompu : profil Organizer modifié.")
            return
        if (dispatch_context is not None and
                (settings_at_start.primary_handle, settings_at_start.macro_mode)
                != dispatch_context):
            self.runtime._emit_status("Auto zaap interrompu : favori ou mode modifié avant worker.")
            return
        favorite_at_start = settings_at_start.primary_handle
        mode_at_start = settings_at_start.macro_mode

        def dispatch_context_changed() -> bool:
            return (
                settings_at_start.primary_handle != favorite_at_start
                or settings_at_start.macro_mode != mode_at_start
            )

        clients = self.runtime.switch_character.ordered_clients_from_source()
        if (self.runtime.settings is not settings_at_start
                or dispatch_context_changed()):
            self.runtime.logger.info(
                "Auto zaap annulé : profil, favori ou mode modifié pendant lecture des sessions."
            )
            self.runtime._emit_status("Auto zaap interrompu : contexte Organizer modifié.")
            return
        if not clients:
            self.runtime.logger.info("Auto zaap ignore: aucune fenetre chargee.")
            self.runtime._emit_status("Auto zaap ignoré : aucune fenêtre DOFUS disponible.")
            return
        # Freeze HWNDs before the native fan-out: Organizer client objects can
        # be modified in place while Win32 yields to the UI thread.
        target_handles = tuple(client.handle for client in clients)
        if (not 1 <= len(target_handles) <= 8
                or any(type(hwnd) is not int or not 0 < hwnd <= (2**64 - 1)
                       for hwnd in target_handles)
                or len(set(target_handles)) != len(target_handles)):
            self.runtime.logger.warning(
                "Auto zaap refusé : liste de clients invalide ou supérieure à huit."
            )
            self.runtime._emit_status(
                "Auto zaap non lancé : clients Organizer invalides."
            )
            return

        def frozen_roster_intact() -> bool:
            return tuple(client.handle for client in clients) == target_handles

        timings = settings_at_start.timings
        self.runtime.logger.info(
            "Auto zaap lance: clients=%s commande=%s",
            len(clients),
            command,
        )
        sent = 0
        focus_lost = False
        last_activated_handle: int | None = None
        action_started_at = perf_counter()
        focus_steps_ms: list[float] = []
        chat_steps_ms: list[float] = []
        try:
            for index, (client, target_hwnd) in enumerate(zip(clients, target_handles)):
                if (self.runtime.macro_lock.should_stop()
                        or self.runtime.settings is not settings_at_start):
                    return
                if dispatch_context_changed():
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto zaap interrompu: favori modifié entre clients."
                    )
                    return
                if (type(target_hwnd) is not int or not 0 < target_hwnd <= (2**64 - 1)
                        or not frozen_roster_intact()):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto zaap interrompu: session remplacée en place hwnd=%r", target_hwnd,
                    )
                    return
                if not is_unity_window(target_hwnd) or not is_dofus_unity_process(target_hwnd):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto zaap interrompu: cible non DOFUS Unity hwnd=%s", target_hwnd,
                    )
                    return
                if not frozen_roster_intact():
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto zaap interrompu: roster muté pendant contrôle natif hwnd=%s",
                        target_hwnd,
                    )
                    return
                focus_started_at = perf_counter()
                try:
                    # Native helper skips only a no-op foreground settle;
                    # it must keep the configured delay when it actually
                    # changes the focused DOFUS client.
                    activated = activate_window(
                        target_hwnd,
                        timings.travel_focus_settle_ms,
                    timings.activate_attempts,
                    timings.activate_retry_ms,
                    self.runtime.logger,
                    "Auto zaap",
                    skip_settle_if_active=(index == 0),
                    should_stop=lambda client=client, hwnd=target_hwnd: (
                        self.runtime.macro_lock.should_stop()
                        or self.runtime.settings is not settings_at_start
                        or not frozen_roster_intact()
                        or dispatch_context_changed()
                    ),
                    )
                except Exception:
                    # A failed native focus operation leaves the foreground
                    # uncertain. Do not send chat or restore the favorite.
                    focus_lost = True
                    self.runtime.logger.exception(
                        "Auto zaap: exception pendant activation hwnd=%s.", target_hwnd,
                    )
                    break
                finally:
                    focus_steps_ms.append(
                        max(0.0, (perf_counter() - focus_started_at) * 1000.0)
                    )
                if not activated:
                    if (self.runtime.macro_lock.should_stop()
                            or self.runtime.settings is not settings_at_start):
                        return
                    if (not frozen_roster_intact()
                            or dispatch_context_changed()):
                        focus_lost = True
                        self.runtime.logger.warning(
                            "Auto zaap interrompu: session ou favori muté pendant activation hwnd=%s",
                            target_hwnd,
                        )
                        return
                    self.runtime.logger.info("Auto zaap activation echec: hwnd=%s", target_hwnd)
                    continue
                # A focus change after activation must not send the chat
                # command to Organizer, another game window, or a browser.
                # Make foreground the last native check. A process probe
                # can yield focus during a multi-window Unity sequence.
                if (self.runtime.settings is not settings_at_start
                        or not is_dofus_unity_process(target_hwnd)
                        or foreground_window() != int(target_hwnd)
                        or not frozen_roster_intact()
                        or dispatch_context_changed()):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto zaap interrompu: focus, identité ou favori perdus avant commande hwnd=%s", target_hwnd
                    )
                    return
                if self.runtime.macro_lock.should_stop():
                    return
                if not frozen_roster_intact():
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto zaap interrompu: session mutée avant chat hwnd=%s", target_hwnd,
                    )
                    return
                last_activated_handle = int(target_hwnd)
                chat_started_at = perf_counter()
                try:
                    accepted = send_chat_command(
                        command,
                    self.runtime.logger,
                    submit_twice=True,
                    chat_open_ms=timings.auto_group_chat_open_ms,
                    key_step_ms=timings.auto_group_key_step_ms,
                    paste_settle_ms=timings.auto_group_paste_settle_ms,
                    # Abort a command at its next cancellable keyboard
                    # boundary when the user switches to another window.
                    # The existing sender checks this before each chat step.
                    should_stop=lambda hwnd=target_hwnd, client=client: (
                        self.runtime.macro_lock.should_stop()
                        or self.runtime.settings is not settings_at_start
                        or not frozen_roster_intact()
                        or dispatch_context_changed()
                        or foreground_window() != int(hwnd)
                    ),
                    )
                except Exception:
                    # Clipboard/keyboard failures leave delivery uncertain:
                    # keep prior emissions but never start a later target.
                    # Restore only through the existing checked cleanup;
                    # chat failure alone does not prove the focus was stolen.
                    self.runtime.logger.exception(
                        "Auto zaap interrompu: commande chat impossible."
                    )
                    break
                finally:
                    chat_steps_ms.append(
                        max(0.0, (perf_counter() - chat_started_at) * 1000.0)
                    )
                if not accepted:
                    if (self.runtime.macro_lock.should_stop()
                            or self.runtime.settings is not settings_at_start):
                        return
                    if (not is_dofus_unity_process(target_hwnd)
                            or foreground_window() != int(target_hwnd)
                            or not frozen_roster_intact()
                            or dispatch_context_changed()):
                        focus_lost = True
                        self.runtime.logger.warning(
                            "Auto zaap interrompu: focus ou identité DOFUS perdus après échec du chat hwnd=%s",
                            target_hwnd,
                        )
                        return
                    # One rejected /zaap leaves its character out of sync.
                    # Do not continue broadcasting to later clients while
                    # the current command was not confirmed emitted.
                    self.runtime.logger.warning(
                        "Auto zaap: commande non émise, arrêt après %s/%s clients.",
                        sent, len(clients),
                    )
                    break
                sent += 1
                if not frozen_roster_intact():
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto zaap interrompu: session mutée après chat hwnd=%s", target_hwnd,
                    )
                    return
                if self.runtime.settings is not settings_at_start:
                    return
        finally:
            # Restituer le favori même si un client ou le chat échoue, mais ne
            # jamais réactiver une fenêtre après un stop d'urgence.
            stopped = self.runtime.macro_lock.should_stop()
            restore_skipped = (
                self.runtime.settings is not settings_at_start
                or not frozen_roster_intact()
                or settings_at_start.macro_mode != mode_at_start
            )
            if restore_skipped:
                self.runtime.logger.info("Auto zaap: retour ignoré, profil remplacé.")
            if (not stopped and not focus_lost and not restore_skipped
                    and not is_dofus_unity_process(target_hwnd)):
                focus_lost = True
                self.runtime.logger.warning(
                    "Auto zaap: identité DOFUS perdue avant restauration hwnd=%s", target_hwnd,
                )
            # Do not reactivate a favorite selected midway through an
            # older macro sequence, even if the foreground did not change.
            if (
                not self.runtime.macro_lock.should_stop() and not focus_lost
                and self.runtime.settings.primary_handle != favorite_at_start
            ):
                restore_skipped = True
                self.runtime.logger.info(
                    "Auto zaap: retour favori ignoré, favori changé."
                )
            # After the final chat submission (or clipboard cleanup),
            # the user may focus a different app. Never force DOFUS back.
            if (
                not self.runtime.macro_lock.should_stop() and not focus_lost
                and not restore_skipped and last_activated_handle is not None
            ):
                try:
                    if foreground_window() != last_activated_handle:
                        restore_skipped = True
                        self.runtime.logger.info(
                            "Auto zaap: retour favori ignoré, focus utilisateur changé."
                        )
                except Exception:
                    restore_skipped = True
                    self.runtime.logger.exception(
                        "Auto zaap: focus illisible avant retour au favori."
                    )
            # Stop may arrive between the identity probe and the restore.
            # Recheck the live lock state instead of using the earlier snapshot.
            if (not self.runtime.macro_lock.should_stop() and not focus_lost
                    and not restore_skipped
                    and self.runtime.settings is settings_at_start
                    and frozen_roster_intact()
                    and not dispatch_context_changed()
                    and last_activated_handle is not None):
                try:
                    self.runtime.switch_character.restore_preferred_client("Auto zaap")
                except Exception:
                    self.runtime.logger.exception("Auto zaap: retour au favori impossible.")
            state = (
                "interrompu" if (self.runtime.macro_lock.should_stop() or focus_lost
                                  or self.runtime.settings is not settings_at_start
                                  or not frozen_roster_intact()
                                  or dispatch_context_changed())
                else "termine" if sent == len(clients)
                else "partiel"
            )
            self.runtime.logger.info(
                "Auto zaap %s: envoyes=%s/%s",
                state,
                sent,
                len(clients),
            )
            self.runtime._emit_status(
                f"Auto zaap {state} : {sent}/{len(clients)} commandes émises "
                "(réception DOFUS non vérifiée)."
            )
            self.runtime.logger.info(
                "Auto zaap mesures: activation=%s/%s p50_p95_p99_ms=%s "
                "chat=%s/%s p50_p95_p99_ms=%s total_ms=%.2f "
                "(envoi, pas rendu Unity)",
                len(focus_steps_ms), len(clients),
                mirror_latency_percentiles_ms(focus_steps_ms) or "NOT_MEASURED",
                len(chat_steps_ms), len(clients),
                mirror_latency_percentiles_ms(chat_steps_ms) or "NOT_MEASURED",
                max(0.0, (perf_counter() - action_started_at) * 1000.0),
            )
