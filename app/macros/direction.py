from __future__ import annotations

from typing import TYPE_CHECKING

from app.macros.input_tools import _vk, key_up, press_key
from app.macros.mirror_plan import is_dofus_unity_process
from app.windows.focus import activate_window
from app.windows.unity_windows import foreground_window, is_unity_window

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime


class DirectionMacro:
    def __init__(self, runtime: "AtlasRuntime"):
        self.runtime = runtime

    def run_async(
        self, key_name: str, *, expected_profile: object | None = None,
    ) -> bool:
        profile_at_dispatch = self.runtime.settings
        if (expected_profile is not None
                and profile_at_dispatch is not expected_profile):
            self.runtime.logger.info(
                "Switch deplacement annulé: profil Organizer remplacé avant dispatch.",
            )
            return False
        dispatch_context = (
            profile_at_dispatch.primary_handle, profile_at_dispatch.macro_mode,
        )
        admitted = self.runtime._spawn_macro(
            "Switch deplacement",
            lambda: self._run(
                key_name, profile_at_dispatch=profile_at_dispatch,
                dispatch_context=dispatch_context,
            ),
        )
        # A hotkey dispatched under an obsolete profile is not accepted just
        # because a worker was queued. The worker also checks before input.
        return bool(admitted and not self.runtime.macro_lock.should_stop()
                    and self.runtime.settings is profile_at_dispatch
                    and (profile_at_dispatch.primary_handle,
                         profile_at_dispatch.macro_mode) == dispatch_context)

    def _run(
        self, key_name: str, *, profile_at_dispatch: object | None = None,
        dispatch_context: tuple[object, object] | None = None,
    ) -> None:
        settings_at_start = self.runtime.settings
        if (profile_at_dispatch is not None
                and settings_at_start is not profile_at_dispatch):
            self.runtime.logger.info(
                "Switch deplacement annulé: profil Organizer remplacé avant worker.",
            )
            return
        if (dispatch_context is not None and
                (settings_at_start.primary_handle, settings_at_start.macro_mode)
                != dispatch_context):
            self.runtime.logger.info(
                "Switch deplacement annulé: favori ou mode modifié avant worker."
            )
            return
        favorite_at_start = settings_at_start.primary_handle
        mode_at_start = settings_at_start.macro_mode

        def dispatch_context_changed() -> bool:
            return (
                settings_at_start.primary_handle != favorite_at_start
                or settings_at_start.macro_mode != mode_at_start
            )

        source = foreground_window()
        if (not source or not is_unity_window(source)
                or not is_dofus_unity_process(source)
                or settings_at_start.client_by_handle(source) is None
                or self.runtime.settings is not settings_at_start
                or dispatch_context_changed()):
            # No synthetic DOWN was issued by this worker. Sending four
            # orphaned KEYUP events to the currently focused foreign app
            # would leak keyboard input outside DOFUS. Emergency Stop still
            # owns explicit release_virtual_inputs() for interrupted macros.
            self.runtime.logger.info("Switch deplacement ignore: fenetre active non Unity.")
            return
        timings = settings_at_start.timings
        focus_lost = False
        last_activated_hwnd: int | None = None
        targets = []
        target_handles: tuple[int, ...] = ()

        def frozen_roster_intact() -> bool:
            return tuple(client.handle for client in targets) == target_handles

        sent = 0
        try:
            targets = self.runtime.switch_character.ordered_clients_from_source(source)
            # Keep a fixed HWND for each physical direction gesture. A mutable
            # Organizer client can be reassigned while focus changes yield.
            target_handles = tuple(client.handle for client in targets)
            for client, target_hwnd in zip(targets, target_handles):
                if (self.runtime.macro_lock.should_stop()
                        or self.runtime.settings is not settings_at_start):
                    return
                if dispatch_context_changed():
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Switch deplacement interrompu: favori modifié entre clients."
                    )
                    return
                if (type(target_hwnd) is not int or not 0 < target_hwnd <= (2**64 - 1)
                        or not frozen_roster_intact()):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Switch deplacement interrompu: session modifiée hwnd=%r", target_hwnd,
                    )
                    return
                if not is_unity_window(target_hwnd) or not is_dofus_unity_process(target_hwnd):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Switch deplacement interrompu: cible non DOFUS Unity hwnd=%s", target_hwnd,
                    )
                    return
                if not frozen_roster_intact():
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Switch deplacement interrompu: roster muté pendant contrôle natif hwnd=%s",
                        target_hwnd,
                    )
                    return
                if activate_window(
                    target_hwnd,
                    timings.click_focus_settle_ms,
                    timings.activate_attempts,
                    timings.activate_retry_ms,
                    self.runtime.logger,
                    "Switch deplacement",
                    should_stop=lambda client=client, hwnd=target_hwnd: (
                        self.runtime.macro_lock.should_stop()
                        or self.runtime.settings is not settings_at_start
                        or not frozen_roster_intact()
                        or dispatch_context_changed()
                    ),
                ):
                    # Validate native identity BEFORE the last focus check:
                    # a process probe may itself yield to a foreign window.
                    if (self.runtime.settings is not settings_at_start
                            or not is_dofus_unity_process(target_hwnd)
                            or foreground_window() != int(target_hwnd)
                            or not frozen_roster_intact()
                            or dispatch_context_changed()):
                        focus_lost = True
                        self.runtime.logger.warning(
                            "Switch deplacement interrompu: focus, identité ou favori perdus avant frappe hwnd=%s",
                            target_hwnd,
                        )
                        return
                    if (self.runtime.macro_lock.should_stop()
                            or self.runtime.settings is not settings_at_start):
                        return
                    if not frozen_roster_intact():
                        focus_lost = True
                        self.runtime.logger.warning(
                            "Switch deplacement interrompu: session mutée avant touche hwnd=%s",
                            target_hwnd,
                        )
                        return
                    last_activated_hwnd = int(target_hwnd)
                    press_key(key_name, timings.movement_key_hold_ms)
                    # Count an input that completed before Stop was observed.
                    sent += 1
                    if not frozen_roster_intact():
                        focus_lost = True
                        self.runtime.logger.warning(
                            "Switch deplacement interrompu: session mutée après touche hwnd=%s",
                            target_hwnd,
                        )
                        return
                    if (self.runtime.macro_lock.should_stop()
                            or self.runtime.settings is not settings_at_start):
                        return
                else:
                    if (self.runtime.macro_lock.should_stop()
                            or self.runtime.settings is not settings_at_start):
                        return
                    if (not frozen_roster_intact()
                            or dispatch_context_changed()):
                        focus_lost = True
                        self.runtime.logger.warning(
                            "Switch deplacement interrompu: session ou favori muté pendant activation hwnd=%s",
                            target_hwnd,
                        )
                        return
                    self.runtime.logger.info(
                        "Switch deplacement: activation echec hwnd=%s",
                        target_hwnd,
                    )
        finally:
            restore_skipped = (
                self.runtime.settings is not settings_at_start
                or not frozen_roster_intact()
                or settings_at_start.macro_mode != mode_at_start
            )
            if restore_skipped:
                self.runtime.logger.info("Switch deplacement: retour ignoré, profil remplacé.")
            if (not self.runtime.macro_lock.should_stop() and not focus_lost
                    and not restore_skipped and not is_dofus_unity_process(source)):
                focus_lost = True
                self.runtime.logger.warning(
                    "Switch deplacement: identité DOFUS perdue avant restauration hwnd=%s", source,
                )
            # The Organizer favorite is part of this action's immutable
            # context. A changed choice is not ours to reactivate.
            if (
                not self.runtime.macro_lock.should_stop() and not focus_lost
                and self.runtime.settings.primary_handle != favorite_at_start
            ):
                restore_skipped = True
                self.runtime.logger.info(
                    "Switch deplacement: retour favori ignoré, favori changé."
                )
            # One final focus probe: a completed synthetic movement key
            # does not authorize bringing DOFUS back after user focus theft.
            if (
                not self.runtime.macro_lock.should_stop() and not focus_lost
                and not restore_skipped and last_activated_hwnd is not None
            ):
                try:
                    if foreground_window() != last_activated_hwnd:
                        restore_skipped = True
                        self.runtime.logger.info(
                            "Switch deplacement: retour favori ignoré, focus utilisateur changé."
                        )
                except Exception:
                    restore_skipped = True
                    self.runtime.logger.exception(
                        "Switch deplacement: focus illisible avant retour au favori."
                    )
            if (not self.runtime.macro_lock.should_stop() and not focus_lost
                    and not restore_skipped
                    and self.runtime.settings is settings_at_start
                    and frozen_roster_intact()
                    and not dispatch_context_changed()
                    and last_activated_hwnd is not None):
                try:
                    self.runtime.switch_character.restore_preferred_client("Switch deplacement")
                except Exception:
                    self.runtime.logger.exception("Switch deplacement: retour au favori impossible.")
            stopped = self.runtime.macro_lock.should_stop()
            state = (
                "interrompu" if (stopped or focus_lost
                                  or self.runtime.settings is not settings_at_start
                                  or not frozen_roster_intact()
                                  or dispatch_context_changed())
                else "ignore" if not targets
                else "termine" if sent == len(targets)
                else "partiel"
            )
            self.runtime.logger.info(
                "Switch deplacement %s: envoyes=%s/%s",
                state, sent, len(targets),
            )

    def release_virtual_inputs(self) -> None:
        for key_name in ("HOME", "DELETE", "END", "PAGEDOWN"):
            try:
                key_up(_vk(key_name))
            except Exception as exc:
                self.runtime.logger.warning(
                    "Relachement touche virtuelle impossible: key=%s error=%s",
                    key_name,
                    exc,
                )
