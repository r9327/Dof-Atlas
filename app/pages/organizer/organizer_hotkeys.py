from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QPushButton

from app.constants import (
    KEY_CLICK_HOTKEY,
    KEY_DEBUG_MODE,
    KEY_ORGANIZER_MACRO_MODE,
    KEY_DOUBLE_CLICK_HOTKEY,
    KEY_SCRIPT_SPEED,
    KEY_SCRIPT_SPEED_SCHEMA,
    KEY_RADIAL_HOTKEY,
    KEY_RADIAL_ENABLED,
    KEY_NEXT_CHARACTER_HOTKEY,
    KEY_STOP_SCRIPT_HOTKEY,
    KEY_SWITCH_CLICK,
    KEY_SWITCH_DOUBLE_CLICK,
    KEY_SWITCH_MOVEMENT,
)
from app.storage import invoke_compatible_callback, key_sequence_to_hotkey, profile_bool
from app.core.settings import normalize_script_speed
from .common import SESSION_SLOT_COUNT, client_slot_hotkey_key


class OrganizerHotkeysMixin:
    def set_macro_mode(self, value: str) -> None:
        mode = "mirror" if value == "mirror" else "macro"
        if mode == self.profiles.get(KEY_ORGANIZER_MACRO_MODE, "macro"):
            return
        # Do not let an active classic macro survive the mode change.
        if callable(self.stop_runtime_callback):
            invoke_compatible_callback(self.stop_runtime_callback, True)
        self.profiles[KEY_ORGANIZER_MACRO_MODE] = mode
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.update_macro_mode_buttons()
        self.update_switch_buttons()
        self.reload_runtime_callback()
        self.status_callback(
            "Miroir : clics, touches courtes et molette recopiés séquentiellement."
            if mode == "mirror" else "Macros classiques réactivées."
        )

    def toggle_radial_enabled(self) -> None:
        enabled = not profile_bool(self.profiles, KEY_RADIAL_ENABLED, True)
        self.profiles[KEY_RADIAL_ENABLED] = enabled
        if enabled:
            self.ensure_radial_participants()
            self.sync_radial_participants(persist=False)
        # Persist ON/OFF + inclusion changes in one profile transaction.
        self.save_profiles(self.profiles)
        # If this key is shared with a slot, changing the active owner
        # requires rebuilding only the runtime hotkey registry.
        binding = self.hotkey_label(KEY_RADIAL_HOTKEY)
        shared_slot = bool(binding) and any(
            self.hotkey_label(client_slot_hotkey_key(slot)) == binding
            for slot in range(SESSION_SLOT_COUNT)
        )
        if shared_slot:
            self.reload_runtime_callback()
        controller = getattr(self, "_radial_controller", None)
        if controller is not None:
            controller.cancel()
            controller.set_shortcut(
                self.hotkey_label(KEY_RADIAL_HOTKEY) if enabled else ""
            )
        self.update_global_buttons()
        self.status_callback(
            "Sélection personnage activée." if enabled
            else "Sélection personnage désactivée."
        )

    def toggle_profile_bool(self, key: str) -> None:
        self.set_profile_bool(key, not profile_bool(self.profiles, key, False))

    def set_profile_bool(self, key: str, value: bool) -> None:
        radial_key = self.hotkey_label(KEY_RADIAL_HOTKEY)
        if key == KEY_SWITCH_MOVEMENT and value and radial_key in {
            "HOME", "DELETE", "END", "PAGEDOWN"
        }:
            self.status_callback(
                "Switch Déplacement incompatible avec la touche du camembert."
            )
            return
        self.profiles[key] = bool(value)
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.update_switch_buttons()
        self.update_debug_button()
        self.reload_runtime_callback()

    def toggle_debug_mode(self) -> None:
        enabled = not profile_bool(self.profiles, KEY_DEBUG_MODE, False)
        self.profiles[KEY_DEBUG_MODE] = enabled
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.update_debug_button()
        invoke_compatible_callback(self.reload_runtime_callback, True)
        self.status_callback(
            "Debug actif: logs runtime detailles."
            if enabled
            else "Debug inactif: logs runtime alleges."
        )

    def hotkey_label(self, key: str) -> str:
        return str(self.profiles.get(key) or "").strip().upper()

    def slot_hotkey_label(self, slot_index: int) -> str:
        return self.hotkey_label(client_slot_hotkey_key(slot_index))

    def client_hotkey_owner(self, hotkey: str, exclude_slot: int | None = None) -> str:
        value = str(hotkey or "").strip().upper()
        if not value:
            return ""
        for slot_index in range(SESSION_SLOT_COUNT):
            if exclude_slot is not None and slot_index == exclude_slot:
                continue
            if self.slot_hotkey_label(slot_index) == value:
                return f"Personnage {slot_index + 1}"
        return ""

    def global_hotkey_owner(self, hotkey: str) -> str:
        value = str(hotkey or "").strip().upper()
        if not value:
            return ""
        for key, label in (
            (KEY_CLICK_HOTKEY, "Switch Clique"),
            (KEY_DOUBLE_CLICK_HOTKEY, "Switch clic x2"),
            (KEY_STOP_SCRIPT_HOTKEY, "Stop script"),
            (KEY_RADIAL_HOTKEY, "Sélection personnage"),
            (KEY_NEXT_CHARACTER_HOTKEY, "Personnage suivant"),
        ):
            if value == self.hotkey_label(key):
                return label
        return ""

    def script_speed(self) -> str:
        return normalize_script_speed(
            self.profiles.get(KEY_SCRIPT_SPEED, "normal"),
            legacy=str(self.profiles.get(KEY_SCRIPT_SPEED_SCHEMA, "1")) != "2",
        )

    def set_script_speed(self, speed: str) -> None:
        resolved = normalize_script_speed(speed)
        schema_v2 = str(self.profiles.get(KEY_SCRIPT_SPEED_SCHEMA, "1")) == "2"
        previous = normalize_script_speed(
            self.profiles.get(KEY_SCRIPT_SPEED, "normal"),
            legacy=not schema_v2,
        )
        # Re-selecting the active v2 preset must not reload Organizer or
        # cancel a live 2–8 client worker without changing any effective delay.
        if previous == resolved and schema_v2:
            return
        # Both a speed change and an old-profile schema migration replace the
        # runtime settings generation. Stop the worker before persisting.
        if callable(getattr(self, "stop_runtime_callback", None)):
            invoke_compatible_callback(self.stop_runtime_callback, True)
        self.profiles[KEY_SCRIPT_SPEED] = resolved
        # Persist the schema together with the chosen preset. Otherwise a
        # future reload would reinterpret a v2 Rapide as legacy v1 Rapide.
        self.profiles[KEY_SCRIPT_SPEED_SCHEMA] = 2
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.update_script_speed_buttons()
        self.reload_runtime_callback()
        label = {
            "classique": "Classique", "normal": "Normal",
            "rapide": "Rapide", "instantane": "Instantané",
        }[resolved]
        self.status_callback(f"Vitesse script : {label}.")

    def stop_script(self) -> None:
        if callable(self.stop_runtime_callback):
            self.stop_runtime_callback()
        else:
            self.status_callback("Stop urgence indisponible.")

    def remove_client_hotkey(self, slot_index: int) -> None:
        self.profiles.pop(client_slot_hotkey_key(slot_index), None)
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.render_sessions()
        self.status_callback(f"Raccourci supprimé pour personnage {slot_index + 1}.")

    def clear_global_hotkey(self, key: str) -> None:
        self.profiles.pop(key, None)
        if key == KEY_RADIAL_HOTKEY:
            controller = getattr(self, "_radial_controller", None)
            if controller is not None:
                controller.set_shortcut("")
        if key == KEY_CLICK_HOTKEY:
            self.profiles[KEY_SWITCH_CLICK] = False
        elif key == KEY_DOUBLE_CLICK_HOTKEY:
            self.profiles[KEY_SWITCH_DOUBLE_CLICK] = False
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.update_switch_buttons()
        self.update_global_buttons()
        self.reload_runtime_callback()
        self.status_callback("Raccourci supprimé.")

    def cancel_capture(self, message: str = "Capture de raccourci annulée.") -> None:
        if not self.capture_target:
            return
        self.capture_target = None
        timer = getattr(self, "_capture_timer", None)
        if timer is not None:
            timer.stop()
        self.update_global_buttons()
        self.render_sessions()
        self.status_callback(message)

    def focusOutEvent(self, event) -> None:
        # A click away, Alt+Tab or a hidden window must never leave the
        # next arbitrary keystroke waiting to be persisted as a shortcut.
        if self.capture_target:
            self.cancel_capture("Capture annulée : Organizer a perdu le focus.")
        super().focusOutEvent(event)

    def begin_capture(
        self,
        kind: str,
        name: str | None = None,
        slot: int | None = None,
        button: QPushButton | None = None,
    ) -> None:
        self.capture_target = {"kind": kind, "name": name, "slot": slot, "button": button}
        timer = getattr(self, "_capture_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(
                lambda: self.cancel_capture("Capture annulée : délai de saisie dépassé.")
            )
            self._capture_timer = timer
        timer.start(12_000)
        if button is not None:
            button.setText("...")
        elif kind == "click":
            self.click_button.setText("...")
        elif kind == "double_click":
            self.double_click_button.setText("...")
        elif kind == "stop_script":
            self.stop_script_hotkey_button.setText("...")
        elif kind == "radial":
            self.radial_hotkey_button.setText("...")
        elif kind == "next_character":
            self.next_character_hotkey_button.setText("...")
        self.setFocus(Qt.ShortcutFocusReason)
        self.status_callback("En attente d'une touche...")

    def keyPressEvent(self, event) -> None:
        if not self.capture_target:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key_Escape:
            self.cancel_capture()
            event.accept()
            return
        hotkey = key_sequence_to_hotkey(event.key(), event.modifiers())
        target = self.capture_target
        self.capture_target = None
        timer = getattr(self, "_capture_timer", None)
        if timer is not None:
            timer.stop()
        if not hotkey:
            self.status_callback("Touche ignorée.")
            self.update_global_buttons()
            self.render_sessions()
            return
        kind = target.get("kind")
        if kind not in {"radial", "client"} and hotkey == self.hotkey_label(KEY_RADIAL_HOTKEY):
            self.update_global_buttons()
            self.render_sessions()
            self.status_callback("Raccourci déjà utilisé par Sélection personnage.")
            return
        if kind == "client":
            # A malformed or stale capture target must never silently bind a
            # shortcut to a different character (int(1.9) == 1, True == 1).
            slot_index = target.get("slot")
            if type(slot_index) is not int or not 0 <= slot_index < SESSION_SLOT_COUNT:
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci ignoré : slot personnage invalide.")
                return
            owner = self.global_hotkey_owner(hotkey)
            if owner == "Sélection personnage":
                owner = ""  # explicit wheel-over-slot priority
            owner = owner or self.client_hotkey_owner(
                hotkey, exclude_slot=slot_index,
            )
            if owner:
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback(f"Raccourci deja utilise par {owner}.")
                return
            self.profiles[client_slot_hotkey_key(slot_index)] = hotkey
        elif kind == "radial":
            if hotkey in {"HOME", "DELETE", "END", "PAGEDOWN"} and profile_bool(
                self.profiles, KEY_SWITCH_MOVEMENT, False
            ):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Touche déjà utilisée par Switch Déplacement.")
                return
            # A slot binding is allowed: the radial wheel owns the key
            # only while enabled, while Stop and other global hotkeys remain
            # exclusive even when the radial wheel is disabled.
            owner = self.global_hotkey_owner(hotkey)
            if owner == "Sélection personnage":
                owner = ""
            if owner:
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback(f"Raccourci déjà utilisé par {owner}.")
                return
            self.ensure_radial_participants()
            self.profiles[KEY_RADIAL_HOTKEY] = hotkey
        elif kind == "next_character":
            if (hotkey in {"HOME", "DELETE", "END", "PAGEDOWN"}
                    and profile_bool(self.profiles, KEY_SWITCH_MOVEMENT, False)):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Touche déjà utilisée par Switch Déplacement.")
                return
            owner = self.global_hotkey_owner(hotkey)
            if owner and owner != "Personnage suivant":
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback(f"Raccourci déjà utilisé par {owner}.")
                return
            owner = self.client_hotkey_owner(hotkey)
            if owner:
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback(f"Raccourci déjà utilisé par {owner}.")
                return
            self.profiles[KEY_NEXT_CHARACTER_HOTKEY] = hotkey
        elif kind == "click":
            if hotkey == self.hotkey_label(KEY_DOUBLE_CLICK_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Switch clic x2.")
                return
            if hotkey == self.hotkey_label(KEY_STOP_SCRIPT_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Stop script.")
                return
            if hotkey == self.hotkey_label(KEY_NEXT_CHARACTER_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Personnage suivant.")
                return
            owner = self.client_hotkey_owner(hotkey)
            if owner:
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback(f"Raccourci deja utilise par {owner}.")
                return
            self.profiles[KEY_CLICK_HOTKEY] = hotkey
        elif kind == "double_click":
            if hotkey == self.hotkey_label(KEY_CLICK_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Switch Clique.")
                return
            if hotkey == self.hotkey_label(KEY_STOP_SCRIPT_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Stop script.")
                return
            if hotkey == self.hotkey_label(KEY_NEXT_CHARACTER_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Personnage suivant.")
                return
            owner = self.client_hotkey_owner(hotkey)
            if owner:
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback(f"Raccourci deja utilise par {owner}.")
                return
            self.profiles[KEY_DOUBLE_CLICK_HOTKEY] = hotkey
        elif kind == "stop_script":
            if hotkey == self.hotkey_label(KEY_CLICK_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Switch Clique.")
                return
            if hotkey == self.hotkey_label(KEY_DOUBLE_CLICK_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Switch clic x2.")
                return
            if hotkey == self.hotkey_label(KEY_NEXT_CHARACTER_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Personnage suivant.")
                return
            owner = self.client_hotkey_owner(hotkey)
            if owner:
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback(f"Raccourci deja utilise par {owner}.")
                return
            self.profiles[KEY_STOP_SCRIPT_HOTKEY] = hotkey
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.update_global_buttons()
        self.render_sessions()
        controller = getattr(self, "_radial_controller", None)
        if controller is not None:
            controller.set_shortcut(
                self.hotkey_label(KEY_RADIAL_HOTKEY)
                if profile_bool(self.profiles, KEY_RADIAL_ENABLED, True) else ""
            )
        self.reload_runtime_callback()
        shared = (
            kind in {"radial", "client"}
            and hotkey == self.hotkey_label(KEY_RADIAL_HOTKEY)
            and bool(self.client_hotkey_owner(hotkey))
        )
        self.status_callback(
            f"Raccourci {hotkey} enregistré : roue prioritaire lorsqu'elle est active."
            if shared else f"Raccourci {hotkey} enregistré."
        )
