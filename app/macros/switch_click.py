from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
from time import perf_counter
from typing import TYPE_CHECKING

from app.macros.mirror_plan import is_dofus_unity_process
from app.windows.clicks import current_cursor_pos, send_client_click, set_cursor_pos
from app.windows.focus import activate_window
from app.windows.unity_windows import (
    clamp_client_point,
    client_center,
    client_point_from_ratio,
    client_point_ratio,
    find_known_client_from_point,
    foreground_window,
    is_unity_window,
    screen_to_client,
)

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime


@dataclass(frozen=True)
class SwitchClickContext:
    source_hwnd: int
    client_x: int | None
    client_y: int | None
    x_ratio: float | None
    y_ratio: float | None
    reason: str


class SwitchClickMacro:
    def __init__(self, runtime: "AtlasRuntime"):
        self.runtime = runtime

    def reset(self) -> None:
        # Aucun état interne propre à cette macro. La méthode reste présente
        # car le stop d'urgence du runtime l'appelle.
        pass

    def run_async(
        self,
        button: str,
        screen_x: int,
        screen_y: int,
        click_count: int,
        action_label: str,
        *,
        exact_source_handle: int | None = None,
        mirror_target_handles: tuple[int, ...] | None = None,
        captured_context: SwitchClickContext | None = None,
        physical_source_delivered: bool = False,
        expected_profile: object | None = None,
    ) -> bool:
        settings_at_dispatch = self.runtime.settings
        if settings_at_dispatch is None:
            # Organizer reload may detach its profile while a native hook
            # dispatches a click; never swallow a real click on that race.
            self.runtime.logger.warning(
                "%s refusé avant clic physique: profil Organizer absent.",
                action_label,
            )
            return False

        def roster_snapshot(clients: object) -> tuple[tuple[type, object], ...] | None:
            if not isinstance(clients, (list, tuple)):
                return None
            # A client may be detached or replaced in-place during reload.
            # Never read .handle unguarded in a low-level hook callback.
            handles = (getattr(client, "handle", None) for client in clients)
            return tuple((type(handle), handle) for handle in handles)

        original_clients = getattr(settings_at_dispatch, "clients", None)
        dispatch_roster = roster_snapshot(original_clients)
        dispatch_mode = getattr(settings_at_dispatch, "macro_mode", None)
        dispatch_primary = getattr(settings_at_dispatch, "primary_handle", None)
        if dispatch_mode not in ("macro", "mirror"):
            # Partial profile reload: an unknown mode can never authorize
            # swallowing the physical source gesture.
            return False

        # A native click may be swallowed as soon as this function admits
        # a worker. Reject a corrupt live Organizer roster BEFORE capture
        # or admission: the low-level hook can then preserve the real click
        # instead of losing it when _run later refuses the same roster.
        if dispatch_roster is not None and (
                not 1 <= len(dispatch_roster) <= 8
                or any(kind is not int or not 0 < hwnd <= (2**64 - 1)
                       for kind, hwnd in dispatch_roster)
                or len({hwnd for _, hwnd in dispatch_roster}) != len(dispatch_roster)):
            self.runtime.logger.warning(
                "%s refusé avant clic physique: roster Organizer invalide.",
                action_label,
            )
            return False

        def dispatch_is_current() -> bool:
            active_mode = getattr(settings_at_dispatch, "macro_mode", None)
            active_primary = getattr(settings_at_dispatch, "primary_handle", None)
            if (self.runtime.settings is not settings_at_dispatch
                    or active_mode != dispatch_mode
                    or type(active_primary) is not type(dispatch_primary)
                    or active_primary != dispatch_primary):
                return False
            if dispatch_roster is None:
                return True
            live = getattr(settings_at_dispatch, "clients", None)
            return roster_snapshot(live) == dispatch_roster

        if expected_profile is not None and settings_at_dispatch is not expected_profile:
            self.runtime.logger.info(
                "%s annulé: profil Organizer remplacé avant capture.", action_label,
            )
            return False
        # Direct consumers must not alias an old favorite/roster with numeric
        # lookalikes, or queue a Mirror gesture after Macro was selected.
        # This check happens before any native context capture.
        if exact_source_handle is not None and (
            type(exact_source_handle) is not int
            or not 0 < exact_source_handle <= (2**64 - 1)
        ):
            return False
        if mirror_target_handles is not None and (
            type(mirror_target_handles) is not tuple
            or not 2 <= len(mirror_target_handles) <= 8
            or exact_source_handle is None
            or mirror_target_handles[0] != exact_source_handle
            or any(type(hwnd) is not int or not 0 < hwnd <= (2**64 - 1)
                   for hwnd in mirror_target_handles)
            or len(set(mirror_target_handles)) != len(mirror_target_handles)
            or dispatch_mode != "mirror"
            or type(dispatch_primary) is not int
            or dispatch_primary != exact_source_handle
            # The native hook may have frozen this gesture before an
            # in-place Organizer slot change. Never accept that stale roster
            # as a new snapshot: the worker would abort after DOWN was eaten.
            or dispatch_roster is None
            or len(dispatch_roster) != len(mirror_target_handles)
            or any(kind is not int for kind, _ in dispatch_roster)
            or (
                exact_source_handle,
                *(hwnd for _, hwnd in dispatch_roster
                  if hwnd != exact_source_handle),
            ) != mirror_target_handles
        ):
            return False
        normalized_button = str(button or "").strip().casefold()
        if normalized_button not in {"left", "right"}:
            self.runtime.logger.warning(
                "%s ignore: bouton invalide=%r",
                action_label,
                button,
            )
            return False

        # Physical screen coordinates are signed Win32 pixels. Casting a
        # fractional, boolean or oversized value can target another object.
        # Refuse it before any expensive hit-test or worker admission.
        if (type(screen_x) is not int or type(screen_y) is not int
                or not -(2**31) <= screen_x < 2**31
                or not -(2**31) <= screen_y < 2**31):
            self.runtime.logger.warning(
                "%s ignore: position souris invalide x=%r y=%r",
                action_label, screen_x, screen_y,
            )
            return False

        try:
            requested_count = int(click_count)
        except (TypeError, ValueError, OverflowError):
            requested_count = 1
        click_count = 2 if requested_count >= 2 else 1
        button_name = "Right" if normalized_button == "right" else "Left"

        # Cette capture reste volontairement légère : aucune activation,
        # attente ou boucle n'est exécutée dans le callback du hook souris.
        context = captured_context
        if context is None:
            context = self._capture_trigger_context(
                screen_x, screen_y, action_label,
            )
        if physical_source_delivered and (
            context is None or context.reason != "cursor"
            or captured_context is None
        ):
            self.runtime.logger.warning(
                "%s refusé: source physique non confirmée.", action_label,
            )
            return False
        if exact_source_handle is not None and (
            context is None
            or context.source_hwnd != exact_source_handle
            or context.reason != "cursor"
        ):
            self.runtime.logger.warning(
                "%s ignore: clic hors du favori explicite hwnd=%s",
                action_label, exact_source_handle,
            )
            return False
        if not dispatch_is_current():
            self.runtime.logger.info(
                "%s annulé: profil ou roster Organizer changé pendant capture.", action_label,
            )
            return False
        if context is None:
            self.runtime.logger.info(
                "%s ignore: aucune fenêtre Unity source ou favorite.",
                action_label,
            )
            return False
        if mirror_target_handles is not None:
            # Only a real integer client pixel or a *finite* 0..1 ratio
            # can authorize consumption of a physical Miroir DOWN.
            # Clamping NaN, infinity, a corrupted ratio, or a fractional
            # client coordinate may click an unrelated object in DOFUS.
            ratio = (context.x_ratio, context.y_ratio)
            pixels = (context.client_x, context.client_y)
            ratio_valid = (
                (ratio[0] is None and ratio[1] is None)
                or all(
                    type(v) in (int, float) and 0 <= v <= 1
                    and (type(v) is int or math.isfinite(v))
                    for v in ratio
                )
            )
            pixels_valid = all(
                type(v) is int and -(2**31) <= v < 2**31
                for v in pixels
            )
            if not ratio_valid or not pixels_valid:
                self.runtime.logger.warning(
                    "%s ignore: coordonnées Unity source invalides.", action_label,
                )
                return False

        # A native DOWN/UP already reached the only registered character.
        # Do not create a macro worker or block physical input for a no-op.
        if (physical_source_delivered and exact_source_handle is None
                and mirror_target_handles is None):
            # Do not read a third live roster in this no-op path: reload may
            # detach a slot after dispatch_is_current() checked the snapshot.
            if dispatch_roster == ((int, context.source_hwnd),):
                self.runtime.logger.debug(
                    "%s: source physique seule, aucune réinjection nécessaire.",
                    action_label,
                )
                return True

        # Count from admission to the last successful *emission*, including
        # scheduler delay. This is never a measure of Unity rendering.
        dispatch_at = perf_counter() if action_label == "Miroir" else None
        # A low-level hook callback must never reserve the physical mouse
        # while a worker is merely queued. The worker validates the source
        # and exact roster before taking ownership of the pointer.
        def worker() -> None:
            if self.runtime.macro_lock.should_stop():
                self.runtime.logger.info(
                    "%s annulé: Stop urgence avant worker.", action_label,
                )
                return
            if not dispatch_is_current():
                self.runtime.logger.info(
                    "%s annulé: roster Organizer changé avant worker.", action_label,
                )
                return
            self._run(
                button_name,
                click_count,
                action_label,
                context,
                exact_source_handle=exact_source_handle,
                mirror_target_handles=mirror_target_handles,
                physical_source_delivered=physical_source_delivered,
                settings_at_dispatch=settings_at_dispatch,
                dispatch_guard=dispatch_is_current,
                dispatch_at=dispatch_at,
            )

        started = self.runtime._spawn_macro(action_label, worker)
        # Worker admission can yield to an Organizer reload after the native
        # mouse hook has validated its context. If that happens, let the
        # real DOWN/UP pass through: the queued worker will reject its stale
        # generation before any synthetic click is sent.
        return bool(
            started and not self.runtime.macro_lock.should_stop()
            and dispatch_is_current()
        )

    def _run(
        self,
        button: str,
        click_count: int,
        action_label: str,
        context: SwitchClickContext,
        mouse_block_started: bool = False,
        exact_source_handle: int | None = None,
        mirror_target_handles: tuple[int, ...] | None = None,
        physical_source_delivered: bool = False,
        settings_at_dispatch: object | None = None,
        dispatch_guard: Callable[[], bool] | None = None,
        dispatch_at: float | None = None,
    ) -> None:
        settings_at_start = (
            settings_at_dispatch if settings_at_dispatch is not None
            else self.runtime.settings
        )
        original_cursor: tuple[int, int] | None = None
        sent_count = 0
        target_total = 0
        mouse_blocked = mouse_block_started
        mouse_block_started_at: float | None = None
        should_restore_preferred = False
        last_activated_hwnd: int | None = None
        focus_lost = False
        delivery_failed = False
        mirror_started_at = perf_counter() if action_label == "Miroir" else None
        last_emission_at: float | None = None
        mirror_send_samples: list[float] = []
        mirror_focus_samples: list[float] = []
        targets = []
        frozen_handles: tuple[int, ...] = ()
        def pointer_interrupted() -> bool:
            # Mock-only test runtimes without a real InputState must not
            # spuriously cancel their senders (a bare Mock is truthy).
            check = getattr(self.runtime.input_state, "mouse_block_interrupted", None)
            return bool(mouse_blocked and callable(check) and check() is True)

        initial_mode = getattr(settings_at_start, "macro_mode", None)
        initial_primary = getattr(settings_at_start, "primary_handle", None)

        def roster_signature(clients: object) -> tuple[tuple[type, object], ...] | None:
            if not isinstance(clients, (list, tuple)):
                return None
            # Do not let a concurrently destroyed client property throw out
            # of the worker's finally block while it owns the pointer lease.
            try:
                handles = (getattr(client, "handle", None) for client in clients)
                return tuple((type(hwnd), hwnd) for hwnd in handles)
            except Exception:
                return None

        initial_clients = getattr(settings_at_start, "clients", None)
        initial_roster = roster_signature(initial_clients)
        initial_roster_invalid = (
            isinstance(initial_clients, (list, tuple))
            and initial_roster is None
        )

        def target_roster_intact() -> bool:
            # Ordered clients contain mutable Organizer records. Use HWNDs
            # accepted before Win32 yields, never their reassigned values.
            return (
                not initial_roster_invalid
                and self.runtime.settings is settings_at_start
                and (dispatch_guard is None or dispatch_guard())
                and getattr(settings_at_start, "macro_mode", None) == initial_mode
                and type(getattr(settings_at_start, "primary_handle", None)) is type(initial_primary)
                and getattr(settings_at_start, "primary_handle", None) == initial_primary
                and (
                    initial_roster is None
                    or roster_signature(
                        getattr(settings_at_start, "clients", None)
                    ) == initial_roster
                )
                and len(targets) == len(frozen_handles)
                and roster_signature(targets) == tuple(
                    (type(hwnd), hwnd) for hwnd in frozen_handles
                )
            )

        try:
            if initial_roster_invalid or (
                mirror_target_handles is not None and initial_roster is None
            ):
                self.runtime.logger.warning(
                    "%s annulé: roster illisible avant worker.", action_label,
                )
                return
            if (self.runtime.settings is not settings_at_start
                    or (dispatch_guard is not None and not dispatch_guard())):
                self.runtime.logger.info(
                    "%s annulé: profil ou roster modifié avant worker.", action_label,
                )
                return
            # The physical DOWN belonged to a real favorite foreground.
            # An asynchronously admitted mirror worker must not reactivate
            # Dofus after the user has already switched to another app.
            if (settings_at_dispatch is not None
                    and mirror_target_handles is not None
                    and exact_source_handle is not None):
                try:
                    if foreground_window() != exact_source_handle:
                        self.runtime.logger.info(
                            "%s annulé: source non active avant worker.", action_label,
                        )
                        self.runtime._emit_status(
                            "Miroir non diffusé : focus source perdu."
                        )
                        return
                except Exception:
                    self.runtime.logger.exception(
                        "%s annulé: focus source illisible avant worker.", action_label,
                    )
                    self.runtime._emit_status(
                        "Miroir non diffusé : focus source perdu."
                    )
                    return
            try:
                original_cursor = current_cursor_pos()
            except Exception:
                self.runtime.logger.exception(
                    "%s lecture position curseur impossible.",
                    action_label,
                )
                # All click deliveries move the physical pointer. Without a
                # reliable original position, the worker cannot give it back.
                # Abort before activating or blocking any client.
                self.runtime._emit_status(
                    f"{action_label} non diffusé : position souris indisponible."
                )
                return

            # The original cursor can be read and roster checked without
            # changing focus, moving the pointer or emitting mouse events.
            # Keep actual physical clicks native through this preflight.
            context = self._validated_context(context, action_label)
            if (self.runtime.settings is not settings_at_start
                    or (dispatch_guard is not None and not dispatch_guard())):
                self.runtime.logger.info(
                    "%s annulé: profil ou roster modifié durant preflight.", action_label,
                )
                return
            # Classic SwitchClick may recover another favorite; Mirror must
            # never silently change its source after a click was consumed.
            if exact_source_handle is not None and (
                context is None
                or context.source_hwnd != exact_source_handle
                or self.runtime.settings.primary_handle != exact_source_handle
            ):
                self.runtime.logger.warning(
                    "%s annulé: favori source modifié ou déconnecté.", action_label,
                )
                return
            if context is None:
                self.runtime.logger.info(
                    "%s ignore: fenêtre Unity source indisponible.",
                    action_label,
                )
                return
            if physical_source_delivered and context.reason != "cursor":
                self.runtime.logger.warning(
                    "%s annulé: source physique remplacée.", action_label,
                )
                return

            resolved_targets = self.runtime.switch_character.ordered_clients_from_source(
                context.source_hwnd
            )
            if not isinstance(resolved_targets, (list, tuple)):
                delivery_failed = True
                self.runtime.logger.warning(
                    "%s interrompu: liste des destinataires invalide.", action_label,
                )
                return
            targets = resolved_targets
            target_total = len(targets)
            frozen_handles = tuple(
                getattr(client, "handle", None) for client in targets
            )
            if not target_roster_intact():
                delivery_failed = True
                self.runtime.logger.warning(
                    "%s interrompu: roster modifié pendant capture.", action_label,
                )
                return
            # Both classic SwitchClick and Miroir must reject a malformed
            # participant roster before taking ownership of the physical
            # pointer. Eight is the Organizer capacity, never a send quota
            # that silently trims an unknown ninth window.
            if (len(frozen_handles) > 8
                    or any(type(hwnd) is not int or not 0 < hwnd <= (2**64 - 1)
                           for hwnd in frozen_handles)
                    or len(set(frozen_handles)) != len(frozen_handles)):
                delivery_failed = True
                self.runtime.logger.warning(
                    "%s refusé: roster Organizer invalide ou supérieur à huit.",
                    action_label,
                )
                return
            if mirror_target_handles is not None:
                # Never fan out to a client that appeared after the physical
                # click, or to a different favorite during an active gesture.
                actual_handles = frozen_handles
                captured_handles = tuple(mirror_target_handles)
                if (
                    len(captured_handles) < 2
                    or len(captured_handles) > 8
                    or len(set(captured_handles)) != len(captured_handles)
                    or len(actual_handles) != len(captured_handles)
                    or set(actual_handles) != set(captured_handles)
                    or context.source_hwnd not in captured_handles
                    or self.runtime.settings.primary_handle != context.source_hwnd
                ):
                    self.runtime.logger.warning(
                        "%s annulé: liste des fenêtres modifiée pendant le clic.",
                        action_label,
                    )
                    return

                def mirror_roster_is_current() -> bool:
                    settings = self.runtime.settings
                    if settings is not settings_at_start:
                        return False
                    live_records = roster_signature(
                        getattr(settings, "clients", None)
                    )
                    if (live_records is None
                            or any(kind is not int for kind, _ in live_records)):
                        return False
                    live = tuple(hwnd for _, hwnd in live_records)
                    ordered = (
                        context.source_hwnd,
                        *(hwnd for hwnd in live if hwnd != context.source_hwnd),
                    )
                    return (
                        getattr(settings, "macro_mode", None) == "mirror"
                        and getattr(settings, "primary_handle", None) == context.source_hwnd
                        and len(live) == len(captured_handles)
                        and ordered == captured_handles
                    )

                if not mirror_roster_is_current():
                    self.runtime.logger.warning(
                        "%s annulé: liste des fenêtres changée après capture.",
                        action_label,
                    )
                    return
            # Targets existing in the roster do not prove that any window
            # was actually activated. Restore the favorite only after at
            # least one target has been confirmed in the foreground.
            if physical_source_delivered and not any(
                getattr(client, "handle", None) == context.source_hwnd
                for client in targets
            ):
                self.runtime.logger.warning(
                    "%s annulé: source physique absente des fenêtres.", action_label,
                )
                return

            if not targets:
                self.runtime.logger.info(
                    "%s ignore: aucune fenêtre Unity cible.",
                    action_label,
                )
                return
            if physical_source_delivered and len(targets) == 1:
                # The only client has already received native DOWN/UP. A
                # synthetic replay or favorite restoration would do nothing
                # useful and may steal focus from the user.
                should_restore_preferred = False
                original_cursor = None  # never reposition a cursor we did not move
                sent_count = 1
                self.runtime.logger.debug(
                    "%s: aucun destinataire secondaire, clic natif conservé.",
                    action_label,
                )
                return

            if (self.runtime.macro_lock.should_stop()
                    or self.runtime.settings is not settings_at_start):
                return
            # The roster scan above can yield to another foreground app.
            # A queued physical Miroir gesture must still belong to the
            # original favorite before we block the pointer or change focus.
            if (settings_at_dispatch is not None
                    and mirror_target_handles is not None
                    and exact_source_handle is not None):
                try:
                    if foreground_window() != exact_source_handle:
                        focus_lost = True
                        self.runtime.logger.warning(
                            "%s interrompu: source perdue pendant preflight.",
                            action_label,
                        )
                        return
                except Exception:
                    focus_lost = True
                    self.runtime.logger.exception(
                        "%s interrompu: source illisible après preflight.",
                        action_label,
                    )
                    return
            settings = settings_at_start
            timings = settings.timings
            # The physical source must finish its native UP before any
            # secondary receives a click. No cursor move or focus change
            # occurs during this cancellable 60 ms settle window: do NOT
            # swallow additional native clicks for this entire wait.
            if physical_source_delivered and self.runtime.macro_lock.wait(60):
                return
            # A Stop or in-place roster change during the native settle wait
            # must not take a mouse lease merely to abort the replay.
            if self.runtime.macro_lock.should_stop() or not target_roster_intact():
                return
            # The pointer remained native during source settle. If the user
            # switched to another app in that interval, do not take a mouse
            # lease or pull foreground back into the old DOFUS gesture.
            if (physical_source_delivered and mirror_target_handles is not None
                    and exact_source_handle is not None):
                try:
                    if foreground_window() != exact_source_handle:
                        focus_lost = True
                        self.runtime.logger.info(
                            "%s annulé: source perdue durant attente native.", action_label,
                        )
                        return
                except Exception:
                    focus_lost = True
                    self.runtime.logger.exception(
                        "%s annulé: focus illisible après attente native.", action_label,
                    )
                    return
            if not mouse_blocked:
                # Own the pointer only for actual client activation/sending
                # and restoration; the shared native hook stays unchanged.
                self.runtime.input_state.begin_mouse_block(action_label)
                mouse_blocked = True
                mouse_block_started_at = perf_counter()
            self.runtime.logger.debug(
                "%s souris physique bloquée pendant diffusion.", action_label,
            )

            for index, (client, target_hwnd) in enumerate(zip(targets, frozen_handles)):
                if pointer_interrupted():
                    delivery_failed = True
                    self.runtime.logger.warning(
                        "%s interrompu: geste physique reçu pendant blocage souris.",
                        action_label,
                    )
                    return
                if not target_roster_intact():
                    delivery_failed = True
                    self.runtime.logger.warning(
                        "%s interrompu: session modifiée avant clic hwnd=%s",
                        action_label, target_hwnd,
                    )
                    return
                if physical_source_delivered and target_hwnd == context.source_hwnd:
                    sent_count += 1  # native UP was forwarded; never inject twice
                    continue
                if (self.runtime.macro_lock.should_stop()
                        or self.runtime.settings is not settings_at_start):
                    self.runtime.logger.info(
                        "%s stoppé ou profil remplacé avant hwnd=%s",
                        action_label,
                        target_hwnd,
                    )
                    return
                if mirror_target_handles is not None and not mirror_roster_is_current():
                    delivery_failed = True
                    self.runtime.logger.warning(
                        "%s interrompu: roster changé avant clic hwnd=%s",
                        action_label, target_hwnd,
                    )
                    return

                if (type(target_hwnd) is not int
                        or not 0 < target_hwnd <= (2**64 - 1)
                        or not is_unity_window(target_hwnd)
                        or not is_dofus_unity_process(target_hwnd)):
                    self.runtime.logger.info(
                        "%s fenêtre introuvable/non Unity: hwnd=%s",
                        action_label,
                        target_hwnd,
                    )
                    if mirror_target_handles is not None:
                        # An already consumed source click must not trigger a
                        # continuation across a missing/replaced Unity target.
                        delivery_failed = True
                        return
                    continue
                if not target_roster_intact():
                    delivery_failed = True
                    return

                focus_started_at = perf_counter() if mirror_started_at is not None else None
                try:
                    activated = activate_window(
                        target_hwnd,
                        timings.switch_background_pre_click_ms,
                        timings.activate_attempts,
                        timings.activate_retry_ms,
                        self.runtime.logger,
                        action_label,
                        should_stop=lambda: (
                            self.runtime.macro_lock.should_stop()
                            or pointer_interrupted()
                            or self.runtime.settings is not settings_at_start
                            or not target_roster_intact()
                        ),
                    )
                except Exception:
                    focus_lost = True
                    self.runtime.logger.exception(
                        "%s interrompu: exception focus hwnd=%s",
                        action_label, target_hwnd,
                    )
                    return
                finally:
                    if focus_started_at is not None:
                        mirror_focus_samples.append(
                            (perf_counter() - focus_started_at) * 1000.0
                        )
                if not activated:
                    if not target_roster_intact():
                        delivery_failed = True
                        self.runtime.logger.warning(
                            "%s interrompu: roster modifié pendant activation hwnd=%s",
                            action_label, target_hwnd,
                        )
                        return
                    self.runtime.logger.info(
                        "%s clic ignoré: activation échec hwnd=%s",
                        action_label, target_hwnd,
                    )
                    if mirror_target_handles is not None:
                        focus_lost = True
                        return
                    continue

                # A successful SetForegroundWindow attempt can become stale
                # before SendInput. Never click another application or client.
                if pointer_interrupted():
                    delivery_failed = True
                    self.runtime.logger.warning(
                        "%s interrompu: clic physique avant émission hwnd=%s",
                        action_label, target_hwnd,
                    )
                    return
                if not target_roster_intact():
                    delivery_failed = True
                    self.runtime.logger.warning(
                        "%s interrompu: roster modifié pendant activation hwnd=%s",
                        action_label, target_hwnd,
                    )
                    return
                if foreground_window() != int(target_hwnd):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "%s interrompu: focus perdu avant clic hwnd=%s",
                        action_label, target_hwnd,
                    )
                    return
                if mirror_target_handles is not None and not mirror_roster_is_current():
                    delivery_failed = True
                    self.runtime.logger.warning(
                        "%s interrompu: roster changé après focus hwnd=%s",
                        action_label, target_hwnd,
                    )
                    return
                should_restore_preferred = True
                last_activated_hwnd = int(target_hwnd)

                target = self._target_point(target_hwnd, context)
                if not target_roster_intact():
                    delivery_failed = True
                    self.runtime.logger.warning(
                        "%s interrompu: roster modifié pendant calcul clic hwnd=%s",
                        action_label, target_hwnd,
                    )
                    return
                if target is None:
                    self.runtime.logger.info(
                        "%s clic ignoré: point cible indisponible hwnd=%s",
                        action_label,
                        target_hwnd,
                    )
                    if mirror_target_handles is not None:
                        delivery_failed = True
                        return
                    continue

                if mirror_target_handles is not None:
                    # A changed Miroir roster is a hard refusal: never send
                    # to targets captured before a favorite/session change.
                    if not mirror_roster_is_current():
                        delivery_failed = True
                        self.runtime.logger.warning(
                            "%s interrompu: roster changé après calcul du point hwnd=%s",
                            action_label, target_hwnd,
                        )
                        return
                # Classic SwitchClick needs the same late process guard as
                # Miroir. A recycled HWND may still be a valid Unity window
                # while belonging to another game or application.
                if not is_dofus_unity_process(target_hwnd):
                    delivery_failed = True
                    self.runtime.logger.warning(
                        "%s interrompu: processus remplacé avant clic hwnd=%s",
                        action_label, target_hwnd,
                    )
                    return
                if (self.runtime.macro_lock.should_stop()
                        or not target_roster_intact()):
                    delivery_failed = True
                    return

                double_gap_ms = timings.input_double_gap_ms
                if click_count == 2:
                    double_gap_ms = max(double_gap_ms, 60)

                # World objects need hover and button-down time across Unity
                # frames; old 1ms synthetic clicks may miss them entirely.
                hover_settle_ms = max(50, timings.switch_background_pre_click_ms)
                press_hold_ms = max(35, timings.switch_click_down_ms)

                self.runtime.logger.debug(
                    "%s envoi clic: label=%s hwnd=%s button=%s "
                    "count=%s x=%s y=%s reason=%s",
                    action_label,
                    client.display_name,
                    target_hwnd,
                    button,
                    click_count,
                    target[0],
                    target[1],
                    context.reason,
                )

                # The canonical click sender checks this predicate during
                # hover, before each DOWN, between double-clicks and on UP.
                # Keep it in-memory: native process probes on every 10 ms
                # settle tick would scale poorly with eight Unity clients.
                def send_interrupted() -> bool:
                    if (self.runtime.macro_lock.should_stop()
                            or pointer_interrupted()
                            or not target_roster_intact()):
                        return True
                    return (
                        mirror_target_handles is not None
                        and not mirror_roster_is_current()
                    )

                send_started_at = perf_counter() if mirror_started_at is not None else None
                delivered = send_client_click(
                    target_hwnd,
                    target[0],
                    target[1],
                    button,
                    click_count,
                    press_hold_ms,
                    double_gap_ms,
                    hover_settle_ms,
                    timings.switch_background_post_up_ms,
                    self.runtime.synthetic_guard,
                    self.runtime.logger,
                    should_stop=send_interrupted,
                )
                if send_started_at is not None:
                    mirror_send_samples.append((perf_counter() - send_started_at) * 1000.0)
                if delivered:
                    sent_count += 1
                    if pointer_interrupted():
                        delivery_failed = True
                        self.runtime.logger.warning(
                            "%s interrompu: nouveau geste physique après clic hwnd=%s",
                            action_label, target_hwnd,
                        )
                        return
                    if mirror_started_at is not None:
                        last_emission_at = perf_counter()
                    if not target_roster_intact():
                        delivery_failed = True
                        self.runtime.logger.warning(
                            "%s interrompu: roster modifié après clic hwnd=%s",
                            action_label, target_hwnd,
                        )
                        return
                else:
                    if pointer_interrupted():
                        delivery_failed = True
                        self.runtime.logger.warning(
                            "%s interrompu: nouveau geste physique pendant clic hwnd=%s",
                            action_label, target_hwnd,
                        )
                    elif (self.runtime.macro_lock.should_stop()
                            or self.runtime.settings is not settings_at_start):
                        self.runtime.logger.info(
                            "%s clic interrompu par Stop ou rechargement hwnd=%s",
                            action_label, target_hwnd,
                        )
                    elif not target_roster_intact():
                        delivery_failed = True
                        self.runtime.logger.warning(
                            "%s interrompu: roster modifié pendant clic hwnd=%s",
                            action_label, target_hwnd,
                        )
                    elif (
                        mirror_target_handles is not None
                        and not mirror_roster_is_current()
                    ):
                        delivery_failed = True
                        self.runtime.logger.warning(
                            "%s interrompu: roster changé pendant clic hwnd=%s",
                            action_label, target_hwnd,
                        )
                    elif foreground_window() != int(target_hwnd):
                        # A stolen focus may have caused the sender to refuse.
                        focus_lost = True
                        self.runtime.logger.warning(
                            "%s interrompu: focus perdu pendant clic hwnd=%s",
                            action_label, target_hwnd,
                        )
                    else:
                        # Never broadcast subsequent clicks after Windows
                        # refused one, and never report an apparent success.
                        delivery_failed = True
                        self.runtime.logger.warning(
                            "%s interrompu: SendInput clic refusé hwnd=%s",
                            action_label, target_hwnd,
                        )
                    return

                if (index < len(targets) - 1
                        and timings.switch_client_settle_ms > 0):
                    # A physical DOWN/wheel during an active Miroir pointer
                    # lease cancels the inter-client wait within the 25ms
                    # stop-event slice. Classic SwitchClick stays unchanged.
                    if mirror_target_handles is not None:
                        interrupted_wait = self.runtime.macro_lock.wait(
                            timings.switch_client_settle_ms,
                            interrupted=pointer_interrupted,
                        )
                    else:
                        interrupted_wait = self.runtime.macro_lock.wait(
                            timings.switch_client_settle_ms,
                        )
                    if interrupted_wait:
                        return
        finally:
            # Retain the collision result even after releasing InputState's
            # lease (which deliberately clears the interruption latch).
            pointer_collision = pointer_interrupted()
            try:
                # Emergency Stop must never be followed by a late cursor or
                # favorite restoration from a worker that is winding down.
                # The user may already have selected another application.
                restore_after_worker = (
                    should_restore_preferred and not focus_lost
                    and not delivery_failed and not pointer_interrupted()
                    and not self.runtime.macro_lock.should_stop()
                    and self.runtime.settings is settings_at_start
                )

                def roster_allows_restore() -> bool:
                    if not target_roster_intact():
                        return False
                    if mirror_target_handles is None:
                        return True
                    try:
                        return mirror_roster_is_current()
                    except Exception:
                        self.runtime.logger.exception(
                            "%s: roster illisible avant restauration.", action_label,
                        )
                        return False

                if restore_after_worker and not roster_allows_restore():
                    restore_after_worker = False
                    self.runtime.logger.info(
                        "%s: restauration ignorée, favori ou roster changé.",
                        action_label,
                    )
                if (
                    restore_after_worker
                    and mirror_target_handles is not None
                    and last_activated_hwnd is not None
                ):
                    # A user may switch to another app after the last successful
                    # SendInput. Never move their pointer or pull DOFUS back on
                    # top just because the sends themselves completed.
                    try:
                        if foreground_window() != last_activated_hwnd:
                            restore_after_worker = False
                            self.runtime.logger.info(
                                "%s: restauration ignorée, focus utilisateur changé.",
                                action_label,
                            )
                    except Exception:
                        restore_after_worker = False
                        self.runtime.logger.exception(
                            "%s: focus non vérifiable avant restauration.",
                            action_label,
                        )
                # Cleanup focus probes may yield to the Stop hotkey after the
                # initial restore decision. Never move the physical pointer on
                # the basis of an obsolete pre-Stop snapshot.
                if (original_cursor is not None and restore_after_worker
                        and not self.runtime.macro_lock.should_stop()
                        and not pointer_interrupted()):
                    try:
                        set_cursor_pos(*original_cursor)
                        # Cursor restoration may invoke native hooks and change
                        # the foreground. Never steal another app's focus.
                        if (
                            mirror_target_handles is not None
                            and last_activated_hwnd is not None
                            and foreground_window() != last_activated_hwnd
                        ):
                            restore_after_worker = False
                            self.runtime.logger.info(
                                "%s: retour au favori ignoré, focus changé après curseur.",
                                action_label,
                            )
                    except Exception:
                        if mirror_target_handles is not None:
                            restore_after_worker = False
                        self.runtime.logger.exception(
                            "%s restauration curseur impossible.",
                            action_label,
                        )

                # The cursor restore can yield to the Organizer profile reload
                # on the UI thread. Do not activate a newly selected favorite.
                if restore_after_worker and not roster_allows_restore():
                    restore_after_worker = False
                    self.runtime.logger.info(
                        "%s: retour au favori ignoré, roster changé après curseur.",
                        action_label,
                    )

                # The last foreground probe can itself yield to Emergency Stop.
                # Never restore a favorite on a stale decision even if the
                # previous check passed before Stop arrived.
                if (restore_after_worker
                        and not self.runtime.macro_lock.should_stop()
                        and not pointer_interrupted()
                        and self.runtime.settings is settings_at_start
                        and target_roster_intact()):
                    try:
                        self.runtime.switch_character.restore_preferred_client(
                            action_label
                        )
                    except Exception:
                        self.runtime.logger.exception(
                            "%s retour au favori impossible.",
                            action_label,
                        )

            finally:
                if mouse_blocked:
                    # Cleanup is unconditional, even if a diagnostic or
                    # favorite/foreground restoration callback raises.
                    try:
                        pointer_collision = pointer_collision or pointer_interrupted()
                    finally:
                        remaining_blocks = self.runtime.input_state.end_mouse_block()
                    self.runtime.logger.debug(
                        "%s souris physique débloquée: remaining=%s",
                        action_label,
                        remaining_blocks,
                    )
                    if mouse_block_started_at is not None:
                        self.runtime.logger.info(
                            "%s blocage_souris_ms=%.2f cibles=%s",
                            action_label,
                            (perf_counter() - mouse_block_started_at) * 1000.0,
                            target_total,
                        )

            if mirror_started_at is not None:
                from app.macros.mirror_plan import mirror_latency_percentiles_ms

                quantiles = mirror_latency_percentiles_ms(mirror_send_samples)
                focus_quantiles = mirror_latency_percentiles_ms(mirror_focus_samples)
                self.runtime.logger.info(
                    "Miroir mesures focus_activation_ms=%s",
                    focus_quantiles if focus_quantiles is not None else "NOT_MEASURED",
                )
                elapsed_ms = round((perf_counter() - mirror_started_at) * 1000.0, 2)
                if dispatch_at is not None:
                    self.runtime.logger.info(
                        "Miroir clic dispatch_to_worker_ms=%.2f "
                        "dispatch_to_last_emit_ms=%s cibles=%s (envoi, pas rendu Unity)",
                        max(0.0, (mirror_started_at - dispatch_at) * 1000.0),
                        (f"{max(0.0, (last_emission_at - dispatch_at) * 1000.0):.2f}"
                         if last_emission_at is not None else "NOT_MEASURED"),
                        target_total,
                    )
                if quantiles is None:
                    self.runtime.logger.info(
                        "Miroir mesures: n=0 total_ms=%s envoyés=%s/%s",
                        elapsed_ms, sent_count, target_total,
                    )
                else:
                    self.runtime.logger.info(
                        "Miroir mesures delivery_step: n=%s p50_ms=%s p95_ms=%s "
                        "p99_ms=%s total_ms=%s envoyés=%s/%s",
                        quantiles["n"], quantiles["p50"], quantiles["p95"],
                        quantiles["p99"], elapsed_ms, sent_count, target_total,
                    )

            if target_total > 0:
                stopped = self.runtime.macro_lock.should_stop()
                state = (
                    "interrompu" if (stopped or focus_lost or pointer_collision
                                     or not target_roster_intact())
                    else "terminé" if sent_count == target_total
                    else "partiel"
                )
                self.runtime.logger.info(
                    "%s %s: envoyés=%s/%s",
                    action_label, state, sent_count, target_total,
                )
                if mirror_started_at is not None:
                    label = (
                        "Miroir interrompu" if state == "interrompu"
                        else "Miroir incomplet" if state == "partiel"
                        else "Miroir"
                    )
                    suffix = (
                        " (geste physique non rejoué)" if pointer_collision else ""
                    )
                    self.runtime._emit_status(
                        f"{label} : {sent_count}/{target_total} fenêtres{suffix}."
                    )

    def _capture_trigger_context(
        self,
        screen_x: int,
        screen_y: int,
        action_label: str,
    ) -> SwitchClickContext | None:
        settings = self.runtime.settings
        handles = tuple(client.handle for client in settings.clients)
        mode_at_start = settings.macro_mode
        favorite_at_start = settings.primary_handle

        def capture_is_current() -> bool:
            # No extra Win32 probes on the low-level hook: just compare the
            # in-memory 2-8 roster used for the original physical DOWN.
            return (
                self.runtime.settings is settings
                and settings.macro_mode == mode_at_start
                and settings.primary_handle == favorite_at_start
                and tuple(client.handle for client in settings.clients) == handles
            )

        source_hwnd = find_known_client_from_point(
            screen_x,
            screen_y,
            handles,
        )
        if not capture_is_current():
            self.runtime.logger.info(
                "%s capture annulée: roster Organizer modifié pendant hit-test.",
                action_label,
            )
            return None
        if source_hwnd and is_unity_window(source_hwnd):
            if not capture_is_current():
                return None
            point = screen_to_client(source_hwnd, screen_x, screen_y)
            if point is not None:
                x, y = clamp_client_point(
                    source_hwnd,
                    point[0],
                    point[1],
                )
                ratio = client_point_ratio(source_hwnd, x, y)
                x_ratio = ratio[0] if ratio else None
                y_ratio = ratio[1] if ratio else None
                if not capture_is_current():
                    self.runtime.logger.info(
                        "%s capture annulée: roster Organizer modifié pendant point.",
                        action_label,
                    )
                    return None

                self.runtime.last_client_point.hwnd = source_hwnd
                self.runtime.last_client_point.x = x
                self.runtime.last_client_point.y = y
                self.runtime.last_client_point.x_ratio = x_ratio
                self.runtime.last_client_point.y_ratio = y_ratio
                self.runtime.last_client_point.valid = True
                self.runtime.active_client_handle = source_hwnd

                self.runtime.logger.debug(
                    "%s contexte clic Unity: source=%s client=%s,%s "
                    "ratio=%s",
                    action_label,
                    source_hwnd,
                    x,
                    y,
                    ratio,
                )
                return SwitchClickContext(
                    source_hwnd=source_hwnd,
                    client_x=x,
                    client_y=y,
                    x_ratio=x_ratio,
                    y_ratio=y_ratio,
                    reason="cursor",
                )

        if not capture_is_current():
            return None
        preferred = self.runtime.switch_character.preferred_client()
        if preferred is None or not capture_is_current():
            return None

        last = self.runtime.last_client_point
        if last.valid:
            self.runtime.logger.debug(
                "%s fallback favori avec dernier point: hwnd=%s "
                "ancien_hwnd=%s",
                action_label,
                preferred.handle,
                last.hwnd,
            )
            return SwitchClickContext(
                source_hwnd=preferred.handle,
                client_x=last.x,
                client_y=last.y,
                x_ratio=last.x_ratio,
                y_ratio=last.y_ratio,
                reason="preferred_last_client_point",
            )

        self.runtime.logger.debug(
            "%s fallback favori sans point mémorisé: hwnd=%s centre",
            action_label,
            preferred.handle,
        )
        return SwitchClickContext(
            source_hwnd=preferred.handle,
            client_x=None,
            client_y=None,
            x_ratio=None,
            y_ratio=None,
            reason="preferred_center",
        )

    def _validated_context(
        self,
        context: SwitchClickContext,
        action_label: str,
    ) -> SwitchClickContext | None:
        settings = self.runtime.settings
        source = settings.client_by_handle(context.source_hwnd)

        if source is not None and is_unity_window(source.handle):
            return context

        preferred = self.runtime.switch_character.preferred_client()
        if preferred is None:
            return None

        self.runtime.logger.debug(
            "%s source remplacée par le favori: ancienne=%s nouvelle=%s",
            action_label,
            context.source_hwnd,
            preferred.handle,
        )
        return SwitchClickContext(
            source_hwnd=preferred.handle,
            client_x=context.client_x,
            client_y=context.client_y,
            x_ratio=context.x_ratio,
            y_ratio=context.y_ratio,
            reason=f"{context.reason}_recovered",
        )

    def _target_point(
        self,
        hwnd: int,
        context: SwitchClickContext,
    ) -> tuple[int, int] | None:
        if context.x_ratio is not None and context.y_ratio is not None:
            point = client_point_from_ratio(
                hwnd,
                context.x_ratio,
                context.y_ratio,
            )
            if point is not None:
                return point

        if context.client_x is not None and context.client_y is not None:
            return clamp_client_point(
                hwnd,
                context.client_x,
                context.client_y,
            )

        return client_center(hwnd)
