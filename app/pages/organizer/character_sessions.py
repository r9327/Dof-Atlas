from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from app.constants import (
    CLIENT_INDEX_INI,
    CLIENT_INDEX_JSON,
    KEY_CLICK_HOTKEY,
    KEY_DEBUG_MODE,
    KEY_DOUBLE_CLICK_HOTKEY,
    KEY_PRIMARY_WINDOW,
    KEY_SCRIPT_SPEED,
    KEY_SESSION_ORDER,
    KEY_STOP_SCRIPT_HOTKEY,
    KEY_SWITCH_CHARACTER,
    KEY_SWITCH_CLICK,
    KEY_SWITCH_DOUBLE_CLICK,
    KEY_SWITCH_MOVEMENT,
    KEY_TRAVEL_TEXT,
    PROFILE_FILE,
)
from app.quest_catalog import is_generic_dofus_client_name
from app.services.profile_settings_service import ProfileSettingsService
from app.storage import (
    clean_auto_group_name,
    default_profiles,
    format_zaap_ratio,
    invoke_compatible_callback,
    normalize_key,
    profile_bool,
    read_json,
    read_zaap_button_ratios,
    read_zaap_click_position,
    write_json,
    write_text_atomic,
)
from app.windows_embed import EVENT_SYSTEM_FOREGROUND, scan_unity_sessions
from .common import (
    RELEASE_RETRY_DELAYS_MS,
    SESSION_SLOT_COUNT,
    client_slot_hotkey_key,
    dofus_class_key_from_window_name,
    empty_session_slot,
    session_hwnd,
    session_is_detected,
    session_is_empty,
    session_name,
    session_pid,
)


