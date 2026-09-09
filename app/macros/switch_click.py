from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.windows.clicks import current_cursor_pos, send_client_click, set_cursor_pos
from app.windows.focus import activate_window
from app.windows.unity_windows import (
    clamp_client_point,
    client_center,
    client_point_from_ratio,
    client_point_ratio,
    find_known_client_from_point,
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
        context = self._capture_trigger_context(
            screen_x,
            screen_y,
            action_label,
        )
        if context is None:
            self.runtime.logger.info(
                "%s ignore: aucune fenêtre Unity source ou favorite.",
                action_label,
            )
            return False

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
    ) -> None:
        original_cursor: tuple[int, int] | None = None
        sent_count = 0
        target_total = 0
        mouse_blocked = mouse_block_started
        should_restore_preferred = False

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
            if context is None:
                self.runtime.logger.info(
                    "%s ignore: fenêtre Unity source indisponible.",
                    action_label,
                )
                return

            targets = self.runtime.switch_character.ordered_clients_from_source(
                context.source_hwnd
            )
            target_total = len(targets)
            should_restore_preferred = bool(targets)

            if not targets:
                self.runtime.logger.info(
                    "%s ignore: aucune fenêtre Unity cible.",
                    action_label,
                )
                return

            settings = self.runtime.settings
            timings = settings.timings

            for index, client in enumerate(targets):
                if self.runtime.macro_lock.should_stop():
                    self.runtime.logger.info(
                        "%s stoppé avant hwnd=%s",
                        action_label,
                        client.handle,
                    )
                    return

                if not is_unity_window(client.handle):
                    self.runtime.logger.info(
                        "%s fenêtre introuvable/non Unity: hwnd=%s",
                        action_label,
                        client.handle,
                    )
                    continue

                if not activate_window(
                    client.handle,
                    timings.switch_background_pre_click_ms,
                    timings.activate_attempts,
                    timings.activate_retry_ms,
                    self.runtime.logger,
                    action_label,
                    should_stop=self.runtime.macro_lock.should_stop,
                ):
                    self.runtime.logger.info(
                        "%s clic ignoré: activation échec hwnd=%s",
                        action_label,
                        client.handle,
                    )
                    continue

                target = self._target_point(client.handle, context)
                if target is None:
                    self.runtime.logger.info(
                        "%s clic ignoré: point cible indisponible hwnd=%s",
                        action_label,
                        client.handle,
                    )
                    continue

                double_gap_ms = timings.input_double_gap_ms
                if click_count == 2:
                    double_gap_ms = max(double_gap_ms, 60)

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

                if send_client_click(
                    client.handle,
                    target[0],
                    target[1],
                    button,
                    click_count,
                    timings.switch_click_down_ms,
                    double_gap_ms,
                    0,
                    timings.switch_background_post_up_ms,
                    self.runtime.synthetic_guard,
                    self.runtime.logger,
                    should_stop=self.runtime.macro_lock.should_stop,
                ):
                    sent_count += 1

                if (
                    index < len(targets) - 1
                    and timings.switch_client_settle_ms > 0
                    and self.runtime.macro_lock.wait(
                        timings.switch_client_settle_ms
                    )
                ):
                    return
        finally:
            if original_cursor is not None:
                try:
                    set_cursor_pos(*original_cursor)
                except Exception:
                    self.runtime.logger.exception(
                        "%s restauration curseur impossible.",
                        action_label,
                    )

            if should_restore_preferred:
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

            if target_total > 0:
                self.runtime.logger.info(
                    "%s terminé: envoyés=%s/%s",
                    action_label,
                    sent_count,
                    target_total,
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
