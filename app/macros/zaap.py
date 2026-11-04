from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.macros.input_tools import send_chat_command
from app.macros.mirror_plan import is_dofus_unity_process
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
        favorite_at_start = self.runtime.settings.primary_handle
        self.runtime.logger.info(
            "Auto zaap lance: clients=%s commande=%s",
            len(clients),
            command,
        )
        sent = 0
        focus_lost = False
        last_activated_handle: int | None = None
        try:
            for client in clients:
                if self.runtime.macro_lock.should_stop():
                    return
                if not is_unity_window(client.handle) or not is_dofus_unity_process(client.handle):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto zaap interrompu: cible non DOFUS Unity hwnd=%s", client.handle,
                    )
                    return
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
                # A focus change after activation must not send the chat
                # command to Organizer, another game window, or a browser.
                # Make foreground the last native check. A process probe
                # can yield focus during a multi-window Unity sequence.
                if (not is_dofus_unity_process(client.handle)
                        or foreground_window() != int(client.handle)):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Auto zaap interrompu: focus ou identité DOFUS perdus avant commande hwnd=%s", client.handle
                    )
                    return
                if self.runtime.macro_lock.should_stop():
                    return
                last_activated_handle = int(client.handle)
                if not send_chat_command(
                    command,
                    self.runtime.logger,
                    submit_twice=True,
                    chat_open_ms=timings.auto_group_chat_open_ms,
                    key_step_ms=timings.auto_group_key_step_ms,
                    paste_settle_ms=timings.auto_group_paste_settle_ms,
                    # Abort a command at its next cancellable keyboard
                    # boundary when the user switches to another window.
                    # The existing sender checks this before each chat step.
                    should_stop=lambda hwnd=client.handle: (
                        self.runtime.macro_lock.should_stop()
                        or foreground_window() != int(hwnd)
                    ),
                ):
                    if self.runtime.macro_lock.should_stop():
                        return
                    if (not is_dofus_unity_process(client.handle)
                            or foreground_window() != int(client.handle)):
                        focus_lost = True
                        self.runtime.logger.warning(
                            "Auto zaap interrompu: focus ou identité DOFUS perdus après échec du chat hwnd=%s",
                            client.handle,
                        )
                        return
                    continue
                sent += 1
        finally:
            # Restituer le favori même si un client ou le chat échoue, mais ne
            # jamais réactiver une fenêtre après un stop d'urgence.
            stopped = self.runtime.macro_lock.should_stop()
            if not stopped and not focus_lost and not is_dofus_unity_process(client.handle):
                focus_lost = True
                self.runtime.logger.warning(
                    "Auto zaap: identité DOFUS perdue avant restauration hwnd=%s", client.handle,
                )
            # Do not reactivate a favorite selected midway through an
            # older macro sequence, even if the foreground did not change.
            if (
                not self.runtime.macro_lock.should_stop() and not focus_lost
                and self.runtime.settings.primary_handle != favorite_at_start
            ):
                focus_lost = True
                self.runtime.logger.info(
                    "Auto zaap: retour favori ignoré, favori changé."
                )
            # After the final chat submission (or clipboard cleanup),
            # the user may focus a different app. Never force DOFUS back.
            if (
                not self.runtime.macro_lock.should_stop() and not focus_lost
                and last_activated_handle is not None
            ):
                try:
                    if foreground_window() != last_activated_handle:
                        focus_lost = True
                        self.runtime.logger.info(
                            "Auto zaap: retour favori ignoré, focus utilisateur changé."
                        )
                except Exception:
                    focus_lost = True
                    self.runtime.logger.exception(
                        "Auto zaap: focus illisible avant retour au favori."
                    )
            # Stop may arrive between the identity probe and the restore.
            # Recheck the live lock state instead of using the earlier snapshot.
            if not self.runtime.macro_lock.should_stop() and not focus_lost:
                try:
                    self.runtime.switch_character.restore_preferred_client("Auto zaap")
                except Exception:
                    self.runtime.logger.exception("Auto zaap: retour au favori impossible.")
            state = (
                "interrompu" if self.runtime.macro_lock.should_stop() or focus_lost
                else "termine" if sent == len(clients)
                else "partiel"
            )
            self.runtime.logger.info(
                "Auto zaap %s: envoyes=%s/%s",
                state,
                sent,
                len(clients),
            )