class CharacterSessionsMixin:
    def _profile_file(self):
        return getattr(self, "profile_file", PROFILE_FILE)

    def _client_index_json(self):
        return getattr(self, "client_index_json", CLIENT_INDEX_JSON)

    def _client_index_ini(self):
        return getattr(self, "client_index_ini", CLIENT_INDEX_INI)

    def _scan_unity_sessions(self) -> list[dict[str, Any]]:
        scanner = getattr(self, "scan_unity_sessions_callback", None)
        if callable(scanner):
            return scanner()

        # Keep compatibility with callers/tests that patch the historical
        # organizer_page.scan_unity_sessions symbol after the mixin split.
        import sys

        owner_module = sys.modules.get("app.pages.organizer_page")
        scanner = getattr(owner_module, "scan_unity_sessions", scan_unity_sessions)
        return scanner()

    def load_profiles(self) -> dict[str, Any]:
        payload = read_json(self._profile_file(), default_profiles())
        if not isinstance(payload, dict):
            payload = default_profiles()
        merged = default_profiles()
        merged.update(payload)
        cleaned = self.sanitize_profiles(merged)
        cleaned[KEY_SESSION_ORDER] = list(self.character_order_service.load_order())
        self._profiles_baseline = dict(cleaned)
        return cleaned

    def sanitize_profiles(self, payload: dict[str, Any]) -> dict[str, Any]:
        cleaned = dict(payload)
        legacy_debug_key = "".join(["__mode_debug_", "a", "h", "k__"])
        if legacy_debug_key in cleaned and KEY_DEBUG_MODE not in cleaned:
            cleaned[KEY_DEBUG_MODE] = cleaned.get(legacy_debug_key)
        cleaned.pop(legacy_debug_key, None)
        legacy_order = cleaned.get(KEY_SESSION_ORDER, [])
        if not isinstance(legacy_order, list):
            legacy_order = []

        for index, raw_name in enumerate(legacy_order[:SESSION_SLOT_COUNT]):
            name = str(raw_name or "").strip()
            if not name:
                continue
            legacy_binding = str(cleaned.get(name, "")).strip().upper()
            slot_key = client_slot_hotkey_key(index)
            if legacy_binding and not str(cleaned.get(slot_key, "")).strip():
                cleaned[slot_key] = legacy_binding

        for key in list(cleaned.keys()):
            if not str(key).startswith("__"):
                cleaned.pop(key, None)
        cleaned.pop(KEY_TRAVEL_TEXT, None)
        cleaned[KEY_SESSION_ORDER] = [str(value or "").strip() for value in legacy_order]
        primary = str(cleaned.get(KEY_PRIMARY_WINDOW, "")).strip()
        if primary and not primary.startswith("hwnd:"):
            cleaned[KEY_PRIMARY_WINDOW] = ""
        return cleaned

    def save_profiles(self, payload: dict[str, Any]) -> None:
        snapshot = dict(payload)
        snapshot[KEY_SESSION_ORDER] = list(self.character_order_service.load_order())
        baseline = dict(getattr(self, "_profiles_baseline", {}))
        updates = {
            key: value
            for key, value in snapshot.items()
            if key not in baseline or baseline.get(key) != value
        }
        removals = tuple(key for key in baseline if key not in snapshot)
        persisted, _changed = ProfileSettingsService(self._profile_file()).update_values(
            updates,
            remove_keys=removals,
            default=default_profiles(),
        )
        current = self.sanitize_profiles(persisted)
        current[KEY_SESSION_ORDER] = list(self.character_order_service.load_order())
        self.profiles = current
        self._profiles_baseline = dict(current)

    def reload_profiles_and_export(self) -> None:
        self.profiles = self.load_profiles()
        self.export_client_index()
        self.request_sessions_render()

    def refresh_sessions_and_export(self, render: bool = False) -> bool:
        self.profiles = self.load_profiles()
        refreshed = False
        if os.name == "nt":
            sessions = self._scan_unity_sessions()
            self.sessions = self.build_session_slots(sessions)
            refreshed = bool(sessions)
        self.export_client_index()
        if render:
            self.request_sessions_render()
        self.sync_event_watcher_sessions()
        self.notify_sessions_changed()
        return refreshed

    def sync_event_watcher_sessions(self) -> None:
        watcher = getattr(self, "session_event_watcher", None)
        if watcher is None:
            return
        watcher.replace_tracked_hwnds(
            session_hwnd(session)
            for session in self.sessions
            if session_is_detected(session)
        )

    def stop_session_event_watcher(self, *_args) -> None:
        self.window_event_refresh_timer.stop()
        self.release_retry_timer.stop()
        watcher = getattr(self, "session_event_watcher", None)
        if watcher is not None:
            watcher.stop()

    def on_unity_window_event(self, event_id: int, hwnd: int) -> None:
        if int(event_id) == EVENT_SYSTEM_FOREGROUND and callable(self.active_session_callback):
            self.active_session_callback(int(hwnd))
        self.window_event_refresh_timer.start()

    def session_identity_signature(self) -> tuple[tuple[int, str, int, int], ...]:
        return tuple(
            (
                slot_index + 1,
                clean_auto_group_name(session_name(session)),
                session_hwnd(session),
                session_pid(session),
            )
            for slot_index, session in enumerate(self.sessions)
            if session_is_detected(session)
        )

    def notify_sessions_changed(self) -> None:
        signature = self.session_identity_signature()
        if signature == self._last_notified_session_signature:
            return
        self._last_notified_session_signature = signature
        if callable(self.sessions_changed_callback):
            self.sessions_changed_callback()

    def load_last_sessions(self) -> list[dict[str, Any]]:
        return []

    def session_slot_count(self) -> int:
        return SESSION_SLOT_COUNT

    def detected_session_count(self) -> int:
        return sum(1 for session in self.sessions if session_is_detected(session))

    def build_session_slots(self, detected_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        detected = [
            dict(session)
            for session in detected_sessions
            if session_is_detected(session)
        ]
        ordered = list(
            self.character_order_service.sort_rows(
                detected,
                label_getter=lambda session: (
                    clean_auto_group_name(session_name(session)) or session_name(session)
                ),
            )
        )
        slots = ordered[:SESSION_SLOT_COUNT]
        while len(slots) < SESSION_SLOT_COUNT:
            slots.append(empty_session_slot())
        return slots

    def session_order_keys(self, session: dict[str, Any]) -> list[str]:
        try:
            hwnd = int(session.get("hwnd", 0))
        except (AttributeError, TypeError, ValueError):
            hwnd = 0
        label = str(session.get("nom", "")).strip() if isinstance(session, dict) else ""
        short_name = clean_auto_group_name(label)
        keys = [normalize_key(label), normalize_key(short_name)]
        if hwnd > 0:
            keys.append(f"hwnd:{hwnd}")
        seen = set()
        return [key for key in keys if key and not (key in seen or seen.add(key))]

    def saved_session_order_map(self) -> dict[str, int]:
        return {
            key: index
            for index, key in enumerate(
                self.character_order_service.load_order()[:SESSION_SLOT_COUNT]
            )
        }

    def apply_saved_session_order(self, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.build_session_slots(sessions)

    def persisted_session_order_key(self, session: dict[str, Any]) -> str:
        if session_is_empty(session):
            return ""
        short_name = normalize_key(clean_auto_group_name(session_name(session)))
        if short_name:
            return short_name
        for key in self.session_order_keys(session):
            if key and not key.startswith("hwnd:"):
                return key
        return ""

    def save_session_order(self) -> None:
        order = [
            self.persisted_session_order_key(session)
            for session in self.sessions
            if session_is_detected(session)
        ]
        if not order:
            return
        self.character_order_service.save_labels(order)
        self.profiles[KEY_SESSION_ORDER] = list(self.character_order_service.load_order())

    def primary_session(self) -> dict[str, Any] | None:
        primary = str(self.profiles.get(KEY_PRIMARY_WINDOW, ""))
        if not primary:
            return None
        primary_matched = False
        for session in self.sessions:
            name = session_name(session)
            hwnd = session_hwnd(session)
            if not name or hwnd <= 0:
                continue
            if self.session_is_primary(name, hwnd, primary):
                if primary.startswith("hwnd:") or not primary_matched:
                    return session
                primary_matched = True
        return None

    def launch_auto_group(self) -> None:
        self.capture_target = None
        invite_names = []
        seen = set()
        for session in self.sessions:
            if not session_is_detected(session):
                continue
            name = clean_auto_group_name(session.get("nom", ""))
            key = normalize_key(name)
            if not name or key in seen:
                continue
            seen.add(key)
            invite_names.append({"name": name, "handle": session_hwnd(session)})
        if not invite_names:
            self.status_callback("Auto-groupe ignoré: aucun personnage détecté.")
            return
        self.export_client_index()
        if callable(self.launch_auto_group_callback):
            self.launch_auto_group_callback(invite_names)
        else:
            self.status_callback("Runtime Python indisponible.")
            return
        self.status_callback(f"Auto-groupe lancé: {len(invite_names)} invitation(s).")

    def scan_sessions(self) -> None:
        if os.name != "nt":
            self.status_callback("Scan sessions disponible seulement sous Windows.")
            return
        self.capture_target = None
        self.sessions = self.build_session_slots(self._scan_unity_sessions())
        self.export_client_index()
        self.request_sessions_render()
        self.sync_event_watcher_sessions()
        self.notify_sessions_changed()
        self.begin_release_identity_retries()
        detected_count = self.detected_session_count()
        if detected_count:
            self.status_callback(f"{detected_count} session(s) Unity détectée(s).")
            self.reload_runtime_callback()
        else:
            self.status_callback("Aucune session Unity détectée.")

    def auto_scan_sessions_on_startup(self) -> None:
        if os.name != "nt":
            return
        previous_count = self.detected_session_count()
        scanned = self.refresh_sessions_and_export(render=True)
        if scanned:
            self.status_callback(f"{self.detected_session_count()} session(s) Unity détectée(s) au lancement.")
            self.reload_runtime_callback()
        self.begin_release_identity_retries()
        if not scanned and previous_count:
            self.status_callback(f"{previous_count} session(s) conservee(s) depuis le dernier scan.")

    def refresh_sessions_from_window_event(self) -> None:
        if os.name != "nt":
            return
        previous_signature = self.session_identity_signature()
        self.profiles = self.load_profiles()
        self.sessions = self.build_session_slots(
            CharacterSessionsMixin._scan_unity_sessions(self)
        )
        changed = self.session_identity_signature() != previous_signature
        if changed:
            self.export_client_index()
            self.request_sessions_render()
            self.notify_sessions_changed()
        self.sync_event_watcher_sessions()
        self.begin_release_identity_retries()

    def begin_release_identity_retries(self) -> None:
        self.release_retry_timer.stop()
        self.release_retry_index = 0
        if self.sessions_have_generic_names():
            self.schedule_next_release_identity_retry()

    def schedule_next_release_identity_retry(self) -> None:
        if self.release_retry_index >= len(RELEASE_RETRY_DELAYS_MS):
            return
        delay_ms = RELEASE_RETRY_DELAYS_MS[self.release_retry_index]
        self.release_retry_index += 1
        self.release_retry_timer.start(delay_ms)

    def retry_release_identity(self) -> None:
        if os.name != "nt" or not self.sessions_have_generic_names():
            return
        previous_signature = self.session_identity_signature()
        self.sessions = self.build_session_slots(
            CharacterSessionsMixin._scan_unity_sessions(self)
        )
        changed = self.session_identity_signature() != previous_signature
        if changed:
            self.export_client_index()
            self.request_sessions_render()
            self.notify_sessions_changed()
        self.sync_event_watcher_sessions()
        if self.sessions_have_generic_names():
            self.schedule_next_release_identity_retry()

    def sessions_have_generic_names(self) -> bool:
        detected = [session for session in self.sessions if session_is_detected(session)]
        if not detected:
            return False
        return any(is_generic_dofus_client_name(session_name(session)) for session in detected)

    def reload_runtime(self) -> None:
        self.capture_target = None
        self.refresh_sessions_and_export(render=True)
        invoke_compatible_callback(self.reload_runtime_callback, True)
        detected_count = self.detected_session_count()
        if detected_count:
            self.status_callback(f"Raccourcis Python recharges: {detected_count} session(s) Unity.")
        else:
            self.status_callback("Raccourcis Python recharges: aucune session Unity detectee.")

    def primary_token_for_session(self, name: str, hwnd: int) -> str:
        return f"hwnd:{hwnd}" if hwnd > 0 else name

    def session_is_primary(self, name: str, hwnd: int, primary: str) -> bool:
        if not primary:
            return False
        if hwnd > 0 and primary == self.primary_token_for_session(name, hwnd):
            return True
        return primary == name

    def set_primary_window(self, session: dict[str, Any] | str) -> None:
        current = str(self.profiles.get(KEY_PRIMARY_WINDOW, ""))
        if isinstance(session, dict):
            name = str(session.get("nom", "Session"))
            try:
                hwnd = int(session.get("hwnd", 0))
            except (TypeError, ValueError):
                hwnd = 0
            token = self.primary_token_for_session(name, hwnd)
        else:
            name = str(session)
            token = name
        self.profiles[KEY_PRIMARY_WINDOW] = "" if current == token else token
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.render_sessions()
        self.status_callback(f"Fenêtre principale : {name}")

    def export_client_index(self) -> None:
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        self.save_session_order()
        primary_token = str(self.profiles.get(KEY_PRIMARY_WINDOW, ""))
        primary_label = ""
        primary_handle = 0
        used_client_bindings: set[str] = set()
        zaap_ratios = read_zaap_button_ratios()
        zaap_ratio_x = format_zaap_ratio(zaap_ratios[0]) if zaap_ratios else ""
        zaap_ratio_y = format_zaap_ratio(zaap_ratios[1]) if zaap_ratios else ""
        click_enabled = profile_bool(self.profiles, KEY_SWITCH_CLICK, False)
        double_click_enabled = profile_bool(self.profiles, KEY_SWITCH_DOUBLE_CLICK, False)
        click_hotkey = str(self.profiles.get(KEY_CLICK_HOTKEY, "")).strip() if click_enabled else ""
        double_click_hotkey = str(self.profiles.get(KEY_DOUBLE_CLICK_HOTKEY, "")).strip() if double_click_enabled else ""
        stop_script_hotkey = str(self.profiles.get(KEY_STOP_SCRIPT_HOTKEY, "")).strip()
        script_speed = self.script_speed()
        debug_enabled = profile_bool(self.profiles, KEY_DEBUG_MODE, False)
        if double_click_enabled and click_hotkey and double_click_hotkey and click_hotkey == double_click_hotkey:
            double_click_enabled = False
            double_click_hotkey = ""
        clients = []
        primary_matched = False
        for slot_index, session in enumerate(self.sessions):
            name = session_name(session)
            hwnd = session_hwnd(session)
            if not name or hwnd <= 0 or session_is_empty(session):
                continue
            client_index = len(clients) + 1
            is_primary = self.session_is_primary(name, hwnd, primary_token)
            if is_primary and not primary_token.startswith("hwnd:"):
                if primary_matched:
                    is_primary = False
                else:
                    primary_matched = True
            if is_primary:
                primary_label = f"Personnage {client_index}"
                primary_handle = hwnd
            binding = self.resolve_client_binding(
                slot_index,
                used_client_bindings,
                {click_hotkey, double_click_hotkey, stop_script_hotkey},
            )
            clients.append(
                {
                    "index": client_index,
                    "label": f"Personnage {client_index}",
                    "name": name,
                    "character_name": clean_auto_group_name(name),
                    "class_key": dofus_class_key_from_window_name(name) or "",
                    "slot": slot_index + 1,
                    "handle": hwnd,
                    "handle_hex": hex(hwnd),
                    "pid": session_pid(session),
                    "binding": binding,
                    "binding_explicit": bool(binding),
                    "primary": is_primary,
                }
            )

        payload = {
            "version": 1,
            "generated_at": timestamp,
            "scan_policy": "startup_and_user_interaction",
            "note": "Index de sessions Unity rafraichi au lancement et par interaction utilisateur.",
            "global_hotkeys": {
                "enabled": profile_bool(self.profiles, KEY_SWITCH_CHARACTER, True),
                "click_enabled": click_enabled,
                "click_hotkey": click_hotkey,
                "double_click_enabled": double_click_enabled,
                "double_click_hotkey": double_click_hotkey,
                "movement_enabled": profile_bool(self.profiles, KEY_SWITCH_MOVEMENT, False),
                "stop_script_hotkey": stop_script_hotkey,
                "script_speed": script_speed,
                "debug_enabled": debug_enabled,
                "zaap_click_x": read_zaap_click_position(self.profiles)[0],
                "zaap_click_y": read_zaap_click_position(self.profiles)[1],
                "zaap_click_x_ratio": zaap_ratio_x,
                "zaap_click_y_ratio": zaap_ratio_y,
                "primary_label": primary_label,
                "primary_handle": primary_handle,
            },
            "count": len(clients),
            "clients": clients,
        }

        lines = [
            "; Genere par session_manager_pyside.py pendant un scan au lancement ou une interaction utilisateur.",
            "; Le Python scanne les fenetres Unity pour alimenter le runtime de macros Python.",
            "[meta]",
            "version=1",
            f"generated_at={timestamp}",
            "scan_policy=startup_and_user_interaction",
            f"count={len(clients)}",
            "",
            "[global_hotkeys]",
            f"enabled={1 if profile_bool(self.profiles, KEY_SWITCH_CHARACTER, True) else 0}",
            f"click_enabled={1 if click_enabled else 0}",
            f"click_hotkey={click_hotkey}",
            f"double_click_enabled={1 if double_click_enabled else 0}",
            f"double_click_hotkey={double_click_hotkey}",
            f"movement_enabled={1 if profile_bool(self.profiles, KEY_SWITCH_MOVEMENT, False) else 0}",
            f"stop_script_hotkey={stop_script_hotkey}",
            f"script_speed={script_speed}",
            f"debug_enabled={1 if debug_enabled else 0}",
            f"zaap_click_x={read_zaap_click_position(self.profiles)[0]}",
            f"zaap_click_y={read_zaap_click_position(self.profiles)[1]}",
            f"zaap_click_x_ratio={zaap_ratio_x}",
            f"zaap_click_y_ratio={zaap_ratio_y}",
            f"primary_label={primary_label}",
            f"primary_handle={primary_handle}",
            "",
        ]
        for client in clients:
            lines.extend(
                [
                    f"[client_{client['index']}]",
                    f"label={client['label']}",
                    f"handle={client['handle']}",
                    f"handle_hex={client['handle_hex']}",
                    f"binding={client['binding']}",
                    f"binding_explicit={1 if client['binding_explicit'] else 0}",
                    f"primary={1 if client['primary'] else 0}",
                    "",
                ]
            )
        write_json(self._client_index_json(), payload)
        write_text_atomic(self._client_index_ini(), "\n".join(lines) + "\n")

    def resolve_client_binding(
        self,
        slot_index: int,
        used_bindings: set[str],
        reserved_bindings: set[str],
    ) -> str:
        reserved = {
            str(binding or "").strip().upper()
            for binding in reserved_bindings
            if str(binding or "").strip()
        }
        binding = self.slot_hotkey_label(slot_index)
        if not binding or binding in reserved or binding in used_bindings:
            return ""
        used_bindings.add(binding)
        return binding
