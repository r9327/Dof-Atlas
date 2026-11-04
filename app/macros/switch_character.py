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
    ) -> bool:
        settings = self.runtime.settings
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
        target = next((client for client in settings.clients if client.index == requested_index), None)
        if target is None:
            self.runtime.logger.info("Activation client ignoree: index introuvable=%s", client_index)
            return False

        def run() -> None:
            # Hotkey callbacks are asynchronous: a slot can be reassigned
            # before this worker receives its turn. Never activate a stale
            # HWND merely because it still belongs to a DOFUS process.
            def target_is_current() -> bool:
                # A new settings object is a new Organizer generation even
                # when the same slot/handle were reloaded from disk.
                return self.runtime.settings is settings and any(
                    client.index == target.index and client.handle == target.handle
                    for client in settings.clients
                )

            if not target_is_current():
                self.runtime.logger.info(
                    "Activation client annulée: slot modifié index=%s", target.index,
                )
                return
            if not is_unity_window(target.handle) or not is_dofus_unity_process(target.handle):
                self.runtime.logger.info(
                    "Activation client ignoree: cible non DOFUS Unity label=%s hwnd=%s",
                    target.display_name,
                    target.handle,
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
                target.handle,
                settings.timings.click_focus_settle_ms,
                settings.timings.activate_attempts,
                settings.timings.activate_retry_ms,
                self.runtime.logger,
                "Activation client",
                should_stop=lambda: (
                    self.runtime.macro_lock.should_stop()
                    or self.runtime.settings is not settings
                ),
            ):
                # Activation success is not enough: the slot may have been
                # reassigned, or Stop/focus theft may have arrived in the meantime.
                if self.runtime.macro_lock.should_stop():
                    return
                if not target_is_current():
                    self.runtime.logger.info(
                        "Activation client non publiée: slot modifié index=%s", target.index,
                    )
                    return
                if (not is_dofus_unity_process(target.handle)
                        or foreground_window() != int(target.handle)):
                    self.runtime.logger.warning(
                        "Activation client ignoree: identite ou focus non confirme hwnd=%s",
                        target.handle,
                    )
                    return
                self.runtime.active_client_handle = target.handle
                self.runtime.logger.info(
                    "Activation par raccourci client: label=%s hwnd=%s",
                    target.display_name,
                    target.handle,
                )

        return self.runtime._spawn_macro("Activation client", run)

    def activate_next(self) -> bool:
        """Advance in live Organizer slot order, wrapping after the last.

        Each target still uses the canonical activation worker with its
        independent foreground, process and stale-slot checks.
        """
        if self.runtime.macro_lock.should_stop():
            return False
        settings = self.runtime.settings
        clients = []
        seen: set[int] = set()
        for client in settings.clients:
            hwnd = client.handle
            if (type(hwnd) is not int or not 0 < hwnd <= (2**64 - 1)
                    or hwnd in seen or not is_unity_window(hwnd)
                    or not is_dofus_unity_process(hwnd)):
                continue
            seen.add(hwnd)
            clients.append(client)
            if self.runtime.settings is not settings:
                return False
        if len(clients) < 2 or self.runtime.settings is not settings:
            return False
        current = self.logical_active_client()
        if self.runtime.settings is not settings or self.runtime.macro_lock.should_stop():
            return False
        current_hwnd = current.handle if current is not None else 0
        position = next(
            (i for i, item in enumerate(clients) if item.handle == current_hwnd), -1,
        )
        return self.activate_by_index(
            clients[(position + 1) % len(clients)].index,
            expected_profile=settings,
        )

    def preferred_client(self) -> "AtlasClient | None":
        """
        Renvoie le personnage principal défini dans l'Organizer.

        AtlasSettings.preferred_client() gère déjà l'ordre suivant :
        primary_handle, client marqué primary, puis premier client configuré.
        """
        preferred = self.runtime.settings.preferred_client()
        if (preferred is None or not is_unity_window(preferred.handle)
                or not is_dofus_unity_process(preferred.handle)):
            return None
        return preferred

    def logical_active_client(self) -> "AtlasClient | None":
        settings = self.runtime.settings
        active = foreground_window()
        if active and is_unity_window(active) and is_dofus_unity_process(active):
            client = settings.client_by_handle(active)
            if client is not None:
                self.runtime.active_client_handle = client.handle
                return client

        if self.runtime.active_client_handle:
            client = settings.client_by_handle(self.runtime.active_client_handle)
            if (client is not None and is_unity_window(client.handle)
                    and is_dofus_unity_process(client.handle)):
                return client

        preferred = self.preferred_client()
        if preferred is not None:
            self.runtime.active_client_handle = preferred.handle
            return preferred

        for client in settings.clients:
            if is_unity_window(client.handle) and is_dofus_unity_process(client.handle):
                self.runtime.active_client_handle = client.handle
                return client
        return None

    def ordered_clients_from_source(
        self,
        source_hwnd: int = 0,
    ) -> list["AtlasClient"]:
        settings_at_start = self.runtime.settings
        clients: list["AtlasClient"] = []
        seen_handles: set[int] = set()

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
            seen_handles.add(handle)
            clients.append(client)
            if self.runtime.settings is not settings_at_start:
                self.runtime.logger.info(
                    "Switch: roster abandonné, profil Organizer remplacé pendant scan.",
                )
                return []
        if self.runtime.settings is not settings_at_start:
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

        if self.runtime.settings is not settings_at_start:
            return []
        if not source_hwnd:
            return clients

        return sorted(
            clients,
            key=lambda client: 0 if client.handle == source_hwnd else 1,
        )

    def restore_preferred_client(self, action_label: str) -> None:
        settings = self.runtime.settings
        if self.runtime.macro_lock.should_stop():
            self.runtime.logger.info(
                "%s retour ignore: stop urgence actif.",
                action_label,
            )
            return

        # preferred_client() already checks DOFUS identity; keep a second
        # independent check only AFTER activation, to catch HWND reuse.
        preferred = self.preferred_client()
        if self.runtime.settings is not settings:
            self.runtime.logger.info(
                "%s retour ignore: profil Organizer remplacé.", action_label,
            )
            return
        if preferred is None:
            self.runtime.logger.info(
                "%s retour ignore: favori/premier indisponible.",
                action_label,
            )
            return

        timings = settings.timings
        if activate_window(
            preferred.handle,
            timings.click_focus_settle_ms,
            timings.activate_attempts,
            timings.activate_retry_ms,
            self.runtime.logger,
            f"{action_label} retour",
            should_stop=lambda: (
                self.runtime.macro_lock.should_stop()
                or self.runtime.settings is not settings
            ),
        ):
            if self.runtime.macro_lock.should_stop() or self.runtime.settings is not settings:
                return
            # The preferred client can change while a Win32 activation is
            # settling. A former favorite must never become the new active
            # character just because its process is still DOFUS.
            current_preferred = self.runtime.settings.preferred_client()
            if (current_preferred is None
                    or current_preferred.handle != preferred.handle):
                self.runtime.logger.info(
                    "%s retour non publié: favori modifié.", action_label,
                )
                return
            if (not is_dofus_unity_process(preferred.handle)
                or foreground_window() != int(preferred.handle)):
                self.runtime.logger.warning(
                    "%s retour non confirmé: identite ou focus différent hwnd=%s",
                    action_label, preferred.handle,
                )
                return
            self.runtime.active_client_handle = preferred.handle
