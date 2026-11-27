from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.character_identity import is_character_key
from app.core.map_coordinates import normalize_guide_travel_command
from app.macros.input_tools import send_chat_command
from app.macros.mirror_plan import is_dofus_unity_process
from app.windows.focus import activate_window
from app.windows.unity_windows import foreground_window, is_unity_window

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime
    from app.core.settings import AtlasClient


class TravelMacro:
    def __init__(self, runtime: "AtlasRuntime"):
        self.runtime = runtime

    def run_async(self, text: str, character_keys=None) -> bool:
        command = normalize_guide_travel_command(text)
        if command is None:
            self.runtime._emit_status("Déplacement ignoré : commande invalide.")
            return False
        targets = None if character_keys is None else tuple(
            dict.fromkeys(str(key or "").strip() for key in character_keys if str(key or "").strip())
        )
        if targets is not None:
            eligible = self._targeted_clients(targets)
            if eligible is None:
                # Guide can fall back to copying /travel immediately.
                return False
            clients, _offline = eligible
            if not any(
                is_unity_window(client.handle)
                and is_dofus_unity_process(client.handle)
                for client in clients
            ):
                # A Unity window may belong to another game. Give Guide an
                # immediate refusal for a copyable /travel fallback instead
                # of accepting a worker that will never send to DOFUS.
                self.runtime._emit_status(
                    "Déplacement ignoré : aucune fenêtre DOFUS utilisable.",
                )
                return False
        # Freeze the entire window/character roster at the user's click,
        # before the async worker can be delayed by other macro operations.
        settings_at_dispatch = self.runtime.settings
        dispatch_roster = tuple(
            (client.character_key, client.handle)
            for client in settings_at_dispatch.clients
        )
        dispatch_mode = getattr(settings_at_dispatch, "macro_mode", None)
        dispatch_preferred = getattr(settings_at_dispatch, "primary_handle", None)
        return self.runtime._spawn_macro(
            "Travel",
            lambda: self._run(
                command, targets,
                settings_at_dispatch=settings_at_dispatch,
                dispatch_roster=dispatch_roster,
                dispatch_mode=dispatch_mode,
                dispatch_preferred=dispatch_preferred,
            ),
        )

    def _targeted_clients(
        self,
        character_keys: tuple[str, ...],
    ) -> tuple[list["AtlasClient"], int] | None:
        if not character_keys:
            self.runtime.logger.info("Travel guide ignore: aucun participant selectionne.")
            self.runtime._emit_status("Déplacement ignoré : aucun participant sélectionné.")
            return None
        if any(not is_character_key(key) for key in character_keys):
            self.runtime.logger.warning("Travel guide ignore: identite participant invalide.")
            self.runtime._emit_status("Déplacement ignoré : identité de participant invalide.")
            return None
        buckets: dict[str, list["AtlasClient"]] = {key: [] for key in character_keys}
        for client in self.runtime.settings.clients:
            if client.character_key in buckets:
                buckets[client.character_key].append(client)
        if any(len(rows) > 1 for rows in buckets.values()):
            self.runtime.logger.warning("Travel guide ignore: identite ambigue dans les fenetres Unity.")
            self.runtime._emit_status("Déplacement ignoré : identité de participant ambiguë.")
            return None
        clients = [buckets[key][0] for key in character_keys if len(buckets[key]) == 1]
        # One HWND must not impersonate two verified characters, including
        # when the other character is not in this Guide's selection.
        identities_by_handle: dict[int, set[str]] = {}
        for client in self.runtime.settings.clients:
            identities_by_handle.setdefault(client.handle, set()).add(client.character_key)
        if any(
            type(client.handle) is not int or client.handle <= 0
            or len(identities_by_handle[client.handle]) != 1
            for client in clients
        ):
            self.runtime.logger.warning("Travel guide ignore: fenetre associee a plusieurs identites.")
            self.runtime._emit_status("Déplacement ignoré : identité de fenêtre ambiguë.")
            return None
        offline = sum(1 for key in character_keys if not buckets[key])
        if not clients:
            self.runtime.logger.info("Travel guide ignore: tous les participants sont hors ligne.")
            self.runtime._emit_status("Déplacement ignoré : tous les participants sont hors ligne.")
            return None
        return clients, offline

    def _run(
        self, command: str, character_keys: tuple[str, ...] | None = None,
        *, settings_at_dispatch=None,
        dispatch_roster: tuple[tuple[str, int], ...] | None = None,
        dispatch_mode=None,
        dispatch_preferred=None,
    ) -> None:
        command = normalize_guide_travel_command(command)
        if command is None:
            self.runtime.logger.info("Travel ignore: commande invalide.")
            if character_keys is not None:
                self.runtime._emit_status("Déplacement ignoré : commande invalide.")
            return
        settings = self.runtime.settings
        if settings_at_dispatch is not None and settings is not settings_at_dispatch:
            self.runtime._emit_status("Déplacement annulé : profils Organizer modifiés.")
            return
        # Freeze all session identities, not only the selected targets. A
        # mutable client list or a mode switch during an async macro must not
        # silently redirect the remaining keyboard events.
        roster = tuple(
            (client.character_key, client.handle) for client in settings.clients
        )
        selected_mode = getattr(settings, "macro_mode", None)
        preferred_hwnd = getattr(settings, "primary_handle", None)
        if settings_at_dispatch is not None and dispatch_roster is not None and (
            roster != dispatch_roster
            or selected_mode != dispatch_mode
            or preferred_hwnd != dispatch_preferred
        ):
            self.runtime._emit_status(
                "Déplacement annulé : personnages ou mode modifiés avant lancement.",
            )
            return

        def context_changed() -> bool:
            return (
                self.runtime.settings is not settings
                or tuple(
                    (client.character_key, client.handle)
                    for client in settings.clients
                ) != roster
                or getattr(settings, "macro_mode", None) != selected_mode
                or getattr(settings, "primary_handle", None) != preferred_hwnd
            )

        offline = 0
        if character_keys is None:
            clients = self.runtime.switch_character.ordered_clients_from_source()
        else:
            targeted = self._targeted_clients(character_keys)
            if targeted is None:
                return
            clients, offline = targeted
        if not clients:
            self.runtime.logger.info("Travel ignore: aucune fenetre chargee.")
            return
        # The game accepts individual chat commands, never shell syntax.
        # Freeze HWNDs so an in-place client mutation cannot retarget input.
        steps = tuple(part.strip() for part in command.split(" ; "))
        target_handles = tuple(client.handle for client in clients)
        if (
            not 1 <= len(target_handles) <= 8
            or any(type(hwnd) is not int or not 0 < hwnd <= 2**64 - 1
                   for hwnd in target_handles)
            or len(set(target_handles)) != len(target_handles)
        ):
            self.runtime._emit_status("Déplacement annulé : fenêtres DOFUS ambiguës.")
            return
        timings = settings.timings
        sent = 0
        focus_lost = False
        last_hwnd: int | None = None

        def interrupted(hwnd: int) -> bool:
            nonlocal focus_lost
            if self.runtime.macro_lock.should_stop() or context_changed():
                return True
            # A successful activation is not proof that the user's foreground
            # stayed on the same Dofus.exe window through SPACE/CTRL+V/ENTER.
            try:
                focused = foreground_window() == hwnd
                valid = is_unity_window(hwnd) and is_dofus_unity_process(hwnd)
            except Exception:
                focused = valid = False
            if not focused or not valid:
                focus_lost = True
                return True
            return False

        try:
            for hwnd in target_handles:
                if self.runtime.macro_lock.should_stop() or context_changed():
                    return
                if last_hwnd is not None and interrupted(last_hwnd):
                    self.runtime.logger.info(
                        "Travel interrompu : focus perdu entre personnages.",
                    )
                    return
                if not is_unity_window(hwnd) or not is_dofus_unity_process(hwnd):
                    self.runtime.logger.info(
                        "Travel annulé : cible non DOFUS Unity hwnd=%s", hwnd,
                    )
                    focus_lost = True
                    return
                try:
                    activated = activate_window(
                        hwnd,
                        timings.travel_focus_settle_ms,
                        timings.activate_attempts,
                        timings.activate_retry_ms,
                        self.runtime.logger,
                        "Travel",
                        should_stop=lambda: (
                            self.runtime.macro_lock.should_stop()
                            or context_changed()
                        ),
                    )
                except Exception:
                    self.runtime.logger.exception(
                        "Travel interrompu : activation Windows impossible.",
                    )
                    focus_lost = True
                    return
                if not activated or interrupted(hwnd):
                    focus_lost = True
                    return
                last_hwnd = hwnd
                for step in steps:
                    if interrupted(hwnd):
                        return
                    try:
                        accepted = send_chat_command(
                            step,
                            self.runtime.logger,
                            submit_twice=True,
                            chat_open_ms=timings.auto_group_chat_open_ms,
                            key_step_ms=timings.auto_group_key_step_ms,
                            paste_settle_ms=timings.auto_group_paste_settle_ms,
                            should_stop=lambda hwnd=hwnd: interrupted(hwnd),
                        )
                    except Exception:
                        self.runtime.logger.exception(
                            "Travel interrompu : commande chat impossible.",
                        )
                        return
                    if not accepted or interrupted(hwnd):
                        # Never broadcast /travel to the remaining characters
                        # after one uncertain or interrupted chat submission.
                        return
                sent += 1
        finally:
            # A physical focus change is user intent: don't bring DOFUS back
            # over another application or a freshly selected Unity window.
            if (
                last_hwnd is not None
                and not focus_lost
                and not self.runtime.macro_lock.should_stop()
                and not context_changed()
                and not interrupted(last_hwnd)
            ):
                try:
                    self.runtime.switch_character.restore_preferred_client("Travel")
                except Exception:
                    self.runtime.logger.exception(
                        "Travel : restauration du personnage favori impossible.",
                    )
            self.runtime.logger.info(
                "Travel terminé : émissions %s/%s", sent, len(target_handles),
            )
            if character_keys is not None:
                suffix = f", {offline} hors ligne" if offline else ""
                self.runtime._emit_status(
                    f"Déplacement : {sent}/{len(target_handles)} commande(s) "
                    f"émise(s){suffix} (réception DOFUS non vérifiée).",
                )
