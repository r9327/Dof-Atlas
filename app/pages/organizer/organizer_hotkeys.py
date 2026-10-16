from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from app.constants import (
    KEY_CLICK_HOTKEY,
    KEY_DEBUG_MODE,
    KEY_DOUBLE_CLICK_HOTKEY,
    KEY_SCRIPT_SPEED,
    KEY_STOP_SCRIPT_HOTKEY,
    KEY_SWITCH_CLICK,
    KEY_SWITCH_DOUBLE_CLICK,
)
from app.storage import invoke_compatible_callback, key_sequence_to_hotkey, profile_bool
from .common import SESSION_SLOT_COUNT, client_slot_hotkey_key


class OrganizerHotkeysMixin:
    def toggle_profile_bool(self, key: str) -> None:
        self.set_profile_bool(key, not profile_bool(self.profiles, key, False))

    def set_profile_bool(self, key: str, value: bool) -> None:
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
        ):
            if value == self.hotkey_label(key):
                return label
        return ""

    def script_speed(self) -> str:
        speed = str(self.profiles.get(KEY_SCRIPT_SPEED, "normal")).strip().casefold()
        return "rapide" if speed in ("rapide", "fast") else "normal"

    def set_script_speed(self, speed: str) -> None:
        resolved = "rapide" if str(speed).strip().casefold() in ("rapide", "fast") else "normal"
        self.profiles[KEY_SCRIPT_SPEED] = resolved
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.update_script_speed_buttons()
        self.reload_runtime_callback()
        label = "Rapide" if resolved == "rapide" else "Normal"
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

    def begin_capture(
        self,
        kind: str,
        name: str | None = None,
        slot: int | None = None,
        button: QPushButton | None = None,
    ) -> None:
        self.capture_target = {"kind": kind, "name": name, "slot": slot, "button": button}
        if button is not None:
            button.setText("...")
        elif kind == "click":
            self.click_button.setText("...")
        elif kind == "double_click":
            self.double_click_button.setText("...")
        elif kind == "stop_script":
            self.stop_script_hotkey_button.setText("...")
        self.setFocus(Qt.ShortcutFocusReason)
        self.status_callback("En attente d'une touche...")

    def keyPressEvent(self, event) -> None:
        if not self.capture_target:
            super().keyPressEvent(event)
            return
        hotkey = key_sequence_to_hotkey(event.key(), event.modifiers())
        target = self.capture_target
        self.capture_target = None
        if not hotkey:
            self.status_callback("Touche ignorée.")
            self.update_global_buttons()
            self.render_sessions()
            return
        kind = target.get("kind")
        if kind == "client" and target.get("slot") is not None:
            slot_index = int(target["slot"])
            owner = self.global_hotkey_owner(hotkey) or self.client_hotkey_owner(hotkey, exclude_slot=slot_index)
            if owner:
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback(f"Raccourci deja utilise par {owner}.")
                return
            self.profiles[client_slot_hotkey_key(slot_index)] = hotkey
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
        self.reload_runtime_callback()
        self.status_callback(f"Raccourci {hotkey} enregistré.")
