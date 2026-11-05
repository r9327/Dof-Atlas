from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from app.constants import (
    CLIENT_INDEX_JSON,
    KEY_CLICK_HOTKEY,
    KEY_ORGANIZER_MACRO_MODE,
    KEY_DEBUG_MODE,
    KEY_DOUBLE_CLICK_HOTKEY,
    KEY_PRIMARY_WINDOW,
    KEY_SCRIPT_SPEED,
    KEY_STOP_SCRIPT_HOTKEY,
    KEY_SCRIPT_SPEED_SCHEMA,
    KEY_NEXT_CHARACTER_HOTKEY,
    KEY_RADIAL_ENABLED,
    KEY_RADIAL_HOTKEY,
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
    character_key: str = ""

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
    macro_mode: str = "macro"
    next_character_hotkey: str = ""
    radial_hotkey: str = ""
    radial_enabled: bool = True

    def client_by_handle(self, hwnd: int) -> AtlasClient | None:
        # The persisted compatibility roster can contain corrupt HWNDs.
        # Reject ambiguous/overflowing values without losing other clients.
        if isinstance(hwnd, (bool, float)):
            return None
        try:
            sought = int(hwnd)
        except (TypeError, ValueError, OverflowError):
            return None
        if not 0 < sought <= (2**64 - 1):
            return None
        for client in self.clients:
            raw = client.handle
            if isinstance(raw, (bool, float)):
                continue
            try:
                handle = int(raw)
            except (TypeError, ValueError, OverflowError):
                continue
            if handle == sought:
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


def normalize_script_speed(value: Any, *, legacy: bool = False) -> str:
    """Normalize persisted v1 speed names without speeding up old profiles.

    Legacy Normal was deliberately conservative -> Classique.
    Legacy Rapide used the v1 fast preset -> new Normal (same timings).
    Versioned v2 labels are unambiguous and do not need conversion.
    """
    name = str(value or "").strip().casefold()
    if legacy and name in {"rapide", "fast"}:
        return "normal"
    if legacy and name in {"normal", ""}:
        return "classique"
    if name in {"instantane", "instantané", "instant"}:
        return "instantane"
    if name in {"rapide", "fast"}:
        return "rapide"
    if name == "normal":
        return "normal"
    return "classique"


def timings_for_speed(speed: str) -> MacroTimings:
    mode = normalize_script_speed(speed)
    if mode == "instantane":
        # Unity click reliability remains protected by sender-side 35ms DOWN
        # and 50ms hover floors even in this optional fastest preset.
        return replace(
            timings_for_speed("normal"),
            click_focus_settle_ms=4, input_double_gap_ms=4,
            travel_focus_settle_ms=6, activate_min_settle_ms=5,
            activate_retry_ms=8, activate_attempts=5,
            switch_background_pre_click_ms=10, switch_background_post_up_ms=2,
            auto_group_chat_open_ms=25, auto_group_key_step_ms=8,
            auto_group_paste_settle_ms=25, auto_group_invite_gap_ms=65,
            movement_key_hold_ms=16,
        )
    if mode == "rapide":
        return replace(
            timings_for_speed("normal"),
            click_focus_settle_ms=6, input_double_gap_ms=4,
            travel_focus_settle_ms=10, activate_min_settle_ms=6,
            activate_retry_ms=10, activate_attempts=6,
            switch_background_pre_click_ms=14, switch_background_post_up_ms=3,
            auto_group_chat_open_ms=35, auto_group_key_step_ms=10,
            auto_group_paste_settle_ms=35, auto_group_invite_gap_ms=100,
            movement_key_hold_ms=17,
        )
    if mode == "normal":
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
    except (TypeError, ValueError, OverflowError):
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

    speed_schema = int_value(
        global_hotkeys.get("script_speed_schema", profile.get(KEY_SCRIPT_SPEED_SCHEMA)), 1,
    )
    speed = normalize_script_speed(
        global_hotkeys.get("script_speed", profile.get(KEY_SCRIPT_SPEED, "normal")),
        legacy=speed_schema < 2,
    )
    clients: list[AtlasClient] = []
    # A partially written/corrupt index must not crash runtime startup.
    raw_clients = index_payload.get("clients", ())
    if not isinstance(raw_clients, (list, tuple)):
        raw_clients = ()
    for raw in raw_clients:
        if not isinstance(raw, dict):
            continue
        raw_handle = raw.get("handle")
        # Never coerce 202.9, True or scientific notation to a native HWND:
        # the truncated value could alias another live DOFUS window.
        if type(raw_handle) is int:
            handle = raw_handle
        elif type(raw_handle) is str:
            token = raw_handle.strip()
            if not token or not token.isascii() or not token.isdecimal():
                continue
            handle = int_value(token)
        else:
            continue
        if not 0 < handle <= (2**64 - 1):
            continue
        raw_index = raw.get("index")
        if type(raw_index) is int and 1 <= raw_index <= 8:
            index = raw_index
        elif type(raw_index) is str:
            token = raw_index.strip()
            index = int_value(token) if (
                token.isascii() and token.isdecimal()
            ) else 0
            if not 1 <= index <= 8:
                index = len(clients) + 1
        else:
            index = len(clients) + 1
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
                character_key=str(raw.get("character_key") or "").strip(),
            )
        )

    raw_primary = global_hotkeys.get("primary_handle")
    if type(raw_primary) is int:
        primary_handle = raw_primary
    elif type(raw_primary) is str and (
        raw_primary.strip().isascii() and raw_primary.strip().isdecimal()
    ):
        primary_handle = int_value(raw_primary.strip())
    else:
        primary_handle = 0
    if not 0 < primary_handle <= (2**64 - 1):
        primary_handle = 0
        primary_token = str(profile.get(KEY_PRIMARY_WINDOW, "")).strip()
        if primary_token.startswith("hwnd:"):
            token = primary_token[5:]
            if token.isascii() and token.isdecimal():
                candidate = int_value(token)
                if 0 < candidate <= (2**64 - 1):
                    primary_handle = candidate

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
        macro_mode="mirror" if profile.get(KEY_ORGANIZER_MACRO_MODE) == "mirror" else "macro",
        next_character_hotkey=str(
            global_hotkeys.get("next_character_hotkey") or profile.get(KEY_NEXT_CHARACTER_HOTKEY, "")
        ).strip().upper(),
        radial_hotkey=str(profile.get(KEY_RADIAL_HOTKEY) or "").strip().upper(),
        radial_enabled=profile_bool(profile, KEY_RADIAL_ENABLED, True),
    )


def assert_zaap_timings_unchanged(settings: AtlasSettings | None = None) -> bool:
    timings = (settings or load_settings()).zaap_timings
    return timings == ZaapTimings()
