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

    def run_async(self, key_name: str) -> bool:
        return self.runtime._spawn_macro("Switch deplacement", lambda: self._run(key_name))

    def _run(self, key_name: str) -> None:
        settings_at_start = self.runtime.settings
        source = foreground_window()
        if (not source or not is_unity_window(source)
                or not is_dofus_unity_process(source)
                or settings_at_start.client_by_handle(source) is None
                or self.runtime.settings is not settings_at_start):
            self.runtime.logger.info("Switch deplacement ignore: fenetre active non Unity.")
            self.release_virtual_inputs()
            return
        timings = settings_at_start.timings
        favorite_at_start = settings_at_start.primary_handle
        focus_lost = False
        last_activated_hwnd: int | None = None
        targets = []
        sent = 0
        try:
            targets = self.runtime.switch_character.ordered_clients_from_source(source)
            for client in targets:
                if (self.runtime.macro_lock.should_stop()
                        or self.runtime.settings is not settings_at_start):
                    return
                if not is_unity_window(client.handle) or not is_dofus_unity_process(client.handle):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "Switch deplacement interrompu: cible non DOFUS Unity hwnd=%s", client.handle,
                    )
                    return
                if activate_window(
                    client.handle,
                    timings.click_focus_settle_ms,
                    timings.activate_attempts,
                    timings.activate_retry_ms,
                    self.runtime.logger,
                    "Switch deplacement",
                    should_stop=lambda: (
                        self.runtime.macro_lock.should_stop()
                        or self.runtime.settings is not settings_at_start
                    ),
                ):
                    # Validate native identity BEFORE the last focus check:
                    # a process probe may itself yield to a foreign window.
                    if (self.runtime.settings is not settings_at_start
                            or not is_dofus_unity_process(client.handle)
                            or foreground_window() != int(client.handle)):
                        focus_lost = True
                        self.runtime.logger.warning(
                            "Switch deplacement interrompu: focus ou identité DOFUS perdus avant frappe hwnd=%s",
                            client.handle,
                        )
                        return
                    if (self.runtime.macro_lock.should_stop()
                            or self.runtime.settings is not settings_at_start):
                        return
                    last_activated_hwnd = int(client.handle)
                    press_key(key_name, timings.movement_key_hold_ms)
                    # Count an input that completed before Stop was observed.
                    sent += 1
                    if (self.runtime.macro_lock.should_stop()
                            or self.runtime.settings is not settings_at_start):
                        return
                else:
                    self.runtime.logger.info(
                        "Switch deplacement: activation echec hwnd=%s",
                        client.handle,
                    )
        finally:
            restore_skipped = self.runtime.settings is not settings_at_start
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
                    and self.runtime.settings is settings_at_start):
                try:
                    self.runtime.switch_character.restore_preferred_client("Switch deplacement")
                except Exception:
                    self.runtime.logger.exception("Switch deplacement: retour au favori impossible.")
            stopped = self.runtime.macro_lock.should_stop()
            state = (
                "interrompu" if stopped or focus_lost or self.runtime.settings is not settings_at_start
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
