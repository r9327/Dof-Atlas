from __future__ import annotations

from typing import TYPE_CHECKING

from app.windows.focus import activate_window
from app.windows.unity_windows import foreground_window, is_unity_window

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime
    from app.core.settings import AtlasClient


class SwitchCharacterMacro:
    def __init__(self, runtime: "AtlasRuntime"):
        self.runtime = runtime

    def activate_by_index(self, client_index: int) -> bool:
        settings = self.runtime.settings
        target = next((client for client in settings.clients if client.index == int(client_index)), None)
        if target is None:
            self.runtime.logger.info("Activation client ignoree: index introuvable=%s", client_index)
            return False

        def run() -> None:
            if not is_unity_window(target.handle):
                self.runtime.logger.info(
                    "Activation client ignoree: cible non Unity label=%s hwnd=%s",
                    target.display_name,
                    target.handle,
                )
                return
            if activate_window(
                target.handle,
                settings.timings.click_focus_settle_ms,
                settings.timings.activate_attempts,
                settings.timings.activate_retry_ms,
                self.runtime.logger,
                "Activation client",
                should_stop=self.runtime.macro_lock.should_stop,
            ):
                self.runtime.active_client_handle = target.handle
                self.runtime.logger.info(
                    "Activation par raccourci client: label=%s hwnd=%s",
                    target.display_name,
                    target.handle,
                )

        return self.runtime._spawn_macro("Activation client", run)

    def preferred_client(self) -> "AtlasClient | None":
        """
        Renvoie le personnage principal défini dans l'Organizer.

        AtlasSettings.preferred_client() gère déjà l'ordre suivant :
        primary_handle, client marqué primary, puis premier client configuré.
        """
        preferred = self.runtime.settings.preferred_client()
        if preferred is None or not is_unity_window(preferred.handle):
            return None
        return preferred

    def logical_active_client(self) -> "AtlasClient | None":
        settings = self.runtime.settings
        active = foreground_window()
        if active and is_unity_window(active):
            client = settings.client_by_handle(active)
            if client is not None:
                self.runtime.active_client_handle = client.handle
                return client

        if self.runtime.active_client_handle:
            client = settings.client_by_handle(self.runtime.active_client_handle)
            if client is not None and is_unity_window(client.handle):
                return client

        preferred = self.preferred_client()
        if preferred is not None:
            self.runtime.active_client_handle = preferred.handle
            return preferred

        for client in settings.clients:
            if is_unity_window(client.handle):
                self.runtime.active_client_handle = client.handle
                return client
        return None

    def ordered_clients_from_source(
        self,
        source_hwnd: int = 0,
    ) -> list["AtlasClient"]:
        clients: list["AtlasClient"] = []
        seen_handles: set[int] = set()

        for client in self.runtime.settings.clients:
            handle = int(client.handle)
            if handle in seen_handles or not is_unity_window(handle):
                continue
            seen_handles.add(handle)
            clients.append(client)

        try:
            source_hwnd = int(source_hwnd or 0)
        except (TypeError, ValueError):
            source_hwnd = 0

        if source_hwnd not in seen_handles:
            source = self.logical_active_client()
            source_hwnd = source.handle if source is not None else 0

        if not source_hwnd:
            return clients

        return sorted(
            clients,
            key=lambda client: 0 if client.handle == source_hwnd else 1,
        )

    def restore_preferred_client(self, action_label: str) -> None:
        if self.runtime.macro_lock.should_stop():
            self.runtime.logger.info(
                "%s retour ignore: stop urgence actif.",
                action_label,
            )
            return

        preferred = self.preferred_client()
        if preferred is None:
            self.runtime.logger.info(
                "%s retour ignore: favori/premier indisponible.",
                action_label,
            )
            return

        timings = self.runtime.settings.timings
        if activate_window(
            preferred.handle,
            timings.click_focus_settle_ms,
            timings.activate_attempts,
            timings.activate_retry_ms,
            self.runtime.logger,
            f"{action_label} retour",
            should_stop=self.runtime.macro_lock.should_stop,
        ):
            self.runtime.active_client_handle = preferred.handle
