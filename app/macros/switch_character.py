from __future__ import annotations

from typing import TYPE_CHECKING

from app.macros.mirror_plan import is_dofus_unity_process
from app.windows.focus import activate_window
from app.windows.unity_windows import foreground_window, is_unity_window

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime
    from app.core.settings import AtlasClient


class SwitchCharacterMacro:
    def __init__(self, runtime: "AtlasRuntime"):
        self.runtime = runtime

    def activate_by_index(
        self, client_index: int, *, expected_profile: object | None = None,
        expected_context: tuple[object, object] | None = None,
    ) -> bool:
        settings = self.runtime.settings
        if settings is None:
            return False
        favorite_at_dispatch = settings.primary_handle
        mode_at_dispatch = settings.macro_mode
        if (expected_context is not None
                and (favorite_at_dispatch, mode_at_dispatch) != expected_context):
            self.runtime.logger.info(
                "Activation client annulée: contexte favori/mode modifié avant dispatch."
            )
            return False
        # A "next" selection may be calculated while native process probes
        # yield to a profile reload. Never route an old slot into a replacement.
        if expected_profile is not None and settings is not expected_profile:
            self.runtime.logger.info(
                "Activation client annulée: profil Organizer remplacé avant dispatch.",
            )
            return False
        # Numeric strings from older profiles remain supported, but do not
        # truncate other number-like objects into a different character slot.
        if type(client_index) not in (int, str):
            self.runtime.logger.info("Activation client ignorée: index invalide=%r", client_index)
            return False
        try:
            requested_index = int(client_index)
        except (TypeError, ValueError, OverflowError):
            self.runtime.logger.info("Activation client ignorée: index invalide=%r", client_index)
            return False
        # A corrupt slot stored as True or 1.0 compares equal to integer 1.
        # Such a client must not hijack a healthy slot's native hotkey.
        if not 1 <= requested_index <= 8:
            self.runtime.logger.info("Activation client ignorée: slot hors limites=%s", requested_index)
            return False
        target = next(
            (client for client in settings.clients
             if type(client.index) is int and client.index == requested_index),
            None,
        )
        if target is None:
            self.runtime.logger.info("Activation client ignoree: index introuvable=%s", client_index)
            return False
        # Direct client hotkeys must use actual Win32 HWNDs. The lower-level
        # Unity helper casts numbers, so reject fractional/bool aliases here
        # before reserving MacroLock or starting a worker.
        if (type(target.handle) is not int
                or not 0 < target.handle <= (2**64 - 1)):
            self.runtime.logger.info(
                "Activation client ignorée: HWND invalide index=%s", requested_index,
            )
            return False

        # Freeze the actual HWND/index pair accepted by the native hotkey.
        # Organizer may mutate an existing client object in place without
        # replacing its container, so comparing it to itself is not a guard.
        target_index = target.index
        target_handle = target.handle
        target_name = target.display_name

        def run() -> None:
            # Hotkey callbacks are asynchronous: a slot can be reassigned
            # before this worker receives its turn. Never activate a stale
            # HWND merely because it still belongs to a DOFUS process.
            def target_is_current() -> bool:
                # A new settings object is a new Organizer generation even
                # when the same slot/handle were reloaded from disk.
                return (
                    self.runtime.settings is settings
                    and settings.primary_handle == favorite_at_dispatch
                    and settings.macro_mode == mode_at_dispatch
                    and any(
                        type(client.index) is int and client.index == target_index
                        and type(client.handle) is int and client.handle == target_handle
                        for client in settings.clients
                    )
                )

            if not target_is_current():
                self.runtime.logger.info(
                    "Activation client annulée: slot modifié index=%s", target_index,
                )
                return
            if not is_unity_window(target_handle) or not is_dofus_unity_process(target_handle):
                self.runtime.logger.info(
                    "Activation client ignoree: cible non DOFUS Unity label=%s hwnd=%s",
                    target_name,
                    target_handle,
                )
                return
            # Native identity checks may release the GIL. Abort before ANY
            # focus change if a newer profile replaced this queued activation.
            if not target_is_current() or self.runtime.macro_lock.should_stop():
                self.runtime.logger.info(
                    "Activation client annulée: profil ou Stop changé après contrôle natif.",
                )
                return
            if activate_window(
                target_handle,
                settings.timings.click_focus_settle_ms,
                settings.timings.activate_attempts,
                settings.timings.activate_retry_ms,
                self.runtime.logger,
                "Activation client",
                should_stop=lambda: (
                    self.runtime.macro_lock.should_stop()
                    or not target_is_current()
                ),
            ):
                # Activation success is not enough: the slot may have been
                # reassigned, or Stop/focus theft may have arrived in the meantime.
                if self.runtime.macro_lock.should_stop():
                    return
                if not target_is_current():
                    self.runtime.logger.info(
                        "Activation client non publiée: slot modifié index=%s", target_index,
                    )
                    return
                if (not is_dofus_unity_process(target_handle)
                        or foreground_window() != int(target_handle)):
                    self.runtime.logger.warning(
                        "Activation client ignoree: identite ou focus non confirme hwnd=%s",
                        target_handle,
                    )
                    return
                # Either Win32 call can yield to a profile reload/Stop. Never
                # publish a stale HWND after the final native identity probe.
                if self.runtime.macro_lock.should_stop() or not target_is_current():
                    self.runtime.logger.info(
                        "Activation client non publiée: profil ou Stop changé après contrôle final.",
                    )
                    return
                self.runtime.active_client_handle = target_handle
                self.runtime.logger.info(
                    "Activation par raccourci client: label=%s hwnd=%s",
                    target_name,
                    target_handle,
                )

        # An in-place preference edit during hotkey resolution must not
        # reserve a worker for an obsolete Organizer generation.
        if (self.runtime.settings is not settings
                or settings.primary_handle != favorite_at_dispatch
                or settings.macro_mode != mode_at_dispatch):
            self.runtime.logger.info(
                "Activation client annulée: favori ou mode modifié avant worker."
            )
            return False
        return self.runtime._spawn_macro("Activation client", run)

    def activate_next(self, *, expected_profile: object | None = None, step: int = 1) -> bool:
        """Advance in live Organizer slot order, wrapping after the last.

        Each target still uses the canonical activation worker with its
        independent foreground, process and stale-slot checks.
        """
        if step not in (-1, 1) or self.runtime.macro_lock.should_stop():
            return False
        settings = self.runtime.settings
        if settings is None:
            return False
        favorite_at_dispatch = settings.primary_handle
        mode_at_dispatch = settings.macro_mode

        def context_current() -> bool:
            return (
                self.runtime.settings is settings
                and settings.primary_handle == favorite_at_dispatch
                and settings.macro_mode == mode_at_dispatch
            )

        if expected_profile is not None and settings is not expected_profile:
            self.runtime.logger.info(
                "Personnage suivant annulé: profil Organizer remplacé avant scan.",
            )
            return False
        clients = []
        accepted: list[tuple[object, int, int]] = []
        seen: set[int] = set()
        seen_slots: set[int] = set()

        def accepted_unchanged() -> bool:
            return all(
                type(item.index) is int and item.index == index
                and type(item.handle) is int and item.handle == hwnd
                for item, index, hwnd in accepted
            )

        for client in settings.clients:
            if not context_current():
                return False
            index, hwnd = client.index, client.handle
            # The eight Organizer slots are integer identities. Ignore bad
            # aliases without probing their HWNDs; two valid clients with
            # the same slot make the cycling order ambiguous.
            if type(index) is not int or not 1 <= index <= 8:
                continue
            if index in seen_slots:
                self.runtime.logger.warning(
                    "Personnage suivant annulé: slot Organizer dupliqué=%s", index,
                )
                return False
            if (type(hwnd) is not int or not 0 < hwnd <= (2**64 - 1)
                    or hwnd in seen or not is_unity_window(hwnd)
                    or not is_dofus_unity_process(hwnd)):
                continue
            # Another client may be reassigned during the Win32 check. Do
            # not create a "next character" action from a mixed generation.
            if (not context_current() or not accepted_unchanged()
                    or client.index != index or client.handle != hwnd):
                return False
            seen.add(hwnd)
            seen_slots.add(index)
            clients.append(client)
            accepted.append((client, index, hwnd))
        if (len(clients) < 2 or not context_current()
                or not accepted_unchanged()):
            return False
        current = self.logical_active_client()
        if (not context_current()
                or self.runtime.macro_lock.should_stop()
                or not accepted_unchanged()):
            return False
        current_hwnd = current.handle if current is not None else 0
        position = next(
            (i for i, (_item, _slot, hwnd) in enumerate(accepted)
             if hwnd == current_hwnd), -1,
        )
        chosen, index, hwnd = accepted[(position + step) % len(accepted)]
        if (type(chosen.index) is not int or chosen.index != index
                or type(chosen.handle) is not int or chosen.handle != hwnd
                or not accepted_unchanged()):
            return False
        if not context_current():
            return False
        return self.activate_by_index(
            index, expected_profile=settings,
            expected_context=(favorite_at_dispatch, mode_at_dispatch),
        )

    def activate_previous(self, *, expected_profile: object | None = None) -> bool:
        """Reverse in the same verified Organizer order as activate_next."""
        return self.activate_next(expected_profile=expected_profile, step=-1)

    def preferred_client(self) -> "AtlasClient | None":
        """
        Renvoie le personnage principal défini dans l'Organizer.

        AtlasSettings.preferred_client() gère déjà l'ordre suivant :
        primary_handle, client marqué primary, puis premier client configuré.
        """
        settings = self.runtime.settings
        if settings is None:
            return None
        favorite_at_start = settings.primary_handle
        mode_at_start = settings.macro_mode
        preferred = settings.preferred_client()
        if preferred is None:
            return None
        # Native process queries can release the GIL while an Organizer
        # preference changes in place. An old favorite is not authorized to
        # receive focus just because its HWND still belongs to DOFUS Unity.
        hwnd = preferred.handle
        if (type(hwnd) is not int
                or not 0 < hwnd <= (2**64 - 1)
                or not is_unity_window(hwnd)
                or not is_dofus_unity_process(hwnd)
                or self.runtime.settings is not settings
                or settings.primary_handle != favorite_at_start
                or settings.macro_mode != mode_at_start
                or preferred.handle != hwnd):
            return None
        # A changed primary flag can also reassign the preferred client
        # without changing the saved primary HWND (fallback profiles).
        return preferred if settings.preferred_client() is preferred else None

    def logical_active_client(self) -> "AtlasClient | None":
        settings = self.runtime.settings
        if settings is None:
            return None
        active = foreground_window()
        if (type(active) is int and 0 < active <= (2**64 - 1)
                and is_unity_window(active) and is_dofus_unity_process(active)):
            if self.runtime.settings is not settings:
                return None
            client = settings.client_by_handle(active)
            if client is not None:
                if (self.runtime.settings is not settings
                        or client.handle != active):
                    return None
                self.runtime.active_client_handle = active
                return client

        remembered = self.runtime.active_client_handle
        if type(remembered) is int and 0 < remembered <= (2**64 - 1):
            client = settings.client_by_handle(remembered)
            if (client is not None and client.handle == remembered
                    and is_unity_window(remembered)
                    and is_dofus_unity_process(remembered)):
                if (self.runtime.settings is not settings
                        or client.handle != remembered):
                    return None
                return client

        if self.runtime.settings is not settings:
            return None
        preferred = self.preferred_client()
        if self.runtime.settings is not settings:
            return None
        if preferred is not None:
            self.runtime.active_client_handle = preferred.handle
            return preferred

        for client in settings.clients:
            hwnd = client.handle
            if (type(hwnd) is int
                    and 0 < hwnd <= (2**64 - 1)
                    and is_unity_window(hwnd)
                    and is_dofus_unity_process(hwnd)):
                if (self.runtime.settings is not settings
                        or client.handle != hwnd):
                    return None
                self.runtime.active_client_handle = hwnd
                return client
        return None

    def ordered_clients_from_source(
        self,
        source_hwnd: int = 0,
    ) -> list["AtlasClient"]:
        settings_at_start = self.runtime.settings
        if settings_at_start is None:
            return []
        clients: list["AtlasClient"] = []
        accepted_hwnds: list[tuple["AtlasClient", int]] = []
        seen_handles: set[int] = set()

        def accepted_unchanged() -> bool:
            return all(client.handle == hwnd for client, hwnd in accepted_hwnds)

        for client in settings_at_start.clients:
            handle = client.handle
            if type(handle) is not int or not 0 < handle <= (2**64 - 1):
                self.runtime.logger.warning(
                    "Switch: fenetre ignoree (handle invalide) slot=%s",
                    client.index,
                )
                continue
            if (handle in seen_handles or not is_unity_window(handle)
                    or not is_dofus_unity_process(handle)):
                continue
            if (self.runtime.settings is not settings_at_start
                    or client.handle != handle or not accepted_unchanged()):
                self.runtime.logger.info(
                    "Switch: roster abandonné, session modifiée pendant scan.",
                )
                return []
            seen_handles.add(handle)
            clients.append(client)
            accepted_hwnds.append((client, handle))
        if (self.runtime.settings is not settings_at_start
                or not accepted_unchanged()):
            return []

        # A bad explicit Win32 source must not silently fall back to the
        # favorite. Never truncate fractional HWND aliases to an active
        # character; only the omitted/default zero requests a fallback.
        if source_hwnd is None:
            source_hwnd = 0
        if (type(source_hwnd) is not int
                or not 0 <= source_hwnd <= (2**64 - 1)):
            self.runtime.logger.warning(
                "Switch: source explicite invalide hwnd=%r", source_hwnd,
            )
            return []

        # A real, explicit source that disappeared from Organizer must not
        # silently turn into the logical favorite: that can broadcast a
        # physical gesture from an unregistered or replaced window.
        if source_hwnd > 0 and source_hwnd not in seen_handles:
            self.runtime.logger.warning(
                "Switch: source explicite absente du roster hwnd=%s", source_hwnd,
            )
            return []
        if source_hwnd not in seen_handles:
            source = self.logical_active_client()
            source_hwnd = source.handle if source is not None else 0

        if (self.runtime.settings is not settings_at_start
                or not accepted_unchanged()):
            return []
        if not source_hwnd:
            return clients

        return [
            client for client, hwnd in sorted(
                accepted_hwnds,
                key=lambda pair: 0 if pair[1] == source_hwnd else 1,
            )
        ]

    def restore_preferred_client(self, action_label: str) -> None:
        settings = self.runtime.settings
        if settings is None:
            return
        favorite_at_dispatch = settings.primary_handle
        mode_at_dispatch = settings.macro_mode

        def context_changed() -> bool:
            return (
                self.runtime.settings is not settings
                or settings.primary_handle != favorite_at_dispatch
                or settings.macro_mode != mode_at_dispatch
            )

        if self.runtime.macro_lock.should_stop():
            self.runtime.logger.info(
                "%s retour ignore: stop urgence actif.",
                action_label,
            )
            return

        # preferred_client() already checks DOFUS identity; keep a second
        # independent check only AFTER activation, to catch HWND reuse.
        preferred = self.preferred_client()
        if context_changed():
            self.runtime.logger.info(
                "%s retour ignore: profil, favori ou mode Organizer modifié.", action_label,
            )
            return
        if preferred is None:
            self.runtime.logger.info(
                "%s retour ignore: favori/premier indisponible.",
                action_label,
            )
            return

        # Freeze the exact HWND; an in-place Organizer edit must not retarget
        # the native call or publish a different favorite as accepted.
        preferred_hwnd = preferred.handle
        if type(preferred_hwnd) is not int or not 0 < preferred_hwnd <= (2**64 - 1):
            self.runtime.logger.info(
                "%s retour ignore: HWND favori invalide.", action_label,
            )
            return
        timings = settings.timings
        if activate_window(
            preferred_hwnd,
            timings.click_focus_settle_ms,
            timings.activate_attempts,
            timings.activate_retry_ms,
            self.runtime.logger,
            f"{action_label} retour",
            should_stop=lambda: (
                self.runtime.macro_lock.should_stop()
                or context_changed()
                or preferred.handle != preferred_hwnd
            ),
        ):
            if self.runtime.macro_lock.should_stop() or context_changed():
                return
            # The preferred client can change while a Win32 activation is
            # settling. A former favorite must never become the new active
            # character just because its process is still DOFUS.
            current_preferred = self.runtime.settings.preferred_client()
            if (current_preferred is None
                    or current_preferred.handle != preferred_hwnd
                    or preferred.handle != preferred_hwnd):
                self.runtime.logger.info(
                    "%s retour non publié: favori modifié.", action_label,
                )
                return
            if (not is_dofus_unity_process(preferred_hwnd)
                or foreground_window() != preferred_hwnd):
                self.runtime.logger.warning(
                    "%s retour non confirmé: identite ou focus différent hwnd=%s",
                    action_label, preferred_hwnd,
                )
                return
            if (self.runtime.macro_lock.should_stop()
                    or context_changed()
                    or preferred.handle != preferred_hwnd):
                self.runtime.logger.info(
                    "%s retour non publié: profil ou Stop changé après contrôle final.",
                    action_label,
                )
                return
            self.runtime.active_client_handle = preferred_hwnd
