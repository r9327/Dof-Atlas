from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.constants import (
    CLIENT_INDEX_JSON,
    KEY_CLICK_HOTKEY,
    KEY_DEBUG_MODE,
    KEY_DOUBLE_CLICK_HOTKEY,
    KEY_PRIMARY_WINDOW,
    KEY_SCRIPT_SPEED,
    KEY_STOP_SCRIPT_HOTKEY,
    KEY_SWITCH_CHARACTER,
    KEY_SWITCH_CLICK,
    KEY_SWITCH_DOUBLE_CLICK,
    KEY_SWITCH_MOVEMENT,
    KEY_TRAVEL_TEXT,
    KEY_ZAAP_CLICK_POSITION,
    PROFILE_FILE,
    ZAAP_CLICK_X,
    ZAAP_CLICK_Y,
)
from app.core.json_store import read_json_resilient
from app.core.profile_settings import (
    default_profiles,
    parse_zaap_click_position,
    profile_bool,
    read_zaap_button_ratios,
)


@dataclass(frozen=True)
class ZaapTimings:
    focus_settle_ms: int = 10
    activate_attempts: int = 5
    activate_retry_ms: int = 2
    open_wait_ms: int = 1200
    click_settle_ms: int = 250
    submit_settle_ms: int = 70
    input_click_down_ms: int = 1
    input_double_gap_ms: int = 5
    reliable_click_pre_ms: int = 35
    reliable_click_post_ms: int = 25


@dataclass(frozen=True)
class MacroTimings:
    click_focus_settle_ms: int
    input_click_down_ms: int
    input_double_gap_ms: int
    travel_focus_settle_ms: int
    activate_min_settle_ms: int
    activate_retry_ms: int
    activate_attempts: int
    switch_client_settle_ms: int
    switch_click_down_ms: int
    switch_click_post_up_ms: int
    switch_background_pre_click_ms: int
    switch_background_post_up_ms: int
    switch_humanize_min_ms: int
    switch_humanize_max_ms: int
    auto_group_chat_open_ms: int
    auto_group_key_step_ms: int
    auto_group_paste_settle_ms: int
    auto_group_invite_gap_ms: int
    movement_key_hold_ms: int


@dataclass(frozen=True)
class AtlasClient:
    index: int
    label: str
    name: str
    handle: int
    binding: str = ""
    primary: bool = False

    @property
    def display_name(self) -> str:
        return self.name or self.label or f"Personnage {self.index}"


@dataclass(frozen=True)
class AtlasSettings:
    clients: tuple[AtlasClient, ...]
    switch_character_enabled: bool
    switch_click_enabled: bool
    switch_click_hotkey: str
    switch_double_click_enabled: bool
    switch_double_click_hotkey: str
    movement_enabled: bool
    stop_hotkey: str
    script_speed: str
    debug_enabled: bool
    travel_text: str
    primary_handle: int
    zaap_click_position: tuple[int, int]
    zaap_click_ratios: tuple[float, float] | None
    timings: MacroTimings
    zaap_timings: ZaapTimings

    def client_by_handle(self, hwnd: int) -> AtlasClient | None:
        for client in self.clients:
            if int(client.handle) == int(hwnd):
                return client
        return None

    def preferred_client(self) -> AtlasClient | None:
        if self.primary_handle:
            client = self.client_by_handle(self.primary_handle)
            if client is not None:
                return client
        for client in self.clients:
            if client.primary:
                return client
        return self.clients[0] if self.clients else None


def normalize_script_speed(value: Any) -> str:
    return "rapide" if str(value or "").strip().casefold() in {"rapide", "fast"} else "normal"


def timings_for_speed(speed: str) -> MacroTimings:
    if normalize_script_speed(speed) == "rapide":
        return MacroTimings(
            click_focus_settle_ms=8,
            input_click_down_ms=1,
            input_double_gap_ms=5,
            travel_focus_settle_ms=12,
            activate_min_settle_ms=6,
            activate_retry_ms=12,
            activate_attempts=8,
            switch_client_settle_ms=0,
            switch_click_down_ms=1,
            switch_click_post_up_ms=2,
            switch_background_pre_click_ms=18,
            switch_background_post_up_ms=5,
            switch_humanize_min_ms=4,
            switch_humanize_max_ms=9,
            auto_group_chat_open_ms=45,
            auto_group_key_step_ms=12,
            auto_group_paste_settle_ms=45,
            auto_group_invite_gap_ms=140,
            movement_key_hold_ms=18,
        )
    return MacroTimings(
        click_focus_settle_ms=16,
        input_click_down_ms=1,
        input_double_gap_ms=8,
        travel_focus_settle_ms=24,
        activate_min_settle_ms=10,
        activate_retry_ms=18,
        activate_attempts=8,
        switch_client_settle_ms=0,
        switch_click_down_ms=1,
        switch_click_post_up_ms=0,
        switch_background_pre_click_ms=35,
        switch_background_post_up_ms=25,
        switch_humanize_min_ms=4,
        switch_humanize_max_ms=9,
        auto_group_chat_open_ms=80,
        auto_group_key_step_ms=20,
        auto_group_paste_settle_ms=80,
        auto_group_invite_gap_ms=220,
        movement_key_hold_ms=30,
    )


