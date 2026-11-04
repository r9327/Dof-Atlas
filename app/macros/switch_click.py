from __future__ import annotations

from dataclasses import dataclass
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
    ) -> bool:
        normalized_button = str(button or "").strip().casefold()
        if normalized_button not in {"left", "right"}:
            self.runtime.logger.warning(
                "%s ignore: bouton invalide=%r",
                action_label,
                button,
            )
            return False

        try:
            screen_x = int(screen_x)
            screen_y = int(screen_y)
        except (TypeError, ValueError):
            self.runtime.logger.warning(
                "%s ignore: position souris invalide x=%r y=%r",
                action_label,
                screen_x,
                screen_y,
            )
            return False

        try:
            requested_count = int(click_count)
        except (TypeError, ValueError):
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
        if context is None:
            self.runtime.logger.info(
                "%s ignore: aucune fenêtre Unity source ou favorite.",
                action_label,
            )
            return False

        # A native DOWN/UP already reached the only registered character.
        # Do not create a macro worker or block physical input for a no-op.
        if (physical_source_delivered and exact_source_handle is None
                and mirror_target_handles is None):
            handles = tuple(client.handle for client in self.runtime.settings.clients)
            if handles == (context.source_hwnd,):
                self.runtime.logger.debug(
                    "%s: source physique seule, aucune réinjection nécessaire.",
                    action_label,
                )
                return True

        self.runtime.input_state.begin_mouse_block(action_label)
        try:
            started = self.runtime._spawn_macro(
                action_label,
                lambda: self._run(
                    button_name,
                    click_count,
                    action_label,
                    context,
                    mouse_block_started=True,
                    exact_source_handle=exact_source_handle,
                    mirror_target_handles=mirror_target_handles,
                    physical_source_delivered=physical_source_delivered,
                ),
            )
        except Exception:
            self.runtime.input_state.end_mouse_block()
            raise

        if not started:
            self.runtime.input_state.end_mouse_block()
        return started

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
    ) -> None:
        original_cursor: tuple[int, int] | None = None
        sent_count = 0
        target_total = 0
        mouse_blocked = mouse_block_started
        should_restore_preferred = False
        focus_lost = False
        delivery_failed = False
        mirror_started_at = perf_counter() if action_label == "Miroir" else None
        mirror_send_samples: list[float] = []
        mirror_focus_samples: list[float] = []

        try:
            try:
                original_cursor = current_cursor_pos()
            except Exception:
                self.runtime.logger.exception(
                    "%s lecture position curseur impossible.",
                    action_label,
                )

            if not mouse_blocked:
                self.runtime.input_state.begin_mouse_block(action_label)
                mouse_blocked = True

            self.runtime.logger.debug(
                "%s souris physique bloquée pendant la boucle.",
                action_label,
            )

            context = self._validated_context(context, action_label)
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

            targets = self.runtime.switch_character.ordered_clients_from_source(
                context.source_hwnd
            )
            target_total = len(targets)
            if mirror_target_handles is not None:
                # Never fan out to a client that appeared after the physical
                # click, or to a different favorite during an active gesture.
                actual_handles = tuple(client.handle for client in targets)
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
                    live = tuple(client.handle for client in settings.clients)
                    ordered = (
                        context.source_hwnd,
                        *(hwnd for hwnd in live if hwnd != context.source_hwnd),
                    )
                    return (
                        settings.macro_mode == "mirror"
                        and settings.primary_handle == context.source_hwnd
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
                client.handle == context.source_hwnd for client in targets
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

            settings = self.runtime.settings
            timings = settings.timings
            # Give the native mouse UP a render frame before switching focus
            # to another Unity client. This wait is cancellable by Stop.
            if physical_source_delivered and self.runtime.macro_lock.wait(60):
                return

            for index, client in enumerate(targets):
                if physical_source_delivered and client.handle == context.source_hwnd:
                    sent_count += 1  # native UP was forwarded; never inject twice
                    continue
                if self.runtime.macro_lock.should_stop():
                    self.runtime.logger.info(
                        "%s stoppé avant hwnd=%s",
                        action_label,
                        client.handle,
                    )
                    return
                if mirror_target_handles is not None and not mirror_roster_is_current():
                    delivery_failed = True
                    self.runtime.logger.warning(
                        "%s interrompu: roster changé avant clic hwnd=%s",
                        action_label, client.handle,
                    )
                    return

                if (not is_unity_window(client.handle)
                        or (mirror_target_handles is not None
                            and not is_dofus_unity_process(client.handle))):
                    self.runtime.logger.info(
                        "%s fenêtre introuvable/non Unity: hwnd=%s",
                        action_label,
                        client.handle,
                    )
                    if mirror_target_handles is not None:
                        # An already consumed source click must not trigger a
                        # continuation across a missing/replaced Unity target.
                        delivery_failed = True
                        return
                    continue

                focus_started_at = perf_counter() if mirror_started_at is not None else None
                try:
                    activated = activate_window(
                        client.handle,
                        timings.switch_background_pre_click_ms,
                        timings.activate_attempts,
                        timings.activate_retry_ms,
                        self.runtime.logger,
                        action_label,
                        should_stop=self.runtime.macro_lock.should_stop,
                    )
                except Exception:
                    focus_lost = True
                    self.runtime.logger.exception(
                        "%s interrompu: exception focus hwnd=%s",
                        action_label, client.handle,
                    )
                    return
                finally:
                    if focus_started_at is not None:
                        mirror_focus_samples.append(
                            (perf_counter() - focus_started_at) * 1000.0
                        )
                if not activated:
                    self.runtime.logger.info(
                        "%s clic ignoré: activation échec hwnd=%s",
                        action_label, client.handle,
                    )
                    if mirror_target_handles is not None:
                        focus_lost = True
                        return
                    continue

                # A successful SetForegroundWindow attempt can become stale
                # before SendInput. Never click another application or client.
                if foreground_window() != int(client.handle):
                    focus_lost = True
                    self.runtime.logger.warning(
                        "%s interrompu: focus perdu avant clic hwnd=%s",
                        action_label, client.handle,
                    )
                    return
                if mirror_target_handles is not None and not mirror_roster_is_current():
                    delivery_failed = True
                    self.runtime.logger.warning(
                        "%s interrompu: roster changé après focus hwnd=%s",
                        action_label, client.handle,
                    )
                    return
                should_restore_preferred = True

                target = self._target_point(client.handle, context)
                if target is None:
                    self.runtime.logger.info(
                        "%s clic ignoré: point cible indisponible hwnd=%s",
                        action_label,
                        client.handle,
                    )
                    if mirror_target_handles is not None:
                        delivery_failed = True
                        return
                    continue

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
                    client.handle,
                    button,
                    click_count,
                    target[0],
                    target[1],
                    context.reason,
                )

                send_started_at = perf_counter() if mirror_started_at is not None else None
                delivered = send_client_click(
                    client.handle,
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
                    should_stop=self.runtime.macro_lock.should_stop,
                )
                if send_started_at is not None:
                    mirror_send_samples.append((perf_counter() - send_started_at) * 1000.0)
                if delivered:
                    sent_count += 1
                else:
                    if foreground_window() != int(client.handle):
                        # A stolen focus may have caused the sender to refuse.
                        focus_lost = True
                        self.runtime.logger.warning(
                            "%s interrompu: focus perdu pendant clic hwnd=%s",
                            action_label, client.handle,
                        )
                    else:
                        # Never broadcast subsequent clicks after Windows
                        # refused one, and never report an apparent success.
                        delivery_failed = True
                        self.runtime.logger.warning(
                            "%s interrompu: SendInput clic refusé hwnd=%s",
                            action_label, client.handle,
                        )
                    return

                if (
                    index < len(targets) - 1
                    and timings.switch_client_settle_ms > 0
                    and self.runtime.macro_lock.wait(
                        timings.switch_client_settle_ms
                    )
                ):
                    return
        finally:
            # Emergency Stop must never be followed by a late cursor or
            # favorite restoration from a worker that is winding down.
            # The user may already have selected another application.
            restore_after_worker = (
                should_restore_preferred and not focus_lost
                and not delivery_failed
                and not self.runtime.macro_lock.should_stop()
            )
            if original_cursor is not None and restore_after_worker:
                try:
                    set_cursor_pos(*original_cursor)
                except Exception:
                    self.runtime.logger.exception(
                        "%s restauration curseur impossible.",
                        action_label,
                    )

            # The user may have deliberately changed foreground window.
            # Never steal it back during an aborted gesture.
            if restore_after_worker:
                try:
                    self.runtime.switch_character.restore_preferred_client(
                        action_label
                    )
                except Exception:
                    self.runtime.logger.exception(
                        "%s retour au favori impossible.",
                        action_label,
                    )

            if mouse_blocked:
                remaining_blocks = self.runtime.input_state.end_mouse_block()
                self.runtime.logger.debug(
                    "%s souris physique débloquée: remaining=%s",
                    action_label,
                    remaining_blocks,
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
                    "interrompu" if stopped or focus_lost
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
                    self.runtime._emit_status(
                        f"{label} : {sent_count}/{target_total} fenêtres."
                    )

    def _capture_trigger_context(
        self,
        screen_x: int,
        screen_y: int,
        action_label: str,
    ) -> SwitchClickContext | None:
        settings = self.runtime.settings
        handles = [client.handle for client in settings.clients]

        source_hwnd = find_known_client_from_point(
            screen_x,
            screen_y,
            handles,
        )
        if source_hwnd and is_unity_window(source_hwnd):
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

        preferred = self.runtime.switch_character.preferred_client()
        if preferred is None:
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
