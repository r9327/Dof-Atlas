"""Bounded Unity-only sequential mirroring for discrete keyboard and wheel gestures.

No background PostMessage, long-held key replay, process injection or network
automation. Windows input is forwarded only after a native hook consumes the
physical event from the explicitly starred foreground DOFUS client.
"""
from __future__ import annotations

import math
from time import perf_counter
from typing import TYPE_CHECKING

from app.macros.mirror_plan import is_dofus_unity_process
from app.windows.focus import activate_window
from app.windows.unity_windows import (
    client_point_from_ratio, client_to_screen, foreground_window,
)
from app.windows.clicks import current_cursor_pos, set_cursor_pos, send_screen_wheel

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime


class MirrorInputMacro:
    def __init__(self, runtime: "AtlasRuntime") -> None:
        self.runtime = runtime

    def run_key(
        self, vk_code: int, source: int, handles: tuple[int, ...],
        *, expected_profile: object | None = None,
    ) -> bool:
        from app.input.hotkeys import MIRROR_DISCRETE_KEYS

        if type(vk_code) is not int or vk_code not in MIRROR_DISCRETE_KEYS:
            return False
        profile_at_dispatch = self.runtime.settings
        if expected_profile is not None and profile_at_dispatch is not expected_profile:
            return False
        return self.runtime._spawn_macro(
            "Miroir clavier",
            lambda: self._run(
                "key", vk_code, source, handles,
                profile_at_dispatch=profile_at_dispatch,
            ),
        )

    def run_wheel(
        self, delta: int, horizontal: bool, x_ratio: float, y_ratio: float,
        source: int, handles: tuple[int, ...],
        *, expected_profile: object | None = None,
    ) -> bool:
        if (type(delta) is not int or delta == 0 or abs(delta) > 32767
                or type(horizontal) is not bool
                or any(type(v) not in (float, int) or not math.isfinite(v)
                       or not 0.0 <= v <= 1.0
                       for v in (x_ratio, y_ratio))):
            return False
        profile_at_dispatch = self.runtime.settings
        if expected_profile is not None and profile_at_dispatch is not expected_profile:
            return False
        return self.runtime._spawn_macro(
            "Miroir molette",
            lambda: self._run(
                "wheel", (delta, horizontal, x_ratio, y_ratio), source, handles,
                profile_at_dispatch=profile_at_dispatch,
            ),
        )

    def _still_current(self, source: int, handles: tuple[int, ...]) -> bool:
        """Cheap roster check; native DOFUS identity is validated separately.

        Do not treat True as authorization to send input. The worker must
        verify all processes at preflight and the recipient before each send.
        """
        settings = self.runtime.settings
        if settings.macro_mode != "mirror" or settings.primary_handle != source:
            return False
        if (
            type(source) is not int
            or not isinstance(handles, tuple)
            or not 2 <= len(handles) <= 8
            or any(type(hwnd) is not int or hwnd <= 0 for hwnd in handles)
            or len(set(handles)) != len(handles)
            or handles[0] != source
        ):
            return False
        # This check runs for every recipient: compare the in-memory roster
        # without re-querying every Windows process O(n²) per gesture.
        # Native process identity is verified once for the whole roster at
        # dispatch, then for each recipient immediately before sending.
        live = tuple(c.handle for c in settings.clients)
        if source not in live:
            return False
        # Favorite-first is the dispatch order, not necessarily the saved
        # Organizer slot order. Do not invalidate a legitimate non-first star.
        expected = (source, *(hwnd for hwnd in live if hwnd != source))
        return expected == handles

    def _run(
        self, kind: str, payload: object, source: int, handles: tuple[int, ...],
        *, profile_at_dispatch: object | None = None,
    ) -> None:
        runtime = self.runtime
        # A queued callback belongs to the profile that accepted the physical
        # gesture. Identical HWNDs after a reload are still a new generation.
        # Reject BEFORE cursor reads, process probes or focus changes.
        profile_at_start = runtime.settings
        if (profile_at_dispatch is not None
                and profile_at_start is not profile_at_dispatch):
            runtime.logger.warning(
                "Miroir %s annulé: profil Organizer remplacé avant worker.", kind,
            )
            runtime._emit_status(
                "Miroir non diffusé : profil Organizer modifié."
            )
            return
        timings = profile_at_start.timings
        start = perf_counter()
        delivered = 0
        send_samples_ms: list[float] = []
        focus_samples_ms: list[float] = []
        cursor = None
        focus_lost = False
        delivery_failed = False
        roster_verified = False
        last_activated_hwnd: int | None = None
        if kind == "wheel":
            try:
                cursor = current_cursor_pos()
            except Exception:
                runtime.logger.exception("Miroir molette: lecture curseur impossible.")
                runtime._emit_status(
                    f"Miroir Molette incomplet : 0/{len(handles)} fenêtres."
                )
                return
        # Keyboard-only replay never moves the pointer. Blocking the real
        # mouse here discards user clicks throughout the 2–8 client fan-out.
        # Wheel replay does move the pointer and needs the native guard.
        mouse_blocked = False
        try:
            if (runtime.settings is not profile_at_start
                    or not self._still_current(source, handles)):
                runtime.logger.warning("Miroir %s annulé: profil, favori ou sessions modifiés.", kind)
                return
            # Fail closed before the first emission if ANY configured HWND
            # has become an unrelated process. Avoid partial delivery caused
            # by a foreign/stale handle discovered halfway through a gesture.
            if not all(is_dofus_unity_process(hwnd) for hwnd in handles):
                runtime.logger.warning("Miroir %s annulé: roster non DOFUS.", kind)
                return
            roster_verified = True
            if runtime.settings is not profile_at_start:
                runtime.logger.warning("Miroir %s annulé: profil remplacé pendant le contrôle des clients.", kind)
                return
            # Authenticate the entire roster before taking a mouse block.
            # This keeps slow Win32 process probes outside the blocked interval.
            if kind == "wheel":
                runtime.input_state.begin_mouse_block("Miroir molette")
                mouse_blocked = True
            for index, hwnd in enumerate(handles):
                if (runtime.macro_lock.should_stop()
                        or runtime.settings is not profile_at_start
                        or not self._still_current(source, handles)):
                    break
                if not is_dofus_unity_process(hwnd):
                    # A validated roster can change identity during fan-out.
                    # Never restore cursor/focus on a partial unsafe delivery.
                    delivery_failed = True
                    runtime.logger.warning("Miroir %s: HWND non DOFUS, annulation.", kind)
                    break
                focus_started_at = perf_counter()
                try:
                    activated = activate_window(
                        hwnd, timings.switch_background_pre_click_ms,
                        timings.activate_attempts, timings.activate_retry_ms,
                        runtime.logger, "Miroir " + kind,
                        should_stop=lambda: (
                            runtime.macro_lock.should_stop()
                            or runtime.settings is not profile_at_start
                            or not self._still_current(source, handles)
                        ),
                    )
                except Exception:
                    focus_lost = True
                    runtime.logger.exception(
                        "Miroir %s: exception pendant activation hwnd=%s.", kind, hwnd,
                    )
                    break
                finally:
                    focus_samples_ms.append((perf_counter() - focus_started_at) * 1000.0)
                if not activated:
                    # Do not force the previous favorite back when the user
                    # may have intentionally switched to another application.
                    focus_lost = True
                    runtime.logger.warning("Miroir %s: activation non confirmée hwnd=%s.", kind, hwnd)
                    break
                if runtime.macro_lock.should_stop():
                    break
                # Activation may run callbacks or release the GIL. Recheck the
                # exact roster and Win32 process identity AFTER focus changes,
                # not only before activating the target.
                if (runtime.settings is not profile_at_start
                        or not self._still_current(source, handles)):
                    delivery_failed = True
                    runtime.logger.warning(
                        "Miroir %s: favori ou roster changé après activation hwnd=%s.",
                        kind, hwnd,
                    )
                    break
                if not is_dofus_unity_process(hwnd):
                    delivery_failed = True
                    runtime.logger.warning(
                        "Miroir %s: processus DOFUS remplacé après activation hwnd=%s.",
                        kind, hwnd,
                    )
                    break
                # The native identity probe can yield to another window.
                # Make foreground the LAST Win32 check before input.
                if foreground_window() != hwnd:
                    focus_lost = True
                    runtime.logger.warning("Miroir %s: focus volé avant envoi hwnd=%s.", kind, hwnd)
                    break
                last_activated_hwnd = hwnd
                if runtime.macro_lock.should_stop():
                    break
                try:
                    sent_at = perf_counter()
                    if kind == "key":
                        from app.macros.input_tools import key_down, key_up
                        vk = int(payload)
                        # Only a successful DOWN owns a matching synthetic
                        # UP. If Windows refused DOWN, an orphaned UP could
                        # affect a different foreground application.
                        key_down(vk)
                        try:
                            runtime.macro_lock.wait(
                                min(40, max(10, timings.switch_click_down_ms))
                            )
                        finally:
                            try:
                                key_up(vk)
                            except OSError:
                                # A refused KEYUP can leave the synthetic key
                                # logically held across clients. Retry once
                                # without changing focus or starting a worker.
                                runtime.logger.warning(
                                    "Miroir clavier: relâchement refusé, tentative de secours vk=%s",
                                    vk,
                                )
                                key_up(vk)
                    else:
                        delta, horizontal, xr, yr = payload
                        point = client_point_from_ratio(hwnd, xr, yr)
                        screen = client_to_screen(hwnd, *point) if point is not None else None
                        if screen is None:
                            delivery_failed = True
                            runtime.logger.warning("Miroir molette: coordonnées indisponibles.")
                            break
                        runtime.synthetic_guard.begin(200)
                        try:
                            set_cursor_pos(*screen)
                            # Cursor motion can activate a different window on
                            # some desktop configurations. Verify again before
                            # dispatching the physical wheel gesture.
                            # Cursor movement can invoke native hooks and user
                            # actions; never emit a wheel tick on a stale
                            # favorite, changed roster or stopped worker.
                            if runtime.macro_lock.should_stop():
                                break
                            if (runtime.settings is not profile_at_start
                                    or not self._still_current(source, handles)):
                                delivery_failed = True
                                runtime.logger.warning(
                                    "Miroir molette: roster changé après déplacement hwnd=%s.", hwnd,
                                )
                                break
                            if not is_dofus_unity_process(hwnd):
                                delivery_failed = True
                                runtime.logger.warning(
                                    "Miroir molette: processus remplacé après déplacement hwnd=%s.", hwnd,
                                )
                                break
                            # Final focus check occurs AFTER identity/roster
                            # validation and immediately before SendInput.
                            if foreground_window() != hwnd:
                                focus_lost = True
                                runtime.logger.warning(
                                    "Miroir molette: focus volé après déplacement hwnd=%s.", hwnd,
                                )
                                break
                            if runtime.macro_lock.should_stop():
                                break
                            if not send_screen_wheel(delta, horizontal=horizontal):
                                delivery_failed = True
                                runtime.logger.warning("Miroir molette: SendInput refusé.")
                                break
                        finally:
                            runtime.synthetic_guard.end(120)
                    delivered += 1
                    send_samples_ms.append((perf_counter() - sent_at) * 1000.0)
                except Exception:
                    delivery_failed = True
                    runtime.logger.exception("Miroir %s: échec SendInput.", kind)
                    break
                # The final recipient does not need a client-switch gap.
                if (index < len(handles) - 1
                        and runtime.macro_lock.wait(max(0, timings.switch_client_settle_ms))):
                    break
        finally:
            # Wheel-only block stays active during cursor/focus restoration.
            # Keyboard never acquires the physical mouse block.
            try:
                # A fully sent command does not authorize taking focus or
                # moving the pointer after the user has switched apps.
                # This is one O(1) native probe per completed worker.
                user_focus_changed = False
                if (
                    roster_verified and not focus_lost and not delivery_failed
                    and not runtime.macro_lock.should_stop()
                    and last_activated_hwnd is not None
                ):
                    try:
                        if foreground_window() != last_activated_hwnd:
                            user_focus_changed = True
                            runtime.logger.info(
                                "Miroir %s: restauration ignorée, focus utilisateur changé.",
                                kind,
                            )
                    except Exception:
                        user_focus_changed = True
                        runtime.logger.exception(
                            "Miroir %s: focus non vérifiable avant restauration.", kind,
                        )
                # Stop, failed SendInput or a stolen focus must not move the
                # user's pointer after the macro has relinquished control.
                if (
                    cursor is not None and roster_verified
                    and not user_focus_changed
                    and not focus_lost and not delivery_failed
                    and not runtime.macro_lock.should_stop()
                    and runtime.settings is profile_at_start
                    and self._still_current(source, handles)
                ):
                    try:
                        set_cursor_pos(*cursor)
                        # A cursor restoration can itself dispatch a desktop
                        # hook, so never restore favorite without checking
                        # foreground once more after the pointer moves.
                        if foreground_window() != last_activated_hwnd:
                            user_focus_changed = True
                            runtime.logger.info(
                                "Miroir %s: retour au favori ignoré, focus changé après curseur.",
                                kind,
                            )
                    except Exception:
                        user_focus_changed = True
                        runtime.logger.exception(
                            "Miroir molette: restauration curseur impossible."
                        )
                # A changed favorite must not be activated as a side effect of
                # aborting the original gesture (same policy as mouse clicks).
                if (roster_verified and not user_focus_changed
                        and not focus_lost and not delivery_failed
                        and not runtime.macro_lock.should_stop()
                        and runtime.settings is profile_at_start
                        and self._still_current(source, handles)
                        and is_dofus_unity_process(source)
                        and runtime.settings is profile_at_start):
                    try:
                        runtime.switch_character.restore_preferred_client("Miroir " + kind)
                    except Exception:
                        runtime.logger.exception("Miroir %s: retour au favori impossible.", kind)
            finally:
                if mouse_blocked:
                    runtime.input_state.end_mouse_block()
            from app.macros.mirror_plan import mirror_latency_percentiles_ms

            latency = mirror_latency_percentiles_ms(send_samples_ms)
            focus_latency = mirror_latency_percentiles_ms(focus_samples_ms)
            runtime.logger.info(
                "Miroir %s: envoyés=%s/%s worker_total_ms=%.2f "
                "delivery_step_ms=%s focus_activation_ms=%s",
                kind, delivered, len(handles), (perf_counter() - start) * 1000.0,
                latency if latency is not None else "NOT_MEASURED",
                focus_latency if focus_latency is not None else "NOT_MEASURED",
            )
            label = "Clavier" if kind == "key" else "Molette"
            if delivered != len(handles) or runtime.macro_lock.should_stop():
                runtime._emit_status(
                    f"Miroir {label} incomplet : {delivered}/{len(handles)} fenêtres."
                )
            else:
                runtime._emit_status(
                    f"Miroir {label} : {delivered}/{len(handles)} fenêtres."
                )