def read_json_file(path: Path, default: Any) -> Any:
    return read_json_resilient(path, default)


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "y", "on", "oui", "vrai"}:
        return True
    if text in {"0", "false", "no", "n", "off", "non", "faux", ""}:
        return False
    return default


def load_profile_payload() -> dict[str, Any]:
    payload = read_json_file(PROFILE_FILE, default_profiles())
    if not isinstance(payload, dict):
        payload = default_profiles()
    legacy_debug_key = "".join(["__mode_debug_", "a", "h", "k__"])
    if legacy_debug_key in payload and KEY_DEBUG_MODE not in payload:
        payload[KEY_DEBUG_MODE] = payload.get(legacy_debug_key)
    payload.pop(legacy_debug_key, None)
    payload.pop(KEY_TRAVEL_TEXT, None)
    merged = default_profiles()
    merged.update(payload)
    return merged


def load_settings() -> AtlasSettings:
    profile = load_profile_payload()
    index_payload = read_json_file(CLIENT_INDEX_JSON, {})
    if not isinstance(index_payload, dict):
        index_payload = {}
    global_hotkeys = index_payload.get("global_hotkeys")
    if not isinstance(global_hotkeys, dict):
        global_hotkeys = {}

    speed = normalize_script_speed(global_hotkeys.get("script_speed", profile.get(KEY_SCRIPT_SPEED, "normal")))
    clients: list[AtlasClient] = []
    for raw in index_payload.get("clients", []):
        if not isinstance(raw, dict):
            continue
        handle = int_value(raw.get("handle"))
        if handle <= 0:
            continue
        index = int_value(raw.get("index"), len(clients) + 1)
        binding = str(raw.get("binding") or "").strip().upper()
        binding_explicit = bool_value(raw.get("binding_explicit"), bool(binding))
        clients.append(
            AtlasClient(
                index=index,
                label=str(raw.get("label") or f"Personnage {index}").strip(),
                name=str(raw.get("name") or "").strip(),
                handle=handle,
                binding=binding if binding_explicit else "",
                primary=bool_value(raw.get("primary"), False),
            )
        )

    primary_handle = int_value(global_hotkeys.get("primary_handle"))
    if primary_handle <= 0:
        primary_token = str(profile.get(KEY_PRIMARY_WINDOW, "")).strip()
        if primary_token.startswith("hwnd:"):
            primary_handle = int_value(primary_token[5:])

    zaap_position = parse_zaap_click_position(
        profile.get(KEY_ZAAP_CLICK_POSITION),
        (
            int_value(global_hotkeys.get("zaap_click_x"), ZAAP_CLICK_X),
            int_value(global_hotkeys.get("zaap_click_y"), ZAAP_CLICK_Y),
        ),
    )

    return AtlasSettings(
        clients=tuple(clients),
        switch_character_enabled=profile_bool(profile, KEY_SWITCH_CHARACTER, True)
        and bool_value(global_hotkeys.get("enabled"), True),
        switch_click_enabled=profile_bool(profile, KEY_SWITCH_CLICK, False)
        and bool_value(global_hotkeys.get("click_enabled"), profile_bool(profile, KEY_SWITCH_CLICK, False)),
        switch_click_hotkey=str(global_hotkeys.get("click_hotkey") or profile.get(KEY_CLICK_HOTKEY, "")).strip().upper(),
        switch_double_click_enabled=profile_bool(profile, KEY_SWITCH_DOUBLE_CLICK, False)
        and bool_value(
            global_hotkeys.get("double_click_enabled"),
            profile_bool(profile, KEY_SWITCH_DOUBLE_CLICK, False),
        ),
        switch_double_click_hotkey=str(
            global_hotkeys.get("double_click_hotkey") or profile.get(KEY_DOUBLE_CLICK_HOTKEY, "")
        )
        .strip()
        .upper(),
        movement_enabled=profile_bool(profile, KEY_SWITCH_MOVEMENT, False)
        and bool_value(global_hotkeys.get("movement_enabled"), profile_bool(profile, KEY_SWITCH_MOVEMENT, False)),
        stop_hotkey=str(global_hotkeys.get("stop_script_hotkey") or profile.get(KEY_STOP_SCRIPT_HOTKEY, "")).strip().upper(),
        script_speed=speed,
        debug_enabled=profile_bool(profile, KEY_DEBUG_MODE, False)
        or bool_value(global_hotkeys.get("debug_enabled"), False),
        travel_text="",
        primary_handle=primary_handle,
        zaap_click_position=zaap_position,
        zaap_click_ratios=read_zaap_button_ratios(),
        timings=timings_for_speed(speed),
        zaap_timings=ZaapTimings(),
    )


def assert_zaap_timings_unchanged(settings: AtlasSettings | None = None) -> bool:
    timings = (settings or load_settings()).zaap_timings
    return timings == ZaapTimings()
