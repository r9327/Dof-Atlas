"""Bounded Unity-only sequential mirroring for discrete keyboard and wheel gestures.

No background PostMessage, long-held key replay, process injection or network
automation. Windows input is forwarded only after a native hook consumes the
physical event from the explicitly starred foreground DOFUS client.
"""
from __future__ import annotations

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

    def run_key(self, vk_code: int, source: int, handles: tuple[int, ...]) -> bool:
        if type(vk_code) is not int or not (1 <= vk_code <= 254):
            return False
        return self.runtime._spawn_macro(
            "Miroir clavier", lambda: self._run("key", vk_code, source, handles)
        )

    def run_wheel(
        self, delta: int, horizontal: bool, x_ratio: float, y_ratio: float,
        source: int, handles: tuple[int, ...],
    ) -> bool:
        if (type(delta) is not int or delta == 0 or abs(delta) > 32767
                or not isinstance(horizontal, bool)):
            return False
        return self.runtime._spawn_macro(
            "Miroir molette", lambda: self._run(
                "wheel", (delta, horizontal, x_ratio, y_ratio), source, handles,
            ),
        )

    def _still_current(self, source: int, handles: tuple[int, ...]) -> bool:
        settings = self.runtime.settings
        if settings.macro_mode != "mirror" or settings.primary_handle != source:
            return False
        if len(handles) < 2 or len(handles) > 8 or len(set(handles)) != len(handles):
            return False
        # Reject roster drift between hook and worker, not merely stale HWNDs.
        live = tuple(c.handle for c in settings.clients if is_dofus_unity_process(c.handle))
        return set(live) == set(handles) and len(live) == len(handles) and source in live

    def _run(
        self, kind: str, payload: object, source: int, handles: tuple[int, ...],
    ) -> None:
        runtime = self.runtime
        timings = runtime.settings.timings
        start = perf_counter()
        delivered = 0
        send_samples_ms: list[float] = []
        cursor = None
        if kind == "wheel":
            try:
                cursor = current_cursor_pos()
            except Exception:
                runtime.logger.exception("Miroir molette: lecture curseur impossible.")
                return
        runtime.input_state.begin_mouse_block("Miroir entrée")
        try:
            if not self._still_current(source, handles):
                runtime.logger.warning("Miroir %s annulé: favori ou sessions modifiés.", kind)
                return
            for hwnd in handles:
                if runtime.macro_lock.should_stop() or not self._still_current(source, handles):
                    break
                if not is_dofus_unity_process(hwnd):
                    runtime.logger.warning("Miroir %s: HWND non DOFUS, annulation.", kind)
                    break
                if not activate_window(
                    hwnd, timings.switch_background_pre_click_ms,
                    timings.activate_attempts, timings.activate_retry_ms,
                    runtime.logger, "Miroir " + kind,
                    should_stop=runtime.macro_lock.should_stop,
                ) or foreground_window() != hwnd:
                    runtime.logger.warning("Miroir %s: activation non confirmée hwnd=%s.", kind, hwnd)
                    break
                if runtime.macro_lock.should_stop():
                    break
                try:
                    sent_at = perf_counter()
                    if kind == "key":
                        from app.macros.input_tools import key_down, key_up
                        vk = int(payload)
                        # Never leave a held key behind, including on stop or SendInput error.
                        try:
                            key_down(vk)
                            runtime.macro_lock.wait(min(40, max(10, timings.switch_click_down_ms)))
                        finally:
                            key_up(vk)
                    else:
                        delta, horizontal, xr, yr = payload
                        point = client_point_from_ratio(hwnd, xr, yr)
                        screen = client_to_screen(hwnd, *point) if point is not None else None
                        if screen is None:
                            runtime.logger.warning("Miroir molette: coordonnées indisponibles.")
                            break
                        runtime.synthetic_guard.begin(200)
                        try:
                            set_cursor_pos(*screen)
                            if not send_screen_wheel(delta, horizontal=horizontal):
                                runtime.logger.warning("Miroir molette: SendInput refusé.")
                                break
                        finally:
                            runtime.synthetic_guard.end(120)
                    delivered += 1
                    send_samples_ms.append((perf_counter() - sent_at) * 1000.0)
                except Exception:
                    runtime.logger.exception("Miroir %s: échec SendInput.", kind)
                    break
                if runtime.macro_lock.wait(max(0, timings.switch_client_settle_ms)):
                    break
        finally:
            runtime.input_state.end_mouse_block()
            if cursor is not None:
                try:
                    set_cursor_pos(*cursor)
                except Exception:
                    runtime.logger.exception("Miroir molette: restauration curseur impossible.")
            # A changed favorite must not be activated as a side effect of
            # aborting the original gesture (same policy as mouse clicks).
            if not runtime.macro_lock.should_stop() and self._still_current(source, handles):
                try:
                    runtime.switch_character.restore_preferred_client("Miroir " + kind)
                except Exception:
                    runtime.logger.exception("Miroir %s: retour au favori impossible.", kind)
            from app.macros.mirror_plan import mirror_latency_percentiles_ms

            latency = mirror_latency_percentiles_ms(send_samples_ms)
            runtime.logger.info(
                "Miroir %s: envoyés=%s/%s total_ms=%.2f SendInput_ms=%s",
                kind, delivered, len(handles), (perf_counter() - start) * 1000.0,
                latency if latency is not None else "NOT_MEASURED",
            )
